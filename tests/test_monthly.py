import tempfile
import unittest
from datetime import date
from pathlib import Path

from highagent.models import DetailItem, MonthlyReport, ReportSection
from highagent.monthly import (
    collect_monthly_reports,
    month_bounds,
    month_label,
    monthly_filename,
)
from highagent.renderer.markdown import render_monthly_markdown


class MonthBoundsTest(unittest.TestCase):
    def test_same_month(self):
        for day in (date(2026, 9, 1), date(2026, 9, 13), date(2026, 9, 30)):
            first, last = month_bounds(day)
            self.assertEqual(first, date(2026, 9, 1))
            self.assertEqual(last, date(2026, 9, 30))

    def test_cross_year_and_feb(self):
        first, last = month_bounds(date(2026, 1, 15))
        self.assertEqual((first, last), (date(2026, 1, 1), date(2026, 1, 31)))
        first, last = month_bounds(date(2024, 2, 10))  # 闰年
        self.assertEqual(last, date(2024, 2, 29))
        first, last = month_bounds(date(2026, 2, 10))
        self.assertEqual(last, date(2026, 2, 28))

    def test_label_and_filename(self):
        self.assertEqual(month_label(date(2026, 9, 13)), "2026-09")
        self.assertEqual(monthly_filename(date(2026, 9, 1)), "monthly-2026-09.md")


class CollectMonthlyTest(unittest.TestCase):
    def test_found_and_missing_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "2026-09-12.md").write_text("日报甲", encoding="utf-8")
            (root / "2026-09-13.md").write_text("日报乙", encoding="utf-8")
            (root / "2026-08-31.md").write_text("上月不进当月", encoding="utf-8")
            found, missing = collect_monthly_reports(root, date(2026, 9, 1))
            self.assertEqual([d.isoformat() for d, _ in found], ["2026-09-12", "2026-09-13"])
            self.assertEqual(len(missing), 28)

    def test_empty_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            found, missing = collect_monthly_reports(Path(tmp), date(2026, 9, 1))
            self.assertEqual(found, [])
            self.assertEqual(len(missing), 30)


class RenderMonthlyTest(unittest.TestCase):
    def test_render(self):
        report = MonthlyReport(
            month_label="2026-09",
            first_day="2026-09-01",
            last_day="2026-09-30",
            overview=ReportSection(
                summary=[DetailItem("highagent", "完成 M1-M4")],
                details=[DetailItem("highagent", "M1 最小链路")],
            ),
        )
        md = render_monthly_markdown(report, [date(2026, 9, 12)], 29)
        self.assertIn("# 月报 2026-09（2026-09-01 ~ 2026-09-30）", md)
        self.assertIn("聚合日报：1 天（2026-09-12）", md)
        self.assertIn("无日报跳过：29 天", md)
        self.assertIn("## 本月工作/学习概览", md)
        self.assertIn("### 总结", md)
        self.assertIn("## 下月计划", md)
        self.assertIn("## 本月遇到的问题", md)


if __name__ == "__main__":
    unittest.main()
