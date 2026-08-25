# Gate C kimi-k3 批次失败根因与 v2 冻结（未执行新的 Provider）

日期：2026-08-26（跨日会话连续）

## 首跑事实（授权消耗 4/12）

在 `sha256:ce01e3c2…` 上执行 kimi-k3 批次恰好按场景各 1 次共 4 次调用（收据：[batch report](2026-08-25-gate-c-heterogeneous-kimi-batch-report.json)）：R02/R04/R07 为 `BadRequestError`，R01 为 `RateLimitError`（连发 400 后的限流）。传输错误不升档、批内继续——执行器行为正确。

## 根因（离线查证，零调用）

[Kimi 官方模型参数参考](https://platform.kimi.com/docs/api/models-overview)：**`kimi-k3` 的 temperature 固定为 1.0，传入任何其他值（含 0.0）直接报错**；官方建议不显式传入 temperature。模型 ID `kimi-k3` 本身正确。附带发现：K3 始终推理（Preserved Thinking 常开），顶层 `reasoning_effort` 支持 low/high/max；K3 多轮对话须原样回传含 `reasoning_content` 的 assistant message（产品 loop 已具备该行为）。

## 修复

- manifest 请求允许**省略 temperature**（= 不发送；`LLMClient` 语义已支持）；出现时仍必须为 0.0。单次调用与旅程两套执行器同步放开。
- kimi 清单移除 `temperature` 字段。
- 旅程执行器 cap 拒绝改为 sticky（loop 同步回退不再造成轮数虚增）。

## v2 冻结

- 受控源码摘要：`sha256:e3e3d14e60b1ee54dfd9e5a2174c5f963c09f672385330dfc38e0ada5c87396e`。
- manifest：`tests/acceptance/route_a_gate_c_heterogeneous_kimi.json`（temperature 已移除；场景、prompt hash、数据 hash、阶梯、端点、凭据均不变）。
- 离线门禁：`57 passed`；本次修复 Provider 调用 `0` 次。

## 所需单独授权

```text
我授权 Gate C 异构模型批次 v2：仅在 source digest sha256:e3e3d14e60b1ee54dfd9e5a2174c5f963c09f672385330dfc38e0ada5c87396e 上，使用 openai/kimi-k3（api_base=https://api.moonshot.cn/v1，凭据 MOONSHOT_API_KEY，不发送 temperature），执行 R02_paired_before_after、R04_game_a_synthesis、R07_end_to_end_publication、R01_retention_curve：每场景按冻结阶梯 [2000, 8000, 32000] 逐档单次请求、仅前档 response_truncated 才升档、任何一档成功即停，每场景至多 3 次、总计至多 12 次，使用本收据冻结的数据 hash、prompt hash、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-26-gate-c-heterogeneous-kimi-v2-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
