from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterator, List

from highagent.collectors.base import Collector, parse_iso_timestamp
from highagent.models import Message

def default_root(home: Path = None) -> Path:
    # Windows 上同样在用户主目录下的同名 dotdir
    return (home or Path.home()) / ".codex"


_TEXT_BLOCK_TYPES = ("input_text", "output_text", "text")


class CodexCollector(Collector):
    """~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl + archived_sessions/；.zst 变体警告跳过。

    子会话：rollout 格式（session_meta + response_item 事件流）无父子会话概念，
    每个 rollout 文件即一个独立会话，无需归并。
    """

    name = "codex"

    def __init__(self, root: Path = None):
        super().__init__()
        self.root = root or default_root()

    def collect(self) -> List[Message]:
        messages: List[Message] = []
        for path in self._session_files():
            messages.extend(self._parse_file(path))
        messages.sort(key=lambda m: m.timestamp)
        return messages

    def _session_files(self) -> Iterator[Path]:
        if not self.root.is_dir():
            return
        for sub in ("sessions", "archived_sessions"):
            root = self.root / sub
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("rollout-*.jsonl*")):
                if path.suffix == ".zst":
                    print(
                        "警告：%s 为 zstd 压缩格式，当前不支持，已跳过。" % path,
                        file=sys.stderr,
                    )
                    continue
                if path.suffix == ".jsonl":
                    yield path

    def _parse_file(self, path: Path) -> List[Message]:
        session_id = path.stem
        project = self.name
        messages: List[Message] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("type")
            payload = event.get("payload") or {}
            if event_type == "session_meta":
                cwd = payload.get("cwd")
                if cwd:
                    project = Path(cwd).name or cwd
                session_id = payload.get("id") or session_id
                continue
            if event_type != "response_item":
                continue
            if payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            content = _content_text(payload.get("content"))
            timestamp = parse_iso_timestamp(event.get("timestamp"))
            if not content or timestamp is None:
                continue
            messages.append(
                Message(
                    role=role,
                    timestamp=timestamp,
                    content=content,
                    session_id=str(session_id),
                    agent=self.name,
                    project=project,
                )
            )
        return messages


def _content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            (block.get("text") or "").strip()
            for block in content
            if isinstance(block, dict) and block.get("type") in _TEXT_BLOCK_TYPES
        ]
        return "\n".join(p for p in parts if p)
    return ""
