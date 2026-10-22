"""Regenerate the synthetic EHR PDF pack and FHIR-shaped fixture snapshots.

Run from the project root: .venv/Scripts/python.exe backend/fixtures_data/generate.py
No network, model calls, patient records or guideline content are used.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
from xml.sax.saxutils import escape
import zipfile

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.fixtures import _CASES, get_summary, SAMPLE_DIR

NAVY = colors.HexColor("#14253D")
TEAL = colors.HexColor("#007F7B")
MUTED = colors.HexColor("#576A7C")
PALE = colors.HexColor("#F4F7FA")
UNKNOWN = "Not available in report"


def _footer(canvas_, doc):
    canvas_.saveState()
    canvas_.setStrokeColor(colors.HexColor("#DCE4EB"))
    canvas_.line(48, 49, 564, 49)
    canvas_.setFont("Helvetica", 8)
    canvas_.setFillColor(MUTED)
    canvas_.drawString(48, 35, "SYNTHETIC TEST DOCUMENT - No real patient data or treatment orders")
    canvas_.drawRightString(564, 35, f"Page {doc.page}")
    canvas_.restoreState()


def report(path, title, case, date, sections, subtitle="Synthetic clinical document"):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Brand", fontName="Helvetica-Bold", fontSize=11, textColor=TEAL, spaceAfter=16))
    styles.add(ParagraphStyle(name="ReportTitle", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=NAVY, spaceAfter=8))
    styles.add(ParagraphStyle(name="Subtitle", fontName="Helvetica", fontSize=10, leading=14, textColor=MUTED, spaceAfter=16))
    styles.add(ParagraphStyle(name="SectionLabel", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=TEAL, spaceBefore=14, spaceAfter=7))
    styles.add(ParagraphStyle(name="FieldText", fontName="Helvetica", fontSize=10, leading=15, textColor=NAVY, spaceAfter=4))
    styles.add(ParagraphStyle(name="SmallNote", fontName="Helvetica", fontSize=9, leading=13, textColor=MUTED))
    doc = SimpleDocTemplate(str(path), pagesize=letter, rightMargin=48, leftMargin=48, topMargin=38, bottomMargin=65,
                            title=title + " - synthetic test document", author="CancerCare AI synthetic fixture generator")
    blocks = [Paragraph("CANCERCARE AI / TEST LABORATORY", styles["Brand"]),
              Paragraph(escape(title), styles["ReportTitle"]), Paragraph(escape(subtitle), styles["Subtitle"])]
    identity_lines = [f"Patient: {case['name']}", f"Patient ID: {case['id']}",
                      f"DOB: {case['dob']}", f"Report date: {date}"]
    panel = Table([[Paragraph(escape(line), styles["FieldText"])] for line in identity_lines], colWidths=[516])
    panel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE), ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#DCE4EB")),
                               ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    blocks.extend([panel, Spacer(1, 7)])
    for heading, lines in sections:
        blocks.append(Paragraph(escape(heading.upper()), styles["SectionLabel"]))
        for line in lines:
            blocks.append(Paragraph(escape(line), styles["FieldText"]))
    blocks.extend([Spacer(1, 18), Paragraph("This invented report exists only to test document extraction and review. It is not a signed clinical result, medical guidance, or an authorization to treat. No guideline citations are supplied.", styles["SmallNote"])])
    doc.build(blocks, onFirstPage=_footer, onLaterPages=_footer)


def pathology_sections(case, markers=None):
    grade = case["grade"] if case["grade"] != "Not documented" else UNKNOWN
    return [
        ("Specimen and diagnosis", [f"Cancer type: {case['cancer_type']}", f"Histological diagnosis: {case['histology']}",
                                    f"Cancer site: {case['site']}", f"Grade: {grade}",
                                    f"Tumor size: {UNKNOWN}", f"Clinical stage: {UNKNOWN}"]),
        ("Biomarker results", [f"{name}: {value}" for name, value, _status in (markers or case["markers"])]),
        ("Limitations", ["Biopsy findings do not establish complete clinical stage or nodal status.",
                          "No definitive resection tumor measurement is available in this report.",
                          "Pending or unperformed biomarker tests are not negative results."]),
    ]


def generate():
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for case in _CASES:
        for doc_id, title, date, kind, filename in case["documents"]:
            if kind == "Pathology":
                sections = pathology_sections(case)
                expected = "Actual text extraction; missing stage/size; no guideline evidence or treatment pathways."
            elif kind == "Imaging":
                sections = [("Imaging observations", [f"Site: {case['site']}", f"Imaging lesion measurement: {case['measurement']}",
                                                       "This measurement is from imaging and is not a pathologic tumor size.",
                                                       "Nodal and distant staging: Not established in this excerpt."]),
                            ("Context", ["This synthetic imaging summary has incomplete clinical context.",
                                         "Refer to the separate pathology report for tissue findings.",
                                         "No overall clinical stage is assigned."])]
                expected = "Viewable supporting document; no pathology measurements or stage should be inferred."
            else:
                sections = [("Endoscopy observations", ["Site: Ascending colon", "A lesion was sampled during colonoscopy.",
                                                        "Lesion measurement: Not available in this excerpt.",
                                                        "The separate synthetic biopsy report contains the histological diagnosis."]),
                            ("Context", ["This endoscopy summary does not establish clinical TNM stage.",
                                         "No treatment order or therapeutic plan is recorded."])]
                expected = "Viewable supporting document; no clinical stage should be inferred."
            target = SAMPLE_DIR / filename
            report(target, title, case, date, sections)
            manifest.append({"filename": filename, "patient_id": case["id"], "document_id": doc_id, "expected": expected})
        snapshot = ROOT / "backend" / "fixtures_data" / f"{case['id']}.json"
        snapshot.write_text(json.dumps(get_summary(case["id"])["fhir"], indent=2), encoding="utf-8")
    breast = _CASES[0]
    contradiction_markers = [("ER", "Negative 0%", "documented"), ("PR", "Positive 65%", "documented"),
                             ("HER2", "IHC 3+ / positive", "documented"), ("Ki-67", "18%", "documented")]
    report(SAMPLE_DIR / "breast-contradiction.pdf", "Pathology - conflicting test fixture", breast, "2026-10-21",
           pathology_sections(breast, contradiction_markers), "Deliberately conflicting biomarkers for reconciliation testing")
    manifest.append({"filename": "breast-contradiction.pdf", "patient_id": breast["id"],
                     "expected": "ER and HER2 conflict with the chart; show reconciliation and block approval until acknowledged."})
    report(SAMPLE_DIR / "missing-findings.pdf", "Pathology - incomplete test fixture", breast, "2026-10-21",
           [("Incomplete specimen note", ["Patient ID is documented, but diagnostic findings are absent from this excerpt.",
                                          "Histological diagnosis: Not available in report", "Grade: Not available in report",
                                          "Clinical stage: Not available in report", "Biomarker results: Not available in report"]),
            ("Expected behavior", ["Extract only supported facts. Preserve missing data and do not infer a cancer diagnosis."])])
    manifest.append({"filename": "missing-findings.pdf", "patient_id": breast["id"],
                     "expected": "Missing facts remain unknown; no inferred diagnosis, stage, biomarker negatives or pathway."})
    import pymupdf
    with pymupdf.open(SAMPLE_DIR / "breast-pathology.pdf") as original:
        raster = original[0].get_pixmap(matrix=pymupdf.Matrix(1.3, 1.3)).tobytes("png")
    scanned = canvas.Canvas(str(SAMPLE_DIR / "scanned-report.pdf"), pagesize=letter)
    scanned.setTitle("Synthetic image-only pathology report - OCR error test")
    scanned.drawImage(ImageReader(io.BytesIO(raster)), 0, 0, width=letter[0], height=letter[1])
    scanned.showPage()
    scanned.save()
    manifest.append({"filename": "scanned-report.pdf", "patient_id": breast["id"],
                     "expected": "Reject with actionable OCR/text-PDF error; do not claim successful extraction."})
    for item in manifest:
        item["sha256"] = hashlib.sha256((SAMPLE_DIR / item["filename"]).read_bytes()).hexdigest()
    (SAMPLE_DIR / "manifest.json").write_text(json.dumps({"synthetic": True, "snapshot_date": "2026-10-21", "documents": manifest}, indent=2), encoding="utf-8")
    with zipfile.ZipFile(SAMPLE_DIR / "synthetic-ehr-test-pack.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in manifest:
            archive.write(SAMPLE_DIR / item["filename"], item["filename"])
        archive.write(SAMPLE_DIR / "manifest.json", "manifest.json")
        readme = SAMPLE_DIR / "README.md"
        if readme.exists():
            archive.write(readme, "README.md")
    print(f"Generated {len(manifest)} synthetic PDFs, 3 FHIR-shaped bundles, manifest and ZIP.")


if __name__ == "__main__":
    generate()
