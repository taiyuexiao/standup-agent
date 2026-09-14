import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from highagent.collectors.qwen_work import QwenWorkCollector
from highagent.collectors.workbuddy import WorkbuddyCollector

MS = 1789368964130  # 2026-09-14 14:56:04 +08:00


class WorkbuddyTest(unittest.TestCase):
    def _fixture(self, root: Path):
        session_dir = root / "projects" / "Users-x-ws" 
        session_dir.mkdir(parents=True)
        events = [
            {"id": "u1", "timestamp": MS, "type": "message", "role": "user",
             "content": [{"type": "input_text",
                          "text": "<system-reminder>tool hint</system-reminder>\n<user_query>真正的问题</user_query>"}]},
            {"id": "a1", "parentId": "u1", "timestamp": MS + 1000, "type": "message",
             "role": "assistant", "status": "completed",
             "content": [{"type": "output_text", "text": "助手回答"}]},
            {"id": "r1", "timestamp": MS + 1500, "type": "reasoning",
             "content": [{"type": "reasoning_text", "text": "思考"}]},
            {"id": "f1", "timestamp": MS + 2000, "type": "function_call",
             "name": "Bash", "arguments": "{}"},
            {"id": "u2", "timestamp": MS + 3000, "type": "message", "role": "user",
             "content": [{"type": "input_text", "text": "<system-reminder data-role=\"user-context\">纯注入</system-reminder>"}]},
        ]
        (session_dir / "sess-1.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events), encoding="utf-8"
        )
        conn = sqlite3.connect(str(root / "workbuddy.db"))
        conn.execute(
            "CREATE TABLE sessions (id TEXT, title TEXT, custom_title TEXT, deleted_at INTEGER)"
        )
        conn.execute("INSERT INTO sessions VALUES ('sess-1', '原始标题', NULL, NULL)")
        conn.execute("INSERT INTO sessions VALUES ('sess-deleted', '已删', NULL, 1)")
        conn.commit()
        conn.close()
        deleted_dir = root / "projects" / "ws2"
        deleted_dir.mkdir(parents=True)
        (deleted_dir / "sess-deleted.jsonl").write_text(
            json.dumps({"id": "u9", "timestamp": MS, "type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "<user_query>已删会话</user_query>"}]}),
            encoding="utf-8",
        )

    def test_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._fixture(Path(tmp))
            c = WorkbuddyCollector(Path(tmp))
            msgs = c.collect()
            self.assertEqual(
                [(m.role, m.content) for m in msgs],
                [("user", "真正的问题"), ("assistant", "助手回答")],
            )
            self.assertEqual(msgs[0].session_id, "sess-1")
            self.assertEqual(msgs[0].project, "Users-x-ws")
            self.assertEqual(c.session_titles(), {"sess-1": "原始标题"})

    def test_missing_root(self):
        c = WorkbuddyCollector(Path("/nonexistent"))
        self.assertEqual(c.collect(), [])
        self.assertEqual(c.session_titles(), {})


class QwenWorkTest(unittest.TestCase):
    def _fixture(self, db: Path):
        conn = sqlite3.connect(str(db))
        conn.executescript(
            """
            CREATE TABLE projects (id TEXT, name TEXT, path TEXT);
            CREATE TABLE chats (id TEXT, name TEXT, project_id TEXT,
                                created_at INTEGER, updated_at INTEGER,
                                archived_at INTEGER, deleted_at INTEGER);
            CREATE TABLE messages (id TEXT, message_id TEXT, chat_id TEXT, sequence INTEGER,
                                   role TEXT, parts TEXT, metadata TEXT,
                                   searchable_text TEXT, created_at INTEGER);
            CREATE TABLE google_oauth_tokens (id TEXT, access_token TEXT);
            """
        )
        conn.execute("INSERT INTO projects VALUES ('p1', '项目甲', '/tmp/proj-a')")
        conn.execute("INSERT INTO chats VALUES ('c1', '会话甲', 'p1', ?, ?, NULL, NULL)", (MS, MS))
        conn.execute("INSERT INTO chats VALUES ('c2', '已归档', 'p1', ?, ?, 1, NULL)", (MS, MS))
        conn.execute(
            "INSERT INTO messages VALUES ('m1', 'm1', 'c1', 1, 'user', NULL, NULL, '千问提问', ?)",
            (MS,),
        )
        conn.execute(
            "INSERT INTO messages VALUES ('m2', 'm2', 'c1', 2, 'assistant', ?, NULL, '', ?)",
            (json.dumps([{"type": "text", "text": "千问回答"}]), MS + 1000),
        )
        conn.execute(
            "INSERT INTO messages VALUES ('m3', 'm3', 'c2', 1, 'user', NULL, NULL, '归档会话消息', ?)",
            (MS + 2000,),
        )
        conn.execute("INSERT INTO google_oauth_tokens VALUES ('t1', 'secret-token')")
        conn.commit()
        conn.close()

    def test_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "agents.db"
            self._fixture(db)
            c = QwenWorkCollector(db)
            msgs = c.collect()
            self.assertEqual(
                [(m.role, m.content) for m in msgs],
                [("user", "千问提问"), ("assistant", "千问回答")],
            )
            self.assertEqual(msgs[0].session_id, "c1")
            self.assertEqual(msgs[0].project, "proj-a")
            self.assertEqual(c.session_titles(), {"c1": "会话甲"})

    def test_missing_db(self):
        c = QwenWorkCollector(Path("/nonexistent/agents.db"))
        self.assertEqual(c.collect(), [])
        self.assertEqual(c.session_titles(), {})


if __name__ == "__main__":
    unittest.main()
