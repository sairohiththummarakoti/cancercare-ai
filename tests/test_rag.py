from pathlib import Path
from types import SimpleNamespace
import json

import numpy as np
import pytest

from rag import GuidelineIndex, RagError, build_index, inspect_guidelines, retrieve


class FakeEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, *, model, input, encoding_format):
        self.calls.append((model, list(input)))
        data = []
        for number, text in enumerate(input):
            vector = [1.0, 0.0] if "breast" in text.lower() else [0.0, 1.0]
            data.append(SimpleNamespace(index=number, embedding=vector))
        # Deliberately return reversed provider order; indices must be honored.
        return SimpleNamespace(data=list(reversed(data)))


@pytest.fixture
def client():
    return SimpleNamespace(embeddings=FakeEmbeddings())


def add_source(directory: Path, text="Breast cancer source evidence for local retrieval tests.", version="2026"):
    directory.mkdir(exist_ok=True)
    (directory / "breast.txt").write_text(text, encoding="utf-8")
    (directory / "manifest.json").write_text(json.dumps({"files": [{"file": "breast.txt", "title": "Synthetic test evidence", "version": version, "section": "Test section"}]}), encoding="utf-8")


def test_missing_corpus_never_calls_api(tmp_path, client):
    index = build_index(tmp_path / "missing", tmp_path / "cache", client, "test-model")
    assert index.chunks == []
    assert retrieve("private report query", index, client, "test-model") == []
    assert client.embeddings.calls == []
    assert not (tmp_path / "cache").exists()
    assert index.warnings


def test_manifest_missing_version_excludes_source(tmp_path, client):
    add_source(tmp_path, version="")
    assert inspect_guidelines(tmp_path)["valid_files"] == 0
    assert build_index(tmp_path, tmp_path / "cache", client, "m").chunks == []
    assert client.embeddings.calls == []


def test_cache_reused_and_content_metadata_model_changes_invalidate(tmp_path, client):
    directory = tmp_path / "guidelines"
    cache = tmp_path / "cache"
    add_source(directory)
    first = build_index(directory, cache, client, "m")
    assert not first.cache_hit
    second = build_index(directory, cache, client, "m")
    assert second.cache_hit
    assert len(client.embeddings.calls) == 1
    add_source(directory, text="Breast updated source evidence for local retrieval tests.")
    changed = build_index(directory, cache, client, "m")
    assert changed.fingerprint != first.fingerprint
    assert not changed.cache_hit
    add_source(directory, text="Breast updated source evidence for local retrieval tests.", version="2027")
    metadata_changed = build_index(directory, cache, client, "m")
    assert metadata_changed.fingerprint != changed.fingerprint
    other_model = build_index(directory, cache, client, "other-model")
    assert other_model.fingerprint != metadata_changed.fingerprint
    assert len(client.embeddings.calls) == 4


def test_cosine_ranking_cutoff_and_query_not_cached(tmp_path, client):
    directory = tmp_path / "guidelines"
    add_source(directory)
    (directory / "lung.txt").write_text("Lung cancer source evidence for local retrieval tests.", encoding="utf-8")
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["files"].append({"file": "lung.txt", "title": "Lung test evidence", "version": "2026"})
    (directory / "manifest.json").write_text(json.dumps(manifest))
    cache = tmp_path / "cache"
    index = build_index(directory, cache, client, "m")
    before = {path.name: path.read_bytes() for path in cache.iterdir()}
    found = retrieve("breast private patient query", index, client, "m")
    assert len(found) == 1
    assert found[0]["source_file"] == "breast.txt"
    assert found[0]["score"] == pytest.approx(1)
    assert {path.name: path.read_bytes() for path in cache.iterdir()} == before
    assert all("private patient" not in chunk["text"] for chunk in index.chunks)


def test_unrelated_vectors_return_no_evidence(client):
    index = GuidelineIndex(chunks=[{"id": "test"}], vectors=np.array([[0, 1]]), model="m")
    assert retrieve("breast query", index, client, "m") == []


@pytest.mark.parametrize("filename", ["../outside.txt", "C:/outside.txt", "/outside.txt", "test.exe"])
def test_traversal_and_unsupported_paths_rejected(tmp_path, client, filename):
    (tmp_path / "manifest.json").write_text(json.dumps({"files": [{"file": filename, "title": "Test", "version": "2026"}]}))
    assert inspect_guidelines(tmp_path)["valid_files"] == 0
    assert build_index(tmp_path, tmp_path / "cache", client, "m").chunks == []
    assert client.embeddings.calls == []


def test_unlisted_files_are_never_indexed(tmp_path, client):
    add_source(tmp_path)
    (tmp_path / "unlisted.txt").write_text("Unlisted text that must not be sent to any API.")
    index = build_index(tmp_path, tmp_path / "cache", client, "m")
    assert {chunk["source_file"] for chunk in index.chunks} == {"breast.txt"}


def test_invalid_cache_rebuilt_without_pickle(tmp_path, client):
    add_source(tmp_path)
    cache = tmp_path / "cache"
    first = build_index(tmp_path, cache, client, "m")
    (cache / f"guidelines-{first.fingerprint}.npz").write_bytes(b"broken cache")
    next_index = build_index(tmp_path, cache, client, "m")
    assert not next_index.cache_hit
    assert len(client.embeddings.calls) == 2
    assert any("rebuilt" in warning for warning in next_index.warnings)


@pytest.mark.parametrize("vector", [[0, 0], [float("nan"), 1], [float("inf"), 1]])
def test_invalid_provider_vectors_fail_safely(tmp_path, vector):
    add_source(tmp_path)
    api = SimpleNamespace(embeddings=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(data=[SimpleNamespace(index=0, embedding=vector)])))
    with pytest.raises(RagError, match="invalid|empty|non-finite"):
        build_index(tmp_path, tmp_path / "cache", api, "m")


def test_dimension_and_model_mismatch_fail_safely(client):
    index = GuidelineIndex(chunks=[{"id": "test"}], vectors=np.array([[1, 0, 0]]), model="m")
    with pytest.raises(RagError, match="dimensions"):
        retrieve("breast", index, client, "m")
    with pytest.raises(RagError, match="models"):
        retrieve("breast", index, client, "different")


def test_api_error_does_not_leak_request_text(tmp_path):
    add_source(tmp_path)
    def fail(**kwargs):
        raise RuntimeError("secret-provider-payload")
    api = SimpleNamespace(embeddings=SimpleNamespace(create=fail))
    with pytest.raises(RagError) as caught:
        build_index(tmp_path, tmp_path / "cache", api, "m")
    assert "secret-provider-payload" not in str(caught.value)


def test_pdf_source_preserves_physical_page_location(tmp_path, client):
    import pymupdf

    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Breast source evidence on the first physical page.")
    pdf.new_page().insert_text((72, 72), "Breast source evidence on the second physical page.")
    pdf.save(tmp_path / "source.pdf")
    pdf.close()
    (tmp_path / "manifest.json").write_text(json.dumps({"files": [{"file": "source.pdf", "title": "Synthetic PDF source", "version": "2026"}]}))
    index = build_index(tmp_path, tmp_path / "cache", client, "m")
    assert [chunk["location"] for chunk in index.chunks] == ["PDF page 1", "PDF page 2"]
