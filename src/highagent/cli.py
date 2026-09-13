from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from highagent import collectors
from highagent.config import CONFIG_PATH, default_config_toml, load_config, output_dir
from highagent.cron import run_install_cron, run_uninstall_cron
from highagent.extractor import filter_by_day, group_by_session
from highagent.models import DailyReport
from highagent.monthly import (
    collect_monthly_reports,
    month_bounds,
    month_label,
    monthly_filename,
    summarize_month,
)
from highagent.reminder_sync import sync_report
from highagent.renderer import write_monthly_report, write_report, write_weekly_report
from highagent.sanitizer import SanitizeStats
from highagent.setup_wizard import run_init
from highagent.store import Store
from highagent.summarizer import LLMError, get_provider, summarize_day, summarize_session
from highagent.weekly import (
    collect_daily_reports,
    summarize_week,
    week_bounds,
    week_label,
    weekly_filename,
)


def _parse_date(raw: str) -> date:
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError("日期格式应为 YYYY-MM-DD：%s" % raw)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="highagent", description="扫描本机 AI coding agent 会话，生成当日工作日报"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    report = sub.add_parser("report", help="生成指定日期（默认今天）的日报")
    report.add_argument("--date", type=_parse_date, default=date.today(), help="目标日期 YYYY-MM-DD，默认今天")
    report.add_argument("--agents", help="逗号分隔的 agent 列表，覆盖配置中的 enabled_agents")
    report.add_argument("--output", help="输出文件路径，覆盖默认的 ~/daily-reports/<date>.md")
    report.add_argument("--dry-run", action="store_true", help="只做提取与统计，不调用 LLM")
    report.add_argument("--force", action="store_true", help="目标日期已生成过时强制重跑")

    init_cmd = sub.add_parser("init", help="交互式生成配置文件")
    init_cmd.add_argument("--yes", action="store_true", help="非交互模式：全部按默认（启用所有探测到的 agent）")

    weekly = sub.add_parser("weekly", help="聚合本周已有日报生成周报")
    weekly.add_argument("--date", type=_parse_date, default=date.today(), help="周内任意一天 YYYY-MM-DD，默认今天所在周（周一为起点）")
    weekly.add_argument("--force", action="store_true", help="周报已存在时强制覆盖")
    weekly.add_argument("--dry-run", action="store_true", help="只列出会聚合哪些日报，不调用 LLM")

    monthly = sub.add_parser("monthly", help="聚合本月已有日报生成月报")
    monthly.add_argument("--date", type=_parse_date, default=date.today(), help="月内任意一天 YYYY-MM-DD，默认今天所在月")
    monthly.add_argument("--force", action="store_true", help="月报已存在时强制覆盖")
    monthly.add_argument("--dry-run", action="store_true", help="只列出会聚合哪些日报，不调用 LLM")

    cron = sub.add_parser("install-cron", help="安装 launchd 定时任务（每天 22:00 生成日报）")
    cron.add_argument("--yes", action="store_true", help="非交互模式：全部按默认")

    sub.add_parser("uninstall-cron", help="卸载 launchd 定时任务")
    return parser


def cmd_report(args) -> int:
    config = load_config()
    if not config.existed:
        print(
            "提示：未找到配置文件 %s，按默认配置运行（enabled_agents = kimi_code）。\n"
            "可运行 highagent init 生成配置。" % CONFIG_PATH,
            file=sys.stderr,
        )
    agents = (
        [a.strip() for a in args.agents.split(",") if a.strip()]
        if args.agents
        else config.enabled_agents
    )

    target = (
        Path(args.output).expanduser()
        if args.output
        else output_dir(config) / ("%s.md" % args.date.isoformat())
    )
    store = None if args.dry_run else Store()
    if not args.dry_run and not args.force:
        if store.has_run(args.date) and target.exists():
            print("该日期已生成过日报：%s（使用 --force 强制重跑）" % target)
            return 0
        if target.exists() and not store.has_run(args.date):
            print("日报文件已存在：%s（使用 --force 强制重跑）" % target)
            return 0

    messages = []
    titles = {}
    valid_agents = []
    for name in agents:
        if not collectors.has_collector(name):
            print("警告：agent %s 的 collector 尚未实现，已跳过。" % name, file=sys.stderr)
            continue
        collector = collectors.get_collector(name)
        collected = collector.collect()
        titles.update(collector.session_titles())
        print("collector %s：读取到 %d 条消息" % (name, len(collected)))
        for child, parent in collector.pop_merges():
            print("  归并子会话 %s -> %s" % (child[:32], parent[:32]))
        messages.extend(collected)
        valid_agents.append(name)
    if agents and not valid_agents:
        print("没有可用的 collector，终止。", file=sys.stderr)
        return 2

    todays = filter_by_day(messages, args.date, config.day_start_hour)
    sessions = group_by_session(todays, titles)
    total_chars = sum(len(m.content) for m in todays)
    print(
        "%s：%d 个会话、%d 条消息、约 %d 字符"
        % (args.date.isoformat(), len(sessions), len(todays), total_chars)
    )
    if not sessions:
        print("该日期没有会话活动，未生成日报。")
        return 0

    if args.dry_run:
        for activity in sessions:
            users = sum(1 for m in activity.messages if m.role == "user")
            assistants = len(activity.messages) - users
            chars = sum(len(m.content) for m in activity.messages)
            print(
                "  - %s [%s] %s：用户 %d 条 / 助手 %d 条 / %d 字符"
                % (
                    activity.session_id[:16],
                    activity.project,
                    activity.title or "(无标题)",
                    users,
                    assistants,
                    chars,
                )
            )
        return 0

    provider = get_provider(config.llm_provider, config)
    stats = SanitizeStats()
    try:
        summaries = []
        for activity in sessions:
            label = "%s [%s]" % (activity.session_id[:16], activity.project)
            print("总结会话 %s ..." % label)
            summary, cache_hit = summarize_session(
                provider,
                activity,
                config.max_session_chars,
                store,
                sanitize=config.sanitize,
                stats=stats,
            )
            if cache_hit:
                print("  session %s 命中缓存，跳过 LLM 调用" % activity.session_id[:16])
            summaries.append(summary)
        print("汇总日报 ...")
        report = summarize_day(provider, args.date, summaries)
    except LLMError as exc:
        print("LLM 调用失败：%s" % exc, file=sys.stderr)
        return 1

    if config.sanitize:
        print(
            "脱敏：%s"
            % (stats.format() if stats.total else "本次送入 LLM 的内容未发现敏感信息")
        )

    if report.today.empty and report.problems.empty and report.tomorrow.empty:
        report = DailyReport(date=args.date.isoformat())
    path = write_report(report, output_dir(config), args.output)
    store.record_run(args.date, path, len(sessions), len(todays))
    print("日报已生成：%s" % path)
    _maybe_sync(config, "daily", args.date.isoformat(), path)
    return 0


