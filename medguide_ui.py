"""Streamlit workspace for real local MedGUIDE ingestion and vector search."""
import json
import time

import streamlit as st

from medguide import DATASET_URL, MODEL_NAME, find_related_cases, findings_search_query, prepare_medguide, read_pipeline_status


def _safe_error(error):
    if error.__class__.__module__ in {"medguide_ingest", "medguide_vectors"} or type(error) is ValueError:
        st.error(str(error))
    else:
        st.error("MedGUIDE processing could not complete. Check the dataset download, available disk space and application dependencies.")


def show_case_matches(matches):
    if not matches:
        st.info("No cases passed the selected similarity threshold. Try a more specific query or a different disease filter.")
    for rank, match in enumerate(matches, 1):
        with st.container(border=True):
            cols = st.columns([3, 1])
            cols[0].markdown(f"**{rank}. {match.get('disease', 'Unspecified')} · Dataset row {match.get('row_index', 'unknown')}**")
            cols[1].caption(f"Cosine similarity {match['score']:.3f}")
            st.caption("Generated research scenario · Dataset-designated answer · Not a patient-specific recommendation")
            st.text(match["text"])
            if match.get("answer_text"):
                st.caption("Dataset-designated answer for this scenario")
                st.text(match["answer_text"])
            if match.get("profile"):
                with st.expander("Read the complete scenario before interpreting the answer"):
                    st.text(match["profile"])
                    st.caption("Decision path recorded by the dataset")
                    for step in match.get("path", []):
                        st.text("• " + step)
            with st.expander("Source and retrieval details"):
                st.write(f"Chunk: {match['id']}")
                st.write(f"Location: {match.get('location', 'Not supplied')}")
                st.write(f"Dataset revision: {match.get('revision', 'Not supplied')}")
                st.write("Original guideline version/page: not provided by this dataset")
                st.link_button("View source dataset", match.get("source_url", DATASET_URL))


def render_medguide_workspace():
    st.subheader("MedGUIDE knowledge base")
    st.write("Ingest the dataset, split it into traceable chunks, create local neural embeddings, and search for related oncology scenarios.")
    st.info("This dataset contains generated multiple-choice scenarios derived from guideline decision trees. Search results are research context, not original NCCN excerpts or treatment recommendations.")
    status = read_pipeline_status()
    pipeline = status.get("pipeline", {})
    index_info = pipeline.get("index", {})
    cols = st.columns(4)
    cols[0].metric("Ingested records", f"{pipeline.get('documents', 0):,}")
    cols[1].metric("Chunks", f"{index_info.get('chunk_count', pipeline.get('chunks_before_token_check', 0)):,}")
    cols[2].metric("Vector dimensions", index_info.get("dimensions", "—") if status["indexed"] else "—")
    cols[3].metric("Index", "Available" if status["indexed"] else "Not built")
    indexed_model = index_info.get("model_name", MODEL_NAME)
    st.caption(f"Embedding model: {indexed_model} · Local CPU inference · No OpenAI key required")
    with st.expander("Ingestion settings and provenance", expanded=not status["indexed"]):
        st.link_button("Open MedGUIDE-MCQA-8K", DATASET_URL)
        st.write("The full train split is downloaded at an immutable repository revision. Incorrect answer options and the question's instructions are excluded from the indexed content.")
        st.write("Chunking uses overlapping sections with record identifiers. Embeddings and source metadata are cached locally. Query text and query vectors are not saved.")
        st.caption('Dataset card license: "TBD. Intended for academic and research use." No explicit open license or original guideline edition is supplied; downloaded data is excluded from Git.')
        if pipeline:
            st.json({"dataset_revision": pipeline.get("ingestion", {}).get("revision"), "model": pipeline.get("model"),
                     "build_seconds": round(pipeline.get("elapsed_seconds", 0), 2), "source_kind": "educational_mcqa"}, expanded=False)
        if st.button("Ingest, chunk and build embeddings", key="medguide_build", width="stretch"):
            st.session_state.pop("medguide_search_result", None)
            with st.status("Preparing MedGUIDE…", expanded=True) as box:
                bar = st.progress(0)
                line = st.empty()
                def update(stage, message, done, total):
                    line.write(f"{message}: {done:,} / {total:,}" if total else message)
                    if total:
                        bar.progress(min(1.0, done / total))
                try:
                    prepare_medguide(progress=update)
                    box.update(label="MedGUIDE vector index is ready", state="complete", expanded=False)
                    st.rerun()
                except Exception as error:
                    box.update(label="Index preparation did not complete", state="error")
                    _safe_error(error)
    if not status["indexed"]:
        st.info("Build the index above to enable vector search. The first run downloads the dataset and embedding model.")
        return
    st.markdown("**Search the vector index**")
    st.caption("Example: ER positive HER2 negative invasive breast carcinoma after surgery")
    disease_counts = pipeline.get("ingestion", {}).get("disease_counts", {})
    with st.form("medguide_search_form"):
        query = st.text_area("Search query", value="ER positive HER2 negative invasive breast carcinoma", key="medguide_query", max_chars=4000)
        a, b, c = st.columns(3)
        top_k = a.slider("Maximum results", min_value=1, max_value=10, value=5)
        threshold = b.slider("Minimum cosine similarity", min_value=0.0, max_value=1.0, value=0.3, step=0.05)
        disease = c.selectbox("Disease code", ["All disease codes"] + sorted(disease_counts))
        submitted = st.form_submit_button("Run vector search", type="primary", width="stretch")
    if submitted:
        st.session_state.pop("medguide_search_result", None)
        if not query.strip():
            st.warning("Enter a query before searching.")
        else:
            start = time.perf_counter()
            with st.spinner("Embedding your query and comparing vectors locally…"):
                try:
                    matches = find_related_cases(query, top_k=top_k, disease=None if disease == "All disease codes" else disease, min_similarity=threshold)
                    st.session_state.medguide_search_result = {"query": query, "matches": matches, "seconds": time.perf_counter() - start,
                                                              "model": indexed_model, "source_kind": "educational_mcqa"}
                except Exception as error:
                    _safe_error(error)
    result = st.session_state.get("medguide_search_result")
    if result:
        st.caption(f"{len(result['matches'])} matched scenarios · {result['seconds']:.2f} seconds · Similarity measures retrieval relevance, not clinical confidence.")
        st.write("Results for: " + result["query"])
        show_case_matches(result["matches"])
        st.download_button("Download search results as JSON", json.dumps(result, indent=2), "medguide-search.json", "application/json")


def render_related_report_cases(findings, input_identity):
    """Bridge pathology results to dataset retrieval without treating MCQs as guidelines."""
    if not read_pipeline_status()["indexed"]:
        return
    with st.expander("Find related MedGUIDE research scenarios"):
        st.caption("Uses the reported findings as a local vector-search query. These cases do not establish treatment eligibility and do not replace guideline evidence.")
        if st.button("Search MedGUIDE using these findings", key="medguide_report_search", width="stretch"):
            st.session_state.pop("medguide_report_matches", None)
            with st.spinner("Searching the local vector index…"):
                try:
                    matches = find_related_cases(findings_search_query(findings))
                    st.session_state.medguide_report_matches = {"input_identity": input_identity, "matches": matches}
                except Exception as error:
                    _safe_error(error)
        saved = st.session_state.get("medguide_report_matches")
        if saved and saved["input_identity"] == input_identity:
            show_case_matches(saved["matches"])
