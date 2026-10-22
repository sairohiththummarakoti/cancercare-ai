"""Pinned ingestion of MedGUIDE educational MCQA records, never clinical guidelines.

The retrievable text deliberately excludes distractor options and the raw MCQ
prompt. Dataset answer labels are preserved as labels, not clinical validation.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable

import requests

DATASET_ID = "MedGUIDE/MedGUIDE-MCQA-8K"
DATASET_URL = f"https://huggingface.co/datasets/{DATASET_ID}"
PARQUET_FILE = "data/train-00000-of-00001.parquet"
SCHEMA_VERSION = 1
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
MAX_DOCUMENTS_BYTES = 100 * 1024 * 1024
MAX_ROWS = 50_000


class MedguideIngestionError(ValueError):
    """Actionable ingestion errors without arbitrary upstream response content."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _revision(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise MedguideIngestionError("Use a full 40-character Hugging Face dataset commit revision.")
    return value.lower()


def _safe_directory(directory: Path | str) -> Path:
    directory = Path(directory)
    if directory.is_symlink():
        raise MedguideIngestionError("The dataset directory must be a regular local directory.")
    return directory


def _file(directory: Path, name: str) -> Path:
    path = directory / name
    if path.is_symlink():
        raise MedguideIngestionError("Dataset cache files must not be symlinks.")
    return path


def _atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".ingest-", suffix=".tmp", delete=False) as target:
            temporary = Path(target.name)
            target.write(data)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _fetch(url: str, limit: int, *, params=None) -> bytes:
    response = None
    try:
        response = requests.get(url, params=params, timeout=(15, 90), stream=True)
        response.raise_for_status()
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > limit:
            raise MedguideIngestionError("The dataset download exceeds the supported size limit.")
        data = bytearray()
        for block in response.iter_content(chunk_size=64 * 1024):
            data.extend(block)
            if len(data) > limit:
                raise MedguideIngestionError("The dataset download exceeds the supported size limit.")
        if not data:
            raise MedguideIngestionError("Hugging Face returned an empty dataset file.")
        return bytes(data)
    except MedguideIngestionError:
        raise
    except Exception:
        raise MedguideIngestionError("Could not download MedGUIDE. Check internet access to Hugging Face and retry.") from None
    finally:
        if response is not None:
            response.close()


def _json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _text(value, *, maximum=50_000) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid_text")
    value = " ".join(value.split())
    if not value or len(value) > maximum:
        raise ValueError("invalid_text")
    return value


def normalize_record(row: dict, row_index: int, revision: str) -> dict:
    """Check label/answer consistency before dropping all incorrect options."""
    if not isinstance(row, dict):
        raise ValueError("invalid_record")
    profile = _text(row.get("profile"))
    if len(profile) < 20:
        raise ValueError("short_profile")
    disease = _text(row.get("disease"), maximum=120)
    answer_text = _text(row.get("answer_text"), maximum=20_000)
    options = row.get("options")
    label = row.get("answer")
    if not isinstance(options, list) or not 2 <= len(options) <= 26:
        raise ValueError("invalid_options")
    if not isinstance(label, str) or not re.fullmatch(r"[A-Z]", label.strip()):
        raise ValueError("invalid_answer_label")
    option_index = ord(label.strip()) - ord("A")
    if option_index >= len(options) or _text(options[option_index]) != answer_text:
        raise ValueError("answer_mismatch")
    if row.get("option_count") != len(options):
        raise ValueError("option_count_mismatch")
    path = row.get("path")
    if not isinstance(path, list) or not path or len(path) > 200:
        raise ValueError("invalid_path")
    path = [_text(part, maximum=20_000) for part in path]
    if len(profile) + len(answer_text) + sum(map(len, path)) > 150_000:
        raise ValueError("record_too_long")
    generation_model = _text(row.get("generation_model"), maximum=150)
    return {
        "id": f"medguide:{revision}:train:{row_index}",
        "row_index": row_index,
        "disease": disease,
        "profile": profile,
        "answer_text": answer_text,
        "path": path,
        "generation_model": generation_model,
        "dataset_id": DATASET_ID,
        "revision": revision,
        "split": "train",
        "source_url": f"{DATASET_URL}/blob/{revision}/{PARQUET_FILE}",
        "source_kind": "educational_mcqa",
        "guideline_version": None,
    }


