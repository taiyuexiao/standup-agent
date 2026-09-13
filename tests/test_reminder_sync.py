import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from highagent.config import Config, load_config
from highagent.reminder_sync import sync_report


class FakeRemainderHandler(BaseHTTPRequestHandler):
    store = {}
    patch_calls = []

    def _handle(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if method == "POST" and self.path == "/api/reports":
            key = (body.get("type"), body.get("date"))
            if key in self.store:
                self._respond({"id": self.store[key]["id"]}, 200)
            else:
                record = {
                    "id": "r-%d" % (len(self.store) + 1),
                    "title": body.get("title"),
                    "content_markdown": body.get("content_markdown"),
                }
                self.store[key] = record
                self._respond({"id": record["id"]}, 201)
            return
        if method == "PATCH" and self.path.startswith("/api/reports/"):
            report_id = self.path.rsplit("/", 1)[1]
            self.patch_calls.append((report_id, body))
            found = False
            for record in self.store.values():
                if record["id"] == report_id:
                    record.update(body)
                    found = True
            self._respond({"ok": found}, 200 if found else 404)
            return
        self._respond({"error": "not found"}, 404)

    def do_POST(self):
        self._handle("POST")

    def do_PATCH(self):
        self._handle("PATCH")

    def _respond(self, payload, code=200):
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class SyncTest(unittest.TestCase):
    def setUp(self):
        FakeRemainderHandler.store = {}
        FakeRemainderHandler.patch_calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeRemainderHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()

    def test_create_path_post_only(self):
        ok = sync_report(self.url, "daily", "2026-09-13", "# 日报内容")
        self.assertTrue(ok)
        record = FakeRemainderHandler.store[("daily", "2026-09-13")]
        # 201 新建：title/content 由 POST 一次写入，无 PATCH
        self.assertEqual(record["title"], "AI 日报 2026-09-13")
        self.assertEqual(record["content_markdown"], "# 日报内容")
        self.assertEqual(FakeRemainderHandler.patch_calls, [])

    def test_existing_path_patches(self):
        sync_report(self.url, "weekly", "2026-09-07", "v1", label="2026-W37")
        sync_report(self.url, "weekly", "2026-09-07", "v2", label="2026-W37")
        self.assertEqual(len(FakeRemainderHandler.store), 1)
        record = FakeRemainderHandler.store[("weekly", "2026-09-07")]
        self.assertEqual(record["title"], "AI 周报 2026-W37")
        self.assertEqual(record["content_markdown"], "v2")
        # 第二次是 200 已存在：补了一次 PATCH
        self.assertEqual(len(FakeRemainderHandler.patch_calls), 1)
        self.assertEqual(
            FakeRemainderHandler.patch_calls[0][1],
            {"title": "AI 周报 2026-W37", "content_markdown": "v2"},
        )

    def test_monthly_title(self):
        sync_report(self.url, "monthly", "2026-09", "月报内容")
        record = FakeRemainderHandler.store[("monthly", "2026-09")]
        self.assertEqual(record["title"], "AI 月报 2026-09")

    def test_connection_refused_returns_false(self):
        self.server.shutdown()
        self.assertFalse(sync_report("http://127.0.0.1:1", "daily", "2026-09-13", "x"))

    def test_http_error_returns_false(self):
        self.assertFalse(sync_report(self.url + "/nope", "daily", "2026-09-13", "x"))


class RemainderConfigTest(unittest.TestCase):
    def test_defaults(self):
        config = Config()
        self.assertFalse(config.remainder_sync)
        self.assertEqual(config.remainder_url, "http://127.0.0.1:3210")

    def test_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(
                'remainder_sync = true\nremainder_url = "http://127.0.0.1:9999"\n',
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertTrue(config.remainder_sync)
            self.assertEqual(config.remainder_url, "http://127.0.0.1:9999")


if __name__ == "__main__":
    unittest.main()
