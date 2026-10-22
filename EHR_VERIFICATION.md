# CancerCare AI verification

Verified locally on October 21, 2026, using synthetic records only. No paid model calls were made.

## Automated checks

- Python suite: **132 passed**, including pipeline, MedGUIDE, API, patient ownership, PDF validation, source authorization, review permissions and durable revision history. One non-failing Starlette/httpx deprecation warning remains.
- React component suite: **7 passed**. Covers patient switching, delayed responses, stale document uploads, navigator restrictions, missing evidence, upload consent/error handling, and saved conflict/edit provenance.
- TypeScript checking and Vite production build: passed. Rollup reports two non-failing annotation warnings in the Zod dependency.
- Actual HTTP verification: **12 checks passed** against the running FastAPI service. Results are saved in `.cache/ehr/http-verification.json`.

## Browser interactions

Verified in Chrome against the running React application and FastAPI service:

- All three quick patient tabs and the patient selector show distinct synthetic charts; patient-specific findings and assessment state change together.
- Overview, clinical history, pathology, treatment journey, medications and AI Assessment activities render their corresponding content.
- Analyze a chart pathology document: actual PDF upload and extraction produce quoted report findings, preserve unknown staging and leave existing chart values unchanged.
- Prepare a local factual draft: real extracted findings populate the assessment; evidence and pathway lists remain empty when authorized guidelines are unavailable.
- Edit and approve: the saved clinician revision, approval status and audit snapshots are visible. Original generated text remains available.
- Navigator role: approval, editing and rejection controls are disabled; the server independently rejects unauthorized review requests.
- Reject: rationale and rejected state persist across patient navigation.
- Source PDF viewer opens the synthetic report; summary export initiates an explicit download.
- The classic layout was visually checked at desktop, tablet and mobile widths. Narrow chart tabs scroll horizontally within their own navigation strip. The Copilot moves below the chart on smaller screens.

The responsive check page is an ignored local QA harness, not part of the production build. It embeds the actual React app at controlled widths. Desktop screenshot: `.cache/ehr/classic-workspace.png`.

## Test materials and limits

Nine synthetic PDF fixtures are in `samples/ehr/`, with expected behavior documented alongside them. Normal reports cover breast, lung and colon cases; additional reports cover contradictions, missing findings and scanned input. The PDF fixture contact sheet was visually inspected during generation.

The OpenAI-backed generation path is implemented but has not been exercised with a live credential in this delivery. No authorized clinical guideline corpus was supplied. MedGUIDE retrieval uses a real local research index; those generated MCQA scenarios are never presented as authoritative clinical guideline evidence. These checks do not establish clinical correctness, regulatory readiness or production security. No treatment orders are generated.

## Reproduce

See `EHR_SETUP.md` for installation and startup. Run the following from the project root while the API is running:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/verify_ehr.py
cd frontend
npm test
npm run build
```

The HTTP verification intentionally creates synthetic review records in the local demo store.
