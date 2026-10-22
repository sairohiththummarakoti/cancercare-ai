"""Application-level MedGUIDE ingestion and retrieval orchestration."""
from pathlib import Path
import json
import os
import re
import time

from config import ROOT

DATA_DIR = ROOT / "data" / "medguide"
INDEX_DIR = DATA_DIR / "index"
MODEL_CACHE = ROOT / ".cache" / "medguide-models"
MODEL_NAME = os.getenv("MEDGUIDE_EMBEDDING_MODEL", "minishlab/potion-retrieval-32M")
DATASET_URL = "https://huggingface.co/datasets/MedGUIDE/MedGUIDE-MCQA-8K"


def read_pipeline_status(data_dir=DATA_DIR):
    """Read small status files without importing the embedding runtime."""
    result = {"ingested": False, "indexed": False}
    for label, filename in (("ingestion", "ingestion.json"), ("index", "index/index.json"), ("pipeline", "pipeline.json")):
        try:
            value = json.loads((Path(data_dir) / filename).read_text(encoding="utf-8"))
            if isinstance(value, dict):
                result[label] = value
        except (OSError, ValueError):
            pass
    ingestion = result.get("ingestion", {})
    result["ingested"] = (isinstance(ingestion.get("accepted_rows"), int) and ingestion["accepted_rows"] > 0
                          and (Path(data_dir) / "documents.jsonl").is_file())
    pointer = result.get("index", {})
    fingerprint = pointer.get("fingerprint", "")
    expected_file = f"generation-{fingerprint}.npz"
    artifact = Path(data_dir) / "index" / expected_file
    result["indexed"] = (pointer.get("schema") == 1 and isinstance(fingerprint, str)
                         and bool(re.fullmatch(r"[a-f0-9]{64}", fingerprint))
                         and pointer.get("file") == expected_file
                         and bool(re.fullmatch(r"[a-f0-9]{64}", str(pointer.get("sha256", ""))))
                         and artifact.is_file() and not artifact.is_symlink() and artifact.stat().st_size > 0)
    return result


def prepare_medguide(data_dir=DATA_DIR, revision=None, progress=None, model_name=MODEL_NAME):
    """Download once, normalize, chunk, embed, then publish a complete local index."""
    from medguide_ingest import ingest_medguide, load_documents, chunk_documents
    from medguide_vectors import build_medguide_index

    start = time.perf_counter()
    directory = Path(data_dir)
    if progress:
        progress("ingestion", "Downloading and validating the dataset", 0, 0)
    ingestion = ingest_medguide(directory, revision=revision)
    documents = load_documents(directory)
    if progress:
        progress("chunking", "Splitting records with overlap and source metadata", len(documents), len(documents))
    chunks = chunk_documents(documents)
    if progress:
        progress("embedding", "Embedding chunks locally", 0, len(chunks))
    index = build_medguide_index(chunks, directory / "index", model_name=model_name, model_cache_dir=MODEL_CACHE,
                                progress=(lambda done, total: progress("embedding", "Embedding chunks locally", done, total)) if progress else None)
    summary = {"dataset_url": DATASET_URL, "model": model_name, "documents": len(documents), "chunks_before_token_check": len(chunks),
               "ingestion": ingestion, "index": index, "elapsed_seconds": time.perf_counter() - start,
               "source_kind": "educational_mcqa", "clinical_guidelines": False}
    temp = directory / "pipeline.json.tmp"
    temp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    temp.replace(directory / "pipeline.json")
    if progress:
        progress("ready", "Vector index ready", len(chunks), len(chunks))
    return summary


def find_related_cases(query, *, top_k=5, disease=None, min_similarity=0.3, data_dir=DATA_DIR):
    from medguide_vectors import load_medguide_index, search_medguide

    index = load_medguide_index(Path(data_dir) / "index")
    return search_medguide(query, index, top_k=top_k, disease=disease, min_similarity=min_similarity, model_cache_dir=MODEL_CACHE)


def findings_search_query(findings):
    """Use only reported findings. Exclude missing-information checklists from retrieval."""
    from schemas import UNKNOWN
    facts = [getattr(findings, field).value for field in ("cancer_type", "histological_diagnosis", "grade", "stage_tnm")]
    facts += [f"{b.name}: {b.value}" for b in findings.biomarkers if b.value != UNKNOWN]
    return "; ".join(value for value in facts if value != UNKNOWN)
