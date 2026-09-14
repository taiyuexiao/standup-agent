import json
import tempfile
import unittest
from pathlib import Path

from highagent.collectors.kimi_work import KimiWorkCollector

MS = 1789368964130  # 2026-09-14 14:56:04 +08:00


def _wire(*events):
    return "\n".join(json.dumps(e) for e in events)


def _user_event(text, kind="user", mid="m1", ts=MS):
    return {
        "type": "context.append_message",
        "time": ts,
        "message": {
            "role": "user",
            "origin": {"kind": kind},
            "content": [{"type": "text", "text": text}],
            "id": mid,
        },
    }


def _assistant_event(text, uuid="a1", ts=MS + 1000):
    return {
        "type": "context.append_loop_event",
        "time": ts,
        "event": {"type": "content.part", "uuid": uuid, "part": {"type": "text", "text": text}},
    }


class KimiWorkTest(unittest.TestCase):
    def _fixture(self, root: Path):
        conv = root / "sessions" / "wd_myproj_hash1" / "conv-abc123"
        (conv / "agents" / "main").mkdir(parents=True)
        (conv / "agents" / "main" / "wire.jsonl").write_text(
            _wire(
                _user_event("看下这个项目 <attachment>附件内容应剔除</attachment>"),
                _user_event("触发噪声", kind="system_trigger", mid="m2", ts=MS + 500),
                _assistant_event("桌面端回答"),
            ),
            encoding="utf-8",
        )
        (conv / "state.json").write_text(
            json.dumps({
                "workDir": "/tmp/myproj",
                "title": '<meta awareness="low" timestamp="2026-09-14 10:00" /> 真实标题',
            }),
            encoding="utf-8",
        )
        ctitle = root / "sessions" / "wd_myproj_hash1" / "ctitle-xyz789"
        (ctitle / "agents" / "main").mkdir(parents=True)
        (ctitle / "agents" / "main" / "wire.jsonl").write_text(
            _wire(_user_event("Generate a concise title..."), _assistant_event("标题", "a9")),
            encoding="utf-8",
        )
        (root / "session_index.jsonl").write_text(
            "\n".join(
                json.dumps({"sessionId": s.name, "sessionDir": str(s)})
                for s in (conv, ctitle)
            ),
            encoding="utf-8",
        )

    def test_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._fixture(root)
            c = KimiWorkCollector(root)
            msgs = c.collect()
            self.assertEqual(
                [(m.role, m.content) for m in msgs],
                [("user", "看下这个项目"), ("assistant", "桌面端回答")],
            )
            self.assertEqual(msgs[0].session_id, "conv-abc123")
            self.assertEqual(msgs[0].project, "myproj")
            self.assertEqual(msgs[0].agent, "kimi_work")
            self.assertEqual(c.session_titles(), {"conv-abc123": "真实标题"})

    def test_glob_fallback_without_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conv = root / "sessions" / "wd_p_h" / "conv-only"
            (conv / "agents" / "main").mkdir(parents=True)
            (conv / "agents" / "main" / "wire.jsonl").write_text(
                _wire(_user_event("无索引会话")), encoding="utf-8"
            )
            msgs = KimiWorkCollector(root).collect()
            self.assertEqual([m.content for m in msgs], ["无索引会话"])

    def test_missing_root(self):
        c = KimiWorkCollector(Path("/nonexistent"))
        self.assertEqual(c.collect(), [])
        self.assertEqual(c.session_titles(), {})


if __name__ == "__main__":
    unittest.main()
