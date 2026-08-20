# Data Agent V2 Slice 5C5A：统一入口真实 Provider 预检

- **日期**：2026-08-20
- **状态**：Executed；首次真实 Provider 规划调用触发 fail-closed
- **基线提交**：`0131c6c`（`test(v2): issue unified deterministic receipts`）
- **分支**：`codex/data-agent-v2`

## 1. 目标

在调用真实 Provider 之前冻结统一入口的模型、问题、数据、请求 token、逐次授权方式和停止条件。预检不得签发 authorization，也不得调用 Provider。

## 2. 冻结请求

- 场景：`unified_analysis_entry`
- 数据：`tests/fixtures/v2_slice4d_combined.csv`
- 数据 SHA-256：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`
- 模型：`openai/deepseek-v4-flash`
- Provider：`api.deepseek.com`
- 问题：`销售如何变化，不同渠道是否存在可靠差异？请给出严谨结论、统计不确定性、方法局限，并仅在上下文支持时给出建议。`

初次规划请求使用实际 system、messages、数据画像和工具协议计算：

```text
estimated_input_tokens = 357
model_context_window_tokens = 1,000,000
reserved_output_tokens = 8,000
available_input_tokens = 992,000
fits = true
```

本预检不设置回答字符上限或任意成本阈值。

## 3. 授权方式

不申请“最多两次”的 blanket authorization。第一次只请求恰好 1 次 `analysis_planning` Provider 调用。

如果第一次返回 `needs_input`：

1. 完整保存用户回答；
2. 使用实际回答重新计算完整 planning token；
3. 再次向用户请求恰好 1 次新授权；
4. 未获得第二次授权时停止，不自动继续。

失败、超限、合约错误或 `unsupported` 都不会自动重试。

## 4. Fail-closed 条件

以下任一情况立即停止：

- source digest 改变；
- 数据 fingerprint 改变；
- planning context 超过实际模型可用输入；
- Provider 请求失败；
- Planner 合约校验失败；
- Planner 返回 unsupported；
- needs_input 后没有新的逐次授权。

请求 fingerprint 同时绑定 source、场景、数据、问题、模型和 token 估算，任一字段变化都会使预检失效。

## 5. 执行结果

- 预检 source digest：`sha256:2983e3090b6bd57a75358e8ee957aeda14bdc0c65d60375d7f885951debdf7e1`
- 预检 validator：PASS
- authorization id：`provider_auth_675950dc44ae4c6fa47c038c882ce435`
- authorization status：consumed
- Provider calls observed：1
- HTTP status：502
- plan id：`plan_5e182aaf6f42822918de8b91`
- plan status：failed
- error code：`PlannerContractError`
- automatic retry：0
- release readiness claimed：false
- root switch authorized：false

本次精确授权已经全部消耗。系统按 `planner_contract_error` 停止，没有执行分析、没有补跑，也没有签发真实 Provider PASS receipt。

当前持久化错误只保留通用消息 `planner invocation or contract validation failed`，没有保留具体的合约拒绝原因或安全脱敏后的 Provider 结构，因此尚不能客观区分以下两类原因：

1. Provider 没有返回恰好一个 `submit_analysis_plan` 工具调用；
2. Provider 返回了工具调用，但参数被本地 Planner 编译合约拒绝。

在修复这一可观测性缺口并重新计算 source digest 之前，不应申请新的真实 Provider 调用。
