import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  Bell,
  ClipboardList,
  Download,
  FileText,
  HeartPulse,
  HelpCircle,
  LayoutDashboard,
  Layers,
  Loader2,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  UserRound,
  UsersRound,
  X,
} from "lucide-react";
import { api, downloadJson } from "@/lib/api";
import type {
  Assessment,
  ClinicalDocument,
  Knowledge,
  Patient,
  PatientSummary,
  Role,
  Section,
  Session,
  Upload,
} from "@/types";
import { PatientContext, ClinicalViews } from "@/components/ClinicalViews";
import { Copilot, ReviewDialog } from "@/components/Copilot";
import { Badge, formatDate, Notice } from "@/components/shared";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

const sections: { id: Section; label: string; icon: typeof Activity }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "history", label: "Clinical History", icon: UserRound },
  { id: "pathology", label: "Pathology & Biomarkers", icon: FileText },
  { id: "timeline", label: "Treatment Journey", icon: Layers },
  { id: "medications", label: "Medications", icon: ClipboardList },
  { id: "ai", label: "AI Assessment", icon: Sparkles },
];
type Modal = "upload" | "search" | "help" | "sources" | "notifications" | null;
const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "The request could not be completed.";
const isAbort = (error: unknown) =>
  error instanceof DOMException && error.name === "AbortError";

