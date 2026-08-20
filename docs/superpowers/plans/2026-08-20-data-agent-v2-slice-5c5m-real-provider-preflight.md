# Data Agent V2 Slice 5C5M：当前源码真实 Provider 旅程预检

- **日期**：2026-08-20
- **状态**：离线预检 PASS，等待新的精确次数授权
- **基线提交**：`9c95d3299c2580a37775d963b8e861aa6f53e306`
- **source digest**：`sha256:402f4ac145c052bc291ea6b89be06fcf43de67afd807f4cfa1c281ec82328499`
- **本切片 Provider calls**：0

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
