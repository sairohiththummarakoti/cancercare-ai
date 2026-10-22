# CancerCare AI — local clinical workspace

The application uses React, TypeScript, Vite, Tailwind CSS and reusable shadcn/ui components. Following the requested redesign, the interface uses a classic desktop EHR layout: blue-gray application chrome, quick patient tabs, a persistent patient storyboard, compact chart activities, flat clinical panels and a docked AI Copilot. It retains CancerCare AI branding; it is an independent interface, not Epic software or an Epic integration. A Python FastAPI service supplies three synthetic patient charts, real PDF text extraction, explicit findings and evidence states, and a documentation review workflow. It is a local research demonstration, not a clinically validated system.

## Start on this computer

Double-click `start_ehr.bat` in the project folder. It starts the API and frontend, opens **http://127.0.0.1:5173**, and keeps a launcher console open. Press **Ctrl+C** in that console to stop both services. If they are already running, the launcher opens the existing workspace. It does not stop other applications using the same ports.

The original Streamlit app remains available through `start_app.bat` on port 8501.

Use the **Classic / Modern** control in the header to compare layouts. The modern option is directly accessible at **http://127.0.0.1:5173/?layout=modern**; the default remains classic. Appearance changes preserve the active chart, upload and assessment. Both layouts use the same backend and evidence rules.

## Install from a fresh checkout

Use Python 3.12 and Node.js 22.12+ or 24 LTS. From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe scripts/run_ehr.py
```

On macOS/Linux, replace `.venv\Scripts\python.exe` with `.venv/bin/python`. The Python launcher works on both platforms. `requirements.lock.txt` records the tested Python environment; `frontend/package-lock.json` pins the frontend dependencies.

For development, start these in separate terminals:

```powershell
# Terminal 1, project root
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log

# Terminal 2, project root
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Vite proxies `/api` to the local FastAPI service. API documentation is at **http://127.0.0.1:8000/docs**. Keep both services on loopback; this demonstration does not provide production authentication or deployment controls.

## What works without an API key

All patient chart views, document viewing, real text-PDF parsing, conservative rule-based field extraction, missing-information checks, chart/report comparison, and draft documentation review run locally. The interface labels this processing mode. Local factual summaries are assembled from extracted findings; they are not LLM-generated treatment assessments or replayed guideline results.

The three charts are fictional: Ava Mitchell (breast), Noah Reynolds (lung), and Maya Ellis (colon). Each has FHIR R4-shaped resources and matching PDF documents. FHIR-shaped means a local data model inspired by those resources, not conformance certification or a connection to a FHIR server. PDFs under `samples/ehr/` are explicitly marked synthetic. Existing PDFs under `samples/` also remain available for the earlier Streamlit demonstration.

For a quick test, open Ava Mitchell, select **Analyze** beside her pathology document, then **Prepare draft assessment**. Alternatively, use **Upload pathology PDF** with `samples/ehr/breast-pathology.pdf` and confirm that the data are synthetic. Review the quoted findings, then use **Edit**, **Approve**, or **Reject** in the Copilot. The matching lung and colon reports exercise their respective patient charts. `breast-contradiction.pdf` tests reconciliation, `missing-findings.pdf` tests incomplete findings, and `scanned-report.pdf` tests the explicit OCR limitation. All nine PDFs are also bundled in `samples/ehr/synthetic-ehr-test-pack.zip`. Expected outcomes are described in `samples/ehr/README.md`; these examples verify software behavior, not clinical accuracy.

No authorized guideline corpus or working OpenAI credential was supplied. The initial workspace therefore shows **Guideline evidence unavailable**, returns empty evidence/pathway lists, and permits review of factual documentation only. Approval is not a prescription, treatment authorization, or order.

## Enable authorized guideline generation later

1. Configure `OPENAI_API_KEY` using secure local setup in ignored `.env.local`, or the process environment. Never paste it into chat or place it in frontend variables. Existing model settings are in `.env.example`.
2. Add only sources you are authorized to use to `guidelines/` and complete `guidelines/manifest.json`. Read [the source setup instructions](guidelines/README.md), including exact publisher/version metadata and the three explicit permission/version attestations required by FastAPI.
3. Restart the API. Confirm knowledge-source readiness in the app, then choose the live processing option and explicitly authorize provider processing of the synthetic report and authorized excerpts.

The existing RAG modules perform chunking, OpenAI embeddings, cosine retrieval, structured draft generation, exact citation checks, and a separate model support check. Only citations to retrieved, versioned source excerpts qualify. Generation failures or insufficient evidence do not fall back to simulated treatment guidance. The paid provider path requires billing/model access and has not been live-tested in this delivery.

MedGUIDE remains available through the existing local pipeline and Streamlit research search. Its generated MCQA scenarios are not substituted for clinical guideline evidence. See the main README for its ingestion commands and provenance limitations.

## Clinical review and data handling

The local demo provides oncologist and navigator roles. A server-issued demo session enforces review permissions; choosing a demo role is not credential verification. Production use would require real identity, authorization, audit governance and clinical validation.

Uploaded PDFs and extracted report text are temporary. Synthetic assessment/review history is stored in the local demo store under `.cache/ehr/`. Do not upload real patient information. Switching patients resets active upload and review UI state; the backend also verifies patient ownership. Editing preserves the original draft and requires renewed review. Exports are explicit downloads of synthetic documentation.

Each chart restores its latest saved assessment. The AI Assessment view retains source warnings, report/chart contradictions, extraction quotations and review revisions after refresh. Editing preserves both the original generated text and prior documentation revisions; clinician-authored text is explicitly labeled as not automatically validated. The application removes known synthetic patient identifiers from exports, but arbitrary free text still needs review before sharing.

Text-based PDFs only: maximum 10 MB and 50 pages. Image-only/scanned, encrypted or malformed PDFs produce a clear error. OCR is not included. Rule-based extraction recognizes explicit labels and common report expressions; it is intentionally conservative and can miss information. Unknown findings remain unknown, stage is never inferred from tumor size, and extracted facts do not overwrite the chart automatically.

## Verification

```powershell
# Python pipeline and API checks
.\.venv\Scripts\python.exe -m pytest -q

# Frontend type checking, production compilation and component tests
cd frontend
npm run build
npm test -- --run
```

See `EHR_VERIFICATION.md` for the final tested interactions and known limits. Startup logs are in `.cache/ehr/api.log` and `.cache/ehr/frontend.log`. If startup fails, check that ports 8000 and 5173 are free and the dependencies are installed. A stopped or failed API is reported in the UI; the frontend does not silently replace it with mock patient or guideline responses.