export default function App() {
  const [params, setParams] = useSearchParams();
  const layout = params.get("layout") === "modern" ? "modern" : "classic";
  const currentParams = useRef(params);
  currentParams.current = params;
  const setChartParams = (patient: string, tab: Section) => {
    const next = new URLSearchParams(currentParams.current);
    next.set("patient", patient);
    next.set("tab", tab);
    setParams(next);
  };
  const changeLayout = (nextLayout: "classic" | "modern") =>
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set("layout", nextLayout);
        return next;
      },
      { replace: true },
    );
  const [patients, setPatients] = useState<Patient[]>([]);
  const [summary, setSummary] = useState<PatientSummary>();
  const [knowledge, setKnowledge] = useState<Knowledge>();
  const [session, setSession] = useState<Session>();
  const [roleBusy, setRoleBusy] = useState(false);
  const [bootError, setBootError] = useState("");
  const [chartError, setChartError] = useState("");
  const [reload, setReload] = useState(0);
  const [upload, setUpload] = useState<Upload>();
  const [assessment, setAssessment] = useState<Assessment>();
  const [processing, setProcessing] = useState("");
  const [error, setError] = useState("");
  const [modal, setModal] = useState<Modal>(null);
  const [search, setSearch] = useState("");
  const [file, setFile] = useState<File>();
  const [confirmed, setConfirmed] = useState(false);
  const [fileError, setFileError] = useState("");
  const [reviewAction, setReviewAction] = useState<
    "approve" | "edit" | "reject" | null
  >(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewError, setReviewError] = useState("");
  const [toast, setToast] = useState("");
  const [viewer, setViewer] = useState<{ title: string; url: string }>();
  const [documentBusy, setDocumentBusy] = useState(false);
  const patientId = params.get("patient") || patients[0]?.id || "";
  const section: Section = sections.some((s) => s.id === params.get("tab"))
    ? (params.get("tab") as Section)
    : "overview";
  const currentId = useRef(patientId);
  currentId.current = patientId;
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const selectedFileInput = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const abort = new AbortController();
    setBootError("");
    Promise.all([
      api.patients(abort.signal),
      api.knowledge(),
      api.session("oncologist"),
    ])
      .then(([p, k, s]) => {
        if (abort.signal.aborted) return;
        setPatients(p);
        setKnowledge(k);
        setSession(s);
      })
      .catch((e) => {
        if (!isAbort(e) && !abort.signal.aborted) setBootError(errorText(e));
      });
    return () => abort.abort();
  }, [reload]);
  useEffect(() => {
    if (!patientId) return;
    const abort = new AbortController();
    controller.current?.abort();
    generation.current++;
    setSummary(undefined);
    setUpload(undefined);
    setAssessment(undefined);
    setProcessing("");
    setError("");
    setChartError("");
    setReviewAction(null);
    setViewer(undefined);
    setModal(null);
    setFile(undefined);
    setConfirmed(false);
    api
      .summary(patientId, abort.signal)
      .then((s) => {
        if (!abort.signal.aborted) {
          setSummary(s);
          setAssessment(s.latest_assessment || undefined);
        }
      })
      .catch((e) => {
        if (!isAbort(e) && !abort.signal.aborted) setChartError(errorText(e));
      });
    return () => abort.abort();
  }, [patientId, reload]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(t);
  }, [toast]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setModal("search");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(
    () => () => {
      if (viewer) URL.revokeObjectURL(viewer.url);
    },
    [viewer],
  );
  useEffect(() => () => controller.current?.abort(), []);
  const navigatePatient = (id: string) => {
    controller.current?.abort();
    generation.current++;
    setChartParams(id, "overview");
    setModal(null);
    setSearch("");
  };
  const navigateSection = (next: Section) => setChartParams(patientId, next);
  const openUpload = () => {
    setFile(undefined);
    setConfirmed(false);
    setFileError("");
    setModal("upload");
  };
  async function switchRole(role: Role) {
    setRoleBusy(true);
    try {
      const next = await api.session(role);
      setSession(next);
      setToast(
        `Demo ${role === "oncologist" ? "oncologist" : "nurse navigator"} session active.`,
      );
    } catch (e) {
      setToast(errorText(e));
    } finally {
      setRoleBusy(false);
    }
  }
  async function extractFile(nextFile: File) {
    if (!session) return;
    const pid = patientId;
    const ownGeneration = ++generation.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setError("");
    setUpload(undefined);
    setAssessment(undefined);
    setProcessing("Extracting PDF text…");
    setModal(null);
    setChartParams(pid, "pathology");
    try {
      const result = await api.upload(
        pid,
        nextFile,
        session.token,
        abort.signal,
      );
      if (currentId.current !== pid || ownGeneration !== generation.current)
        return;
      setUpload(result);
      setToast(
        "PDF extracted. Compare report findings with the chart before drafting.",
      );
    } catch (e) {
      if (
        !isAbort(e) &&
        currentId.current === pid &&
        ownGeneration === generation.current
      )
        setError(errorText(e));
    } finally {
      if (currentId.current === pid && ownGeneration === generation.current)
        setProcessing("");
    }
  }
  const useDocument = useCallback(
    async (doc: ClinicalDocument) => {
      if (!session || processing || documentBusy) return;
      const pid = currentId.current;
      const ownGeneration = ++generation.current;
      setDocumentBusy(true);
      setError("");
      try {
        const blob = await api.blob(doc.url, session.token);
        if (currentId.current !== pid || ownGeneration !== generation.current)
          return;
        const filename = `${doc.id}.pdf`;
        await extractFile(
          new File([blob], filename, { type: "application/pdf" }),
        );
      } catch (e) {
        if (currentId.current === pid && ownGeneration === generation.current)
          setError(errorText(e));
      } finally {
        setDocumentBusy(false);
      }
    },
    [patientId, session, processing, documentBusy],
  );
  const viewDocument = useCallback(
    async (doc: ClinicalDocument) => {
      const pid = currentId.current;
      const ownGeneration = generation.current;
      setDocumentBusy(true);
      try {
        const blob = await api.blob(doc.url, session?.token);
        if (currentId.current !== pid || ownGeneration !== generation.current)
          return;
        setViewer({ title: doc.title, url: URL.createObjectURL(blob) });
      } catch (e) {
        if (currentId.current === pid && ownGeneration === generation.current)
          setToast(errorText(e));
      } finally {
        setDocumentBusy(false);
      }
    },
    [session],
  );
  async function prepareAssessment(mode: "local" | "openai", consent: boolean) {
    if (!session || !upload) return;
    const pid = patientId;
    const ownGeneration = ++generation.current;
    const abort = new AbortController();
    controller.current = abort;
    setError("");
    setAssessment(undefined);
    setProcessing(
      mode === "local"
        ? "Preparing factual draft…"
        : "Retrieving evidence and drafting…",
    );
    try {
      const result = await api.assess(
        pid,
        upload,
        mode,
        consent,
        session.token,
        abort.signal,
      );
      if (currentId.current !== pid || ownGeneration !== generation.current)
        return;
      setAssessment(result);
      setChartParams(pid, "ai");
      setToast(
        "Draft ready for clinician review. No treatment orders were created.",
      );
    } catch (e) {
      if (
        !isAbort(e) &&
        currentId.current === pid &&
        ownGeneration === generation.current
      )
        setError(errorText(e));
    } finally {
      if (currentId.current === pid && ownGeneration === generation.current)
        setProcessing("");
    }
  }
  function cancel() {
    controller.current?.abort();
    generation.current++;
    setProcessing("");
    setError(
      "Request canceled in this workspace. Any server-side processing already started may still finish; no result will be applied to this chart.",
    );
  }
  async function saveReview(
    action: "approve" | "edit" | "reject",
    values: { notes: string; edited_text: string },
  ) {
    if (!assessment || !session) return;
    const pid = patientId;
    const ownGeneration = generation.current;
    setReviewBusy(true);
    setReviewError("");
    try {
      const result = await api.review(
        assessment,
        action,
        values.notes,
        values.edited_text,
        session.token,
      );
      if (currentId.current !== pid || ownGeneration !== generation.current)
        return;
      setAssessment(result);
      setReviewAction(null);
      setToast(
        action === "approve"
          ? "Draft approved for documentation. No treatment order placed."
          : action === "edit"
            ? "Clinician edit saved; approval is pending."
            : "Draft rejected and review recorded.",
      );
    } catch (e) {
      if (currentId.current === pid && ownGeneration === generation.current)
        setReviewError(errorText(e));
    } finally {
      setReviewBusy(false);
    }
  }
  async function exportSummary() {
    if (!summary) return;
    const pid = patientId;
    const ownGeneration = generation.current;
    try {
      const exported = await api.export(
        pid,
        assessment?.assessment_id,
        session?.token,
      );
      if (currentId.current !== pid || ownGeneration !== generation.current)
        return;
      downloadJson(exported, "CancerCareAI_Synthetic_Summary.json");
      setToast(
        "Synthetic summary exported with known demo identifiers removed. Review any free text before sharing.",
      );
    } catch (e) {
      if (currentId.current === pid && ownGeneration === generation.current)
        setToast(errorText(e));
    }
  }

  const chartReady = summary?.patient.id === patientId;
  const patient = chartReady ? summary.patient : undefined;
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to patient chart
      </a>
      <div className={`app-shell ${layout}-ehr`}>
        {layout === "modern" && (
          <nav className="modern-rail" aria-label="Workspace shortcuts">
            <div className="modern-rail-brand" aria-hidden="true">
              <HeartPulse size={24} />
            </div>
            {sections.map((s) => (
              <button
                key={s.id}
                aria-label={`Open ${s.label}`}
                title={s.label}
                aria-current={section === s.id ? "page" : undefined}
                className={section === s.id ? "active" : ""}
                onClick={() => navigateSection(s.id)}
              >
                <s.icon size={20} />
              </button>
            ))}
            <div className="modern-rail-bottom">
              <span>CC</span>
              <small>WORKSPACE</small>
            </div>
          </nav>
        )}
        <div className="main-shell">
          <header className="topbar">
            <div className="brand">
              <HeartPulse size={23} aria-hidden="true" />
              <span>
                CancerCare <b>AI</b>
              </span>
              <small>ONCOLOGY WORKSPACE</small>
            </div>
            <div className="topbar-actions">
              <div
                className="layout-switch"
                role="group"
                aria-label="Workspace appearance"
              >
                <button
                  aria-pressed={layout === "classic"}
                  onClick={() => changeLayout("classic")}
                >
                  Classic
                </button>
                <button
                  aria-pressed={layout === "modern"}
                  onClick={() => changeLayout("modern")}
                >
                  Modern
                </button>
              </div>
              <button
                className="search-button"
                aria-label="Find patient"
                onClick={() => setModal("search")}
              >
                <Search size={16} />
                <span>Find patient</span>
                <kbd>Ctrl K</kbd>
              </button>
              <button
                className="top-tool"
                aria-label="Knowledge sources and settings"
                onClick={() => setModal("sources")}
              >
                <Settings2 size={15} />
                <span>Sources</span>
              </button>
              <button
                className="top-tool"
                aria-label="Help"
                onClick={() => setModal("help")}
              >
                <HelpCircle size={15} />
                <span>Help</span>
              </button>
              <Badge tone="amber" className="demo-badge">
                SYNTHETIC DEMO
              </Badge>
              <button
                className="icon-button notification-button"
                aria-label="Clinical notifications"
                onClick={() => setModal("notifications")}
              >
                <Bell size={18} />
                {summary?.gaps.length && <span />}
              </button>
              <div className="clinician">
                <span className="clinician-avatar">
                  {session?.role === "navigator" ? "SP" : "EM"}
                </span>
                <div>
                  <strong>{session?.reviewer || "Demo clinician"}</strong>
                  <label className="sr-only" htmlFor="demo-role">
                    Demo role
                  </label>
                  <select
                    id="demo-role"
                    value={session?.role || "oncologist"}
                    disabled={roleBusy || !!processing || reviewBusy}
                    onChange={(e) => switchRole(e.target.value as Role)}
                  >
                    <option value="oncologist">Oncologist · demo</option>
                    <option value="navigator">Nurse navigator · demo</option>
                  </select>
                </div>
              </div>
            </div>
          </header>
          <div className="workspace-header">
            <nav
              className="open-patient-tabs"
              aria-label="Open synthetic patient charts"
            >
              <span className="workspace-label">
                <UsersRound size={14} /> Patient charts
              </span>
              {patients.map((p) => (
                <button
                  key={p.id}
                  className={patientId === p.id ? "active" : ""}
                  aria-current={patientId === p.id ? "page" : undefined}
                  onClick={() => navigatePatient(p.id)}
                >
                  <UserRound size={14} />
                  <span>{p.name}</span>
                  <small>{p.mrn}</small>
                </button>
              ))}
            </nav>
            {patient && (
              <section className="patient-banner" aria-label="Patient identity">
                <div className="patient-identity">
                  <div className="patient-avatar">{patient.initials}</div>
                  <div>
                    <div className="patient-heading">
                      <h1>{patient.name}</h1>
                      <span className="synthetic-label">Synthetic patient</span>
                    </div>
                    <p>
                      {patient.mrn}
                      <span>•</span>
                      {patient.age} years, {patient.sex}
                      <span>•</span>DOB {formatDate(patient.dob)}
                    </p>
                  </div>
                </div>
                <div className="patient-tags">
                  <Badge tone="teal">
                    <Activity size={12} />
                    {patient.cancer_type}
                  </Badge>
                  <Badge tone="amber">Stage pending</Badge>
                  {summary?.allergies.map((a) => (
                    <Badge
                      key={a.substance}
                      tone={/none/i.test(a.substance) ? "neutral" : "red"}
                    >
                      {/none/i.test(a.substance)
                        ? a.substance
                        : `Allergy: ${a.substance}${a.reaction ? ` (${a.reaction})` : ""}`}
                    </Badge>
                  ))}
                  <Badge>New oncology referral</Badge>
                </div>
              </section>
            )}
          </div>
          {bootError || chartError ? (
            <div className="workspace-error">
              <Notice tone="red" title="Workspace unavailable">
                {bootError || chartError}
              </Notice>
              <Button variant="outline" onClick={() => setReload((r) => r + 1)}>
                Retry connection
              </Button>
            </div>
          ) : !chartReady ? (
            <div className="loading-chart" role="status">
              <Loader2 size={25} className="animate-spin" />
              <h2>Opening patient chart</h2>
              <p>Loading synthetic clinical records…</p>
            </div>
          ) : (
            <div className="workspace-grid">
              <PatientContext
                key={`storyboard:${patientId}`}
                summary={summary}
                patients={patients}
                onPatient={navigatePatient}
                knowledgeReady={!!knowledge?.guidelines_available}
              />
              <div className="chart-workspace">
                <div className="patient-navigation">
                  <nav
                    className="patient-tabs"
                    aria-label="Patient chart sections"
                  >
                    {sections.map((s) => (
                      <button
                        key={s.id}
                        aria-current={section === s.id ? "page" : undefined}
                        className={section === s.id ? "active" : ""}
                        onClick={() => navigateSection(s.id)}
                      >
                        <s.icon size={14} />
                        {s.label}
                      </button>
                    ))}
                  </nav>
                  <div className="workspace-actions">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={exportSummary}
                      disabled={!chartReady}
                    >
                      <Download />
                      Export summary
                    </Button>
                    <Button
                      size="sm"
                      onClick={openUpload}
                      disabled={!chartReady || !!processing || !session}
                    >
                      <UploadCloud />
                      Upload pathology PDF
                    </Button>
                  </div>
                </div>
                <ClinicalViews
                  key={`${patientId}:${section}`}
                  section={section}
                  summary={summary}
                  upload={upload}
                  assessment={assessment}
                  onView={viewDocument}
                  onUse={useDocument}
                  onViewUpload={() =>
                    upload &&
                    viewDocument({
                      id: upload.upload_id,
                      title: upload.filename,
                      date: "",
                      type: "Pathology",
                      status: "Uploaded",
                      url: upload.pdf_url,
                    })
                  }
                />
              </div>
              <Copilot
                key={`copilot:${patientId}`}
                summary={summary}
                upload={upload}
                assessment={assessment}
                knowledge={knowledge}
                session={session}
                processing={processing}
                error={error}
                onUpload={openUpload}
                onAnalyze={prepareAssessment}
                onCancel={cancel}
                onReview={(a) => {
                  setReviewError("");
                  setReviewAction(a);
                }}
                onAssessmentTab={() => navigateSection("ai")}
              />
            </div>
          )}
          <footer className="workspace-footer">
            <span>
              <ShieldCheck size={13} />
              Synthetic research workspace · No live EHR connection
            </span>
            <span>Local session · No treatment orders</span>
          </footer>
        </div>
      </div>
      <Dialog open={!!modal} onOpenChange={(open) => !open && setModal(null)}>
        <DialogContent className={modal === "sources" ? "max-w-2xl" : ""}>
          <DialogTitle className="modal-title">
            {modal === "upload"
              ? "Upload pathology report"
              : modal === "search"
                ? "Find a synthetic patient"
                : modal === "sources"
                  ? "Knowledge sources & workspace"
                  : modal === "notifications"
                    ? "Clinical attention items"
                    : "About CancerCare AI"}
          </DialogTitle>
          <DialogDescription className="modal-description">
            {modal === "upload"
              ? "Extract findings from a text-based synthetic pathology PDF. Chart facts remain unchanged."
              : modal === "search"
                ? "Select a chart to open the patient workspace."
                : modal === "sources"
                  ? "Source availability is reported by the Python backend."
                  : modal === "notifications"
                    ? "Current chart information gaps and source readiness."
                    : "An oncology research demonstration connecting source reports, clinical context, and clinician review."}
          </DialogDescription>
          {modal === "upload" && (
            <>
              <input
                ref={selectedFileInput}
                type="file"
                accept="application/pdf,.pdf"
                className="sr-only"
                aria-label="Pathology PDF file"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  setFileError("");
                  if (
                    f &&
                    (!f.name.toLowerCase().endsWith(".pdf") ||
                      f.size > 10 * 1024 * 1024)
                  ) {
                    setFile(undefined);
                    setFileError("Choose a PDF no larger than 10 MB.");
                    return;
                  }
                  setFile(f);
                }}
              />
              <button
                className="file-picker"
                onClick={() => selectedFileInput.current?.click()}
              >
                <UploadCloud size={30} />
                <strong>{file ? file.name : "Choose a PDF report"}</strong>
                <span>
                  {file
                    ? `${(file.size / 1024).toFixed(1)} KB`
                    : "Text-based PDF · maximum 10 MB · no scans"}
                </span>
              </button>
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                I confirm this file contains synthetic patient data.
              </label>
              {fileError && <Notice tone="red">{fileError}</Notice>}
              <Notice tone="neutral">
                The local extraction step does not send the report to an
                external model. Scanned reports require OCR and will be rejected
                with an explanation.
              </Notice>
              <div className="modal-actions">
                <Button variant="outline" onClick={() => setModal(null)}>
                  Cancel
                </Button>
                <Button
                  disabled={!file || !confirmed || !session}
                  onClick={() => file && extractFile(file)}
                >
                  <FileText />
                  Extract report
                </Button>
              </div>
            </>
          )}
          {modal === "search" && (
            <>
              <div className="search-input-wrap">
                <Search size={18} />
                <input
                  className="input"
                  autoFocus
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name, synthetic MRN, or cancer type"
                  aria-label="Search synthetic patients"
                />
              </div>
              <div className="patient-search-results">
                {patients
                  .filter((p) =>
                    `${p.name} ${p.mrn} ${p.cancer_type}`
                      .toLowerCase()
                      .includes(search.toLowerCase()),
                  )
                  .map((p) => (
                    <button key={p.id} onClick={() => navigatePatient(p.id)}>
                      <span className="patient-avatar small">{p.initials}</span>
                      <span>
                        <strong>{p.name}</strong>
                        <small>
                          {p.mrn} · {p.cancer_type}
                        </small>
                      </span>
                      <ArrowRight size={17} />
                    </button>
                  ))}
                {!patients.some((p) =>
                  `${p.name} ${p.mrn} ${p.cancer_type}`
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                ) && (
                  <p className="muted-copy">No matching synthetic patients.</p>
                )}
              </div>
            </>
          )}
          {modal === "sources" && (
            <div className="detail-stack">
              <Notice
                tone={knowledge?.guidelines_available ? "teal" : "amber"}
                title={
                  knowledge?.guidelines_available
                    ? "Authorized source collection available"
                    : "Guideline evidence unavailable"
                }
              >
                {knowledge?.guidelines_available
                  ? "Only qualifying retrieved excerpts may support generated pathways."
                  : "Add authorized, versioned guideline files and a completed permission manifest to enable the guideline pipeline."}
              </Notice>
              {knowledge?.collections.map((c) => (
                <article className="source-card" key={c.id}>
                  <div className="flex-row between">
                    <h4>{c.title}</h4>
                    <Badge>{c.status}</Badge>
                  </div>
                  <p>
                    {c.document_count} documents · {c.reason}
                  </p>
                </article>
              ))}
              <div className="form-field">
                <label htmlFor="settings-role">Demo reviewer role</label>
                <select
                  id="settings-role"
                  className="input"
                  value={session?.role || "oncologist"}
                  disabled={roleBusy || !!processing || reviewBusy}
                  onChange={(e) => switchRole(e.target.value as Role)}
                >
                  <option value="oncologist">Oncologist · demo</option>
                  <option value="navigator">Nurse navigator · demo</option>
                </select>
              </div>
              <div className="note-box">
                <h4>Model access</h4>
                <p>
                  {knowledge?.live_model_available
                    ? "OpenAI configuration is present. Live requests require explicit processing consent."
                    : "No live model key is configured. Local PDF extraction and factual draft preparation remain available."}
                </p>
              </div>
              <div className="note-box">
                <h4>MedGUIDE research index</h4>
                <p>
                  {knowledge?.medguide.available
                    ? "Local semantic search index is available in the existing MedGUIDE workspace."
                    : "Index not available."}{" "}
                  Generated MCQA scenarios are never substituted for clinical
                  guideline evidence.
                </p>
              </div>
              <p className="muted-copy">
                Demo roles enforce review permissions within this local
                application. They are not production authentication or
                professional credential verification.
              </p>
            </div>
          )}
          {modal === "notifications" && (
            <>
              <ul className="gap-list">
                {summary?.gaps.map((g) => (
                  <li key={g}>
                    <Activity size={15} />
                    {g}
                  </li>
                ))}
              </ul>
              <Notice title="Evidence readiness">
                {knowledge?.guidelines_available
                  ? "A versioned source collection is available."
                  : "No qualifying authorized guideline collection is connected."}
              </Notice>
            </>
          )}
          {modal === "help" && (
            <div className="detail-stack">
              <div className="note-box">
                <h4>1 · Review the patient chart</h4>
                <p>
                  Use Patient 360 or Ctrl K to switch among synthetic breast,
                  lung, and colon cancer charts. Each tab keeps the selected
                  patient context.
                </p>
              </div>
              <div className="note-box">
                <h4>2 · Extract a source report</h4>
                <p>
                  Upload a synthetic text PDF, or select Analyze on a pathology
                  document. Review verbatim quotations and resolve chart/report
                  discrepancies.
                </p>
              </div>
              <div className="note-box">
                <h4>3 · Prepare and review documentation</h4>
                <p>
                  Local mode produces a factual summary. Live mode requires
                  authorized evidence and model access for supported pathway
                  drafting. The oncologist demo role can edit, approve for
                  documentation, or reject.
                </p>
              </div>
              <Notice>
                No diagnosis or treatment accuracy is guaranteed. This workspace
                is not a validated clinical system and has no order-entry
                functionality.
              </Notice>
            </div>
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={!!viewer}
        onOpenChange={(open) => !open && setViewer(undefined)}
      >
        <DialogContent className="pdf-dialog">
          <DialogTitle className="modal-title">{viewer?.title}</DialogTitle>
          <DialogDescription className="modal-description">
            Synthetic source document · Read alongside extracted findings.
          </DialogDescription>
          {viewer && (
            <>
              <iframe
                src={viewer.url}
                title={`PDF preview: ${viewer.title}`}
                className="pdf-frame"
              />
              <a
                className="text-button"
                href={viewer.url}
                download={`${viewer.title}.pdf`}
              >
                Download this synthetic PDF
              </a>
            </>
          )}
        </DialogContent>
      </Dialog>
      <ReviewDialog
        action={reviewAction}
        assessment={assessment}
        onClose={() => setReviewAction(null)}
        onSave={saveReview}
        busy={reviewBusy}
        error={reviewError}
      />
      {documentBusy && (
        <div className="document-loading" role="status">
          <Loader2 size={15} className="animate-spin" /> Opening source
          document…
        </div>
      )}
      {toast && (
        <div className="toast" role="status">
          <ShieldCheck size={17} />
          <span>{toast}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
    </>
  );
}
