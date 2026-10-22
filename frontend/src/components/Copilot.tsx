import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  AlertCircle,
  Check,
  CheckCheck,
  Clock3,
  FileText,
  Loader2,
  Pencil,
  ShieldCheck,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import type {
  Assessment,
  Knowledge,
  PatientSummary,
  Session,
  Upload,
} from "@/types";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "./ui/dialog";
import { Badge, Notice, Status } from "./shared";
const schema = z.object({
  notes: z.string().max(4000, "Keep review notes under 4,000 characters."),
  edited_text: z.string().max(12000, "Keep the draft under 12,000 characters."),
});
type Values = z.infer<typeof schema>;
export function ReviewDialog({
  action,
  assessment,
  onClose,
  onSave,
  busy,
  error,
}: {
  action: "approve" | "edit" | "reject" | null;
  assessment?: Assessment;
  onClose: () => void;
  onSave: (
    action: "approve" | "edit" | "reject",
    values: Values,
  ) => Promise<void>;
  busy: boolean;
  error: string;
}) {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { notes: "", edited_text: "" },
  });
  useEffect(() => {
    form.reset({
      notes: "",
      edited_text:
        assessment?.clinician_edit || assessment?.clinical_summary || "",
    });
  }, [action, assessment?.assessment_id, form]);
  if (!action || !assessment) return null;
  const titles = {
    approve: "Approve for documentation",
    edit: "Edit the draft assessment",
    reject: "Reject the draft",
  };
  return (
    <Dialog
      open={!!action}
      onOpenChange={(open) => !open && !busy && onClose()}
    >
      <DialogContent>
        <DialogTitle className="modal-title">{titles[action]}</DialogTitle>
        <DialogDescription className="modal-description">
          {action === "approve"
            ? "Approval records review of this draft documentation. It does not authorize treatment, sign an EHR order, or resolve missing evidence."
            : action === "edit"
              ? "Your text is stored as a clinician-authored edit. The original generated draft and its evidence remain available."
              : "Record why this draft should not be used. The original draft remains in the local review history."}
        </DialogDescription>
        <form
          onSubmit={form.handleSubmit(async (values) => {
            if (action !== "approve" && !values.notes.trim()) {
              form.setError("notes", {
                message: "A review rationale is required.",
              });
              return;
            }
            if (action === "edit" && !values.edited_text.trim()) {
              form.setError("edited_text", {
                message: "Enter the revised draft text.",
              });
              return;
            }
            await onSave(action, values);
          })}
        >
          {action === "edit" && (
            <div className="form-field">
              <label htmlFor="edited-draft">Clinician-edited draft</label>
              <textarea
                id="edited-draft"
                className="input"
                rows={8}
                {...form.register("edited_text")}
              />
              {form.formState.errors.edited_text && (
                <p className="field-error">
                  {form.formState.errors.edited_text.message}
                </p>
              )}
            </div>
          )}
          <div className="form-field">
            <label htmlFor="review-notes">
              Review rationale{" "}
              {action !== "approve"
                ? "*"
                : "(required when reconciling conflicts)"}
            </label>
            <textarea
              id="review-notes"
              className="input"
              rows={3}
              placeholder="Record your review, edits, or reason for rejection…"
              {...form.register("notes")}
            />
            {form.formState.errors.notes && (
              <p className="field-error">
                {form.formState.errors.notes.message}
              </p>
            )}
          </div>
          {error && <Notice tone="red">{error}</Notice>}
          <div className="modal-actions">
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant={action === "reject" ? "destructive" : "default"}
              disabled={busy}
            >
              {busy ? (
                <Loader2 className="animate-spin" />
              ) : action === "approve" ? (
                <CheckCheck />
              ) : action === "edit" ? (
                <Pencil />
              ) : (
                <X />
              )}
              {busy
                ? "Saving review…"
                : action === "edit"
                  ? "Save edited draft"
                  : titles[action]}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function Copilot({
  summary,
  upload,
  assessment,
  knowledge,
  session,
  processing,
  error,
  onUpload,
  onAnalyze,
  onCancel,
  onReview,
  onAssessmentTab,
}: {
  summary: PatientSummary;
  upload?: Upload;
  assessment?: Assessment;
  knowledge?: Knowledge;
  session?: Session;
  processing: string;
  error: string;
  onUpload: () => void;
  onAnalyze: (mode: "local" | "openai", consent: boolean) => void;
  onCancel: () => void;
  onReview: (action: "approve" | "edit" | "reject") => void;
  onAssessmentTab: () => void;
}) {
  const [mode, setMode] = useState<"local" | "openai">("local");
  const [consent, setConsent] = useState(false);
  useEffect(() => {
    setMode("local");
    setConsent(false);
  }, [summary.patient.id, upload?.upload_id]);
  const gaps =
    assessment?.missing_information ||
    upload?.findings.missing_information ||
    summary.gaps;
  const canReview =
    !!assessment && session?.role === "oncologist" && !processing;
  return (
    <aside className="right-column" aria-label="Oncology AI Copilot">
      <section className="clinical-card copilot">
        <header className="copilot-head">
          <div className="flex-row between">
            <span className="ai-mark">
              <Sparkles size={20} />
            </span>
            {processing ? (
              <Badge tone="blue">
                <Loader2 size={12} className="animate-spin" /> Processing
              </Badge>
            ) : (
              <Status status={assessment?.status} />
            )}
          </div>
          <h2>Oncology AI Copilot</h2>
          <p>
            Traceable findings. Evidence-aware drafts.
            <br />
            Your clinical judgment stays in control.
          </p>
        </header>
        <section className="copilot-section">
          <div className="section-title">
            <h3>Pathology intake</h3>
            <span className="meta">
              {upload ? "Report extracted" : "Awaiting report"}
            </span>
          </div>
          {upload ? (
            <div className="uploaded-file">
              <FileText size={21} />
              <div>
                <strong>{upload.filename}</strong>
                <small>
                  {(upload.processing_ms / 1000).toFixed(2)} s · Local
                  rule-based extraction
                </small>
              </div>
              <Check size={15} />
            </div>
          ) : (
            <button className="upload-zone" onClick={onUpload}>
              <UploadCloud size={24} />
              <strong>Add pathology report</strong>
              <span>Synthetic, text-based PDF · up to 10 MB</span>
            </button>
          )}
          {upload && (
            <button
              className="text-button"
              onClick={onUpload}
              disabled={!!processing}
            >
              Replace report
            </button>
          )}
          {processing && (
            <div className="processing-status" role="status">
              <Loader2 className="animate-spin" size={17} />
              <div>
                <strong>{processing}</strong>
                <small>Processing the selected report</small>
              </div>
              <button className="text-button" onClick={onCancel}>
                Cancel
              </button>
            </div>
          )}
          {error && (
            <Notice tone="red" title="Could not complete">
              {error}
            </Notice>
          )}
          {upload?.warnings.map((warning, i) => (
            <p className="inline-warning" key={i}>
              <AlertCircle size={14} />
              {warning}
            </p>
          ))}
          {upload && !upload.compatible && (
            <Notice tone="red" title="Report incompatible with chart">
              Select the matching patient or replace this report before
              continuing.
            </Notice>
          )}
          {upload && upload.contradictions.length > 0 && upload.compatible && (
            <Notice title="Reconciliation needed">
              Review the report/chart differences in Pathology. A reconciliation
              rationale is required when approving the draft.
            </Notice>
          )}
          <label htmlFor="analysis-mode" className="small-label">
            Draft preparation
          </label>
          <select
            id="analysis-mode"
            className="input"
            value={mode}
            onChange={(e) => {
              setMode(e.target.value as "local" | "openai");
              setConsent(false);
            }}
            disabled={!!processing}
          >
            <option value="local">Local factual summary · no LLM</option>
            <option value="openai" disabled={!knowledge?.live_model_available}>
              AI + authorized guideline retrieval
              {!knowledge?.live_model_available ? " · not configured" : ""}
            </option>
          </select>
          {mode === "openai" && (
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              I authorize sending this synthetic report and permitted source
              excerpts to OpenAI.
            </label>
          )}
          <Button
            className="w-full mt-3"
            disabled={
              !upload ||
              !upload.compatible ||
              !!processing ||
              !session ||
              (mode === "openai" && !consent)
            }
            onClick={() => onAnalyze(mode, consent)}
          >
            <Sparkles size={15} />
            {processing ? "Processing…" : "Prepare draft assessment"}
          </Button>
        </section>
        <section className="copilot-section">
          <div className="section-title">
            <h3>Draft assessment</h3>
            {assessment && (
              <span className="meta">
                <Clock3 size={12} />{" "}
                {(assessment.processing_ms / 1000).toFixed(2)} s
              </span>
            )}
          </div>
          {assessment ? (
            <>
              <Badge tone="blue">
                {assessment.generation_mode === "local_factual_summary"
                  ? "Local factual summary"
                  : assessment.generation_mode === "openai_extraction_only"
                    ? "AI extraction · no guideline evidence"
                    : "AI-assisted draft"}
              </Badge>
              <p className="copilot-summary">
                {assessment.clinician_edit || assessment.clinical_summary}
              </p>
              {assessment.clinician_edit && (
                <small className="muted-copy">
                  Clinician edit · automated citation checks do not validate
                  edited text.
                </small>
              )}
              <button className="text-button" onClick={onAssessmentTab}>
                Review full assessment <span aria-hidden>→</span>
              </button>
            </>
          ) : (
            <p className="empty-copy">
              The draft will appear here after a report is extracted. Missing
              information stays explicit.
            </p>
          )}
        </section>
        <section className="copilot-section">
          <div className="section-title">
            <h3>Required information</h3>
            <span className="meta">{gaps.length} gaps</span>
          </div>
          <ul className="gap-list">
            {gaps.map((gap) => (
              <li key={gap}>
                <AlertCircle size={15} />
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </section>
        <section className="copilot-section">
          <div className="section-title">
            <h3>Retrieval evidence</h3>
            <span className="meta">Sources & citations</span>
          </div>
          {assessment?.evidence.length ? (
            <>
              <Badge tone="teal">
                <ShieldCheck size={12} />
                {assessment.evidence.length} retrieved excerpts
              </Badge>
              {assessment.evidence.slice(0, 2).map((e) => (
                <div className="source-card" key={e.id}>
                  <strong>{e.title}</strong>
                  <small>
                    {e.publisher} · {e.version} · {e.location}
                  </small>
                </div>
              ))}
              <button className="text-button" onClick={onAssessmentTab}>
                Inspect source excerpts →
              </button>
            </>
          ) : (
            <div className="source-empty">
              <ShieldCheck size={18} />
              <strong>Guideline evidence unavailable</strong>
              <p>
                {knowledge?.guidelines_available
                  ? "An authorized collection is configured; this draft has no qualifying evidence."
                  : "No authorized, verified guideline collection is connected."}
              </p>
              <span>Unsupported treatment pathways are withheld.</span>
            </div>
          )}
          {knowledge?.medguide.available && (
            <p className="research-note">
              MedGUIDE research scenarios are available separately. They are not
              clinical guideline evidence.
            </p>
          )}
        </section>
        <section className="copilot-section">
          <div className="section-title">
            <h3>Oncologist review</h3>
            <ShieldCheck size={14} />
          </div>
          <div className="review-actions">
            <Button
              size="sm"
              variant="outline"
              disabled={
                !canReview ||
                assessment?.status === "approved_for_documentation" ||
                assessment?.status === "rejected"
              }
              onClick={() => onReview("approve")}
            >
              <CheckCheck />
              Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!canReview}
              onClick={() => onReview("edit")}
            >
              <Pencil />
              Edit
            </Button>
            <Button
              size="sm"
              variant="destructive"
              disabled={
                !canReview ||
                assessment?.status === "approved_for_documentation" ||
                assessment?.status === "rejected"
              }
              onClick={() => onReview("reject")}
            >
              <X />
              Reject
            </Button>
          </div>
          <p className="review-note">
            {session?.role === "navigator"
              ? "Navigator role: review actions require the demo oncologist session."
              : "Approval is for draft documentation only."}
          </p>
        </section>
        <footer className="copilot-section">
          <Notice title="Research demonstration">
            Synthetic records only. No treatment orders or prescriptions. Not
            validated for clinical use.
          </Notice>
        </footer>
      </section>
    </aside>
  );
}
