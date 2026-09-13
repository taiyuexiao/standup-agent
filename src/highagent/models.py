from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class Message:
    role: str
    timestamp: datetime
    content: str
    session_id: str
    agent: str
    project: str


@dataclass
class SessionActivity:
    session_id: str
    agent: str
    project: str
    title: str
    messages: List[Message] = field(default_factory=list)


@dataclass
class SessionSummary:
    session_id: str
    project: str
    title: str
    tasks: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    todos: List[str] = field(default_factory=list)


@dataclass
class DetailItem:
    category: str
    text: str


@dataclass
class ReportSection:
    summary: List[DetailItem] = field(default_factory=list)
    details: List[DetailItem] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.summary and not self.details


@dataclass
class DailyReport:
    date: str
    today: ReportSection = field(default_factory=ReportSection)
    tomorrow: ReportSection = field(default_factory=ReportSection)
    problems: ReportSection = field(default_factory=ReportSection)


@dataclass
class WeeklyReport:
    week_label: str
    monday: str
    sunday: str
    overview: ReportSection = field(default_factory=ReportSection)
    next_week: ReportSection = field(default_factory=ReportSection)
    problems: ReportSection = field(default_factory=ReportSection)


@dataclass
class MonthlyReport:
    month_label: str
    first_day: str
    last_day: str
    overview: ReportSection = field(default_factory=ReportSection)
    next_month: ReportSection = field(default_factory=ReportSection)
    problems: ReportSection = field(default_factory=ReportSection)
