import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Assessment, Patient, PatientSummary } from "./types";
import App from "./App";
import { api } from "./lib/api";
vi.mock("./lib/api", () => ({
  api: {
    patients: vi.fn(),
    knowledge: vi.fn(),
    session: vi.fn(),
    summary: vi.fn(),
    upload: vi.fn(),
    assess: vi.fn(),
    review: vi.fn(),
    blob: vi.fn(),
    export: vi.fn(),
  },
  downloadJson: vi.fn(),
}));
const ava: Patient = {
  id: "breast",
  name: "Ava Mitchell",
  initials: "AM",
  mrn: "DEMO-001",
  age: 54,
  sex: "Female",
  dob: "1972-04-18",
  cancer_type: "Breast cancer",
  diagnosis: "Invasive ductal carcinoma",
};
const noah: Patient = {
  ...ava,
  id: "lung",
  name: "Noah Reynolds",
  initials: "NR",
  mrn: "DEMO-002",
  age: 63,
  sex: "Male",
  cancer_type: "Lung cancer",
  diagnosis: "Pulmonary adenocarcinoma",
};
const findings = {
  cancer_type: { value: "Breast cancer", quote: "Breast cancer" },
  histological_diagnosis: {
    value: "Invasive ductal carcinoma",
    quote: "Invasive ductal carcinoma",
  },
  grade: { value: "Grade 2", quote: "Grade 2" },
  tumor_size: { value: "Not available in report", quote: "" },
  stage_tnm: { value: "Not available in report", quote: "" },
  biomarkers: [],
  other_findings: [],
  missing_information: ["Clinical staging"],
};
const assessment: Assessment = {
  assessment_id: "a-1",
  patient_id: "breast",
  upload_id: "u-1",
  status: "pending_clinician_review",
  revision: 1,
  created_at: "2026-10-21",
  processing_ms: 100,
  mode: "local",
  generation_mode: "local_factual_summary",
  findings,
  clinical_summary: "Ava-specific extracted factual summary.",
  missing_information: ["Clinical staging"],
  pathway_considerations: [],
  evidence: [],
  warnings: [],
  contradictions: [],
  source_status: "unavailable",
  clinician_edit: null,
  review_notes: "",
  audit: [],
  disclaimer: "No orders.",
};
function chart(
  patient: Patient,
  latest: Assessment | null = null,
): PatientSummary {
  return {
    patient,
    profile: {
      histology: patient.diagnosis,
      site: patient.id === "breast" ? "Left breast" : "Right lung",
      grade: "Grade 2",
      stage: "Not established",
      tumor_size: { value: "2.1 cm", source: "Imaging" },
      diagnosis_date: "2026-10-14",
      ecog: "Not documented",
    },
    biomarkers: [
      {
        name: patient.id === "breast" ? "ER" : "EGFR",
        value: patient.id === "breast" ? "Positive 92%" : "Pending",
        status: "documented",
        source: "Synthetic chart",
      },
    ],
    history: {
      medical: "Documented history",
      family: "Unknown",
      social: "Unknown",
    },
    allergies: [{ substance: "None documented", reaction: "" }],
    vitals: [{ name: "BP", value: "124/78" }],
    medications: [],
    care_team: [{ name: "Dr. E. Morgan", role: "Oncologist" }],
    timeline: [],
    gaps: ["Clinical staging"],
    documents: [],
    fhir: { resourceType: "Bundle" },
    latest_assessment: latest,
  };
}
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.patients).mockResolvedValue([ava, noah]);
  vi.mocked(api.knowledge).mockResolvedValue({
    guidelines_available: false,
    live_model_available: false,
    collections: [],
    warnings: [],
    medguide: { available: true, source_kind: "educational_mcqa" },
  });
  vi.mocked(api.session).mockImplementation(async (role) => ({
    token: "demo-token",
    role,
    reviewer: role === "oncologist" ? "Dr. E. Morgan" : "Jordan Lee",
    expires_at: "2026-10-22",
    demo: true,
  }));
  vi.mocked(api.summary).mockImplementation(async (id) =>
    chart(id === "lung" ? noah : ava, id === "breast" ? assessment : null),
  );
});
afterEach(cleanup);
describe("patient workspace isolation and review access", () => {
  it("keeps saved conflicts, source warnings and edited-text provenance visible after chart hydration", async () => {
    vi.mocked(api.summary).mockResolvedValue(
      chart(ava, {
        ...assessment,
        clinician_edit: "Clinician review text.",
        warnings: ["No authorized guideline evidence was available."],
        contradictions: [
          {
            field: "ER",
            chart_value: "Positive 92%",
            report_value: "Negative",
            message: "ER differs from the chart.",
            severity: "warning",
          },
        ],
      }),
    );
    render(
      <MemoryRouter initialEntries={["/?patient=breast&tab=ai"]}>
        <App />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("ER differs from the chart."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No authorized guideline evidence was available."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Clinician edit · not automatically validated"),
    ).toBeInTheDocument();
    expect(screen.getByText("Original generated summary")).toBeInTheDocument();
    expect(
      screen.getByText("Extracted findings & source quotations"),
    ).toBeInTheDocument();
  });
  it("requires a PDF and synthetic-data confirmation before submitting an upload", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Ava Mitchell" });
    await user.click(
      screen.getByRole("button", { name: "Upload pathology PDF" }),
    );
    const submit = screen.getByRole("button", { name: "Extract report" });
    expect(submit).toBeDisabled();
    await user.upload(
      screen.getByLabelText("Pathology PDF file"),
      new File(["%PDF-1.7 synthetic test"], "synthetic.pdf", {
        type: "application/pdf",
      }),
    );
    expect(submit).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: "I confirm this file contains synthetic patient data.",
      }),
    );
    expect(submit).toBeEnabled();
    vi.mocked(api.upload).mockRejectedValue(
      new Error("The PDF has no extractable text. OCR is required."),
    );
    await user.click(submit);
    expect(
      await screen.findByText(
        "The PDF has no extractable text. OCR is required.",
      ),
    ).toBeInTheDocument();
    expect(api.upload).toHaveBeenCalled();
    expect(api.assess).not.toHaveBeenCalled();
  });
  it("refreshes every patient-specific panel and clears the prior assessment on patient switch", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    expect(
      await screen.findByRole("heading", { name: "Ava Mitchell" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Ava-specific extracted factual summary."),
    ).toBeInTheDocument();
    await user.selectOptions(
      screen.getByLabelText("Synthetic patient chart"),
      "lung",
    );
    expect(
      await screen.findByRole("heading", { name: "Noah Reynolds" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Ava-specific extracted factual summary."),
    ).not.toBeInTheDocument();
    expect(screen.getByText("EGFR")).toBeInTheDocument();
    expect(screen.queryByText("ER")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
  });
  it("ignores a delayed previous-patient summary after navigation", async () => {
    const user = userEvent.setup();
    const stale = deferred<PatientSummary>();
    let breastRequests = 0;
    vi.mocked(api.summary).mockImplementation(async (id) =>
      id === "breast" && breastRequests++ === 0
        ? stale.promise
        : chart(id === "lung" ? noah : ava),
    );
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await user.click(
      await screen.findByRole("button", { name: /Find patient/ }),
    );
    await user.click(
      await screen.findByRole("button", { name: /Noah Reynolds/ }),
    );
    expect(
      await screen.findByRole("heading", { name: "Noah Reynolds" }),
    ).toBeInTheDocument();
    await act(async () => stale.resolve(chart(ava, assessment)));
    expect(
      screen.getByRole("heading", { name: "Noah Reynolds" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Ava-specific extracted factual summary."),
    ).not.toBeInTheDocument();
  });
  it("prevents the navigator session from approving, editing, or rejecting", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Ava Mitchell" });
    expect(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
    await user.selectOptions(screen.getByLabelText("Demo role"), "navigator");
    await waitFor(() => expect(api.session).toHaveBeenCalledWith("navigator"));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled(),
    );
    expect(screen.getByRole("button", { name: "Edit" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(
      screen.getByText(/Navigator role: review actions/),
    ).toBeInTheDocument();
  });
  it("displays missing guideline evidence and never invents source citations", async () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Ava Mitchell" });
    expect(
      screen.getByText("Guideline evidence unavailable"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Unsupported treatment pathways are withheld."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /Open source/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Draft preparation")).toHaveValue("local");
  });
  it("does not apply a stale document after leaving and returning to the same patient", async () => {
    const user = userEvent.setup();
    const document = deferred<Blob>();
    vi.mocked(api.blob).mockReturnValue(document.promise);
    vi.mocked(api.summary).mockImplementation(async (id) => {
      const result = chart(id === "lung" ? noah : ava);
      result.documents = [
        {
          id: "report-1",
          title: "Pathology report",
          date: "2026-10-14",
          type: "Pathology",
          status: "Signed",
          url: "/api/sample.pdf",
        },
      ];
      return result;
    });
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { name: "Ava Mitchell" });
    await user.click(
      screen.getByRole("button", { name: "Analyze Pathology report" }),
    );
    await user.selectOptions(
      screen.getByLabelText("Synthetic patient chart"),
      "lung",
    );
    await screen.findByRole("heading", { name: "Noah Reynolds" });
    await user.selectOptions(
      screen.getByLabelText("Synthetic patient chart"),
      "breast",
    );
    await screen.findByRole("heading", { name: "Ava Mitchell" });
    await act(async () =>
      document.resolve(new Blob(["%PDF-1.7"], { type: "application/pdf" })),
    );
    expect(api.upload).not.toHaveBeenCalled();
    expect(screen.getByText("Awaiting report")).toBeInTheDocument();
  });
});
