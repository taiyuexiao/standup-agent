from pathlib import Path

from highagent.collectors.session_db import SessionDbCollector


class OpencodeCollector(SessionDbCollector):
    name = "opencode"

    def __init__(self, db_path: Path = None):
        super().__init__()
        self.db_path = (
            db_path or Path.home() / ".local" / "share" / "opencode" / "opencode.db"
        )
        # opencode 本机无 agents 目录结构，父子关系只走 session.parent_id
        self.agents_dir = None
