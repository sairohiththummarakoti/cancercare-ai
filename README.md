# Oncology Care AI

**New: CancerCare AI enterprise-style clinical workspace.** The React + TypeScript + Vite interface and FastAPI backend live in `frontend/` and `backend/`. Start with [EHR_SETUP.md](EHR_SETUP.md), or double-click `start_ehr.bat` after installing the dependencies. The original Streamlit application below remains available separately.

A local Streamlit application for the workflow **Upload → Extract → Retrieve → Draft → Clinician Review**, based on the supplied hackathon requirements. Includes six synthetic pathology PDFs and a repeatable demo that runs without a key or guideline files.

The **MedGUIDE search** mode also provides a complete, real ingestion → chunking → neural embeddings → vector search pipeline over the user-selected MedGUIDE-MCQA-8K research dataset. This uses a local ONNX model and needs no OpenAI key.

**Research demonstration only. Not validated for clinical use. Final treatment decisions require qualified oncology professionals.**

## Try it now

On this computer, double-click `start_app.bat`, then open **http://localhost:8501**. Choose **Sample demo**, select a prepared test case, and click **Analyze & Generate Treatment Assessment**. You can also download a sample and upload that unchanged PDF.

The sample demo reads the PDF, checks its SHA-256 against the included manifest, and replays known findings and authored educational notes. It is explicitly labeled fixture replay: **no LLM, embedding retrieval, or NCCN guidance is claimed**. It accepts only these exact sample PDFs. Edited or arbitrary reports require Live analysis. The shown processing time is measured for the selected mode.

Three cancer profiles produce findings, conditional educational discussions, evidence links and information gaps. The incomplete and benign reports deliberately withhold treatment pathways. The scanned report deliberately produces an OCR error. See `samples/README.md` for the expected results for each file.

## MedGUIDE ingestion and vector search

Choose **MedGUIDE search** in the sidebar to search the built index, filter by the dataset's disease/decision-tree code, adjust top-k and minimum cosine similarity, inspect full scenarios and provenance, and download search results. After a pathology analysis, expand **Find related MedGUIDE research scenarios** to search with the extracted findings. This is real retrieval, separate from the fixed sample-demo output.

