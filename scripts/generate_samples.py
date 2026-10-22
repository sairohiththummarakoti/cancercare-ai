"""Regenerate the six invented, one-page pathology fixtures and their manifest.

Run with: python scripts/generate_samples.py
Dependencies: reportlab, pypdfium2, Pillow (optional authoring tools).
No network or API access is used. The fixtures contain no real patient data.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from xml.sax.saxutils import escape

import pypdfium2 as pdfium
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen.canvas import Canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"
UNKNOWN = "Not available in report"
TEAL = colors.HexColor("#087F8C")
INK = colors.HexColor("#172B35")
MUTED = colors.HexColor("#52646B")
RULE = colors.HexColor("#D8E5E7")


def fact(value: str, quote: str | None = None) -> dict[str, str]:
    evidence = value if quote is None else quote
    # Exact evidence spans are deliberately used for the deterministic fixtures.
    # Do not turn a supported sentence into an unsupported clinical paraphrase.
    if " ".join(value.lower().split()) not in " ".join(evidence.lower().split()):
        value = evidence.rstrip(".")
    return {"value": value, "quote": evidence}


def absent() -> dict[str, str]:
    return {"value": UNKNOWN, "quote": ""}


def marker(name: str, value: str, quote: str) -> dict[str, str]:
    if value != UNKNOWN and " ".join(value.lower().split()) not in " ".join(quote.lower().split()):
        value = quote.split(": ", 1)[-1].rstrip(".")
    return {"name": name, "value": value, "quote": quote}


def make_cases() -> list[dict]:
    """Return the fixture source data, including verbatim evidence quotations."""
    common_missing = [
        "Clinical stage and staging evaluation",
        "Nodal and distant metastatic status",
        "Clinical history, performance status, and comorbidities",
        "Prior cancer treatment and patient preferences",
    ]
    shared = {
        "cancer_type": fact("Breast cancer", "Invasive carcinoma of the breast"),
        "histological_diagnosis": fact("Invasive carcinoma of no special type", "Histological diagnosis: Invasive carcinoma of no special type."),
        "stage_tnm": absent(),
    }
    cases = [
        {
            "id": "breast_er_positive_her2_negative",
            "title": "Breast ER positive HER2 negative",
            "filename": "01_breast_er_positive_her2_negative.pdf",
            "description": "Synthetic core biopsy with ER and PR positivity and HER2 IHC 1+.",
            "expected_behavior": "Extract invasive breast carcinoma and the reported receptors; preserve unknown stage. With no authorized guideline evidence, show findings and the no-evidence limitation only.",
            "accession": "SYN-BC-001",
            "specimen": "Left breast, 10 o'clock, ultrasound-guided core biopsy.",
            "sections": [
                ("Final diagnosis", [
                    "Invasive carcinoma of the breast.",
                    "Histological diagnosis: Invasive carcinoma of no special type.",
                    "Histological grade: Nottingham grade 2 (score 6 of 9).",
                    "Tumor extent in cores: Largest contiguous invasive focus measures 12 mm. This is a core-biopsy measurement, not the overall tumor size.",
                ]),
                ("Immunohistochemistry", [
                    "ER: Positive, 95% of tumor nuclei, strong intensity.",
                    "PR: Positive, 70% of tumor nuclei, moderate to strong intensity.",
                    "HER2: IHC 1+ (negative).",
                    "Ki-67: 18% of tumor nuclei.",
                ]),
                ("Additional findings and limitations", [
                    "Lymphovascular invasion: Not identified in this limited sample.",
                    "Lymph nodes: Not submitted.",
                    "Overall tumor size and clinical stage/TNM: Not available in report.",
                    "This core biopsy does not establish clinical stage. Clinical history and staging studies are not provided.",
                ]),
            ],
            "findings": {
                **shared,
                "grade": fact("Nottingham grade 2 (score 6 of 9)", "Histological grade: Nottingham grade 2 (score 6 of 9)."),
                "tumor_size": fact("12 mm invasive focus in core biopsy; overall tumor size unavailable", "Largest contiguous invasive focus measures 12 mm. This is a core-biopsy measurement, not the overall tumor size."),
                "biomarkers": [marker("ER", "Positive, 95%, strong", "ER: Positive, 95% of tumor nuclei, strong intensity."), marker("PR", "Positive, 70%, moderate to strong", "PR: Positive, 70% of tumor nuclei, moderate to strong intensity."), marker("HER2", "IHC 1+ (negative)", "HER2: IHC 1+ (negative)."), marker("Ki-67", "18%", "Ki-67: 18% of tumor nuclei.")],
                "other_findings": [fact("No lymphovascular invasion identified in limited sample", "Lymphovascular invasion: Not identified in this limited sample."), fact("Lymph nodes not submitted", "Lymph nodes: Not submitted.")],
                "missing_information": ["Overall tumor size", *common_missing],
            },
        },
        {
            "id": "breast_her2_positive",
            "title": "Breast HER2 positive",
            "filename": "02_breast_her2_positive.pdf",
            "description": "Synthetic invasive breast core biopsy with HER2 IHC 3+ and negative hormone receptors.",
            "expected_behavior": "Extract HER2 IHC 3+, ER/PR negative, and biopsy extent. Do not infer clinical stage, eligibility, or a regimen from pathology alone.",
            "accession": "SYN-BC-002",
            "specimen": "Right breast, 2 o'clock, ultrasound-guided core biopsy.",
            "sections": [
                ("Final diagnosis", [
                    "Invasive carcinoma of the breast.",
                    "Histological diagnosis: Invasive carcinoma of no special type.",
                    "Histological grade: Nottingham grade 3 (score 8 of 9).",
                    "Tumor extent in cores: Largest contiguous invasive focus measures 15 mm. Overall tumor size cannot be determined from this biopsy.",
                ]),
                ("Immunohistochemistry", [
                    "ER: Negative, less than 1% of tumor nuclei.",
                    "PR: Negative, less than 1% of tumor nuclei.",
                    "HER2: IHC 3+ (positive), complete intense membrane staining in 80% of invasive tumor cells.",
                    "Ki-67: 45% of tumor nuclei.",
                ]),
                ("Additional findings and limitations", [
                    "Lymphovascular invasion: Not identified in this limited sample.",
                    "Lymph nodes: Not submitted.",
                    "Clinical stage/TNM: Not available in report.",
                    "No imaging, cardiac assessment, clinical history, or staging workup accompanies this specimen.",
                ]),
            ],
            "findings": {
                **shared,
                "grade": fact("Nottingham grade 3 (score 8 of 9)", "Histological grade: Nottingham grade 3 (score 8 of 9)."),
                "tumor_size": fact("15 mm invasive focus in core biopsy; overall tumor size unavailable", "Largest contiguous invasive focus measures 15 mm. Overall tumor size cannot be determined from this biopsy."),
                "biomarkers": [marker("ER", "Negative, less than 1%", "ER: Negative, less than 1% of tumor nuclei."), marker("PR", "Negative, less than 1%", "PR: Negative, less than 1% of tumor nuclei."), marker("HER2", "IHC 3+ (positive)", "HER2: IHC 3+ (positive), complete intense membrane staining in 80% of invasive tumor cells."), marker("Ki-67", "45%", "Ki-67: 45% of tumor nuclei.")],
                "other_findings": [fact("Lymph nodes not submitted", "Lymph nodes: Not submitted.")],
                "missing_information": ["Overall tumor size", "Baseline cardiac assessment where clinically relevant", *common_missing],
            },
        },
        {
            "id": "breast_triple_negative",
            "title": "Breast triple negative",
            "filename": "03_breast_triple_negative.pdf",
            "description": "Synthetic invasive breast core biopsy with negative ER, PR, and HER2 results.",
            "expected_behavior": "Extract the three negative receptor results without assuming germline status, PD-L1 status, clinical stage, or treatment eligibility.",
            "accession": "SYN-BC-003",
            "specimen": "Left breast, 4 o'clock, ultrasound-guided core biopsy.",
            "sections": [
                ("Final diagnosis", [
                    "Invasive carcinoma of the breast.",
                    "Histological diagnosis: Invasive carcinoma of no special type.",
                    "Histological grade: Nottingham grade 3 (score 9 of 9).",
                    "Tumor extent in cores: Largest contiguous invasive focus measures 10 mm. Overall tumor size is not established by this biopsy.",
                ]),
                ("Immunohistochemistry", [
                    "ER: Negative, less than 1% of tumor nuclei.",
                    "PR: Negative, less than 1% of tumor nuclei.",
                    "HER2: IHC 0 (negative).",
                    "Ki-67: 75% of tumor nuclei.",
                ]),
                ("Additional findings and limitations", [
                    "Lymph nodes: Not submitted.",
                    "PD-L1 and germline testing results: Not available in report.",
                    "Clinical stage/TNM: Not available in report.",
                    "Clinical history, imaging, and prior treatment information are not provided.",
                ]),
            ],
            "findings": {
                **shared,
                "grade": fact("Nottingham grade 3 (score 9 of 9)", "Histological grade: Nottingham grade 3 (score 9 of 9)."),
                "tumor_size": fact("10 mm invasive focus in core biopsy; overall tumor size unavailable", "Largest contiguous invasive focus measures 10 mm. Overall tumor size is not established by this biopsy."),
                "biomarkers": [marker("ER", "Negative, less than 1%", "ER: Negative, less than 1% of tumor nuclei."), marker("PR", "Negative, less than 1%", "PR: Negative, less than 1% of tumor nuclei."), marker("HER2", "IHC 0 (negative)", "HER2: IHC 0 (negative)."), marker("Ki-67", "75%", "Ki-67: 75% of tumor nuclei.")],
                "other_findings": [fact("Lymph nodes not submitted", "Lymph nodes: Not submitted.")],
                "missing_information": ["Overall tumor size", "PD-L1 status if clinically indicated", "Germline testing and counseling eligibility", *common_missing],
            },
        },
        {
            "id": "breast_incomplete",
            "title": "Breast incomplete biomarkers",
            "filename": "04_breast_incomplete_information.pdf",
            "description": "Synthetic limited core biopsy deliberately omitting grade, size, stage, and receptor results.",
            "expected_behavior": "Show Not available in report for all missing fields. Flag pending ER, PR, and HER2 results and do not invent a subtype, stage, or regimen.",
            "accession": "SYN-BC-004",
            "specimen": "Right breast, image-guided core biopsy; location not further specified.",
            "sections": [
                ("Final diagnosis", [
                    "Invasive carcinoma of the breast.",
                    "Histological diagnosis: Invasive carcinoma, not further classified in this limited sample.",
                    "Histological grade: Not available in report.",
                    "Tumor size: Not available in report.",
                ]),
                ("Pending studies", [
                    "ER, PR, and HER2 studies are pending; no results are supplied in this report.",
                    "Ki-67: Not available in report.",
                    "No receptor-defined subtype can be assigned from the information supplied.",
                ]),
                ("Additional findings and limitations", [
                    "Lymph nodes: Not submitted.",
                    "Clinical stage/TNM: Not available in report.",
                    "A final pathology addendum, clinical history, and staging workup are not included.",
                ]),
            ],
            "findings": {
                "cancer_type": fact("Breast cancer", "Invasive carcinoma of the breast"),
                "histological_diagnosis": fact("Invasive carcinoma, not further classified", "Histological diagnosis: Invasive carcinoma, not further classified in this limited sample."),
                "grade": absent(), "tumor_size": absent(), "stage_tnm": absent(),
                "biomarkers": [marker("ER", UNKNOWN, ""), marker("PR", UNKNOWN, ""), marker("HER2", UNKNOWN, ""), marker("Ki-67", UNKNOWN, "")],
                "other_findings": [fact("ER, PR, and HER2 studies pending", "ER, PR, and HER2 studies are pending; no results are supplied in this report."), fact("Lymph nodes not submitted", "Lymph nodes: Not submitted.")],
                "missing_information": ["Final histological classification and grade", "Overall tumor size", "ER, PR, and HER2 results", "Ki-67 result if clinically relevant", *common_missing],
            },
        },
        {
            "id": "breast_benign",
            "title": "Breast benign biopsy",
            "filename": "05_breast_benign_no_malignancy.pdf",
            "description": "Synthetic benign breast biopsy used to verify that the app does not invent a cancer diagnosis or oncology pathway.",
            "expected_behavior": "Report benign findings and no malignancy identified in the submitted tissue. Suppress cancer treatment pathways; do not claim the patient is cancer-free outside this specimen.",
            "accession": "SYN-BC-005",
            "specimen": "Left breast, 8 o'clock, ultrasound-guided core biopsy.",
            "sections": [
                ("Final diagnosis", [
                    "Histological diagnosis: Fibroadenoma with benign breast tissue.",
                    "No atypia or malignancy identified in the submitted tissue.",
                    "No invasive carcinoma or ductal carcinoma in situ identified in this sample.",
                ]),
                ("Additional findings", [
                    "Histological grade: Not applicable to the reported benign diagnosis.",
                    "Tumor size: Not available in report.",
                    "ER, PR, HER2, and Ki-67 studies: Not performed.",
                    "Clinical stage/TNM: Not applicable to the reported benign diagnosis.",
                ]),
                ("Specimen limitations", [
                    "This result describes only the tissue submitted. Imaging-pathology concordance is not provided.",
                    "No clinical history or radiology report accompanies this specimen.",
                ]),
            ],
            "findings": {
                "cancer_type": fact("No atypia or malignancy identified in the submitted tissue", "No atypia or malignancy identified in the submitted tissue."),
                "histological_diagnosis": fact("Fibroadenoma with benign breast tissue", "Histological diagnosis: Fibroadenoma with benign breast tissue."),
                "grade": fact("Not applicable to reported benign diagnosis", "Histological grade: Not applicable to the reported benign diagnosis."),
                "tumor_size": absent(),
                "stage_tnm": fact("Not applicable to reported benign diagnosis", "Clinical stage/TNM: Not applicable to the reported benign diagnosis."),
                "biomarkers": [marker("ER", UNKNOWN, ""), marker("PR", UNKNOWN, ""), marker("HER2", UNKNOWN, ""), marker("Ki-67", UNKNOWN, "")],
                "other_findings": [fact("No carcinoma identified in sample", "No invasive carcinoma or ductal carcinoma in situ identified in this sample."), fact("Receptor studies not performed", "ER, PR, HER2, and Ki-67 studies: Not performed.")],
                "missing_information": ["Imaging-pathology concordance", "Clinical history and radiology report"],
            },
        },
    ]
    return cases


def styles():
    base = getSampleStyleSheet()
    base.add(ParagraphStyle(name="SampleTitle", fontName="Helvetica-Bold", fontSize=24, leading=28, textColor=INK, spaceAfter=7))
    base.add(ParagraphStyle(name="SampleSubtitle", fontName="Helvetica", fontSize=11, leading=15, textColor=MUTED, spaceAfter=12))
    base.add(ParagraphStyle(name="SampleHeading", fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=TEAL, spaceBefore=13, spaceAfter=6))
    base.add(ParagraphStyle(name="SampleBody", fontName="Helvetica", fontSize=10, leading=14, textColor=INK, spaceAfter=5))
    base.add(ParagraphStyle(name="SampleMeta", fontName="Helvetica", fontSize=9, leading=13, textColor=INK))
    base.add(ParagraphStyle(name="SampleNote", fontName="Helvetica", fontSize=9, leading=13, textColor=MUTED, spaceBefore=10))
    return base


def page_decoration(canvas: Canvas, doc):
    width, height = letter
    canvas.saveState()
    canvas.setFillColor(TEAL)
    canvas.rect(0, height - 12, width, 12, fill=1, stroke=0)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(48, height - 38, "ONCOLOGY CARE AI  /  SYNTHETIC TEST DATA")
    canvas.setStrokeColor(RULE)
    canvas.line(48, 55, width - 48, 55)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(48, 40, "Invented educational fixture. No real patient, laboratory, or clinician.")
    canvas.drawRightString(width - 48, 40, f"Page {doc.page}")
    canvas.restoreState()


def render_report(case: dict, destination: Path):
    style = styles()
    doc = SimpleDocTemplate(str(destination), pagesize=letter, leftMargin=48, rightMargin=48, topMargin=64, bottomMargin=72, title=f"SYNTHETIC TEST DATA - {case['title']}", author="Oncology Care AI synthetic test generator")
    story = [
        Paragraph("Synthetic pathology report", style["SampleTitle"]),
        Paragraph(escape(case["title"]), style["SampleSubtitle"]),
    ]
    meta_rows = [
        [Paragraph("<b>Accession</b>", style["SampleMeta"]), Paragraph(escape(case["accession"]), style["SampleMeta"])],
        [Paragraph("<b>Subject</b>", style["SampleMeta"]), Paragraph("Fictional test specimen; no patient identifiers", style["SampleMeta"])],
        [Paragraph("<b>Specimen</b>", style["SampleMeta"]), Paragraph(escape(case["specimen"]), style["SampleMeta"])],
    ]
    table = Table(meta_rows, colWidths=[80, 436], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F7F8")), ("BOX", (0, 0), (-1, -1), 0.5, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story.append(table)
    for heading, lines in case["sections"]:
        story.append(Paragraph(escape(heading), style["SampleHeading"]))
        for line in lines:
            story.append(Paragraph(escape(line), style["SampleBody"]))
    story.append(Paragraph("SYNTHETIC TEST DATA. This report was invented to exercise software behavior. It is not a clinical record and contains no treatment recommendation.", style["SampleNote"]))
    doc.build(story, onFirstPage=page_decoration, onLaterPages=page_decoration)


def raster_only_copy(source: Path, destination: Path):
    """Embed a rendered page as an image, with no searchable text or OCR layer."""
    document = pdfium.PdfDocument(str(source))
    page = document[0]
    bitmap = page.render(scale=2.0)
    image = bitmap.to_pil()
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    canvas = Canvas(str(destination), pagesize=letter)
    canvas.setTitle("SYNTHETIC TEST DATA - Image-only PDF negative test")
    canvas.setAuthor("Oncology Care AI synthetic test generator")
    canvas.drawImage(ImageReader(io.BytesIO(buf.getvalue())), 0, 0, width=letter[0], height=letter[1])
    canvas.save()
    bitmap.close()
    page.close()
    document.close()


def generate():
    OUT.mkdir(parents=True, exist_ok=True)
    cases = make_cases()
    manifest = []
    for case in cases:
        path = OUT / case["filename"]
        render_report(case, path)
        entry = {key: case[key] for key in ("id", "title", "filename", "description", "expected_behavior", "findings")}
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.append(entry)
    scanned = OUT / "06_scanned_image_only.pdf"
    raster_only_copy(OUT / cases[0]["filename"], scanned)
    manifest.append({
        "id": "scanned_image_only", "title": "Image-only PDF negative test", "filename": scanned.name,
        "description": "A rasterized copy of the first synthetic report, deliberately without a PDF text layer.",
        "expected_behavior": "Reject with an actionable scanned/image-only PDF error. Do not send an empty report to the model or infer findings.",
        "sha256": hashlib.sha256(scanned.read_bytes()).hexdigest(), "findings": None,
    })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Created {len(manifest)} synthetic PDFs and samples/manifest.json")


if __name__ == "__main__":
    generate()
