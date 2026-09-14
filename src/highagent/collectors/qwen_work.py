from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from highagent.collectors.base import Collector
from highagent.collectors.sqlite_base import connect_readonly, table_exists
from highagent.models import Message


def default_db_path(platform: str = None, environ=None, home: Path = None) -> Path:
    """QwenWorkCN agents.db 路径（仅 macOS 路径有实据，其余平台为推断）。"""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = home or Path.home()
    if platform == "win32":
        base = environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / "QwenWorkCN" / "data" / "agents.db"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "QwenWorkCN" / "data" / "agents.db"
    return home / ".config" / "QwenWorkCN" / "data" / "agents.db"


class QwenWorkCollector(Collector):
    """~/Library/Application Support/QwenWorkCN/data/agents.db（drizzle ORM，SQLite+WAL）。

    只 SELECT chats/messages/projects 三表；google_oauth_tokens、mcp_oauth_tokens、
    ms365_auth_states、auth.dat 等凭证表/文件绝不触碰。
    时间戳 created_at 按毫秒 epoch 实现（本机零数据未实测，待验证）。
    """

    name = "qwen_work"

    def __init__(self, db_path: Path = None):
        super().__init__()
        self.db_path = db_path or default_db_path()

    def _open(self) -> Optional[sqlite3.Connection]:
        if not self.db_path.is_file():
            return None
        try:
            conn = connect_readonly(self.db_path)
        except sqlite3.Error:
            return None
        if not all(table_exists(conn, t) for t in ("chats", "messages")):
            conn.close()
            return None
        return conn

    def collect(self) -> List[Message]:
        conn = self._open()
        if conn is None:
            return []
        try:
            chats = self._chats(conn)
            projects = self._projects(conn)
            messages: List[Message] = []
            for chat_id, sequence, role, parts, searchable_text, created_at in conn.execute(
                "SELECT chat_id, sequence, role, parts, searchable_text, created_at"
                " FROM messages ORDER BY chat_id, sequence"
            ):
                chat = chats.get(str(chat_id))
                if chat is None:
                    continue
                if role not in ("user", "assistant"):
                    continue
                content = (searchable_text or "").strip() or _parts_text(parts)
                timestamp = _ms_to_datetime(created_at)
                if not content or timestamp is None:
                    continue
                project = projects.get(chat.get("project_id"), "") or self.name
                messages.append(
                    Message(
                        role=role,
                        timestamp=timestamp,
                        content=content,
                        session_id=str(chat_id),
                        agent=self.name,
                        project=Path(project).name or project,
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
            return {
                sid: chat["name"]
                for sid, chat in self._chats(conn).items()
                if chat.get("name")
            }
        finally:
            conn.close()

    @staticmethod
    def _chats(conn: sqlite3.Connection) -> Dict[str, dict]:
        chats: Dict[str, dict] = {}
        for cid, name, project_id, archived_at, deleted_at in conn.execute(
            "SELECT id, name, project_id, archived_at, deleted_at FROM chats"
        ):
            if archived_at or deleted_at:
                continue
            chats[str(cid)] = {"name": name or "", "project_id": project_id}
        return chats

    @staticmethod
    def _projects(conn: sqlite3.Connection) -> Dict[str, str]:
        if not table_exists(conn, "projects"):
            return {}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(projects)")}
        name_col = "path" if "path" in columns else ("name" if "name" in columns else None)
        if name_col is None:
            return {}
        return {
            str(pid): value or ""
            for pid, value in conn.execute("SELECT id, %s FROM projects" % name_col)
        }


def _parts_text(parts) -> str:
    try:
        blocks = json.loads(parts)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(blocks, list):
        return ""
    texts = [
        (block.get("text") or "").strip()
        for block in blocks
        if isinstance(block, dict) and block.get("text")
    ]
    return "\n".join(t for t in texts if t)


def _ms_to_datetime(raw) -> Optional[datetime]:
    if not isinstance(raw, (int, float)):
        return None
    return datetime.fromtimestamp(raw / 1000).astimezone()
