# Data Agent V2 Slice 5B3A：Run-scoped 多轮事实账本

- **日期**：2026-08-13
- **状态**：Complete（未提交）
- **基线提交**：`5893e58`（`feat(v2): add unified workbench and durable stop`）
- **分支**：`codex/data-agent-v2`

## 1. 为什么不直接实现 steer

当前 `V2FactStore` 把 `commitments.json` 作为 session 级覆盖文件，各 runtime 又使用整 session 的 Commitment/Event/Finding 计算 Projection。若直接把运行中消息排到同一 session 的下一轮：

- 新一轮 Commitment 会覆盖上一轮 Commitment；
- 上一轮 interrupted/system_failed core Commitment 可能让下一轮永远不可发布；
- 完成状态不再是当前 run 的事实投影，而会受到历史轮次污染。

因此直接添加“发送到运行中”按钮只是交互伪装。Slice 5B3A 先建立 run-scoped append-only 事实边界，Slice 5B3B 才接入 durable queued steer。

## 2. 目标

- Commitment 改为 append-only journal，不再 session 级覆盖；
- 每条 Commitment 绑定唯一 `run_id`、`turn_id`；
- Runtime/Executor/停止协议只用当前 run 的 Commitment、Event、Finding 计算 Projection；
- 同一 session 可顺序执行多个 turn，历史 completed/interrupted 事实不能污染新 run；
- turn blocks 继续按 turn 独立恢复。

## 3. 硬不变量

1. Commitment journal 只追加；相同 Commitment ID 的不同 run/turn/content 必须冲突；
2. `read_run_facts(run_id)` 是 runtime Projection 的唯一事实入口；
3. 当前 run 只能看到绑定当前 run 的 events 和绑定其 Commitment 的 findings；
4. 审计可读取整个 session，但 runtime 不得用 session 全量事实判定当前 run 是否可发布；
5. 不迁移或兼容旧 V2 测试会话；当前仍是未切主入口的 V2 canary；
6. 本切片不增加 steer UI/API，不宣称 Codex 式发送已完成。

## 4. 验收

- 同一 session 连续两个分析 turn 均能独立完成和恢复；
- run 1 interrupted 不阻塞 run 2 supported；
- Commitment journal 同时保留两个 run 的记录；
- runtime 源码不再通过 session 全量 `read_commitments/read_events/read_findings` 计算 Projection；
- 停止协议只中断当前 run 的 Commitment；
- 全部 V2 回归通过，不调用真实 Provider。

## 5. 实施结果（2026-08-13）

- `commitments.json` 覆盖文件已删除，改为 `commitments.jsonl` append-only journal；
- `append_commitments(run_id, turn_id, commitments)` 把每条 Commitment 绑定到唯一 run/turn；同 ID 的不同绑定或内容触发 immutable conflict；
- `read_commitments(run_id=..., turn_id=...)` 支持审计过滤，`read_run_facts(run_id)` 返回当前 run 的 Commitment、Execution Event 和 Finding；
- Slice 1/2/3/4A/4B/4C/4D/4E 与 durable stop controller 全部改用 run-scoped facts 计算 Projection；
- 日期确认恢复按 proposal 的 run 定位 Commitment，不读取 session 当前/历史混合状态；
- 同一 session 顺序运行两个真实统一 API turn 均完成，两个 turn blocks 和两条 Commitment 历史同时保留；
- run 1 interrupted、run 2 supported 的回归证明历史中断不会阻塞下一轮；
- 清理了上一提交中 `tests/test_v2_analysis_router.py` 的末尾多余空行。

## 6. 验证记录

- Run-scoped/store/停止/API 专项：`28 passed`；
- 全部 `test_v2*.py`：`174 passed`；
- JavaScript 语法、Python compileall、`git diff --check`：通过；
- 未调用真实 Provider，未生成 release receipt，未切换 `/`。

## 7. 下一切片

Slice 5B3B 可以在此账本上实现 durable queued steer：运行中发送的新消息绑定当前 run，记录 `steer_received`，在安全边界进入下一 turn。5B3B 必须明确 queued/consumed/superseded 状态，不得修改已冻结 Commitment，也不得把前端输入框变化伪装成当前 run 已重规划。
