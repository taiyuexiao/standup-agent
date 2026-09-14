from __future__ import annotations

from typing import Dict

from highagent.collectors.base import Collector
from highagent.collectors.claude_code import ClaudeCodeCollector
from highagent.collectors.codex import CodexCollector
from highagent.collectors.cursor import CursorCollector
from highagent.collectors.kimi_code import KimiCodeCollector
from highagent.collectors.kimi_work import KimiWorkCollector
from highagent.collectors.opencode import OpencodeCollector
from highagent.collectors.qwen_work import QwenWorkCollector
from highagent.collectors.workbuddy import WorkbuddyCollector
from highagent.collectors.zcode import ZcodeCollector

_REGISTRY = {
    KimiCodeCollector.name: KimiCodeCollector,
    ZcodeCollector.name: ZcodeCollector,
    OpencodeCollector.name: OpencodeCollector,
    CursorCollector.name: CursorCollector,
    ClaudeCodeCollector.name: ClaudeCodeCollector,
    CodexCollector.name: CodexCollector,
    WorkbuddyCollector.name: WorkbuddyCollector,
    QwenWorkCollector.name: QwenWorkCollector,
    KimiWorkCollector.name: KimiWorkCollector,
}


def available_agents() -> list:
    return sorted(_REGISTRY)


def has_collector(name: str) -> bool:
    return name in _REGISTRY


def get_collector(name: str) -> Collector:
    if name not in _REGISTRY:
        raise ValueError(
            "未知的 agent: %s（当前支持: %s）" % (name, ", ".join(available_agents()))
        )
    return _REGISTRY[name]()
