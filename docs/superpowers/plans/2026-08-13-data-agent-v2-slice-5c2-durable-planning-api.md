# Data Agent V2 Slice 5C2：持久化规划 API

- **日期**：2026-08-13
- **状态**：Completed
- **基线提交**：`13a48e5`（`feat(v2): add bounded structured planner`）
- **分支**：`codex/data-agent-v2`

## 1. 目标

把 Slice 5C1 的 provider-neutral Planner 接入一个独立、可恢复的服务端规划流程。规划与分析执行仍是两个动作：Planner 只能生成经服务端校验的方法计划，`AnalysisRouter` 仍是唯一方法运行入口。

## 2. 状态机

```text
requested -> ready -> consumed
requested -> needs_input
requested -> unsupported
requested -> failed
```

- `requested` 必须在 Provider 调用前落盘，记录问题、数据画像、调用授权和 client request identity；
- 同一 `client_request_id`、相同内容的终态重试直接返回旧记录，不增加 Provider 调用；
- 若进程在 `requested` 后中断，不得用旧授权隐式重试；客户端必须用新的 request identity 与授权重新规划；
- `ready` 计划由 `plan_id` 消费，目标 turn 绑定后不可改写；
- 其他终态不能执行分析。

## 3. Provider 授权

规划请求必须同时包含：

- `provider_calls_authorized: 1`；
- 非空 `provider_authorization_ref`；
- 唯一 `client_request_id`。

服务端使用 `chat_once`，恰好发起一次请求，不自动 repair、重试或 fallback。无论成功或失败，终态记录 `provider_calls: 1`。单元和 API 测试使用假 Planner，真实 Provider 调用次数为 0。

## 4. API

- `POST /api/v2/plans`：注册请求、执行一次规划并持久化终态；
- `GET /api/v2/sessions/{session}/plans/{plan}`：恢复规划结果；
- `POST /api/v2/analyze` 携带 `plan_id`：从 Plan Ledger 恢复服务端参数，注册 run 后消费计划。

消费请求不能提交或覆盖 `analysis_kind`、metric、group、time field 等方法字段。最终 turn 的 request context 持久化 `plan_id`，用于追溯。

## 5. 本切片不做

- 不在工作台自动发起规划；
- 不执行真实 Provider；
- 不允许模型生成自由 Python；
- 不实现 needs_input 的对话回答协议；
- 不切换 `/` 或删除旧运行时。

## 6. 验收

- request-before-call、精确一次调用、终态持久化和幂等回归；
- requested 崩溃态不能复用旧授权；
- ready plan 只能消费一次并绑定 target turn；
- plan_id 执行只使用持久化参数，忽略消费请求注入字段；
- needs_input、unsupported、failed 不可执行；
- source plan 与 target turn 均可刷新恢复；
- 完整 V2 回归通过，真实 Provider 调用为 0。

## 7. 实施结果

- 新增 append-only `PlanStore`，实现 `requested -> ready/needs_input/unsupported/failed` 与 `ready -> consumed`；
- 规划请求在 Planner 调用前落盘；终态记录授权引用、模型身份和本次授权消费的调用数；
- 同一 client request 的终态重试只恢复旧记录；中断在 requested 的请求不能隐式重试；同一会话内授权引用不能资助两个请求；
- 新增 `POST /api/v2/plans` 与 plan 恢复 API，严格要求 `provider_calls_authorized == 1`，Planner 使用 `chat_once`；
- `POST /api/v2/analyze` 可消费 ready `plan_id`，只使用服务端持久化的方法参数，消费请求不能覆盖方法、字段或问题；
- 规划上下文绑定上传源 SHA-256；同名文件被替换时拒绝执行并保持计划 ready；
- target turn 的恢复投影包含来源 plan 及 `plan_id`，不新增第二个运行事实写入者；
- 21 项 Planner/Plan Store/API 定向回归和 205 项完整 V2 回归通过；测试使用假 Planner，真实 Provider 调用次数为 0；
- 工作台尚未接入该 API。当前 `provider_authorization_ref` 仍由调用者提供；在 UI 自动规划前，需要服务端签发的一次性授权身份，不能把任意前端字符串当作真实用户授权证明。

## 8. 下一切片

Slice 5C3 应先实现服务端一次性 Provider 授权收据和 `needs_input` 可恢复消息块，再把“由系统选择方法”作为工作台中的显式用户动作接入。不能直接在上传或页面加载时自动调用 Provider，也不能在失败后自动 repair。完成真实 Provider 旅程仍需用户另行给出精确调用次数授权。
