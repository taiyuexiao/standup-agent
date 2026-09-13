import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from highagent import cron
from highagent.collectors import claude_code, codex, cursor, kimi_code, opencode, zcode


class SchtasksTest(unittest.TestCase):
    def test_create_cmd(self):
        cmd = cron.build_schtasks_create_cmd(Path("C:\\proj\\.venv\\Scripts\\highagent.exe"))
        self.assertEqual(cmd[:2], ["schtasks", "/create"])
        self.assertEqual(cmd[cmd.index("/tn") + 1], "HighAgentDaily")
        self.assertEqual(
            cmd[cmd.index("/tr") + 1],
            '"C:\\proj\\.venv\\Scripts\\highagent.exe" report',
        )
        self.assertEqual(cmd[cmd.index("/sc") + 1], "daily")
        self.assertEqual(cmd[cmd.index("/st") + 1], "22:00")
        self.assertIn("/f", cmd)

    def test_delete_cmd(self):
        self.assertEqual(
            cron.build_schtasks_delete_cmd(),
            ["schtasks", "/delete", "/tn", "HighAgentDaily", "/f"],
        )

    def test_install_calls_schtasks(self):
        with mock.patch.object(cron.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            where = cron._install_schtasks(Path("C:\\x\\highagent.exe"))
        args = run.call_args[0][0]
        self.assertEqual(args[0], "schtasks")
        self.assertIn("任务计划程序", where)

    def test_uninstall_calls_schtasks(self):
        with mock.patch.object(cron.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stderr="", stdout="")
            self.assertTrue(cron._uninstall_schtasks())
        self.assertEqual(run.call_args[0][0][1], "/delete")


class CrontabTest(unittest.TestCase):
    def test_line(self):
        line = cron.build_crontab_line(Path("/home/u/proj/.venv/bin/highagent"))
        self.assertTrue(line.startswith("0 22 * * * /home/u/proj/.venv/bin/highagent report >> "))
        self.assertTrue(line.endswith("# highagent"))

    def test_merge_appends_and_replaces(self):
        existing = "0 9 * * * /usr/bin/foo\n0 22 * * * /old/highagent report >> /x 2>&1 # highagent\n"
        merged = cron.merge_crontab(existing, cron.build_crontab_line(Path("/new/highagent")))
        self.assertIn("/usr/bin/foo", merged)
        self.assertNotIn("/old/highagent", merged)
        self.assertIn("/new/highagent report", merged)
        self.assertEqual(merged.count("# highagent"), 1)

    def test_strip(self):
        existing = "a\nb # highagent\nc # highagent\n"
        text, removed = cron.strip_crontab(existing)
        self.assertEqual(text, "a\n")
        self.assertEqual(removed, 2)

    def test_install_missing_crontab(self):
        with mock.patch.object(cron.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                cron._install_crontab(Path("/x/highagent"))

    def test_install_writes_crontab(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd == ["crontab", "-l"]:
                return mock.Mock(returncode=0, stdout="0 9 * * * /usr/bin/foo\n", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(cron.shutil, "which", return_value="/usr/bin/crontab"), \
             mock.patch.object(cron.subprocess, "run", side_effect=fake_run):
            where = cron._install_crontab(Path("/new/highagent"))
        self.assertEqual(calls[0], ["crontab", "-l"])
        self.assertEqual(calls[1], ["crontab", "-"])
        self.assertIn("crontab", where)


class LaunchdTest(unittest.TestCase):
    def test_plist_unchanged(self):
        plist = cron._build_plist(Path("/p/.venv/bin/highagent"), None)
        self.assertEqual(plist["ProgramArguments"], ["/p/.venv/bin/highagent", "report"])
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 22, "Minute": 0})
        self.assertIn("cron.log", plist["StandardOutPath"])
        self.assertNotIn("EnvironmentVariables", plist)


class BinaryResolutionTest(unittest.TestCase):
    def test_win32_exe_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            scripts = Path(tmp) / "Scripts"
            scripts.mkdir()
            (scripts / "highagent.exe").write_text("x")
            with mock.patch.object(sys, "executable", str(scripts / "python.exe")):
                binary = cron._highagent_binary("win32")
            self.assertEqual(binary.name, "highagent.exe")

    def test_posix_name(self):
        binary = cron._highagent_binary("darwin")
        self.assertEqual(binary.name, "highagent")


class CollectorPathTest(unittest.TestCase):
    def test_opencode_windows_appdata(self):
        with tempfile.TemporaryDirectory() as tmp:
            appdata = Path(tmp) / "Roaming"
            (appdata / "opencode").mkdir(parents=True)
            (appdata / "opencode" / "opencode.db").write_text("")
            path = opencode.default_db_path(
                platform="win32", environ={"APPDATA": str(appdata)}
            )
            self.assertEqual(path, appdata / "opencode" / "opencode.db")

    def test_opencode_windows_localappdata_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "Local"
            (local / "opencode").mkdir(parents=True)
            (local / "opencode" / "opencode.db").write_text("")
            path = opencode.default_db_path(
                platform="win32",
                environ={"APPDATA": str(Path(tmp) / "Roaming"), "LOCALAPPDATA": str(local)},
            )
            self.assertEqual(path, local / "opencode" / "opencode.db")

    def test_opencode_posix(self):
        path = opencode.default_db_path(platform="linux", environ={}, home=Path("/home/u"))
        self.assertEqual(path, Path("/home/u/.local/share/opencode/opencode.db"))

    def test_cursor_platforms(self):
        mac = cursor.default_db_path(platform="darwin", environ={}, home=Path("/Users/u"))
        self.assertEqual(
            mac,
            Path("/Users/u/Library/Application Support/Cursor/User/globalStorage/state.vscdb"),
        )
        win = cursor.default_db_path(
            platform="win32", environ={"APPDATA": "C:\\Users\\u\\AppData\\Roaming"}
        )
        self.assertEqual(
            win,
            Path("C:\\Users\\u\\AppData\\Roaming/Cursor/User/globalStorage/state.vscdb"),
        )
        linux = cursor.default_db_path(platform="linux", environ={}, home=Path("/home/u"))
        self.assertEqual(
            linux, Path("/home/u/.config/Cursor/User/globalStorage/state.vscdb")
        )

    def test_dotdir_collectors(self):
        home = Path("/home/u")
        self.assertEqual(kimi_code.default_root(home), home / ".kimi-code")
        self.assertEqual(zcode.default_db_path(home), home / ".zcode/cli/db/db.sqlite")
        self.assertEqual(zcode.default_agents_dir(home), home / ".zcode/cli/agents")
        self.assertEqual(claude_code.default_root(home), home / ".claude/projects")
        self.assertEqual(codex.default_root(home), home / ".codex")


if __name__ == "__main__":
    unittest.main()
