import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from highagent.collectors.claude_code import ClaudeCodeCollector
from highagent.collectors.codex import CodexCollector
from highagent.collectors.cursor import CursorCollector
from highagent.collectors.zcode import ZcodeCollector

MS_0913_AM = 1789149600000  # 2026-09-13 10:00:00 +08:00
MS_0913_PM = 1789185600000  # 2026-09-13 20:00:00 +08:00


def _make_session_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,
                              time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT,
                              time_created INTEGER, time_updated INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                           time_created INTEGER, time_updated INTEGER, data TEXT);
        """
    )
    conn.execute(
        "INSERT INTO session VALUES ('sess1', '/tmp/myproj', '测试会话', ?, ?)",
        (MS_0913_AM, MS_0913_PM),
    )
    conn.execute(
        "INSERT INTO message VALUES ('m1', 'sess1', ?, ?, ?)",
        (MS_0913_AM, MS_0913_AM, json.dumps({"role": "user", "time": {"created": MS_0913_AM}})),
    )
    conn.execute(
        "INSERT INTO message VALUES ('m2', 'sess1', ?, ?, ?)",
        (MS_0913_PM, MS_0913_PM, json.dumps({"role": "assistant"})),
    )
    conn.execute(
        "INSERT INTO part VALUES ('p1', 'm1', 'sess1', ?, ?, ?)",
        (MS_0913_AM, MS_0913_AM, json.dumps({"type": "text", "text": "帮我看下这个问题"})),
    )
    conn.execute(
        "INSERT INTO part VALUES ('p2', 'm2', 'sess1', ?, ?, ?)",
        (MS_0913_PM, MS_0913_PM, json.dumps({"type": "reasoning", "text": "思考中"})),
    )
    conn.execute(
        "INSERT INTO part VALUES ('p3', 'm2', 'sess1', ?, ?, ?)",
        (MS_0913_PM, MS_0913_PM, json.dumps({"type": "text", "text": "这是回答"})),
    )
    conn.commit()
    conn.close()


def _make_cursor_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE composerHeaders (composerId TEXT PRIMARY KEY, workspaceId TEXT,
                                      createdAt INTEGER, lastUpdatedAt INTEGER, value TEXT);
        CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT);
        """
    )
    conn.execute(
        "INSERT INTO composerHeaders VALUES ('comp1', 'ws', ?, ?, '{}')",
        (MS_0913_AM, MS_0913_PM),
    )
    bubbles = [
        ("bubbleId:comp1:b1", {"type": 1, "text": "cursor 里问个问题", "createdAt": MS_0913_AM}),
        ("bubbleId:comp1:b2", {"type": 2, "text": "cursor 的回答", "createdAt": MS_0913_PM}),
        ("bubbleId:comp1:b3", {"type": 3, "text": "非对话类型应跳过"}),
    ]
    conn.executemany(
        "INSERT INTO cursorDiskKV VALUES (?, ?)",
        [(k, json.dumps(v)) for k, v in bubbles],
    )
    conn.execute(
        "INSERT INTO ItemTable VALUES ('cursorAuth/accessToken', 'sk-secret-token')",
    )
    conn.execute(
        "INSERT INTO ItemTable VALUES ('aiService.prompts', ?)",
        (json.dumps([{"text": "旧格式问题", "createdAt": MS_0913_AM}]),),
    )
    conn.commit()
    conn.close()


class SessionDbTest(unittest.TestCase):
    def test_zcode_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "db.sqlite"
            _make_session_db(db)
            c = ZcodeCollector(db)
            msgs = c.collect()
            self.assertEqual([(m.role, m.content) for m in msgs], [
                ("user", "帮我看下这个问题"),
                ("assistant", "这是回答"),
            ])
            self.assertEqual(msgs[0].timestamp.year, 2026)
            self.assertEqual(msgs[0].timestamp.month, 9)
            self.assertEqual(msgs[0].project, "myproj")
            self.assertEqual(c.session_titles(), {"sess1": "测试会话"})

    def test_missing_db_returns_empty(self):
        c = ZcodeCollector(Path("/nonexistent/db.sqlite"))
        self.assertEqual(c.collect(), [])
        self.assertEqual(c.session_titles(), {})


