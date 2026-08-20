# Data Agent V2 Slice 5C4D：统一入口确定性收据

- **日期**：2026-08-20
- **状态**：Implemented；待提交
- **基线提交**：`865d54b`（`test(v2): compose unified browser receipts`）
- **分支**：`codex/data-agent-v2`

## 1. 目标

为 `unified_analysis_entry` 补齐三个此前只有测试、没有 source-bound release receipt 的确定性层：

- `owner_contract`
- `incident_replay`
- `sse_transport_contract`

本切片不把 pytest 数量映射成 PASS。新 oracle 实际运行真实 multi-finding runtime、读取持久化 Ledger/Projection/Publisher 状态，并独立构造停止与错误回放。

## 2. Owner contract oracle

统一入口完成旅程必须同时证明：

1. Dataset Registry 中 raw 与 analysis 版本均可读取，analysis 的 parent 是 raw；
2. Finding 的 Commitment、结果类型、方法 capability 和数据版本均与声明匹配；
3. `project_run()` 从不可变 Commitment/Event/Finding 计算出 publishable，而不是由模块写入“完成”；
4. 所有答案块 `support_refs` 都指向真实 Finding，正文不含内部 evidence marker；
5. 正文图表均由答案块引用，图表 `finding_refs` 绑定真实 Finding；
6. turn 只有在 projection publishable 且增量答案块数量与持久化块一致时才是 finalized。

任一观察不是明确 `true` 时，owner receipt 不生成。

## 3. Incident replay oracle

本切片回放五类系统性风险：

- 不受 Commitment 接受范围支持的 Finding 不得推进发布；
- 停止在安全边界获胜后，源 generator 不得继续到 final block；
- interrupted turn 必须持久化且 blocks 为空；
- 停止后的 finalized 写入必须抛出 `TurnPublicationBlocked`；
- 新 session 的 Commitment/Event/Finding 必须为空，不能读取另一 session 的事实。

这些是具体故障不变量，不是历史会话文本或 phrase-list 匹配。

## 4. SSE transport oracle

完成流实际观察：

```text
turn_started
commitment_snapshot
tool_started/tool_finished × 2
artifact_created × 2
outcome_snapshot
final_block_delta × 4
turn_completed
```

中断流实际观察：

```text
turn_started
commitment_snapshot
tool_started
outcome_snapshot
turn_interrupted
```

validator 同时要求事件集合、先后顺序、4 个增量答案块，以及完成/中断终态互斥。不能仅凭连接成功或事件数量签发 SSE PASS。

## 5. Source-bound 结果

最终源码摘要：

```text
sha256:f48187be392cc2875d4d9c6a0dca577f69f7eea379013cd77ae2990bb3d060ff
```

确定性原始证据：

- `docs/superpowers/evidence/2026-08-20-v2-5c4d-unified-deterministic-evidence.json`

对应三张 release receipts：

- `docs/superpowers/evidence/2026-08-20-v2-5c4d-unified-deterministic-release-receipts.json`

由于新增 oracle 改变了源码摘要，5C4C 的浏览器收据自动 stale。本切片随后在最终摘要完整重跑 planning 和 interaction，没有复用旧观察：

- `docs/superpowers/evidence/2026-08-20-v2-5c4d-planning-browser.json`
- `docs/superpowers/evidence/2026-08-20-v2-5c4d-interaction-browser.json`

当前摘要五张统一入口收据汇总：

- `docs/superpowers/evidence/2026-08-20-v2-5c4d-current-unified-release-receipts.json`

这五张收据没有 stale、conflict 或 incomplete。

## 6. 当前边界

统一入口的七层要求中，当前已有五层 PASS。仍明确缺少：

- `real_provider_analysis_journey`
- `human_semantic_review`

完整九场景矩阵仍有 58 项缺失，因此状态保持：

```text
not_ready
provider_calls = 0
root_switch_authorized = false
```

## 7. 下一步与授权边界

下一阶段应先设计并冻结 real-provider journey 的问题、数据、模型、token 估算、显式调用清单和停止条件，再请求用户给出精确调用次数授权。

建议首个统一入口真实旅程允许最多两个、逐次显式签发的 Planner 调用：第一次用于初始规划；只有返回 `needs_input` 时，第二次才用于保存回答后的重规划。任何失败都停止，不自动重试。未经用户确认前，本切片不会调用真实 Provider。

真实结果完成后仍需独立人工语义评审；即使统一入口七层齐备，也不能自动替代其他八个场景或授权根入口切换。
