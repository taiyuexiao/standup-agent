from __future__ import annotations

import sys
from typing import Callable, List, Tuple

from highagent import collectors
from highagent.collectors import (
    claude_code,
    codex,
    cursor,
    kimi_code,
    opencode,
    qwen_work,
    workbuddy,
    zcode,
)
from highagent.config import CONFIG_PATH, ENV_PATH

Probe = Callable[[], Tuple[bool, str]]

AGENT_PROBES: List[Tuple[str, str, Probe]] = []


def _probe(name: str, description: str):
    def decorator(func: Probe) -> Probe:
        AGENT_PROBES.append((name, description, func))
        return func

    return decorator


@_probe("kimi_code", "Kimi Code")
def _probe_kimi_code() -> Tuple[bool, str]:
    root = kimi_code.default_root() / "sessions"
    count = len(list(root.glob("wd_*/session_*"))) if root.is_dir() else 0
    return count > 0, "检测到 %d 个会话" % count if count else "未发现会话目录"


@_probe("zcode", "ZCode")
def _probe_zcode() -> Tuple[bool, str]:
    db = zcode.default_db_path()
    return db.is_file(), "检测到 db.sqlite" if db.is_file() else "未发现 db.sqlite"


@_probe("opencode", "OpenCode")
def _probe_opencode() -> Tuple[bool, str]:
    db = opencode.default_db_path()
    return db.is_file(), "检测到 opencode.db" if db.is_file() else "未发现 opencode.db"


@_probe("cursor", "Cursor")
def _probe_cursor() -> Tuple[bool, str]:
    db = cursor.default_db_path()
    return db.is_file(), "检测到 state.vscdb" if db.is_file() else "未发现 state.vscdb"


@_probe("claude_code", "Claude Code")
def _probe_claude_code() -> Tuple[bool, str]:
    root = claude_code.default_root()
    count = len(list(root.glob("**/*.jsonl"))) if root.is_dir() else 0
    return count > 0, "检测到 %d 个会话文件" % count if count else "未发现 projects 目录"


@_probe("codex", "Codex")
def _probe_codex() -> Tuple[bool, str]:
    root = codex.default_root() / "sessions"
    count = len(list(root.glob("**/*.jsonl"))) if root.is_dir() else 0
    return count > 0, "检测到 %d 个会话文件" % count if count else "未发现 sessions 目录"


@_probe("workbuddy", "WorkBuddy")
def _probe_workbuddy() -> Tuple[bool, str]:
    root = workbuddy.default_root() / "projects"
    count = len(list(root.glob("*/*.jsonl"))) if root.is_dir() else 0
    return count > 0, "检测到 %d 个会话" % count if count else "未发现 projects 目录"


@_probe("qwen_work", "千问办公")
def _probe_qwen_work() -> Tuple[bool, str]:
    db = qwen_work.default_db_path()
    return db.is_file(), "检测到 agents.db" if db.is_file() else "未发现 agents.db"


def _ask(question: str, default: bool, assume_yes: bool) -> bool:
    if assume_yes:
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input("%s %s " % (question, suffix)).strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def _config_toml(enabled: List[str], remainder_sync: bool = False) -> str:
    agents = ", ".join('"%s"' % a for a in enabled)
    sync_value = "true" if remainder_sync else "false"
    return (
        "enabled_agents = [%s]\n"
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
        "remainder_sync = %s\n"
        '# remainder_url = "http://127.0.0.1:3210"\n' % (agents, sync_value)
    )


def run_init(assume_yes: bool) -> int:
    if not assume_yes and not sys.stdin.isatty():
        print(
            "提示：stdin 不是交互终端，将按回车默认值处理每个问题；"
            "也可用 --yes 直接接受全部默认。",
            file=sys.stderr,
        )
    if CONFIG_PATH.exists():
        print("已存在配置文件：%s" % CONFIG_PATH)
        if assume_yes:
            print("--yes 模式：直接覆盖。")
        elif not _ask("是否覆盖？", False, assume_yes):
            print("已取消，未修改配置。")
            return 0

    enabled: List[str] = []
    print("探测本机 AI coding agent 数据：")
    for name, description, probe in AGENT_PROBES:
        detected, detail = probe()
        supported = collectors.has_collector(name)
        note = "" if supported else "（collector 尚未实现，启用后 report 会跳过）"
        print("  - %s (%s)：%s %s" % (name, description, detail, note))
        if _ask("    是否启用 %s？" % name, detected, assume_yes):
            enabled.append(name)

    if not enabled:
        print("未启用任何 agent，未写入配置。")
        return 0

    remainder_sync = _ask(
        "是否在生成报告后同步到本机 Remainder 应用？", False, assume_yes
    )

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(_config_toml(enabled, remainder_sync), encoding="utf-8")
    print("配置已写入 %s：\n%s" % (CONFIG_PATH, CONFIG_PATH.read_text(encoding="utf-8")))
    print(
        "提醒：请设置环境变量 DEEPSEEK_API_KEY；如需定时任务可用，"
        "可运行 highagent install-cron 时选择写入 %s（权限 0600）。" % ENV_PATH
    )
    return 0
