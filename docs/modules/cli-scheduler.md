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
- 定时：launchd plist `~/Library/LaunchAgents/com.highagent.daily.plist`，每晚 22:00，ProgramArguments = `.venv/bin/highagent report`（绝对路径），日志 `~/.local/share/highagent/cron.log`；当天已生成则跳过（查 store 运行记录），`--force` 强制

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

## 已知限制与待办
- [x] M1 `report` 命令完成（含 `--date/--agents/--output/--dry-run/--force`）
- [x] M2 `init` 向导、`install-cron` 完成并实测（launchctl 已加载，每晚 22:00）
- [x] M4 `weekly` 命令（ISO 周一为周起点；聚合 `~/daily-reports/` 已有日报，缺失天跳过并注明）
- [x] ⚠️ cron 环境依赖 `.env` 提供 key——用户已手动写入 `~/.config/highagent/.env`（0600），明晚 22:00 起 cron 可正常调 LLM
- [ ] `weekly` 未进 launchd：若需周日自动出周报，可在 plist 增加每周触发（当前只能手动跑）

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建 | 项目启动 |
| 2026-09-13 | `report` 命令实现并端到端验证 | M1 |
| 2026-09-13 | `init`/`install-cron`/`uninstall-cron` 实现并实测；.env key 回退机制 | M2、BUG-001 |
| 2026-09-13 | `weekly` 命令实现并验证（聚合 09-12/09-13 两份日报出首份周报） | M4 |
