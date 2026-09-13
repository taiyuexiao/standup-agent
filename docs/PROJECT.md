# HighAgent 项目总览

> GitHub：https://github.com/taiyuexiao/standup-agent （仓库名 standup-agent，包/CLI 名沿用 highagent）
> 本文件是项目文档的入口：先读这里，再按需读 docs/modules/ 下的模块文档。
> 更新纪律：每完成一个模块或处理一个变更，当轮更新「变更日志」和受影响的索引条目。

## 一句话说明
本地 Python 工具：扫描本机多个 AI coding agent 的当日会话活动，用 LLM 自动生成当日工作日报（markdown），省去人工回忆与整理。

## 技术栈与关键约定
- 语言：Python（本地运行，产品级质量目标）
- LLM：可插拔 provider，首发 DeepSeek；API key 只走环境变量 `DEEPSEEK_API_KEY`，**绝不写入配置/代码/对话**
- 配置：`~/.config/highagent/config.toml`，由 `highagent init` 交互式向导生成
- 输出：`~/daily-reports/YYYY-MM-DD.md`
- 目录约定：`src/highagent/{collectors,extractor,summarizer,renderer,store,cli}`

### 核心设计原则（不可协商）
1. **「今日」= 消息级时间戳归属**：今日新建的 session + 老 session 里今日继续的对话都算；默认本地自然日 0 点切分，日界可配置
2. **「做了什么」= 两级 LLM 总结**：session 级结构化摘要（含 problems 字段）→ 日级汇总 + 跨 session 按任务聚类合并
3. **扫描范围 = 配置的 `enabled_agents`**：按需启用、随时增删，不全量探测本机
4. **「遇到的问题」纯靠 LLM 语义提取**，不用规则（各 agent 错误格式千差万别，规则维护成本高）
5. 「明日计划」由 LLM 推断并标注「（推断）」，用户可手改

## 模块索引
| 模块 | 文档 | 状态 | 一句话摘要 |
|---|---|---|---|
| collectors | [modules/collectors.md](modules/collectors.md) | 🚧 | 各 agent 会话日志的插件式解析层（kimi_code ✅，其余 M3） |
| extractor | [modules/extractor.md](modules/extractor.md) | ✅ | 消息级时间过滤，产出「当日活动集」 |
| summarizer | [modules/summarizer.md](modules/summarizer.md) | ✅ | 两级 LLM 总结：session 摘要 → 日级汇总+聚类 |
| renderer | [modules/renderer.md](modules/renderer.md) | ✅ | 三段式 markdown 日报渲染 |
| store | [modules/store.md](modules/store.md) | ✅ | SQLite 薄缓存：session 摘要按内容指纹复用 |
| sanitizer | [modules/sanitizer.md](modules/sanitizer.md) | ✅ | LLM 输入侧脱敏：key/token/密码/私钥 → 占位符 |
| cli+scheduler | [modules/cli-scheduler.md](modules/cli-scheduler.md) | ✅ | report/init/install-cron 全实现；launchd 每晚 22:00 已安装 |

状态约定：🚧 开发中 / ✅ 稳定 / ⚠️ 有已知问题 / 🗑 已废弃 / ⬜ 未开始

## 里程碑
- **M1 最小链路**（✅ 2026-09-13）：kimi collector + extractor + summarizer(DeepSeek) + renderer + `report` 命令，已用本机真实数据端到端跑出首份日报
- **M2 成本与自动化**（✅ 2026-09-13）：store 缓存（二次运行 6/6 命中）、init 向导、launchd 定时已安装
- **M3 数据源扩展**（✅ 2026-09-13）：6 家 collector 全实现；zcode/opencode 真实数据验证，cursor/claude/codex 夹具验证（本机未验证）
- **M4 打磨**（✅ 2026-09-13）：脱敏层提前落地（sanitizer）；周报聚合（`weekly`）；日级 prompt 收敛（明日计划 ≤8 去重、问题未解决置顶）
- 后续：cursor/claude/codex 真机数据复核；周报条目程序端截断兜底；codex .zst 支持

