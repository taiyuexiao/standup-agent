# 模块：summarizer（LLM 总结层）

> 状态：✅ 稳定（M2：缓存接入 + provider 加固）
> 最近更新：2026-09-13

## 摘要
两级 LLM 总结：session 级结构化摘要（做了什么/改了什么/问题/待办）→ 日级汇总，跨 session 按任务聚类合并。另含第三级：周报聚合已生成的日报（`src/highagent/weekly.py`，WEEK prompt）。

## 动机
日报质量的核心。用户每天跟多个 agent、开多个 session，简单拼接摘要没有价值；按任务聚类合并才是「不用自己回忆」的关键。

## 范围与非范围
- 范围内：session 级摘要（含 `problems` 字段）、日级汇总、跨 session 任务聚类、「明日计划」推断（标注「（推断）」）
- 明确不做：不用规则识别问题（纯 LLM 语义提取）；不做工时估算（v2 参考 cc-session-tools 思路）

## 上下游依赖
- 上游：extractor、store（M2 缓存）
- 下游：renderer

## 关键接口与运行时信息
- 关键文件：`src/highagent/summarizer/core.py`、`prompts.py`（两级提示词）、`providers/deepseek.py`（urllib 直连，零第三方依赖）
- 对外接口：`build_transcript(messages, max_chars, sanitize=True, stats=None)`（脱敏在送给 LLM 前完成，见 modules/sanitizer.md）/ `summarize_session(provider, activity, max_chars, store=None, sanitize=True, stats=None) -> (SessionSummary, cache_hit)` / `summarize_day(provider, target, summaries) -> DailyReport` / `get_provider("deepseek")`；provider 接口 `complete_json(system, user) -> dict`
- LLM provider 可插拔且可配置：`config.toml` 的 `llm_provider`（预设 deepseek/moonshot/openai，均为 OpenAI 兼容协议）+ `llm_model`/`llm_base_url`/`llm_api_key_env` 三项可选覆盖；实现在 `providers/openai_compat.py`（PRESETS 预设表）；API key 三级读取：环境变量 → `~/.config/highagent/.env` → 报错（变量名随配置/预设）
- 长 session 截断：`max_session_chars` 配置（默认 20000），超限时优先丢最早的助手消息、保留用户消息
- 输出加固：剥 markdown fence、JSON 解析失败重试一次、LLM 输出中的 API key 字面值替换为 `***`
- 缓存：session 级摘要按内容指纹缓存在 store，命中则跳过 LLM 调用；日级汇总每次重算
- 参照：vibe-log-cli 的「分会话并行分析→汇总」流程；claude-code-log 的消息分级压缩策略

## 设计决策与假设
- 「遇到的问题」从会话语义提取：明确提出的报错/不行/无效 + 需推理的（同一 bug 频繁多次问答）
- 「明日计划」从对话中未完成任务/提到的下一步推断，条目加「（推断）」标记
- 两层结构 = LLM 调用量翻倍，用户已接受（DeepSeek 成本低）
- M4 日级 prompt 收敛规则：明日计划 ≤8 条且与今日完成不重复；问题 ≤10 条按严重程度排，未解决的必须保留并排前（哪怕超条数）
- 周报（M4）：聚合已生成的日报文件而非原始会话（两级汇总的第二级）；聚合前再过一遍 sanitize_text 防御手工编辑；周报同样 ≤8/≤10 收敛规则
- 月报（`monthly.py`，2026-09-13）：同模式聚合当月日报 → `monthly-YYYY-MM.md`；MONTH prompt 复用周报收敛规则；weekly/monthly 共用 `collect_reports_in_range`
- **报告双段式 + 类别分组（2026-09-13 需求）**：每段拆「总结」（领导视角：按工作类别聚块、无技术细节）+「细节」（复盘用：现有粒度）；条目带 `category` 字段（LLM 按语义定，可参考但不限于消息的 project 字段）；收敛规则作用于 details。模型：`ReportSection(summary, details)` / `DetailItem(category, text)`；解析防御式（兼容 LLM 返回纯字符串数组）

## Bug 与问题记录

### BUG-001 DeepSeek 间歇性返回非法 JSON（2026-09-13，已解决）
- 错误行为：WHEN 调用 DeepSeek 做 session 摘要 THEN 偶发返回 markdown fence 包裹或截断的非法 JSON，解析失败
- 期望行为：WHEN 同样条件 THEN 系统 SHALL 稳定解析出结构化摘要
- 不可破坏的行为：WHEN 加重试逻辑 THEN 正常 JSON 响应 SHALL CONTINUE TO 一次成功不重复调用
- 根因：模型偶发输出 fence 包裹/超长截断
- 解决方式：`providers/deepseek.py` 剥 fence + 解析失败重试一次 + `max_tokens=8000`
- 验证方式：修复后三次全量跑（约 20 次调用）零失败

### BUG-002 验证用 API key 被带进摘要和日报（2026-09-13，已解决）
- 错误行为：WHEN 会话记录中含 API key 字面值（如命令行 env 赋值被 wire.jsonl 记录）THEN LLM 摘要引用该 key，落进 cache.db 和日报 md
- 期望行为：WHEN 同样条件 THEN 系统 SHALL 在输出侧把 key 字面值替换为 `***`
- 不可破坏的行为：WHEN 加输出过滤 THEN 正常摘要内容 SHALL CONTINUE TO 不受影响
- 根因：无任何脱敏层
- 解决方式：provider 输出侧 key 字面值替换；删除污染的旧 cache.db 并重新生成日报
- 验证方式：泄漏扫描（src/、config、cache.db、日报、plist）全部干净
- 遗留：仅覆盖 key 字面值；密码等其他敏感信息未覆盖（见已知限制，M4 脱敏需提前）

## 已知限制与待办
- [ ] 长 session 的超上下文压缩策略（当前为 20000 字符截断，参照 claude-code-log detail levels 可升级）
- [x] 聚类质量已用真实数据验证（09-13 日报：6 session 跨 3 个项目聚类准确，「（推断）」标注正常）
- [x] 敏感信息进日报——已由 sanitizer 输入侧解决（见 modules/sanitizer.md）
- [x] 「明日计划」/「遇到的问题」日级收敛（M4）：明日计划 12→8 条、重复消除；问题 23→18 条、未解决置顶
- [ ] ⚠️ 周报条目上限 LLM 服从度差：输入内容多时模型不严格守 ≤8/≤10（下周计划实测 19 条）；后续可做程序端截断兜底（需先让 LLM 给未解决项加标记）
- [ ] 缓存驱逐副作用：交替跑不同日期会互逐 session 缓存（每 session 只留最新指纹）；同一天重跑不受影响；可优化为 session+日期 复合 key

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建 | 项目启动 |
| 2026-09-13 | 两级总结 + DeepSeek provider 实现，端到端生成首份真实日报 | M1 |
| 2026-09-13 | 接入 store 缓存；provider 加固（剥 fence/重试/key 掩码） | M2、BUG-001、BUG-002 |
| 2026-09-13 | 周报聚合（weekly.py + WEEK prompt）；日级 prompt 收敛优化 | M4 |
| 2026-09-13 | 报告双段式（总结/细节）+ category 分组；ReportSection/DetailItem 模型演进，防御式解析 | 用户需求：日报结构改造 |