def _read_summary(directory: Path) -> dict:
    summary_path = _file(directory, "ingestion.json")
    try:
        if summary_path.stat().st_size > 2_000_000:
            raise ValueError
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if (summary.get("schema_version") != SCHEMA_VERSION or summary.get("dataset_id") != DATASET_ID
                or summary.get("source_kind") != "educational_mcqa"):
            raise ValueError
        _revision(summary.get("revision"))
        if not isinstance(summary.get("accepted_rows"), int) or not 1 <= summary["accepted_rows"] <= MAX_ROWS:
            raise ValueError
        return summary
    except (OSError, ValueError, TypeError, AttributeError):
        raise MedguideIngestionError("No valid MedGUIDE ingestion is available. Run ingestion before indexing.") from None


def _checked_bytes(directory: Path, name: str, digest: str, limit: int) -> bytes:
    try:
        path = _file(directory, name)
        if path.stat().st_size > limit or not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            raise ValueError
        data = path.read_bytes()
        if _sha256(data) != digest:
            raise ValueError
        return data
    except (OSError, ValueError, TypeError):
        raise MedguideIngestionError("The MedGUIDE cache is incomplete or changed. Run ingestion again to rebuild it.") from None


def load_documents(data_dir: Path | str) -> list[dict]:
    """Load only checksum-verified, normalized records, without making a request."""
    directory = _safe_directory(data_dir)
    summary = _read_summary(directory)
    raw = _checked_bytes(directory, "documents.jsonl", summary.get("documents_sha256"), MAX_DOCUMENTS_BYTES)
    try:
        documents = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        if len(documents) != summary["accepted_rows"]:
            raise ValueError
        seen = set()
        for document in documents:
            if (not isinstance(document, dict) or document.get("dataset_id") != DATASET_ID
                    or document.get("revision") != summary["revision"]
                    or document.get("source_kind") != "educational_mcqa"
                    or document.get("guideline_version") is not None
                    or document.get("split") != "train"
                    or not isinstance(document.get("row_index"), int)
                    or document["row_index"] < 0
                    or document.get("id") != f"medguide:{summary['revision']}:train:{document['row_index']}"):
                raise ValueError
            if document["id"] in seen:
                raise ValueError
            seen.add(document["id"])
            for field in ("profile", "answer_text", "disease", "generation_model", "source_url"):
                _text(document.get(field))
            if not isinstance(document.get("path"), list) or not document["path"]:
                raise ValueError
            for part in document["path"]:
                _text(part)
            if any(key in document for key in ("options", "prompt", "answer")):
                raise ValueError
        return documents
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise MedguideIngestionError("The normalized MedGUIDE records are invalid. Run ingestion again.") from None


def _cached(directory: Path, revision: str) -> dict | None:
    try:
        summary = _read_summary(directory)
        if summary["revision"] != revision:
            return None
        load_documents(directory)
        for name, field, limit in (("source.parquet", "raw_sha256", MAX_DOWNLOAD_BYTES),
                                   ("dataset_metadata.json", "metadata_sha256", 2_000_000),
                                   ("dataset_card.md", "card_sha256", 2_000_000)):
            _checked_bytes(directory, name, summary.get(field), limit)
        return dict(summary, cache_hit=True)
    except MedguideIngestionError:
        return None


