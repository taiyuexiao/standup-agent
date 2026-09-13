from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

from highagent.models import WeeklyReport
from highagent.sanitizer import SanitizeStats, sanitize_text
from highagent.summarizer import prompts
from highagent.summarizer.core import parse_section
from highagent.summarizer.providers.base import LLMProvider


def week_bounds(day: date) -> Tuple[date, date]:
    """ISO 周（周一为起点）：返回 day 所在周的 (周一, 周日)。"""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def week_label(day: date) -> str:
    iso_year, iso_week, _ = day.isocalendar()
    return "%d-W%02d" % (iso_year, iso_week)


def weekly_filename(day: date) -> str:
    return "weekly-%s.md" % week_label(day)


def collect_reports_in_range(
    reports_dir: Path, start: date, days: int
) -> Tuple[List[Tuple[date, str]], List[date]]:
    """收集 start 起 days 天内已有的日报；返回 (found, missing)，found 按日期升序。"""
    found: List[Tuple[date, str]] = []
    missing: List[date] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        path = reports_dir / ("%s.md" % day.isoformat())
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                found.append((day, text))
            else:
                missing.append(day)
        else:
            missing.append(day)
    return found, missing


def collect_daily_reports(
    reports_dir: Path, monday: date
) -> Tuple[List[Tuple[date, str]], List[date]]:
    """收集周一到周日已有的日报；返回 (found, missing)，found 按日期升序。"""
    return collect_reports_in_range(reports_dir, monday, 7)


def summarize_week(
    provider: LLMProvider,
    monday: date,
    found: List[Tuple[date, str]],
    sanitize: bool = True,
    stats: SanitizeStats = None,
) -> WeeklyReport:
    sunday = monday + timedelta(days=6)
    parts = []
    for day, text in found:
        if sanitize:
            text = sanitize_text(text, stats)
        parts.append("### %s\n\n%s" % (day.isoformat(), text))
    user = prompts.WEEK_USER_TEMPLATE.format(
        monday=monday.isoformat(),
        sunday=sunday.isoformat(),
        week_label=week_label(monday),
        count=len(found),
        reports="\n\n---\n\n".join(parts),
    )
    data = provider.complete_json(prompts.WEEK_SYSTEM, user)
    return WeeklyReport(
        week_label=week_label(monday),
        monday=monday.isoformat(),
        sunday=sunday.isoformat(),
        overview=parse_section(data.get("overview")),
        next_week=parse_section(data.get("next_week")),
        problems=parse_section(data.get("problems")),
    )
