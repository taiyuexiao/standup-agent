from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path


def connect_readonly(path: Path) -> sqlite3.Connection:
    """只读打开 SQLite；WAL 库只读失败时复制 db+wal+shm 到临时目录再连。"""
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchall()
        return conn
    except sqlite3.Error:
        tmp = Path(tempfile.mkdtemp(prefix="highagent-db-"))
        for suffix in ("", "-wal", "-shm"):
            src = Path(str(path) + suffix)
            if src.is_file():
                shutil.copy2(str(src), str(tmp / src.name))
        return sqlite3.connect(str(tmp / path.name))


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    return row is not None
