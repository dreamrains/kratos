# Data Agent V2 Slice 5B2：持久化停止协议

- **日期**：2026-08-13
- **状态**：Complete（未提交）
- **基线提交**：`88824f4`（Slice 5B1 尚未提交）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标

为统一 V2 工作台提供无确认的一键停止。停止不是断开浏览器 SSE，而是先在服务端持久化绑定当前 run/commitment 的 `USER_INTERRUPTED` 事实和 turn 终态，再通知执行线程在下一个安全边界关闭 generator。停止成功后禁止写入 finalized 答案。

## 2. 硬不变量

1. 停止请求必须绑定 `session_id`、`turn_id`、`run_id` 和当前 Commitment；
2. API 返回成功前，`USER_INTERRUPTED` 事实及 `interrupted` turn 必须已落盘；
3. 停止与 finalized 发布使用同一原子门禁；先获得门禁的一方决定合法终态；
4. 若停止先发生，后续 finalized 写入必须失败，且不得发送 `final_block_delta`/`turn_completed`；
5. 若 finalized 已先完成，停止返回冲突，不得把完成结果倒改为 interrupted；
6. Run Projection 从事实计算 interrupted；即使安全边界前已产生部分 Finding，用户停止仍覆盖正常发布状态；
7. 前端不调用 `AbortController` 伪装停止，继续消费 SSE，直到收到 `turn_interrupted`；
8. 同一 session 不允许两个统一 V2 run 并发修改状态。

## 3. 安全边界

本切片不强杀 Python 线程。停止可在语义事件边界关闭 generator；如果统计工具正在执行，其当前原子计算可能完成并留下部分 Execution Event/Finding，但发布门禁保证它们不能形成正式答案。后续若引入可中断子进程工具，可在 ResultContract 层增加更细粒度取消。

## 4. 组件职责

- `V2FactStore`：持久化 turn control；串行化事实追加、停止和 finalized 写入；
- `ActiveRunRegistry`：只管理当前进程内的 stop signal 和活跃 run 映射，不决定完成状态；
- `ControlledAnalysisRun`：观察 runtime 语义事件，停止时关闭 generator并发送 `outcome_snapshot`、`turn_interrupted`；
- Run Projection：从 `USER_INTERRUPTED` 计算 interrupted；
- Workbench：发送一次 stop 请求并展示“正在安全停止/已停止”，不主动截断 SSE。

## 5. API

`POST /api/v2/runs/stop`

```json
{
  "session_id": "...",
  "turn_id": "..."
}
```

- `202`：停止事实已持久化；
- `409`：run 尚未到可停止边界、不活跃或已经完成；
- 重复停止对同一 interrupted run 幂等。

## 6. 不做

- steer 当前轮；
- 强杀 Python 线程或第三方库；
- 停止后发布部分分析结论；
- 将旧 `/api/chat/interrupt` 接到 V2；
- 切换主入口 `/`；
- real-provider 调用或发布收据。

## 7. 验收

- RED 回归证明“已有 Finding + USER_INTERRUPTED”投影为 interrupted；
- 停止先于发布时，finalized 写被阻断；完成先于停止时，停止返回冲突；
- 停止 API 返回前，turn 和 interruption events 可从磁盘恢复；
- controlled generator 停止后不再推进 runtime，不发送完成事件；
- 页面运行期间显示独立停止按钮，点击无确认、不使用 AbortController；
- 刷新 interrupted turn 后仍显示已停止；
- 全部 V2 回归及真实浏览器停止旅程通过。

## 8. 实施结果（2026-08-13）

- `V2FactStore` 新增 turn control，事实追加、停止预留和 turn 状态写入在当前服务进程内共享写锁；
- 一旦 stop control 为 `stop_requested`/`interrupted`，`draft`、`failed`、`finalized` 均不能覆盖 interrupted；
- `ActiveRunRegistry` 禁止同一 session 并发运行，`ActiveRun` 在停止 API 返回前写入所有当前 Commitment 的 `USER_INTERRUPTED` 事实和空块 interrupted turn；
- `ControlledAnalysisRun` 在安全边界关闭 generator，发送 `outcome_snapshot` 与 `turn_interrupted`，不发送完成块或完成事件；
- Run Projection 调整为 interruption 优先于部分 Finding，避免停止后被误投影成 supported；
- `POST /api/v2/runs/stop` 支持活跃停止和 worker 注销后的幂等 interrupted 回执；已完成 turn 的晚到停止返回冲突；
- Workbench 新增独立停止按钮，不确认、不主动断开 SSE；刷新 interrupted turn 后显示“已停止”；
- 发布矩阵的统一入口改为当前真实 `/v2-workbench`，并要求 `turn_interrupted`，禁止 interrupt 后出现 final block/turn completed。

## 9. 验证记录

### 自动化

- 停止/投影/API/页面/发布矩阵专项：`27 passed`（最终相关组合 `26 passed`）；
- 全部 `test_v2*.py`：`170 passed`；
- JavaScript 语法、Python compileall、`git diff --check`：通过；
- 竞争回归覆盖 stop control 已预留、runtime 同时尝试写 draft 的窗口；结果等待 durable interruption，而不是误发 `turn_failed`；
- 未运行真实 provider；未生成发布 receipt；未把浏览器旅程写成产品 PASS。

### 本地真实浏览器旅程

- 运行受限探索 Python，在 `tool_started(v2.run_python)` 后点击停止；
- 磁盘事件顺序为核心工具成功、探索工具开始、`USER_INTERRUPTED`、探索工具失败，证明停止发生在探索工具结束之前；
- 恢复的 turn 为 `interrupted`，`blocks=[]`，没有 `turn_completed`；
- 页面显示“已停止”，问题输入保持可编辑；刷新后恢复分析类型、问题与已停止状态，仍无答案块；
- 浏览器控制台无 error/warn；活动 overlay 的人工展开状态不改变默认收起设计；
- 本地服务、3 个 QA 上传副本及 7 个明确由 Slice 5B1/5B2 浏览器验收生成的测试会话已删除。

## 10. 剩余边界

- 当前停止是线程内协作式安全边界，不是任意指令级抢占；工具若要更快取消，应在未来改为可取消子进程/ResultContract 能力；
- `ActiveRunRegistry` 是进程内信号目录，durable interruption facts 才是恢复权威；多 worker 部署前需增加跨进程 active-run 发现，但不得把 Registry 升格为完成权威；
- steer 仍未实现；主入口 `/` 仍未切换；real-provider 分析和人工语义层仍未执行。
