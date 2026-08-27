# Gate C 结构化传输契约与 canary 预检

日期：2026-08-25

## 当前基线

- 受控源码摘要：`sha256:e1b698fa7028c2099961e94fe0469f77ce407e51fe7ecb8f29875732100f921f`。
- 本次没有调用 Provider。此前 `e260…bf76b` 的 R01–R07 批次已严格完成 7 次：R03 为 `response_not_json`，其余 6 项通过；该历史结果见 [wrapped JSON 批次报告](2026-08-25-gate-c-main-model-r01-r07-wrapped-json-batch-report.json)，不能作为当前源码的通过证据。
- 本地 LiteLLM 未登记 `openai/deepseek-v4-flash` 的模型能力；`response_format={"type":"json_object"}` 会被转发，但不能被本地代码当作远端强制 JSON 的证明。

## 共享契约

1. 只要响应中恰有一个完整 JSON 对象，就可以忽略其前后展示文字；该对象仍须通过场景 ID、完整冻结事实 ID、数值锚点、非空限制、禁止推断和非模板输出检查。
2. 两个或更多互不包含的 JSON 对象一律拒绝，绝不选择其中之一。
3. 所有成功或失败收据只记录 `response_shape`、`response_length_bucket`、`response_finish_reason` 与既有稳定失败码；绝不记录 Provider 原文、推理或密钥。
4. 单请求、`num_retries=0`、无工具、无 AgentLoop、无 fallback 的边界保持不变。

## 离线门禁

- `tests/test_route_a_provider_preflight.py` 覆盖：空/纯文本/无效 JSON/非对象/多对象、带前后展示文字的唯一对象、语义校验、无正文收据和单次调用边界。
- 组合验证：`25 passed`、`compileall`、`git diff --check`。
- R01–R07 主批次与 C01 canary 都已执行零调用预检，模型、请求、数据和 prompt hash 均一致。

## 下一次真实调用的顺序

先做 C01，而不是再次盲跑 R01–R07：

- manifest：`tests/acceptance/route_a_gate_c_transport_canary.json`；
- 模型：`openai/deepseek-v4-flash`；
- 请求：`temperature=0`、`max_tokens=1000`、`timeout=120`、`response_format={"type":"json_object"}`；
- 精确预算：仅 `C01_transport_contract` 1 次；
- 冻结数据：`savings_card_before_after` `sha256:e110c7e9e4abe5e21cede1e99a77e8f8a6827ef562a773eea16482808f6dce37`；
- 冻结 prompt：`sha256:5e60aa47bac91456aa75cf40d7abbdc4d6f567f71196a66ed73f830c39387684`；
- 报告路径需是尚不存在的 `docs/audit/*.json`。C01 失败则不运行 R01–R07；C01 通过仅说明该次传输可用，仍需新的精确授权才能运行完整 7 场语义批次。

这不是 Provider 通过、真实 Web 通过或 Gate C 完成的声明。
