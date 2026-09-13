from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List, Tuple

from highagent.models import Message, SessionActivity


def day_window(target: date, day_start_hour: int = 0) -> Tuple[datetime, datetime]:
    start = datetime.combine(target, time(hour=day_start_hour)).astimezone()
    return start, start + timedelta(days=1)


def filter_by_day(
    messages: Iterable[Message], target: date, day_start_hour: int = 0
) -> List[Message]:
    start, end = day_window(target, day_start_hour)
    selected = [m for m in messages if start <= m.timestamp < end]
    selected.sort(key=lambda m: m.timestamp)
    return selected


def group_by_session(messages: Iterable[Message], titles: Dict[str, str] = None) -> List[SessionActivity]:
    titles = titles or {}
    sessions: Dict[str, SessionActivity] = {}
    for message in messages:
        activity = sessions.get(message.session_id)
        if activity is None:
            activity = SessionActivity(
                session_id=message.session_id,
                agent=message.agent,
                project=message.project,
                title=titles.get(message.session_id, ""),
            )
            sessions[message.session_id] = activity
        activity.messages.append(message)
    ordered = sorted(
        sessions.values(),
        key=lambda a: a.messages[0].timestamp if a.messages else datetime.min,
    )
    return ordered
