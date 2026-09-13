from pathlib import Path

from highagent.collectors.session_db import SessionDbCollector


class ZcodeCollector(SessionDbCollector):
    name = "zcode"

    def __init__(self, db_path: Path = None, agents_dir: Path = None):
        super().__init__()
        self.db_path = db_path or Path.home() / ".zcode" / "cli" / "db" / "db.sqlite"
        self.agents_dir = agents_dir or Path.home() / ".zcode" / "cli" / "agents"
