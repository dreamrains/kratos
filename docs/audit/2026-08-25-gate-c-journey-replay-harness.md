# Gate C 旅程离线回放构架与 R07 结构测量（未执行 Provider）

日期：2026-08-25

## 目的

单次调用 Gate C 批次验证的是冻结事实包上的有界判断；旅程级 Gate C 还须验证真实工具循环（上传 → 提问 → 工具轮 → 最终回答）。按计划 §12 要求，申请授权前须先以离线回放测出每个旅程的实际调用结构。本收据交付该测量构架，全程 Provider 调用 `0` 次。

## 构架

- 模块：`scripts/acceptance/route_a_gate_c_journey.py`。
- `ScriptedJourneyClient`：按冻结脚本逐轮回放模型行为（工具调用与/或最终文本），模拟真实 Provider 的流式形态（先 `StreamTextDelta` 后 `StreamComplete`——loop 的正文发布依赖 delta 事件，这是实现中实测确认的契约）；轮次硬上限，超出即 `round_cap_exceeded` 失败而非静默成功；逐轮记录 `(system, messages)` 摘要、暴露工具 schema 数量与摘要。
- `run_journey_replay`：驱动**真实** AgentLoop、真实工具注册表与真实数据文件；数据 hash 先行校验；会话目录限定 `gate_c_journey_replay` 前缀并每次重建；收据只含结构化判定（轮数、每轮摘要、已执行工具、契约判定、错误事件摘要），不保留正文。
- 契约判定：必需工具已执行、最终回答含冻结数值锚点、无错误事件、轮数与脚本一致。
- 清单 schema：`route_a_journey_replay.v1`；试点：`tests/acceptance/route_a_gate_c_journey_r07_replay.json`。

## R07 实测结构

- 受控源码摘要：`sha256:996485ac2cd0429c4b004f65c7e94d33d236fb2f4c79bc5144095bc9ca3d5751`。
- 3 轮：`load_data`（省钱卡订单.xlsx）→ `compare_periods`（支付时间 × 售价，2026-04-07~04-21 vs 04-22~05-06）→ 最终回答（含 1818/684/71/30 锚点与边界声明）。
- 每轮暴露工具 schema `64` 项（core 激活组；总注册面 73，其余按组激活）。
- 逐轮 prompt 摘要：`1bc09ff6…` / `5b3e4622…` / `f953117f…`；工具面摘要：`cb639f96…`。
- 契约判定全过；`provider_calls=0`。

## 边界与推论

1. 脚本测的是**结构与契约机制**，不是真实模型行为；旅程级授权单因此必须按轮数上限声明预算（实际调用数入收据），不能预设精确轮数。
2. 第 2 轮起的 prompt 依赖真实模型此前的工具选择，**只有第 1 轮 prompt 可预先 hash 冻结**；离线摘要仅约束脚本回放自身的可复现性。
3. 下一块工作：旅程级可数执行器（真实 `chat_once` 语义包裹 AgentLoop：每轮单次请求、无重试、冻结逐轮预算、调用计数与逐轮收据）+ 试点旅程授权单。

## 离线门禁

- `tests/test_route_a_journey_replay.py`：`5 passed`（含 R07 全链路回放、锚点缺失失败路径、数据/会话拒绝路径）。
- 全量 `python -m pytest tests/`：`2258 passed, 9 skipped, 3 failed`；3 个失败中 2 个为 HEAD 上即失败（此前 stash 对照已证），1 个（`test_method_playbooks`）单独运行通过、属已知顺序依赖抖动。
- `compileall`、`git diff --check` 通过。
