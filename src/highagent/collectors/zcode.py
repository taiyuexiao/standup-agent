from pathlib import Path

from highagent.collectors.session_db import SessionDbCollector


def default_db_path(home: Path = None) -> Path:
    return (home or Path.home()) / ".zcode" / "cli" / "db" / "db.sqlite"


def default_agents_dir(home: Path = None) -> Path:
    return (home or Path.home()) / ".zcode" / "cli" / "agents"


class ZcodeCollector(SessionDbCollector):
    name = "zcode"

    def __init__(self, db_path: Path = None, agents_dir: Path = None):
        super().__init__()
        self.db_path = db_path or default_db_path()
        self.agents_dir = agents_dir or default_agents_dir()
