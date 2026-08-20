# Data Agent V2 Slice 5C5O：分析单位修复后的真实 Provider 预检

- **日期**：2026-08-20
- **状态**：精确单次调用完成；时间聚合语义评审 FAIL
- **基线提交**：`38b6cee2a05b41dd9dfe24af53dcda07d4327d41`
- **source digest**：`sha256:db3464a5249f9ae6ea7787998298bcbdf5aae4ea2fe56b1e5aef656840b7151c`
- **本切片 Provider calls**：1

## 1. 前置闭环

5C5M 的单次真实调用返回可执行 route，但错误地把 datetime `date` 同时绑定为 `time_field` 和 `analysis_unit`。5C5N 已用 provider-neutral RED 闭合分析单位角色、multi-finding 时间/单位关系，以及 factor target/unit 关系，并在当前 digest 上通过 318 个 V2/config 测试及 owner/incident/SSE 三层确定性 journey。

5C5M authorization 已 consumed，不能复用；`sha256:402f...` 的 preflight、browser/refresh receipt 和真实 attempt 都不是当前源码 PASS。

## 2. 当前预检身份

- 场景：`unified_analysis_entry`；
- 目的：`analysis_planning`；
- 模型：`openai/deepseek-v4-flash`；
- Provider host：`api.deepseek.com`；
- fixture：`tests/fixtures/v2_slice4d_combined.csv`；
- dataset fingerprint：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`；
- request fingerprint：`sha256:2221702dbc3d4870f1cf2fed175a8468e4ab34bfc64138f4d03bb40f50f3ff30`；
- Planner schema fingerprint：`sha256:6d0eaf57ac63110ee5cc6ca5a6290bc7fe206c69cb6a7b4d943cf60a9ac363e8`。

## 3. 离线结果

- preflight validator：PASS，reason codes 为空；
- Planner parity：PASS，7 个自动分析类型、9 个状态分支；
- estimated input：3,510 tokens；
- model context：1,000,000 tokens；
- reserved output：8,000 tokens；
- available input：992,000 tokens；
- fits：true；
- authorization issued：false；
- Provider calls observed：0。

新估算和两个 fingerprint 均不同于 5C5M，符合源码和 schema 变化后的身份重算要求。

## 4. 下一次调用的精确边界

如用户后续明确授权，只需要恰好 1 次 `analysis_planning` Provider 调用。授权必须绑定本文件的 source digest、模型、场景、目的、Provider host 和精确次数；允许发送的仅是上述规划元数据。

失败即停止，不自动重试。若返回 `needs_input`，保存回答与重新估算不调用 Provider，但 follow-up planning 必须重新获得精确授权。

本 preflight 不签发 authorization，不调用 Provider，不构成 `real_provider_analysis_journey` 或 `human_semantic_review` PASS，不宣称 release readiness、产品完成或根入口切换。

## 5. 已授权单次调用

- upload、estimate：HTTP 200；authorization、planning：HTTP 201；
- Provider calls observed：1；automatic retries：0；
- authorization：`provider_auth_390dc641d71c46a59282b07ca0f33b64`，状态 `consumed`；
- plan：`plan_b9163ff88f3fa2b70d1106dd`；
- route：`multi_finding_synthesis`；
- 参数：`time_field=date`、`metric=sales`、`frequency=weekly`、`aggregation=sum`、`group=channel`、`analysis_unit=unit_id`；
- 确定性续跑：Provider calls 0、analysis/refresh HTTP 200、`turn_completed`、4 blocks、2 charts。

5C5N 的分析单位修复在真实输出中生效，`analysis_unit=unit_id`。本次授权已经耗尽，不可复用。

## 6. 语义评审结论

独立复算验证双组比较数字完全一致，但周频求和趋势包含两个不完整边界周：首周只有 2026-01-01 至 01-04 四天、末周只有 02-09 至 02-11 三天。系统把它们与五个完整周直接回归，并把 period bucket 的 2025-12-29 误写为数据范围起点，最终发布“未检出可靠历史趋势”。

这属于不完整周期比较，可能将增长序列扭曲为 null result，不能签发真实旅程或人工语义 PASS。旧 runner 的 `data_scope_present=false` 还有一个固定查找“日周期”的检查器误报，但实际 blocker 是方法本身未识别不完整边界周，而非该字符串检查。

历史调用证据见 `docs/superpowers/evidence/2026-08-20-v2-5c5o-real-provider-attempt.json`，续跑证据见 `docs/superpowers/evidence/2026-08-20-v2-5c5o-deterministic-continuation.json`。后续修复不得重放 plan、自动 repair 或再次调用 Provider。
