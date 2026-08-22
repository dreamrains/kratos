# Data Agent V2 Slice 5B3B：持久化排队 Steer

- **日期**：2026-08-13
- **状态**：Completed
- **基线提交**：`2242015`（`refactor(v2): scope facts to analysis runs`）
- **分支**：`codex/data-agent-v2`
- **依赖**：Slice 5B3A run-scoped ledger

## 1. 目标

允许用户在当前分析仍运行时编辑问题并显式发送。消息不修改当前 run 已冻结的 Commitment，而是绑定当前 `session_id/turn_id/run_id` 持久化为 queued steer。当前轮达到终态后，客户端用 steer ID 请求下一轮；服务端从 steer 中的冻结方法快照重建请求，只替换问题，并在下一 turn 注册成功后将 steer 标记为 consumed。

## 2. 状态机

```text
queued -> consumed
queued -> superseded
```

- 同一 source run 只保留一个 queued steer；再次发送时旧消息变为 superseded，最新消息 queued；
- consumed 绑定目标 `turn_id`，重复消费同一目标幂等；
- source run 被用户停止时 queued steer 自动 superseded，不得在停止后自动启动；
- 当前 run 完成/失败不会篡改 steer 历史。

## 3. 硬不变量

1. 输入框变化不是 steer；必须点击“发送到下一轮”；
2. steer API 返回 `202` 前消息及冻结 resume payload 已落盘；
3. steer 必须带 expected `run_id`，防止旧页面把消息发给新 run；
4. 当前 run 的 Commitment、Finding、问题快照不得被 steer 修改；
5. 下一轮参数来自服务端持久化 resume payload，而不是消费时的 DOM；仅 `question` 替换为 steer message；
6. `steer_received` 只表示消息已持久化，不表示当前 run 已重规划；
7. 断线/刷新后 queued steer 可恢复并继续；
8. 本切片不实现当前工具中途重规划，不切换主入口 `/`。

## 4. API

- `POST /api/v2/runs/steer`：绑定活跃 run，持久化 queued steer；
- `POST /api/v2/analyze` 携带 `steer_id`：服务端恢复冻结请求、创建下一 turn、注册 run 后消费 steer；
- `GET /api/v2/sessions/{session}/turns/{turn}`：返回该 source turn 的 steer 投影，供刷新恢复。

## 5. UI

- 运行期间 Run 按钮禁用，Stop 和“发送到下一轮”独立显示；
- question 保持可编辑；点击发送后显示排队状态；
- 当前轮完成后自动进入最新 queued steer 的下一 turn；
- 刷新已完成 source turn 且仍有 queued steer 时显示“继续排队消息”按钮；
- stop 后不自动消费 steer。

## 6. 验收

- append-only steer 状态投影、幂等、supersede 和 stop 取消有回归；
- safe-boundary SSE 发出 `steer_received`，且当前 Commitment 内容不变；
- 下一 turn 使用冻结方法参数和新问题，source/target turn 均可恢复；
- 同 session 历史事实不污染下一 turn；
- 浏览器验证运行中编辑、发送、当前轮完成、下一轮自动启动、刷新恢复；
- 全部 V2 回归通过，不调用真实 Provider。

## 7. 实施结果

- 新增 append-only `SteerStore`，以 `client_request_id` 保证排队幂等，并显式投影 `queued -> consumed/superseded`；
- 活跃 run 在安全边界发布 `steer_received`，但不改写已冻结 Commitment；Stop 会先将同 run 的 queued steer 标为 superseded；
- `/api/v2/runs/steer` 在返回 `202` 前完成持久化，并在 worker 已注销后仍可对相同请求幂等返回；
- `/api/v2/analyze` 消费 steer 时仅使用服务端冻结的 resume payload，只把 question 替换为 steer message；
- 工作台支持运行中显式排队、当前轮完成后自动创建下一 turn、刷新后手动继续，以及 Stop 取消排队；
- 浏览器验收发现自动续跑若与当前 SSE 消费链同步重入会卡在开始状态；现将续跑安排到当前响应关闭后的下一宏任务，再发起 target turn；
- 定向 steer/API/页面回归 27 项通过；全部 V2 回归 183 项通过；未调用真实 Provider。
