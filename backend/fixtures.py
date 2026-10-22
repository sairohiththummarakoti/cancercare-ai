"""Synthetic chart fixtures shaped after FHIR R4, not an EHR connection.

All records are invented for the supplied UI prototype. The chart snapshot is
fixed at 2026-10-21; absent facts stay absent. Returned objects are deep copies.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "samples" / "ehr"
SNAPSHOT_DATE = "2026-10-21"

_CASES = [
    {
        "id": "DEMO-00248", "name": "Ava Mitchell", "initials": "AM", "age": 54,
        "sex": "Female", "dob": "1972-04-18", "cancer_type": "Breast cancer",
        "diagnosis": "Invasive ductal carcinoma of the left breast", "diagnosis_date": "2026-10-14",
        "histology": "Invasive ductal carcinoma", "site": "Left breast", "grade": "Nottingham grade 2",
        "measurement": "2.1 cm", "measurement_source": "Synthetic breast imaging, 2026-10-16; not pathologic size",
        "markers": [("ER", "Positive 92%", "documented"), ("PR", "Positive 65%", "documented"),
                    ("HER2", "IHC 0 / negative", "documented"), ("Ki-67", "18%", "documented")],
        "allergies": [{"substance": "Sulfa", "reaction": "Rash"}],
        "history": "Hypertension; no prior cancer treatment recorded.",
        "social": "Social history is incomplete in the synthetic chart.",
        "gaps": ["Clinical TNM staging and nodal status", "Final imaging review and multidisciplinary context",
                 "Patient goals, comorbidities and performance status"],
        "events": [("2026-10-14", "Pathology diagnosis documented", "Core biopsy with carcinoma diagnosis.", "completed"),
                   ("2026-10-16", "Imaging report available", "Lesion measurement documented; not a pathologic tumor size.", "completed"),
                   ("2026-10-19", "Navigator intake", "Referral and care coordination initiated.", "completed"),
                   ("Pending", "Oncology review", "Requires complete clinical context. No treatment has been selected or ordered.", "pending")],
        "documents": [("pathology", "Pathology - core biopsy", "2026-10-14", "Pathology", "breast-pathology.pdf"),
                      ("imaging", "Breast imaging summary", "2026-10-16", "Imaging", "breast-imaging.pdf")],
    },
    {
        "id": "DEMO-00352", "name": "Noah Reynolds", "initials": "NR", "age": 63,
        "sex": "Male", "dob": "1963-09-04", "cancer_type": "Lung cancer",
        "diagnosis": "Non-small cell lung cancer - adenocarcinoma", "diagnosis_date": "2026-10-12",
        "histology": "Pulmonary adenocarcinoma", "site": "Right upper lobe", "grade": "Not documented",
        "measurement": "3.4 cm", "measurement_source": "Synthetic chest CT, 2026-10-14; not pathologic size",
        "markers": [("EGFR", "Pending", "pending"), ("ALK", "Pending", "pending"),
                    ("PD-L1", "Pending", "pending"), ("ROS1", "Pending", "pending")],
        "allergies": [{"substance": "None documented", "reaction": "Allergy history requires confirmation"}],
        "history": "COPD; hypertension; no prior cancer treatment recorded.",
        "social": "Former tobacco use documented. Quantity and quit date are not available.",
        "gaps": ["Complete TNM stage and PET/CT review", "Molecular panel and PD-L1 results",
                 "Performance status and complete comorbidity review"],
        "events": [("2026-10-12", "Pathology diagnosis documented", "Lung biopsy reported adenocarcinoma.", "completed"),
                   ("2026-10-14", "Chest CT available", "Pulmonary lesion documented; complete staging is unavailable.", "completed"),
                   ("2026-10-16", "Molecular workup pending", "Requested molecular results have not been documented.", "pending"),
                   ("Pending", "Oncology review", "Requires staging and molecular results. No treatment order exists.", "pending")],
        "documents": [("pathology", "Pathology - lung biopsy", "2026-10-12", "Pathology", "lung-pathology.pdf"),
                      ("imaging", "Chest CT summary", "2026-10-14", "Imaging", "lung-imaging.pdf")],
    },
    {
        "id": "DEMO-00419", "name": "Maya Ellis", "initials": "ME", "age": 59,
        "sex": "Female", "dob": "1967-07-11", "cancer_type": "Colon cancer",
        "diagnosis": "Colonic adenocarcinoma", "diagnosis_date": "2026-10-16",
        "histology": "Moderately differentiated adenocarcinoma", "site": "Ascending colon", "grade": "Moderately differentiated",
        "measurement": "Not available", "measurement_source": "No definitive measurement in the synthetic pathology excerpt",
        "markers": [("MMR", "Pending", "pending"), ("MSI", "Pending", "pending"),
                    ("KRAS", "Not ordered", "not_ordered"), ("BRAF", "Not ordered", "not_ordered")],
        "allergies": [{"substance": "Penicillin", "reaction": "Rash"}],
        "history": "Type 2 diabetes; no prior cancer treatment recorded.",
        "social": "Social history is incomplete in the synthetic chart.",
        "gaps": ["Clinical staging including distant metastasis evaluation", "MMR/MSI testing results",
                 "Surgical evaluation and complete medical history"],
        "events": [("2026-10-16", "Biopsy diagnosis documented", "Colonoscopy specimen confirmed carcinoma.", "completed"),
                   ("2026-10-17", "Oncology referral requested", "Clinical care navigation initiated.", "completed"),
                   ("2026-10-20", "Additional staging pending", "Imaging and biomarker workup are incomplete.", "pending"),
                   ("Pending", "Multidisciplinary review", "Requires full clinical assessment. No treatment order exists.", "pending")],
        "documents": [("pathology", "Pathology - colon biopsy", "2026-10-16", "Pathology", "colon-pathology.pdf"),
                      ("endoscopy", "Colonoscopy summary", "2026-10-16", "Endoscopy", "colon-endoscopy.pdf")],
    },
]


def _patient(case: dict) -> dict:
    return {key: case[key] for key in ("id", "name", "initials", "age", "sex", "dob", "cancer_type", "diagnosis")} | {
        "mrn": case["id"], "synthetic": True, "snapshot_date": SNAPSHOT_DATE,
    }


def _documents(case: dict) -> list[dict]:
    return [{"id": identity, "title": title, "date": date, "type": kind,
             "status": "Final" if kind == "Pathology" else "Available", "author": "Synthetic clinical record",
             "url": f"/api/patients/{case['id']}/documents/{identity}/pdf", "synthetic": True}
            for identity, title, date, kind, _filename in case["documents"]]


def _fhir_bundle(case: dict) -> dict:
    """Collection bundle with relative references; not profile-validated FHIR."""
    pid = case["id"]
    subject = {"reference": f"Patient/{pid}"}
    resources = []
    tag = {"system": "https://cancercare.example/tags", "code": "synthetic", "display": "Synthetic demonstration data"}

    def add(kind, resource_id, **fields):
        resource = {"resourceType": kind, "id": resource_id, "meta": {"versionId": "1", "tag": [tag]}, **fields}
        resources.append(resource)
        return {"reference": f"{kind}/{resource_id}"}

    given, family = case["name"].split(" ", 1)
    add("Patient", pid, active=True, identifier=[{"system": "https://cancercare.example/demo-mrn", "value": pid}],
        name=[{"use": "usual", "text": case["name"], "family": family, "given": [given]}],
        gender=case["sex"].lower(), birthDate=case["dob"])
    add("Condition", f"{pid}-diagnosis", subject=subject, code={"text": case["diagnosis"]},
        clinicalStatus={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
        verificationStatus={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
        onsetDateTime=case["diagnosis_date"], recordedDate=case["diagnosis_date"], bodySite=[{"text": case["site"]}],
        note=[{"text": "Synthetic diagnosis. Clinical stage and TNM are not established."}])
    observed = []
    for name, value, state in case["markers"]:
        fields = {"status": "final" if state == "documented" else "registered", "code": {"text": name},
                  "subject": subject, "effectiveDateTime": case["diagnosis_date"],
                  "note": [{"text": f"Synthetic chart status: {value}"}]}
        if state == "documented":
            fields["valueString"] = value
        else:
            fields["dataAbsentReason"] = {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
                                                        "code": "temp-unknown" if state == "pending" else "not-performed"}], "text": value}
        observed.append(add("Observation", f"{pid}-{name.lower().replace('-', '')}", **fields))
    add("Observation", f"{pid}-stage", status="registered", code={"text": "Clinical stage / TNM"}, subject=subject,
        dataAbsentReason={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/data-absent-reason", "code": "unknown"}]})
    for doc in _documents(case):
        report_ref = add("DiagnosticReport", f"{pid}-{doc['id']}-report", status="final", code={"text": doc["title"]},
                         subject=subject, effectiveDateTime=doc["date"],
                         result=observed if doc["type"] == "Pathology" else [],
                         conclusion=case["diagnosis"] if doc["type"] == "Pathology" else "See synthetic document; incomplete staging context.",
                         presentedForm=[{"contentType": "application/pdf", "url": doc["url"], "title": doc["title"]}])
        add("DocumentReference", f"{pid}-{doc['id']}-document", status="current", docStatus="final", subject=subject,
            type={"text": doc["type"]}, date=f"{doc['date']}T12:00:00Z", description="Synthetic document for software testing",
            content=[{"attachment": {"contentType": "application/pdf", "url": doc["url"], "title": doc["title"], "creation": doc["date"]}}],
            context={"related": [report_ref]})
    for i, allergy in enumerate(case["allergies"]):
        if allergy["substance"] == "None documented":
            continue  # Absence of documentation is not a negative allergy assessment.
        add("AllergyIntolerance", f"{pid}-allergy-{i}", patient=subject, code={"text": allergy["substance"]},
            clinicalStatus={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
            verificationStatus={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": "unconfirmed"}]},
            reaction=[{"manifestation": [{"text": allergy["reaction"]}]}], note=[{"text": "Synthetic chart; confirm allergy history."}])
    clinician = add("Practitioner", "demo-oncologist", name=[{"text": "Dr. E. Morgan (demo)"}])
    navigator = add("Practitioner", "demo-navigator", name=[{"text": "Jordan Lee, RN (demo)"}])
    add("CareTeam", f"{pid}-careteam", status="active", subject=subject, name="Synthetic oncology team",
        participant=[{"role": [{"text": "Oncologist"}], "member": clinician}, {"role": [{"text": "Nurse navigator"}], "member": navigator}])
    add("Encounter", f"{pid}-intake", status="finished", subject=subject,
        **{"class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"}},
        type=[{"text": "Synthetic oncology navigation intake"}], period={"start": "2026-10-19T10:00:00Z", "end": "2026-10-19T10:30:00Z"})
    add("List", f"{pid}-medications", status="current", mode="snapshot", subject=subject,
        code={"text": "Home medications"}, emptyReason={"coding": [{"system": "http://terminology.hl7.org/CodeSystem/list-empty-reason", "code": "unavailable"}]},
        note=[{"text": "Medication history is not reconciled. No MedicationStatement or MedicationRequest is asserted."}])
    for i, gap in enumerate(case["gaps"]):
        add("Task", f"{pid}-gap-{i}", status="requested", intent="proposal", description=gap,
            **{"for": subject}, owner=navigator, note=[{"text": "Synthetic information-gathering task; not a clinical order."}])
    add("Provenance", f"{pid}-fixture-provenance", target=[subject], recorded="2026-10-21T12:00:00Z",
        activity={"text": "Authored synthetic fixture"}, agent=[{"who": {"display": "CancerCare AI synthetic fixture generator"}}])
    return {"resourceType": "Bundle", "id": f"{pid}-chart", "type": "collection", "timestamp": "2026-10-21T12:00:00Z",
            "meta": {"tag": [tag]}, "entry": [{"fullUrl": f"https://cancercare.example/fhir/{r['resourceType']}/{r['id']}", "resource": r} for r in resources]}


def _summary(case: dict) -> dict:
    return {
        "patient": _patient(case),
        "profile": {"histology": case["histology"], "site": case["site"], "grade": case["grade"], "stage": "Not established",
                    "tumor_size": {"value": case["measurement"], "source": case["measurement_source"]},
                    "diagnosis_date": case["diagnosis_date"], "ecog": "Not available", "care_status": "Workup in progress",
                    "last_encounter": "2026-10-19"},
        "biomarkers": [{"name": n, "value": v, "status": s, "source": f"Synthetic pathology chart, {case['diagnosis_date']}"} for n, v, s in case["markers"]],
        "history": {"medical": case["history"], "family": "Family history is incomplete in the synthetic chart.", "social": case["social"]},
        "allergies": case["allergies"],
        "vitals": [{"name": label, "value": "Not documented"} for label in ("Blood pressure", "Heart rate", "Temperature", "Weight")],
        "medications": [{"name": "Home medication list", "status": "Not reconciled", "note": "Drug names, doses and frequency are not available. No treatment medications or orders are recorded."}],
        "care_team": [{"name": "Dr. E. Morgan", "role": "Oncologist (demo)"}, {"name": "Jordan Lee, RN", "role": "Nurse navigator (demo)"}],
        "timeline": [{"id": f"{case['id']}-event-{i}", "date": date, "title": title, "detail": detail, "status": status}
                     for i, (date, title, detail, status) in enumerate(case["events"])],
        "gaps": case["gaps"], "documents": _documents(case), "fhir": _fhir_bundle(case), "synthetic": True,
    }


def _case(patient_id: str) -> dict | None:
    return next((case for case in _CASES if case["id"] == patient_id), None)


def list_patients() -> list[dict]:
    return deepcopy([_patient(case) for case in _CASES])


def get_patient(patient_id: str) -> dict | None:
    case = _case(patient_id)
    return deepcopy(_patient(case)) if case else None


def get_summary(patient_id: str) -> dict | None:
    case = _case(patient_id)
    return deepcopy(_summary(case)) if case else None


def get_documents(patient_id: str) -> list[dict] | None:
    case = _case(patient_id)
    return deepcopy(_documents(case)) if case else None


def get_document_path(patient_id: str, document_id: str) -> Path | None:
    case = _case(patient_id)
    if not case:
        return None
    doc = next((doc for doc in case["documents"] if doc[0] == document_id), None)
    return SAMPLE_DIR / doc[4] if doc else None
