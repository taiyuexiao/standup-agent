import tempfile
import unittest
from datetime import date
from pathlib import Path

from highagent.models import DetailItem, ReportSection, WeeklyReport
from highagent.renderer.markdown import render_weekly_markdown
from highagent.weekly import (
    collect_daily_reports,
    week_bounds,
    week_label,
    weekly_filename,
)


class WeekBoundsTest(unittest.TestCase):
    def test_monday_to_sunday(self):
        # 2026-09-13 是周日
        for day in [date(2026, 9, 7) , date(2026, 9, 9), date(2026, 9, 13)]:
            monday, sunday = week_bounds(day)
            self.assertEqual(monday, date(2026, 9, 7))
            self.assertEqual(sunday, date(2026, 9, 13))
            self.assertEqual(monday.weekday(), 0)
            self.assertEqual(sunday.weekday(), 6)

    def test_month_crossing(self):
        monday, sunday = week_bounds(date(2026, 9, 1))
        self.assertEqual(monday, date(2026, 8, 31))
        self.assertEqual(sunday, date(2026, 9, 6))

    def test_label_and_filename(self):
        self.assertEqual(week_label(date(2026, 9, 13)), "2026-W37")
        self.assertEqual(weekly_filename(date(2026, 9, 7)), "weekly-2026-W37.md")
        # 跨年边界：2026-01-01 属于 2026-W01
        self.assertEqual(week_label(date(2026, 1, 1)), "2026-W01")


class CollectDailyReportsTest(unittest.TestCase):
    def test_found_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2026-09-07.md").write_text("# 日报 2026-09-07\n内容甲", encoding="utf-8")
            (root / "2026-09-09.md").write_text("# 日报 2026-09-09\n内容乙", encoding="utf-8")
            (root / "2026-09-11.md").write_text("", encoding="utf-8")  # 空文件按缺失处理
            found, missing = collect_daily_reports(root, date(2026, 9, 7))
            self.assertEqual([d.isoformat() for d, _ in found], ["2026-09-07", "2026-09-09"])
            self.assertEqual(
                [d.isoformat() for d in missing],
                ["2026-09-08", "2026-09-10", "2026-09-11", "2026-09-12", "2026-09-13"],
            )
            self.assertIn("内容甲", found[0][1])

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            found, missing = collect_daily_reports(Path(tmp), date(2026, 9, 7))
            self.assertEqual(found, [])
            self.assertEqual(len(missing), 7)


class RenderWeeklyTest(unittest.TestCase):
    def test_render(self):
        report = WeeklyReport(
            week_label="2026-W37",
            monday="2026-09-07",
            sunday="2026-09-13",
            overview=ReportSection(
                summary=[DetailItem("HRM", "HRM 本周完成文档与科室功能")],
                details=[DetailItem("HRM", "实现科室管理"), DetailItem("HRM", "修复下拉框卡顿")],
            ),
            next_week=ReportSection(details=[DetailItem("highagent", "继续打磨（推断）")]),
            problems=ReportSection(details=[DetailItem("HRM", "e2e 时间敏感用例失败")]),
        )
        md = render_weekly_markdown(
            report, [date(2026, 9, 12), date(2026, 9, 13)], [date(2026, 9, 7)]
        )
        self.assertIn("# 周报 2026-W37（2026-09-07 ~ 2026-09-13）", md)
        self.assertIn("聚合日报：2026-09-12、2026-09-13", md)
        self.assertIn("无日报跳过：2026-09-07", md)
        self.assertIn("## 本周工作/学习概览", md)
        self.assertIn("### 总结", md)
        self.assertIn("- **HRM**：HRM 本周完成文档与科室功能", md)
        self.assertIn("### 细节", md)
        self.assertIn("**HRM**", md)
        self.assertIn("## 下周计划", md)
        self.assertIn("## 本周遇到的问题", md)


if __name__ == "__main__":
    unittest.main()
