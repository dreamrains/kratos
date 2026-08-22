# Data Agent V2 Slice 5C3B：可恢复规划问题与回答血缘

- **日期**：2026-08-13
- **状态**：Implemented（待提交）
- **基线提交**：`0c8a639`（`feat(v2): add one-time provider authorization`）
- **分支**：`codex/data-agent-v2`

## 1. 目标

让 Planner 的 `needs_input` 成为可刷新恢复、可回答、可追溯的服务端事实，同时不把原计划重新打开为可写状态。

## 2. 不变量

- 原 `needs_input` plan 保持终态，不转回 `requested`，也不被用户回答改写；
- 问题块由 plan 的持久化 `questions` 确定性投影，每个问题有稳定 `question_id`；
- 用户回答写入独立 append-only Planning Input Ledger，绑定 source plan、问题集合和 `client_reply_id`；
- 相同 reply identity 与相同内容幂等，内容变化冲突；
- 一个 Planning Input 只能派生一个新 plan request；
- 派生规划仍需新的服务端一次性 Provider 授权，旧授权不能复用；
- 新授权绑定 planning input identity，回答变化或输入替换后不可使用；
- 回答保存动作和授权签发动作都不调用 Provider；只有创建派生 plan 才消费恰好一次授权。

## 3. API

- `POST /api/v2/sessions/{session}/plans/{plan}/answers`：保存与稳定问题 ID 对齐的回答；
- `GET /api/v2/sessions/{session}/planning-inputs/{input}`：刷新恢复回答；
- `POST /api/v2/provider-authorizations`：可选携带 `planning_input_id`，签发绑定该回答的收据；
- `POST /api/v2/plans`：可选携带 `planning_input_id`，创建带 `parent_plan_id` 血缘的新计划。

## 4. 非目标

- 不把该流程接入工作台；
- 不在回答提交后自动签发授权或调用 Provider；
- 不执行真实 Provider；
- 不引入自由 Markdown 问答解析或自由 Python。

## 5. 实施结果

- `needs_input` plan 的恢复投影新增稳定 `planning_question` 消息块；
- 新增 append-only `PlanningInputStore`，回答与问题 ID 严格一一对应并完整持久化，不设置应用层字符或成本门槛；
- 新增回答写入与恢复 API，重复 reply identity 只恢复旧事实，不调用 Planner；
- Planner 接收结构化 `clarifications`，系统提示明确将问题、回答和数据画像视作数据；
- 新计划持久化 `parent_plan_id` 与 `planning_input_id`，一个回答只能派生一个计划请求；
- Provider 授权指纹加入 `planning_input_id`，未绑定回答的收据不能资助派生规划；
- 原 `needs_input` plan 在回答与派生后仍保持终态，未增加回写或重开路径；
- 33 项规划链路定向回归及 217 项完整 V2 回归通过；真实 Provider 调用次数为 0。

## 6. 下一切片

Slice 5C3C 再接入工作台显式旅程：用户点击“由系统选择方法”时签发一次授权并规划；若返回 `needs_input`，页面内展示问题块、保存回答，并在用户再次明确点击后使用新的授权派生计划。上传、页面恢复和失败处理均不得自动调用 Provider。
