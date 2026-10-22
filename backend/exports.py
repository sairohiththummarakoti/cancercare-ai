"""Remove known synthetic chart identifiers from documentation exports."""
from __future__ import annotations

from datetime import date
import re

from backend.fixtures import list_patients


def deidentified_export(payload: dict) -> dict:
    identifiers = set()
    for patient in list_patients():
        identifiers.update((patient["name"], patient["id"], patient.get("mrn", patient["id"]), patient["dob"]))
        dob = date.fromisoformat(patient["dob"])
        identifiers.update((dob.strftime("%d %b %Y"), dob.strftime("%d %B %Y"), dob.strftime("%m/%d/%Y"), dob.strftime("%B %d, %Y"), dob.strftime("%b %d, %Y")))
    pattern = re.compile("|".join(re.escape(value) for value in sorted(identifiers, key=len, reverse=True) if value), re.I)

    def redact(value):
        if isinstance(value, str):
            return pattern.sub("[redacted synthetic identifier]", value)
        if isinstance(value, dict):
            return {key: redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    result = redact(payload)
    result["export_scope"] = "De-identified synthetic documentation"
    result["deidentification_notice"] = "Known synthetic patient names, MRNs and dates of birth were removed, including from review text. This is not a general-purpose PHI detector; unrecognized identifiers in free text may remain. Synthetic data only."
    return result
