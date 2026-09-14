from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from highagent.collectors.base import Collector
from highagent.models import Message

KIMI_ROOT = Path.home() / ".kimi-code"
SESSION_INDEX = KIMI_ROOT / "session_index.jsonl"
SESSIONS_DIR = KIMI_ROOT / "sessions"

_ATTACHMENT_RE = re.compile(r"<attachment>.*?</attachment>", re.DOTALL)
_META_PREFIX_RE = re.compile(r"^<meta [^>]*/>\s*")


def default_root(home: Path = None) -> Path:
    # Windows 上同样在用户主目录下的同名 dotdir
    return (home or Path.home()) / ".kimi-code"


class KimiCodeCollector(Collector):
    name = "kimi_code"
    noise_origins = frozenset({"injection", "skill_activation", "task"})
    skip_session_prefixes: tuple = ()
    strip_attachments = False
    strip_meta_prefix = False

    def __init__(self, root: Path = None):
        super().__init__()
        self.root = root or default_root()
        self.index_path = self.root / "session_index.jsonl"
        self.sessions_dir = self.root / "sessions"

    def collect(self) -> List[Message]:
        messages: List[Message] = []
        for session_dir in self._session_dirs():
            messages.extend(self._parse_session(session_dir))
        messages.sort(key=lambda m: m.timestamp)
        return messages

    def session_titles(self) -> Dict[str, str]:
        titles: Dict[str, str] = {}
        for session_dir in self._session_dirs():
            if session_dir.name.startswith(self.skip_session_prefixes):
                continue
            state = session_dir / "state.json"
            if not state.is_file():
                continue
            try:
                data = json.loads(state.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            title = data.get("title")
            if isinstance(title, str) and title:
                titles[session_dir.name] = _META_PREFIX_RE.sub("", title).strip() or title
        return titles

    def _session_dirs(self) -> Iterator[Path]:
        seen = set()
        if self.index_path.exists():
            for line in self.index_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_dir = Path(entry.get("sessionDir", ""))
                if session_dir.is_dir() and session_dir not in seen:
                    seen.add(session_dir)
                    yield session_dir
        if self.sessions_dir.is_dir():
            for wire in sorted(self.sessions_dir.glob("wd_*/*/agents/*/wire.jsonl")):
                session_dir = wire.parents[2]
                if session_dir not in seen:
                    seen.add(session_dir)
                    yield session_dir

    def _parse_session(self, session_dir: Path) -> List[Message]:
        if session_dir.name.startswith(self.skip_session_prefixes):
            return []
        agents_dir = session_dir / "agents"
        if not agents_dir.is_dir():
            return []
        session_id = session_dir.name
        project = self._project_name(session_dir)
        messages: List[Message] = []
        for wire in sorted(agents_dir.glob("*/wire.jsonl")):
            agent_name = wire.parent.name
            agent_messages = self._parse_wire(wire, session_id, project)
            if agent_name != "main" and agent_messages:
                self.merges.append((agent_name, session_id))
            messages.extend(agent_messages)
        messages.sort(key=lambda m: m.timestamp)
        return messages

    def _parse_wire(self, wire: Path, session_id: str, project: str) -> List[Message]:
        messages: List[Message] = []
        seen_ids = set()
        for event in self._iter_events(wire):
            message = self._event_to_message(event, session_id, project, seen_ids)
            if message is not None:
                messages.append(message)
        return messages

    def _iter_events(self, wire: Path) -> Iterator[dict]:
        with wire.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def _event_to_message(
        self, event: dict, session_id: str, project: str, seen_ids: set
    ) -> Optional[Message]:
        event_type = event.get("type")
        role = None
        text = None
        dedupe_key = None
        if event_type == "context.append_message":
            body = event.get("message") or {}
            origin = (body.get("origin") or {}).get("kind", "user")
            if body.get("role") != "user" or origin in self.noise_origins:
                return None
            role = "user"
            text = _parts_text(body.get("content"))
            if self.strip_attachments:
                text = _ATTACHMENT_RE.sub("", text)
            if self.strip_meta_prefix:
                text = _META_PREFIX_RE.sub("", text.strip())
            dedupe_key = ("msg", body.get("id"))
        elif event_type == "context.append_loop_event":
            loop_event = event.get("event") or {}
            if loop_event.get("type") != "content.part":
                return None
            part = loop_event.get("part") or {}
            if part.get("type") != "text":
                return None
            role = "assistant"
            text = part.get("text") or ""
            dedupe_key = ("part", loop_event.get("uuid"))
        else:
            return None
        text = (text or "").strip()
        if not text:
            return None
        timestamp = _event_time(event)
        if timestamp is None:
            return None
        if dedupe_key[1] is not None:
            if dedupe_key in seen_ids:
                return None
            seen_ids.add(dedupe_key)
        return Message(
            role=role,
            timestamp=timestamp,
            content=text,
            session_id=session_id,
            agent=self.name,
            project=project,
        )

    def _project_name(self, session_dir: Path) -> str:
        state = session_dir / "state.json"
        if state.is_file():
            try:
                data = json.loads(state.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
            workdir = data.get("workDir") or data.get("cwd") or ""
            if workdir:
                return Path(workdir).name or workdir
        parent = session_dir.parent.name
        if parent.startswith("wd_"):
            return parent[3:].rsplit("_", 1)[0]
        return parent


def _parts_text(parts) -> str:
    if not isinstance(parts, list):
        return ""
    return "".join(
        part.get("text", "") for part in parts if isinstance(part, dict) and part.get("type") == "text"
    )


def _event_time(event: dict) -> Optional[datetime]:
    raw = event.get("time", event.get("created_at"))
    if not isinstance(raw, (int, float)):
        return None
    return datetime.fromtimestamp(raw / 1000).astimezone()
