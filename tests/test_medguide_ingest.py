"""Offline ingestion and provenance tests; no network or paid API requests."""
from copy import deepcopy
import hashlib
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import medguide_ingest as ingest

REVISION = "a" * 40


def row(**changes):
    value = {
        "generation_model": "synthetic-test-model", "disease": "breast_1",
        "path": ["Reported receptor profile", "Specialist educational review"],
        "profile": "An invented breast cancer case reports hormone-receptor positivity; full stage is not supplied.",
        "options": ["Dataset correct educational answer", "UNSAFE DISTRACTOR MUST NOT BE INDEXED"],
        "option_count": 2, "answer": "A", "answer_text": "Dataset correct educational answer",
        "prompt": "RAW PROMPT WITH INCORRECT OPTIONS MUST NOT BE INDEXED",
    }
    value.update(changes)
    return value


def parquet_bytes(rows):
    target = pa.BufferOutputStream()
    pq.write_table(pa.Table.from_pylist(rows), target)
    return target.getvalue().to_pybytes()


class FakeResponse:
    def __init__(self, data):
        self.data = data
        self.headers = {"Content-Length": str(len(data))}
        self.closed = False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.data), chunk_size):
            yield self.data[offset:offset + chunk_size]

    def close(self):
        self.closed = True


def fake_network(monkeypatch, rows=None, *, digest=None, metadata_changes=None):
    source = parquet_bytes(rows or [row()])
    metadata = {"id": ingest.DATASET_ID, "sha": REVISION, "private": False, "gated": False,
                "cardData": {}, "siblings": [{"rfilename": "README.md"},
                {"rfilename": ingest.PARQUET_FILE, "lfs": {"sha256": digest or hashlib.sha256(source).hexdigest()}}]}
    metadata.update(metadata_changes or {})
    card = b"# MedGUIDE\n\n## License\nTBD. Intended for academic and research use.\n"
    calls = []

    def get(url, *, params=None, timeout=None, stream=None):
        calls.append(url)
        assert stream is True
        assert timeout == (15, 90)
        if "/api/datasets/" in url:
            return FakeResponse(json.dumps(metadata).encode())
        if url.endswith("README.md"):
            return FakeResponse(card)
        assert url.endswith(ingest.PARQUET_FILE)
        return FakeResponse(source)

    monkeypatch.setattr(ingest.requests, "get", get)
    return calls


def test_ingest_pins_revision_and_excludes_wrong_answers(tmp_path, monkeypatch):
    calls = fake_network(monkeypatch, [row(), row(answer="B")])
    messages = []
    summary = ingest.ingest_medguide(tmp_path, progress=messages.append)
    assert summary["revision"] == REVISION
    assert summary["accepted_rows"] == 1
    assert summary["rejected_rows"] == 1
    assert summary["rejection_reasons"] == {"answer_mismatch": 1}
    assert summary["license_identifier"] is None
    assert summary["license_status"] == "not_specified"
    assert summary["license_statement"] == "TBD. Intended for academic and research use."
    assert all(f"/resolve/{REVISION}/" in url for url in calls if "/api/" not in url)
    records = ingest.load_documents(tmp_path)
    assert records[0]["row_index"] == 0
    assert records[0]["guideline_version"] is None
    text = (tmp_path / "documents.jsonl").read_text()
    assert "UNSAFE DISTRACTOR" not in text
    assert "RAW PROMPT" not in text
    assert records[0]["source_kind"] == "educational_mcqa"
    assert messages[-1].startswith("Ingested 1")


def test_explicit_pinned_complete_cache_has_no_network(tmp_path, monkeypatch):
    calls = fake_network(monkeypatch)
    ingest.ingest_medguide(tmp_path, REVISION)
    assert len(calls) == 3
    monkeypatch.setattr(ingest.requests, "get", lambda *args, **kwargs: pytest.fail("Cache must be offline"))
    result = ingest.ingest_medguide(tmp_path, REVISION)
    assert result["cache_hit"] is True
    assert len(ingest.load_documents(tmp_path)) == 1


def test_unpinned_cache_checks_latest_metadata(tmp_path, monkeypatch):
    calls = fake_network(monkeypatch)
    ingest.ingest_medguide(tmp_path)
    result = ingest.ingest_medguide(tmp_path)
    assert result["cache_hit"] is True
    assert len(calls) == 4


def test_changed_source_cache_is_repaired(tmp_path, monkeypatch):
    calls = fake_network(monkeypatch)
    ingest.ingest_medguide(tmp_path, REVISION)
    (tmp_path / "source.parquet").write_bytes(b"corrupt source")
    repaired = ingest.ingest_medguide(tmp_path, REVISION)
    assert repaired["cache_hit"] is False
    assert len(calls) == 6
    assert hashlib.sha256((tmp_path / "source.parquet").read_bytes()).hexdigest() == repaired["raw_sha256"]


