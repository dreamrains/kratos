# Gate C 最终化纠正轮：R07 / R09 授权冻结（未执行 Provider）

日期：2026-08-26

## 当前基线与预检

- 分支：`rebuild`
- 受控源码摘要：`sha256:6581966b5c515eea55c88f08827aad201de7ee373c3d2be3d1e715fac4365f3e`
- 当前受控行为：实质分析后关闭工具 schema；若模型把工具调用写成 DSML/`tool_calls` 正文，则丢弃该正文并至多发起一次仍为 `tools=None` 的直接作答纠正轮。
- 预检已验证 R07/R09 都为 `ready=true`、`provider_calls=0`。
- 结构门禁要求 `round_cap >= wrap_up_round + 2`，以保留首次最终化和一次纠正；当前 R07 为 `10=8+2`，R09 为 `12>8+2`。

纠正轮是同一次有界旅程中的下一轮模型请求，始终无工具 schema，计入下列最大调用数；它不是失败后的重试、回退或补跑。

## R07（独立授权）

- 清单：`tests/acceptance/route_a_gate_c_journey_r07_candidate.json`
- 场景：`R07_end_to_end_publication_journey`
- 模型：`openai/deepseek-v4-flash`
- 上传：`savings_card_orders`（`sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`）上传为 `省钱卡订单.xlsx`；问题固定含 `分析文件: 省钱卡订单.xlsx`。
- 请求：temperature=0、timeout=120 秒；每轮 `[2000,8000,32000]`，仅 `finish_reason=length` 升档；round_cap=10，最多 30 次调用。
- 契约：`load_data` 已调用；最终答案包含 `1818`、`684`、`71`、`30`。
- 唯一报告：`docs/audit/2026-08-26-gate-c-finalization-recovery-r07-report.json`。

```text
我授权 Gate C 最终化纠正轮 R07 重验：仅在 source digest sha256:6581966b5c515eea55c88f08827aad201de7ee373c3d2be3d1e715fac4365f3e 上，使用 openai/deepseek-v4-flash，按 docs/audit/2026-08-26-gate-c-finalization-recovery-r07-r09-authorization-freeze.md 与 tests/acceptance/route_a_gate_c_journey_r07_candidate.json 冻结的上传、问题、数据 hash、temperature=0、timeout=120 秒、每轮阶梯 [2000,8000,32000] 和 round_cap=10，执行 R07_end_to_end_publication_journey 恰好 1 次；总计至多 30 次 Provider 调用，仅 finish_reason=length 才升档。最终化 DSML/tool_calls 正文的至多一次无工具纠正轮属于该同一受权旅程并计入上述上限；预检不通过则零调用；失败即停止该旅程；不重试、不换模型、不回退、不补跑；仅写入 docs/audit/2026-08-26-gate-c-finalization-recovery-r07-report.json。
```

## R09（独立授权）

- 清单：`tests/acceptance/route_a_gate_c_journey_r09_candidate.json`
- 场景：`R01_retention_curve_routing_journey`（R09）
- 模型：`openai/deepseek-v4-flash`
- 数据：`game_b_retention`（`sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0`）；问题固定引用 `reference/test_doc/游戏B留存.xlsx`。
- 请求：temperature=0、timeout=120 秒；每轮 `[2000,8000,32000]`，仅 `finish_reason=length` 升档；round_cap=12，最多 36 次调用。
- 契约：`load_data`、`curve_fitting` 已调用；最终答案包含 `0.188`、`0.982`、`62`。
- 唯一报告：`docs/audit/2026-08-26-gate-c-finalization-recovery-r09-report.json`。

```text
我授权 Gate C 最终化纠正轮 R09 重验：仅在 source digest sha256:6581966b5c515eea55c88f08827aad201de7ee373c3d2be3d1e715fac4365f3e 上，使用 openai/deepseek-v4-flash，按 docs/audit/2026-08-26-gate-c-finalization-recovery-r07-r09-authorization-freeze.md 与 tests/acceptance/route_a_gate_c_journey_r09_candidate.json 冻结的问题、数据 hash、temperature=0、timeout=120 秒、每轮阶梯 [2000,8000,32000] 和 round_cap=12，执行 R01_retention_curve_routing_journey（R09）恰好 1 次；总计至多 36 次 Provider 调用，仅 finish_reason=length 才升档。最终化 DSML/tool_calls 正文的至多一次无工具纠正轮属于该同一受权旅程并计入上述上限；预检不通过则零调用；失败即停止该旅程；不重试、不换模型、不回退、不补跑；仅写入 docs/audit/2026-08-26-gate-c-finalization-recovery-r09-report.json。
```

任一授权不扩展到另一条旅程、历史失败报告、主模型/异构批次、推送、部署或 Gate D。
