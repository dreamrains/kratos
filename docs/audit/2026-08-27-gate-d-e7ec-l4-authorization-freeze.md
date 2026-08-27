# Gate D `e7ec4011` L4 授权冻结（已消费；正文保留授权前快照）

日期：2026-08-27

> 状态更新：用户已逐字粘贴三段授权，三项执行均通过；结果见 [L4 执行结果与候选决定边界](2026-08-27-gate-d-e7ec-l4-execution-and-candidate-decision.md)。三段授权均已消费，不得再次执行、重试或补跑。除本状态注记外，正文保留授权前冻结事实与原始精确文案。

## 结论与公共边界（授权前冻结快照）

本冻结提供三个互相独立的精确授权段落。当前真实 Provider 调用为 **0**，三个新报告路径均不存在。本文不授权提交、合并、推送、部署、切根、删除历史实现、处理 `artifacts/` / `tmp/`，也不授权失败后的补跑。

| 项目 | 冻结事实 |
|---|---|
| 分支 / HEAD | `rebuild` / `787534486052af805ab487b41b96f73bc4b1d996` |
| release source digest | `sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc`（346 项） |
| 模型 | `openai/deepseek-v4-flash` |
| 主请求 | `temperature=0.0`、`timeout_seconds=120`、ladder `[2000,8000,32000]`；每档最多一次，仅 `finish_reason=length` 升档 |
| auxiliary（R07 / R09） | 主 / 辅助共享 exact counter；`counted_once`、`max_tokens=300`、`call_cap=6`、JSON object；每钩子至多一次、不升档、不重试 |
| 失败纪律 | 请求失败占用槽位；禁用 countable stream→sync fallback；不换模型、不做 Provider fallback、不补跑 |

无效辅助语义只允许既有本地确定性规则继续，不产生第二次 Provider 请求。

当前 digest 已有：完整集合 `2222 passed, 9 skipped`、独立九文件矩阵 `32 passed`、compileall / diff check 通过、真实本地浏览器 L3 通过。三项 preflight 均 `ready=true`、`errors=[]`；R07 / R09 均 `provider_calls=0`。

## 冻结一：R01–R06 判断纪律批次

- candidate：`tests/acceptance/route_a_gate_d_r01_r06_candidates.json`。
- candidate SHA-256：`sha256:42e49c150d2d0bfb8d8ffaacb670d030437516abd7d5ffdca49cfcee0c4d9249`。
- 顺序：R02、R03、R04、R01、R05、R06；每场景最多 3 次，总上限 18。
- `response_format={"type":"json_object"}`；场景失败时净化记录后继续其余尚未执行场景。

| 场景 | 数据 SHA-256 | prompt SHA-256 |
|---|---|---|
| `R02_paired_before_after` | `savings_card_before_after=e110c7e9e4abe5e21cede1e99a77e8f8a6827ef562a773eea16482808f6dce37` | `sha256:ce3a489e2e2fe0c52d670b996558e5cf26fd610ff1edb74043d2497f5e68dec7` |
| `R03_dirty_cross_promotion` | `game_cross_promotion=063f5415f490f90967b48d2e29972b3d2e1b908335aeb4a6420a90fb2eb19f83` | `sha256:980727a4567acc13a8d0227a477f1e2771f3e88a7bae9542f994622e95be4b9c` |
| `R04_game_a_synthesis` | `game_a_rewarded_video=cd70017a106f6f2a64ff81bab7c75f4b8936745931679fd4782c414db1088ff7`; `game_a_in_app_purchase=fe1644834de2c3495870ea9780d9a866bf780126368c3128924725647399624e`; `game_a_banner=21919b8480488a3a24a19b27e75f8bf5ee9c9d36b3003e2f6d823cc154b39a8a` | `sha256:469349d64f70d04c6107b0073689781a0fbf7b3e99060d0522e529a416cd840e` |
| `R01_retention_curve` | `game_b_retention=63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0` | `sha256:85af8c9c7320ad6f906683facdc43570b6449ed1eb3f482ca6638c798af6fb2b` |
| `R05_relationship_scope` | `savings_card_orders=9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`; `savings_card_user_payments=cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03` | `sha256:2f3103f89767535d9509c9b931eb4cad652f3412c4e6f2a63de3ed903c41694d` |
| `R06_long_term_value_cohort` | `savings_card_user_payments=cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03` | `sha256:1c22ed1548b54abf6218de897810f3218b2609fb1424ac14243d4bf2e4a75f1e` |

唯一报告路径：`docs/audit/2026-08-27-gate-d-e7ec-r01-r06-countable-batch-report.json`。

### R01–R06 精确授权文案

```text
我授权 Gate D 测试契约收口后当前 digest 的 R01–R06 判断纪律批次：仅在 source digest sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc 上，使用 openai/deepseek-v4-flash，按冻结顺序执行 R02_paired_before_after、R03_dirty_cross_promotion、R04_game_a_synthesis、R01_retention_curve、R05_relationship_scope、R06_long_term_value_cohort；每场景按冻结阶梯 [2000,8000,32000] 逐档各单次请求，仅前档 finish_reason=length 才升档，任何非截断响应即停止该场景，每场景至多 3 次、总计至多 18 次 Provider 调用；使用 2026-08-27-gate-d-e7ec-l4-authorization-freeze.md 冻结的 candidate SHA-256、数据 hash、prompt hash、temperature=0、timeout=120 秒与 response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-27-gate-d-e7ec-r01-r06-countable-batch-report.json。预检不通过则零调用；批内某场景失败时记录失败后继续其余尚未执行场景；除冻结的 length 阶梯升档外不重试、不换模型、不做 Provider 回退、不补跑。
```

