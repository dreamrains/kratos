# Gate C 主模型 R01–R07 JSON-object 预检收据（未执行 Provider）

日期：2026-08-25

- 基线提交：`7d9a40553fa9674a147a24e1b4d8e733a02def86`。
- 当前受控源码摘要：`sha256:80b149a2c035cd8430c45be3cca06e5d1ea1fad3dfae48a3d4983350be33b531`。
- 模型与请求：`openai/deepseek-v4-flash`，`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`、`response_format={"type":"json_object"}`。
- 七场景 R01–R07 各一次，总计恰好 7 次；数据 ID/SHA-256 和 prompt SHA-256 与 [R01–R07 预检](2026-08-25-gate-c-main-model-r01-r07-preflight.md) 相同，当前预检已重新验证。
- 本预检 Provider 调用：`0`。

## 依据与报告

前一审计批次在 source digest `63166…dd2a7` 实际完成 7 次，其中 R02 唯一返回非 JSON，而其余 6 场景通过，详见 [审计批次收据](2026-08-25-gate-c-main-model-r01-r07-audited-batch.md)。本版将标准 `json_object` 响应格式作为所有场景的共享请求契约，并保持逐场景 in-flight checkpoint；不放宽 R02 或为它增加例外。

新批次只可写入尚不存在的 `docs/audit/2026-08-25-gate-c-main-model-r01-r07-json-object-batch-report.json`，执行前、每场景前后均原子更新，且只含摘要/稳定错误码。

验证：`24 passed`、`compileall`、`git diff --check` 以及模型/数据/source 预检通过。

```text
我授权 Gate C 主模型批次：仅在 source digest sha256:80b149a2c035cd8430c45be3cca06e5d1ea1fad3dfae48a3d4983350be33b531 上，使用 openai/deepseek-v4-flash，执行 R01、R02、R03、R04、R05、R06、R07；每个场景恰好 1 次，总计恰好 7 次，使用冻结的数据 hash、prompt hash、temperature=0、max_tokens=1000、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-main-model-r01-r07-json-object-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
