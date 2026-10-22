from types import SimpleNamespace

import pytest

from pathology import (ClinicalAPIError, PDFExtractionError, extract_findings,
                       extract_pdf_text, validate_findings)
from schemas import (UNKNOWN, Assessment, AssessmentVerification, Biomarker, Citation,
                     Finding, PathologyFindings, Pathway, PathwayCheck)
from treatment import generate_assessment, validate_citations


def findings():
    return PathologyFindings(
        cancer_type=Finding(value="Breast carcinoma", quote="Breast carcinoma"),
        histological_diagnosis=Finding(value="Invasive ductal carcinoma", quote="Invasive ductal carcinoma"),
        grade=Finding(value="Grade 2", quote="Grade 2"),
        tumor_size=Finding(value=UNKNOWN, quote=""), stage_tnm=Finding(value=UNKNOWN, quote=""),
        biomarkers=[Biomarker(name="ER", value="Positive", quote="ER positive (90%)")],
        other_findings=[], missing_information=["Clinical staging"],
    )


def fake_client(*outputs):
    calls = []
    iterator = iter(outputs)
    def parse(**kwargs):
        calls.append(kwargs)
        output = next(iterator)
        if isinstance(output, Exception):
            raise output
        return SimpleNamespace(output_parsed=output, status="completed")
    return SimpleNamespace(responses=SimpleNamespace(parse=parse), calls=calls)


def evidence():
    return [{"id": "chunk-1", "title": "Authorized test source", "version": "test-v1",
             "location": "Section 1", "text": "A conditional option requires completed staging.",
             "source_file": "fixture.txt", "score": 0.9}]


def assessment(quote="A conditional option requires completed staging.", chunk_id="chunk-1"):
    return Assessment(
        pathways=[Pathway(title="Conditional review", conditional_assessment="If staging confirms eligibility, discuss this option with the oncology team.",
                          citations=[Citation(chunk_id=chunk_id, quote=quote)], prerequisites=["Completed staging"])],
        missing_information=[], limitations=[],
    )


def make_pdf(text):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 70), text)
    result = doc.tobytes()
    doc.close()
    return result


def test_extracts_text_pdf_in_memory():
    text = "SYNTHETIC PATHOLOGY REPORT\nInvasive ductal carcinoma. ER positive (90%)."
    assert "Invasive ductal carcinoma" in extract_pdf_text(make_pdf(text))


@pytest.mark.parametrize("data", [b"", b"not a PDF", b"%PDF-broken"])
def test_bad_pdf_gives_safe_error(data):
    with pytest.raises(PDFExtractionError):
        extract_pdf_text(data)


def test_size_limit_before_parser():
    with pytest.raises(PDFExtractionError, match="10 MB"):
        extract_pdf_text(b"%PDF-" + b"a" * (10 * 1024 * 1024))


def test_image_only_pdf_rejected():
    import pymupdf
    image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
    image.clear_with(255)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=image)
    data = doc.tobytes()
    doc.close()
    with pytest.raises(PDFExtractionError, match="scanned or image-only"):
        extract_pdf_text(data)


def test_encrypted_pdf_rejected():
    import pymupdf
    doc = pymupdf.open(stream=make_pdf("SYNTHETIC PATHOLOGY REPORT\nThis is a text report with sufficient characters."), filetype="pdf")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
    doc.close()
    with pytest.raises(PDFExtractionError, match="password protected"):
        extract_pdf_text(data)


def test_fabricated_finding_quote_removed_and_missing_stage_preserved():
    parsed = findings()
    parsed.grade = Finding(value="Grade 3", quote="invented grade")
    parsed.stage_tnm = Finding(value="Stage II", quote="ER positive (90%)")
    result = validate_findings(parsed, "Breast carcinoma. Invasive ductal carcinoma. ER positive (90%).")
    assert result.grade.value == UNKNOWN
    assert result.stage_tnm.value == UNKNOWN
    assert result.biomarkers[0].value == "Positive"
    assert "Tumor grade" in result.missing_information


def test_real_quote_cannot_justify_invented_value():
    parsed = findings()
    parsed.grade = Finding(value="Grade 3", quote="Grade 2")
    parsed.stage_tnm = Finding(value="Stage II", quote="pT2 pN0")
    result = validate_findings(parsed, "Breast carcinoma. Grade 2. pT2 pN0.")
    assert result.grade.value == UNKNOWN
    assert result.stage_tnm.value == UNKNOWN


def test_explicit_tnm_subclassification_preserved():
    parsed = findings()
    parsed.stage_tnm = Finding(value="ypT1b pN0", quote="Pathological classification: ypT1b pN0")
    result = validate_findings(parsed, "Pathological classification: ypT1b pN0")
    assert result.stage_tnm.value == "ypT1b pN0"


def test_api_uses_structured_output_and_disables_response_storage():
    client = fake_client(findings())
    result = extract_findings("Breast carcinoma. Invasive ductal carcinoma. Grade 2. ER positive (90%).", client, "test-model")
    assert result.grade.value == "Grade 2"
    assert client.calls[0]["store"] is False
    assert client.calls[0]["text_format"] is PathologyFindings
    assert "UNTRUSTED DATA" in client.calls[0]["input"][0]["content"]


def test_api_error_never_exposes_report_or_key():
    client = fake_client(RuntimeError("secret-report-content sk-secret-value"))
    with pytest.raises(ClinicalAPIError) as error:
        extract_findings("Some sufficiently long report contents", client, "test")
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("bad", [assessment(quote="invented excerpt"), assessment(chunk_id="not-present")])
def test_bad_citation_suppresses_entire_pathway(bad):
    assert validate_citations(bad, evidence()).pathways == []


def test_exact_citation_passes_structural_validation():
    assert len(validate_citations(assessment(), evidence()).pathways) == 1


def test_no_evidence_never_calls_api():
    client = fake_client()
    assert generate_assessment(findings(), [], client, "test").pathways == []
    assert client.calls == []


def test_missing_version_never_calls_api():
    chunks = evidence()
    chunks[0]["version"] = ""
    client = fake_client()
    assert generate_assessment(findings(), chunks, client, "test").pathways == []
    assert client.calls == []


def test_unrelated_but_real_quote_withheld_by_verification():
    client = fake_client(assessment(), AssessmentVerification(checks=[PathwayCheck(
        pathway_index=0, fully_supported=False, conditional=True, no_personalized_regimen_or_dose=True)]))
    result = generate_assessment(findings(), evidence(), client, "test")
    assert result.pathways == []
    assert len(client.calls) == 2


def test_verified_conditional_pathway_is_returned():
    client = fake_client(assessment(), AssessmentVerification(checks=[PathwayCheck(
        pathway_index=0, fully_supported=True, conditional=True, no_personalized_regimen_or_dose=True)]))
    result = generate_assessment(findings(), evidence(), client, "test")
    assert len(result.pathways) == 1
    assert "Clinical staging" in result.missing_information


def test_verification_failure_withholds_pathways():
    client = fake_client(assessment(), RuntimeError("network error"))
    assert generate_assessment(findings(), evidence(), client, "test").pathways == []


def test_duplicate_verification_check_withholds_pathway():
    check = PathwayCheck(pathway_index=0, fully_supported=True, conditional=True, no_personalized_regimen_or_dose=True)
    client = fake_client(assessment(), AssessmentVerification(checks=[check, check]))
    assert generate_assessment(findings(), evidence(), client, "test").pathways == []


def test_dose_is_suppressed_before_semantic_verification():
    draft = assessment()
    draft.pathways[0].conditional_assessment = "Consider 100 mg daily."
    assert validate_citations(draft, evidence()).pathways == []