## 冻结二：R07 publication journey

- candidate：`tests/acceptance/route_a_gate_c_journey_r07_candidate.json`。
- candidate SHA-256：`sha256:b6dd3397cac0302c57bd50fabda7d80fe99b2d62f4bafea5a4260133343549ca`。
- 问题 UTF-8 SHA-256：`sha256:7822388b42f78708f4a90bb86751f502456db0ae647be5f3b1eadf4c18268d0c`。
- 数据：`savings_card_orders=sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`；上传为 `省钱卡订单.xlsx`。
- oracle replay：`tests/acceptance/route_a_gate_c_journey_r07_replay.json`，`sha256:ebcbef8687a26a791b9348300ae3fd42eb55a777866e800f8e058fd9199519ec`。
- `round_cap=10`；主上限 30、辅助上限 6、总上限 36。
- publication：真实执行 `load_data + compare_periods`；无 error event；最终文本含 1818、684、71、30。

唯一报告路径：`docs/audit/2026-08-27-gate-d-e7ec-r07-countable-publication-report.json`。

### R07 精确授权文案

```text
我授权 Gate D 测试契约收口后当前 digest 的 R07 publication journey：仅在 source digest sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop 执行 R07_end_to_end_publication_journey 恰好 1 次；主轮至多 10，每轮按冻结阶梯 [2000,8000,32000] 逐档各单次非流式请求，仅该档 finish_reason=length 才升档，主请求至多 30 次；辅助 LLM 与主轮共用 exact counter，按 counted_once 以 max_tokens=300、response_format={"type":"json_object"} 每个辅助钩子至多单次请求、辅助总上限 6、不升档不重试，总计至多 36 次 Provider 调用；使用 2026-08-27-gate-d-e7ec-l4-authorization-freeze.md 冻结的 candidate SHA-256、问题文本 hash、savings_card_orders 数据 hash、oracle replay hash、temperature=0、timeout=120 秒与 publication 契约（真实执行 load_data 与 compare_periods、无错误事件、轮数不超上限、最终文本包含 1818、684、71、30），并仅写入 docs/audit/2026-08-27-gate-d-e7ec-r07-countable-publication-report.json。预检不通过则零调用；执行失败即停止该旅程；countable journey 禁止 stream→sync 补发，除主轮冻结的 length 阶梯升档外不重试、不换模型、不做 Provider 回退、不补跑；无效辅助语义只允许本地确定性规则继续且不得产生第二次 Provider 请求。
```

## 冻结三：R09 routing_integrity journey

- candidate：`tests/acceptance/route_a_gate_d_journey_r09_routing_candidate.json`。
- candidate SHA-256：`sha256:5be9d0444e72b083fed327193cde5f8418ef3049c7edc189d80e17eda656d21b`。
- 问题 UTF-8 SHA-256：`sha256:2eae4212b36927bfa62a78a29ffde03bfabdef6764512defd260013378f80929`。
- 数据：`game_b_retention=sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0`。
- `round_cap=12`；主上限 36、辅助上限 6、总上限 42。
- `routing_integrity`：真实执行 `load_data + curve_fitting`；无 error event；`final_answer_numeric_anchors=[]` 且 verdict 为 `not_required`。

唯一报告路径：`docs/audit/2026-08-27-gate-d-e7ec-r09-countable-routing-report.json`。

### R09 精确授权文案

```text
我授权 Gate D 测试契约收口后当前 digest 的 R09 系统完整性与路由旅程：仅在 source digest sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop 执行 R01_retention_curve_routing_journey 恰好 1 次；主轮至多 12，每轮按冻结阶梯 [2000,8000,32000] 逐档各单次非流式请求，仅该档 finish_reason=length 才升档，主请求至多 36 次；辅助 LLM 与主轮共用 exact counter，按 counted_once 以 max_tokens=300、response_format={"type":"json_object"} 每个辅助钩子至多单次请求、辅助总上限 6、不升档不重试，总计至多 42 次 Provider 调用；使用 2026-08-27-gate-d-e7ec-l4-authorization-freeze.md 冻结的 candidate SHA-256、问题文本 hash、game_b_retention 数据 hash、temperature=0、timeout=120 秒与 routing_integrity 契约（真实执行 load_data 与 curve_fitting、无错误事件、轮数不超上限、final_answer_numeric_anchors=[] 且最终文本数值锚点 not_required），并仅写入 docs/audit/2026-08-27-gate-d-e7ec-r09-countable-routing-report.json。预检不通过则零调用；执行失败即停止该旅程；countable journey 禁止 stream→sync 补发，除主轮冻结的 length 阶梯升档外不重试、不换模型、不做 Provider 回退、不补跑；无效辅助语义只允许本地确定性规则继续且不得产生第二次 Provider 请求。
```

## 授权前停止点（已由精确授权解除；不得再次执行）

只有用户逐字粘贴上述某一段，才执行对应的一个批次 / 旅程；三段互不蕴含。每次执行前重新运行零调用 preflight，核对当前 digest、全部冻结 hash 与唯一报告路径不存在。任何不匹配都停在 Provider 0。

上述条件已在 2026-08-27 满足并各执行一次。此冻结不提供任何后续 Provider 调用额度。
