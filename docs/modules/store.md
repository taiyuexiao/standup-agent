# 模块：store（缓存层）

> 状态：✅ 稳定（M2）
> 最近更新：2026-09-13

## 摘要
极薄的 SQLite 层：session 级摘要缓存（内容指纹为 key）+ 运行记录。

## 动机
同一天手动跑+定时跑多次、补跑历史日期时，内容没变的 session 不重复调 LLM，重跑接近零成本。

## 范围与非范围
- 范围内：session 摘要缓存（key = session id + 内容指纹）、运行记录（供「当天已跑过则跳过」判断）
- 明确不做：不引入 ORM；缓存只覆盖 session 级，日级汇总每次重算（输入是各 session 摘要，成本低）

## 上下游依赖
- 上游：summarizer（读写缓存）、cli（运行记录）
- 下游：无

## 关键接口与运行时信息
- 关键文件：`src/highagent/store/db.py`（`Store` 类、``fingerprint``）
- 存储位置：`~/.local/share/highagent/cache.db`
- 表结构：
  - `session_summaries(session_id, fingerprint, payload JSON, created_at, PRIMARY KEY(session_id, fingerprint))`
  - `report_runs(date PRIMARY KEY, path, sessions, messages, created_at)`
- 指纹 = sha256（消息数 + 逐条 `role|毫秒时间戳|content`），任何消息变化都会变指纹
- 接入点：`summarize_session(..., store=None) -> (SessionSummary, cache_hit)`；report 成功后 `record_run`

## 设计决策与假设
- 缓存第一期不做是刻意决策：M1 先验证总结质量，M2 才优化成本
- 指纹含时间戳和全文，宁可误判 miss 也不容忍脏缓存

## Bug 与问题记录
暂无

## 已知限制与待办
- [ ] 缓存无过期/清理策略（长期使用后 cache.db 会增长，量级小，暂不处理）
- [ ] 每 session 只留最新指纹（`put_session_summary` 自动清理旧指纹）：交替跑不同日期会互逐缓存导致重调 LLM；同一天重复跑不受影响。可优化为 session+日期 复合 key

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建 | 项目启动 |
| 2026-09-13 | 实现并验证：二次运行 6/6 命中缓存零 session 级 LLM 调用；指纹对真实新增消息正确失效 | M2 |
| 2026-09-13 | 指纹追加 sanitizer 版本后缀（`:san2`）；旧指纹条目自动清理 | 脱敏层提前 |
