# Data Agent V2 Slice 5C4A：Provider-neutral 浏览器验收与规划恢复

- **日期**：2026-08-14
- **状态**：Implemented；实际浏览器终验因控制层安全策略阻塞，未签发 PASS receipt
- **基线提交**：`77a6b67`（`feat(v2): add explicit budgeted workbench planning`）
- **分支**：`codex/data-agent-v2`

## 1. 本切片解决什么

Slice 5C3C 已把 Planner 接入工作台，但当时的浏览器旅程依赖人工操作，且没有固化 Provider 失败、显式重试和规划上下文超限。5C4A 将这些状态做成 provider-neutral fixture、可验证观察合约和回归测试；它不调用真实 Provider，也不把浏览器活动升级为产品完成。

## 2. 失败后重试不变量

规划失败是持久化终态，绝不自动重试。重试必须经过：

```text
failed plan
  -> 用户点击“重新估算规划（不调用模型）”
  -> 保留原 planning_input_id 和完整回答
  -> 展示新的输入 token 预算
  -> 用户点击“确认并重新规划（调用模型 1 次）”
  -> 新 client_request_id + 新一次性 authorization
  -> Planner 最多调用 1 次
```

同一个 `planning_input_id` 可以拥有多个失败的派生尝试，但最多只能存在一个非失败派生计划。每个尝试必须使用新的 request identity 和 authorization；同一 request 重放只能恢复原记录，不能再次调用 Planner。

本切片实际发现并修复了两个缺陷：

1. 失败响应渲染时会清空 `planning_input_id`，页面可能丢失已持久化回答的绑定；
2. 服务端此前禁止失败派生计划使用同一回答进行显式重试，导致新授权仍返回 409。

## 3. 上下文超限

`planning_context_too_large` 页面必须显示：

- 预计输入 token；
- 模型上下文窗口；
- 预留输出 token；
- 可用输入 token；
- “未裁剪任何内容”的明确说明。

超限估算不签发 authorization、不调用 Planner，也不缩短问题、数据画像或已保存回答。固定的超限 fixture 只用于触发状态，不形成产品级字符或 token 限制。

## 4. Provider-neutral 浏览器合约

固定旅程按累计计数验证以下 checkpoint：

1. `loaded`：0 次 Planner、0 个授权；
2. `estimated`：估算后仍为 0；
3. `needs_input`：第一次明确确认后恰好 1 次；
4. `answer_estimated`：完整回答保存与估算不增加调用；
5. `failed`：第二次明确确认后恰好 2 次；
6. `failure_stable`：失败停留不自动增加调用；
7. `retry_estimated`：显式重试估算仍为 2 次；
8. `completed`：再次明确确认后恰好 3 次并完成分析；
9. `refreshed`：刷新恢复不增加调用。

回答完整性使用写入前后 SHA-256 相等和非空字符计数验证，不设置长度阈值。fixture 内的 Planner 是确定性假实现，`provider_calls` 永远为 0；其调用计数只用于发现隐藏重试。

该旅程只是 `unified_analysis_entry` 的规划证据片段。它尚未覆盖同一场景矩阵中的停止、运行中发送、会话隔离等全部交互，因此不能生成完整的 `browser_interaction_journey` PASS receipt。

## 5. Gate E / Gate F 的最终职责

旧 `Gate E` 名称和“浏览器打开即产品通过”的聚合语义继续删除。其有价值目标分别落入：

- `sse_transport_contract`：事件顺序、终态互斥和增量内容；
- `browser_interaction_journey`：真实 DOM、点击、输入、覆盖式任务面板和图文邻接；
- `refresh_persistence_journey`：URL 身份、持久化答案、失败/完成恢复和会话隔离。

旧 `Gate F` 不恢复，替换为 `real_provider_analysis_journey`：

- 必须绑定当前 source digest、实际模型和明确的授权引用；
- 授权清单逐场景写明确切允许调用次数；`needs_input` 场景把首次规划与回答后重规划分别计数；
- 不允许隐式 retry、补跑或复用旧 receipt；
- 记录实际问题、数据版本、计划路由、SSE 终态、答案块、图表和第一失败阶段；
- 真实旅程之后仍需独立 `human_semantic_review`，逐维评审问题理解、方法适配、统计严谨性、结论校准、金字塔结构、图表价值和建议质量。

浏览器层或真实 Provider 层都不能单独得出产品 PASS；所有当前源码 receipt 齐备后也只进入 `ready_for_human_decision`，根入口切换仍需单独决策。

## 6. 验收状态

- 新增 provider-neutral fixture、浏览器观察 validator 与只读校验 CLI；
- 规划回答失败后的身份保留与显式重试已由 store、HTTP API 和页面合约回归覆盖；
- 上下文超限的精确信息和零授权/零调用已由 fixture API 回归覆盖；
- 实际浏览器已观察到估算 0 次调用、`needs_input`、7040 字符回答完整保存、失败稳定以及 `planning_input_id` 保留，并据此发现服务端重试冲突；
- 修复后重跑时，浏览器控制层拒绝继续访问本地地址。按 fail-closed 原则，本次实际浏览器终验为 `blocked`，此前部分观察不拼接、不复用为 PASS receipt；
- 真实 Provider 调用次数：0。

## 7. 下一步

Slice 5C4B 在浏览器控制可用时重新从当前 source digest 独立执行完整规划旅程，并补齐统一入口的停止、运行中发送、会话隔离和刷新交互。只有得到完整的当前源码浏览器/刷新证据后，才进入精确次数授权的 `real_provider_analysis_journey`；未获得用户授权前不得调用真实 Provider。
