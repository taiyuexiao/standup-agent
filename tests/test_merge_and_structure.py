import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from highagent.collectors.kimi_code import KimiCodeCollector
from highagent.collectors.zcode import ZcodeCollector
from highagent.models import DailyReport, DetailItem, ReportSection
from highagent.renderer.markdown import render_markdown
from highagent.summarizer.core import parse_detail_items, parse_section

MS = 1789149600000


def _make_zcode_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, directory TEXT, title TEXT,
                              parent_id TEXT, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT,
                              time_created INTEGER, time_updated INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
                           time_created INTEGER, time_updated INTEGER, data TEXT);
        """
    )

    def add(sid, parent, title, msg_id, role, text, ts):
        conn.execute(
            "INSERT INTO session VALUES (?, '/tmp/proj', ?, ?, ?, ?)",
            (sid, title, parent, ts, ts),
        )
        conn.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?, ?)",
            (msg_id, sid, ts, ts, json.dumps({"role": role})),
        )
        conn.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
            ("p-" + msg_id, msg_id, sid, ts, ts, json.dumps({"type": "text", "text": text})),
        )

    add("sess_parent", None, "父会话", "m1", "user", "父会话提问", MS)
    # parent_id 路径归并
    add("sess_subagent_agent_aaa", "sess_parent", "子任务A", "m2", "assistant", "子任务A回答", MS + 1000)
    # 目录兜底路径：session 表无 parent_id 的孤儿子会话
    conn.execute(
        "INSERT INTO message VALUES ('m3', 'sess_subagent_agent_bbb', ?, ?, ?)",
        (MS + 2000, MS + 2000, json.dumps({"role": "assistant"})),
    )
    conn.execute(
        "INSERT INTO part VALUES ('p-m3', 'm3', 'sess_subagent_agent_bbb', ?, ?, ?)",
        (MS + 2000, MS + 2000, json.dumps({"type": "text", "text": "孤儿子会话回答"})),
    )
    conn.commit()
    conn.close()


def _make_kimi_session(root: Path):
    session_dir = root / "sessions" / "wd_proj_hash" / "session_abc"
    for agent, events in (
        ("main", [
            {"type": "context.append_message", "time": MS,
             "message": {"role": "user", "origin": {"kind": "user"},
                         "content": [{"type": "text", "text": "主会话提问"}], "id": "u1"}},
            {"type": "context.append_loop_event", "time": MS + 2000,
             "event": {"type": "content.part", "uuid": "a1",
                       "part": {"type": "text", "text": "主会话回答"}}},
        ]),
        ("agent-0", [
            {"type": "context.append_message", "time": MS + 1000,
             "message": {"role": "user", "origin": {"kind": "system_trigger"},
                         "content": [{"type": "text", "text": "子代理任务"}], "id": "u2"}},
            {"type": "context.append_loop_event", "time": MS + 3000,
             "event": {"type": "content.part", "uuid": "a2",
                       "part": {"type": "text", "text": "子代理回答"}}},
        ]),
    ):
        wire = session_dir / "agents" / agent / "wire.jsonl"
        wire.parent.mkdir(parents=True, exist_ok=True)
        wire.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    state = {"cwd": "/tmp/proj", "title": "测试", "createdAt": str(MS)}
    (session_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")


class SessionDbMergeTest(unittest.TestCase):
    def test_parent_id_and_dir_fallback_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "db.sqlite"
            _make_zcode_db(db)
            agents = Path(tmp) / "agents"
            (agents / "sess_parent" / "agent_bbb").mkdir(parents=True)
            c = ZcodeCollector(db, agents)
            msgs = c.collect()
            self.assertEqual({m.session_id for m in msgs}, {"sess_parent"})
            self.assertEqual(
                [m.content for m in msgs],
                ["父会话提问", "子任务A回答", "孤儿子会话回答"],
            )
            merges = c.pop_merges()
            self.assertEqual(
                sorted(merges),
                [("sess_subagent_agent_aaa", "sess_parent"),
                 ("sess_subagent_agent_bbb", "sess_parent")],
            )
            self.assertEqual(c.session_titles(), {"sess_parent": "父会话"})


class KimiSubagentMergeTest(unittest.TestCase):
    def test_subagents_merged_by_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_kimi_session(Path(tmp))
            c = KimiCodeCollector(Path(tmp))
            msgs = c.collect()
            self.assertEqual(
                [(m.role, m.content) for m in msgs],
                [("user", "主会话提问"),
                 ("user", "子代理任务"),
                 ("assistant", "主会话回答"),
                 ("assistant", "子代理回答")],
            )
            self.assertEqual({m.session_id for m in msgs}, {"session_abc"})
            self.assertEqual(c.pop_merges(), [("agent-0", "session_abc")])


class ParseSectionTest(unittest.TestCase):
    def test_dict_and_string_items(self):
        section = parse_section({
            "summary": [{"category": "HRM", "text": "概括"}],
            "details": [{"category": "HRM", "text": "条目1"}, "纯字符串条目", {"text": "无类别"}],
        })
        self.assertEqual(section.summary, [DetailItem("HRM", "概括")])
        self.assertEqual(
            section.details,
            [DetailItem("HRM", "条目1"), DetailItem("其他", "纯字符串条目"), DetailItem("其他", "无类别")],
        )
        self.assertFalse(section.empty)

    def test_legacy_list_and_empty(self):
        section = parse_section(["旧格式字符串数组"])
        self.assertEqual(section.summary, [])
        self.assertEqual(section.details, [DetailItem("其他", "旧格式字符串数组")])
        self.assertTrue(parse_section(None).empty)


class RenderGroupingTest(unittest.TestCase):
    def test_daily_grouped_details(self):
        report = DailyReport(
            date="2026-09-13",
            today=ReportSection(
                summary=[DetailItem("HRM", "HRM 概括"), DetailItem("调研", "调研概括")],
                details=[
                    DetailItem("HRM", "任务1"),
                    DetailItem("调研", "任务2"),
                    DetailItem("HRM", "任务3"),
                ],
            ),
        )
        md = render_markdown(report)
        self.assertIn("### 总结", md)
        self.assertIn("- **HRM**：HRM 概括", md)
        self.assertIn("### 细节", md)
        # HRM 条目连续成组，且细节区 HRM 组在 调研 组之前
        self.assertIn("**HRM**\n- 任务1\n- 任务3\n", md)
        self.assertLess(md.index("**HRM**\n- 任务1"), md.index("**调研**\n- 任务2"))
        self.assertIn("（无）", md)  # tomorrow / problems 为空


if __name__ == "__main__":
    unittest.main()
