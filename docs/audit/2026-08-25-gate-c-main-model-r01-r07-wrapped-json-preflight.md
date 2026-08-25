# Gate C 主模型 R01–R07 严格 JSON 信封预检收据（未执行 Provider）

日期：2026-08-25

- 基线提交：`7bda4d449ec82a9471116523b2010c8bf5a18739`。
- 当前受控源码摘要：`sha256:e260b9d98cfafb561556396d1d95307946b92831f13b65d941479de9576bf76b`。
- 模型与请求：`openai/deepseek-v4-flash`，`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`、`response_format={"type":"json_object"}`；R01–R07 各 1 次、总计 7 次。数据和 prompt hash 沿用 [R01–R07 预检](2026-08-25-gate-c-main-model-r01-r07-preflight.md) 并已重新验证。
- 本预检调用 Provider：`0`。

前一 JSON-object 批次已审计地完成 7 次，其中 R05 唯一为 `response_not_json`，其余 6 通过，详见 [JSON-object 批次收据](2026-08-25-gate-c-main-model-r01-r07-json-object-batch.md)。本版不会把任意文本当 JSON：仅接受一个直接对象、一个 fenced 对象，或一个带展示前缀且无尾随内容的对象，并记录 `direct/fenced/embedded` 摘要；字段、事实 ID、数值落地、限制和禁止推断校验不变。

新批次只写入尚不存在的 `docs/audit/2026-08-25-gate-c-main-model-r01-r07-wrapped-json-batch-report.json`，逐场景原子 checkpoint，且不保留原始 Provider 文本。

验证：`26 passed`、`compileall`、`git diff --check`、模型/数据/source 预检均通过。

```text
我授权 Gate C 主模型批次：仅在 source digest sha256:e260b9d98cfafb561556396d1d95307946b92831f13b65d941479de9576bf76b 上，使用 openai/deepseek-v4-flash，执行 R01、R02、R03、R04、R05、R06、R07；每个场景恰好 1 次，总计恰好 7 次，使用冻结的数据 hash、prompt hash、temperature=0、max_tokens=1000、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-main-model-r01-r07-wrapped-json-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
