# standup-agent

每天下班不用再回忆"我今天到底干了啥"。standup-agent 扫描你本机各个 AI coding agent 的当日会话记录，用 LLM 自动生成工作日报/周报（markdown）。

支持的会话来源：**Kimi Code、ZCode、OpenCode、Cursor、Claude Code、Codex、WorkBuddy、千问办公（QwenWork）**

> 豆包不支持：本地无对话正文存储，拿不到会话内容。

> 注意：CLI 命令名为 `highagent`（历史沿用，后续版本会统一为 `standup-agent`）。

## 它能做什么

- **自动日报**：每晚定时（或手动一条命令）把当天所有 AI 会话总结成三段式日报：今日工作 · 明日计划 · 遇到的问题
- **总结 + 细节双层**：每段先给按项目聚合的概括（可以直接发领导），再保留完整细节（自己复盘用）
- **跨会话聚类**：同一任务在多个 agent、多个会话里的记录自动合并成一条；子代理会话归并到父会话
- **隐私优先**：数据全部本地处理；发给 LLM 前自动脱敏（API key / 密码 / 私钥 → 占位符）；摘要本地缓存，内容没变的会话不重复调 LLM
- **周报**：`highagent weekly` 聚合本周日报生成周报

## 安装

要求：macOS / Linux / Windows，Python ≥ 3.9，零第三方依赖。

macOS / Linux：

```bash
git clone https://github.com/taiyuexiao/standup-agent.git
cd standup-agent
python3 -m venv .venv && .venv/bin/pip install -e .

# 让 highagent 命令全局可用（任选其一）：
pipx install .                                                     # 方式一（推荐，如有 pipx）
ln -sf "$PWD/.venv/bin/highagent" ~/.local/bin/highagent           # 方式二：符号链接（确保 ~/.local/bin 在 PATH）
```

Windows（PowerShell）：

```powershell
git clone https://github.com/taiyuexiao/standup-agent.git
cd standup-agent
py -m venv .venv; .venv\Scripts\pip install -e .

# 让 highagent 命令全局可用（任选其一）：
pipx install .                          # 方式一（推荐，如有 pipx）
# 方式二：把 .venv\Scripts 目录加入 PATH（入口为 highagent.exe）
```

## 三分钟上手

```bash
# 1. 初始化：自动探测你机器上各 agent 的会话数据，逐个问你启用哪些
highagent init

# 2. 配置 LLM key（默认 DeepSeek；写入 0600 权限的本地文件）
echo 'DEEPSEEK_API_KEY=<你的key>' > ~/.config/highagent/.env
chmod 600 ~/.config/highagent/.env

# 3. 生成今天的日报
highagent report        # → ~/daily-reports/2026-09-13.md

# 4. 安装定时任务：每晚 22:00 自动生成
highagent install-cron
```

定时任务按平台落到：macOS = launchd（`~/Library/LaunchAgents/com.highagent.daily.plist`）、Linux = crontab（带 `# highagent` 标记行）、Windows = 任务计划程序（任务名 `HighAgentDaily`）。

## 常用命令

```bash
highagent report                     # 今日日报（当天已生成则跳过）
highagent report --force             # 强制重跑（内容未变的会话走缓存，几乎零成本）
highagent report --date 2026-09-12   # 补跑/回看某一天
highagent report --agents kimi_code,zcode  # 只跑指定来源
highagent report --dry-run           # 只看提取了多少会话/消息，不调 LLM
highagent weekly                     # 本周周报 → weekly-2026-W37.md
highagent weekly --date 2026-09-08   # 补跑某周
highagent init                       # 重新配置（新增/停用 agent）
highagent uninstall-cron             # 卸载定时任务
```

## 配置（`~/.config/highagent/config.toml`）

```toml
# 启用哪些数据源：kimi_code / zcode / opencode / cursor / claude_code / codex / workbuddy / qwen_work
enabled_agents = ["kimi_code"]

day_start_hour = 0            # 日界：默认 0 点；设 3 则凌晨 3 点前算"昨天"
output_dir = "~/daily-reports"
max_session_chars = 20000     # 单会话喂给 LLM 的字符上限（超出截断，优先保留你的提问）
sanitize = true               # 发给 LLM 前脱敏

# LLM：预设 deepseek / moonshot / openai，或任意 OpenAI 兼容端点
llm_provider = "deepseek"
# llm_model = "deepseek-chat"
# llm_base_url = "https://api.deepseek.com"
# llm_api_key_env = "DEEPSEEK_API_KEY"
```

## 工作原理

```
各 agent 本地会话存储（JSONL/SQLite，只读）
  → collectors 插件解析（统一消息模型，父子会话归并）
  → extractor 按消息时间戳筛出"今日活动"（跨午夜按消息逐条归属）
  → sanitizer 脱敏（key/密码/私钥 → 占位符）
  → summarizer 两级 LLM 总结（会话级 → 日级跨会话聚类）
  → renderer 渲染三段式 markdown（总结 + 细节）
```

关键设计：「今日」按**消息级时间戳**算——今天在老会话里继续聊的内容也算今天；「遇到的问题」靠 LLM 语义提取（包括"同一个 bug 反复问了好几轮"这种需要推理的），不用规则。

## 文件位置

| 东西 | 位置 |
|---|---|
| 日报 / 周报 | `~/daily-reports/` |
| 配置 | `~/.config/highagent/config.toml` |
| LLM key | `~/.config/highagent/.env`（0600） |
| 摘要缓存 | `~/.local/share/highagent/cache.db` |
| 定时任务日志 | `~/.local/share/highagent/cron.log` |

## 隐私与安全

- 所有原始数据只读本机文件，零网络探测；只有脱敏后的文本发给配置的 LLM
- Cursor 数据库里明文的登录 token（`cursorAuth/*`）在解析层就被白名单排除
- 建议仍留意：日报写给自己看没问题，发出去前扫一眼细节段

## 平台说明

- 各 agent 数据目录按平台解析：Kimi Code / ZCode / Claude Code / Codex 全平台都在用户主目录同名 dotdir；OpenCode 在 Windows 上探测 `%APPDATA%`/`%LOCALAPPDATA%`；Cursor 在 Windows 为 `%APPDATA%\Cursor\...`、Linux 为 `~/.config/Cursor/...`
- highagent 自身配置/缓存/日志全平台统一放 `~/.config/highagent/` 与 `~/.local/share/highagent/`
- Windows 上 `.env` 的 0600 权限设置语义有限（NTFS 无 POSIX 权限位），文件内容仍只写本机

## 开发与文档

项目文档：`docs/PROJECT.md`（模块索引、变更日志、关键问题）+ `docs/modules/`（每模块一份：为什么这么做、坑与解法）。

```bash
python3 -m unittest discover -s tests   # 运行测试
```

## License

MIT
