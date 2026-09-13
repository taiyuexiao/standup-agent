# 模块：extractor（当日活动提取）

> 状态：✅ 稳定（M1）
> 最近更新：2026-09-13

## 摘要
对 collectors 产出的消息流做消息级时间过滤，产出「当日活动集」。

## 动机
承载核心原则：「今日」= 今日的消息活动，不是今日创建的 session。老 session 今天续聊的内容必须算进今天。

## 范围与非范围
- 范围内：按目标日期（默认今天，`--date` 可指定任意日）做消息级时间戳过滤；日界可配置（默认本地自然日 0 点）
- 明确不做：不做内容理解/摘要（那是 summarizer）；不做「打工人日」智能切分（v2）

## 上下游依赖
- 上游：collectors
- 下游：summarizer

## 关键接口与运行时信息
- 关键文件：`src/highagent/extractor/core.py`
- 对外接口：`day_window(target, day_start_hour) -> (datetime, datetime)` / `filter_by_day(messages, target, day_start_hour=0)` / `group_by_session(messages, titles) -> List[SessionActivity]`
- 日界配置：`config.toml` 中 `day_start_hour`（默认 0）；已验证 `day_start_hour=3` 时凌晨消息正确归入前一天

## 设计决策与假设
- 独立成模块而非并入 collectors：「今日=消息级过滤」是产品核心原则，需要单独可测
- 跨午夜 session 按消息时间戳逐条拆分到两天

## Bug 与问题记录
暂无

## 已知限制与待办
- [x] 跨午夜拆分已用真实数据验证（session 5d452718 正确拆分为 09-12→32 条、09-13→3 条）

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建 | 项目启动 |
| 2026-09-13 | 实现并通过真实数据验证（含跨午夜拆分、自定义日界） | M1 |
