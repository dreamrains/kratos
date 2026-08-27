# Gate D 当前 digest R01–R06 / R09 授权冻结（未执行 Provider）

日期：2026-08-26

## 结论与边界

本冻结单只申请两个互相独立、可精确计数的真实 Provider 执行。当前仍为 **Provider 0 次**，Gate D 仍是“已审阅，非发布候选”。本文件不授权提交、合并、推送、部署、切根、删除历史实现、重跑失败批次或处理 `artifacts/`、`tmp/`。

| 项目 | 当前事实 |
|---|---|
| 分支 / HEAD | `rebuild` / `787534486052af805ab487b41b96f73bc4b1d996` |
| release source digest | `sha256:98e6005607dac86e4fe2c403e0e1560cf216e8b35065d9d89e892f7161dbc2e4`（346 个受控条目） |
| 受控源码改动 | `scripts/acceptance/route_a_gate_c_journey.py`、`tests/test_route_a_journey_countable.py` 与两个 Gate D candidate；没有在预检后继续修改受控源码 |
| 用户资产 | 既存未跟踪 `artifacts/`、`tmp/`；未暂存、未删除、未改写 |

## 零调用门禁

- 断网式目标矩阵：`API_BASE=http://127.0.0.1:9`、假 key、`GOLDEN_LIVE_SMOKE=0`；`61 passed in 173.44s`。
- `python -m compileall -q src scripts/acceptance`：通过。
- `git diff --check`：通过；只有 Git 的 LF→CRLF 工作副本提示，没有 whitespace error。
- R01–R06 preflight：`ready=true`、`errors=[]`、总上限 18、同一 source digest。
- R09 preflight：`ready=true`、`errors=[]`、`provider_calls=0`、总上限 36、同一 source digest。
- 预检的规范调用形式是 `python -m scripts.acceptance.route_a_provider_preflight`。一次直接按文件路径启动在导入阶段因 `ModuleNotFoundError: scripts` 退出，尚未进入 preflight，更未创建客户端或调用 Provider；随后按模块形式重跑通过。

## 冻结一：R01–R06 判断纪律批次

- candidate：`tests/acceptance/route_a_gate_d_r01_r06_candidates.json`。
- candidate SHA-256：`sha256:42e49c150d2d0bfb8d8ffaacb670d030437516abd7d5ffdca49cfcee0c4d9249`。
- 模型：`openai/deepseek-v4-flash`。
- 请求：`temperature=0.0`、`timeout_seconds=120`、`response_format={"type":"json_object"}`、`max_tokens_ladder=[2000,8000,32000]`。
- 阶梯语义：每档只有一次请求；仅前档 `finish_reason=length` 才进入下一档；任何非截断响应即停止该场景。该冻结阶梯是预算内的有界截断恢复，不授权失败重试。
- 场景顺序：R02、R03、R04、R01、R05、R06；每场景最多 3 次，总计最多 18 次。某场景失败时，净化记录该失败后继续尚未执行的其余场景；不得补跑已经结束的场景。

| 场景 | 冻结数据 SHA-256 | prompt SHA-256 |
|---|---|---|
| `R02_paired_before_after` | `savings_card_before_after=e110c7e9e4abe5e21cede1e99a77e8f8a6827ef562a773eea16482808f6dce37` | `sha256:ce3a489e2e2fe0c52d670b996558e5cf26fd610ff1edb74043d2497f5e68dec7` |
| `R03_dirty_cross_promotion` | `game_cross_promotion=063f5415f490f90967b48d2e29972b3d2e1b908335aeb4a6420a90fb2eb19f83` | `sha256:980727a4567acc13a8d0227a477f1e2771f3e88a7bae9542f994622e95be4b9c` |
| `R04_game_a_synthesis` | `game_a_rewarded_video=cd70017a106f6f2a64ff81bab7c75f4b8936745931679fd4782c414db1088ff7`; `game_a_in_app_purchase=fe1644834de2c3495870ea9780d9a866bf780126368c3128924725647399624e`; `game_a_banner=21919b8480488a3a24a19b27e75f8bf5ee9c9d36b3003e2f6d823cc154b39a8a` | `sha256:469349d64f70d04c6107b0073689781a0fbf7b3e99060d0522e529a416cd840e` |
| `R01_retention_curve` | `game_b_retention=63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0` | `sha256:85af8c9c7320ad6f906683facdc43570b6449ed1eb3f482ca6638c798af6fb2b` |
| `R05_relationship_scope` | `savings_card_orders=9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`; `savings_card_user_payments=cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03` | `sha256:2f3103f89767535d9509c9b931eb4cad652f3412c4e6f2a63de3ed903c41694d` |
| `R06_long_term_value_cohort` | `savings_card_user_payments=cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03` | `sha256:1c22ed1548b54abf6218de897810f3218b2609fb1424ac14243d4bf2e4a75f1e` |

