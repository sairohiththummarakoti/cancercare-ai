"""Local neural embeddings and an auditable, persistent MedGUIDE vector index.

Dataset embeddings are persisted; search queries and their vectors never are.
The index contains educational MCQA material, not verified clinical guidelines.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib.metadata import version
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable
import zipfile

import numpy as np

DEFAULT_MODEL = "minishlab/potion-retrieval-32M"
INDEX_SCHEMA = 1
BATCH_SIZE = 32
MAX_TOKENS = 512
MAX_CHUNKS = 100_000
MAX_INDEX_BYTES = 1_000_000_000


class MedguideVectorError(ValueError):
    """Safe, actionable indexing or retrieval failure."""


@dataclass
class MedguideIndex:
    chunks: list[dict]
    vectors: np.ndarray
    metadata: dict


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError):
        raise MedguideVectorError("Index metadata must contain finite JSON-compatible values.") from None


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@lru_cache(maxsize=2)
def _cached_local_embedder(model_name: str, cache_dir: str):
    try:
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=4,
                             providers=["CPUExecutionProvider"])
    except Exception:
        raise MedguideVectorError(
            "The local embedding model could not load. Install requirements, check available disk space, "
            "and allow the first model download from Hugging Face. No API key is required."
        ) from None


def get_local_embedder(model_name: str = DEFAULT_MODEL, model_cache_dir: Path | str | None = None):
    """Warm or reuse the local ONNX model; the first call downloads its weights."""
    if not isinstance(model_name, str) or not model_name.strip():
        raise MedguideVectorError("Choose a supported local embedding model.")
    root = Path(model_cache_dir) if model_cache_dir else Path(__file__).resolve().parent / ".cache" / "embedding-models"
    return _cached_local_embedder(model_name, str(root.resolve()))


def _embedder_signature(embedder, model_name: str) -> dict:
    actual_name = getattr(embedder, "model_name", model_name)
    if actual_name != model_name:
        raise MedguideVectorError("The selected embedding model differs from the index model. Rebuild the index.")
    inner = getattr(embedder, "model", None)
    model_dir = getattr(inner, "_model_dir", None)
    if model_dir is None:
        # Dependency injection is reserved for tests or explicit caller-provided implementations.
        return {"model_name": model_name, "provider": "injected", "implementation": type(embedder).__qualname__,
                "revision": str(getattr(embedder, "fingerprint", "test-or-caller-supplied")),
                "passage_method": "passage_embed", "query_method": "query_embed"}
    description = getattr(inner, "model_description", None)
    model_file = getattr(description, "model_file", None)
    if not model_file:
        raise MedguideVectorError("The local model does not expose a verifiable ONNX model file.")
    model_root = Path(model_dir)
    paths = [model_root / model_file]
    paths += [model_root / name for name in ("tokenizer.json", "config.json", "tokenizer_config.json", "special_tokens_map.json")
              if (model_root / name).is_file()]
    paths += [model_root / name for name in (getattr(description, "additional_files", None) or [])]
    try:
        checksums = {str(path.relative_to(model_root)).replace("\\", "/"): _sha_file(path) for path in paths}
    except OSError:
        raise MedguideVectorError("The cached embedding model is incomplete. Download it again before rebuilding.") from None
    return {"model_name": model_name, "provider": "fastembed-onnx-cpu", "fastembed_version": version("fastembed"),
            "model_files_sha256": checksums, "dimensions": int(description.dim), "max_tokens": MAX_TOKENS,
            "passage_method": "passage_embed", "query_method": "query_embed", "normalization": "l2"}


def _token_lengths(embedder, texts: list[str]) -> list[int] | None:
    """Clone the model tokenizer with truncation disabled; do not alter the live model."""
    inner = getattr(embedder, "model", None)
    tokenizer = getattr(inner, "tokenizer", None)
    if tokenizer is None:
        if inner is not None:
            raise MedguideVectorError("Cannot verify this model's token limit. Use a supported local embedding model.")
        return None  # Test/caller-injected implementations define their own input limits.
    try:
        from tokenizers import Tokenizer
        counter = Tokenizer.from_str(tokenizer.to_str())
        counter.no_truncation()
        counter.no_padding()
        return [len(item.ids) for item in counter.encode_batch(texts)]
    except Exception:
        raise MedguideVectorError("Cannot verify text token lengths for the local embedding model.") from None


def _check_token_limit(embedder, texts: list[str], *, query=False):
    lengths = _token_lengths(embedder, texts)
    if lengths and max(lengths) > MAX_TOKENS:
        if query:
            raise MedguideVectorError("This search exceeds the 512-token local model limit. Use a shorter focused query.")
        raise MedguideVectorError("A dataset chunk exceeds the 512-token model limit. Rechunk with a smaller max_chars value; no text was silently truncated.")


def _validate_chunks(chunks: Any) -> list[dict]:
    if not isinstance(chunks, list) or not chunks or len(chunks) > MAX_CHUNKS:
        raise MedguideVectorError("The dataset index needs between 1 and 100,000 chunks.")
    required = ("id", "title", "version", "location", "text", "disease", "dataset_id", "revision", "source_url", "answer_text")
    ids = set()
    for chunk in chunks:
        if not isinstance(chunk, dict) or any(not isinstance(chunk.get(key), str) or not chunk[key].strip() for key in required):
            raise MedguideVectorError("A dataset chunk is missing its text or required provenance.")
        if chunk.get("source_kind") != "educational_mcqa" or not isinstance(chunk.get("row_index"), int) or isinstance(chunk.get("row_index"), bool) or chunk["row_index"] < 0:
            raise MedguideVectorError("Only provenance-labeled educational MCQA chunks can enter this index.")
        if len(chunk["text"]) > 20_000 or chunk["id"] in ids:
            raise MedguideVectorError("Chunk identifiers must be unique and chunk text must be bounded.")
        ids.add(chunk["id"])
    _canonical(chunks)
    return chunks


def _normalize(values: Any, rows: int, expected_dims: int | None = None) -> np.ndarray:
    try:
        vectors = np.asarray(values, dtype=np.float32)
    except (TypeError, ValueError, OverflowError):
        raise MedguideVectorError("The embedding model returned invalid vectors.") from None
    if vectors.ndim != 2 or vectors.shape[0] != rows or not 1 <= vectors.shape[1] <= 8192:
        raise MedguideVectorError("Embedding count or dimensions do not match the dataset.")
    if expected_dims is not None and vectors.shape[1] != expected_dims:
        raise MedguideVectorError("Embedding dimensions differ from the configured model.")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.isfinite(vectors).all() or not np.isfinite(norms).all() or np.any(norms <= 0):
        raise MedguideVectorError("Embeddings contain zero, non-finite, or invalid vectors.")
    return np.ascontiguousarray(vectors / norms[:, None])


def _write_atomic(path: Path, data: bytes):
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".write-", delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def load_medguide_index(index_dir: Path | str) -> MedguideIndex:
    """Load only a complete atomic generation and reject corruption or mixed metadata."""
    root = Path(index_dir)
    pointer_path = root / "index.json"
    try:
        if pointer_path.is_symlink() or pointer_path.stat().st_size > 2_000_000:
            raise ValueError
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        fingerprint = pointer["fingerprint"]
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
            raise ValueError
        filename = f"generation-{fingerprint}.npz"
        if pointer["file"] != filename or pointer["schema"] != INDEX_SCHEMA:
            raise ValueError
        artifact = root / filename
        if artifact.is_symlink() or not 0 < artifact.stat().st_size <= MAX_INDEX_BYTES or _sha_file(artifact) != pointer["sha256"]:
            raise ValueError
        with np.load(artifact, allow_pickle=False) as archive:
            metadata = json.loads(str(archive["metadata"].item()))
            chunks = _validate_chunks(json.loads(str(archive["chunks"].item())))
            vectors = _normalize(archive["vectors"], len(chunks), metadata["dimensions"])
        expected = hashlib.sha256(_canonical({"schema": INDEX_SCHEMA, "encoder": metadata["encoder"], "chunks": chunks})).hexdigest()
        if expected != fingerprint or metadata["fingerprint"] != fingerprint or metadata["chunk_count"] != len(chunks) or metadata["schema"] != INDEX_SCHEMA:
            raise ValueError
        if metadata["source_kind"] != "educational_mcqa" or metadata["model_name"] != metadata["encoder"]["model_name"]:
            raise ValueError
        return MedguideIndex(chunks=chunks, vectors=vectors, metadata=metadata)
    except (OSError, ValueError, TypeError, KeyError, EOFError, zipfile.BadZipFile):
        raise MedguideVectorError("The MedGUIDE vector index is missing, incomplete or corrupt. Run ingestion and indexing again.") from None


def build_medguide_index(chunks: list[dict], index_dir: Path | str, model_name: str = DEFAULT_MODEL,
                        model_cache_dir: Path | str | None = None, progress: Callable | None = None,
                        embedder=None) -> dict:
    """Embed all chunks with a real local encoder, then atomically publish the index.

    Passing embedder enables offline unit tests. Production uses FastEmbed ONNX.
    The callback receives (completed_chunks, total_chunks).
    """
    started = time.perf_counter()
    chunks = _validate_chunks(chunks)
    encoder = embedder if embedder is not None else get_local_embedder(model_name, model_cache_dir)
    signature = _embedder_signature(encoder, model_name)
    fingerprint = hashlib.sha256(_canonical({"schema": INDEX_SCHEMA, "encoder": signature, "chunks": chunks})).hexdigest()
    root = Path(index_dir)
    if (root / "index.json").is_file():
        try:
            cached = load_medguide_index(root)
            if cached.metadata["fingerprint"] == fingerprint:
                if progress:
                    progress(len(chunks), len(chunks))
                return dict(cached.metadata, cache_hit=True, elapsed_seconds=time.perf_counter() - started)
        except MedguideVectorError:
            pass  # Rebuilding does not overwrite the old pointer until the new index is complete.
    all_vectors = []
    dimensions = signature.get("dimensions")
    for start in range(0, len(chunks), BATCH_SIZE):
        texts = [chunk["text"] for chunk in chunks[start:start + BATCH_SIZE]]
        _check_token_limit(encoder, texts)
        try:
            batch = list(encoder.passage_embed(texts, batch_size=BATCH_SIZE))
        except Exception:
            raise MedguideVectorError("Local embedding failed. Check memory and model availability, then rebuild the dataset index.") from None
        vectors = _normalize(batch, len(texts), dimensions)
        dimensions = vectors.shape[1]
        all_vectors.append(vectors)
        if progress:
            progress(start + len(texts), len(chunks))
    matrix = np.concatenate(all_vectors)
    metadata = {
        "schema": INDEX_SCHEMA, "fingerprint": fingerprint, "model_name": model_name, "encoder": signature,
        "dimensions": int(matrix.shape[1]), "chunk_count": len(chunks),
        "document_count": len({(c["dataset_id"], c["revision"], c["row_index"]) for c in chunks}),
        "diseases": sorted({chunk["disease"] for chunk in chunks}),
        "source_kind": "educational_mcqa", "dataset_revisions": sorted({c["revision"] for c in chunks}),
        "embedding_seconds": time.perf_counter() - started, "similarity": "cosine on L2-normalized vectors",
    }
    temporary = None
    try:
        root.mkdir(parents=True, exist_ok=True)
        destination = root / f"generation-{fingerprint}.npz"
        with tempfile.NamedTemporaryFile(dir=root, prefix=".generation-", suffix=".npz", delete=False) as output:
            temporary = Path(output.name)
            np.savez_compressed(output, vectors=matrix, chunks=np.asarray(_canonical(chunks).decode("utf-8")),
                                metadata=np.asarray(_canonical(metadata).decode("utf-8")))
            output.flush()
            os.fsync(output.fileno())
        checksum = _sha_file(temporary)
        os.replace(temporary, destination)
        temporary = None
        pointer = {"schema": INDEX_SCHEMA, "fingerprint": fingerprint, "file": destination.name, "sha256": checksum}
        _write_atomic(root / "index.json", _canonical(pointer))
    except OSError:
        raise MedguideVectorError("The vector index could not be saved. Check local disk space and write permissions.") from None
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    # Do not claim success until the published generation passes its own read contract.
    load_medguide_index(root)
    return dict(metadata, cache_hit=False, elapsed_seconds=time.perf_counter() - started)


def search_medguide(query: str, index: MedguideIndex, top_k: int = 5, disease: str | None = None,
                    min_similarity: float = 0.3, embedder=None, model_cache_dir: Path | str | None = None) -> list[dict]:
    """Rank by real cosine similarity, with exact disease filtering and row deduplication."""
    if not isinstance(query, str) or not query.strip():
        return []
    if len(query) > 20_000:
        raise MedguideVectorError("Use a shorter focused search query.")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or not 1 <= top_k <= 20:
        raise MedguideVectorError("Choose between 1 and 20 search results.")
    if not isinstance(min_similarity, (int, float)) or not np.isfinite(min_similarity) or not -1 <= min_similarity <= 1:
        raise MedguideVectorError("Similarity threshold must be a finite number between -1 and 1.")
    candidates = [i for i, chunk in enumerate(index.chunks) if disease is None or chunk["disease"] == disease]
    if not candidates:
        return []
    model_name = index.metadata["model_name"]
    encoder = embedder if embedder is not None else get_local_embedder(model_name, model_cache_dir)
    signature = _embedder_signature(encoder, model_name)
    if signature != index.metadata["encoder"]:
        raise MedguideVectorError("The local embedding model has changed since indexing. Rebuild before searching.")
    _check_token_limit(encoder, [query], query=True)
    try:
        query_vector = _normalize(list(encoder.query_embed(query)), 1, index.metadata["dimensions"])[0]
    except MedguideVectorError:
        raise
    except Exception:
        raise MedguideVectorError("The local search embedding failed. Check the cached model and retry.") from None
    vectors = _normalize(index.vectors, len(index.chunks), index.metadata["dimensions"])
    scores = np.clip(vectors[candidates] @ query_vector, -1, 1)
    order = np.argsort(-scores, kind="stable")
    results = []
    seen = set()
    for offset in order:
        if float(scores[offset]) < min_similarity:
            break
        chunk = index.chunks[candidates[int(offset)]]
        row = (chunk["dataset_id"], chunk["revision"], chunk["row_index"])
        if row in seen:
            continue
        seen.add(row)
        results.append(dict(chunk, score=float(scores[offset])))
        if len(results) == top_k:
            break
    return results
