from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List

from highagent.collectors.base import Collector, parse_iso_timestamp
from highagent.models import Message

DEFAULT_ROOT = Path.home() / ".claude" / "projects"

_TEXT_BLOCK_TYPES = ("text", "input_text", "output_text")


class ClaudeCodeCollector(Collector):
    """~/.claude/projects/<路径转义目录>/<session-uuid>.jsonl，每行一个事件。

    子会话：Task 工具子转录以 isSidechain=true 消息内联在同一会话 jsonl 里，
    本 collector 不按 isSidechain 过滤，子代理对话天然并入所属会话，无需归并。
    """

    name = "claude_code"

    def __init__(self, root: Path = None):
        super().__init__()
        self.root = root or DEFAULT_ROOT

    def collect(self) -> List[Message]:
        messages: List[Message] = []
        for path in self._session_files():
            messages.extend(self._parse_file(path))
        messages.sort(key=lambda m: m.timestamp)
        return messages

    def _session_files(self) -> Iterator[Path]:
        if not self.root.is_dir():
            return
        yield from sorted(self.root.glob("*/*.jsonl"))

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
            role = event.get("type")
            if role not in ("user", "assistant"):
                continue
            content = _content_text((event.get("message") or {}).get("content"))
            timestamp = parse_iso_timestamp(event.get("timestamp"))
            if not content or timestamp is None:
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
