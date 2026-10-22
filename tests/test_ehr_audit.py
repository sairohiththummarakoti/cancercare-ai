"""Review history must retain the actual text that an oncologist approved."""
import json
import sqlite3

import pytest

from backend.store import Store


ACTOR = {"reviewer": "Dr. E. Morgan (demo)", "role": "oncologist"}


def draft():
    return {
        "assessment_id": "audit-assessment", "patient_id": "DEMO-00248", "revision": 1,
        "status": "pending_clinician_review", "created_at": "2026-10-21T12:00:00Z",
        "clinical_summary": "Original report-grounded summary. Stage remains unknown.",
        "clinician_edit": None, "review_notes": "", "contradictions": [],
        "audit": [{"action": "created", "reviewer": ACTOR["reviewer"], "role": ACTOR["role"],
                   "at": "2026-10-21T12:00:00Z", "notes": "Created", "revision": 1}],
    }


def test_approved_documentation_survives_later_edit_and_stale_review(tmp_path):
    store = Store(tmp_path / "reviews.sqlite3")
    original = draft()
    store.save(original)
    assert original["revision_history"][0]["clinical_summary"] == original["clinical_summary"]
    store.review("audit-assessment", "DEMO-00248", 1, "edit", "Clarified source scope", "First clinician clarification", ACTOR)
    approved = store.review("audit-assessment", "DEMO-00248", 2, "approve", "Reviewed the first edit", None, ACTOR)
    reopened = store.review("audit-assessment", "DEMO-00248", 3, "edit", "Reopened to incorporate context", "Second clinician clarification", ACTOR)

    assert approved["status"] == "approved_for_documentation"
    assert reopened["status"] == "edited"
    assert reopened["clinical_summary"] == original["clinical_summary"]
    assert reopened["clinician_edit"] == "Second clinician clarification"
    assert [entry["revision"] for entry in reopened["revision_history"]] == [1, 2, 3, 4]
    assert reopened["revision_history"][1]["clinician_edit"] == "First clinician clarification"
    assert reopened["revision_history"][2]["status"] == "approved_for_documentation"
    assert reopened["revision_history"][2]["clinician_edit"] == "First clinician clarification"
    assert reopened["revision_history"][2]["review_notes"] == "Reviewed the first edit"
    assert reopened["revision_history"][2]["at"] == reopened["audit"][2]["at"]
    with pytest.raises(ValueError, match="changed since"):
        store.review("audit-assessment", "DEMO-00248", 2, "approve", "Stale screen", None, ACTOR)
    assert store.get("audit-assessment", "DEMO-00248") == reopened

    # Reload from a new store to verify durable historical text, not only a
    # Python object retained by this test.
    restored = Store(store.db_path).get("audit-assessment", "DEMO-00248")
    assert restored["revision_history"] == reopened["revision_history"]
    assert restored["audit"] == reopened["audit"]


def test_legacy_record_preserves_current_approved_text_before_edit(tmp_path):
    store = Store(tmp_path / "reviews.sqlite3")
    legacy = draft()
    legacy.update(revision=3, status="approved_for_documentation", clinician_edit="Previously approved legacy documentation")
    with store.connection() as connection:
        connection.execute("INSERT INTO assessments VALUES (?,?,?,?)", (legacy["assessment_id"], legacy["patient_id"], 3, json.dumps(legacy)))
    edited = store.review("audit-assessment", "DEMO-00248", 3, "edit", "Reopened", "New documentation", ACTOR)
    assert [entry["revision"] for entry in edited["revision_history"]] == [3, 4]
    assert edited["revision_history"][0]["status"] == "approved_for_documentation"
    assert edited["revision_history"][0]["clinician_edit"] == "Previously approved legacy documentation"
    assert edited["revision_history"][1]["clinician_edit"] == "New documentation"


def test_connection_closes_after_commit_and_rollback(tmp_path):
    store = Store(tmp_path / "reviews.sqlite3")
    with store.connection() as connection:
        connection.execute("CREATE TABLE lifecycle (value TEXT)")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")
    with pytest.raises(RuntimeError, match="rollback"):
        with store.connection() as failed_connection:
            failed_connection.execute("INSERT INTO lifecycle VALUES ('must not persist')")
            raise RuntimeError("rollback")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        failed_connection.execute("SELECT 1")
    with store.connection() as check:
        assert check.execute("SELECT COUNT(*) FROM lifecycle").fetchone()[0] == 0
