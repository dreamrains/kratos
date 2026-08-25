# Gate C 主模型 R01–R07 阶梯批次预检收据（未执行 Provider）

日期：2026-08-25

## 冻结绑定

- manifest：`tests/acceptance/route_a_gate_c_main_ladder.json`（由 `route_a_gate_c_candidates.json` 程序化变换生成：场景、问题、事实包逐字节保留，仅请求形式由标量改为阶梯，`call_budget` 1→3）。
- 当前受控源码摘要：`sha256:bb6fed2a01841843c946f365d2e212069270c1a676d3ccd7e6cda27cfa176464`。
- 模型：`openai/deepseek-v4-flash`。
- 请求：`temperature=0.0`、`timeout_seconds=120`、`response_format={"type":"json_object"}`、`max_tokens_ladder=[2000, 8000, 32000]`；无标量 `max_tokens`。
- 场景与预算：R02、R03、R04、R07、R01、R05、R06 各 `call_budget=3`（阶梯档数），总计恰好 21 次（最坏情形上限；任何一档成功即停，实际消耗可低于上限）。
- 数据 hash：8 项与 [2000-token 批次报告](2026-08-25-gate-c-main-model-r01-r07-2000-batch-report.json) 完全一致。
- prompt hash：7 项与该报告逐字一致（R02 `ce3a489e…`、R03 `980727a4…`、R04 `469349d6…`、R07 `018865ff…`、R01 `85af8c9c…`、R05 `2f3103f8…`、R06 `1c22ed15…`）。本批次相对该已执行批次的唯一差异是冻结阶梯。

## 变更依据

2000-token 批次 6/7 通过、R05 截断；R05 阶梯 canary（授权消耗恰好 1 次，第一档 2000 通过，reasoning 桶 257_to_1024）证明原截断为推理长度方差而非 prompt 确定性属性。冻结阶梯是对该方差的免疫形式：仅在 `response_truncated` 时升档、语义/传输失败不升档、收据记录命中档位。无重试、无换模型、无 reasoning_effort 降级；事实包、数值锚点、限制、禁止推断与 JSON 契约全部不变。

## 离线门禁

- `tests/test_route_a_provider_preflight.py`：`31 passed`（新增主阶梯清单冻结测试：prompt hash 与旧清单及已执行 2000 批次收据三方一致）。
- `compileall`、`git diff --check` 通过；本预检调用 Provider `0` 次。
- 通过不等于真实 Provider、异构模型、真实 Web、完整 Gate C 或 Gate D 通过。

## 所需单独授权

```text
我授权 Gate C 主模型阶梯批次：仅在 source digest sha256:bb6fed2a01841843c946f365d2e212069270c1a676d3ccd7e6cda27cfa176464 上，使用 openai/deepseek-v4-flash，执行 R02_paired_before_after、R03_dirty_cross_promotion、R04_game_a_synthesis、R07_end_to_end_publication、R01_retention_curve、R05_relationship_scope、R06_long_term_value_cohort：每场景按冻结阶梯 [2000, 8000, 32000] 逐档单次请求、仅前档 response_truncated 才升档、任何一档成功即停，每场景至多 3 次、总计至多 21 次，使用本收据冻结的数据 hash、prompt hash、temperature=0、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-main-model-r01-r07-ladder-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