def ingest_medguide(data_dir: Path | str, revision: str | None = None,
                   progress: Callable[[str], None] | None = None) -> dict:
    """Download one immutable dataset revision and normalize all valid train rows.

    An explicitly pinned, complete cache is reused without network access.
    A request without a revision resolves current metadata before cache reuse.
    """
    directory = _safe_directory(data_dir)
    notify = progress or (lambda message: None)
    if revision is not None:
        revision = _revision(revision)
        cached = _cached(directory, revision)
        if cached is not None:
            notify("Using the verified, pinned MedGUIDE ingestion cache.")
            return cached
    notify("Resolving the MedGUIDE dataset revision…")
    api_url = f"https://huggingface.co/api/datasets/{DATASET_ID}"
    if revision is not None:
        api_url += f"/revision/{revision}"
    metadata_bytes = _fetch(api_url, 2_000_000, params={"blobs": "true"})
    try:
        metadata = json.loads(metadata_bytes)
        resolved = _revision(metadata["sha"])
        if metadata.get("id") != DATASET_ID or metadata.get("private") or metadata.get("gated"):
            raise ValueError
        if revision is not None and resolved != revision:
            raise ValueError
        files = {item["rfilename"]: item for item in metadata["siblings"]}
        if PARQUET_FILE not in files or "README.md" not in files:
            raise ValueError
    except (ValueError, KeyError, TypeError):
        raise MedguideIngestionError("The dataset metadata is incompatible or access-restricted. No records were ingested.") from None
    revision = resolved
    cached = _cached(directory, revision)
    if cached is not None:
        notify("Using the verified MedGUIDE ingestion cache for the current revision.")
        return cached
    notify("Downloading the dataset card and pinned Parquet data…")
    card_bytes = _fetch(f"{DATASET_URL}/resolve/{revision}/README.md", 2_000_000)
    parquet_bytes = _fetch(f"{DATASET_URL}/resolve/{revision}/{PARQUET_FILE}", MAX_DOWNLOAD_BYTES)
    source_sha = _sha256(parquet_bytes)
    lfs = files[PARQUET_FILE].get("lfs") or {}
    expected_sha = lfs.get("sha256") or lfs.get("oid")
    if expected_sha and source_sha != str(expected_sha).removeprefix("sha256:"):
        raise MedguideIngestionError("The dataset checksum did not match its pinned Hugging Face metadata. Download again.")
    notify("Validating answer labels and normalizing educational cases…")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pq.read_table(pa.BufferReader(parquet_bytes))
        if not 1 <= table.num_rows <= MAX_ROWS:
            raise ValueError
        rows = table.to_pylist()
    except Exception:
        raise MedguideIngestionError("The downloaded Parquet dataset could not be read or exceeds the supported row limit.") from None
    documents = []
    rejected = Counter()
    for row_index, row in enumerate(rows):
        try:
            documents.append(normalize_record(row, row_index, revision))
        except ValueError as error:
            rejected[str(error)] += 1
    if not documents:
        raise MedguideIngestionError("No valid MedGUIDE cases remained after answer and schema checks.")
    document_bytes = ("\n".join(json.dumps(document, ensure_ascii=False, sort_keys=True) for document in documents) + "\n").encode("utf-8")
    if len(document_bytes) > MAX_DOCUMENTS_BYTES:
        raise MedguideIngestionError("The normalized dataset exceeds the supported size limit.")
    card = card_bytes.decode("utf-8", errors="replace")
    license_id = (metadata.get("cardData") or {}).get("license")
    license_statement = "TBD. Intended for academic and research use." if re.search(r"TBD\.\s*Intended for academic and research use\.", card) else "No explicit license identifier found in dataset metadata."
    summary = {
        "schema_version": SCHEMA_VERSION, "dataset_id": DATASET_ID, "dataset_url": DATASET_URL,
        "revision": revision, "split": "train", "source_file": PARQUET_FILE,
        "source_kind": "educational_mcqa", "guideline_version": None,
        "total_rows": len(rows), "accepted_rows": len(documents), "rejected_rows": sum(rejected.values()),
        "rejection_reasons": dict(rejected), "disease_counts": dict(sorted(Counter(d["disease"] for d in documents).items())),
        "raw_sha256": source_sha, "documents_sha256": _sha256(document_bytes),
        "metadata_sha256": _sha256(metadata_bytes), "card_sha256": _sha256(card_bytes),
        "license_identifier": license_id, "license_status": "declared" if license_id else "not_specified",
        "license_statement": license_statement,
        "limitations": ["Educational multiple-choice cases; not primary clinical guideline evidence.",
                        "Dataset-provided answers are not clinically validated by this ingestion.",
                        "Disease code suffixes identify dataset decision trees, not guideline versions.",
                        "The dataset card's license is unresolved; verify permissions before redistribution or clinical/commercial use."],
        "cache_hit": False,
    }
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for name, data in (("dataset_metadata.json", metadata_bytes), ("dataset_card.md", card_bytes),
                           ("source.parquet", parquet_bytes), ("documents.jsonl", document_bytes)):
            _atomic_write(_file(directory, name), data)
        _atomic_write(_file(directory, "ingestion.json"), _json_bytes(summary))
    except OSError:
        raise MedguideIngestionError("The MedGUIDE dataset cache could not be saved. Check the destination folder's permissions and disk space.") from None
    notify(f"Ingested {len(documents):,} educational cases; rejected {sum(rejected.values()):,} invalid records.")
    return summary


