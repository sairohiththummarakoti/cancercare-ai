"""Oncology Care AI: local, session-only pathology demonstration workspace."""
import hashlib
import html
import json
import time

import streamlit as st

from config import ROOT, make_client, settings
from demo import replay_sample, sample_catalog, SAMPLES
from pathology import extract_findings, extract_pdf_text
from rag import build_index, inspect_guidelines, retrieve
from review import APPROVED, PENDING, REJECTED, export_result, set_review
from schemas import Assessment, UNKNOWN
from treatment import generate_assessment
from medguide import read_pipeline_status
from medguide_ui import render_medguide_workspace, render_related_report_cases

st.set_page_config(page_title="Oncology Care AI", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container {max-width: 1260px; padding-top: 4.5rem; padding-bottom: 3rem;}
[data-testid="stSidebar"] {background: #102e3a;}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] h4,
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] .stCaption {color: #e2eff3;}
[data-testid="stSidebar"] [data-testid="stButton"] button p {color: #17313c;}
[data-testid="stSidebar"] [data-testid="stAlert"] p {color: #17313c;}
h1 {font-weight: 750 !important; letter-spacing: -1.5px;}
h2 {font-size: 1.4rem !important; letter-spacing: -.35px;}
.eyebrow {color: #087f8c; font-size: .76rem; font-weight: 750; letter-spacing: .13em; margin-bottom: .6rem;}
.subhead {color: #617680; margin-bottom: 1.8rem; font-size: 1.05rem;}
.safety {border-left: 3px solid #c49a41; background: #fff8e9; padding: .85rem 1rem; border-radius: 0 6px 6px 0; font-size: .88rem; margin: 1.2rem 0 1.6rem; color: #65552f;}
.stepbar {display:flex; justify-content:space-between; gap:12px; border-top:1px solid #dbe5ea; border-bottom:1px solid #dbe5ea; padding:14px 0; margin-bottom:1.8rem; color:#5f747e; font-size:.88rem;}
.stepbar b {color:#087f8c; margin-right:5px;}
.field-label {font-size: .73rem; text-transform: uppercase; letter-spacing: .07em; color: #6b7f88; margin-bottom: 5px;}
.field-value {color:#17313c; font-size:1rem; line-height:1.5; margin-bottom:18px; overflow-wrap:anywhere;}
.empty {padding:2rem 1rem 1.2rem; text-align:center; color:#6b7f88;}
@media(max-width:700px){.block-container{padding-top:4rem}.stepbar{flex-wrap:wrap;justify-content:flex-start}.stepbar span{width:43%}}
</style>
""", unsafe_allow_html=True)


def field(label, value):
    st.markdown(f'<div class="field-label">{html.escape(label)}</div><div class="field-value">{html.escape(value)}</div>', unsafe_allow_html=True)


cfg = settings()
corpus = inspect_guidelines(ROOT / "guidelines")
catalog = sample_catalog()
with st.sidebar:
    st.markdown("## ◈ Oncology Care AI")
    st.caption("CLINICIAN REVIEW WORKSPACE")
    st.divider()
    mode = st.radio("Analysis mode", ["Sample demo", "MedGUIDE search", "Live analysis"], key="mode")
    if mode == "Sample demo":
        st.caption("Repeatable results for the included synthetic reports. No API calls. No NCCN retrieval.")
    elif mode == "MedGUIDE search":
        st.caption("Real local embeddings and vector search over generated oncology research scenarios.")
    else:
        st.caption("OpenAI extraction + embedding retrieval over your authorized local guidelines.")
    st.divider()
    st.markdown("#### Workspace readiness")
    st.write(f"{'●' if cfg['api_key'] else '○'} OpenAI key {'configured' if cfg['api_key'] else 'not configured'}")
    st.write(f"{'●' if corpus['valid_files'] else '○'} {corpus['valid_files']} valid guideline files")
    st.write(f"● {len(catalog)} synthetic test reports")
    medguide_ready = read_pipeline_status()["indexed"]
    st.write(f"{'●' if medguide_ready else '○'} MedGUIDE index {'available' if medguide_ready else 'not built'}")
    st.caption("A configured key still requires a valid project, available model access and API billing.")
    with st.expander("Live mode setup"):
        st.write("Add an OpenAI key to your ignored .env.local file using secure setup. Put authorized guideline files and a completed manifest.json in guidelines/.")
        st.write("See the project README and guidelines/README.md for the exact format.")
        st.caption(f"Model: {cfg['model']} · Embeddings: {cfg['embedding_model']}")
    if st.button("Clear session", width="stretch"):
        for key in list(st.session_state):
            if key != "mode":
                del st.session_state[key]
        st.rerun()
    st.divider()
    st.caption("LOCAL RESEARCH DEMONSTRATION")
    st.caption("Reports and results stay in this session. Live mode sends extracted report text and guideline excerpts to OpenAI. No treatment orders or prescriptions.")

st.markdown('<div class="eyebrow">PATHOLOGY → EVIDENCE → CLINICIAN REVIEW</div>', unsafe_allow_html=True)
st.title("Oncology Care AI")
st.markdown('<div class="subhead">AI-Powered Pathology Analysis and Guideline-Grounded Treatment Planning.</div>', unsafe_allow_html=True)
st.markdown('<div class="safety"><b>Research demonstration only.</b> Not validated for clinical use. Final treatment decisions require qualified oncology professionals.</div>', unsafe_allow_html=True)
if st.session_state.get("active_mode") != mode:
    for key in ("result", "review_notes", "edit_text", "show_editor", "api_consent", "medguide_search_result", "medguide_report_matches"):
        st.session_state.pop(key, None)
    st.session_state.active_mode = mode
if mode == "MedGUIDE search":
    render_medguide_workspace()
    st.stop()
st.markdown('<div class="stepbar"><span><b>01</b> Add a report</span><span><b>02</b> Extract findings</span><span><b>03</b> Review evidence</span><span><b>04</b> Clinician review</span></div>', unsafe_allow_html=True)

left, right = st.columns([1.12, 1], gap="large")
with left:
    st.subheader("Start with a pathology report")
    st.caption("Upload one text-based PDF, or select a synthetic sample to try the complete workflow.")
    uploaded = st.file_uploader("Pathology report", type=["pdf"], key="report_upload", help="One text-based PDF, up to 10 MB. Scanned PDFs need OCR, which this demo does not provide.")
with right:
    st.subheader("Try a prepared test case")
    chosen = st.selectbox("Synthetic test reports", options=[None] + list(range(len(catalog))),
                          format_func=lambda i: "Choose a sample…" if i is None else catalog[i]["title"], key="sample_selection")
    if chosen is not None:
        item = catalog[chosen]
        st.caption(item["description"])
        st.download_button("Download this sample PDF", (SAMPLES / item["filename"]).read_bytes(), item["filename"], "application/pdf", width="stretch")
    else:
        st.caption("Known biomarker profiles, missing-information cases and a scanned-PDF error test.")

file_bytes = uploaded.getvalue() if uploaded is not None else ((SAMPLES / catalog[chosen]["filename"]).read_bytes() if chosen is not None else None)
filename = uploaded.name if uploaded is not None else (catalog[chosen]["filename"] if chosen is not None else "")
if uploaded is not None and chosen is not None:
    st.caption("Your uploaded PDF takes priority over the selected sample.")
identity = hashlib.sha256(file_bytes).hexdigest() + mode + filename if file_bytes else mode
if st.session_state.get("input_identity") != identity:
    for key in ("result", "review_notes", "edit_text", "show_editor", "api_consent", "medguide_report_matches"):
        st.session_state.pop(key, None)
    st.session_state["input_identity"] = identity

consent = True
if mode == "Live analysis":
    consent = st.checkbox("I am authorized to send this synthetic or appropriately de-identified report and these guideline excerpts to OpenAI.", key="api_consent")
    if not corpus["valid_files"]:
        st.info("No valid guideline corpus is available. Live mode can extract findings, but it will withhold guideline-grounded treatment pathways.")
    if not cfg["api_key"]:
        st.warning("No OpenAI API key is configured. Sample demo is ready to use now.")

analyze = st.button("Analyze & Generate Treatment Assessment", type="primary", width="stretch",
                    disabled=not file_bytes or not consent or (mode == "Live analysis" and not cfg["api_key"]))
if analyze:
    for key in ("result", "review_notes", "edit_text", "show_editor", "medguide_report_matches"):
        st.session_state.pop(key, None)
    started = time.perf_counter()
    with st.status("Reading the pathology report…", expanded=True) as progress:
        try:
            report_text = extract_pdf_text(file_bytes)
            st.write("Text extracted from the PDF.")
            if mode == "Sample demo":
                findings, assessment, chunks = replay_sample(file_bytes)
                st.write("Matched the exact synthetic sample and loaded its expected findings.")
                st.write("Loaded labeled educational notes. No live model or NCCN retrieval was used.")
            else:
                client = make_client()
                findings = extract_findings(report_text, client, cfg["model"])
                st.write("Structured findings extracted; unsupported values withheld.")
                index = build_index(ROOT / "guidelines", ROOT / ".cache" / "guidelines", client, cfg["embedding_model"])
                query_parts = [getattr(findings, name).value for name in ("cancer_type", "histological_diagnosis", "grade", "tumor_size", "stage_tnm")]
                query_parts += [f"{b.name}: {b.value}" for b in findings.biomarkers if b.value != UNKNOWN]
                chunks = retrieve("; ".join(v for v in query_parts if v != UNKNOWN), index, client, cfg["embedding_model"], top_k=5, min_similarity=cfg["min_similarity"])
                st.write(f"Retrieved {len(chunks)} evidence excerpts with embedding similarity search.")
                assessment = generate_assessment(findings, chunks, client, cfg["model"])
                assessment.limitations.extend(index.warnings)
                st.write("Draft completed with evidence checks and explicit information gaps.")
            elapsed = time.perf_counter() - started
            st.session_state.result = {"filename": filename, "mode": mode, "findings": findings, "assessment": assessment,
                                       "chunks": chunks, "elapsed": elapsed, "review_status": PENDING, "review_notes": ""}
            progress.update(label=f"Ready for review · {elapsed:.2f} seconds", state="complete", expanded=False)
        except Exception as exc:
            progress.update(label="Analysis could not complete", state="error", expanded=False)
            # Only application-owned errors are safe to display. SDK messages can include submitted data.
            if exc.__class__.__module__ in {"pathology", "rag", "treatment"} or type(exc) is ValueError:
                st.error(str(exc))
            else:
                st.error("Analysis could not complete. Check your API configuration, project billing and network connection, then try again. No draft was saved.")
            st.caption(f"Attempt duration: {time.perf_counter() - started:.2f} seconds")

result = st.session_state.get("result")
if result:
    st.divider()
    r1, r2, r3 = st.columns([2, 1, 1])
    r1.caption("REPORT")
    r1.write(result["filename"])
    r2.metric("Processing time", f"{result['elapsed']:.2f} s")
    r3.metric("Evidence excerpts", len(result["chunks"]))
    if result["mode"] == "Sample demo":
        st.info("Sample demo · Expected results from a matching fixture. This duration is fixture processing time, not AI or RAG performance.")
    findings = result["findings"]
    assessment = result["assessment"]
    st.subheader("A · Pathology summary")
    a, b, c = st.columns(3)
    with a:
        field("Cancer type", findings.cancer_type.value)
        field("Histological diagnosis", findings.histological_diagnosis.value)
    with b:
        field("Grade", findings.grade.value)
        field("Tumor size", findings.tumor_size.value)
    with c:
        field("Available stage / TNM", findings.stage_tnm.value)
        st.caption("Stage is not inferred from a biopsy or from absent information.")
    if findings.biomarkers:
        st.dataframe([{"Biomarker": b.name, "Reported result": b.value} for b in findings.biomarkers], hide_index=True, width="stretch")
    else:
        st.caption("Biomarkers: Not available in report")
    if findings.other_findings:
        for entry in findings.other_findings:
            st.write("• " + entry.value)
    with st.expander("Verify findings against the report"):
        for name in ("cancer_type", "histological_diagnosis", "grade", "tumor_size", "stage_tnm"):
            item = getattr(findings, name)
            if item.quote:
                st.caption(name.replace("_", " ").title())
                st.text(item.quote)
        for item in findings.biomarkers:
            if item.quote:
                st.caption(item.name)
                st.text(item.quote)

    st.subheader("B · " + ("Educational pathway discussion" if result["mode"] == "Sample demo" else "Potentially relevant guideline pathways"))
    if not assessment.pathways:
        st.warning("No supported treatment pathway is available. Findings and information gaps remain available for review.")
    for i, pathway in enumerate(assessment.pathways, 1):
        with st.container(border=True):
            st.markdown(f"**{i}. {pathway.title}**")
            st.write(pathway.conditional_assessment)
            for prerequisite in pathway.prerequisites:
                st.caption("Required review: " + prerequisite)
            st.caption("Evidence: " + ", ".join(c.chunk_id for c in pathway.citations))

    st.subheader("C · Evidence and citations")
    if not result["chunks"]:
        st.caption("No qualifying evidence retrieved. No NCCN-grounded assessment is claimed.")
    for chunk in result["chunks"]:
        with st.expander(f"{chunk['id']} · {chunk['title']}"):
            st.write(f"Version: {chunk['version']} · {chunk['location']}")
            if chunk.get("score") is not None:
                st.caption(f"Cosine similarity: {chunk['score']:.3f} · Retrieval score, not clinical confidence")
            st.text(chunk["text"])
            if chunk.get("url"):
                st.link_button("Read the NCI background source", chunk["url"])
            for i, pathway in enumerate(assessment.pathways, 1):
                for citation in pathway.citations:
                    if citation.chunk_id == chunk["id"]:
                        st.caption(f"Supports discussion {i}: {pathway.title}")
                        st.text(citation.quote)

    st.subheader("D · Information needed before planning")
    missing = list(dict.fromkeys(findings.missing_information + assessment.missing_information))
    if missing:
        for item in missing:
            st.write("☐ " + item)
    else:
        st.caption("No additional gaps were listed by this extraction. This does not establish completeness or treatment eligibility.")
    if assessment.limitations:
        with st.expander("Scope and limitations", expanded=not bool(assessment.pathways)):
            for limitation in dict.fromkeys(assessment.limitations):
                st.write("• " + limitation)

    render_related_report_cases(findings, identity)

    st.subheader("E · Clinician review")
    status = result["review_status"]
    (st.success if status == APPROVED else st.error if status == REJECTED else st.info)(status)
    st.caption("These controls update this session only. Approval does not sign an oncology plan, prescribe medication or order treatment.")
    if result.get("clinician_edit"):
        st.markdown("**Clinician-edited assessment**")
        st.text(result["clinician_edit"])
        st.caption("Clinician-authored content; not verified by the automated citation checks. Original AI/demo draft is preserved above.")
    notes = st.text_area("Reviewer notes", key="review_notes", placeholder="Record your review or reason for rejecting this draft.")
    c1, c2, c3 = st.columns(3)
    if c1.button("Approve for Documentation", width="stretch"):
        st.session_state.result = set_review(result, "approve", notes)
        st.rerun()
    if c2.button("Edit", width="stretch"):
        st.session_state.show_editor = True
    if c3.button("Reject", width="stretch"):
        st.session_state.result = set_review(result, "reject", notes)
        st.rerun()
    if st.session_state.get("show_editor"):
        initial = result.get("clinician_edit") or "\n\n".join(p.conditional_assessment for p in assessment.pathways)
        edited = st.text_area("Edit assessment text", value=initial, height=150, key="edit_text")
        if st.button("Save edited draft", disabled=not edited.strip()):
            st.session_state.result = set_review(result, "edit", edited)
            st.session_state.result["review_notes"] = notes.strip()
            st.session_state.pop("show_editor", None)
            st.rerun()
    st.download_button("Download review as JSON", json.dumps(export_result(result), indent=2, ensure_ascii=False),
                       "oncology-review.json", "application/json", width="stretch")
else:
    with st.container(border=True):
        st.markdown('<div class="empty"><b>Your review starts here</b><br><br>Select a sample or upload a report, then analyze it.<br>Findings, supporting evidence and clinical information gaps will appear together.</div>', unsafe_allow_html=True)
    st.caption("Use synthetic or appropriately de-identified reports only. No clinical validation is claimed.")