class CursorTest(unittest.TestCase):
    def test_bubbles_and_auth_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.vscdb"
            _make_cursor_db(db)
            c = CursorCollector(db)
            msgs = c.collect()
            self.assertEqual([(m.role, m.content) for m in msgs], [
                ("user", "cursor 里问个问题"),
                ("assistant", "cursor 的回答"),
            ])
            joined = json.dumps([m.content for m in msgs])
            self.assertNotIn("sk-secret-token", joined)

    def test_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "state.vscdb"
            conn = sqlite3.connect(str(db))
            conn.execute("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT INTO ItemTable VALUES ('aiService.prompts', ?)",
                (json.dumps([{"text": "旧格式问题", "createdAt": MS_0913_AM}]),),
            )
            conn.execute(
                "INSERT INTO ItemTable VALUES ('aiService.generations', ?)",
                (json.dumps([{"text": "旧格式回答", "createdAt": MS_0913_PM}]),),
            )
            conn.commit()
            conn.close()
            msgs = CursorCollector(db).collect()
            self.assertEqual(
                [(m.role, m.content, m.session_id) for m in msgs],
                [("user", "旧格式问题", "cursor-legacy"),
                 ("assistant", "旧格式回答", "cursor-legacy")],
            )

    def test_missing_db_returns_empty(self):
        self.assertEqual(CursorCollector(Path("/nonexistent/state.vscdb")).collect(), [])


class ClaudeCodeTest(unittest.TestCase):
    def test_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "-Users-x-projects-myproj"
            proj.mkdir()
            lines = [
                {"type": "user", "timestamp": "2026-09-13T02:00:00.000Z",
                 "message": {"role": "user", "content": "字符串形式的提问"}},
                {"type": "assistant", "timestamp": "2026-09-13T02:00:05.000Z",
                 "message": {"role": "assistant", "content": [
                     {"type": "thinking", "thinking": "内部思考"},
                     {"type": "text", "text": "块形式的回答"},
                     {"type": "tool_use", "name": "Bash"},
                 ]}},
                {"type": "system", "timestamp": "2026-09-13T02:00:06.000Z",
                 "message": {"content": "系统噪声应跳过"}},
            ]
            (proj / "sess-uuid-1.jsonl").write_text(
                "\n".join(json.dumps(l) for l in lines), encoding="utf-8"
            )
            msgs = ClaudeCodeCollector(Path(tmp)).collect()
            self.assertEqual([(m.role, m.content) for m in msgs], [
                ("user", "字符串形式的提问"),
                ("assistant", "块形式的回答"),
            ])
            self.assertEqual(msgs[0].session_id, "sess-uuid-1")
            self.assertEqual(msgs[0].project, "-Users-x-projects-myproj")
            self.assertEqual(msgs[0].timestamp.hour, 10)  # UTC+8

    def test_missing_dir_returns_empty(self):
        self.assertEqual(ClaudeCodeCollector(Path("/nonexistent")).collect(), [])


class CodexTest(unittest.TestCase):
    def test_fixture_and_zst_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            day = Path(tmp) / "sessions" / "2026" / "09" / "13"
            day.mkdir(parents=True)
            lines = [
                {"timestamp": "2026-09-13T02:00:00.000Z", "type": "session_meta",
                 "payload": {"id": "codex-sess-1", "cwd": "/tmp/codexproj"}},
                {"timestamp": "2026-09-13T02:00:01.000Z", "type": "response_item",
                 "payload": {"type": "message", "role": "user",
                             "content": [{"type": "input_text", "text": "codex 提问"}]}},
                {"timestamp": "2026-09-13T02:00:02.000Z", "type": "turn_context",
                 "payload": {"cwd": "/tmp/codexproj"}},
                {"timestamp": "2026-09-13T02:00:03.000Z", "type": "response_item",
                 "payload": {"type": "message", "role": "assistant",
                             "content": [{"type": "output_text", "text": "codex 回答"}]}},
            ]
            (day / "rollout-2026-09-13T02-00-00-abc.jsonl").write_text(
                "\n".join(json.dumps(l) for l in lines), encoding="utf-8"
            )
            (day / "rollout-2026-09-13T03-00-00-def.jsonl.zst").write_bytes(b"fake-zst")
            msgs = CodexCollector(Path(tmp)).collect()
            self.assertEqual([(m.role, m.content) for m in msgs], [
                ("user", "codex 提问"),
                ("assistant", "codex 回答"),
            ])
            self.assertEqual(msgs[0].session_id, "codex-sess-1")
            self.assertEqual(msgs[0].project, "codexproj")
            self.assertEqual(msgs[0].timestamp.hour, 10)

    def test_missing_dir_returns_empty(self):
        self.assertEqual(CodexCollector(Path("/nonexistent")).collect(), [])


if __name__ == "__main__":
    unittest.main()
