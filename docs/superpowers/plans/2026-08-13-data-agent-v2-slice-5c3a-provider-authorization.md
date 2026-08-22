# Data Agent V2 Slice 5C3A：服务端一次性 Provider 授权

- **日期**：2026-08-13
- **状态**：Implemented（待提交）
- **基线提交**：`524ba22`（`feat(v2): add durable planning API`）
- **分支**：`codex/data-agent-v2`

## 1. 问题

Slice 5C2 已能限制 Planner 使用 `chat_once`，但 `provider_authorization_ref` 与 `provider_calls_authorized` 仍由规划请求直接上报。后端只能检查“字符串非空、数字等于 1”，不能证明该授权来自一次独立、明确的用户动作，也不能在 Plan Ledger 之前原子地阻止跨请求复用。

## 2. 决策

新增 session-scoped、append-only `ProviderAuthorizationStore`。授权和规划拆成两个 API 动作：

```text
explicit client action -> issued -> consumed by one client_request_id
```

- `POST /api/v2/provider-authorizations` 只签发收据，不创建 Planner，也不调用 Provider；
- 签发必须显式提交 `confirm_provider_call: true` 与 `provider_calls_authorized: 1`；
- 收据绑定 `purpose=analysis_planning`、上传文件名、源 SHA-256、问题文本和 session；
- `POST /api/v2/plans` 只接受服务端签发的 `provider_authorization_id`，不再接受客户端自报授权引用；
- 收据在 Planner 调用前消费；Provider 失败不返还授权，也不自动重试；
- 同一 `client_action_id` 的相同签发请求幂等恢复旧收据，内容变化则冲突；
- 同一收据由同一 `client_request_id` 重放时幂等，由其他请求消费时冲突。

## 3. 崩溃与重放语义

- 消费授权后、Plan request 落盘前崩溃：同一 client request 可幂等恢复消费并补写 request；
- Plan request 落盘后、Provider 终态前崩溃：沿用 Slice 5C2 规则，旧 request 与授权都不能再次触发 Provider；
- Plan 已进入终态：同一 request 恢复旧计划，不重新创建 Planner；
- 数据或问题在签发后变化：授权绑定校验失败，保持未消费，必须针对新内容重新显式授权。

## 4. 非目标

- 本切片不把自动规划按钮接入工作台；
- 不实现 `needs_input` 的回答/重规划协议；
- 不调用真实 Provider；
- 不提供兼容旧 `provider_authorization_ref` 请求的适配层。

## 5. 验收

- 授权签发、幂等、内容冲突、单次消费、跨请求拒绝均有状态机测试；
- 授权 API 本身不创建 Planner；
- 伪造或未知授权不能触发规划；
- 已完成/失败规划的相同请求重放不增加 Planner 调用；
- 完整 V2 回归通过，真实 Provider 调用次数为 0。

## 6. 后续边界

Slice 5C3B 应实现可刷新恢复的 `needs_input` 消息块与回答身份：回答不能改写原计划，而应生成新的规划 request，并要求新的、精确一次的 Provider 授权。完成后再把“由系统选择方法”接入工作台的显式点击旅程；页面加载、文件上传和失败恢复不得自动签发或消费授权。
