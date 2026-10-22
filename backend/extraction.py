"""Conservative extraction from actual PDF text, without an LLM or fixture replay."""
from __future__ import annotations

import re

from pathology import validate_findings
from schemas import UNKNOWN, Biomarker, Finding, PathologyFindings

MARKERS = ("ER", "PR", "HER2", "Ki-67", "EGFR", "ALK", "PD-L1", "ROS1", "MMR", "MSI", "KRAS", "BRAF")
ABSENT = re.compile(r"not available|not documented|not established|unknown|not reported|not supplied|not assessed", re.I)
PENDING = re.compile(r"pending|not ordered|equivocal|indeterminate|not available|unknown", re.I)


def _label(text: str, labels: tuple[str, ...]) -> Finding:
    for label in labels:
        match = re.search(r"(?im)^\s*" + re.escape(label) + r"\s*[:=]\s*([^\r\n]{1,500})", text)
        if match:
            value = match.group(1).strip()
            if ABSENT.search(value):
                return Finding(value=UNKNOWN, quote="")
            return Finding(value=value, quote=match.group(0).strip())
    return Finding(value=UNKNOWN, quote="")


def extract_local_findings(text: str) -> PathologyFindings:
    """Extract explicit labeled spans only; unsupported formats stay unknown.

    This parser intentionally avoids inferred stage, combined biomarker conclusions,
    negation guessing and patient-specific therapeutic interpretation.
    """
    fields = {
        "cancer_type": _label(text, ("Cancer type", "Cancer site")),
        "histological_diagnosis": _label(text, ("Histological diagnosis", "Histology", "Final diagnosis", "Diagnosis")),
        "grade": _label(text, ("Tumor grade", "Grade", "Nottingham grade")),
        "tumor_size": _label(text, ("Pathologic tumor size", "Tumor size", "Definitive tumor size")),
        "stage_tnm": _label(text, ("Clinical stage", "Clinical TNM", "Pathologic stage", "Stage / TNM", "Stage", "TNM")),
    }
    biomarkers = []
    missing = []
    for name in MARKERS:
        aliases = {"ER": ("ER", "Estrogen receptor (ER)", "Estrogen receptor"),
                   "PR": ("PR", "Progesterone receptor (PR)", "Progesterone receptor"),
                   "HER2": ("HER2", "HER2 IHC"), "Ki-67": ("Ki-67", "Ki67")}.get(name, (name,))
        result = _label(text, aliases)
        if result.value != UNKNOWN:
            biomarkers.append(Biomarker(name=name, value=result.value, quote=result.quote))
            if PENDING.search(result.value):
                missing.append(f"Confirmed {name} result")
    cancer = fields["cancer_type"].value.lower()
    required = ("ER", "PR", "HER2") if "breast" in cancer else ("EGFR", "ALK", "PD-L1", "ROS1") if "lung" in cancer else ("MMR", "MSI") if "colon" in cancer else ()
    present = {marker.name for marker in biomarkers}
    missing.extend(f"Confirmed {name} result" for name in required if name not in present)
    findings = PathologyFindings(**fields, biomarkers=biomarkers, other_findings=[], missing_information=missing)
    return validate_findings(findings, text)


def _marker_status(value: str) -> str | None:
    if PENDING.search(value) or ABSENT.search(value):
        return None
    if re.search(r"\bnegative\b|\bIHC\s*0\b", value, re.I):
        return "negative"
    if re.search(r"\bpositive\b|\bIHC\s*3\+", value, re.I):
        return "positive"
    return None


