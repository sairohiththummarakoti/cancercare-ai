"""Explicit, hash-locked fixture replay. This is NOT a substitute for live RAG."""
import hashlib
import json
from pathlib import Path

from schemas import Assessment, Citation, PathologyFindings, Pathway

SAMPLES = Path(__file__).resolve().parent / "samples"
NCI_URL = "https://www.cancer.gov/types/breast/diagnosis/breast-cancer-biomarker-tests"
DEMO_LIMITATION = (
    "Sample fixture replay only: no language model or embedding retrieval was run. "
    "These authored educational notes are not NCCN guidelines or a personalized treatment plan."
)


def sample_catalog():
    manifest = SAMPLES / "manifest.json"
    if not manifest.exists():
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else data.get("samples", [])


def match_sample(data):
    digest = hashlib.sha256(data).hexdigest()
    return next((item for item in sample_catalog() if item["sha256"] == digest), None)


def replay_sample(data):
    item = match_sample(data)
    if not item or not item.get("findings"):
        raise ValueError("Sample demo supports only the included, unchanged text PDFs. Choose a sample below or use Live analysis for other reports.")
    findings = PathologyFindings.model_validate(item["findings"])
    biomarker = {b.name.upper(): b.value.lower() for b in findings.biomarkers}
    er = next((v for k, v in biomarker.items() if k == "ER" or "ESTROGEN" in k), "")
    her2 = next((v for k, v in biomarker.items() if "HER2" in k or "HER-2" in k), "")
    pr = next((v for k, v in biomarker.items() if k == "PR" or "PROGESTERONE" in k), "")
    source = None
    if "positive" in her2:
        source = ("demo-her2", "HER2 status", "HER2 status helps clinicians assess whether HER2-directed treatment may be relevant.",
                  "HER2 pathway discussion", "If the HER2 result and cancer diagnosis are confirmed, discuss whether a HER2-directed pathway is relevant after staging and clinical eligibility review.")
    elif "positive" in er:
        source = ("demo-er", "Breast cancer hormone receptor status", "Hormone-receptor-positive breast cancers are often treated using hormone therapy.",
                  "Hormone receptor pathway discussion", "If the hormone-receptor-positive diagnosis is confirmed, discuss whether an endocrine-treatment pathway is relevant after staging and clinical review.")
    elif "negative" in er and "negative" in pr and "negative" in her2:
        source = ("demo-tnbc", "Biomarker test results and molecular subtypes", "ER-negative, PR-negative and HER2-negative results define the triple-negative biomarker profile. This profile informs specialist evaluation of treatment options.",
                  "Triple-negative profile review", "If these receptor findings are confirmed, request specialist review of the triple-negative profile and complete staging before discussing treatment options.")
    chunks = []
    pathways = []
    if source:
        source_id, section, note, title, conditional = source
        chunks = [{"id": source_id, "title": "Authored demo note based on NCI Tests for Breast Cancer Biomarkers",
                   "version": "Demo note 1.0; NCI page posted December 2, 2025",
                   "location": section, "text": note, "source_file": "Built-in educational demo note",
                   "score": None, "url": NCI_URL}]
        pathways = [Pathway(title=title, conditional_assessment=conditional,
                            citations=[Citation(chunk_id=source_id, quote=note)],
                            prerequisites=["Confirm complete stage and clinical context with the oncology team.",
                                           "No specific drug, dose, regimen or eligibility is determined here."])]
    limitations = [DEMO_LIMITATION]
    if not pathways:
        limitations.append("No treatment pathway is displayed for this sample. Review the diagnosis and missing information before considering cancer treatment.")
    return findings, Assessment(pathways=pathways, missing_information=findings.missing_information, limitations=limitations), chunks
