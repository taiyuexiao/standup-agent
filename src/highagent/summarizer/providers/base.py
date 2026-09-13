from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def complete_json(self, system: str, user: str) -> dict:
        """Send a chat completion expecting a JSON object response."""
