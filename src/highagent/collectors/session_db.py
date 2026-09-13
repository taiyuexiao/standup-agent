from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from highagent.collectors.base import Collector
from highagent.collectors.sqlite_base import connect_readonly, table_exists
from highagent.models import Message

_REQUIRED_TABLES = ("session", "message", "part")


class SessionDbCollector(Collector):
    """zcode/opencode 共用：session/message/part 三表，data 列为 JSON 文本。

    父子会话归并：优先 session.parent_id；缺失时用 agents 目录结构兜底
    （agents_dir/sess_<父>/agent_<子>/ 对应子会话 sess_subagent_agent_<子>）。
    """

    db_path: Path
    agents_dir: Optional[Path] = None
    subagent_session_prefix = "sess_subagent_"

    def _open(self) -> Optional[sqlite3.Connection]:
        if not self.db_path.is_file():
            return None
        try:
            conn = connect_readonly(self.db_path)
        except sqlite3.Error:
            return None
        if not all(table_exists(conn, t) for t in _REQUIRED_TABLES):
            conn.close()
            return None
        return conn

    def _child_to_parent(self, sessions: Dict[str, dict]) -> Dict[str, str]:
        mapping = {
            sid: info["parent"] for sid, info in sessions.items() if info.get("parent")
        }
        if self.agents_dir is not None and self.agents_dir.is_dir():
            for parent_dir in sorted(self.agents_dir.iterdir()):
                if not parent_dir.is_dir():
                    continue
                for child_dir in sorted(parent_dir.iterdir()):
                    child_sid = self.subagent_session_prefix + child_dir.name
                    mapping.setdefault(child_sid, parent_dir.name)
        return mapping

    def collect(self) -> List[Message]:
        conn = self._open()
        if conn is None:
            return []
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(session)")}
            parent_col = "parent_id" if "parent_id" in columns else "NULL"
            sessions = {
                sid: {"directory": directory or "", "title": title or "", "parent": parent}
                for sid, directory, title, parent in conn.execute(
                    "SELECT id, directory, title, %s FROM session" % parent_col
                )
            }
            child_to_parent = self._child_to_parent(sessions)
            texts = self._message_texts(conn)
            messages: List[Message] = []
            seen_merges = set()
            for msg_id, session_id, time_created, data in conn.execute(
                "SELECT id, session_id, time_created, data FROM message ORDER BY time_created"
            ):
                role = self._role(data)
                if role not in ("user", "assistant"):
                    continue
                content = "\n".join(texts.get(msg_id, [])).strip()
                timestamp = self._timestamp(time_created, data)
                if not content or timestamp is None:
                    continue
                session_id = str(session_id)
                parent = child_to_parent.get(session_id)
                if parent is not None:
                    if session_id not in seen_merges:
                        seen_merges.add(session_id)
                        self.merges.append((session_id, parent))
                    session_id = parent
                directory = sessions.get(session_id, {}).get("directory", "")
                messages.append(
                    Message(
                        role=role,
                        timestamp=timestamp,
                        content=content,
                        session_id=session_id,
                        agent=self.name,
                        project=Path(directory).name or directory or self.name,
                    )
                )
            messages.sort(key=lambda m: m.timestamp)
            return messages
        finally:
            conn.close()

    def session_titles(self) -> Dict[str, str]:
        conn = self._open()
        if conn is None:
            return {}
        try:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(session)")}
            parent_col = "parent_id" if "parent_id" in columns else "NULL"
            rows = conn.execute(
                "SELECT id, title, %s FROM session" % parent_col
            ).fetchall()
            sessions = {sid: {"title": title, "parent": parent} for sid, title, parent in rows}
            child_to_parent = self._child_to_parent(sessions)
            titles: Dict[str, str] = {}
            for sid, info in sessions.items():
                if not child_to_parent.get(sid) and info["title"]:
                    titles[str(sid)] = info["title"]
            for sid, info in sessions.items():
                parent = child_to_parent.get(sid)
                if parent and info["title"] and parent not in titles:
                    titles[str(parent)] = info["title"]
            return titles
        finally:
            conn.close()

    def _message_texts(self, conn: sqlite3.Connection) -> Dict[str, List[str]]:
        texts: Dict[str, List[str]] = {}
        for message_id, data in conn.execute(
            "SELECT message_id, data FROM part ORDER BY time_created"
        ):
            try:
                part = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                continue
            if part.get("type") != "text":
                continue
            text = (part.get("text") or "").strip()
            if text:
                texts.setdefault(str(message_id), []).append(text)
        return texts

    @staticmethod
    def _role(data: str) -> Optional[str]:
        try:
            return json.loads(data).get("role")
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _timestamp(time_created, data: str) -> Optional[datetime]:
        raw = time_created
        if not isinstance(raw, (int, float)):
            try:
                raw = json.loads(data).get("time", {}).get("created")
            except (json.JSONDecodeError, TypeError, AttributeError):
                raw = None
        if not isinstance(raw, (int, float)):
            return None
        return datetime.fromtimestamp(raw / 1000).astimezone()
