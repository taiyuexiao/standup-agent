# 模块：collectors（会话解析层）

> 状态：✅ 稳定（6 家全部实现：kimi_code/zcode/opencode 真实数据验证；cursor/claude_code/codex 夹具验证、本机未验证）
> 最近更新：2026-09-13

## 摘要
每个 AI coding agent 一个 collector 插件，从各家的本地会话存储中提取对话，输出统一消息模型。是全部数据源的入口。

## 动机
各家 agent 的会话存储格式完全不同（JSONL / SQLite / 混合），需要一个插件式解析层把差异收敛掉，让下游只面对一种消息模型。

## 范围与非范围
- 范围内：kimi_code（M1）、zcode、opencode、cursor、claude_code、codex（M3）；只读取本机数据，只读不写
- 明确不做：浏览器历史（信噪比低，v2 再议）；不全量探测——只加载配置中 `enabled_agents` 的 collector

## 上下游依赖
- 上游：各 agent 本地存储（见下「数据流」）
- 下游：extractor

## 关键接口与运行时信息
- 关键文件：`src/highagent/collectors/base.py`（Collector 抽象基类 + `parse_iso_timestamp()`）、`__init__.py`（注册表，6 家全注册）、`kimi_code.py`、`sqlite_base.py`（`connect_readonly()`：只读 URI 连接，失败则复制 db+wal+shm 到临时目录）、`session_db.py`（zcode/opencode 共享基类 `SessionDbCollector`）、`zcode.py`/`opencode.py`（薄子类）、`cursor.py`、`claude_code.py`、`codex.py`
- 对外接口：`get_collector(name: str) -> Collector`、`has_collector(name)`；`Collector.collect() -> List[Message]`；`Collector.session_titles() -> Dict[str, str]`
- 测试：`tests/test_collectors.py` 9 个 unittest 用例（纯标准库，夹具在临时目录现造）；`python3 -m unittest discover -s tests`
- 对外接口：`get_collector(name: str) -> Collector`；`Collector.collect() -> List[Message]`；`Collector.session_titles() -> Dict[str, str]`
- 统一消息模型：`Message(role, timestamp, content, session_id, agent, project)`，timestamp 为本地时区 aware datetime（`src/highagent/models.py`）
- 各 agent 存储实况（2026-09-13 本机实测）：

