# Data Agent V2 Slice 5C5C：修复后真实 Provider 预检

- **日期**：2026-08-20
- **状态**：Authorized attempt completed；Planner contract failure 后已停止
- **基线提交**：`ec5e637e610b74fd6c198493bad9bbf037a47f51`（`fix(v2): harden planner authorization diagnostics`）
- **分支**：`codex/data-agent-v2`
- **Provider calls**：1
- **Authorization**：consumed；不可复用

## 1. 目的

在 5C5B 修复 Planner 安全诊断与 authorization 消费绑定后，重新制作当前 source digest 上的统一入口真实 Provider 预检。该步骤只构建实际 Planner request、计算 token、冻结身份并运行 validator；不签发 authorization，不调用 Provider。

## 2. 冻结身份

- source digest：`sha256:ce17634adf292aeab07d9a8b7063793372cdaa86be1d02451dd89870a5e5a719`
- 场景：`unified_analysis_entry`
- fixture：`tests/fixtures/v2_slice4d_combined.csv`
- dataset fingerprint：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`
- 模型：`openai/deepseek-v4-flash`
- Provider host：`api.deepseek.com`
- 问题：`销售如何变化，不同渠道是否存在可靠差异？请给出严谨结论、统计不确定性、方法局限，并仅在上下文支持时给出建议。`
- release preflight request fingerprint：`sha256:212ca700f303521b0625299bb5293a8f8f9bfabcccd33a2f43a47ad428588142`

## 3. Token 预检

```text
estimated_input_tokens = 357
model_context_window_tokens = 1,000,000
reserved_output_tokens = 8,000
available_input_tokens = 992,000
fits = true
```

没有设置回答字符上限或任意成本阈值。

## 4. 验证结果

- preflight builder：PASS；
- preflight validator：PASS；
- reason codes：空；
- Provider calls observed：0；
- authorization issued：false；
- release readiness claimed：false；
- root switch authorized：false。

证据文件：

- `docs/superpowers/evidence/2026-08-20-v2-5c5c-real-provider-preflight.json`

## 5. 下一授权边界

如果继续真实旅程，需要用户另行明确授权：

- source digest：`sha256:ce17634adf292aeab07d9a8b7063793372cdaa86be1d02451dd89870a5e5a719`；
- 模型：`openai/deepseek-v4-flash`；
- 目的：为 `unified_analysis_entry` 执行 `analysis_planning`；
- 精确次数：恰好 1 次 Provider 调用；
- 失败、Provider error、Planner contract error 或 unsupported：立即停止，不重试；
- needs_input：保存问题并停止，任何后续规划必须重新估算并获得新的逐次授权。

本预检自身不构成调用授权。旧 5C5A authorization 已耗尽且不可复用。

## 6. 已授权尝试结果

用户随后针对本文件冻结的 source digest、模型、场景、目的和精确 1 次调用完成授权，并明确允许把 fixture 派生的规划元数据发送至 `api.deepseek.com`。执行结果：

- upload：HTTP 200，Provider calls 0；
- planning estimate：HTTP 200，Provider calls 0；
- authorization issue：HTTP 201，Provider calls 0；
- analysis planning：HTTP 502，Provider calls 1；
- authorization：`consumed`；
- plan：`plan_4603e45ba88bbd0bdd915969`，状态 `failed`；
- error：`PlannerContractError`；
- reason：`plan_status_payload_invalid`；
- failure stage：`plan_compilation`；
- automatic retries：0；
- downstream deterministic analysis：未执行。

脱敏诊断表明 Provider 返回 `finish_reason=tool_calls`，且只有 1 个名为 `submit_analysis_plan` 的工具调用；arguments 是对象，顶层字段集合完整。失败发生在本地 plan compilation 的 status/payload 一致性校验，而不是 Provider response shape 校验。现有安全证据不保存字段值，因此不能进一步断言是哪一种 status/payload 组合违规，也不据此放宽合同。

证据文件：

- `docs/superpowers/evidence/2026-08-20-v2-5c5c-real-provider-attempt.json`

本次逐次授权已经完全耗尽。没有签发真实 Provider PASS receipt，没有宣称 Gate F 或产品完成，也没有授权根入口切换。任何修复后的真实调用都必须重新计算 source digest、重新制作 preflight，并获得新的精确逐次授权。

## 7. 5C5D 后续根因修复

后续 provider-neutral RED 证明，当时的 `submit_analysis_plan` tool schema 会接受本地编译器拒绝的 status/payload 组合。该共享合同漂移已经在 Slice 5C5D 修复；不能根据现有脱敏证据反推 5C5C 响应的具体字段值。

源码变更后的未提交 source digest 为 `sha256:ac33d746dbbce7ff2cd2d37352720f9d585140a40fc2e39cd595f934d3f24005`，因此本文件记录的 5C5C preflight 已不再匹配当前源码。本文件和 attempt evidence 只保留为历史记录，不构成新的 authorization 或 PASS receipt。

后续记录：`docs/superpowers/plans/2026-08-20-data-agent-v2-slice-5c5d-planner-status-payload-contract-alignment.md`。
