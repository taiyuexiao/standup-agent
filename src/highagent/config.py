from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

CONFIG_PATH = Path.home() / ".config" / "highagent" / "config.toml"
ENV_PATH = Path.home() / ".config" / "highagent" / ".env"
DEFAULT_OUTPUT_DIR = "~/daily-reports"
DEFAULT_AGENTS = ["kimi_code"]
DEFAULT_DAY_START_HOUR = 0
DEFAULT_MAX_SESSION_CHARS = 20000


@dataclass
class Config:
    enabled_agents: List[str] = field(default_factory=lambda: list(DEFAULT_AGENTS))
    day_start_hour: int = DEFAULT_DAY_START_HOUR
    output_dir: str = DEFAULT_OUTPUT_DIR
    max_session_chars: int = DEFAULT_MAX_SESSION_CHARS
    sanitize: bool = True
    llm_provider: str = "deepseek"
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key_env: str = ""
    remainder_sync: bool = False
    remainder_url: str = "http://127.0.0.1:3210"
    path: Path = field(default=CONFIG_PATH)
    existed: bool = False


def _strip_inline_comment(line: str) -> str:
    in_quote = False
    for index, char in enumerate(line):
        if char == '"':
            in_quote = not in_quote
        elif char == "#" and not in_quote:
            return line[:index]
    return line


def _parse_scalar(raw: str):
    raw = raw.strip()
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1]
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(item) for item in inner.split(",")]
    try:
        return int(raw)
    except ValueError:
        pass
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    return raw


def _parse_toml_fallback(text: str) -> dict:
    data: dict = {}
    for line in text.splitlines():
        line = _strip_inline_comment(line).strip()
        if not line or (line.startswith("[") and line.endswith("]")):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = _parse_scalar(value)
    return data


def _load_toml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib

        return tomllib.loads(text)
    except ImportError:
        return _parse_toml_fallback(text)


def load_config(path: Path = CONFIG_PATH) -> Config:
    config = Config(path=path)
    if not path.exists():
        return config
    config.existed = True
    data = _load_toml(path)
    agents = data.get("enabled_agents")
    if isinstance(agents, list) and agents:
        config.enabled_agents = [str(a) for a in agents]
    hour = data.get("day_start_hour")
    if isinstance(hour, int) and 0 <= hour <= 23:
        config.day_start_hour = hour
    output = data.get("output_dir")
    if isinstance(output, str) and output:
        config.output_dir = output
    max_chars = data.get("max_session_chars")
    if isinstance(max_chars, int) and max_chars > 0:
        config.max_session_chars = max_chars
    sanitize = data.get("sanitize")
    if isinstance(sanitize, bool):
        config.sanitize = sanitize
    for key in ("llm_provider", "llm_model", "llm_base_url", "llm_api_key_env"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            setattr(config, key, value.strip())
    remainder_sync = data.get("remainder_sync")
    if isinstance(remainder_sync, bool):
        config.remainder_sync = remainder_sync
    remainder_url = data.get("remainder_url")
    if isinstance(remainder_url, str) and remainder_url.strip():
        config.remainder_url = remainder_url.strip()
    return config


def default_config_toml() -> str:
    return (
        'enabled_agents = ["kimi_code"]\n'
        "day_start_hour = 0\n"
        'output_dir = "~/daily-reports"\n'
        "max_session_chars = 20000\n"
        "sanitize = true\n"
        "# LLM 预设：deepseek / moonshot / openai，默认 deepseek\n"
        'llm_provider = "deepseek"\n'
        "# 以下三项可选，覆盖预设值\n"
        '# llm_model = "deepseek-chat"\n'
        '# llm_base_url = "https://api.deepseek.com"\n'
        '# llm_api_key_env = "DEEPSEEK_API_KEY"\n'
        "# Remainder 同步：生成报告后推送到本机 Remainder 应用\n"
        "remainder_sync = false\n"
        '# remainder_url = "http://127.0.0.1:3210"\n'
    )


def output_dir(config: Config) -> Path:
    return Path(os.path.expanduser(config.output_dir))


def read_env_file(path: Path = ENV_PATH) -> dict:
    values: dict = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_env_file(key: str, value: str, path: Path = ENV_PATH) -> Path:
    values = read_env_file(path)
    values[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["%s=%s" % (k, v) for k, v in sorted(values.items())]
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    os.chmod(str(path), 0o600)
    # Windows 上 chmod 语义有限（仅只读位生效），属无害调用，保留以兼容 POSIX
    return path