## 变更日志
| 日期 | 类型 | 摘要 | 涉及模块 |
|---|---|---|---|
| 2026-09-13 | 新增 | 项目启动：完成需求 grill 与调研，落盘文档骨架，开工 M1 | 全部 |
| 2026-09-13 | 新增 | M1 完成：kimi collector + extractor + summarizer + renderer + report 命令端到端跑通，真实数据生成首份日报（6 会话/144 条消息） | collectors、extractor、summarizer、renderer、cli |
| 2026-09-13 | 新增 | M2 完成：store 缓存（指纹机制实测正确失效/命中）、init 向导、install-cron（launchd 已装）；修复 cron plist 漏参数、DeepSeek 非法 JSON、key 泄漏三个 bug | store、cli、summarizer |
| 2026-09-13 | 新增 | 脱敏层从 M4 提前落地：sanitizer 模块接入 summarizer 输入侧，7 类规则 + 缓存指纹版本化；09-13 日报 4 处密码 1 处 key 已掩码 | sanitizer、summarizer、store |
| 2026-09-13 | 新增 | M3 完成：zcode/opencode（共享 SQLite 基类）真实数据验证，cursor/claude_code/codex 夹具验证；多源端到端日报（09-12 含 zcode 任务） | collectors |
| 2026-09-13 | 新增 | M4 完成：`weekly` 周报聚合（两级汇总第二级）；日级 prompt 收敛（明日计划 12→8 条去重、问题未解决置顶） | summarizer、renderer、cli |
| 2026-09-13 | 新增 | LLM provider 配置化：deepseek/moonshot/openai 三预设 + model/base_url/key 变量名覆盖；修复 TOML fallback 解析器吃行内注释隐患；25 测试全过 | summarizer、config |
| 2026-09-13 | 新增 | 全局命令入口：`~/.local/bin/highagent` 符号链接 + zshrc PATH；新增 README.md 作为安装/分发入口 | cli |
| 2026-09-13 | 修复+新增 | 父子会话归并通用机制（修复 kimi 子代理漏读 bug：消息 210→315）；日报/周报双段式（总结+细节）+ 按类别分组 | collectors、summarizer、renderer |
| 2026-09-13 | 新增 | 开源发布：GitHub 仓库 taiyuexiao/standup-agent（public，MIT）；README 重写为完整使用说明；推送前脱敏 scrub（sanitizer.md 中的真实密码案例改为泛化描述） | 全部 |

## 关键问题与解决
- **「今日」语义**：用户既有今日新开的 session，也有老 session 今日续聊——过滤单位必须是消息级时间戳而非 session 创建时间
- **本机数据实况（2026-09-13 实测）**：Kimi Code 6 会话（最全）、ZCode 1 会话、OpenCode 1 会话；Claude Code/Codex/Cursor 本机无实际会话数据，按文档格式实现 parser + 测试夹具，标记「本机未验证」
- **Cursor 特殊风险**：`state.vscdb` 的 `ItemTable` 明文存 `cursorAuth/accessToken`，解析输出必须过凭证黑名单；其格式近两年变过 3 版，parser 需兼容新旧
- **系统 Python 仅 3.9.6**（无 Homebrew/pyenv，pip user-site 被禁）：代码保持 3.9 兼容（`from __future__ import annotations`、tomllib 缺失时内置迷你 TOML 回退），安装走项目内 `.venv` + setup.py shim
- **敏感信息会进日报（M1/M2 两次实证，已解决）**：首份日报出现会话里的明文密码；M2 验证用的 API key 也通过 wire.jsonl 命令记录被 LLM 引用进摘要——已由 sanitizer 模块在 LLM 输入侧掩码（见 modules/sanitizer.md），provider 输出侧掩码作兜底

## 待处理 / 后期处理
- [x] ~~用户手动操作：写 DEEPSEEK_API_KEY 到 ~/.config/highagent/.env~~（用户已完成，0600，cron 自明晚 22:00 起可用）；已贴入对话的旧 key 仍建议吊销重发
- [x] ~~脱敏层提前~~（已于 2026-09-13 落地为 sanitizer 模块）
- [ ] 浏览器历史作为数据源（v2，信噪比低，第一期明确砍掉）
- [ ] 飞书/钉钉/邮件推送
- [ ] 周报程序端截断兜底（LLM 对条目上限服从度差，需先让未解决项带标记）
- [ ] launchd 增加每周触发（周日自动出周报，当前 weekly 只能手动跑）
- [ ] cursor/claude_code/codex 真机数据复核（当前仅夹具验证）
- [ ] 「打工人日」日界预设（如凌晨 3 点前算昨天）

## 可参考的类似项目
- [vibe-log-cli](https://github.com/vibe-log/vibe-log-cli)：整体架构蓝本（会话发现→脱敏→并行总结→报告），脱敏层设计
- [cc-session-tools](https://github.com/Suto-Michimasa/cc-session-tools)：日报四段式模板、工时估算思路
- [claude-code-log](https://github.com/daaain/claude-code-log)：JSONL → 压缩 Markdown 管道、消息分级压缩策略
- [ccusage](https://github.com/ccusage/ccusage) / [CASS](https://github.com/Dicklesworthstone/coding_agent_session_search)：多 agent 日志格式权威对照、provider 插件式架构

## 后续优化方向
- 差异化点：Kimi Code / ZCode 等国产 CLI 的会话解析在开源界是空白
- 日报写作风格个性化（喂用户写作样本）
