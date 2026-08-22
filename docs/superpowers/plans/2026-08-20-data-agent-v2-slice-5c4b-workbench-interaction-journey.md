# Data Agent V2 Slice 5C4B：工作台交互、恢复与会话隔离

- **日期**：2026-08-20
- **状态**：Implemented；provider-neutral interaction journey PASS
- **基线提交**：`a7cdec8`（`test(v2): add provider-neutral planning journey`）
- **分支**：`codex/data-agent-v2`

## 1. 目标

在不调用真实 Provider 的条件下，用真实浏览器、HTTP、SSE 和持久化账本验证统一工作台剩余的高风险交互：

- 运行期间问题输入保持可编辑；
- 消息显式排队到下一轮，当前运行不被篡改；
- 当前轮完成后在同一 session 的新 turn 自动消费排队消息；
- 停止事实先持久化，再以 `turn_interrupted` 终止事件流；
- interrupted 后不得出现 final block 或 `turn_completed`；
- 完成态和停止态刷新后按 URL 身份恢复；
- 新页面使用新 session，不得串入旧会话；
- 失败后修改输入，在同一 session 创建新 turn 重试；
- 任务面板始终默认收起并覆盖内容，而不挤压正文。

## 2. Fixture 边界

验收 Router 继续调用真实 `AnalysisRouter`、方法 runtime、Evidence Ledger、Publisher、SSE 和停止/排队控制器，只在每个语义事件后增加 1 秒延迟，以提供确定的点击窗口。

生产默认 Router 不增加延迟。依赖注入只用于 provider-neutral fixture；fixture 不实现分析逻辑、不替换停止事实，也不能调用真实 Provider。

## 3. 本切片发现并修复的问题

### 3.1 手工运行丢失会话连续性

原 `run()` 只提交方法参数，不提交当前 `session_id/turn_id`。因此同一页面在分析失败后修改输入再运行，会被服务端分配到另一个 session。

修复后的不变量：

```text
fresh page -> create one session_id
each explicit manual run -> create a new turn_id in that session
fresh page/tab -> create a different session_id
```

这使错误恢复、连续分析和会话隔离同时可验证。

### 3.2 验收夹具竞争窗口不稳定

最初 350ms 延迟不足以稳定完成“编辑草稿后停止”，运行可能先自然结束。固定为 1 秒后，停止请求能够在 commitment 已持久化、final block 尚未发布的窗口内确定获胜。

验收过程中还发现端口上残留两个旧 fixture 进程；已按 PID 和启动时间确认并只停止本次启动的进程。旧实例产生的观察全部废弃，未拼接到最终结果。

## 4. Interaction receipt

`v2_provider_neutral_interaction_journey.v1` 要求：

- `observer=actual_browser`；
- 当前 `source_digest`；
- 三个互不相同的 session：steer、stop、isolation/error recovery；
- `provider_calls=0`；
- 浏览器 console error 为空；
- 所有交互观察均为明确 `true`，缺一即失败。

该 receipt 的 observed interactions 为：

- `upload`
- `live_progress`
- `draft_while_running`
- `queued_steer`
- `stop`
- `error_recovery`
- `session_isolation`
- `task_overlay_collapsed`
- `refresh_restore`

receipt validator 明确输出 `release_readiness_claimed=false`。它不能替代 planning journey、真实 Provider 旅程或人工语义评审。

## 5. 实际浏览器结果

最终重跑使用三个隔离 session：

1. **停止旅程**：运行中输入可编辑；停止后答案为空；刷新仍为 `interrupted`；恢复的问题是服务端冻结的原问题，不是运行中草稿；console error 为空。
2. **排队续轮**：消息持久化后当前分析继续；随后同 session 新 turn 自动执行；目标问题和三个答案块刷新后完整恢复；任务面板前后均默认收起；console error 为空。
3. **错误恢复/隔离**：无效字段使当前 turn 失败；改回有效字段后在同一 session 新 turn 成功；该 session 与停止、续轮 session 均不同；刷新后答案一致；console error 为空。

服务端最终事实与浏览器观察一致：停止 turn 为 `interrupted` 且 0 blocks；续轮 source/target 均为 `finalized` 且各 3 blocks；错误恢复后的新 turn 为 `finalized` 且 3 blocks。真实 Provider 调用次数为 0。

## 6. 当前边界与下一步

5C4B 只让 interaction 子旅程通过。当前 source digest 仍没有完整 planning browser PASS，因此不能签发统一入口完整 `browser_interaction_journey` PASS receipt，更不能切换 `/`。

下一步 Slice 5C4C 应在当前源码重新执行 5C4A 的规划全旅程，并把 planning 与 interaction 两份独立观察合成为 unified browser/refresh receipts。完成后再评估根入口替换条件。真实 Provider 调用仍必须由用户另行给出精确次数授权。
