from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from highagent.config import ENV_PATH, read_env_file, write_env_file

PLIST_LABEL = "com.highagent.daily"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / ("%s.plist" % PLIST_LABEL)
DATA_DIR = Path.home() / ".local" / "share" / "highagent"
LOG_PATH = DATA_DIR / "cron.log"
CRON_HOUR = 22
CRON_MINUTE = 0
API_KEY_ENV = "DEEPSEEK_API_KEY"


def _highagent_binary() -> Path:
    candidate = Path(sys.executable).absolute().with_name("highagent")
    if candidate.is_file():
        return candidate
    raise RuntimeError(
        "未找到 highagent 可执行文件（预期与 python 同目录：%s）。"
        "请先在虚拟环境中 pip install -e ." % candidate
    )


def _build_plist(binary: Path, env_key: str = None) -> dict:
    plist = {
        "Label": PLIST_LABEL,
        "ProgramArguments": [str(binary), "report"],
        "StartCalendarInterval": {"Hour": CRON_HOUR, "Minute": CRON_MINUTE},
        "StandardOutPath": str(LOG_PATH),
        "StandardErrorPath": str(LOG_PATH),
        "RunAtLoad": False,
    }
    if env_key:
        plist["EnvironmentVariables"] = {API_KEY_ENV: env_key}
    return plist


def _reload_plist() -> str:
    subprocess.run(
        ["launchctl", "unload", str(PLIST_PATH)],
        capture_output=True,
    )
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("launchctl load 失败：%s" % (result.stderr or result.stdout).strip())
    return "launchctl load 完成"


def _ask_choice(question: str, options, default: str, assume_yes: bool) -> str:
    if assume_yes:
        return default
    print(question)
    for key, text in options:
        print("  [%s] %s" % (key, text))
    try:
        answer = input("请选择（默认 %s）：" % default).strip().lower()
    except EOFError:
        return default
    return answer if answer in [k for k, _ in options] else default


def run_install_cron(assume_yes: bool) -> int:
    try:
        binary = _highagent_binary()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not assume_yes and not sys.stdin.isatty():
        print(
            "提示：stdin 不是交互终端，将按默认值处理每个问题；也可用 --yes 接受全部默认。",
            file=sys.stderr,
        )

    env_key = None
    current_key = os.environ.get(API_KEY_ENV, "").strip()
    if current_key:
        choice = _ask_choice(
            "检测到当前环境已设置 %s。cron 环境读不到 shell 环境变量，如何处理？" % API_KEY_ENV,
            [
                ("1", "写入 %s（权限 0600，推荐；report 运行时自动读取）" % ENV_PATH),
                ("2", "明文写入 plist（有泄露风险，不建议）"),
                ("3", "不处理（cron 运行时将因缺少 key 失败）"),
            ],
            "1",
            assume_yes,
        )
        if choice == "1":
            path = write_env_file(API_KEY_ENV, current_key)
            print("已写入 %s（权限 0600）。" % path)
        elif choice == "2":
            print("警告：API key 将以明文存于 %s，任何本机用户可读。" % PLIST_PATH, file=sys.stderr)
            env_key = current_key
        else:
            print("已跳过 key 处理。")
    elif read_env_file_has_key():
        print("检测到 %s 中已有 %s，cron 将直接使用。" % (ENV_PATH, API_KEY_ENV))
    else:
        print(
            "警告：当前环境没有 %s，%s 也不存在；cron 每晚运行将失败。"
            "请先 export key 后重跑 install-cron，或手动创建该文件（0600）。"
            % (API_KEY_ENV, ENV_PATH),
            file=sys.stderr,
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(_build_plist(binary, env_key), handle)
    print("plist 已写入：%s" % PLIST_PATH)

    try:
        print(_reload_plist())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "已安装：每天 %02d:%02d 运行 %s，日志见 %s。"
        "卸载用 highagent uninstall-cron。" % (CRON_HOUR, CRON_MINUTE, binary, LOG_PATH)
    )
    return 0


def read_env_file_has_key() -> bool:
    return bool(read_env_file().get(API_KEY_ENV, "").strip())


def run_uninstall_cron() -> int:
    if PLIST_PATH.exists():
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
        PLIST_PATH.unlink()
        print("已卸载并删除 %s。" % PLIST_PATH)
    else:
        print("未安装（%s 不存在）。" % PLIST_PATH)
    return 0
