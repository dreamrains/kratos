# Gate C R03 截断 canary 预检收据（未执行 Provider）

日期：2026-08-25

## 冻结绑定

- 当前受控源码摘要：`sha256:4ea926eed416ab4ea6e7608df71141c4238b5c2f3bb6fc74711d22bdefa54518`。
- 模型：`openai/deepseek-v4-flash`。
- 唯一场景：`R03_dirty_cross_promotion`，预算恰好 `1`。
- 请求：`temperature=0.0`、`max_tokens=2000`、`timeout_seconds=120`、`response_format={"type":"json_object"}`。
- 冻结数据：`game_cross_promotion`，`sha256:063f5415f490f90967b48d2e29972b3d2e1b908335aeb4a6420a90fb2eb19f83`。
- 冻结 prompt：`sha256:980727a4567acc13a8d0227a477f1e2771f3e88a7bae9542f994622e95be4b9c`。

## 背景与预检

在旧摘要 `e1b698…f921f` 的主模型批次中，R03 是唯一失败项，安全收据显示空正文和 `finish_reason=length`。当前 canary 只提高它的 output 上限来验证该已确认的截断假设；没有放宽事实、数值、限制、禁止推断、单次请求或 JSON 契约。

`route_a_provider_preflight` 结果：`ready=true`、无错误、总预算 `1`。本预检调用 Provider `0` 次。

## 所需单独授权

```text
我授权 Gate C R03 截断 canary：仅在 source digest sha256:4ea926eed416ab4ea6e7608df71141c4238b5c2f3bb6fc74711d22bdefa54518 上，使用 openai/deepseek-v4-flash，执行 R03_dirty_cross_promotion 恰好 1 次、总计恰好 1 次，使用本收据冻结的数据 hash、prompt hash、temperature=0、max_tokens=2000、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-r03-truncation-canary-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```

本次通过只说明 R03 在提高预算后的单次输出可完成；仍需新的授权才能执行完整 R01–R07。