def cmd_weekly(args) -> int:
    config = load_config()
    monday, sunday = week_bounds(args.date)
    reports_dir = output_dir(config)
    target = reports_dir / weekly_filename(args.date)
    print("周范围：%s ~ %s" % (monday.isoformat(), sunday.isoformat()))

    if target.exists() and not args.force and not args.dry_run:
        print("周报已存在：%s（使用 --force 强制覆盖）" % target)
        return 0

    found, missing = collect_daily_reports(reports_dir, monday)
    for day, _text in found:
        print("  聚合 %s 日报" % day.isoformat())
    for day in missing:
        print("  跳过 %s（无日报）" % day.isoformat())
    if not found:
        print("本周没有任何日报，未生成周报。")
        return 0
    if args.dry_run:
        print("dry-run：将聚合 %d 份日报 -> %s" % (len(found), target))
        return 0

    provider = get_provider(config.llm_provider, config)
    stats = SanitizeStats()
    try:
        report = summarize_week(provider, monday, found, config.sanitize, stats)
    except LLMError as exc:
        print("LLM 调用失败：%s" % exc, file=sys.stderr)
        return 1
    if config.sanitize and stats.total:
        print("脱敏：%s" % stats.format())
    path = write_weekly_report(report, reports_dir, [d for d, _ in found], missing)
    print("周报已生成：%s" % path)
    _maybe_sync(config, "weekly", monday.isoformat(), path, label=week_label(args.date))
    return 0


def cmd_monthly(args) -> int:
    config = load_config()
    first, last = month_bounds(args.date)
    reports_dir = output_dir(config)
    target = reports_dir / monthly_filename(args.date)
    print("月范围：%s ~ %s" % (first.isoformat(), last.isoformat()))

    if target.exists() and not args.force and not args.dry_run:
        print("月报已存在：%s（使用 --force 强制覆盖）" % target)
        return 0

    found, missing = collect_monthly_reports(reports_dir, first)
    for day, _text in found:
        print("  聚合 %s 日报" % day.isoformat())
    if missing:
        print("  跳过 %d 天（无日报）" % len(missing))
    if not found:
        print("本月没有任何日报，未生成月报。")
        return 0
    if args.dry_run:
        print("dry-run：将聚合 %d 份日报 -> %s" % (len(found), target))
        return 0

    provider = get_provider(config.llm_provider, config)
    stats = SanitizeStats()
    try:
        report = summarize_month(provider, first, found, config.sanitize, stats)
    except LLMError as exc:
        print("LLM 调用失败：%s" % exc, file=sys.stderr)
        return 1
    if config.sanitize and stats.total:
        print("脱敏：%s" % stats.format())
    path = write_monthly_report(report, reports_dir, [d for d, _ in found], len(missing))
    print("月报已生成：%s" % path)
    _maybe_sync(config, "monthly", month_label(args.date), path)
    return 0


def _maybe_sync(config, report_type: str, date_str: str, path: Path, label: str = None) -> None:
    if not config.remainder_sync:
        return
    sync_report(
        config.remainder_url, report_type, date_str, path.read_text(encoding="utf-8"), label
    )


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "report":
        return cmd_report(args)
    if args.command == "weekly":
        return cmd_weekly(args)
    if args.command == "monthly":
        return cmd_monthly(args)
    if args.command == "init":
        return run_init(args.yes)
    if args.command == "install-cron":
        return run_install_cron(args.yes)
    if args.command == "uninstall-cron":
        return run_uninstall_cron()
    return 2


if __name__ == "__main__":
    sys.exit(main())
