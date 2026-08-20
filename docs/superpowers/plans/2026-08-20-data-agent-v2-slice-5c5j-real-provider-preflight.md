# Data Agent V2 Slice 5C5J：修复后真实 Provider 规划预检

- **日期**：2026-08-20
- **状态**：离线预检通过；等待新的精确调用授权
- **基线提交**：`c005ebbe0bf8c4cbfe7ed21c020b6139e0aa8ecc`
- **source digest**：`sha256:3212b49e5f36fd38d51d92e5920b58a342125c763d39bae0826efda324d4a1f3`
- **本切片 Provider calls**：0

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

下一次真实调用必须由用户针对上述 model、source digest、场景、目的和精确次数重新授权。授权范围只允许恰好 1 次 `analysis_planning` 调用；失败即停止，不自动重试。若返回 `needs_input`，任何 follow-up 都需要新的授权与重新估算。

本预检不构成真实 Provider PASS receipt，不宣称 Gate F、产品完成或根入口切换。

证据：`docs/superpowers/evidence/2026-08-20-v2-5c5j-real-provider-preflight.json`。
