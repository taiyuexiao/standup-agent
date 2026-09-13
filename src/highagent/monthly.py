from __future__ import annotations

import calendar
from datetime import date
from pathlib import Path
from typing import List, Tuple

from highagent.models import MonthlyReport
from highagent.sanitizer import SanitizeStats, sanitize_text
from highagent.summarizer import prompts
from highagent.summarizer.core import parse_section
from highagent.summarizer.providers.base import LLMProvider
from highagent.weekly import collect_reports_in_range


def month_bounds(day: date) -> Tuple[date, date]:
    """返回 day 所在月的 (1 日, 月末日)。"""
    first = day.replace(day=1)
    last = day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return first, last


def month_label(day: date) -> str:
    return "%d-%02d" % (day.year, day.month)


def monthly_filename(day: date) -> str:
    return "monthly-%s.md" % month_label(day)


def collect_monthly_reports(
    reports_dir: Path, first: date
) -> Tuple[List[Tuple[date, str]], List[date]]:
    days = calendar.monthrange(first.year, first.month)[1]
    return collect_reports_in_range(reports_dir, first, days)


def summarize_month(
    provider: LLMProvider,
    first: date,
    found: List[Tuple[date, str]],
    sanitize: bool = True,
    stats: SanitizeStats = None,
) -> MonthlyReport:
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    parts = []
    for day, text in found:
        if sanitize:
            text = sanitize_text(text, stats)
        parts.append("### %s\n\n%s" % (day.isoformat(), text))
    user = prompts.MONTH_USER_TEMPLATE.format(
        month_label=month_label(first),
        first_day=first.isoformat(),
        last_day=last.isoformat(),
        count=len(found),
        reports="\n\n---\n\n".join(parts),
    )
    data = provider.complete_json(prompts.MONTH_SYSTEM, user)
    return MonthlyReport(
        month_label=month_label(first),
        first_day=first.isoformat(),
        last_day=last.isoformat(),
        overview=parse_section(data.get("overview")),
        next_month=parse_section(data.get("next_month")),
        problems=parse_section(data.get("problems")),
    )
