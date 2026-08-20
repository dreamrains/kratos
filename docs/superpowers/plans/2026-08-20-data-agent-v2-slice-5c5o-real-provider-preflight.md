# Data Agent V2 Slice 5C5O：分析单位修复后的真实 Provider 预检

- **日期**：2026-08-20
- **状态**：离线预检 PASS，等待新的精确次数授权
- **基线提交**：`38b6cee2a05b41dd9dfe24af53dcda07d4327d41`
- **source digest**：`sha256:db3464a5249f9ae6ea7787998298bcbdf5aae4ea2fe56b1e5aef656840b7151c`
- **本切片 Provider calls**：0

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
