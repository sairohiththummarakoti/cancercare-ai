# CancerCare API contract

This loopback-only API serves synthetic fixtures. Demo roles are server-issued role sessions, not production authentication. Start with `POST /api/demo-session {"role":"oncologist"}` and send the returned token as `Authorization: Bearer ...` for mutations. `navigator` cannot review.

- `GET /api/demo-patients`: array of patient identity objects.
- `GET /api/patients/{id}/summary`: complete normalized synthetic chart plus FHIR-shaped Bundle.
- `GET /api/patients/{id}/documents`: document metadata array.
- `GET /api/patients/{id}/assessments`: saved assessment history for that patient. The summary endpoint also returns `latest_assessment` so review state survives a refresh.
- `GET /api/patients/{id}/export`: de-identified synthetic chart JSON.
- `GET /api/patients/{id}/documents/{document_id}/pdf`: actual synthetic PDF.
- `POST /api/patients/{id}/pathology`: multipart `file`, `synthetic_confirmed=true`. Returns `upload_id`, `patient_id`, `filename`, `extraction_mode`, `findings`, `processing_ms`, `warnings`, `contradictions`, `compatible`, `pdf_url`.
- `GET /api/patients/{id}/uploads/{upload_id}/pdf`: original upload while retained in bounded memory.
- `POST /api/assessments`: `{patient_id,upload_id,mode:'local'|'openai',api_consent:false,collection_id:'authorized-guidelines'}`. Local mode extracts real report facts but does not pretend to generate an LLM or guideline assessment.
- `GET /api/assessments/{id}?patient_id=...`: patient-bound assessment.
- `POST /api/assessments/{id}/review`: `{patient_id,action:'approve'|'edit'|'reject',expected_revision,notes,edited_text?}`. Notes required for edit/reject; approve requires reconciliation notes for contradictions.
- `GET /api/assessments/{id}/export?patient_id=...`: documentation export without patient name or DOB.
- `GET /api/knowledge-sources`: actual guideline/model/research corpus readiness.
- `POST /api/research-search`: `{query,top_k:5,disease?}` returns real local MedGUIDE search matches, separately labeled generated research context. It never supplies treatment evidence.
- `GET /api/health`: service status.

`findings` uses `PathologyFindings`: cancer_type, histological_diagnosis, grade, tumor_size and stage_tnm are `{value,quote}`; biomarkers are `{name,value,quote}[]`, other_findings `{value,quote}[]`, missing_information `string[]`. Unknown values are `Not available in report`.

Assessment fields: assessment_id, patient_id, upload_id, status, revision, created_at, processing_ms, mode, generation_mode, findings, clinical_summary, missing_information, pathway_considerations, evidence, warnings, contradictions, source_status, clinician_edit, review_notes, audit, revision_history, disclaimer. Status is pending_clinician_review, edited, approved_for_documentation or rejected. Generation mode is local_factual_summary, openai_extraction_only or openai_grounded. Pathway considerations retain validated citation chunk IDs and quotations. Evidence contains id/title/publisher/version/location/text/score/url. `source_status` is unavailable, available or no_matches. Audit entries contain action/reviewer/role/at/notes/revision. Revision history preserves documentation text at each review revision.

An uploaded report is never merged into chart fixtures. Identity/cancer-site conflicts make it incompatible; other contradictory findings require clinician reconciliation. Source metadata comes from the real local manifest. Every source must declare `authorized: true`, `allow_external_processing: true`, `version_verified: true`, and a publisher before external guideline processing is enabled. No treatment-order endpoints exist.

Source document URLs bind to the filename, content checksum and declared version. A changed source invalidates an old URL rather than serving a new document under an old citation. Exports recursively remove known synthetic chart names, MRNs and DOBs, including in clinician edits and revision history; they include a notice that arbitrary unrecognized identifiers in free text cannot be guaranteed absent.
