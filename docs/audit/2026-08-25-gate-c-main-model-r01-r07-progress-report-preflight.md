# Gate C 主模型 R01–R07 逐场景持久化预检收据（未执行 Provider）

日期：2026-08-25

- 基线提交：`65d9c8e1e3b9b27993d57940b65fb40e58012cd0`。
- 当前受控源码摘要：`sha256:c5d5454067a836bbc33bdb43d8b12d847ed76088906a7836543bc0751e9053fd`。
- 模型与请求：`openai/deepseek-v4-flash`，`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`；R01–R07 各 1 次、总计恰好 7 次，数据与 prompt hash 沿用并复核 [R01–R07 预检](2026-08-25-gate-c-main-model-r01-r07-preflight.md)。
- 本预检调用 Provider：`0`。

## 报告恢复契约

真实执行必须使用尚不存在的路径 `docs/audit/2026-08-25-gate-c-main-model-r01-r07-batch-report.json`。预检和授权通过后，执行器在第一请求前原子写入：

```json
{"status":"in_progress","calls_made":0,"in_flight_scenario_id":"R01_retention_curve"}
```

每个场景返回后立即原子更新 `calls_made`、结果摘要或稳定失败码；只有全部 7 场景完成后才删除 `in_flight_scenario_id` 并返回 `passed` 或 `completed_with_failures`。若进程/通道再次中断，保留的报告是已到达调用的精确下界和 in-flight 场景，从而禁止盲目重跑。

报告仍拒绝原始 response/text/reasoning/raw 字段。`24 passed`（含逐场景持久化模拟、真实数据 oracle、模型/数据/source 预检）以及 `compileall`、`git diff --check` 通过。

```text
我授权 Gate C 主模型批次：仅在 source digest sha256:c5d5454067a836bbc33bdb43d8b12d847ed76088906a7836543bc0751e9053fd 上，使用 openai/deepseek-v4-flash，执行 R01、R02、R03、R04、R05、R06、R07；每个场景恰好 1 次，总计恰好 7 次，使用上一版 R01–R07 预检中冻结的数据 hash、prompt hash、temperature=0、max_tokens=1000、timeout=120 秒，并仅写入 docs/audit/2026-08-25-gate-c-main-model-r01-r07-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
