"""No-network contracts for persistent local neural vector retrieval."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from medguide_vectors import (
    MedguideVectorError,
    build_medguide_index,
    load_medguide_index,
    search_medguide,
)


class FakeEncoder:
    model_name = "test-encoder"
    fingerprint = "test-revision-1"

    def __init__(self):
        self.passage_calls = []
        self.query_calls = []

    @staticmethod
    def vector(text):
        text = text.lower()
        if "breast" in text:
            return np.array([3.0, 0.0, 0.0])
        if "lung" in text:
            return np.array([2.0, 2.0, 0.0])
        return np.array([0.0, 0.0, 2.0])

    def passage_embed(self, texts, **kwargs):
        self.passage_calls.append(list(texts))
        return (self.vector(text) for text in texts)

    def query_embed(self, query, **kwargs):
        self.query_calls.append(query)
        return [self.vector(query)]


def chunk(row, text, disease="breast", suffix="0"):
    return {
        "id": f"mcqa-{row}-{suffix}", "title": "Educational MCQA dataset case", "version": "dataset revision abcdef",
        "location": f"train row {row}", "text": text, "disease": disease, "dataset_id": "MedGUIDE/MedGUIDE-MCQA-8K",
        "revision": "abcdef", "source_url": "https://huggingface.co/datasets/MedGUIDE/MedGUIDE-MCQA-8K",
        "source_kind": "educational_mcqa", "answer_text": "Dataset-labeled answer", "row_index": row,
    }


def build(tmp_path, encoder, chunks=None):
    chunks = chunks or [chunk(0, "Breast cancer profile"), chunk(1, "Lung cancer profile", "lung")]
    summary = build_medguide_index(chunks, tmp_path, model_name=encoder.model_name, embedder=encoder)
    return summary, load_medguide_index(tmp_path)


def test_actual_cosine_ranking_and_query_not_persisted(tmp_path):
    encoder = FakeEncoder()
    summary, index = build(tmp_path, encoder)
    assert summary["dimensions"] == 3
    assert summary["document_count"] == 2
    assert np.allclose(np.linalg.norm(index.vectors, axis=1), 1)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    matches = search_medguide("breast confidential-query-marker", index, embedder=encoder)
    assert [m["row_index"] for m in matches] == [0, 1]
    assert matches[0]["score"] == pytest.approx(1)
    assert matches[1]["score"] == pytest.approx(1 / np.sqrt(2))
    assert encoder.query_calls == ["breast confidential-query-marker"]
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_cache_hit_does_not_embed_documents_again(tmp_path):
    encoder = FakeEncoder()
    first, _ = build(tmp_path, encoder)
    second, _ = build(tmp_path, encoder)
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert len(encoder.passage_calls) == 1
    assert first["fingerprint"] == second["fingerprint"]


def test_content_metadata_and_model_revision_invalidate_cache(tmp_path):
    encoder = FakeEncoder()
    first, _ = build(tmp_path, encoder)
    changed = [chunk(0, "Breast altered profile"), chunk(1, "Lung cancer profile", "lung")]
    second, _ = build(tmp_path, encoder, changed)
    changed[0]["title"] = "Updated provenance title"
    third, _ = build(tmp_path, encoder, changed)
    encoder.fingerprint = "test-revision-2"
    fourth, _ = build(tmp_path, encoder, changed)
    assert len({s["fingerprint"] for s in (first, second, third, fourth)}) == 4
    assert len(encoder.passage_calls) == 4


def test_disease_filter_cutoff_and_row_deduplication(tmp_path):
    encoder = FakeEncoder()
    chunks = [chunk(0, "Breast first chunk"), chunk(0, "Breast overlapping chunk", suffix="1"),
              chunk(1, "Lung profile", "lung"), chunk(2, "Leukemia profile", "aml")]
    _, index = build(tmp_path, encoder, chunks)
    assert [r["row_index"] for r in search_medguide("breast", index, embedder=encoder)] == [0, 1]
    assert [r["row_index"] for r in search_medguide("breast", index, disease="lung", embedder=encoder)] == [1]
    assert len(search_medguide("breast", index, min_similarity=.9, embedder=encoder)) == 1
    count = len(encoder.query_calls)
    assert search_medguide("breast", index, disease="unknown", embedder=encoder) == []
    assert search_medguide(" ", index, embedder=encoder) == []
    assert len(encoder.query_calls) == count


def test_query_encoder_revision_mismatch_fails_closed(tmp_path):
    encoder = FakeEncoder()
    _, index = build(tmp_path, encoder)
    encoder.fingerprint = "changed-weight-files"
    with pytest.raises(MedguideVectorError, match="changed since indexing"):
        search_medguide("breast", index, embedder=encoder)


def test_wrong_model_name_fails_before_embedding(tmp_path):
    encoder = FakeEncoder()
    with pytest.raises(MedguideVectorError, match="differs from the index"):
        build_medguide_index([chunk(0, "Breast")], tmp_path, model_name="different-model", embedder=encoder)
    assert not encoder.passage_calls


@pytest.mark.parametrize("value", [0, 21, True, 2.5])
def test_invalid_top_k(tmp_path, value):
    encoder = FakeEncoder()
    _, index = build(tmp_path, encoder)
    with pytest.raises(MedguideVectorError, match="between 1 and 20"):
        search_medguide("breast", index, top_k=value, embedder=encoder)


def test_checksum_corruption_fails_and_rebuild_recovers(tmp_path):
    encoder = FakeEncoder()
    build(tmp_path, encoder)
    pointer = json.loads((tmp_path / "index.json").read_text())
    (tmp_path / pointer["file"]).write_bytes(b"corrupt")
    with pytest.raises(MedguideVectorError, match="corrupt"):
        load_medguide_index(tmp_path)
    summary, index = build(tmp_path, encoder)
    assert not summary["cache_hit"]
    assert index.vectors.shape == (2, 3)


def test_pointer_cannot_escape_index_directory(tmp_path):
    encoder = FakeEncoder()
    build(tmp_path, encoder)
    pointer = json.loads((tmp_path / "index.json").read_text())
    pointer["file"] = "../foreign.npz"
    (tmp_path / "index.json").write_text(json.dumps(pointer))
    with pytest.raises(MedguideVectorError, match="corrupt"):
        load_medguide_index(tmp_path)


def test_failed_rebuild_preserves_previous_generation(tmp_path):
    encoder = FakeEncoder()
    summary, _ = build(tmp_path, encoder)
    original_pointer = (tmp_path / "index.json").read_bytes()
    encoder.passage_embed = lambda texts, **kwargs: (_ for _ in ()).throw(RuntimeError("provider error"))
    with pytest.raises(MedguideVectorError, match="Local embedding failed"):
        build(tmp_path, encoder, [chunk(8, "New breast case")])
    assert (tmp_path / "index.json").read_bytes() == original_pointer
    assert load_medguide_index(tmp_path).metadata["fingerprint"] == summary["fingerprint"]


@pytest.mark.parametrize("values", [[[0, 0, 0]], [[float("nan"), 1, 2]], [[1, 2]], []])
def test_invalid_vectors_not_published(tmp_path, values):
    encoder = FakeEncoder()
    # One row expects count validation; [1,2] is rejected by a declared dimension here.
    if values == [[1, 2]]:
        encoder.passage_embed = lambda texts, **kwargs: [[1, 2], [1, 2, 3]]
    else:
        encoder.passage_embed = lambda texts, **kwargs: values
    with pytest.raises(MedguideVectorError):
        build(tmp_path, encoder, [chunk(0, "Breast case")])
    assert not (tmp_path / "index.json").exists()


def test_duplicate_ids_and_non_mcqa_sources_rejected(tmp_path):
    encoder = FakeEncoder()
    with pytest.raises(MedguideVectorError, match="unique"):
        build(tmp_path, encoder, [chunk(0, "Breast"), chunk(0, "Breast other")])
    candidate = chunk(0, "Breast")
    candidate["source_kind"] = "clinical_guideline"
    with pytest.raises(MedguideVectorError, match="educational MCQA"):
        build(tmp_path, encoder, [candidate])


def test_progress_covers_every_chunk_and_batch_order_is_preserved(tmp_path):
    encoder = FakeEncoder()
    chunks = [chunk(i, "Breast" if i % 2 else "Lung") for i in range(35)]
    progress = []
    build_medguide_index(chunks, tmp_path, model_name=encoder.model_name, embedder=encoder,
                         progress=lambda done, total: progress.append((done, total)))
    assert progress == [(32, 35), (35, 35)]
    index = load_medguide_index(tmp_path)
    assert [c["row_index"] for c in index.chunks] == list(range(35))
    assert index.vectors[1].tolist() == [1, 0, 0]


def test_dimension_change_between_batches_is_rejected(tmp_path):
    encoder = FakeEncoder()
    counter = []

    def inconsistent(texts, **kwargs):
        counter.append(1)
        return [[1, 0, 0] if len(counter) == 1 else [1, 0] for _ in texts]

    encoder.passage_embed = inconsistent
    with pytest.raises(MedguideVectorError, match="dimensions differ"):
        build(tmp_path, encoder, [chunk(i, "Breast") for i in range(35)])
    assert not (tmp_path / "index.json").exists()


def test_oversized_tokens_are_rejected_without_mutating_model_tokenizer(tmp_path):
    from tokenizers import Tokenizer
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace

    tokenizer = Tokenizer(WordLevel({"[UNK]": 0, "breast": 1}, unk_token="[UNK]"))
    tokenizer.pre_tokenizer = Whitespace()
    tokenizer.enable_truncation(512)
    encoder = FakeEncoder()
    encoder.model = SimpleNamespace(tokenizer=tokenizer)
    text = "breast " * 600
    assert len(tokenizer.encode(text).ids) == 512
    with pytest.raises(MedguideVectorError, match="no text was silently truncated"):
        build(tmp_path, encoder, [chunk(0, text)])
    assert len(tokenizer.encode(text).ids) == 512
    assert not encoder.passage_calls
