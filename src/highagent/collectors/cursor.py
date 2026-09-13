from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from highagent.collectors.base import Collector
from highagent.collectors.sqlite_base import connect_readonly, table_exists
from highagent.models import Message

DEFAULT_DB = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Cursor"
    / "User"
    / "globalStorage"
    / "state.vscdb"
)

_BUBBLE_PREFIX = "bubbleId:"
_AUTH_PREFIX = "cursorAuth/"
_LEGACY_KEYS = ("aiService.prompts", "aiService.generations")
_BUBBLE_ROLES = {1: "user", 2: "assistant"}


class CursorCollector(Collector):
    """cursorDiskKV 的 bubbleId:* 消息（新格式），ItemTable aiService.* 兜底（旧格式）。

    cursorAuth/* 键含明文 accessToken，查询显式排除，绝不读取。
    子会话：composerHeaders 有 isSubagent 标记与 numSubComposers 计数，但没有
    可靠的父子关联字段（本机无真实子会话可考证），暂摊平处理，不做归并。
    """

    name = "cursor"

    def __init__(self, db_path: Path = None):
        super().__init__()
        self.db_path = db_path or DEFAULT_DB

    def _open(self) -> Optional[sqlite3.Connection]:
        if not self.db_path.is_file():
            return None
        try:
            return connect_readonly(self.db_path)
        except sqlite3.Error:
            return None

    def collect(self) -> List[Message]:
        conn = self._open()
        if conn is None:
            return []
        try:
            messages = self._collect_bubbles(conn)
            if not messages:
                messages = self._collect_legacy(conn)
            messages.sort(key=lambda m: m.timestamp)
            return messages
        finally:
            conn.close()

    def _collect_bubbles(self, conn: sqlite3.Connection) -> List[Message]:
        if not table_exists(conn, "cursorDiskKV"):
            return []
        headers = self._composer_headers(conn)
        messages: List[Message] = []
        for key, value in conn.execute(
            "SELECT key, value FROM cursorDiskKV WHERE key LIKE ? AND key NOT LIKE ?",
            (_BUBBLE_PREFIX + "%", _AUTH_PREFIX + "%"),
        ):
            parts = str(key).split(":")
            if len(parts) != 3:
                continue
            composer_id = parts[1]
            try:
                bubble = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            role = _BUBBLE_ROLES.get(bubble.get("type"))
            text = (bubble.get("text") or "").strip()
            if role is None or not text:
                continue
            header = headers.get(composer_id, {})
            timestamp = _ms_to_datetime(
                bubble.get("createdAt") or header.get("createdAt")
            )
            if timestamp is None:
                continue
            messages.append(
                Message(
                    role=role,
                    timestamp=timestamp,
                    content=text,
                    session_id=composer_id,
                    agent=self.name,
                    project="cursor",
                )
            )
        return messages

    def _composer_headers(self, conn: sqlite3.Connection) -> Dict[str, dict]:
        if not table_exists(conn, "composerHeaders"):
            return {}
        headers: Dict[str, dict] = {}
        for composer_id, created_at, value in conn.execute(
            "SELECT composerId, createdAt, value FROM composerHeaders"
        ):
            header = {"createdAt": created_at}
            try:
                header["name"] = (json.loads(value) or {}).get("name")
            except (json.JSONDecodeError, TypeError):
                pass
            headers[str(composer_id)] = header
        return headers

    def _collect_legacy(self, conn: sqlite3.Connection) -> List[Message]:
        if not table_exists(conn, "ItemTable"):
            return []
        fallback_ts = datetime.fromtimestamp(self.db_path.stat().st_mtime).astimezone()
        messages: List[Message] = []
        for key, role in (("aiService.prompts", "user"), ("aiService.generations", "assistant")):
            row = conn.execute(
                "SELECT value FROM ItemTable WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                continue
            try:
                entries = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                text = (entry.get("text") or "").strip()
                if not text:
                    continue
                messages.append(
                    Message(
                        role=role,
                        timestamp=_ms_to_datetime(entry.get("createdAt")) or fallback_ts,
                        content=text,
                        session_id="cursor-legacy",
                        agent=self.name,
                        project="cursor",
                    )
                )
        return messages

    def session_titles(self) -> Dict[str, str]:
        conn = self._open()
        if conn is None:
            return {}
        try:
            return {
                cid: h["name"]
                for cid, h in self._composer_headers(conn).items()
                if h.get("name")
            }
        finally:
            conn.close()


def _ms_to_datetime(raw) -> Optional[datetime]:
    if not isinstance(raw, (int, float)):
        return None
    return datetime.fromtimestamp(raw / 1000).astimezone()
