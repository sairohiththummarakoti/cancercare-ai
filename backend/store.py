"""Bounded ephemeral upload/session storage and a synthetic-only review store."""
from __future__ import annotations

import copy
from contextlib import contextmanager
import json
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.uploads = {}
        self.sessions = {}
        with self.connection() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS assessments (id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL)")

    @contextmanager
    def connection(self):
        """Commit or roll back each operation, then release its SQLite handle."""
        connection = sqlite3.connect(self.db_path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _snapshot(assessment: dict, at: str | None = None) -> dict:
        """Capture documentation as it existed at an exact review revision.

        Generated findings, evidence and pathways are immutable on the parent
        assessment. Both the original summary and every clinician text revision
        are retained here so an older approval can be reconstructed.
        """
        last_event = assessment.get("audit", [])[-1:]
        return copy.deepcopy({
            "revision": assessment["revision"],
            "status": assessment["status"],
            "clinical_summary": assessment["clinical_summary"],
            "clinician_edit": assessment.get("clinician_edit"),
            "review_notes": assessment.get("review_notes", ""),
            "at": at or (last_event[0].get("at") if last_event else None) or assessment.get("created_at") or timestamp(),
        })

    def session(self, role: str) -> dict:
        with self.lock:
            now = time.time()
            self.sessions = {key: value for key, value in self.sessions.items() if value["expires"] > now}
            if len(self.sessions) >= 100:
                del self.sessions[next(iter(self.sessions))]
            token = secrets.token_urlsafe(32)
            entry = {"token": token, "role": role, "reviewer": "Dr. E. Morgan (demo)" if role == "oncologist" else "Sam Patel, Navigator (demo)",
                     "expires": now + 8 * 3600, "expires_at": datetime.fromtimestamp(now + 8 * 3600, timezone.utc).isoformat(), "demo": True}
            self.sessions[token] = entry
            return {key: value for key, value in entry.items() if key != "expires"}

    def actor(self, token: str) -> dict | None:
        with self.lock:
            session = self.sessions.get(token)
            return copy.deepcopy(session) if session and session["expires"] > time.time() else None

    def add_upload(self, item: dict) -> None:
        with self.lock:
            now = time.time()
            self.uploads = {key: value for key, value in self.uploads.items() if value["expires"] > now}
            while self.uploads and (len(self.uploads) >= 20 or sum(len(row["pdf"]) for row in self.uploads.values()) + len(item["pdf"]) > 80 * 1024 * 1024):
                del self.uploads[next(iter(self.uploads))]
            self.uploads[item["upload_id"]] = dict(item, expires=now + 3600)

    def purge_expired(self) -> None:
        with self.lock:
            now = time.time()
            self.uploads = {key: value for key, value in self.uploads.items() if value["expires"] > now}
            self.sessions = {key: value for key, value in self.sessions.items() if value["expires"] > now}

    def upload(self, upload_id: str, patient_id: str) -> dict | None:
        with self.lock:
            item = self.uploads.get(upload_id)
            if not item or item["patient_id"] != patient_id or item["expires"] <= time.time():
                return None
            return copy.deepcopy(item)

    def save(self, assessment: dict) -> None:
        # Initial generation is a reviewable revision too, even before edits.
        assessment["revision_history"] = [self._snapshot(assessment)]
        with self.connection() as connection:
            connection.execute("INSERT INTO assessments VALUES (?,?,?,?)", (assessment["assessment_id"], assessment["patient_id"], assessment["revision"], json.dumps(assessment)))

    def get(self, assessment_id: str, patient_id: str) -> dict | None:
        with self.connection() as connection:
            row = connection.execute("SELECT payload FROM assessments WHERE id=? AND patient_id=?", (assessment_id, patient_id)).fetchone()
            return json.loads(row[0]) if row else None

    def history(self, patient_id: str) -> list[dict]:
        with self.connection() as connection:
            rows = connection.execute("SELECT payload FROM assessments WHERE patient_id=? ORDER BY rowid DESC LIMIT 50", (patient_id,)).fetchall()
            return [json.loads(row[0]) for row in rows]

    def review(self, assessment_id: str, patient_id: str, expected_revision: int, action: str, notes: str, edited_text: str | None, actor: dict) -> dict:
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload FROM assessments WHERE id=? AND patient_id=?", (assessment_id, patient_id)).fetchone()
            if not row:
                raise KeyError("Assessment not found for the selected patient.")
            item = json.loads(row[0])
            if item["revision"] != expected_revision:
                raise ValueError("This draft changed since it was loaded. Refresh it before reviewing.")
            if action == "approve" and item["status"] in {"approved_for_documentation", "rejected"}:
                raise ValueError("This draft is already finalized. Edit it to create a new review revision first.")
            if action == "reject" and item["status"] in {"approved_for_documentation", "rejected"}:
                raise ValueError("This draft is already finalized. Edit it before changing the review decision.")
            if action == "approve" and item["contradictions"] and not notes.strip():
                raise ValueError("Document how the conflicting chart and report findings were reconciled before approving.")
            # Older local demo records did not retain text snapshots. Preserve
            # their current state before the first subsequent mutation; prior
            # lost edits cannot be reconstructed and are never fabricated.
            if not item.get("revision_history"):
                item["revision_history"] = [self._snapshot(item)]
            item["revision"] += 1
            item["status"] = {"approve": "approved_for_documentation", "reject": "rejected", "edit": "edited"}[action]
            item["review_notes"] = notes
            if action == "edit":
                item["clinician_edit"] = edited_text
            reviewed_at = timestamp()
            item["audit"].append({"action": action, "reviewer": actor["reviewer"], "role": actor["role"], "at": reviewed_at, "notes": notes, "revision": item["revision"]})
            item["revision_history"].append(self._snapshot(item, reviewed_at))
            connection.execute("UPDATE assessments SET revision=?,payload=? WHERE id=? AND patient_id=?", (item["revision"], json.dumps(item), assessment_id, patient_id))
            return item
