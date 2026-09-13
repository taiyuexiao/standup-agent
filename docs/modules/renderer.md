# 模块：renderer（日报渲染）

> 状态：✅ 稳定（M1）
> 最近更新：2026-09-13

## 摘要
把 summarizer 的日级汇总渲染成三段式 markdown 日报，写入 `~/daily-reports/YYYY-MM-DD.md`。

## 动机
用户自用，无公司模板；结构固定为三段式，模板可配置。

## 范围与非范围
- 范围内：三段式结构「今日工作/学习任务 · 明日工作/学习计划 · 遇到的问题」；按日期归档
- 明确不做：推送到飞书/钉钉/邮件（后续模块）；HTML 报告（vibe-log 有，我们不需要）

## 上下游依赖
- 上游：summarizer
- 下游：用户（读 markdown）

## 关键接口与运行时信息
- 关键文件：`src/highagent/renderer/markdown.py`
- 对外接口：`render_markdown(report) -> str` / `write_report(report, output_dir, output=None) -> Path`；周报：`render_weekly_markdown(weekly) -> str` / `write_weekly_report()`
- 输出路径：日报 `~/daily-reports/YYYY-MM-DD.md`，周报 `~/daily-reports/weekly-YYYY-Www.md`（头部注明聚合了哪些日报、跳过哪些天）；可用 `--output` 覆盖；已存在时跳过，`--force` 重写
- 参照：cc-session-tools 的 `~/daily-reports/` 归档惯例

## 设计决策与假设
- 模板可配置但第一期只内置三段式

## Bug 与问题记录
暂无

## 已知限制与待办
- [ ] 自定义模板支持

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建 | 项目启动 |
| 2026-09-13 | 三段式渲染与归档实现，首份真实日报落盘 | M1 |
| 2026-09-13 | 周报渲染（聚合标注、跳过天注明） | M4 |
| 2026-09-13 | 双段式渲染：`### 总结`（`- **类别**：概括`）+ `### 细节`（按 category 分小标题分组，组序按首现） | 用户需求：日报结构改造 |
