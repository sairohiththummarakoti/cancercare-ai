"""Permission-gated access to the existing versioned guideline RAG pipeline."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from rag import _load_documents, _non_placeholder, _source_path


def inspect_authorized_sources(directory: Path) -> dict:
    path = directory / "manifest.json"
    unavailable = {"available": False, "documents": [], "metadata": {}, "warnings": []}
    if not path.is_file() or path.is_symlink():
        return dict(unavailable, warnings=["Guideline evidence unavailable: no authorized source manifest is configured."])
    try:
        if path.stat().st_size > 1_000_000:
            raise ValueError
        entries = json.loads(path.read_text(encoding="utf-8-sig"))["files"]
        if not isinstance(entries, list) or not entries or len(entries) > 100:
            raise ValueError
    except (OSError, ValueError, KeyError, TypeError):
        return dict(unavailable, warnings=["Guideline evidence unavailable: the source manifest is invalid or empty."])
    for entry in entries:
        if (not isinstance(entry, dict) or not all(entry.get(flag) is True for flag in ("authorized", "allow_external_processing", "version_verified"))
                or not _non_placeholder(entry.get("publisher"))):
            return dict(unavailable, warnings=["Guideline evidence unavailable: every source requires explicit authorization, external-processing permission, verified version, and publisher metadata."])
        if entry.get("source_kind") == "educational_mcqa":
            return dict(unavailable, warnings=["Generated MCQA research cases cannot be used as original guideline evidence."])
    documents, warnings = _load_documents(directory)
    # Fail closed if any declared source is invalid; no partly approved corpus is transmitted.
    if len(documents) != len(entries):
        return dict(unavailable, warnings=warnings + ["Guideline source validation failed; external processing is disabled."])
    metadata = {}
    by_file = {Path(entry["file"]).as_posix(): entry for entry in entries}
    for document in documents:
        entry = by_file[document["file"]]
        identifier = hashlib.sha256(f"{document['file']}\n{document['sha256']}\n{document['version']}".encode()).hexdigest()[:24]
        metadata[document["file"]] = {"source_id": identifier, "publisher": entry["publisher"].strip(),
                                      "url": f"/api/knowledge-sources/documents/{identifier}"}
    return {"available": bool(documents), "documents": documents, "metadata": metadata, "warnings": warnings}


def source_document(directory: Path, source_id: str):
    status = inspect_authorized_sources(directory)
    for filename, metadata in status["metadata"].items():
        if metadata["source_id"] == source_id:
            return _source_path(directory, filename)
    return None
