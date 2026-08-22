# Data Agent V2 Slice 5C5N：分析单位语义身份闭合

- **日期**：2026-08-20
- **状态**：Implemented；deterministic verification PASS；等待 review
- **基线提交**：`a81a715814de2b2fe71b4ac3f3f9cd2180be83d5`
- **历史触发 digest**：`sha256:402f4ac145c052bc291ea6b89be06fcf43de67afd807f4cfa1c281ec82328499`
- **修复后 source digest**：`sha256:db3464a5249f9ae6ea7787998298bcbdf5aae4ea2fe56b1e5aef656840b7151c`
- **本切片 Provider calls**：0

## 1. 真实失败事实

5C5M 在精确授权下执行了恰好一次 `analysis_planning`：HTTP 201、Provider calls 1、automatic retries 0，authorization consumed。Planner 返回 ready `multi_finding_synthesis`，但参数同时为 `time_field=date` 与 `analysis_unit=date`，没有选择已公开为 identifier 的 `unit_id`。

后续零 Provider 调用的确定性执行和刷新都完成，恰好证明问题不是 transport 或执行器崩溃：最终比较块写成“按 date 为分析单位”，方法块与 Finding 也把 population scope 固化为 `analysis_unit:date`。因此本次旅程的语义评审为 FAIL，不签发 release receipt。

## 2. RED 回归

新增 provider-neutral 参数化回归直接把已观察 payload 送入同一 tool schema 和 compiler，并确认修复前两条路径均被接受：

- group comparison：`analysis_unit=date`；
- multi-finding：`time_field=date` 且 `analysis_unit=date`。

初次执行结果：`2 failed`，失败点均为 schema 没有产生 validation error。随后补齐 factor relationship 的 `target=analysis_unit` 回归，以一次离线审查覆盖设计文档已声明但共享关系表遗漏的相邻缺口。

## 3. 共享合同修复

- `analysis_unit` 从 `_ANY_COLUMN_PARAMETERS` 分离成独立列策略；
- schema 只枚举非 datetime、非 unknown 的候选列，并携带受控语义描述；
- compiler 在跨字段关系检查后独立拒绝 datetime/unknown 分析单位；
- multi-finding 新增 `time_field/analysis_unit` 互异；
- factor relationship 新增 `target/analysis_unit` 互异；
- system contract 明确 analysis unit 是观察实体或聚类单位，不得复用 datetime、metric、grouping 或 time field。

没有放宽 ready plan 合同，没有增加自动 repair、隐式重试、模型特例或旧 Agent loop。

## 4. 安全诊断与 HTTP

字段角色错误继续使用稳定的 `plan_column_binding_invalid`；跨字段身份错误继续使用 `plan_parameter_relation_invalid`。两者只持久化受控的 `invalid_parameter_fields`，不持久化参数值、原始响应、reasoning 或不受控模型文本。公共 HTTP plan 投影仍不包含内部 diagnostic，因而无需增加补丁式 API 分支。

## 5. 验证与证据

- RED：`2 failed`，确认 observed payload 在修复前被 schema 接受；
- relation/role focused：`8 passed`；
- Planner + Plan Ledger + planning API：`87 passed`；
- V2/config：`318 passed`；
- Planner parity gate：PASS，7 个 ready variants、9 个状态 variants；
- 新 schema fingerprint：`sha256:6d0eaf57ac63110ee5cc6ca5a6290bc7fe206c69cb6a7b4d943cf60a9ac363e8`；
- unified deterministic journey：PASS，owner/incident/SSE 三层 receipt，Provider calls 0；
- compileall 与 `git diff --check`：PASS。

确定性证据：`docs/superpowers/evidence/2026-08-20-v2-5c5n-analysis-unit-semantic-identity-evidence.json`、`docs/superpowers/evidence/2026-08-20-v2-5c5n-unified-deterministic-evidence.json` 与 `docs/superpowers/evidence/2026-08-20-v2-5c5n-unified-deterministic-release-receipts.json`。

## 6. 后续边界

`sha256:402f...` 的 preflight 和任何 PASS receipt 对修复后源码均失效；5C5M attempt 仍是不可改写的历史调用事实。修复后的源码尚未获得新的真实 Provider 授权，也不宣称 Gate F、产品完成或根入口切换。

若 review 和提交通过，才具备基于 clean committed source 重制 5C5A-style preflight 的代码条件；任何真实调用仍必须由用户按新 source digest、模型、场景、目的和精确次数另行授权。
