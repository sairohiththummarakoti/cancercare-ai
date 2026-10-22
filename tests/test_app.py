"""User-visible integration coverage without API/network access."""
import pytest
from streamlit.testing.v1 import AppTest

from config import ROOT
from demo import SAMPLES, replay_sample, sample_catalog
from pathology import extract_pdf_text, validate_findings
from review import APPROVED, PENDING, REJECTED, export_result, set_review


@pytest.mark.parametrize("item", [s for s in sample_catalog() if s.get("findings")], ids=lambda s: s["id"])
def test_exact_sample_replay_is_grounded(item):
    data = (SAMPLES / item["filename"]).read_bytes()
    text = extract_pdf_text(data)
    findings, assessment, chunks = replay_sample(data)
    verified = validate_findings(findings, text)
    for key in ("cancer_type", "histological_diagnosis", "grade", "tumor_size", "stage_tnm"):
        assert getattr(verified, key) == getattr(findings, key)
    # Live validation omits unknown marker rows and lists them as missing.
    assert verified.biomarkers == [b for b in findings.biomarkers if b.value != "Not available in report"]
    if "incomplete" in item["id"] or "benign" in item["id"]:
        assert assessment.pathways == []
    else:
        assert assessment.pathways
        assert chunks
    assert "no language model" in assessment.limitations[0]


def test_demo_does_not_guess_for_arbitrary_or_changed_files():
    item = next(s for s in sample_catalog() if s.get("findings"))
    original = (SAMPLES / item["filename"]).read_bytes()
    with pytest.raises(ValueError, match="included, unchanged"):
        replay_sample(original + b"\nmodified")


def test_review_preserves_original_and_marks_edits_pending():
    item = next(s for s in sample_catalog() if s.get("findings"))
    findings, assessment, chunks = replay_sample((SAMPLES / item["filename"]).read_bytes())
    result = {"filename": item["filename"], "mode": "Sample demo", "elapsed": 0.01,
              "findings": findings, "assessment": assessment, "chunks": chunks, "review_status": PENDING}
    approved = set_review(result, "approve", "Reviewed")
    assert approved["review_status"] == APPROVED
    assert result["review_status"] == PENDING
    edited = set_review(approved, "edit", "Clinician revision")
    assert edited["review_status"] == PENDING
    assert edited["assessment"] == assessment
    assert export_result(edited)["clinician_edit"] == "Clinician revision"
    assert set_review(edited, "reject")["review_status"] == REJECTED


def click_button(app, label):
    next(b for b in app.button if b.label == label).click().run()
    assert not app.exception


def test_screen_workflow_and_input_change_clears_review():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert next(b for b in app.button if b.label.startswith("Analyze")).disabled
    app.selectbox(key="sample_selection").set_value(0).run()
    click_button(app, "Analyze & Generate Treatment Assessment")
    assert app.session_state.result["assessment"].pathways
    assert app.session_state.result["elapsed"] > 0
    click_button(app, "Approve for Documentation")
    assert app.session_state.result["review_status"] == APPROVED
    click_button(app, "Edit")
    app.text_area(key="edit_text").set_value("A clinician-authored revision.").run()
    click_button(app, "Save edited draft")
    assert app.session_state.result["review_status"] == PENDING
    assert app.session_state.result["clinician_edit"] == "A clinician-authored revision."
    click_button(app, "Reject")
    assert app.session_state.result["review_status"] == REJECTED
    click_button(app, "Edit")
    app.text_area(key="review_notes").set_value("Old reviewer note").run()
    click_button(app, "Analyze & Generate Treatment Assessment")
    assert app.session_state.result["review_status"] == PENDING
    assert app.text_area(key="review_notes").value == ""
    assert "show_editor" not in app.session_state
    app.selectbox(key="sample_selection").set_value(1).run()
    assert "result" not in app.session_state


def test_scanned_pdf_shows_actionable_error_without_result():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    index = next(i for i, s in enumerate(sample_catalog()) if s.get("findings") is None)
    app.selectbox(key="sample_selection").set_value(index).run()
    click_button(app, "Analyze & Generate Treatment Assessment")
    assert "result" not in app.session_state
    assert any("OCR" in e.value for e in app.error)
