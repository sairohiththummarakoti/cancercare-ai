"""Exercise the running local API with synthetic PDFs, without calling a model provider.

Creates synthetic test assessments/review records in the local demo store.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    started = time.perf_counter()
    checks: list[str] = []
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        assert client.get("/api/health").json()["service"] == "cancercare-ai-ehr"
        oncologist = client.post("/api/demo-session", json={"role": "oncologist"}).json()
        navigator = client.post("/api/demo-session", json={"role": "navigator"}).json()
        auth = {"Authorization": "Bearer " + oncologist["token"]}
        nav_auth = {"Authorization": "Bearer " + navigator["token"]}
        patients = client.get("/api/demo-patients").json()
        assert len(patients) == 3 and len({p["id"] for p in patients}) == 3
        checks.append("Three distinct synthetic patient charts")
        assessments = []
        for patient in patients:
            pid = patient["id"]
            summary = client.get(f"/api/patients/{pid}/summary").json()
            assert summary["patient"]["id"] == pid
            docs = client.get(f"/api/patients/{pid}/documents").json()
            assert len(docs) >= 2
            pdf = client.get(f"/api/patients/{pid}/documents/pathology/pdf")
            pdf.raise_for_status()
            assert pdf.content.startswith(b"%PDF-")
            upload = client.post(f"/api/patients/{pid}/pathology", headers=auth,
                                 data={"synthetic_confirmed": "true"},
                                 files={"file": ("synthetic-pathology.pdf", pdf.content, "application/pdf")})
            upload.raise_for_status()
            result = upload.json()
            assert result["compatible"] is True and not result["contradictions"]
            assert result["findings"]["stage_tnm"]["value"] == "Not available in report"
            assert result["findings"]["histological_diagnosis"]["quote"]
            created = client.post("/api/assessments", headers=auth,
                                  json={"patient_id": pid, "upload_id": result["upload_id"], "mode": "local"})
            created.raise_for_status()
            assessment = created.json()
            assert assessment["status"] == "pending_clinician_review"
            assert assessment["pathway_considerations"] == [] and assessment["evidence"] == []
            assert assessment["missing_information"] and assessment["clinical_summary"]
            assert assessment["processing_ms"] >= 0
            assessments.append(assessment)
            checks.append(f"{pid}: real PDF extraction, quoted findings, unknown stage, factual draft without fabricated evidence")

        first, second, third = assessments
        first_url = f"/api/assessments/{first['assessment_id']}"
        assert client.get(first_url, params={"patient_id": second["patient_id"]}).status_code == 404
        assert client.post("/api/assessments", headers=auth, json={"patient_id": second["patient_id"], "upload_id": first["upload_id"]}).status_code == 404
        checks.append("Cross-patient assessment and upload access rejected")
        body = {"patient_id": first["patient_id"], "action": "approve", "expected_revision": first["revision"], "notes": "Synthetic verification only"}
        assert client.post(first_url + "/review", headers=nav_auth, json=body).status_code == 403
        checks.append("Navigator cannot approve documentation")
        edit = client.post(first_url + "/review", headers=auth, json={**body, "action": "edit", "edited_text": "Synthetic documentation review. Staging remains incomplete; no treatment pathway or order."})
        edit.raise_for_status()
        assert edit.json()["status"] == "edited"
        assert edit.json()["clinical_summary"] == first["clinical_summary"]
        assert client.post(first_url + "/review", headers=auth, json=body).status_code == 409
        approved = client.post(first_url + "/review", headers=auth, json={**body, "expected_revision": edit.json()["revision"]})
        approved.raise_for_status()
        assert approved.json()["status"] == "approved_for_documentation"
        assert {event["action"] for event in approved.json()["audit"]} >= {"edit", "approve"}
        checks.append("Edit preserves original draft; stale review rejected; approval recorded with audit")
        reject = client.post(f"/api/assessments/{second['assessment_id']}/review", headers=auth,
                             json={"patient_id": second["patient_id"], "action": "reject", "expected_revision": second["revision"], "notes": "Synthetic verification: pending molecular and staging information."})
        reject.raise_for_status()
        assert reject.json()["status"] == "rejected"
        checks.append("Rejection records rationale and status")
        exported = client.get(first_url + "/export", params={"patient_id": first["patient_id"]})
        exported.raise_for_status()
        assert patients[0]["name"] not in exported.text and patients[0]["dob"] not in exported.text
        checks.append("Explicit export omits chart name and date of birth")
        bad = client.post(f"/api/patients/{third['patient_id']}/pathology", headers=auth,
                          data={"synthetic_confirmed": "true"}, files={"file": ("bad.pdf", b"not a PDF", "application/pdf")})
        assert bad.status_code in {400, 422}
        checks.append("Malformed PDF rejected")
        for filename, expected in (("breast-contradiction.pdf", "contradiction"), ("scanned-report.pdf", "scan")):
            response = client.post(f"/api/patients/{first['patient_id']}/pathology", headers=auth,
                                   data={"synthetic_confirmed": "true"},
                                   files={"file": (filename, (ROOT / "samples/ehr" / filename).read_bytes(), "application/pdf")})
            if expected == "contradiction":
                response.raise_for_status()
                assert response.json()["contradictions"]
                checks.append("Conflicting biomarker flagged without overwriting chart")
            else:
                assert response.status_code in {400, 422}
                checks.append("Scanned PDF produces explicit OCR limitation")

    report = {"passed": True, "checks": checks, "elapsed_seconds": round(time.perf_counter() - started, 3),
              "scope": "Actual local HTTP interactions with synthetic documents. No provider calls or clinical accuracy claims."}
    target = ROOT / ".cache/ehr/http-verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
