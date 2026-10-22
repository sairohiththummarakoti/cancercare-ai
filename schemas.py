"""Validated data contracts shared by the analysis pipeline and the UI."""

from pydantic import BaseModel, ConfigDict, Field

UNKNOWN = "Not available in report"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Finding(StrictModel):
    value: str
    quote: str


class Biomarker(StrictModel):
    name: str
    value: str
    quote: str


class PathologyFindings(StrictModel):
    cancer_type: Finding
    histological_diagnosis: Finding
    grade: Finding
    tumor_size: Finding
    stage_tnm: Finding
    biomarkers: list[Biomarker]
    other_findings: list[Finding]
    missing_information: list[str]


class Citation(StrictModel):
    chunk_id: str
    quote: str


class Pathway(StrictModel):
    title: str
    conditional_assessment: str
    citations: list[Citation]
    prerequisites: list[str]


class Assessment(StrictModel):
    pathways: list[Pathway]
    missing_information: list[str]
    limitations: list[str]


class PathwayCheck(StrictModel):
    pathway_index: int
    fully_supported: bool
    conditional: bool
    no_personalized_regimen_or_dose: bool


class AssessmentVerification(StrictModel):
    checks: list[PathwayCheck]
