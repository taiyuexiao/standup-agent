from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 10

_TITLES = {
    "daily": "AI 日报 %s",
    "weekly": "AI 周报 %s",
    "monthly": "AI 月报 %s",
}


def sync_report(
    base_url: str, report_type: str, date_str: str, markdown: str, label: str = None
) -> bool:
    """推一份报告到 Remainder。任何失败只警告不抛错。

    POST /api/reports 带完整字段（title + content_markdown）：
    返回 201（新建）即完成；返回 200（已存在）时内容可能未更新，补一次 PATCH。
    label 用于标题（如 weekly 传 ISO 周标签 2026-W37），缺省用 date_str。
    """
    base_url = base_url.rstrip("/")
    title = _TITLES.get(report_type, "AI 报告 %s") % (label or date_str)
    try:
        status, body = _request(
            "POST",
            base_url + "/api/reports",
            {
                "type": report_type,
                "date": date_str,
                "title": title,
                "content_markdown": markdown,
            },
        )
        report_id = _extract_id(body)
        if report_id is None:
            print("警告：Remainder 返回中未找到报告 id，跳过同步。", file=sys.stderr)
            return False
        if status == 200:
            _request(
                "PATCH",
                "%s/api/reports/%s" % (base_url, report_id),
                {"title": title, "content_markdown": markdown},
            )
    except urllib.error.HTTPError as exc:
        print("警告：Remainder 同步失败（HTTP %s），不影响主流程。" % exc.code, file=sys.stderr)
        return False
    except urllib.error.URLError as exc:
        print("Remainder 未运行，跳过同步（%s）。" % exc.reason)
        return False
    print("已同步到 Remainder：%s" % title)
    return True


def _extract_id(body):
    if isinstance(body, dict):
        for container in (body, body.get("data"), body.get("report")):
            if isinstance(container, dict) and container.get("id") is not None:
                return container["id"]
    return None


def _request(method: str, url: str, payload: dict):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8")
        status = response.status
    try:
        return status, json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return status, {}
