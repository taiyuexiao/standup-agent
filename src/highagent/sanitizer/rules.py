from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple

_RULES: List[Tuple[str, str, str]] = [
    (
        "private_key",
        "<PRIVATE_KEY>",
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    ),
    ("jwt", "<TOKEN>", r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}"),
    (
        "bearer",
        r"\1 <TOKEN>",
        r"(?i)\b(authorization\s*[:=]\s*bearer|bearer)\s+([A-Za-z0-9._~+/=-]{8,})",
    ),
    ("api_key", "<API_KEY>", r"\bsk-[A-Za-z0-9][A-Za-z0-9_-]{15,}\b"),
    (
        "api_key",
        r"\1\2<API_KEY>",
        r"(?i)\b(api[_-]?key|apikey|access[_-]?key|secret[_-]?key)\b(\s*[:=]\s*[\"']?)"
        r"(?=[A-Za-z0-9_-]{20,})[A-Za-z0-9_-]{20,}[\"']?",
    ),
    (
        "secret",
        r"\1=<TOKEN>",
        r"(?i)\b([A-Za-z][A-Za-z0-9_]*(?:_KEY|_SECRET|_TOKEN|_PASSWORD|_PWD))"
        r"[ \t]*=[ \t]*[\"']?(?!<)[^\s\"']{4,}[\"']?",
    ),
    (
        "password",
        r"\1<PASSWORD>",
        r"(?i)((?:密码|口令|password|passwd|pwd)\s*(?:是|为|[:：=])\s*)[\"']?(?!<)[^\s\"'，。；,;]{3,}[\"']?",
    ),
    (
        "password",
        r"\1<PASSWORD>",
        r"(?i)((?:密码|口令|password|passwd|pwd)[^\n]{0,15}?)\d{6,}",
    ),
]

_COMPILED: List[Tuple[str, str, "re.Pattern[str]"]] = [
    (name, repl, re.compile(pattern, re.DOTALL)) for name, repl, pattern in _RULES
]


@dataclass
class SanitizeStats:
    counts: dict = field(default_factory=dict)

    def add(self, name: str, n: int) -> None:
        if n:
            self.counts[name] = self.counts.get(name, 0) + n

    def merge(self, other: "SanitizeStats") -> None:
        for name, n in other.counts.items():
            self.add(name, n)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def format(self) -> str:
        labels = {
            "api_key": "API key",
            "jwt": "JWT",
            "bearer": "Bearer/Authorization",
            "password": "密码",
            "private_key": "私钥",
            "secret": "KEY/SECRET/TOKEN 赋值",
        }
        parts = ["%d 处%s" % (n, labels.get(name, name)) for name, n in sorted(self.counts.items())]
        return "、".join(parts)


def sanitize_text(text: str, stats: SanitizeStats = None) -> str:
    for name, repl, pattern in _COMPILED:
        if stats is not None:
            text, n = pattern.subn(repl, text)
            stats.add(name, n)
        else:
            text = pattern.sub(repl, text)
    return text


SANITIZER_VERSION = "san2"
