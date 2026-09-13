from __future__ import annotations

import json
from datetime import date
from typing import List

from highagent.models import (
    DailyReport,
    DetailItem,
    Message,
    ReportSection,
    SessionActivity,
    SessionSummary,
)
from highagent.sanitizer import SANITIZER_VERSION, SanitizeStats, sanitize_text
from highagent.store import Store, fingerprint
from highagent.summarizer import prompts
from highagent.summarizer.providers.base import LLMProvider

_PER_MESSAGE_CAP = 3000
_TRUNCATED = "\n…（内容过长，已截断）"
_DROPPED = "…（会话过长，已省略较早的 {n} 条助手回复）"

_ROLE_LABEL = {"user": "[用户]", "assistant": "[助手]"}


def build_transcript(
    messages: List[Message],
    max_chars: int,
    sanitize: bool = True,
    stats: SanitizeStats = None,
) -> str:
    def prepare(content: str) -> str:
        if sanitize:
            content = sanitize_text(content, stats)
        if len(content) > _PER_MESSAGE_CAP:
            content = content[:_PER_MESSAGE_CAP] + _TRUNCATED
        return content

    capped = [
        Message(
            role=m.role,
            timestamp=m.timestamp,
            content=prepare(m.content),
            session_id=m.session_id,
            agent=m.agent,
            project=m.project,
        )
        for m in messages
    ]

    def render(items: List[Message]) -> str:
        lines = []
        for m in items:
            label = _ROLE_LABEL.get(m.role, "[%s]" % m.role)
            lines.append("%s %s" % (label, m.content))
        return "\n\n".join(lines)

    kept = list(capped)
    dropped = 0
    while len(render(kept)) > max_chars:
        for index, m in enumerate(kept):
            if m.role == "assistant":
                kept.pop(index)
                dropped += 1
                break
        else:
            kept = [kept[-1]] if kept else []
            dropped += len(capped) - 1
            break
    transcript = render(kept)
    if dropped and kept:
        transcript = _DROPPED.format(n=dropped) + "\n\n" + transcript
    return transcript


def _str_list(value) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def summarize_session(
    provider: LLMProvider,
    activity: SessionActivity,
    max_chars: int,
    store: Store = None,
    sanitize: bool = True,
    stats: SanitizeStats = None,
) -> tuple:
    """返回 (SessionSummary, cache_hit)。传入 store 时按 session id + 内容指纹查缓存。"""
    fp = fingerprint(activity.messages)
    if sanitize:
        fp = fp + ":" + SANITIZER_VERSION
    if store is not None:
        cached = store.get_session_summary(activity.session_id, fp)
        if cached is not None:
            return cached, True
    transcript = build_transcript(activity.messages, max_chars, sanitize, stats)
    user = prompts.SESSION_USER_TEMPLATE.format(
        project=activity.project,
        title=activity.title or activity.session_id,
        transcript=transcript,
    )
    data = provider.complete_json(prompts.SESSION_SYSTEM, user)
    summary = SessionSummary(
        session_id=activity.session_id,
        project=activity.project,
        title=activity.title,
        tasks=_str_list(data.get("tasks")),
        files=_str_list(data.get("files")),
        problems=_str_list(data.get("problems")),
        todos=_str_list(data.get("todos")),
    )
    if store is not None:
        store.put_session_summary(summary, fp)
    return summary, False


def parse_detail_items(value) -> List[DetailItem]:
    items: List[DetailItem] = []
    if not isinstance(value, list):
        return items
    for entry in value:
        if isinstance(entry, dict):
            text = str(entry.get("text", "")).strip()
            if text:
                items.append(DetailItem(category=str(entry.get("category", "")).strip() or "其他", text=text))
        elif str(entry).strip():
            items.append(DetailItem(category="其他", text=str(entry).strip()))
    return items


def parse_section(value) -> ReportSection:
    if isinstance(value, dict):
        return ReportSection(
            summary=parse_detail_items(value.get("summary")),
            details=parse_detail_items(value.get("details")),
        )
    return ReportSection(details=parse_detail_items(value))


def summarize_day(
    provider: LLMProvider, target: date, summaries: List[SessionSummary]
) -> DailyReport:
    payload = [
        {
            "project": s.project,
            "title": s.title,
            "tasks": s.tasks,
            "files": s.files,
            "problems": s.problems,
            "todos": s.todos,
        }
        for s in summaries
    ]
    user = prompts.DAY_USER_TEMPLATE.format(
        date=target.isoformat(),
        summaries=json.dumps(payload, ensure_ascii=False, indent=2),
    )
    data = provider.complete_json(prompts.DAY_SYSTEM, user)
    return DailyReport(
        date=target.isoformat(),
        today=parse_section(data.get("today")),
        tomorrow=parse_section(data.get("tomorrow")),
        problems=parse_section(data.get("problems")),
    )
