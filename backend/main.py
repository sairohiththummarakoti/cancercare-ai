"""FastAPI adapter for the local synthetic CancerCare clinical workspace."""
from __future__ import annotations

import json
import asyncio
from contextlib import asynccontextmanager, suppress
import secrets
import time
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import ROOT, make_client, settings
from pathology import MAX_PDF_BYTES, ClinicalAPIError, PDFExtractionError, extract_findings, extract_pdf_text
from rag import RagError, build_index, retrieve
from schemas import PathologyFindings
from treatment import generate_assessment
from backend.extraction import compare_with_chart, extract_local_findings, factual_summary
from backend.exports import deidentified_export
from backend.knowledge import inspect_authorized_sources, source_document
from backend.store import Store, timestamp


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SessionInput(StrictModel):
    role: Literal["oncologist", "navigator"]


class AssessmentInput(StrictModel):
    patient_id: str = Field(min_length=1, max_length=80)
    upload_id: str = Field(min_length=1, max_length=80)
    mode: Literal["local", "openai"] = "local"
    api_consent: bool = False
    collection_id: Literal["authorized-guidelines"] = "authorized-guidelines"


class ReviewInput(StrictModel):
    patient_id: str = Field(min_length=1, max_length=80)
    action: Literal["approve", "edit", "reject"]
    expected_revision: int = Field(ge=1)
    notes: str = Field(default="", max_length=4000)
    edited_text: str | None = Field(default=None, max_length=12000)

    @model_validator(mode="after")
    def review_content(self):
        self.notes = self.notes.strip()
        if self.action in {"edit", "reject"} and not self.notes:
            raise ValueError("Review rationale is required for editing or rejection.")
        if self.action == "edit" and (not self.edited_text or not self.edited_text.strip()):
            raise ValueError("Enter the edited documentation text.")
        if self.edited_text:
            self.edited_text = self.edited_text.strip()
        return self


class ResearchInput(StrictModel):
    query: str = Field(min_length=2, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)
    disease: str | None = Field(default=None, max_length=60)


