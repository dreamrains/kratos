# Gate C R09 路由旅程冻结（未执行 Provider）

日期：2026-08-26

## 冻结绑定

- manifest：`tests/acceptance/route_a_gate_c_journey_r09_candidate.json`（schema `route_a_journey_candidate.v1`）。
- 受控源码摘要：`sha256:0cb60d1cfa611bcbe3fa6a69a46e8d68278c0ed3ab65cfe71806e7baa0135872`。
- 模型：`openai/deepseek-v4-flash`；请求：`temperature=0.0`、`timeout_seconds=120`、每轮非流式单请求、每轮冻结阶梯 `[2000, 8000, 32000]`（`finish_reason=length` 即升档）、`round_cap=8`（含默认 `WRAP_UP_ROUND=8` 收尾机制）；**至多 24 次**。
- 问题（显式文件路径，R07 四跑教训）：「请加载 reference/test_doc/游戏B留存.xlsx，对日留存曲线做曲线拟合分析，给出最优曲线族、拟合参数与不可外推的边界。」
- 数据：`game_b_retention` `sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0`。
- 契约（R09 的靶风险是「高级工具存在但实际不可达」）：必需工具 `load_data` + **`curve_fitting`**（路由验证本体）；最终回答须含锚点 `0.188`（幂律 a=0.18800129 前缀）、`0.982`（R²=0.98240474 前缀）、`62`（观测日数）；无错误事件；轮数不超上限。
- 收据：仅写入 `docs/audit/2026-08-26-gate-c-journey-r09-report.json`。
- 离线门禁：`12 passed`（旅程套件）；本冻结 Provider 调用 `0` 次。

## 所需单独授权

```text
我授权 Gate C R09 路由旅程：仅在 source digest sha256:0cb60d1cfa611bcbe3fa6a69a46e8d68278c0ed3ab65cfe71806e7baa0135872 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop（含默认 WRAP_UP_ROUND=8 收尾机制）执行 R01_retention_curve_routing_journey 恰好 1 次：轮次至多 8、每轮按冻结阶梯 [2000, 8000, 32000] 单次非流式请求、该轮 finish_reason=length（无论正文形态）即升档，总计至多 24 次 Provider 调用，使用本收据冻结的问题（显式数据路径）、数据 hash、temperature=0、timeout=120 秒与契约（load_data 与 curve_fitting 必需、最终回答含 0.188/0.982/62 锚点），并仅写入 docs/audit/2026-08-26-gate-c-journey-r09-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```
