# Gate C 主模型 R01–R07 2000-token 预检收据（未执行 Provider）

日期：2026-08-25

## 当前冻结

- 受控源码摘要：`sha256:5f79c9a14fdc72eb93ad289787922b7ea81013e01ebf3642cd6d0bcd9e87e3cd`。
- 模型：`openai/deepseek-v4-flash`。
- 请求：`temperature=0.0`、`max_tokens=2000`、`timeout_seconds=120`、`response_format={"type":"json_object"}`。
- 场景：R01、R02、R03、R04、R05、R06、R07 各恰好 1 次，总计恰好 7 次。
- 当前 manifest：`tests/acceptance/route_a_gate_c_candidates.json`；已零调用预检，模型、7 个数据 hash、7 个 prompt hash、请求和总预算全部匹配。

## 变更依据

旧摘要 `e1b698…f921f` 的完整批次在 `max_tokens=1000` 下只有 R03 失败，安全诊断为正文为空且 `finish_reason=length`。R03 专项 canary 在旧摘要 `4ea926…54518`、同模型和同 prompt/data hash、`max_tokens=2000` 下恰好 1 次通过，`finish_reason=stop`。因此本批次只将已经验证的预算提升应用于所有场景；数据、prompt、温度、超时、响应格式、无工具与无重试边界不变。

## 离线门禁

- `28 passed`、`compileall`、`git diff --check`；本预检 Provider 调用 `0`。
- 通过不等于真实 Provider、异构模型、真实 Web、完整 Gate C 或 Gate D 通过。

## 所需单独授权

```text
我授权 Gate C 主模型批次：仅在 source digest sha256:5f79c9a14fdc72eb93ad289787922b7ea81013e01ebf3642cd6d0bcd9e87e3cd 上，使用 openai/deepseek-v4-flash，执行 R01、R02、R03、R04、R05、R06、R07；每个场景恰好 1 次、总计恰好 7 次，使用当前冻结的数据 hash、prompt hash、temperature=0、max_tokens=2000、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-main-model-r01-r07-2000-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
