"""Application wiring tests use fake retrieval; real model smoke checks are separate."""
import pytest
import json
from streamlit.testing.v1 import AppTest

import medguide_ui
from config import ROOT
from demo import replay_sample, sample_catalog, SAMPLES
from medguide import findings_search_query, read_pipeline_status
from treatment import generate_assessment


def test_mcqa_cannot_be_promoted_to_guideline_treatment():
    case = next(s for s in sample_catalog() if s.get("findings"))
    findings, _, _ = replay_sample((SAMPLES / case["filename"]).read_bytes())
    result = generate_assessment(findings, [{"source_kind": "educational_mcqa"}], None, "unused")
    assert result.pathways == []
    assert "research scenarios" in result.limitations[0]


def test_report_query_excludes_missing_information_and_unknown_fields():
    case = next(s for s in sample_catalog() if s.get("findings"))
    findings, _, _ = replay_sample((SAMPLES / case["filename"]).read_bytes())
    query = findings_search_query(findings)
    assert "ER:" in query
    assert "Not available in report" not in query
    assert "patient preferences" not in query


def test_missing_or_empty_vector_artifact_is_not_ready(tmp_path):
    folder = tmp_path / "index"
    folder.mkdir()
    pointer = folder / "index.json"
    pointer.write_text("{}", encoding="utf-8")
    assert not read_pipeline_status(tmp_path)["indexed"]
    pointer.write_text(json.dumps({"schema":1,"fingerprint":"a"*64,"sha256":"b"*64,"file":"generation-"+"a"*64+".npz"}),encoding="utf-8")
    assert not read_pipeline_status(tmp_path)["indexed"]
    (folder / ("generation-"+"a"*64+".npz")).touch()
    assert not read_pipeline_status(tmp_path)["indexed"]


def test_medguide_search_screen_uses_real_search_interface(monkeypatch):
    status = {"indexed": True, "ingested": True, "pipeline": {"documents": 1, "index": {"chunk_count": 1,"dimensions": 384},
               "ingestion": {"disease_counts": {"bre_1": 1}}}}
    monkeypatch.setattr(medguide_ui, "read_pipeline_status", lambda: status)
    requests = []
    def search(query, **kwargs):
        requests.append((query, kwargs))
        return [{"id":"MG-test","row_index":9,"disease":"bre_1","text":"Educational case context.",
                 "score":0.8,"profile":"Complete fictional scenario for test.","path":["Dataset branch"],
                 "answer_text":"Dataset test label","revision":"a"*40,"location":"train row 9"}]
    monkeypatch.setattr(medguide_ui, "find_related_cases", search)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="mode").set_value("MedGUIDE search").run()
    assert not app.exception
    next(b for b in app.button if b.label == "Run vector search").click().run()
    assert not app.exception
    assert requests[0][1]["top_k"] == 5
    assert requests[0][1]["disease"] is None
    assert app.session_state.medguide_search_result["matches"][0]["row_index"] == 9
    assert app.session_state.medguide_search_result["seconds"] > 0


def test_medguide_failure_clears_prior_search_result(monkeypatch):
    monkeypatch.setattr(medguide_ui, "read_pipeline_status", lambda: {"indexed":True,"pipeline":{}})
    def fail(*args, **kwargs):
        raise ValueError("The local test index is missing.")
    monkeypatch.setattr(medguide_ui, "find_related_cases", fail)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.radio(key="mode").set_value("MedGUIDE search").run()
    app.session_state.medguide_search_result = {"query":"old","matches":[],"seconds":1}
    next(b for b in app.button if b.label == "Run vector search").click().run()
    assert not app.exception
    assert "medguide_search_result" not in app.session_state
    assert any("test index is missing" in error.value for error in app.error)
