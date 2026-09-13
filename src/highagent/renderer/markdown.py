from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List, Tuple

from highagent.models import DailyReport, DetailItem, MonthlyReport, ReportSection, WeeklyReport

_EMPTY = "（无）"


def _group_by_category(items: List[DetailItem]) -> List[Tuple[str, List[DetailItem]]]:
    groups: List[Tuple[str, List[DetailItem]]] = []
    index = {}
    for item in items:
        category = item.category or "其他"
        if category not in index:
            index[category] = []
            groups.append((category, index[category]))
        index[category].append(item)
    return groups


def _render_section(title: str, section: ReportSection) -> str:
    lines = ["## %s" % title, ""]
    if section.empty:
        lines.append(_EMPTY)
        return "\n".join(lines)
    lines.append("### 总结")
    lines.append("")
    if section.summary:
        lines.extend("- **%s**：%s" % (item.category, item.text) for item in section.summary)
    else:
        lines.append(_EMPTY)
    lines.append("")
    lines.append("### 细节")
    lines.append("")
    if section.details:
        for category, items in _group_by_category(section.details):
            lines.append("**%s**" % category)
            lines.extend("- %s" % item.text for item in items)
            lines.append("")
        lines.pop()
    else:
        lines.append(_EMPTY)
    return "\n".join(lines)


def render_markdown(report: DailyReport) -> str:
    parts = [
        "# 日报 %s" % report.date,
        "",
        _render_section("今日工作/学习任务", report.today),
        "",
        _render_section("明日工作/学习计划", report.tomorrow),
        "",
        _render_section("遇到的问题", report.problems),
        "",
    ]
    return "\n".join(parts)


def write_report(report: DailyReport, output_dir: Path, output: str = None) -> Path:
    if output:
        path = Path(output).expanduser()
    else:
        path = output_dir / ("%s.md" % report.date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path


def render_weekly_markdown(
    report: WeeklyReport, included: List[date], missing: List[date]
) -> str:
    header = [
        "# 周报 %s（%s ~ %s）" % (report.week_label, report.monday, report.sunday),
        "",
        "聚合日报：%s" % "、".join(d.isoformat() for d in included),
    ]
    if missing:
        header.append("无日报跳过：%s" % "、".join(d.isoformat() for d in missing))
    parts = header + [
        "",
        _render_section("本周工作/学习概览", report.overview),
        "",
        _render_section("下周计划", report.next_week),
        "",
        _render_section("本周遇到的问题", report.problems),
        "",
    ]
    return "\n".join(parts)


def write_weekly_report(
    report: WeeklyReport,
    output_dir: Path,
    included: List[date],
    missing: List[date],
) -> Path:
    path = output_dir / ("weekly-%s.md" % report.week_label)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_weekly_markdown(report, included, missing), encoding="utf-8")
    return path


def render_monthly_markdown(
    report: MonthlyReport, included: List[date], missing_count: int
) -> str:
    header = [
        "# 月报 %s（%s ~ %s）" % (report.month_label, report.first_day, report.last_day),
        "",
        "聚合日报：%d 天（%s）"
        % (len(included), "、".join(d.isoformat() for d in included)),
    ]
    if missing_count:
        header.append("无日报跳过：%d 天" % missing_count)
    parts = header + [
        "",
        _render_section("本月工作/学习概览", report.overview),
        "",
        _render_section("下月计划", report.next_month),
        "",
        _render_section("本月遇到的问题", report.problems),
        "",
    ]
    return "\n".join(parts)


def write_monthly_report(
    report: MonthlyReport,
    output_dir: Path,
    included: List[date],
    missing_count: int,
) -> Path:
    path = output_dir / ("monthly-%s.md" % report.month_label)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_monthly_markdown(report, included, missing_count), encoding="utf-8"
    )
    return path
