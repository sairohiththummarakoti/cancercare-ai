import type {
  Assessment,
  Knowledge,
  Patient,
  PatientSummary,
  Role,
  Session,
  Upload,
} from "@/types";
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      "The clinical workspace API is unavailable. Start the FastAPI backend and retry.",
      0,
    );
  }
  if (!response.ok) {
    let detail = "The request could not be completed.";
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail))
        detail = "Some request fields were invalid. Review the form and retry.";
    } catch {
      /* No upstream content rendered. */
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}
export const api = {
  export: (patientId: string, assessmentId?: string, token?: string) =>
    request<unknown>(
      assessmentId
        ? `/assessments/${encodeURIComponent(assessmentId)}/export?patient_id=${encodeURIComponent(patientId)}`
        : `/patients/${encodeURIComponent(patientId)}/export`,
      {},
      token,
    ),
  patients: (signal?: AbortSignal) =>
    request<Patient[]>("/demo-patients", { signal }),
  summary: (id: string, signal?: AbortSignal) =>
    request<PatientSummary>(`/patients/${encodeURIComponent(id)}/summary`, {
      signal,
    }),
  knowledge: () => request<Knowledge>("/knowledge-sources"),
  session: (role: Role) =>
    request<Session>("/demo-session", {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
  upload: (id: string, file: File, token: string, signal?: AbortSignal) => {
    const form = new FormData();
    form.append("file", file);
    form.append("synthetic_confirmed", "true");
    return request<Upload>(
      `/patients/${encodeURIComponent(id)}/pathology`,
      { method: "POST", body: form, signal },
      token,
    );
  },
  assess: (
    id: string,
    upload: Upload,
    mode: "local" | "openai",
    consent: boolean,
    token: string,
    signal?: AbortSignal,
  ) =>
    request<Assessment>(
      "/assessments",
      {
        method: "POST",
        body: JSON.stringify({
          patient_id: id,
          upload_id: upload.upload_id,
          mode,
          api_consent: consent,
          collection_id: "authorized-guidelines",
        }),
        signal,
      },
      token,
    ),
  review: (
    assessment: Assessment,
    action: "approve" | "edit" | "reject",
    notes: string,
    edited_text: string,
    token: string,
  ) =>
    request<Assessment>(
      `/assessments/${assessment.assessment_id}/review`,
      {
        method: "POST",
        body: JSON.stringify({
          patient_id: assessment.patient_id,
          action,
          expected_revision: assessment.revision,
          notes,
          edited_text: action === "edit" ? edited_text : undefined,
        }),
      },
      token,
    ),
  blob: async (url: string, token?: string) => {
    if (!url.startsWith("/api/"))
      throw new Error("The requested document location is not supported.");
    const response = await fetch(url, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok)
      throw new Error("The requested document could not be opened.");
    return response.blob();
  },
};
export function downloadJson(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
