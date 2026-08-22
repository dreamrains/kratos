# Data Agent V2 Slice 5C5J：修复后真实 Provider 规划预检

- **日期**：2026-08-20
- **状态**：精确单次调用与后续零调用确定性执行均完成
- **基线提交**：`c005ebbe0bf8c4cbfe7ed21c020b6139e0aa8ecc`
- **source digest**：`sha256:3212b49e5f36fd38d51d92e5920b58a342125c763d39bae0826efda324d4a1f3`
- **本切片 Provider calls**：1

## 1. 预检身份

- 场景：`unified_analysis_entry`
- 目的：`analysis_planning`
- 模型：`openai/deepseek-v4-flash`
- Provider host：`api.deepseek.com`
- request fingerprint：`sha256:af50de8dcd731914396d20547ce5ff4e978ff08db2398e62f62146414eaf6d76`
- planner schema fingerprint：`sha256:d87c12de5d78ade97697634d94b4aa12618416209a53921668ebd0d047ca1587`

## 2. 离线结果

- preflight validation：PASS；
- reason codes：空；
- Planner 合同 parity gate：PASS，7 个自动分析类型、9 个状态分支；
- estimated input tokens：3,200；
- available input tokens：992,000；
- fits：true；
- authorization issued：false；
- Provider calls observed：0。

## 3. 后续边界

下一次真实调用必须由用户针对上述 model、source digest、场景、目的和精确次数重新授权。已执行授权范围只允许恰好 1 次 `analysis_planning` 调用；失败即停止，不自动重试。若返回 `needs_input`，任何 follow-up 都需要新的授权与重新估算。

本预检不构成真实 Provider PASS receipt，不宣称 Gate F、产品完成或根入口切换。

证据：`docs/superpowers/evidence/2026-08-20-v2-5c5j-real-provider-preflight.json`。

## 4. 已授权调用结果

- upload：HTTP 200；
- planning estimate：HTTP 200；
- authorization issue：HTTP 201；
- analysis planning：HTTP 201；
- Provider calls observed：1；
- automatic retries：0；
- authorization：`provider_auth_a8573689e8dc49a3b9ef6664d0042d13`，状态 `consumed`；
- plan：`plan_72e74976d0f7082c406e790c`，状态 `ready`；
- analysis kind：`multi_finding_synthesis`；
- 参数身份：`time_field=date`、`metric=sales`、`group=channel`、`analysis_unit=unit_id`；
- safe diagnostic：空。

调用证据未保存 API key、原始 Provider 响应、reasoning、Planner rationale 或其他不受控模型文本。本次授权已完全耗尽，不可复用。

Attempt 证据：`docs/superpowers/evidence/2026-08-20-v2-5c5j-real-provider-attempt.json`。

## 5. 确定性续跑结果

在同一 source digest、session 和 ready plan 上执行后续本地分析，并把任何 Provider completion 调用替换为立即失败：

- Provider calls observed：0；
- analysis：HTTP 200；
- terminal event：`turn_completed`；
- final block deltas：4；
- plan：`ready` → `consumed`；
- refresh GET：HTTP 200；
- restored turn：`finalized`，4 个 blocks；
- blocks：直接回答、历史趋势、双组比较、方法与共同边界；
- findings：2，均为 `structured_checked`；
- charts：2；
- 两个推断区块均包含统计不确定性与方法局限，没有宣称因果效应。

这证明 5C5H 修复后的 Planner 关系合同能够通过真实规划输出并驱动确定性执行闭环。该结果仍不自动构成 release receipt、Gate F 或产品完成声明。

确定性证据：`docs/superpowers/evidence/2026-08-20-v2-5c5j-deterministic-continuation.json`。
