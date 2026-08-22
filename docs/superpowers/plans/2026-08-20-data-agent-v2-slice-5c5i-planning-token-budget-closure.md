# Data Agent V2 Slice 5C5I：完整 Planner 请求 token 预算闭环

- **日期**：2026-08-20
- **状态**：实现与确定性验证完成；未提交
- **基线提交**：`ca20a81581f64f080c4384dffcb8eec8d6a9fff7`
- **当前未提交 source digest**：`sha256:3212b49e5f36fd38d51d92e5920b58a342125c763d39bae0826efda324d4a1f3`
- **本切片 Provider calls**：0

## 1. 发现

5C5H 审查 tool schema 扩张后的 token 身份时，发现 LiteLLM 对当前模型的 `token_counter(messages=..., tools=...)` 返回 348；但当前 messages JSON 为 1,274 字符，tool schema JSON 为 14,592 字符。messages 单独计数为 311，tool schema 作为 canonical text 单独计数为 4,037。

因此 native 计数只给 tools 增加了约 37 tokens，不能支持“完整请求计数”的声明。5C5G preflight 中 348 的 token 身份不完整。

已发生调用的 context window 为 1,000,000、预留输出为 8,000；即使按完整 schema 计数也远低于 992,000 可用输入，因此没有窗口越界事实。但不完整计数使 5C5G preflight 不能升级为合格 PASS 证据。

## 2. RED → 修复

RED：`2 failed, 3 passed`，证明旧实现既没有单独计算 canonical tool schema，也不会在该分项不可计数时 fail closed。

新预算计算：

1. 保留 LiteLLM native messages+tools 结果作为下限；
2. 单独计算完整 messages；
3. 对排序、紧凑 JSON 的完整 tools 计算 token；
4. 使用 `max(native_request_tokens, message_tokens + canonical_tool_schema_tokens)`；
5. 任一分项异常、负数、布尔值或非整数均 fail closed。

该方法是保守的完整请求估算，不再宣称 Provider 内部不可观察的精确计费 token。没有增加成本阈值、自动缩短 prompt、repair 或 Provider 调用。

## 3. GREEN

- planning budget：`5 passed`；
- focused planning contracts：`102 passed`；
- V2/config：`313 passed`；
- compileall：PASS；
- `git diff --check`：PASS。

当前离线候选：

- source digest：`sha256:3212b49e5f36fd38d51d92e5920b58a342125c763d39bae0826efda324d4a1f3`；
- source dirty：true；
- estimated input tokens：3,200；
- available input tokens：992,000；
- fits：true；
- schema fingerprint：`sha256:d87c12de5d78ade97697634d94b4aa12618416209a53921668ebd0d047ca1587`；
- request fingerprint：`sha256:af50de8dcd731914396d20547ce5ff4e978ff08db2398e62f62146414eaf6d76`；
- Provider calls：0；
- authorization issued：false。

证据：`docs/superpowers/evidence/2026-08-20-v2-5c5i-planning-token-budget-evidence.json`。

## 4. 边界

5C5G attempt 继续证明原 digest 上实际发生了恰好一次调用、没有自动重试且 planning 返回 ready；但其 preflight token 估算不完整，不能签发或补签 PASS receipt。

当前源码未提交，不制作可执行 preflight，不申请新 Provider 授权，不宣称 Gate F、产品完成或根入口切换。
