# Data Agent V2 Slice 5C5M：当前源码真实 Provider 旅程预检

- **日期**：2026-08-20
- **状态**：精确单次调用完成；语义路由评审 FAIL
- **基线提交**：`9c95d3299c2580a37775d963b8e861aa6f53e306`
- **source digest**：`sha256:402f4ac145c052bc291ea6b89be06fcf43de67afd807f4cfa1c281ec82328499`
- **本切片 Provider calls**：1

## 1. 为什么现在才预检

5C5L 已完成所有可在离线完成的共享合同与浏览器闭环：fixture 模型身份、测试全局隔离、multi-finding 数据范围、确定性三层 receipt、实际浏览器与刷新两层 receipt。5C5J 和中间 5C5K 证据均因源码变化成为历史证据，不能复用。

当前源码已 clean commit，才具备制作新 preflight 的身份条件。

## 2. 预检身份

- 场景：`unified_analysis_entry`；
- 目的：`analysis_planning`；
- 模型：`openai/deepseek-v4-flash`；
- Provider host：`api.deepseek.com`；
- fixture：`tests/fixtures/v2_slice4d_combined.csv`；
- dataset fingerprint：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`；
- request fingerprint：`sha256:beb5b8c279f52c9221b93066dbff60c855a0f8af83ed3498778b718958e428e0`；
- Planner schema fingerprint：`sha256:d87c12de5d78ade97697634d94b4aa12618416209a53921668ebd0d047ca1587`。

## 3. 离线结果

- preflight validator：PASS，reason codes 为空；
- Planner parity：PASS，7 个自动分析类型、9 个状态分支；
- estimated input：3,200 tokens；
- model context：1,000,000 tokens；
- reserved output：8,000 tokens；
- available input：992,000 tokens；
- fits：true；
- authorization issued：false；
- Provider calls observed：0。

## 4. 下一次调用的精确边界

若用户后续明确授权，只需要恰好 1 次 `analysis_planning` Provider 调用。授权必须同时绑定本文件中的 source digest、模型、场景、目的、Provider host 和精确次数；允许发送的仅是上述规划元数据。

失败即停止，不自动重试。若返回 `needs_input`，保存回答与重新估算不调用 Provider，但任何 follow-up planning 调用仍必须获得新的精确授权。

本 preflight 不签发 authorization，不调用 Provider，不构成 `real_provider_analysis_journey` 或 `human_semantic_review` PASS，不宣称 release readiness、产品完成或根入口切换。

## 5. 已授权单次调用结果

- upload：HTTP 200；planning estimate：HTTP 200；authorization issue：HTTP 201；analysis planning：HTTP 201；
- Provider calls observed：1；automatic retries：0；
- authorization：`provider_auth_c8b4888ac3fc4f4390cd6cbe552d8816`，状态 `consumed`，本次授权已经耗尽；
- plan：`plan_892483484a1f23d1e13b0b94`，规划后 `ready`，确定性执行后 `consumed`；
- route：`multi_finding_synthesis`；
- 参数：`time_field=date`、`metric=sales`、`group=channel`、`analysis_unit=date`；
- 后续确定性分析没有调用 Provider：analysis HTTP 200、refresh HTTP 200、`turn_completed`、恢复状态 `finalized`、4 个 blocks、2 个 charts。

调用证据没有保存 API key、原始 Provider 响应、reasoning 或 Planner rationale。证据见 `docs/superpowers/evidence/2026-08-20-v2-5c5m-real-provider-attempt.json` 与 `docs/superpowers/evidence/2026-08-20-v2-5c5m-deterministic-continuation.json`。

## 6. 为什么本次不签发 PASS

Planner 把 datetime 角色的 `date` 同时绑定为 `time_field` 和 `analysis_unit`，虽然数据集已公开 identifier 角色的 `unit_id`。当前 schema 把 `analysis_unit` 视为任意列，且 multi-finding 的关系合同没有声明 `time_field` 与 `analysis_unit` 必须互异；本地 compiler 因而接受了这条语义错误路由。

确定性执行成功只证明 transport、执行、持久化与刷新链路可运行，不证明方法身份正确。发布内容明确写成“按 date 为分析单位”，population scope 也成为 `analysis_unit:date`，因此 `real_provider_analysis_journey` 与 `human_semantic_review` 都不得签发 PASS。

后续修复必须在共享 Planner schema/compiler 合同中完成：排除 datetime 分析单位，补齐 multi-finding 的 `time_field/analysis_unit` 关系，并以 provider-neutral RED 回归覆盖。不得重放本 plan、自动 repair 或复用已 consumed authorization。
