# 模块：cli + scheduler（入口层）

> 状态：✅ 稳定（M2 完成）
> 最近更新：2026-09-13

## 摘要
`highagent` 命令行入口 + macOS launchd 定时任务（每晚 22:00）。

## 范围与非范围
- 范围内：`init`（交互式配置向导）、`report [--date] [--agents] [--force]`、`install-cron` / `uninstall-cron`
- 明确不做：TUI 交互界面（whathaveidone 有，非核心）

## 上下游依赖
- 上游：全部模块（编排入口）
- 下游：用户

## 关键接口与运行时信息
- 关键文件：`src/highagent/cli.py`（子命令：`report [--date] [--agents] [--output] [--dry-run] [--force]`、`weekly [--date] [--force] [--dry-run]`、`init [--yes]`、`install-cron`、`uninstall-cron`）、`src/highagent/config.py`、`src/highagent/setup_wizard.py`、`src/highagent/cron.py`、`src/highagent/weekly.py`
- 配置：`~/.config/highagent/config.toml`，含 `enabled_agents`（按需启用、随时增删）、`day_start_hour`、`output_dir`、`max_session_chars`、`sanitize`、`llm_provider`/`llm_model`/`llm_base_url`/`llm_api_key_env`（LLM 预设 deepseek/moonshot/openai + 覆盖）；配置不存在时默认启用 kimi_code 并提示
- 安装：项目内 `.venv`（系统 Python 仅 3.9.6，见「设计决策」），`pip install -e .` 需走 venv；全局入口：`~/.local/bin/highagent` 符号链接指向 `.venv/bin/highagent`（已加入 ~/.zshrc 的 PATH；注意项目目录移动后需重建链接）
- API key 三级读取：环境变量 `DEEPSEEK_API_KEY` → `~/.config/highagent/.env`（0600 权限，供 cron 无 shell 环境使用）→ 报错；install-cron 时可选把 key 写入 .env，不写 plist（plist 明文有泄露风险）
- `init` 向导：探测 6 个 agent 的本机数据实况（会话数/库文件），逐个询问启用；未探测到数据的默认 n 但可手动启用；已存在配置时询问覆盖；非 tty 时管道输入可作答案、EOF 回退默认值
- 定时：三平台分发（`cron.py`）——macOS launchd plist `~/Library/LaunchAgents/com.highagent.daily.plist`、Linux crontab（`0 22 * * *` + `# highagent` 标记行）、Windows 任务计划程序（`schtasks /tn "HighAgentDaily" /sc daily /st 22:00`，入口 `.venv/Scripts/highagent.exe`）；均每晚 22:00，当天已生成则跳过（查 store 运行记录），`--force` 强制。⚠️ Windows/Linux 分支经 mock 单测覆盖但未实机验证

## 设计决策与假设
- 定时时间用户明确要求 22:00 整
- `--date` 补跑任意一天是第一天就设计进去的（时间过滤是参数不是硬编码）
- `init --yes` 语义 = 直接覆盖为「探测到的全启用」，并打印说明

## Bug 与问题记录

### BUG-001 install-cron 生成的 plist 漏了 `report` 参数（2026-09-13，已解决）
- 错误行为：WHEN launchd 触发定时任务 THEN 裸 binary 只打印 help，不生成日报
- 期望行为：WHEN launchd 触发 THEN 系统 SHALL 执行 `highagent report` 完整命令
- 不可破坏的行为：WHEN 修复 plist THEN 手动 `highagent report` 及跳过逻辑 SHALL CONTINUE TO 正常工作
- 根因：ProgramArguments 只写了二进制绝对路径，漏了子命令
- 解决方式：`src/highagent/cron.py` 补上 `report` 参数；用 `launchctl start` 实测暴露并验证
- 验证方式：`launchctl start com.highagent.daily` 后 cron.log 出现正确的运行记录跳过日志

另注：`Path(sys.executable).resolve()` 会穿透 venv 符号链接解析到系统 Python，plist 路径生成须用 `.absolute()`。

## 已知限制与待办（跨平台，2026-09-13）
- [ ] Windows schtasks `/tr` 引号转义未实测（路径含空格时可能需 `cmd /c` 包裹）
- [ ] Windows 任务计划程序无 stdout 重定向，cron 日志在 Windows 上会丢（可考虑 report 自身写日志）
- [ ] `.env` 0600 在 Windows 无效（NTFS 无 POSIX 权限位），依赖用户目录 ACL
- [ ] Linux 精简发行版无 crontab 时只报错提示，未做 systemd timer
- [ ] kimi/zcode 等 CLI 在 Windows 的 dotdir 位置是推断，需实机确认

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建 | 项目启动 |
| 2026-09-13 | `report` 命令实现并端到端验证 | M1 |
| 2026-09-13 | `init`/`install-cron`/`uninstall-cron` 实现并实测；.env key 回退机制 | M2、BUG-001 |
| 2026-09-13 | `weekly` 命令实现并验证（聚合 09-12/09-13 两份日报出首份周报） | M4 |
| 2026-09-13 | 定时任务三平台分发（launchd/crontab/schtasks），macOS 路径回归不变性测试 | Windows 支持 |
