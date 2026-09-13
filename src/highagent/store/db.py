from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import List, Optional

from highagent.models import Message, SessionSummary

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "highagent" / "cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_summaries (
    session_id  TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    payload     TEXT NOT NULL,
    created_at  INTEGER NOT NULL,
    PRIMARY KEY (session_id, fingerprint)
);
CREATE TABLE IF NOT EXISTS report_runs (
    date       TEXT PRIMARY KEY,
    path       TEXT NOT NULL,
    sessions   INTEGER NOT NULL,
    messages   INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
"""

_SUMMARY_FIELDS = ("session_id", "project", "title", "tasks", "files", "problems", "todos")


def fingerprint(messages: List[Message]) -> str:
    digest = hashlib.sha256()
    digest.update(str(len(messages)).encode())
    for m in messages:
        digest.update(b"\x00")
        digest.update(m.role.encode())
        digest.update(b"\x00")
        digest.update(str(int(m.timestamp.timestamp() * 1000)).encode())
        digest.update(b"\x00")
        digest.update(m.content.encode("utf-8"))
    return digest.hexdigest()


def summary_to_payload(summary: SessionSummary) -> str:
    return json.dumps(
        {field: getattr(summary, field) for field in _SUMMARY_FIELDS},
        ensure_ascii=False,
    )


def summary_from_payload(payload: str) -> SessionSummary:
    data = json.loads(payload)
    return SessionSummary(**{field: data.get(field) for field in _SUMMARY_FIELDS})


class Store:
    def __init__(self, path: Path = DEFAULT_DB_PATH):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.executescript(_SCHEMA)
        return conn

    def get_session_summary(
        self, session_id: str, fp: str
    ) -> Optional[SessionSummary]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM session_summaries WHERE session_id = ? AND fingerprint = ?",
                (session_id, fp),
            ).fetchone()
        if row is None:
            return None
        try:
            return summary_from_payload(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def put_session_summary(self, summary: SessionSummary, fp: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM session_summaries WHERE session_id = ? AND fingerprint <> ?",
                (summary.session_id, fp),
            )
            conn.execute(
                "INSERT OR REPLACE INTO session_summaries (session_id, fingerprint, payload, created_at)"
                " VALUES (?, ?, ?, ?)",
                (summary.session_id, fp, summary_to_payload(summary), int(time.time())),
            )

    def has_run(self, target: date) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM report_runs WHERE date = ?", (target.isoformat(),)
            ).fetchone()
        return row is not None

    def record_run(self, target: date, path: Path, sessions: int, messages: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO report_runs (date, path, sessions, messages, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (target.isoformat(), str(path), sessions, messages, int(time.time())),
            )