唯一收据路径（当前不存在）：`docs/audit/2026-08-26-gate-d-r01-r06-current-digest-batch-report.json`。该执行不得写 R09 报告或其他新报告路径。

### R01–R06 精确授权文案

```text
我授权 Gate D 当前 digest 的 R01–R06 判断纪律批次：仅在 source digest sha256:98e6005607dac86e4fe2c403e0e1560cf216e8b35065d9d89e892f7161dbc2e4 上，使用 openai/deepseek-v4-flash，按冻结顺序执行 R02_paired_before_after、R03_dirty_cross_promotion、R04_game_a_synthesis、R01_retention_curve、R05_relationship_scope、R06_long_term_value_cohort；每场景按冻结阶梯 [2000,8000,32000] 逐档各单次请求，仅前档 finish_reason=length 才升档，任何非截断响应即停止该场景，每场景至多 3 次、总计至多 18 次 Provider 调用；使用 2026-08-26-gate-d-r01-r06-r09-authorization-freeze.md 冻结的 candidate SHA-256、数据 hash、prompt hash、temperature=0、timeout=120 秒与 response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-26-gate-d-r01-r06-current-digest-batch-report.json。预检不通过则零调用；批内某场景失败时记录失败后继续其余尚未执行场景；除冻结的 length 阶梯升档外不重试、不换模型、不回退、不补跑。
```

## 冻结二：R09 系统完整性与高级工具路由旅程

- candidate：`tests/acceptance/route_a_gate_d_journey_r09_routing_candidate.json`。
- candidate SHA-256：`sha256:c453290f97d994199ffd9fbc624a80689bac8965f444c9e672b952003c3b71e2`。
- 冻结问题 UTF-8 SHA-256：`sha256:2eae4212b36927bfa62a78a29ffde03bfabdef6764512defd260013378f80929`。
- 数据：`game_b_retention=sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0`。
- 模型与请求：`openai/deepseek-v4-flash`、`temperature=0.0`、`timeout_seconds=120`、每轮冻结阶梯 `[2000,8000,32000]`、`round_cap=12`；最多 36 次。
- 验收语义：`contract.acceptance_mode=routing_integrity`；必须在真实 AgentLoop 中真实执行 `load_data` 与 `curve_fitting`；无 error event；轮数不超过 12；`final_answer_numeric_anchors=[]` 且报告中的锚点 verdict 必须为 `not_required`。这保持历史 R09 的“系统完整性 + 高级工具实际路由”结案标准，不把反复不稳定的软收尾最终文本改造成 publication 硬门槛，也不削弱默认 `publication` 旅程。
- 零调用 preflight 不实例化 AgentLoop，因此完整运行时 prompt 还不存在，不能诚实给出逐轮 `prompt_sha256`；本冻结以 candidate hash、问题文本 hash、数据 hash 和 source digest 绑定输入。获授权执行后，唯一净化报告必须记录每轮实际 `structure[].prompt_sha256` 与 `tools_sha256`。
- 失败边界：预检失败则零调用；旅程执行中首次结构错误、Provider 请求错误、错误事件或越过冻结轮次即停止该旅程。不得再运行同一旅程。

唯一收据路径（当前不存在）：`docs/audit/2026-08-26-gate-d-r09-routing-integrity-report.json`。该执行不得写 R01–R06 报告或其他新报告路径。

### R09 精确授权文案

```text
我授权 Gate D 当前 digest 的 R09 系统完整性与路由旅程：仅在 source digest sha256:98e6005607dac86e4fe2c403e0e1560cf216e8b35065d9d89e892f7161dbc2e4 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop 执行 R01_retention_curve_routing_journey 恰好 1 次；轮次至多 12，每轮按冻结阶梯 [2000,8000,32000] 逐档各单次非流式请求，仅该档 finish_reason=length 才升档，总计至多 36 次 Provider 调用；使用 2026-08-26-gate-d-r01-r06-r09-authorization-freeze.md 冻结的 candidate SHA-256、问题文本 hash、game_b_retention 数据 hash、temperature=0、timeout=120 秒与 routing_integrity 契约（真实执行 load_data 与 curve_fitting、无错误事件、轮数不超上限、final_answer_numeric_anchors=[] 且最终文本数值锚点 not_required），并仅写入 docs/audit/2026-08-26-gate-d-r09-routing-integrity-report.json。预检不通过则零调用；执行失败即停止该旅程；除冻结的 length 阶梯升档外不重试、不换模型、不回退、不补跑。
```

## 授权前停止点

只有用户逐字粘贴上述某一段授权文案，才执行对应的一个批次或旅程；两段授权互不蕴含。授权前不运行任何带 `--execute` 的命令，不创建两个目标报告，也不把离线通过称为当前 digest 的 Provider 或 Gate D 通过证据。
