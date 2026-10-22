# Synthetic pathology reports

These six one-page PDFs contain **SYNTHETIC TEST DATA** only. All accession numbers and specimen findings are invented. No real patient, clinician, or hospital is represented. The reports contain no treatment recommendations and are not clinical records.

| File | Test case | Expected result |
| --- | --- | --- |
| `01_breast_er_positive_her2_negative.pdf` | Invasive breast carcinoma, ER 95%, PR 70%, HER2 IHC 1+, Ki-67 18% | Extract the reported findings. Keep clinical stage unknown. |
| `02_breast_her2_positive.pdf` | Invasive breast carcinoma, ER/PR negative, HER2 IHC 3+, Ki-67 45% | Identify the HER2 result without inferring eligibility or stage. |
| `03_breast_triple_negative.pdf` | Invasive breast carcinoma, ER/PR negative, HER2 IHC 0, Ki-67 75% | Preserve unknown stage, PD-L1, and germline status. |
| `04_breast_incomplete_information.pdf` | Invasive carcinoma with pending receptors and omitted grade, size, and stage | Display `Not available in report` for missing values and list missing information. |
| `05_breast_benign_no_malignancy.pdf` | Fibroadenoma with no malignancy identified in the submitted tissue | Report the benign findings and suppress cancer treatment pathways. Do not generalize beyond the sampled tissue. |
| `06_scanned_image_only.pdf` | Image-only version of the first report | Reject with a readable error explaining that a text-based PDF is required. |

The first three reports state the measured invasive focus **within a core biopsy**. This is not the overall tumor size and must not be used to invent a clinical stage.

The first five PDFs guarantee an extractable text fixture, not guaranteed medical conclusions or guaranteed API availability. The sixth intentionally has no extractable text. A successful result can be a safe limitation message: without authorized guideline files and adequate metadata, the app must not produce a purported NCCN-grounded treatment assessment.

`manifest.json` contains a list of cases, SHA-256 checksums, expected behavior, and field-level expected findings with verbatim supporting quotations. Unknown values use `Not available in report` and an empty quotation. The scanned fixture has `findings: null`. Checksums identify exact bundled files; edits or regeneration change the checksum.

Regenerate the files from the project root with:

```powershell
python scripts/generate_samples.py
```

Authoring requires `reportlab`, `pypdfium2`, and `Pillow`. No API or network request is made by the generator. These authoring dependencies are separate from normal application use.