def compare_with_chart(text: str, findings: PathologyFindings, chart: dict) -> list[dict]:
    conflicts = []
    patient = chart["patient"]
    ids = set(re.findall(r"\bDEMO-\d{5}\b", text, re.I))
    explicit_id = re.search(r"(?im)^\s*(?:Synthetic patient ID|Patient ID|MRN)\s*:\s*([^\r\n]+)", text)
    if explicit_id:
        ids.add(explicit_id.group(1).strip())
    if ids and ids != {patient["id"]}:
        conflicts.append({"field": "patient_identity", "chart_value": patient["id"], "report_value": ", ".join(sorted(ids)),
                          "severity": "error", "message": "The report identifies a different synthetic patient. Upload the matching report."})
    report_name = re.search(r"(?im)^\s*(?:Patient name|Patient)\s*:\s*([^\r\n]+)", text)
    if report_name and report_name.group(1).strip().casefold() != patient["name"].casefold():
        conflicts.append({"field": "patient_identity", "chart_value": patient["name"], "report_value": report_name.group(1).strip(),
                          "severity": "error", "message": "The report name does not match this synthetic chart. Confirm the report identity."})
    source = findings.cancer_type.value.lower()
    target = patient["cancer_type"].lower()
    histology = findings.histological_diagnosis.value.lower()
    if re.search(r"benign|no (?:evidence of )?malignancy|non.?malignant", histology):
        conflicts.append({"field": "histological_diagnosis", "chart_value": patient["diagnosis"], "report_value": findings.histological_diagnosis.value,
                          "severity": "error", "message": "Nonmalignant histology conflicts with the cancer chart. Confirm the report and patient identity."})
    if source != UNKNOWN.lower():
        families = ("breast", "lung", "colon")
        report_family = next((word for word in families if word in source), None)
        chart_family = next((word for word in families if word in target), None)
        if report_family and chart_family and report_family != chart_family:
            conflicts.append({"field": "cancer_type", "chart_value": patient["cancer_type"], "report_value": findings.cancer_type.value,
                              "severity": "error", "message": "Cancer site differs from the selected chart. Review patient and report identity before analysis."})
        elif re.search(r"benign|no (?:evidence of )?malignancy|non.?malignant", source):
            conflicts.append({"field": "cancer_type", "chart_value": patient["cancer_type"], "report_value": findings.cancer_type.value,
                              "severity": "error", "message": "Nonmalignant report findings conflict with the cancer chart. No treatment pathway can be generated."})
    chart_markers = {item["name"].casefold(): item for item in chart["biomarkers"]}
    for key, name, report_finding in (("histology", "histological_diagnosis", findings.histological_diagnosis),
                                      ("grade", "grade", findings.grade), ("stage", "stage_tnm", findings.stage_tnm)):
        existing_value = chart["profile"].get(key, "")
        report_value = report_finding.value
        if not existing_value or ABSENT.search(existing_value) or ABSENT.search(report_value) or PENDING.search(existing_value) or PENDING.search(report_value):
            continue
        old = " ".join(re.findall(r"\w+", existing_value.casefold()))
        new = " ".join(re.findall(r"\w+", report_value.casefold()))
        differs = old not in new and new not in old
        if key == "grade":
            old_grade = re.search(r"\b(?:grade\s*)?([1-3])\b", old)
            new_grade = re.search(r"\b(?:grade\s*)?([1-3])\b", new)
            if old_grade and new_grade:
                differs = old_grade.group(1) != new_grade.group(1)
        if differs:
            conflicts.append({"field": name, "chart_value": existing_value, "report_value": report_value, "severity": "warning",
                              "message": f"Reported {key} differs from the chart. Review the original sources; neither source has been overwritten."})
    for marker in findings.biomarkers:
        existing = chart_markers.get(marker.name.casefold())
        if not existing:
            continue
        chart_status, report_status = _marker_status(existing["value"]), _marker_status(marker.value)
        polarity_conflict = chart_status and report_status and chart_status != report_status
        equivocal_conflict = chart_status and re.search(r"equivocal|indeterminate", marker.value, re.I)
        chart_percent = re.search(r"(\d+(?:\.\d+)?)\s*%", existing["value"])
        report_percent = re.search(r"(\d+(?:\.\d+)?)\s*%", marker.value)
        quantitative_conflict = chart_percent and report_percent and float(chart_percent.group(1)) != float(report_percent.group(1))
        if polarity_conflict or equivocal_conflict or quantitative_conflict:
            conflicts.append({"field": marker.name, "chart_value": existing["value"], "report_value": marker.value, "severity": "warning",
                              "message": f"{marker.name} differs between the chart and uploaded report. Neither source has been overwritten."})
    return conflicts


def factual_summary(findings: PathologyFindings) -> str:
    facts = []
    for label, name in (("Reported cancer type", "cancer_type"), ("Histology", "histological_diagnosis"), ("Grade", "grade"), ("Reported tumor measurement", "tumor_size"), ("Explicit stage/TNM", "stage_tnm")):
        value = getattr(findings, name).value
        facts.append(f"{label}: {value}.")
    if findings.biomarkers:
        facts.append("Reported biomarkers: " + "; ".join(f"{b.name}: {b.value}" for b in findings.biomarkers) + ".")
    facts.append("This is a factual documentation draft from the uploaded report. It does not select a treatment pathway.")
    return " ".join(facts)