The pipeline processes the complete [MedGUIDE-MCQA-8K train split](https://huggingface.co/datasets/MedGUIDE/MedGUIDE-MCQA-8K): **7,747 records** at revision `1460ec478280a7295040b92f7eb985327f77dcbe`.

1. **Ingest:** download immutable-revision Parquet and its dataset card; check the download checksum against Hugging Face metadata, validate schema and answer-letter alignment, and write normalized JSONL records. Incorrect options and raw MCQ instructions remain only in the raw source file and never enter indexed text.
2. **Chunk:** split the clinical vignette, dataset-provided decision path and designated answer into sections of at most 1,200 characters, with 160-character overlap in the case body. Repeat provenance labels and mark partial cases. The complete profile, path and answer remain in metadata for inspection. The current dataset yields **15,642 chunks**. Character limits are additionally checked against the model's actual 512-token limit; oversized text is rejected rather than silently truncated.
3. **Embed:** run the local `minishlab/potion-retrieval-32M` model through FastEmbed/ONNX on CPU, producing **512-dimensional pretrained static semantic embeddings**. This retrieval-tuned Model2Vec model was selected after a local throughput benchmark. Its learned embeddings are not hash vectors or keyword counts; unlike a contextual transformer, it pools learned token representations. The first run downloads model weights; later searches reuse the cached local model.
4. **Search:** L2-normalize vectors and queries, calculate exact NumPy cosine similarity, apply an optional disease filter and similarity cutoff, and return top-k distinct source records. Multiple matching chunks from the same record do not crowd out other records. Scores express retrieval similarity, not clinical confidence.

The vector index records a fingerprint of the source chunks, provenance, model weights/tokenizer and embedding implementation. It is published atomically and validated using checksums. Rebuilding unchanged inputs reuses the index. Query text and query vectors are not saved by retrieval; exporting search results explicitly downloads the query and returned cases.

Run the full pipeline from PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts/medguide_pipeline.py ingest --revision 1460ec478280a7295040b92f7eb985327f77dcbe
.\.venv\Scripts\python.exe scripts/medguide_pipeline.py search "ER positive HER2 negative breast cancer" --top-k 5
.\.venv\Scripts\python.exe scripts/medguide_pipeline.py status
```

Omit `--revision` when intentionally checking for the current remote dataset revision. A pinned, verified ingestion cache is reusable without network access. The app's **Ingest, chunk and build embeddings** control runs the same pipeline. A failed build leaves an existing complete index usable; it does not publish partial vectors.

Set `MEDGUIDE_EMBEDDING_MODEL` or pass `ingest --model BAAI/bge-small-en-v1.5` to use the slower contextual transformer model (384 dimensions) instead. Changing models requires a full rebuild; vectors from different models are never mixed. Retrieval quality remains unvalidated for clinical use. See the default model's [primary model card](https://huggingface.co/minishlab/potion-retrieval-32M) for its design and published evaluation.

Local artifacts are kept in ignored `data/medguide/`: `source.parquet`, `dataset_card.md`, `dataset_metadata.json`, `documents.jsonl`, `ingestion.json`, `pipeline.json`, and `index/index.json` plus a content-addressed vector generation. Model files are under ignored `.cache/medguide-models/`. No downloaded dataset is included in Git.

**Evidence scope and license:** the dataset card describes LLM-generated oncology MCQA derived from NCCN decision trees. It is not the original guideline corpus and does not supply original guideline editions or page citations. The card states **“TBD. Intended for academic and research use.”** An explicit open license is not supplied. The app retains this statement and labels retrieved answers as research scenarios; it does not promote them into guideline-grounded treatment assessments. Verify permissions before redistribution or clinical/commercial use.

## Install on another computer

Use Python 3.12 or newer. From the project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

On macOS/Linux, use `.venv/bin/python` instead. The app binds to `127.0.0.1:8501`, with telemetry disabled. `requirements.lock.txt` records the tested package versions.

## Enable live extraction and real guideline retrieval

Live mode is implemented but **was not exercised against the paid API in this delivery**. The secure local key-save step was declined; no key was created. No authorized NCCN files have been supplied.

1. Configure `OPENAI_API_KEY` securely in the ignored `.env.local` file or process environment. Do not paste a key into chat or commit it. The application reads `.env.local` and `.env` without overriding environment variables. `.env.example` lists the supported settings.
2. Put only guideline files you are authorized to use in `guidelines/`. Confirm your authorization also permits processing their text with the selected API. This application does not download, scrape or redistribute NCCN content.
3. Create `guidelines/manifest.json` using `guidelines/manifest.example.json`. Supply each source's actual title and version/year, plus section and cancer types when available. PDF citations preserve physical page numbers; these may differ from printed page labels. See `guidelines/README.md` for details.
4. Restart Streamlit, select **Live analysis**, and confirm that the report is synthetic or appropriately de-identified and that the API processing is authorized. Analyze a text PDF.

Default configurable models are `gpt-4.1-mini` and `text-embedding-3-small`. Model access, billing, quotas and network access must work for the selected project. The app sends structured-output extraction and assessment/verification requests through the OpenAI Responses API with `store=False`. This parameter is not a promise of zero provider retention; use the API only under your approved data policy.

Actual RAG chunks the authorized local corpus, obtains OpenAI embeddings, normalizes them and uses NumPy cosine similarity to return up to five excerpts. A content-addressed cache under `.cache/guidelines/` contains guideline vectors and source metadata. It does **not** cache report text, patient queries or query vectors. Changing the content, metadata, embedding model or chunk configuration rebuilds the relevant index. Old cache files can be removed when no longer needed.

`RAG_MIN_SIMILARITY` defaults to `0.30`. It is an uncalibrated retrieval threshold, not a clinical confidence score. Citation checks and a separate model support check withhold unsupported pathways; neither provides clinical validation. If the corpus is empty, metadata is missing, or no evidence qualifies, findings are still shown and purported guideline-grounded pathways are withheld.

## Review and data handling

- Findings must carry quotations from the submitted report. Unsupported values become **Not available in report**. The app does not calculate clinical stage from pathology alone.
- Guideline citations must refer to retrieved identifiers and exact quotations. Draft pathways remain conditional and are withheld when citation/support verification fails. No doses, orders, prescriptions or EHR integration are provided.
- **Approve for Documentation**, **Edit** and **Reject** update the current Streamlit session. Editing preserves the original generated draft and resets review to pending. A clinician's edited text is labeled as clinician-authored and has not undergone automated citation checks.
- Reports, extracted findings and review states are held in session memory. Changing the selected input or analysis mode clears the prior result. **Clear session** resets the workspace. Streamlit/browser memory cleanup follows their own lifecycles; there is no durable patient database.
- Downloading the JSON review is an explicit user action that saves data to the browser's download location. Otherwise, the application does not write uploaded report bytes or text to disk.
- This is a single-user local demonstration without authentication. Do not expose it publicly or use it as a clinical system. API failures are shown without disclosing submitted content or raw upstream errors.

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests run without API keys or network calls. They cover PDF validity and scans, evidence-backed extraction and missing stages, real cosine ranking using fake embeddings, cache invalidation/corruption, invalid citations and verification, sample integrity, and the Streamlit review workflow. `pytest.ini` keeps test temporary files inside the project.

To exercise the built MedGUIDE index with the real local embedding model:

```powershell
.\.venv\Scripts\python.exe scripts/verify_medguide.py
```

This checks retrieval for three oncology queries and a disease-filtered query, writing a technical verification report to `.cache/medguide-retrieval-verification.json`. These are smoke checks, not a clinical accuracy evaluation. Disease codes are source labels, not independently verified classifications: for example, dataset rows 2765 and 3324 carry `vulvar_3` while their profiles describe breast cancer. A disease filter restricts those labels but cannot correct inconsistent generated content. Inspect the complete scenario before interpreting a match.

To regenerate the samples:

```powershell
.\.venv\Scripts\python.exe scripts/generate_samples.py
```

The generator updates the PDFs and manifest hashes together. Fixture outputs are a demonstration contract, not a guarantee of live model correctness.

## Project files

| File | Purpose |
|---|---|
| `app.py` | Streamlit upload, results, citations, timing and review |
| `pathology.py` | In-memory PDF parsing and grounded structured extraction |
| `rag.py` | Local-source validation, chunking, embeddings, cache and cosine search |
| `treatment.py` | Conditional drafting, exact citations and support verification |
| `schemas.py` | Pydantic data contracts |
| `demo.py` | Clearly labeled, hash-locked sample replay |
| `review.py` | Session-only review changes and explicit JSON export |
| `medguide_ingest.py` | Pinned dataset download, record validation and overlapping chunks |
| `medguide_vectors.py` | Local ONNX embeddings, atomic vector index and cosine search |
| `medguide.py` / `medguide_ui.py` | Pipeline orchestration and the dataset search workspace |
| `scripts/medguide_pipeline.py` | Ingestion, status and search CLI |
| `samples/` | Six synthetic PDFs, hashes and expected results |
| `guidelines/` | Setup instructions; no NCCN content included |
| `tests/` | Automated offline checks |

## Sources and limits

Demo educational notes are short paraphrases based on the National Cancer Institute's [Tests for Breast Cancer Biomarkers](https://www.cancer.gov/types/breast/diagnosis/breast-cancer-biomarker-tests), posted December 2, 2025 and checked October 21, 2026. They are not NCCN excerpts and do not establish individual treatment eligibility.

API implementation follows OpenAI's [structured outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs) and [embedding documentation](https://developers.openai.com/api/docs/guides/embeddings). These API contracts were checked during implementation; live credentials and licensed source validation remain necessary before claiming a complete live demonstration.

OCR, clinical validation, authentication, cloud deployment, databases, EHR access, signatures and treatment ordering are outside the MVP scope.
