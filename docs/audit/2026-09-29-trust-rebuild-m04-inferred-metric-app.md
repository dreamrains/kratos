# M04 推断列与当前计划关系：Provider 禁用 app 正反收据

日期：2026-09-29。实施树 `codex/trust-rebuild-20260927@4bb7f85` 加保留的未提交 M04 工作树修正；供体 `main@b181646` 未写入。本收据对应[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)包 B 的 M04 局部验证，不升级 R3/R4/R5 全局出口。

## 检查与控制身份

- 已核 worktree/HEAD、`.venv/Scripts/python.exe` 和既有 `scripts/testing/run_p7_browser_rehearsal.py`。控制路线预选 `local_http_api`，Provider 禁用；新目录 `tmp/m04-inferred-metric-app-20260929-r2` 原先不存在，端口 18750 原先无 listener。
- 仅用既有演练服务入口；本轮演练 launcher SHA-256 `695B0C01CF66EB3E4DE24C2D08DDB6035FA7B8322AA58722F602126EAE7E39C7`，两轮 HTTP 控制器 `tmp/m04_inferred_http_probe.py` SHA-256 `768F3BAAB7D3028BC2F1E96B42B17D5C2C15323D0033A9BAE7C6F5E6833A6864`。服务 exec session `64201`、监听 PID `2736`；前后健康均 `ok=true/provider_enabled=false`，结束后服务和 listener 已停止。
- 同会话 `855f0251969a`；v1 `F-HYP.csv` 与 v2 `F-HYP-FLAT.csv` 各上传一次，返回 ticket 文件名/SHA 已与文件核对。两轮各一个 `turn_start` 和一个 `turn_end=completed`；durable run state 均 `completed`，确认未悬挂。
- 结果 `tmp/m04-inferred-metric-app-20260929-r2/m04-inferred-http-result.json` SHA-256 `61A7403BF4C310AF9C7CFA1A6BD3CD76B70813053D64B0B1F4C1ABBF6806A41E`。同目录 `runtime.jsonl` 共 22 条，SHA-256 `F5EACAFE549E9F2088AC93E390FDE083C8472421F9B6427CC99FC45FE530CD5F`；`forbidden_provider_transport=0`，实际 Provider initiated **0**。Markdown 导出存在，SHA-256 `BD0146326D2140331CC0F90C618A806482B0A897CDD7B90B5B51DD5502D45F7F`，两轮 canonical assistant 正文均在导出中。

## 独立判据与结果

| 判据 | 原始回执 / 宿主结论 | 判定 |
| --- | --- | --- |
| v1 真实列与描述性支持 | `analyze_time_series` 只传 `{name:hyp}`；摘要结果 `inferred_columns.value_col=amount`、3 点、范围 10—20、slope 5、direction up。当前 plan `spec_945e46a3ef7e` 的 `h1` 有一条同版回执关系 `supported`。 | 本地 app 正例通过。 |
| 错指标提案 | 同一 EvidenceRecord 的模型候选把 `trend_slope` 当指标；当前 plan `h1` 保留 `relation_candidates.reason=metric_not_target`，其它假设未随之升级。 | 错指标负例通过；正确的宿主直接描述关系仍保留。 |
| v2 旧版与当前平坦 | v2 新 `version_id`/fingerprint；原 v1 `h1` 失去关系并为 `stale`。当前 plan `spec_7d2ec47d6e0c` 的工具再次只传 `{name:hyp}`，结果实际列仍为 `amount`，3 点均为 10、slope 0、direction flat；当前 `h1` 获描述性 `refuted` 一条，错 `trend_slope` 提案再次为 `metric_not_target`。 | 旧版负例和当前关系正例通过。 |
| 显式列与推断列冲突 | 在途 `receipt_verified_descriptive_directions` 已拒显式/推断列不一致；本轮将同一拒绝规则用于 `receipt_verified_hypothesis_measurements`，防止另一条提案路径借冲突列获支持。`tests/test_hypotheses.py` 定向 18 passed。 | E1 通过；该人为冲突输入未由 app 脚本生成。 |

首个 `tmp/m04-inferred-metric-app-20260929-r1` 是另一个保留的结果身份：三轮控制器在 v2 后又发一轮请求，造成新 plan `spec_d3030ceca736` 却无本轮新测量；该第三轮不能和前两轮拼成当前计划闭合。收紧为上面的两轮冻结并更正错误提案使用当轮真实 ID 后，使用全新 r2 目录、端口和服务完整重跑；未重写 r1 收据。

该 E3 是 Provider 禁用的正常 app HTTP 上传→AgentLoop/工具→SSE→会话/导出路径，不是浏览器 picker、视觉或刷新证据；这些 UI oracle 为 `unassessed`。它也不证明自然模型会生成正确关系提案、全部 M01—M06 通过或 M04 开放解释质量。当前修正只允许宿主从同版摘要回执确认实际数值列，不按模型散文别名猜事实。
