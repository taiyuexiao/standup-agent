from __future__ import annotations

import os
import plistlib
import shutil
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
SCHTASKS_NAME = "HighAgentDaily"
CRONTAB_MARKER = "# highagent"


def _highagent_binary(platform: str = None) -> Path:
    platform = platform or sys.platform
    exe_name = "highagent.exe" if platform == "win32" else "highagent"
    candidate = Path(sys.executable).absolute().with_name(exe_name)
    if candidate.is_file():
        return candidate
    raise RuntimeError(
        "未找到 highagent 可执行文件（预期与 python 同目录：%s）。"
        "请先在虚拟环境中 pip install -e ." % candidate
    )


# ---------- macOS launchd ----------


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
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    result = subprocess.run(
        ["launchctl", "load", str(PLIST_PATH)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError("launchctl load 失败：%s" % (result.stderr or result.stdout).strip())
    return "launchctl load 完成"


def _install_launchd(binary: Path, env_key: str = None) -> str:
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PLIST_PATH.open("wb") as handle:
        plistlib.dump(_build_plist(binary, env_key), handle)
    _reload_plist()
    return "launchd（%s）" % PLIST_PATH


def _uninstall_launchd() -> bool:
    if not PLIST_PATH.exists():
        return False
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink()
    return True


# ---------- Windows 任务计划程序 ----------


def build_schtasks_create_cmd(binary: Path) -> list:
    return [
        "schtasks", "/create",
        "/tn", SCHTASKS_NAME,
        "/tr", '"%s" report' % binary,
        "/sc", "daily",
        "/st", "%02d:%02d" % (CRON_HOUR, CRON_MINUTE),
        "/f",
    ]


def build_schtasks_delete_cmd() -> list:
    return ["schtasks", "/delete", "/tn", SCHTASKS_NAME, "/f"]


def _install_schtasks(binary: Path) -> str:
    result = subprocess.run(build_schtasks_create_cmd(binary), capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("schtasks /create 失败：%s" % (result.stderr or result.stdout).strip())
    return "Windows 任务计划程序（任务名 %s）" % SCHTASKS_NAME


def _uninstall_schtasks() -> bool:
    result = subprocess.run(build_schtasks_delete_cmd(), capture_output=True, text=True)
    return result.returncode == 0


# ---------- Linux crontab ----------


def build_crontab_line(binary: Path) -> str:
    return "%d %d * * * %s report >> %s 2>&1 %s" % (
        CRON_MINUTE, CRON_HOUR, binary, LOG_PATH, CRONTAB_MARKER,
    )


def merge_crontab(existing: str, line: str) -> str:
    kept, _removed = strip_crontab(existing)
    return kept + line + "\n"


def strip_crontab(existing: str):
    lines = [l for l in existing.splitlines() if CRONTAB_MARKER not in l]
    removed = len(existing.splitlines()) - len(lines)
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    return text, removed


def _install_crontab(binary: Path) -> str:
    if shutil.which("crontab") is None:
        raise RuntimeError("未找到 crontab 命令：请安装 cron（如 apt install cron）后重试。")
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    text = existing.stdout if existing.returncode == 0 else ""
    new_text = merge_crontab(text, build_crontab_line(binary))
    result = subprocess.run(["crontab", "-"], input=new_text, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("crontab 写入失败：%s" % (result.stderr or result.stdout).strip())
    return "crontab（crontab -l 可查，标记 %s）" % CRONTAB_MARKER


def _uninstall_crontab() -> bool:
    if shutil.which("crontab") is None:
        return False
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if existing.returncode != 0:
        return False
    new_text, removed = strip_crontab(existing.stdout)
    if removed:
        subprocess.run(["crontab", "-"], input=new_text, capture_output=True, text=True)
    return removed > 0


# ---------- 入口 ----------


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


def _handle_api_key(assume_yes: bool, platform: str) -> str:
    """返回需要嵌入定时任务配置的 key（仅 launchd 支持嵌入），否则 None。"""
    current_key = os.environ.get(API_KEY_ENV, "").strip()
    if current_key:
        options = [
            ("1", "写入 %s（权限 0600，推荐；report 运行时自动读取）" % ENV_PATH),
        ]
        if platform == "darwin":
            options.append(("2", "明文写入 plist（有泄露风险，不建议）"))
        options.append(("3", "不处理（定时任务运行时将因缺少 key 失败）"))
        choice = _ask_choice(
            "检测到当前环境已设置 %s。定时任务环境读不到 shell 环境变量，如何处理？" % API_KEY_ENV,
            options,
            "1",
            assume_yes,
        )
        if choice == "1":
            path = write_env_file(API_KEY_ENV, current_key)
            print("已写入 %s（权限 0600）。" % path)
        elif choice == "2":
            print("警告：API key 将以明文存于 %s，任何本机用户可读。" % PLIST_PATH, file=sys.stderr)
            return current_key
        else:
            print("已跳过 key 处理。")
    elif read_env_file_has_key():
        print("检测到 %s 中已有 %s，定时任务将直接使用。" % (ENV_PATH, API_KEY_ENV))
    else:
        print(
            "警告：当前环境没有 %s，%s 也不存在；定时任务每晚运行将失败。"
            "请先 export key 后重跑 install-cron，或手动创建该文件（0600）。"
            % (API_KEY_ENV, ENV_PATH),
            file=sys.stderr,
        )
    return None


def run_install_cron(assume_yes: bool, platform: str = None) -> int:
    platform = platform or sys.platform
    try:
        binary = _highagent_binary(platform)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if not assume_yes and not sys.stdin.isatty():
        print(
            "提示：stdin 不是交互终端，将按默认值处理每个问题；也可用 --yes 接受全部默认。",
            file=sys.stderr,
        )

    env_key = _handle_api_key(assume_yes, platform)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if platform == "darwin":
            where = _install_launchd(binary, env_key)
        elif platform == "win32":
            where = _install_schtasks(binary)
        else:
            where = _install_crontab(binary)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "已安装到 %s：每天 %02d:%02d 运行 %s report，日志见 %s。"
        "卸载用 highagent uninstall-cron。"
        % (where, CRON_HOUR, CRON_MINUTE, binary, LOG_PATH)
    )
    return 0


def read_env_file_has_key() -> bool:
    return bool(read_env_file().get(API_KEY_ENV, "").strip())


def run_uninstall_cron(platform: str = None) -> int:
    platform = platform or sys.platform
    if platform == "darwin":
        removed = _uninstall_launchd()
    elif platform == "win32":
        removed = _uninstall_schtasks()
    else:
        removed = _uninstall_crontab()
    if removed:
        print("已卸载定时任务。")
    else:
        print("未安装，无需卸载。")
    return 0
