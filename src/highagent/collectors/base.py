from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional

from highagent.models import Message


def parse_iso_timestamp(raw) -> Optional[datetime]:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


class Collector(ABC):
    name: str

    def __init__(self):
        self.merges: List[tuple] = []  # [(子会话标识, 父会话 id)]

    @abstractmethod
    def collect(self) -> List[Message]:
        """Read local session storage and return unified messages."""

    def session_titles(self) -> Dict[str, str]:
        return {}

    def pop_merges(self) -> List[tuple]:
        merges, self.merges = self.merges, []
        return merges
