import { useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import {
  Activity,
  ArrowUpRight,
  ClipboardList,
  FileText,
  FlaskConical,
  HeartPulse,
  History,
  Layers,
  ShieldCheck,
  UserRound,
  Users,
  AlertTriangle,
  Stethoscope,
  Braces,
} from "lucide-react";
import type {
  Assessment,
  ClinicalDocument,
  Patient,
  PatientSummary,
  Section,
  Upload,
} from "@/types";
import { Badge, Card, formatDate, Notice, Status } from "./shared";

export function PatientContext({
  summary,
  patients,
  onPatient,
  knowledgeReady,
}: {
  summary: PatientSummary;
  patients: Patient[];
  onPatient: (id: string) => void;
  knowledgeReady: boolean;
}) {
  const s = summary;
  return (
    <aside className="left-column column" aria-label="Patient 360">
      <div className="storyboard-identity">
        <div className="storyboard-avatar">{s.patient.initials}</div>
        <strong>{s.patient.name}</strong>
        <span>
          {s.patient.age} years · {s.patient.sex}
        </span>
        <span>DOB {formatDate(s.patient.dob)}</span>
        <span className="storyboard-mrn">MRN {s.patient.mrn}</span>
        <div className="storyboard-allergies">
          {s.allergies.map((a) => (
            <Badge
              key={a.substance}
              tone={/none/i.test(a.substance) ? "neutral" : "red"}
            >
              {a.substance}
              {a.reaction ? ` · ${a.reaction}` : ""}
            </Badge>
          ))}
        </div>
        <span className="storyboard-demo">SYNTHETIC PATIENT · DEMO ONLY</span>
      </div>
      <Card
        title="Patient 360"
        icon={UserRound}
        aside={<span className="meta">FHIR-shaped</span>}
      >
        <div className="card-body">
          <label className="eyebrow" htmlFor="patient-select">
            Synthetic patient chart
          </label>
          <select
            id="patient-select"
            value={s.patient.id}
            onChange={(e) => onPatient(e.target.value)}
            className="input select-patient"
          >
            {patients.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.cancer_type}
              </option>
            ))}
          </select>
          <div className="separator" />
          <div className="field-grid">
            {[
              ["Diagnosis date", formatDate(s.profile.diagnosis_date)],
              ["Cancer site", s.profile.site],
              ["Care status", "Workup in progress"],
              ["Performance status", s.profile.ecog || "Not documented"],
            ].map(([label, value]) => (
              <div className="field" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <div className="separator" />
          <div className="eyebrow">Care team</div>
          {s.care_team.map((member) => (
            <div className="team-row" key={member.name}>
              <span className="team-avatar">
                <Users size={15} />
              </span>
              <div>
                <strong>{member.name}</strong>
                <small>{member.role}</small>
              </div>
              <span className="availability" aria-label="Assigned" />
            </div>
          ))}
        </div>
      </Card>
      <Card
        title="Clinical alerts"
        icon={AlertTriangle}
        aside={<Badge tone="amber">Needs review</Badge>}
      >
        <div className="card-body alert-list">
          <div>
            <span className="alert-dot amber" />
            <div>
              <strong>Staging incomplete</strong>
              <small>{s.profile.stage}</small>
            </div>
          </div>
          <div>
            <span className="alert-dot amber" />
            <div>
              <strong>Therapy not initiated</strong>
              <small>No treatment orders recorded</small>
            </div>
          </div>
          <div>
            <span className="alert-dot blue" />
            <div>
              <strong>Guideline evidence</strong>
              <small>
                {knowledgeReady
                  ? "Authorized collection available"
                  : "Authorized source required"}
              </small>
            </div>
          </div>
        </div>
      </Card>
      <Card
        title="Vitals & history"
        icon={HeartPulse}
        aside={<span className="meta">Chart data</span>}
      >
        <div className="card-body">
          <div className="vitals-grid">
            {s.vitals.map((v) => (
              <div className="vital" key={v.name}>
                <span>{v.name}</span>
                <strong>{v.value}</strong>
              </div>
            ))}
          </div>
          <div className="separator" />
          <div className="eyebrow">Relevant history</div>
          <p className="muted-copy">{s.history.medical}</p>
        </div>
      </Card>
    </aside>
  );
}

export function Documents({
  documents,
  onView,
  onUse,
}: {
  documents: ClinicalDocument[];
  onView: (doc: ClinicalDocument) => void;
  onUse: (doc: ClinicalDocument) => void;
}) {
  const columns = useMemo<ColumnDef<ClinicalDocument>[]>(
    () => [
      {
        accessorKey: "title",
        header: "Document",
        cell: (info) => (
          <div className="document-name">
            <span className="file-icon">
              <FileText size={17} />
            </span>
            <div>
              <strong>{info.getValue<string>()}</strong>
              <small>{info.row.original.type}</small>
            </div>
          </div>
        ),
      },
      {
        accessorKey: "date",
        header: "Date",
        cell: (info) => (
          <span className="nowrap">{formatDate(info.getValue<string>())}</span>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <Badge tone="teal">{info.getValue<string>()}</Badge>,
      },
      {
        id: "actions",
        header: "",
        cell: (info) => (
          <div className="table-actions">
            <button
              className="text-button"
              onClick={() => onView(info.row.original)}
              aria-label={`View ${info.row.original.title}`}
            >
              View <ArrowUpRight size={12} />
            </button>
            {/pathology/i.test(
              info.row.original.type + " " + info.row.original.title,
            ) && (
              <button
                className="text-button"
                onClick={() => onUse(info.row.original)}
                aria-label={`Analyze ${info.row.original.title}`}
              >
                Analyze
              </button>
            )}
          </div>
        ),
      },
    ],
    [onView, onUse],
  );
  const table = useReactTable({
    data: documents,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });
  return (
    <Card
      title="Clinical documents"
      icon={ClipboardList}
      aside={<span className="meta">{documents.length} documents</span>}
    >
      <div className="table-wrap">
        <table>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((h) => (
                  <th key={h.id}>
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Profile({ summary }: { summary: PatientSummary }) {
  const p = summary.profile;
  return (
    <div className="card-body">
      <div className="diagnosis-panel">
        <div className="diagnosis-top">
          <div>
            <h4>{summary.patient.diagnosis}</h4>
            <p>Synthetic chart · Documented {formatDate(p.diagnosis_date)}</p>
          </div>
          <Badge tone="amber">Staging incomplete</Badge>
        </div>
        <dl className="profile-grid">
          <div>
            <dt>Cancer site</dt>
            <dd>{p.site}</dd>
          </div>
          <div>
            <dt>Histology</dt>
            <dd>{p.histology}</dd>
          </div>
          <div>
            <dt>Grade</dt>
            <dd>{p.grade}</dd>
          </div>
          <div>
            <dt>Measurement</dt>
            <dd>
              {p.tumor_size.value}
              <small>{p.tumor_size.source}</small>
            </dd>
          </div>
        </dl>
        <div className="biomarker-grid">
          {summary.biomarkers.map((b) => (
            <div className="biomarker" key={b.name}>
              <span>{b.name}</span>
              <strong
                className={
                  /pending|unknown|not /i.test(b.value) ? "pending" : ""
                }
              >
                {b.value}
              </strong>
              <small>{b.source}</small>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Timeline({ summary }: { summary: PatientSummary }) {
  return (
    <Card
      title="Cancer care timeline"
      icon={Layers}
      aside={<span className="meta">Clinical journey</span>}
    >
      <ol className="timeline">
        {summary.timeline.map((event) => (
          <li
            className={event.status === "pending" ? "pending" : ""}
            key={event.id}
          >
            <div className="timeline-top">
              <strong>{event.title}</strong>
              <span>{formatDate(event.date)}</span>
            </div>
            <p>{event.detail}</p>
          </li>
        ))}
      </ol>
      <div className="card-footer">
        <ShieldCheck size={14} /> No treatment orders are placed by this
        workspace.
      </div>
    </Card>
  );
}

export function FindingsView({
  upload,
  summary,
  onView,
}: {
  upload: Upload;
  summary: PatientSummary;
  onView: () => void;
}) {
  const f = upload.findings;
  const rows = [
    ["Cancer type", summary.patient.cancer_type, f.cancer_type],
    ["Histology", summary.profile.histology, f.histological_diagnosis],
    ["Grade", summary.profile.grade, f.grade],
    ["Measurement", summary.profile.tumor_size.value, f.tumor_size],
    ["Stage / TNM", summary.profile.stage, f.stage_tnm],
  ] as const;
  return (
    <Card
      title="Report extraction & provenance"
      icon={FlaskConical}
      aside={<Badge tone="blue">Local rules</Badge>}
    >
      <div className="card-body">
        <div className="flex-row between">
          <p className="muted-copy">
            {upload.filename} · {(upload.processing_ms / 1000).toFixed(2)} s
          </p>
          <button className="text-button" onClick={onView}>
            Open PDF <ArrowUpRight size={12} />
          </button>
        </div>
        <Notice tone="neutral">
          Extracted from PDF text using explicit labels and rules. Review
          quotations; this is not an LLM interpretation.
        </Notice>
        {upload.contradictions.map((c, i) => (
          <Notice
            key={i}
            tone={c.severity === "error" ? "red" : "amber"}
            title="Chart / report reconciliation"
          >
            {c.message}
            <p>
              Chart: {c.chart_value} · Report: {c.report_value}
            </p>
          </Notice>
        ))}
        <div className="extraction-list">
          {rows.map(([name, chart, report]) => (
            <div className="extraction-row" key={name}>
              <strong>{name}</strong>
              <div>
                <span className="eyebrow">Existing chart</span>
                <p>{chart}</p>
              </div>
              <div>
                <span className="eyebrow">Uploaded report</span>
                <p>{report.value}</p>
                {report.quote && <blockquote>{report.quote}</blockquote>}
              </div>
            </div>
          ))}
          {f.biomarkers.map((b) => (
            <div className="extraction-row" key={b.name}>
              <strong>{b.name}</strong>
              <div>
                <span className="eyebrow">Existing chart</span>
                <p>
                  {summary.biomarkers.find(
                    (m) => m.name.toUpperCase() === b.name.toUpperCase(),
                  )?.value || "Not documented"}
                </p>
              </div>
              <div>
                <span className="eyebrow">Uploaded report</span>
                <p>{b.value}</p>
                <blockquote>{b.quote}</blockquote>
              </div>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export function EvidenceView({ assessment }: { assessment?: Assessment }) {
  return (
    <Card
      title="Assessment evidence"
      icon={ShieldCheck}
      aside={<span className="meta">Source traceability</span>}
    >
      <div className="card-body">
        {!assessment?.evidence.length ? (
          <Notice title="Guideline evidence unavailable">
            No qualifying authorized guideline excerpts are attached. No
            guideline-supported treatment pathway is generated.
          </Notice>
        ) : (
          assessment.evidence.map((e) => (
            <article className="evidence-card" key={e.id}>
              <Badge tone="teal">{e.id}</Badge>
              <h4>{e.title}</h4>
              <p>
                {e.publisher} · {e.version} · {e.location}
              </p>
              <blockquote>{e.text}</blockquote>
              <small>
                Retrieval similarity {e.score?.toFixed(3)}; not clinical
                confidence.
              </small>
              {e.url && (
                <a
                  href={e.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-button"
                >
                  Open source <ArrowUpRight size={13} />
                </a>
              )}
            </article>
          ))
        )}
      </div>
    </Card>
  );
}

export function ClinicalViews({
  section,
  summary,
  upload,
  assessment,
  onView,
  onUse,
  onViewUpload,
}: {
  section: Section;
  summary: PatientSummary;
  upload?: Upload;
  assessment?: Assessment;
  onView: (doc: ClinicalDocument) => void;
  onUse: (doc: ClinicalDocument) => void;
  onViewUpload: () => void;
}) {
  const titles: Record<Section, string> = {
    overview: "Oncology care overview",
    history: "Longitudinal clinical history",
    pathology: "Pathology & biomarkers",
    timeline: "Cancer treatment journey",
    medications: "Medications & safety",
    ai: "Clinical decision support",
  };
  const days = Math.max(
    0,
    Math.floor(
      (new Date("2026-10-21T12:00:00Z").valueOf() -
        new Date(summary.profile.diagnosis_date).valueOf()) /
        86400000,
    ),
  );
  return (
    <main id="main-content" className="center-column column" tabIndex={-1}>
      <div className="center-title">
        <h2>{titles[section]}</h2>
        <span className="meta">Synthetic chart</span>
      </div>
      <div className="stats-grid">
        <div className="stat">
          <span>Days since diagnosis</span>
          <strong>{Number.isNaN(days) ? "—" : days}</strong>
          <small>As of Oct 21, 2026</small>
        </div>
        <div className="stat">
          <span>Information gaps</span>
          <strong className="amber-text">
            {assessment?.missing_information.length || summary.gaps.length}
          </strong>
          <small>Clinical review needed</small>
        </div>
        <div className="stat">
          <span>Available reports</span>
          <strong>{summary.documents.length + (upload ? 1 : 0)}</strong>
          <small>Traceable sources</small>
        </div>
        <div className="stat">
          <span>Assessment</span>
          <strong className="stat-status">
            {assessment
              ? assessment.status === "approved_for_documentation"
                ? "Approved"
                : assessment.status === "rejected"
                  ? "Rejected"
                  : "In review"
              : "Not started"}
          </strong>
          <small>Documentation only</small>
        </div>
      </div>
      {(section === "overview" || section === "pathology") && (
        <Card
          title="Oncology profile"
          icon={Stethoscope}
          aside={<Badge tone="teal">Chart record</Badge>}
        >
          <Profile summary={summary} />
        </Card>
      )}
      {section === "history" && (
        <Card title="Longitudinal record" icon={History}>
          <div className="card-body detail-stack">
            {[
              ["Medical history", summary.history.medical],
              ["Family history", summary.history.family],
              ["Social history", summary.history.social],
              [
                "Recent oncology assessment",
                `${summary.patient.diagnosis}. ${summary.profile.stage}.`,
              ],
            ].map(([name, text]) => (
              <article className="note-box" key={name}>
                <h4>{name}</h4>
                <p>{text}</p>
              </article>
            ))}
          </div>
        </Card>
      )}
      {section === "pathology" &&
        (upload ? (
          <FindingsView
            upload={upload}
            summary={summary}
            onView={onViewUpload}
          />
        ) : (
          <Notice tone="neutral" title="Compare source and report">
            Upload a synthetic pathology PDF or analyze a chart document to
            review extracted findings alongside existing chart data. Chart
            values are never automatically overwritten.
          </Notice>
        ))}
      {section === "timeline" && (
        <Notice title="Diagnostic workup in progress">
          Staging and clinical context remain incomplete. Timeline events
          represent chart documentation; draft preparation does not start or
          schedule treatment.
        </Notice>
      )}
      {section === "medications" && (
        <>
          <Card title="Allergies & adverse reactions" icon={AlertTriangle}>
            <div className="card-body detail-stack">
              {summary.allergies.map((a) => (
                <Notice
                  tone={
                    a.substance.toLowerCase().includes("none")
                      ? "neutral"
                      : "red"
                  }
                  key={a.substance}
                >
                  <strong>{a.substance}</strong> {a.reaction}
                </Notice>
              ))}
            </div>
          </Card>
          <Card title="Medication reconciliation" icon={ClipboardList}>
            <div className="card-body">
              {summary.medications.map((m) => (
                <article className="medication-row" key={m.name}>
                  <div>
                    <h4>{m.name}</h4>
                    <p>{m.note}</p>
                  </div>
                  <Badge>{m.status}</Badge>
                </article>
              ))}
              <Notice title="Reconciliation required">
                Medication data are synthetic and may be incomplete. This
                workspace does not prescribe or place medication orders.
              </Notice>
            </div>
          </Card>
        </>
      )}
      {section === "ai" && (
        <>
          <Card
            title="Draft assessment"
            icon={Activity}
            aside={<Status status={assessment?.status} />}
          >
            <div className="card-body">
              {assessment ? (
                <>
                  <Badge tone="blue">
                    {assessment.clinician_edit
                      ? "Clinician edit · not automatically validated"
                      : assessment.generation_mode === "local_factual_summary"
                        ? "Local factual summary"
                        : assessment.generation_mode ===
                            "openai_extraction_only"
                          ? "AI extraction · no guideline evidence"
                          : "AI draft · citation checked"}
                  </Badge>
                  {assessment.contradictions.map((c, i) => (
                    <Notice
                      key={`conflict-${i}`}
                      tone={c.severity === "error" ? "red" : "amber"}
                      title="Chart / report reconciliation"
                    >
                      {c.message}
                      <p>
                        Chart: {c.chart_value} · Report: {c.report_value}
                      </p>
                    </Notice>
                  ))}
                  {assessment.warnings.map((warning, i) => (
                    <Notice key={`warning-${i}`} tone="neutral">
                      {warning}
                    </Notice>
                  ))}
                  <p className="assessment-copy">
                    {assessment.clinician_edit || assessment.clinical_summary}
                  </p>
                  {assessment.clinician_edit && (
                    <details>
                      <summary>Original generated summary</summary>
                      <p className="muted-copy">
                        {assessment.clinical_summary}
                      </p>
                    </details>
                  )}
                  <details className="saved-findings">
                    <summary>Extracted findings & source quotations</summary>
                    {[
                      {
                        name: "Cancer type",
                        ...assessment.findings.cancer_type,
                      },
                      {
                        name: "Histology",
                        ...assessment.findings.histological_diagnosis,
                      },
                      { name: "Grade", ...assessment.findings.grade },
                      {
                        name: "Measurement",
                        ...assessment.findings.tumor_size,
                      },
                      { name: "Stage / TNM", ...assessment.findings.stage_tnm },
                      ...assessment.findings.biomarkers,
                    ].map((f, i) => (
                      <div className="saved-finding" key={`${f.name}-${i}`}>
                        <strong>{f.name}</strong>
                        <p>{f.value}</p>
                        {f.quote && <blockquote>{f.quote}</blockquote>}
                      </div>
                    ))}
                  </details>
                  {assessment.pathway_considerations.map((p, i) => (
                    <article className="note-box" key={i}>
                      <h4>{p.title}</h4>
                      <p>{p.conditional_assessment}</p>
                      <ul>
                        {p.prerequisites.map((x) => (
                          <li key={x}>{x}</li>
                        ))}
                      </ul>
                      {p.citations.map((c) => (
                        <blockquote key={c.chunk_id}>
                          {c.quote}
                          <cite>{c.chunk_id}</cite>
                        </blockquote>
                      ))}
                    </article>
                  ))}
                  {!assessment.pathway_considerations.length && (
                    <Notice>
                      No supported treatment pathway is available.
                    </Notice>
                  )}
                </>
              ) : (
                <div className="empty-state">
                  <ShieldCheck size={34} />
                  <h4>Start with the source report</h4>
                  <p>
                    Upload a synthetic PDF to extract findings, identify
                    clinical gaps, and prepare a draft for review.
                  </p>
                </div>
              )}
            </div>
          </Card>
          <EvidenceView assessment={assessment} />
          {assessment && (
            <Card title="Documentation review history" icon={History}>
              <div className="card-body audit-list">
                {assessment.audit.length ? (
                  assessment.audit.map((a, i) => (
                    <div key={i}>
                      <Badge tone={a.action === "approve" ? "teal" : "neutral"}>
                        {a.action}
                      </Badge>
                      <p>
                        <strong>{a.reviewer}</strong> · {a.role}
                      </p>
                      <small>
                        {new Date(a.at).toLocaleString()} · revision{" "}
                        {a.revision}
                      </small>
                      {a.notes && <p>{a.notes}</p>}
                      {assessment.revision_history?.find(
                        (r) => r.revision === a.revision,
                      ) && (
                        <details>
                          <summary>
                            View documentation at revision {a.revision}
                          </summary>
                          <p className="assessment-copy">
                            {(() => {
                              const r = assessment.revision_history!.find(
                                (r) => r.revision === a.revision,
                              )!;
                              return r.clinician_edit || r.clinical_summary;
                            })()}
                          </p>
                        </details>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="muted-copy">No review actions yet.</p>
                )}
              </div>
            </Card>
          )}
        </>
      )}
      {section !== "medications" && section !== "ai" && (
        <Timeline summary={summary} />
      )}
      <Documents documents={summary.documents} onView={onView} onUse={onUse} />
      {section === "history" && (
        <Card title="FHIR-shaped source bundle" icon={Braces}>
          <div className="card-body">
            <p className="muted-copy">
              Synthetic FHIR R4-shaped resources. No live EHR connection.
            </p>
            <details>
              <summary>Inspect source resources</summary>
              <pre className="json-preview">
                {JSON.stringify(summary.fhir, null, 2)}
              </pre>
            </details>
          </div>
        </Card>
      )}
    </main>
  );
}
