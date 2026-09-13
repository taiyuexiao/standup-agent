# 模块：remainder-sync（Remainder 同步）

> 状态：✅ 稳定
> 最近更新：2026-09-13

## 摘要
report/weekly/monthly 成功生成后，通过 HTTP 幂等推送一份到 Remainder 应用的报告栏目（日报/周报/月报）。

## 动机
用户的 Remainder 应用有报告栏目，希望 standup-agent 的产物（含每晚 cron 自动生成的）自动出现在那里，不用手动复制。

## 范围与非范围
- 范围内：生成后推送（幂等：同 type+date 覆盖更新）、Remainder 未运行时优雅跳过
- 明确不做：无重试/队列（Remainder 未跑就跳过，不事后补推——可手动 `report --force` 补）；反向（Remainder 调 standup-agent）由 Remainder 侧 `POST /api/reports/standup` 实现，不在本模块

## 上下游依赖
- 上游：cli（生成成功后 `_maybe_sync` 钩子）
- 下游：Remainder 服务 `http://127.0.0.1:3210`（接口契约见下）

## 关键接口与运行时信息
- 关键文件：`src/highagent/reminder_sync.py`（`sync_report(base_url, report_type, date_str, markdown, label=None) -> bool`）
- 配置：`remainder_sync = false`（默认关）、`remainder_url = "http://127.0.0.1:3210"`；init 向导末尾询问
- 接口契约（Remainder 侧 M35 实现）：
  - `POST /api/reports` 带 `{type, date, title, content_markdown}` 一次写全——201 新建即完成；200（已存在）补 `PATCH /api/reports/{id}` 保证内容最新
  - date 规范：daily=YYYY-MM-DD、weekly=当周周一 YYYY-MM-DD、monthly=YYYY-MM；标题：「AI 日报 2026-09-13」「AI 周报 2026-W37」（ISO 周标签，与 Remainder 侧一致）「AI 月报 2026-09」
- 失败语义：连接拒绝→「Remainder 未运行，跳过同步」exit 0；HTTP 错误→警告不炸；超时 10s

## 设计决策与假设
- POST 一次带全字段（而非 POST+PATCH 两段）：避免触发 Remainder 服务端 weekly 的 LLM 预填浪费；200 幂等路径仍补 PATCH 保内容最新
- Remainder 端 content 是 Tiptap JSON，markdown→Tiptap 转换在 Remainder 侧做（`content_markdown` 字段），highagent 只送 markdown 原文——Tiptap 知识不跨项目泄漏

## Bug 与问题记录
- `urllib.error.HTTPError` 是 `URLError` 子类，except 顺序错了会把 404 误报为「未运行」——已修正（HTTPError 在前），单测覆盖

## 已知限制与待办
- [ ] 无重试/outbox：cron 时 Remainder 未启动则当天漏推，需手动补
- [ ] POST 201 路径依赖 Remainder 返回码契约（实测已验证；若 Remainder 改返回 204 会落入警告分支）

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块实现；mock + 真实集成验证（双向链路：Remainder 按钮调 highagent、highagent 推送 Remainder） | Remainder 集成（Remainder 侧见 remainder 仓库 docs/modules/M35） |
| 2026-09-13 | 周报标题统一为 ISO 周标签；POST 一次带全字段消除 Remainder 侧 LLM 预填浪费 | 遗留修复 |
