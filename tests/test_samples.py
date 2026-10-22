"""Validate bundled fixture integrity, text evidence, and the image-only case."""

import hashlib
import json
from pathlib import Path

import fitz
import pytest


SAMPLES = Path(__file__).resolve().parents[1] / "samples"
MANIFEST = json.loads((SAMPLES / "manifest.json").read_text(encoding="utf-8"))
UNKNOWN = "Not available in report"


def normalized(text):
    return " ".join(text.split())


@pytest.mark.parametrize("case", MANIFEST, ids=lambda case: case["id"])
def test_pdf_integrity_and_expected_text_layer(case):
    raw = (SAMPLES / case["filename"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == case["sha256"]
    with fitz.open(stream=raw, filetype="pdf") as document:
        assert len(document) == 1
        text = normalized(document[0].get_text())
        if case["findings"] is None:
            assert not text
            assert document[0].get_images()
        else:
            assert "SYNTHETIC TEST DATA" in text
            assert len(text) > 500
            assert "No real patient" in text


@pytest.mark.parametrize("case", [case for case in MANIFEST if case["findings"]], ids=lambda case: case["id"])
def test_expected_findings_are_supported_by_pdf(case):
    with fitz.open(SAMPLES / case["filename"]) as document:
        text = normalized(document[0].get_text())
    findings = case["findings"]
    entries = [findings[field] for field in ("cancer_type", "histological_diagnosis", "grade", "tumor_size", "stage_tnm")]
    entries += findings["biomarkers"] + findings["other_findings"]
    for entry in entries:
        if entry["value"] == UNKNOWN:
            assert entry["quote"] == ""
        else:
            assert entry["quote"]
            assert normalized(entry["quote"]) in text
            assert normalized(entry["value"]).lower() in normalized(entry["quote"]).lower()
    assert findings["missing_information"]


def test_cases_cover_success_missing_data_benign_and_scanned():
    by_id = {case["id"]: case for case in MANIFEST}
    assert len(by_id) == 6
    assert by_id["scanned_image_only"]["findings"] is None
    incomplete = by_id["breast_incomplete"]["findings"]
    assert incomplete["stage_tnm"]["value"] == UNKNOWN
    assert all(marker["value"] == UNKNOWN for marker in incomplete["biomarkers"])
    for name in ("breast_er_positive_her2_negative", "breast_her2_positive", "breast_triple_negative"):
        assert by_id[name]["findings"]["stage_tnm"]["value"] == UNKNOWN
    assert "No atypia or malignancy" in by_id["breast_benign"]["findings"]["cancer_type"]["value"]