def create_app(db_path: Path | None = None, guideline_dir: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        async def cleanup():
            while True:
                await asyncio.sleep(30)
                application.state.store.purge_expired()
        cleanup_task = asyncio.create_task(cleanup())
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task

    api = FastAPI(title="CancerCare AI — Synthetic Clinical Workspace", version="1.0.0", lifespan=lifespan)
    api.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver", "[::1]"])
    api.state.store = Store(db_path or ROOT / ".cache" / "ehr" / "reviews.sqlite3")
    api.state.guideline_dir = guideline_dir or ROOT / "guidelines"

    @api.middleware("http")
    async def local_security_headers(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8000", "http://localhost:8000"}:
            return JSONResponse({"detail": "This local demonstration only accepts same-workspace requests."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @api.exception_handler(RequestValidationError)
    async def safe_validation(_request, _error):
        return JSONResponse(status_code=422, content={"detail": "Invalid request. Check required fields, review rationale, and supported values."})

    @api.exception_handler(Exception)
    async def safe_failure(_request, _error):
        return JSONResponse(status_code=500, content={"detail": "The local service could not complete this request. Retry or check the local setup."})

    def actor(authorization: str | None = Header(default=None)):
        token = authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
        session = api.state.store.actor(token)
        if not session:
            raise HTTPException(401, "Choose a demo workspace role to start a session.")
        return session

    def chart(patient_id: str):
        from backend.fixtures import get_summary
        value = get_summary(patient_id)
        if value is None:
            raise HTTPException(404, "Synthetic patient not found.")
        return value

    def stored_assessment(assessment_id: str, patient_id: str):
        chart(patient_id)
        result = api.state.store.get(assessment_id, patient_id)
        if not result:
            raise HTTPException(404, "Assessment not found for the selected patient.")
        return result

    @api.get("/api/health")
    def health():
        return {"status": "ok", "service": "cancercare-ai-ehr", "synthetic_only": True, "version": "1.0.0"}

    @api.post("/api/demo-session")
    def demo_session(body: SessionInput):
        return api.state.store.session(body.role)

    @api.get("/api/demo-patients")
    def patients():
        from backend.fixtures import list_patients
        return list_patients()

    @api.get("/api/patients/{patient_id}/summary")
    def summary(patient_id: str):
        result = chart(patient_id)
        history = api.state.store.history(patient_id)
        result["latest_assessment"] = history[0] if history else None
        return result

    @api.get("/api/patients/{patient_id}/assessments")
    def assessment_history(patient_id: str):
        chart(patient_id)
        return [{key: item[key] for key in ("assessment_id", "status", "revision", "created_at", "generation_mode")} for item in api.state.store.history(patient_id)]

    @api.get("/api/patients/{patient_id}/documents")
    def documents(patient_id: str):
        return chart(patient_id)["documents"]

    @api.get("/api/patients/{patient_id}/export")
    def export_chart(patient_id: str):
        patient_chart = chart(patient_id)
        payload = {key: patient_chart[key] for key in ("profile", "biomarkers", "history", "allergies", "medications", "timeline", "gaps")}
        payload["synthetic_only"] = True
        payload["disclaimer"] = "Synthetic documentation only. No treatment orders or prescriptions."
        return Response(json.dumps(deidentified_export(payload), indent=2), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="cancercare-synthetic-summary.json"'})

    @api.get("/api/patients/{patient_id}/documents/{document_id}/pdf")
    def document_pdf(patient_id: str, document_id: str):
        from backend.fixtures import get_document_path
        chart(patient_id)
        path = get_document_path(patient_id, document_id)
        if not path or not Path(path).is_file():
            raise HTTPException(404, "Synthetic document not found.")
        return FileResponse(path, media_type="application/pdf", filename=Path(path).name, content_disposition_type="inline")

    @api.post("/api/patients/{patient_id}/pathology")
    async def upload_pathology(patient_id: str, request: Request, _actor=Depends(actor)):
        patient_chart = chart(patient_id)
        content_type = request.headers.get("content-type", "")
        if not content_type.startswith("multipart/form-data"):
            raise HTTPException(415, "Upload a PDF using a multipart form.")
        maximum = MAX_PDF_BYTES + 64 * 1024
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > maximum):
            raise HTTPException(413, "The upload exceeds the 10 MB PDF limit.")
        async def bounded_stream():
            total = 0
            async for chunk in request.stream():
                total += len(chunk)
                if total > maximum:
                    raise HTTPException(413, "The upload exceeds the 10 MB PDF limit.")
                yield chunk
        # Starlette normally spools >1 MB to disk. This instance is bounded above
        # and its threshold is higher than the entire permitted multipart body.
        parser = MultiPartParser(request.headers, bounded_stream(), max_files=1, max_fields=2, max_part_size=maximum)
        parser.spool_max_size = maximum + 1
        try:
            form = await parser.parse()
        except MultiPartException:
            raise HTTPException(400, "Upload one PDF and confirm that it contains synthetic data.") from None
        try:
            upload = form.get("file")
            if not isinstance(upload, UploadFile):
                raise HTTPException(422, "Choose one PDF file.")
            if str(form.get("synthetic_confirmed", "")).lower() != "true":
                raise HTTPException(422, "Confirm this is a synthetic test report before uploading.")
            if not upload.filename or not upload.filename.lower().endswith(".pdf"):
                raise HTTPException(415, "Only PDF reports are supported.")
            raw = await upload.read(MAX_PDF_BYTES + 1)
            filename = Path(upload.filename.replace("\\", "/")).name[:180]
            if len(raw) > MAX_PDF_BYTES:
                raise HTTPException(413, "The PDF exceeds the 10 MB limit.")
        finally:
            await form.close()
        start = time.perf_counter()
        try:
            text = await run_in_threadpool(extract_pdf_text, raw)
        except PDFExtractionError as error:
            raise HTTPException(422, str(error)) from None
        if "synthetic" not in text.casefold():
            raise HTTPException(422, "This demo accepts only explicitly labeled synthetic reports. Use an included test PDF.")
        findings = extract_local_findings(text)
        contradictions = compare_with_chart(text, findings, patient_chart)
        upload_id = "upload-" + secrets.token_hex(16)
        result = {"upload_id": upload_id, "patient_id": patient_id, "filename": filename, "extraction_mode": "local_rules", "findings": findings.model_dump(),
                  "processing_ms": round((time.perf_counter() - start) * 1000), "warnings": ["Real PDF text extraction with a conservative local label parser. This is not LLM analysis; unsupported report formats remain unknown."],
                  "contradictions": contradictions, "compatible": not any(c["severity"] == "error" for c in contradictions),
                  "pdf_url": f"/api/patients/{patient_id}/uploads/{upload_id}/pdf"}
        api.state.store.add_upload(dict(result, pdf=raw, text=text))
        return result

    @api.get("/api/patients/{patient_id}/uploads/{upload_id}/pdf")
    def uploaded_pdf(patient_id: str, upload_id: str):
        chart(patient_id)
        uploaded = api.state.store.upload(upload_id, patient_id)
        if not uploaded:
            raise HTTPException(404, "Upload not found for this patient, or its one-hour memory retention has expired.")
        return Response(uploaded["pdf"], media_type="application/pdf", headers={"Content-Disposition": "inline"})

    @api.get("/api/knowledge-sources")
    def knowledge_sources():
        source = inspect_authorized_sources(api.state.guideline_dir)
        try:
            from medguide import read_pipeline_status
            research_ready = bool(read_pipeline_status()["indexed"])
        except Exception:
            research_ready = False
        live = bool(settings()["api_key"])
        return {"guidelines_available": source["available"], "live_model_available": live,
                "collections": [{"id": "authorized-guidelines", "title": "Authorized clinical guideline sources", "status": "available" if source["available"] else "unavailable",
                                 "document_count": len(source["documents"]), "reason": "; ".join(source["warnings"]) or "Authorized source metadata validated; retrieval runs when explicitly requested."}],
                "warnings": source["warnings"], "medguide": {"available": research_ready, "source_kind": "educational_mcqa"}}

    @api.get("/api/knowledge-sources/documents/{source_id}")
    def guideline_document(source_id: str):
        path = source_document(api.state.guideline_dir, source_id)
        if path is None:
            raise HTTPException(404, "Authorized source document not found.")
        return FileResponse(path, media_type="application/pdf" if path.suffix.lower() == ".pdf" else "text/plain", filename=path.name, content_disposition_type="inline")

    @api.post("/api/research-search")
    def research_search(body: ResearchInput, _reviewer=Depends(actor)):
        from medguide import find_related_cases, read_pipeline_status
        if not read_pipeline_status()["indexed"]:
            raise HTTPException(503, "The MedGUIDE research index is not built. Run its ingestion pipeline first.")
        began = time.perf_counter()
        try:
            matches = find_related_cases(body.query, top_k=body.top_k, disease=body.disease)
        except Exception:
            raise HTTPException(503, "The local research search could not complete. Check the saved index and embedding model.") from None
        return {"matches": matches, "processing_ms": round((time.perf_counter() - began) * 1000), "source_kind": "educational_mcqa",
                "disclaimer": "Generated research scenarios, not original clinical guidelines. Dataset labels can be inconsistent. Results do not authorize treatment and are never used as guideline evidence."}

    @api.post("/api/assessments")
    def assess(body: AssessmentInput, reviewer=Depends(actor)):
        patient_chart = chart(body.patient_id)
        upload = api.state.store.upload(body.upload_id, body.patient_id)
        if not upload:
            raise HTTPException(404, "Upload not found for this patient, or its one-hour memory retention has expired.")
        if not upload["compatible"]:
            raise HTTPException(409, "The report is incompatible with the selected patient. Resolve identity or cancer-site conflicts by uploading the correct report.")
        start = time.perf_counter()
        findings = PathologyFindings.model_validate(upload["findings"])
        source = inspect_authorized_sources(api.state.guideline_dir)
        evidence, pathways = [], []
        warnings = list(upload["warnings"])
        source_status = "unavailable"
        generation_mode = "local_factual_summary"
        if body.mode == "openai":
            cfg = settings()
            if not body.api_consent:
                raise HTTPException(422, "Explicit authorization is required before sending report text and authorized sources to OpenAI.")
            if not cfg["api_key"]:
                raise HTTPException(503, "OpenAI access is not configured. Local factual extraction remains available; no API or guideline output has been simulated.")
            try:
                client = make_client()
                findings = extract_findings(upload["text"], client, cfg["model"])
                if source["available"]:
                    index = build_index(api.state.guideline_dir, ROOT / ".cache" / "ehr-guidelines", client, cfg["embedding_model"])
                    from medguide import findings_search_query
                    evidence = retrieve(findings_search_query(findings), index, client, cfg["embedding_model"], top_k=5, min_similarity=cfg["min_similarity"])
                    for chunk in evidence:
                        chunk.update(source["metadata"].get(chunk["source_file"], {}))
                        if "PDF page " in chunk["location"]:
                            import re
                            page = re.search(r"PDF page (\d+)", chunk["location"])
                            if page:
                                chunk["url"] += "#page=" + page.group(1)
                    assessment = generate_assessment(findings, evidence, client, cfg["model"])
                    pathways = [pathway.model_dump() for pathway in assessment.pathways]
                    findings.missing_information = list(dict.fromkeys(findings.missing_information + assessment.missing_information))
                    warnings.extend(index.warnings + assessment.limitations)
                    source_status = "available" if evidence else "no_matches"
                    generation_mode = "openai_grounded" if pathways else "openai_extraction_only"
                else:
                    generation_mode = "openai_extraction_only"
            except (ClinicalAPIError, RagError, ValueError) as error:
                safe = str(error) if isinstance(error, (ClinicalAPIError, RagError)) else "Live analysis did not complete. Check local configuration and retry."
                raise HTTPException(502, safe) from None
        if not evidence:
            warnings.extend(source["warnings"])
            warnings.append("Guideline evidence unavailable. No guideline-grounded treatment pathway has been generated.")
            if body.mode == "local" and source["available"]:
                warnings.append("Local factual mode does not call external embedding or generation APIs. Choose authorized live analysis to search the configured guideline collection.")
        contradictions = compare_with_chart(upload["text"], findings, patient_chart)
        if any(item["severity"] == "error" for item in contradictions):
            raise HTTPException(409, "Extracted report findings conflict with the selected patient. No draft was saved.")
        if contradictions:
            pathways = []
            warnings.append("Treatment pathways are withheld because chart and report findings conflict. Reconcile the sources before making clinical decisions.")
        result = {"assessment_id": "assessment-" + secrets.token_hex(16), "patient_id": body.patient_id, "upload_id": body.upload_id,
                  "status": "pending_clinician_review", "revision": 1, "created_at": timestamp(), "processing_ms": round((time.perf_counter() - start) * 1000) + upload["processing_ms"],
                  "mode": body.mode, "generation_mode": generation_mode, "findings": findings.model_dump(), "clinical_summary": factual_summary(findings),
                  "missing_information": list(dict.fromkeys(findings.missing_information + patient_chart["gaps"])), "pathway_considerations": pathways,
                  "evidence": evidence, "warnings": list(dict.fromkeys(warnings)), "contradictions": contradictions, "source_status": source_status,
                  "clinician_edit": None, "review_notes": "", "audit": [{"action": "created", "reviewer": reviewer["reviewer"], "role": reviewer["role"], "at": timestamp(), "notes": "Synthetic documentation draft created.", "revision": 1}],
                  "disclaimer": "Synthetic research demonstration. Draft documentation only; no treatment orders, prescriptions, or clinical validation."}
        api.state.store.save(result)
        return result

    @api.get("/api/assessments/{assessment_id}")
    def get_assessment(assessment_id: str, patient_id: str = Query(min_length=1, max_length=80)):
        return stored_assessment(assessment_id, patient_id)

    @api.post("/api/assessments/{assessment_id}/review")
    def review(assessment_id: str, body: ReviewInput, reviewer=Depends(actor)):
        if reviewer["role"] != "oncologist":
            raise HTTPException(403, "Only the demo oncologist role can edit, approve, or reject documentation.")
        chart(body.patient_id)
        try:
            return api.state.store.review(assessment_id, body.patient_id, body.expected_revision, body.action, body.notes, body.edited_text, reviewer)
        except KeyError:
            raise HTTPException(404, "Assessment not found for the selected patient.") from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @api.get("/api/assessments/{assessment_id}/export")
    def export_assessment(assessment_id: str, patient_id: str = Query(min_length=1, max_length=80)):
        item = stored_assessment(assessment_id, patient_id)
        return Response(json.dumps(deidentified_export(item), indent=2), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="cancercare-synthetic-review.json"'})

    return api


app = create_app()
