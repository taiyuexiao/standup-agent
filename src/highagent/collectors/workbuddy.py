from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from highagent.collectors.base import Collector
from highagent.collectors.sqlite_base import connect_readonly, table_exists
from highagent.models import Message

_USER_QUERY_RE = re.compile(r"<user_query>(.*?)</user_query>", re.DOTALL)
_TEXT_BLOCK_TYPES = ("input_text", "output_text")


def default_root(home: Path = None) -> Path:
    # 旧版残留目录 ~/.workbuddy-ai（0 数据）不要碰
    return (home or Path.home()) / ".workbuddy"


class WorkbuddyCollector(Collector):
    """~/.workbuddy/projects/<工作区>/<session-id>.jsonl + workbuddy.db 取标题/删除标记。

    只读 projects/**/*.jsonl 与 workbuddy.db；security/、settings.json 等含凭证不碰。
    """

    name = "workbuddy"

    def __init__(self, root: Path = None):
        super().__init__()
        self.root = root or default_root()

    def collect(self) -> List[Message]:
        titles, deleted = self._session_meta()
        messages: List[Message] = []
        for path in self._session_files():
            session_id = path.stem
            if session_id in deleted:
                continue
            messages.extend(self._parse_file(path))
        messages.sort(key=lambda m: m.timestamp)
        return messages

    def session_titles(self) -> Dict[str, str]:
        titles, deleted = self._session_meta()
        return {sid: t for sid, t in titles.items() if sid not in deleted}

    def _session_files(self) -> Iterator[Path]:
        projects = self.root / "projects"
        if not projects.is_dir():
            return
        yield from sorted(projects.glob("*/*.jsonl"))

    def _session_meta(self):
        """返回 ({session_id: title}, {deleted_session_id})。库缺失时均为空。"""
        db = self.root / "workbuddy.db"
        titles: Dict[str, str] = {}
        deleted = set()
        if not db.is_file():
            return titles, deleted
        try:
            conn = connect_readonly(db)
        except sqlite3.Error:
            return titles, deleted
        try:
            if not table_exists(conn, "sessions"):
                return titles, deleted
            for sid, title, custom_title, deleted_at in conn.execute(
                "SELECT id, title, custom_title, deleted_at FROM sessions"
            ):
                sid = str(sid)
                if deleted_at:
                    deleted.add(sid)
                    continue
                name = custom_title or title
                if name:
                    titles[sid] = name
            return titles, deleted
        finally:
            conn.close()

    def _parse_file(self, path: Path) -> List[Message]:
        session_id = path.stem
        project = path.parent.name
        messages: List[Message] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "message":
                continue
            role = event.get("role")
            if role not in ("user", "assistant"):
                continue
            timestamp = _ms_to_datetime(event.get("timestamp"))
            if timestamp is None:
                continue
            cwd = event.get("cwd")
            if cwd:
                project = Path(cwd).name or project
            content = _extract_text(role, event.get("content"))
            if not content:
                continue
            messages.append(
                Message(
                    role=role,
                    timestamp=timestamp,
                    content=content,
                    session_id=session_id,
                    agent=self.name,
                    project=project,
                )
            )
        return messages


def _extract_text(role: str, content) -> str:
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") not in _TEXT_BLOCK_TYPES:
            continue
        text = (block.get("text") or "").strip()
        if not text:
            continue
        if role == "user":
            extracted = _user_text(text)
            if extracted:
                parts.append(extracted)
        else:
            parts.append(text)
    return "\n".join(parts)


def _user_text(text: str) -> str:
    match = _USER_QUERY_RE.search(text)
    if match:
        return match.group(1).strip()
    if text.startswith("<system-reminder"):
        return ""
    return text


def _ms_to_datetime(raw) -> Optional[datetime]:
    if not isinstance(raw, (int, float)):
        return None
    return datetime.fromtimestamp(raw / 1000).astimezone()
