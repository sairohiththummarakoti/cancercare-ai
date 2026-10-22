"""Exercise the saved production index with real local embeddings (no API)."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from medguide import DATA_DIR, MODEL_CACHE
from medguide_vectors import load_medguide_index, search_medguide


def main():
    start = time.perf_counter()
    index = load_medguide_index(DATA_DIR / "index")
    cases = [
        ("ER positive HER2 negative invasive breast carcinoma", "bre_"),
        ("HER2 positive metastatic breast cancer", "bre_"),
        ("Acute promyelocytic leukemia relapse after arsenic trioxide and ATRA", "aml_"),
    ]
    checks = []
    for query, prefix in cases:
        began = time.perf_counter()
        hits = search_medguide(query, index, model_cache_dir=MODEL_CACHE)
        rows = [hit["row_index"] for hit in hits]
        passed = bool(hits) and hits[0]["disease"].startswith(prefix) and len(rows) == len(set(rows))
        checks.append({"query":query,"expected_family":prefix,"passed":passed,"seconds":time.perf_counter()-began,
                       "hits":[{"row":h["row_index"],"disease":h["disease"],"score":round(h["score"],4)} for h in hits]})
    filtered = search_medguide(cases[0][0], index, disease="bre_1", top_k=3, model_cache_dir=MODEL_CACHE)
    checks.append({"query": cases[0][0], "disease_filter": "bre_1",
                   "passed": len(filtered) == 3 and all(h["disease"] == "bre_1" for h in filtered),
                   "hits": [{"row": h["row_index"], "disease": h["disease"], "score": round(h["score"], 4)} for h in filtered]})
    report = {"model":index.metadata["model_name"],"dimensions":index.metadata["dimensions"],
              "documents":index.metadata["document_count"],"chunks":index.metadata["chunk_count"],
              "fingerprint":index.metadata["fingerprint"],"checks":checks,"seconds":time.perf_counter()-start,
              "scope":"Technical retrieval smoke checks only; not medical correctness or clinical validation."}
    target = Path(__file__).resolve().parents[1] / ".cache" / "medguide-retrieval-verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(item["passed"] for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
