import os
import sys
from pathlib import Path

from highagent.collectors.session_db import SessionDbCollector


def default_db_path(platform: str = None, environ=None, home: Path = None) -> Path:
    """opencode 数据库路径：macOS/Linux 在 XDG 风格目录，Windows 探测 %APPDATA%/%LOCALAPPDATA%。"""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = home or Path.home()
    if platform == "win32":
        for var in ("APPDATA", "LOCALAPPDATA"):
            base = environ.get(var)
            if base and (Path(base) / "opencode" / "opencode.db").is_file():
                return Path(base) / "opencode" / "opencode.db"
        base = environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / "opencode" / "opencode.db"
    return home / ".local" / "share" / "opencode" / "opencode.db"


class OpencodeCollector(SessionDbCollector):
    name = "opencode"

    def __init__(self, db_path: Path = None):
        super().__init__()
        self.db_path = db_path or default_db_path()
        # opencode 本机无 agents 目录结构，父子关系只走 session.parent_id
        self.agents_dir = None