def test_changed_normalized_records_are_not_loaded(tmp_path, monkeypatch):
    fake_network(monkeypatch)
    ingest.ingest_medguide(tmp_path, REVISION)
    with (tmp_path / "documents.jsonl").open("a") as file:
        file.write("{}\n")
    with pytest.raises(ingest.MedguideIngestionError, match="incomplete or changed"):
        ingest.load_documents(tmp_path)


def test_remote_checksum_mismatch_never_publishes_summary(tmp_path, monkeypatch):
    fake_network(monkeypatch, digest="0" * 64)
    with pytest.raises(ingest.MedguideIngestionError, match="checksum"):
        ingest.ingest_medguide(tmp_path, REVISION)
    assert not (tmp_path / "ingestion.json").exists()


@pytest.mark.parametrize("change,reason", [
    ({"answer": "B"}, "answer_mismatch"),
    ({"answer": "E"}, "answer_mismatch"),
    ({"answer": "correct"}, "invalid_answer_label"),
    ({"option_count": 3}, "option_count_mismatch"),
    ({"path": []}, "invalid_path"),
    ({"profile": "short"}, "short_profile"),
])
def test_bad_record_rejected_before_indexing(change, reason):
    with pytest.raises(ValueError, match=reason):
        ingest.normalize_record(row(**change), 0, REVISION)


def test_chunking_preserves_context_and_provenance_without_distractors():
    document = ingest.normalize_record(row(), 5, REVISION)
    chunks = ingest.chunk_documents([document])
    assert len(chunks) == 1
    chunk = chunks[0]
    assert document["profile"] in chunk["text"]
    assert document["answer_text"] in chunk["text"]
    assert "UNSAFE DISTRACTOR" not in chunk["text"]
    assert "RAW PROMPT" not in chunk["text"]
    assert chunk["record_id"] == document["id"]
    assert chunk["row_index"] == 5
    assert chunk["source_kind"] == "educational_mcqa"
    assert chunk["guideline_version"] is None
    assert chunk["version"] == f"Dataset revision {REVISION}"
    assert "not a clinical guideline" in chunk["text"]


def test_long_cases_split_with_overlap_and_complete_case_metadata():
    profile = "Clinical context is needed before interpreting the answer. " * 50
    document = ingest.normalize_record(row(profile=profile), 1, REVISION)
    chunks = ingest.chunk_documents([document], max_chars=900, overlap=120)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 900 for c in chunks)
    assert all("incomplete context" in c["text"] for c in chunks)
    assert all(c["profile"] == profile.strip() for c in chunks)
    assert all(c["answer_text"] == document["answer_text"] for c in chunks)
    assert all(c["chunk_count"] == len(chunks) for c in chunks)
    assert chunks[1]["char_start"] == chunks[0]["char_end"] - 120
    assert chunks == ingest.chunk_documents([document], max_chars=900, overlap=120)
    assert len({c["id"] for c in chunks}) == len(chunks)
    altered = ingest.chunk_documents([document], max_chars=1000, overlap=120)
    assert chunks[0]["id"] != altered[0]["id"]


def test_duplicates_and_wrong_source_kind_refused():
    document = ingest.normalize_record(row(), 1, REVISION)
    with pytest.raises(ingest.MedguideIngestionError, match="unique"):
        ingest.chunk_documents([document, document])
    altered = deepcopy(document)
    altered["source_kind"] = "clinical_guideline"
    with pytest.raises(ingest.MedguideIngestionError, match="educational"):
        ingest.chunk_documents([altered])


def test_invalid_revision_rejected_without_network(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest.requests, "get", lambda *args, **kwargs: pytest.fail("No network expected"))
    with pytest.raises(ingest.MedguideIngestionError, match="40-character"):
        ingest.ingest_medguide(tmp_path, "main")


def test_download_size_limit_checked_and_connection_closed(monkeypatch):
    response = FakeResponse(b"too much data")
    monkeypatch.setattr(ingest.requests, "get", lambda *args, **kwargs: response)
    with pytest.raises(ingest.MedguideIngestionError, match="size limit"):
        ingest._fetch("https://huggingface.co/known-source", 4)
    assert response.closed


def test_upstream_error_body_not_exposed(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("UPSTREAM_BODY_MUST_NOT_LEAK")
    monkeypatch.setattr(ingest.requests, "get", fail)
    with pytest.raises(ingest.MedguideIngestionError) as error:
        ingest.ingest_medguide(tmp_path)
    assert "UPSTREAM_BODY" not in str(error.value)
