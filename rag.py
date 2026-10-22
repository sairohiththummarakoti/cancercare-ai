"""Local, manifest-controlled guideline retrieval with real OpenAI embeddings.

Only guideline text/vectors are cached. Report text, queries, and query vectors
are never written to disk. Retrieved text is evidence data, never instructions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import zipfile

import numpy as np


CHUNK_SIZE = 1600
CHUNK_OVERLAP = 200
EMBED_BATCH_SIZE = 64
CACHE_SCHEMA = 1
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_CORPUS_CHUNKS = 10000


class RagError(ValueError):
    """An actionable error that contains no patient data or provider payload."""


@dataclass
class GuidelineIndex:
    chunks: list[dict[str, Any]] = field(default_factory=list)
    vectors: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=np.float32))
    model: str = ""
    fingerprint: str = ""
    warnings: list[str] = field(default_factory=list)
    cache_hit: bool = False


def _non_placeholder(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        return False
    normalized = value.strip().lower()
    return normalized not in {"unknown", "n/a", "none", "not available", "not available in report"} and not any(
        marker in normalized for marker in ("replace with", "your title", "your version", "<", ">")
    )


def _source_path(directory: Path, filename: Any) -> Path:
    if not isinstance(filename, str) or not filename.strip():
        raise RagError("The manifest entry has no source filename.")
    relative = Path(filename)
    if relative.is_absolute() or relative.drive or ".." in relative.parts or relative.suffix.lower() not in {".pdf", ".txt", ".md"}:
        raise RagError("Use a relative PDF, TXT, or Markdown filename inside guidelines/.")
    root = directory.resolve()
    candidate = root / relative
    # Reject both file symlinks and symlinked intermediate directories.
    for part in [candidate, *candidate.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise RagError("Symlinked guideline files and folders are not supported.")
    try:
        candidate.resolve().relative_to(root)
    except ValueError:
        raise RagError("The source path must stay inside guidelines/.") from None
    if not candidate.is_file():
        raise RagError("The listed source file does not exist.")
    if candidate.stat().st_size > MAX_FILE_BYTES:
        raise RagError("A guideline file exceeds the 25 MB limit.")
    return candidate


def _read_pages(path: Path) -> tuple[bytes, list[tuple[str, str]]]:
    """Return original bytes and (location, text) pages; no OCR or truncation."""
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise RagError("A guideline file exceeds the 25 MB limit.")
    if path.suffix.lower() == ".pdf":
        try:
            import pymupdf

            with pymupdf.open(stream=raw, filetype="pdf") as pdf:
                if pdf.needs_pass:
                    raise RagError("The guideline PDF is password-protected.")
                if len(pdf) > 800:
                    raise RagError("The guideline PDF exceeds the 800-page limit.")
                pages = [(f"PDF page {number + 1}", page.get_text("text").strip()) for number, page in enumerate(pdf)]
        except RagError:
            raise
        except Exception:
            raise RagError("The guideline PDF could not be read. Use a valid text-based PDF.") from None
    else:
        try:
            pages = [("", raw.decode("utf-8-sig").strip())]
        except UnicodeDecodeError:
            raise RagError("Text guideline files must use UTF-8 encoding.") from None
    usable = [(location, text) for location, text in pages if len(text.strip()) >= 20]
    if not usable:
        raise RagError("The guideline has no usable text. Image-only PDFs need OCR outside this app.")
    if sum(len(text) for _, text in usable) > 2_000_000:
        raise RagError("The guideline exceeds the two-million-character limit.")
    return raw, usable


def _load_documents(directory: Path) -> tuple[list[dict[str, Any]], list[str]]:
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        return [], ["No guideline manifest.json found. Add authorized local sources with a title and version; no NCCN-grounded assessment is available."]
    if manifest_path.is_symlink():
        return [], ["The guideline manifest must be a regular local file, not a symlink."]
    try:
        if manifest_path.stat().st_size > 1_000_000:
            raise ValueError
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        entries = manifest["files"]
        if not isinstance(entries, list) or len(entries) > 100:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        return [], ["Guideline manifest.json is invalid. Use an object with a files array containing at most 100 entries."]
    if not entries:
        return [], ["The guideline manifest contains no sources. No NCCN-grounded assessment is available."]
    documents: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for number, entry in enumerate(entries, 1):
        try:
            if not isinstance(entry, dict):
                raise RagError("Use an object with file, title, and version fields.")
            if not _non_placeholder(entry.get("title")) or not _non_placeholder(entry.get("version")):
                raise RagError("A real source title and version/year are required; this source was excluded.")
            section = entry.get("section", "")
            if not isinstance(section, str) or len(section) > 300:
                raise RagError("The optional section field must be text with at most 300 characters.")
            cancer_types = entry.get("cancer_types", [])
            if not isinstance(cancer_types, list) or len(cancer_types) > 30 or not all(isinstance(x, str) and 0 < len(x.strip()) < 100 for x in cancer_types):
                raise RagError("The optional cancer_types field must be a list of short names.")
            path = _source_path(directory, entry.get("file"))
            canonical = str(path.resolve()).casefold()
            if canonical in seen:
                raise RagError("Duplicate source file in the manifest; this entry was excluded.")
            raw, pages = _read_pages(path)
            seen.add(canonical)
            documents.append({
                "file": path.relative_to(directory.resolve()).as_posix(),
                "title": entry["title"].strip(),
                "version": entry["version"].strip(),
                "section": section.strip(),
                "cancer_types": [value.strip().lower() for value in cancer_types],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "pages": pages,
            })
        except (RagError, OSError) as error:
            message = str(error) if isinstance(error, RagError) else "The source could not be read. Check local file permissions."
            warnings.append(f"Guideline entry {number}: {message}")
    if not documents:
        warnings.append("No valid guideline sources remain. No NCCN-grounded assessment is available.")
    return documents, warnings


def inspect_guidelines(directory: Path | str) -> dict[str, Any]:
    """Read local metadata/text without network calls or index mutation."""
    documents, warnings = _load_documents(Path(directory))
    return {"valid_files": len(documents), "warnings": warnings}


def _split_text(text: str) -> list[tuple[int, str]]:
    chunks: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        stop = min(start + CHUNK_SIZE, len(text))
        if stop < len(text):
            boundary = text.rfind(" ", start + CHUNK_SIZE // 2, stop)
            if boundary > start:
                stop = boundary
        chunk = text[start:stop].strip()
        if chunk:
            chunks.append((start, chunk))
        if stop == len(text):
            break
        start = max(start + 1, stop - CHUNK_OVERLAP)
    return chunks


def _make_chunks(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for document in documents:
        for page_location, text in document["pages"]:
            for number, (offset, snippet) in enumerate(_split_text(text), 1):
                location = "; ".join(x for x in (document["section"], page_location, f"text chunk {number}" if not page_location else "") if x)
                identifier = hashlib.sha256(f"{document['file']}\n{page_location}\n{offset}\n{snippet}".encode()).hexdigest()[:16]
                chunks.append({
                    "id": "G-" + identifier,
                    "title": document["title"],
                    "version": document["version"],
                    "location": location,
                    "text": snippet,
                    "source_file": document["file"],
                    "cancer_types": document["cancer_types"],
                    "score": 0.0,
                })
                if len(chunks) > MAX_CORPUS_CHUNKS:
                    raise RagError("The corpus exceeds 10,000 chunks. Use a smaller authorized guideline selection.")
    return chunks


def _validated_vectors(values: Any, expected_rows: int) -> np.ndarray:
    try:
        vectors = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError, OverflowError):
        raise RagError("The embedding service returned invalid vectors.") from None
    if vectors.ndim != 2 or vectors.shape[0] != expected_rows or vectors.shape[1] < 1 or not np.isfinite(vectors).all():
        raise RagError("The embedding service returned invalid or incomplete vectors.")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(norms).all() or np.any(norms <= 0):
        raise RagError("The embedding service returned empty or non-finite vectors.")
    return vectors / norms[:, None]


def _embed(texts: list[str], client: Any, model: str) -> np.ndarray:
    batches: list[np.ndarray] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        try:
            response = client.embeddings.create(model=model, input=batch, encoding_format="float")
        except Exception as error:
            kind = type(error).__name__
            if kind == "AuthenticationError":
                message = "OpenAI authentication failed. Check the configured API key."
            elif kind == "RateLimitError":
                message = "OpenAI rate or quota limit reached. Check account billing and retry later."
            else:
                message = "OpenAI embedding request failed. Check connectivity, model access, and API configuration."
            raise RagError(message) from None
        try:
            data = sorted(response.data, key=lambda item: item.index)
            if [item.index for item in data] != list(range(len(batch))):
                raise ValueError
            vectors = _validated_vectors([item.embedding for item in data], len(batch))
        except (AttributeError, TypeError, ValueError):
            raise RagError("The embedding service returned invalid or incomplete vectors.") from None
        if batches and vectors.shape[1] != batches[0].shape[1]:
            raise RagError("The embedding dimensions changed during indexing. Retry with one embedding model.")
        batches.append(vectors)
    return np.concatenate(batches, axis=0) if batches else np.empty((0, 0), dtype=np.float32)


def build_index(directory: Path | str, cache_dir: Path | str, client: Any, embedding_model: str) -> GuidelineIndex:
    """Build or reuse a content-addressed guideline-only vector cache."""
    if not isinstance(embedding_model, str) or not embedding_model.strip():
        raise RagError("Configure an embedding model before building the guideline index.")
    documents, warnings = _load_documents(Path(directory))
    chunks = _make_chunks(documents)
    fingerprint_data = {
        "schema": CACHE_SCHEMA,
        "model": embedding_model,
        "chunk_size": CHUNK_SIZE,
        "overlap": CHUNK_OVERLAP,
        "sources": [{key: value for key, value in document.items() if key != "pages"} for document in documents],
    }
    fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True).encode()).hexdigest()
    index = GuidelineIndex(chunks=chunks, model=embedding_model, fingerprint=fingerprint, warnings=warnings)
    if not chunks:
        return index
    cache_dir = Path(cache_dir)
    cache_path = cache_dir / f"guidelines-{fingerprint}.npz"
    metadata = json.dumps({"fingerprint": fingerprint, "model": embedding_model, "schema": CACHE_SCHEMA, "chunks": chunks}, sort_keys=True)
    if cache_path.is_file() and not cache_path.is_symlink():
        try:
            with np.load(cache_path, allow_pickle=False) as cached:
                if str(cached["metadata"].item()) != metadata:
                    raise ValueError("Metadata mismatch")
                index.vectors = _validated_vectors(cached["vectors"], len(chunks))
            index.cache_hit = True
            return index
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
            index.warnings.append("The guideline vector cache was unreadable and has been rebuilt.")
    index.vectors = _embed([chunk["text"] for chunk in chunks], client, embedding_model)
    temporary: str | None = None
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=cache_dir, prefix=".guidelines-", suffix=".npz", delete=False) as output:
            temporary = output.name
            np.savez_compressed(output, vectors=index.vectors, metadata=np.array(metadata))
        os.replace(temporary, cache_path)
        temporary = None
    except OSError:
        index.warnings.append("The guideline cache could not be saved. Retrieval still works for this session.")
    finally:
        if temporary:
            try:
                Path(temporary).unlink(missing_ok=True)
            except OSError:
                pass
    return index


def retrieve(query: str, index: GuidelineIndex, client: Any, embedding_model: str, top_k: int = 5, min_similarity: float = 0.3) -> list[dict[str, Any]]:
    """Return up to five cosine-ranked chunks; the score is NOT clinical confidence.

    Query vectors are ephemeral. Similarity is a retrieval heuristic, not proof
    of relevance or clinical applicability; the assessment must check support.
    """
    if not index.chunks or not query.strip():
        return []
    if embedding_model != index.model:
        raise RagError("The query and index embedding models differ. Rebuild the guideline index.")
    if not isinstance(top_k, int) or not 1 <= top_k <= 5:
        raise RagError("Retrieve between one and five evidence chunks.")
    if not np.isfinite(min_similarity) or not -1 <= min_similarity <= 1:
        raise RagError("The similarity threshold must be a finite number between -1 and 1.")
    if len(query) > 20000:
        raise RagError("The retrieval query is too long. Use concise structured findings.")
    vectors = _validated_vectors(index.vectors, len(index.chunks))
    query_vector = _embed([query], client, embedding_model)[0]
    if vectors.shape[1] != query_vector.shape[0]:
        raise RagError("The embedding dimensions differ. Rebuild the guideline index with the configured model.")
    scores = np.clip(vectors @ query_vector, -1.0, 1.0)
    ranked = np.argsort(-scores, kind="stable")
    return [dict(index.chunks[int(position)], score=float(scores[int(position)])) for position in ranked if scores[int(position)] >= min_similarity][:top_k]
