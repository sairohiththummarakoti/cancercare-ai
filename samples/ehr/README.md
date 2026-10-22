# Synthetic EHR test pack

Every identity, clinical detail and document in this directory is fictional. These reports exercise software behavior; they do not establish treatment eligibility or medical accuracy. The chart snapshot is October 21, 2026. No guideline content is included.

| File | Open this patient | Expected behavior |
|---|---|---|
| `breast-pathology.pdf` | Ava Mitchell / DEMO-00248 | Extract breast pathology and ER/PR/HER2/Ki-67 values. Preserve missing clinical stage and definitive pathologic size. |
| `lung-pathology.pdf` | Noah Reynolds / DEMO-00352 | Extract pulmonary adenocarcinoma. Preserve pending molecular tests and unknown grade/stage/size. |
| `colon-pathology.pdf` | Maya Ellis / DEMO-00419 | Extract colonic adenocarcinoma. Keep MMR/MSI pending and KRAS/BRAF not ordered. |
| `breast-imaging.pdf` | Ava Mitchell | Show 2.1 cm as an imaging observation, not definitive pathology size. |
| `lung-imaging.pdf` | Noah Reynolds | Show 3.4 cm as a CT observation, not definitive pathology size. |
| `colon-endoscopy.pdf` | Maya Ellis | View the supporting colonoscopy summary without inventing stage. |
| `breast-contradiction.pdf` | Ava Mitchell | Flag deliberately discordant ER and HER2 findings for clinician reconciliation. |
| `missing-findings.pdf` | Ava Mitchell | Preserve absent facts; do not infer a malignancy or negative biomarkers. |
| `scanned-report.pdf` | Ava Mitchell | Return the explicit OCR/text-based-PDF error. |

For a patient-isolation test, select Noah Reynolds and upload `breast-pathology.pdf`: the ID and cancer-type mismatch must be surfaced. Never silently transfer chart context or a prior patient's draft.

Without authorized guideline sources, every case must report that guideline evidence is unavailable and return no guideline-based pathway. A successful PDF parse is not a claim of successful LLM analysis or RAG.

The application serves the six chart documents through patient-scoped endpoints. The additional three edge cases are available here and in `synthetic-ehr-test-pack.zip`. `manifest.json` contains hashes and expected behavior. Regenerate from the project root using:

```powershell
.\.venv\Scripts\python.exe backend/fixtures_data/generate.py
```

FHIR-shaped bundles under `backend/fixtures_data/` use R4 collection/resource structures. They are not certified profiles, a FHIR server, or a live EHR connection. Medication/vital information is intentionally absent; no drug values or orders are invented. Reference structures: [FHIR R4 Bundle](https://hl7.org/fhir/R4/bundle.html) and [FHIR R4 Observation](https://hl7.org/fhir/R4/observation.html).