def _segments(text: str, budget: int, overlap: int) -> list[tuple[int, int, str]]:
    segments = []
    start = 0
    while start < len(text):
        stop = min(start + budget, len(text))
        if stop < len(text):
            boundary = text.rfind("\n", start + budget // 2, stop)
            if boundary < 0:
                boundary = text.rfind(" ", start + budget // 2, stop)
            if boundary > start:
                stop = boundary
        segments.append((start, stop, text[start:stop]))
        if stop == len(text):
            break
        start = max(start + 1, stop - overlap)
    return segments


def chunk_documents(documents: list[dict], max_chars: int = 1200, overlap: int = 160) -> list[dict]:
    """Split case records with overlap and explicit, repeated educational context.

    Full case profiles and answers remain in metadata for inspection of every hit.
    A multi-part hit explicitly says the context is incomplete, avoiding a bare
    answer being mistaken for a standalone clinical recommendation.
    """
    if not isinstance(max_chars, int) or not 500 <= max_chars <= 20_000:
        raise MedguideIngestionError("Chunk size must be between 500 and 20,000 characters.")
    if not isinstance(overlap, int) or not 0 <= overlap < max_chars // 3:
        raise MedguideIngestionError("Chunk overlap must be nonnegative and less than one third of the chunk size.")
    chunks = []
    seen = set()
    for document in documents:
        if (document.get("source_kind") != "educational_mcqa" or document.get("dataset_id") != DATASET_ID
                or document.get("guideline_version") is not None or document.get("id") in seen):
            raise MedguideIngestionError("Only unique, normalized MedGUIDE educational records can be chunked.")
        seen.add(document["id"])
        disease = _text(document["disease"], maximum=120)
        body = (f"Case context:\n{document['profile']}\n\nDataset-provided reasoning path:\n"
                + "\n".join(f"- {part}" for part in document["path"])
                + f"\n\nDataset-labelled correct answer for this complete case:\n{document['answer_text']}")
        header = f"Educational MCQA example; not a clinical guideline. Disease label: {disease}.\n"
        multi_note = "Case segment; incomplete context. Read the full case before interpreting the dataset answer.\n"
        if len(header) + len(body) <= max_chars:
            segments = [(0, len(body), body)]
            prefix = header
        else:
            prefix = header + multi_note
            budget = max_chars - len(prefix)
            if budget <= overlap:
                raise MedguideIngestionError("The chunk size is too small for this record's provenance header.")
            segments = _segments(body, budget, overlap)
        for number, (start, stop, part) in enumerate(segments, 1):
            identifier = _sha256(f"{document['id']}|{max_chars}|{overlap}|{start}|{part}".encode())[:24]
            chunks.append({
                "id": f"MG-{identifier}", "record_id": document["id"],
                "title": f"MedGUIDE educational case — {disease}",
                "version": f"Dataset revision {document['revision']}",
                "location": f"train row {document['row_index']} (zero-based); chunk {number} of {len(segments)}",
                "source_file": PARQUET_FILE, "text": prefix + part, "disease": disease,
                "dataset_id": DATASET_ID, "revision": document["revision"], "split": "train",
                "row_index": document["row_index"], "source_url": document["source_url"],
                "source_kind": "educational_mcqa", "guideline_version": None,
                "answer_text": document["answer_text"], "profile": document["profile"],
                "path": list(document["path"]), "generation_model": document["generation_model"],
                "chunk_index": number, "chunk_count": len(segments), "char_start": start, "char_end": stop,
            })
    return chunks
