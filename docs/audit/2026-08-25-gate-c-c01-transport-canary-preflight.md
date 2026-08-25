# Gate C C01 传输 canary 预检收据（未执行 Provider）

日期：2026-08-25

## 冻结绑定

- 准备基线提交：`2f1281ee8977326661a59382e5d34f6f5d70d328`。
- 受控源码摘要：`sha256:e1b698fa7028c2099961e94fe0469f77ce407e51fe7ecb8f29875732100f921f`。
- 模型：`openai/deepseek-v4-flash`。
- 请求：`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`、`response_format={"type":"json_object"}`。
- 唯一场景：`C01_transport_contract`，精确预算 `1`。
- 冻结数据：`savings_card_before_after`，`sha256:e110c7e9e4abe5e21cede1e99a77e8f8a6827ef562a773eea16482808f6dce37`。
- 冻结 prompt：`sha256:5e60aa47bac91456aa75cf40d7abbdc4d6f567f71196a66ed73f830c39387684`。

## 预检结果

- 执行 `route_a_provider_preflight`：`ready=true`、`errors=[]`、总预算 `1`。
- 本收据及其预检调用 Provider：`0`。
- 真实执行时仅能写入一个尚不存在的 `docs/audit/*.json` 报告；报告必须不含 Provider 原文、推理或密钥。

## 需要的单独授权

```text
我授权 Gate C C01 传输 canary：仅在 source digest sha256:e1b698fa7028c2099961e94fe0469f77ce407e51fe7ecb8f29875732100f921f 上，使用 openai/deepseek-v4-flash，执行 C01_transport_contract 恰好 1 次、总计恰好 1 次，使用本收据冻结的数据 hash、prompt hash、temperature=0、max_tokens=1000、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-c01-transport-canary-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```

通过只说明本次单请求的传输与语义提取契约可用；它不等于 R01–R07、异构模型、真实 Web、Gate C 或 Gate D 通过。失败时禁止自动进入 R01–R07，必须先根据安全形态诊断离线修复。
