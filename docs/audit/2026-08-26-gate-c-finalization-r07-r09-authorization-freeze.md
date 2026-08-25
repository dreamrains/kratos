# Gate C 最终化重验：R07 / R09 授权冻结（未执行 Provider）

日期：2026-08-26

## 当前基线与零调用预检

- 分支：`rebuild`
- HEAD：`5b5942d52a25864f5de9f6150bb64bb68a12e0f0`
- 受控源码摘要：`sha256:61edff7c3c979d0b17fca0a955ee55e6e378b3f818f0bc4630a89976c9b85290`
- 工作树的非受控内容仅为用户资产：`artifacts/`、`tmp/`。
- R07、R09 清单预检均为 `ready=true`、`provider_calls=0`；预检不请求 Provider。

本次重验只验证提交 `5b5942d` 的最终化行为：在已成功完成实质分析后，模型仍自主推理和作答，但工具 schema 已关闭。它不改变模型、temperature、超时、数据、问题、推理参数或预算阶梯。

## R07 最终化旅程（独立授权）

- 清单：`tests/acceptance/route_a_gate_c_journey_r07_candidate.json`
- 场景：`R07_end_to_end_publication_journey`
- 模型：`openai/deepseek-v4-flash`
- 上传：`savings_card_orders`（`sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`）经产品 inbox 上传为 `省钱卡订单.xlsx`；用户消息固定含 `分析文件: 省钱卡订单.xlsx`。
- 请求：temperature=0、timeout=120 秒、每轮按 `[2000, 8000, 32000]` 逐档，仅 `finish_reason=length` 才升档；round_cap=10；最坏 30 次。
- 契约：必须调用 `load_data`；最终回答必须包含 `1818`、`684`、`71`、`30`。
- 唯一报告路径：`docs/audit/2026-08-26-gate-c-finalization-r07-report.json`。

```text
我授权 Gate C 最终化 R07 重验：仅在 source digest sha256:61edff7c3c979d0b17fca0a955ee55e6e378b3f818f0bc4630a89976c9b85290 上，使用 openai/deepseek-v4-flash，按 docs/audit/2026-08-26-gate-c-finalization-r07-r09-authorization-freeze.md 与 tests/acceptance/route_a_gate_c_journey_r07_candidate.json 冻结的上传、问题、数据 hash、temperature=0、timeout=120 秒、每轮阶梯 [2000,8000,32000] 和 round_cap=10，执行 R07_end_to_end_publication_journey 恰好 1 次；总计至多 30 次 Provider 调用，仅 finish_reason=length 才升档。预检不通过则零调用；失败即停止该旅程；不重试、不换模型、不回退、不补跑；仅写入 docs/audit/2026-08-26-gate-c-finalization-r07-report.json。
```

## R09 最终化旅程（独立授权）

- 清单：`tests/acceptance/route_a_gate_c_journey_r09_candidate.json`
- 场景：`R01_retention_curve_routing_journey`（R09 路由旅程）
- 模型：`openai/deepseek-v4-flash`
- 数据：`game_b_retention`（`sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0`）；问题固定引用 `reference/test_doc/游戏B留存.xlsx`。
- 请求：temperature=0、timeout=120 秒、每轮按 `[2000, 8000, 32000]` 逐档，仅 `finish_reason=length` 才升档；round_cap=12；最坏 36 次。
- 契约：必须调用 `load_data`、`curve_fitting`；最终回答必须包含 `0.188`、`0.982`、`62`。
- 唯一报告路径：`docs/audit/2026-08-26-gate-c-finalization-r09-report.json`。

```text
我授权 Gate C 最终化 R09 重验：仅在 source digest sha256:61edff7c3c979d0b17fca0a955ee55e6e378b3f818f0bc4630a89976c9b85290 上，使用 openai/deepseek-v4-flash，按 docs/audit/2026-08-26-gate-c-finalization-r07-r09-authorization-freeze.md 与 tests/acceptance/route_a_gate_c_journey_r09_candidate.json 冻结的问题、数据 hash、temperature=0、timeout=120 秒、每轮阶梯 [2000,8000,32000] 和 round_cap=12，执行 R01_retention_curve_routing_journey（R09）恰好 1 次；总计至多 36 次 Provider 调用，仅 finish_reason=length 才升档。预检不通过则零调用；失败即停止该旅程；不重试、不换模型、不回退、不补跑；仅写入 docs/audit/2026-08-26-gate-c-finalization-r09-report.json。
```

任一独立授权均不授权另一条旅程，也不授权主模型/异构模型批次、推送、部署或 Gate D 通过判定。