| agent | 路径 | 格式 | 时间字段 | 本机数据 |
|---|---|---|---|---|
| kimi_code | `~/.kimi-code/sessions/wd_*/session_*/agents/main/wire.jsonl` | JSONL，16 种事件类型 | 毫秒 epoch（`time`/`createdAt`） | ✅ 6 会话 |
| kimi_work | `~/Library/Application Support/kimi-desktop/daimon-share/daimon/runtime/kimi-code/home/`（Kimi 桌面端 Kimi Work 模式的内嵌独立 home，与 CLI 零重叠） | 同 kimi_code 的 wire.jsonl | 毫秒 epoch | ✅ 4 会话（ctitle-* 旁路已过滤） |
| workbuddy | `~/.workbuddy/projects/<工作区>/<session-id>.jsonl` + `workbuddy.db`（标题） | JSONL（OpenAI Responses 风格） | `timestamp` 毫秒 epoch | ✅ 1 会话（09-14 活跃） |
| 千问办公 qwen_work | `~/Library/Application Support/QwenWorkCN/data/agents.db` | SQLite（drizzle：chats/messages/projects） | 毫秒 epoch（待实测） | ❌ 零对话数据 |
| 豆包 | IndexedDB LevelDB（只有会话标题列表，无正文无时间戳） | — | — | ❌ **不支持**（正文在服务端） |
| zcode | `~/.zcode/cli/db/db.sqlite` + `cli/log/zcode-YYYY-MM-DD.jsonl` | SQLite+嵌套 JSON | 毫秒整数 | ✅ 1 会话 |
| opencode | `~/.local/share/opencode/opencode.db` | SQLite+嵌套 JSON | `time_created` 毫秒 | ✅ 1 会话 |
| cursor | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` | SQLite（composerHeaders + cursorDiskKV） | 毫秒 | ❌ 无实际对话 |
| claude_code | `~/.claude/projects/<项目>/<uuid>.jsonl`（文档标准） | JSONL | ISO `timestamp` | ❌ |
| codex | `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`（文档标准） | JSONL（注意 .zst 变体） | 目录按日期 | ❌（未登录过） |

- kimi_code 解析要点（M1 实测修正）：真实用户消息 = `context.append_message` 且 `message.role=="user"` 且 `origin.kind=="user"`（`injection`/`skill_activation`/`task` 均为噪声，须排除）；助手回复 = `context.append_loop_event` 中 `event.type=="content.part"` 且 `part.type=="text"`（`think` 推理内容排除）；用户消息按 `message.id`、助手按 `part.uuid` 去重；`profile.bind` 的 system prompt 天然不进提取结果；`~/.kimi-code/session_index.jsonl` 是全局索引
- zcode/opencode 库表结构几乎一致（疑同源 fork），共享 SQLite 基类

## 设计决策与假设
- 插件式架构参照 CASS 的 provider 模式；新增 agent = 新增一个插件 + 配置启用
- **父子会话归并（通用机制，`base.py` 的 `merges` + `pop_merges()`）**：子会话消息并入父会话（session_id 改写为父 id、按时间戳排序、project/title 取父会话），在 collector 层完成，下游无感知；指纹基于归并后消息集。各家实查结论：
  - kimi_code：有 `agents/agent-N/` 子代理目录（用户消息 origin 为 `system_trigger`），合并所有 `agents/*/wire.jsonl`
  - zcode：优先 `session.parent_id`，session 表缺行时用 `~/.zcode/cli/agents/sess_<父>/agent_<子>/` 目录结构兜底
  - opencode：只走 `parent_id`（本机全 NULL）；cursor：有 `isSubagent` 标记但无父子关联字段，暂摊平
  - claude_code：Task 子转录 `isSidechain=true` 内联在同一 jsonl，天然并入；codex：无父子概念
- cursor parser 兼容新旧两版格式（ItemTable → cursorDiskKV/composerHeaders 变迁），凭证防护用白名单查询（`LIKE 'bubbleId:%'` + 显式排除 `cursorAuth/%`），全代码无通配扫表——宁可少取不碰凭证键；bubble 无 `createdAt` 时回退 composerHeaders 时间戳
- claude_code/codex/cursor 本机无数据可验证，按文档+开源参照实现，配测试夹具，标记「本机未验证」
- M3 实测结论：zcode 的 assistant 报错消息（带 error 字段、无 text part）自然丢弃；opencode 库的 account/credential 表（含 access_token 列）不触碰；codex `session_meta` 的 payload 是扁平结构；codex `.jsonl.zst` 压缩归档警告跳过（保持零依赖）
- zcode 数据模型（2026-09-13 实证）：**session 表不是全集**（可能只有部分顶层会话），message 表的 `session_id` 分组才是；subagent 会话命名 `sess_subagent_agent_*`，父子关系体现在 `~/.zcode/cli/agents/sess_<父>/agent_<子>/transcript.jsonl` 目录结构；UI 只显示顶层会话，collector 摊平后会出现"用户看不到的 session"（如 1 次调研 = 1 主 + 3 子）；`directory` 字段实测为 `default`，无法作项目归属
- ⚠️ 手动查 zcode 库时必须复制 WAL 再读，直接 `mode=ro` 连活库会丢最新数据（曾因此误判 session 表只有 1 行）
- 所有 collector 对「目录/库不存在」优雅返回空（用户可能没装某 agent）
- 路径平台适配（2026-09-13）：每家抽 `default_root/default_db_path(home, platform, environ)` 小函数；kimi/zcode/claude/codex 主目录 dotdir 天然跨平台；opencode Windows 探测 `%APPDATA%`→`%LOCALAPPDATA%`；cursor 三分支（darwin `~/Library/Application Support/`、win32 `%APPDATA%`、linux `~/.config/`）；init 探针复用同一组函数

## Bug 与问题记录

### BUG-001 kimi_code 子代理对话被漏读（2026-09-13，已解决）
- 错误行为：WHEN kimi 会话存在 `agents/agent-N/` 子代理目录 THEN collector 只读 `agents/main/wire.jsonl`，子代理对话全部丢失（本机 7 个 session 中 4 个有子代理）
- 期望行为：WHEN 同样条件 THEN 系统 SHALL 把同一 session 下所有子代理的消息归并进该 session
- 不可破坏的行为：WHEN 归并子代理 THEN 主会话消息提取规则（origin.kind 过滤、id 去重）SHALL CONTINUE TO 不变
- 根因：wire.jsonl 的 glob 写死 `agents/main/`
- 解决方式：归并机制通用化（见设计决策「父子会话归并」），kimi 侧 glob 放宽到 `agents/*/` 按时间戳合并
- 验证方式：本机消息数 210→315；30 个单元测试全过

### BUG-002 zcode subagent 会话摊平导致日报平铺（2026-09-13，已解决）
- 错误行为：WHEN zcode 一次任务产生 1 主 + N 子代理会话 THEN 日报按 N+1 个独立 session 平铺总结
- 期望行为：WHEN 同样条件 THEN 系统 SHALL 把子会话归并到父会话，日报只出现父会话一条
- 不可破坏的行为：WHEN 归并 THEN 子会话消息内容 SHALL CONTINUE TO 完整保留参与总结
- 根因：collector 按 message 表 session_id 分组，未处理 parent_id/目录父子关系
- 解决方式：zcode 双路径归并（parent_id 优先、`cli/agents/` 目录兜底）
- 验证方式：09-13 dry-run 显示 4 session 归并为 1（DSH 调研），日报不再平铺

## 已知限制与待办
- [x] M1 kimi_code（真实数据验证：7 会话/180 条消息，噪声泄漏 0）
- [x] M3 全部 6 家实现（zcode 22 条/opencode 4 条真实验证；cursor/claude/codex 夹具验证）
- [ ] cursor/claude_code/codex 待真机出现数据后复核字段
- [ ] codex `.zst` 压缩归档未解析（需引入 zstd 依赖或调系统命令，暂未做）
- [ ] 助手消息极端重复场景（如 compaction 重放 content.part）目前只按 uuid 去重，未做内容级去重
- [ ] zcode 重复发送的消息按不同 message id 忠实提取为多条（数据源实况，不去重）
- [ ] zcode 按天日志 `cli/log/zcode-YYYY-MM-DD.jsonl` 未解析（主路径走 SQLite）

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建 | 项目启动 |
| 2026-09-13 | kimi_code collector 实现并用本机真实数据验证通过 | M1 |
| 2026-09-13 | zcode/opencode（共享 SessionDbCollector）+ cursor + claude_code + codex 实现；多源端到端验证（09-12 日报含 zcode 任务） | M3 |
| 2026-09-13 | 父子会话归并通用机制（6 家逐一实查/实现）；修复 kimi 子代理漏读、zcode subagent 平铺 | BUG-001、BUG-002 |

## 已知限制与待办（补充）
- [ ] kimi 归并后单 session 可能超 `max_session_chars` 截断（session_4fc865a5 达 7.9 万字符）；主会话对子代理的引用摘要与子代理原文并存，靠 LLM 去重
- [ ] cursor 子会话归并缺真实数据支撑（有 `isSubagent` 无关联字段）
- [ ] qwen_work 时间戳单位未实测（毫秒假设，本机零数据）；projects/local_projects 两表并存目前只 join projects
- [ ] workbuddy user 消息提取依赖 `<user_query>` 标签稳定存在（input_text 几乎全是 system-reminder 注入）；有新版本数据时复核
