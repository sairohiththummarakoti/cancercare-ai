export type Role = "oncologist" | "navigator";
export type Section =
  "overview" | "history" | "pathology" | "timeline" | "medications" | "ai";
export interface Patient {
  id: string;
  name: string;
  initials: string;
  mrn: string;
  age: number;
  sex: string;
  dob: string;
  cancer_type: string;
  diagnosis: string;
}
export interface ClinicalDocument {
  id: string;
  title: string;
  date: string;
  type: string;
  status: string;
  url: string;
}
export interface PatientSummary {
  patient: Patient;
  profile: {
    histology: string;
    site: string;
    grade: string;
    stage: string;
    tumor_size: { value: string; source: string };
    diagnosis_date: string;
    ecog: string;
  };
  biomarkers: { name: string; value: string; status: string; source: string }[];
  history: { medical: string; family: string; social: string };
  allergies: { substance: string; reaction: string }[];
  vitals: { name: string; value: string }[];
  medications: { name: string; status: string; note: string }[];
  care_team: { name: string; role: string }[];
  timeline: {
    id: string;
    date: string;
    title: string;
    detail: string;
    status: string;
  }[];
  gaps: string[];
  documents: ClinicalDocument[];
  fhir: unknown;
  latest_assessment?: Assessment | null;
}
export interface Finding {
  value: string;
  quote: string;
}
export interface Findings {
  cancer_type: Finding;
  histological_diagnosis: Finding;
  grade: Finding;
  tumor_size: Finding;
  stage_tnm: Finding;
  biomarkers: (Finding & { name: string })[];
  other_findings: Finding[];
  missing_information: string[];
}
export interface Contradiction {
  field: string;
  chart_value: string;
  report_value: string;
  message: string;
  severity: "warning" | "error";
}
export interface Upload {
  upload_id: string;
  patient_id: string;
  filename: string;
  extraction_mode: string;
  findings: Findings;
  processing_ms: number;
  warnings: string[];
  contradictions: Contradiction[];
  compatible: boolean;
  pdf_url: string;
}
export interface Evidence {
  id: string;
  title: string;
  publisher: string;
  version: string;
  location: string;
  text: string;
  score: number;
  url: string;
}
export interface Assessment {
  assessment_id: string;
  patient_id: string;
  upload_id: string;
  status:
    | "pending_clinician_review"
    | "edited"
    | "approved_for_documentation"
    | "rejected";
  revision: number;
  created_at: string;
  processing_ms: number;
  mode: "local" | "openai";
  generation_mode: string;
  findings: Findings;
  clinical_summary: string;
  missing_information: string[];
  pathway_considerations: {
    title: string;
    conditional_assessment: string;
    prerequisites: string[];
    citations: { chunk_id: string; quote: string }[];
  }[];
  evidence: Evidence[];
  warnings: string[];
  contradictions: Contradiction[];
  source_status: string;
  clinician_edit: string | null;
  review_notes: string;
  revision_history?: {
    revision: number;
    status: string;
    clinical_summary: string;
    clinician_edit: string | null;
    review_notes: string;
    at: string;
  }[];
  audit: {
    action: string;
    reviewer: string;
    role: string;
    at: string;
    notes: string;
    revision: number;
  }[];
  disclaimer: string;
}
export interface Knowledge {
  guidelines_available: boolean;
  live_model_available: boolean;
  collections: {
    id: string;
    title: string;
    status: string;
    document_count: number;
    reason: string;
  }[];
  warnings: string[];
  medguide: { available: boolean; source_kind: string };
}
export interface Session {
  token: string;
  role: Role;
  reviewer: string;
  expires_at: string;
  demo: true;
}
