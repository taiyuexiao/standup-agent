# 模块：sanitizer（脱敏层）

> 状态：✅ 稳定
> 最近更新：2026-09-13

## 摘要
在消息进入 summarizer（LLM）之前做敏感信息掩码：API key、token、密码、私钥等替换为占位符，并输出替换统计。

## 动机
M1/M2 两次实证：会话里的明文密码进了日报正文、验证用 API key 被 LLM 引用进摘要和缓存。脱敏必须挡在 LLM 调用之前（输入侧），而不是事后补救输出侧。原计划 M4，因风险实证提前。

## 范围与非范围
- 范围内：API key/token（sk-*、JWT、Bearer）、密码模式、私钥块、.env 风格赋值；替换统计上报
- 明确不做：语义级脱敏（送给 LLM 判断本身即泄露，自相矛盾）；变量名/字段名不脱敏（`users.password_plain` 这类不是秘密本身，日报需要可读性）；不对路径/项目名脱敏

## 上下游依赖
- 上游：extractor（输出当日活动集，原文）
- 下游：summarizer（build_transcript 收到的消息已脱敏）

## 关键接口与运行时信息
- 关键文件：`src/highagent/sanitizer/rules.py`（规则表 + `sanitize_text(text, stats)` + `SanitizeStats` + `SANITIZER_VERSION`）
- 接入点：`summarizer.build_transcript(messages, max_chars, sanitize=True, stats=None)`——先逐条脱敏再截断；session 级与日级看到的都是脱敏后内容
- 配置：`config.toml` 中 `sanitize = true`（默认开）
- 规则清单（按序执行，占位符防二次掩码）：

| 类别 | 规则要点 | 占位符 |
|---|---|---|
| 私钥块 | `-----BEGIN ... PRIVATE KEY-----` 整段 | `<PRIVATE_KEY>` |
| JWT | `eyJ` 开头三段式 | `<TOKEN>` |
| Bearer | `Bearer xxx`（保留头名） | `Bearer <TOKEN>` |
| API key | `sk-` 开头 16+ 位；`api_key/secret_key` 等后跟 20+ 位值 | `<API_KEY>` |
| env 赋值 | `XXX_KEY/SECRET/TOKEN/PASSWORD/PWD=值`（保留变量名） | `NAME=<TOKEN>` |
| 密码（分隔符） | `密码/口令/passwd/password/pwd` + `是/为/:/=/：` + 值 | `密码是 <PASSWORD>` |
| 密码（窗口） | 密码关键词后 15 字符内出现 6 位以上纯数字（覆盖 `密码（6位数字）`、`密码框，输 \`6位数字\`` 真实案例） | `<PASSWORD>` |

- 缓存协同：指纹追加 sanitizer 版本后缀（当前 `:san2`），规则演进时 bump `SANITIZER_VERSION` 一处即全量失效重跑；`put_session_summary` 会清理同 session 旧指纹条目
- 兜底：provider 输出侧的 key 字面值掩码保留（双保险）

## 设计决策与假设
- 放输入侧而非输出侧：敏感信息一旦发给 LLM 就算泄露，输出侧只是兜底
- 掩码用占位符而非删除：保留"这里有个凭证"的语义（如"修复了密码相关 bug"仍可读）
- 误伤可接受：实测「33528 账号」「8080/5173 端口」「v0.2.5 版本号」均正确保留；已知会误伤的形态=密码关键词 15 字符内的 6 位以上数字（如日期），按共识接受

## Bug 与问题记录
暂无

## 已知限制与待办
- [x] 验证通过：09-13 日报中的真实明文密码已掩码（端到端输出「脱敏：1 处API key、4 处密码」），cache.db 无残留
- [ ] 关键词窗口外的纯数字密码仍可能漏（完全无「密码」语境的独立数字串）；更激进规则误伤面大，暂未启用
- [ ] LLM 可能把占位符改写（如 `<PASSWORD>` → 「密码进入」），值已拦、占位符留存率依赖 LLM，可接受

## 变更历史
| 日期 | 变更 | 关联需求 / bug |
|---|---|---|
| 2026-09-13 | 模块骨架创建（从 M4 提前） | summarizer BUG-002 实证 |
| 2026-09-13 | 实现并端到端验证：14 条掩码用例 + 9 条误伤用例全过，真实日报 4 处密码掩码 | 脱敏层提前 |
