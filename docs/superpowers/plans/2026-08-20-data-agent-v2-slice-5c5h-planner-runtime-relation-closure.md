# Data Agent V2 Slice 5C5H：Planner 与确定性执行器字段关系闭环

- **日期**：2026-08-20
- **状态**：实现与确定性验证完成；未提交
- **基线提交**：`ca20a81581f64f080c4384dffcb8eec8d6a9fff7`
- **基线 source digest**：`sha256:31026edbfad63ff84265a08aa7a0c8b757286f400a612892ef73a4afcf7fb3a5`
- **当前未提交 source digest**：`sha256:3212b49e5f36fd38d51d92e5920b58a342125c763d39bae0826efda324d4a1f3`
- **本切片 Provider calls**：0

## 1. 触发事实

5C5G 在精确授权下成功完成一次真实 planning：HTTP 201、Provider calls 1、自动重试 0，得到 `ready` 的 `multi_finding_synthesis` plan。Provider 返回 `group=channel`、`analysis_unit=channel`。

后续本地确定性执行没有调用 Provider，但立即产生 `turn_failed`：`metric, group, and analysis_unit must be distinct`。plan 已变为 consumed，而 turn GET 返回 404。

## 2. 根因

`GroupComparisonSpec` 要求 metric、group、analysis_unit 三个字段身份互异；`FactorAnalysisSpec` 还要求 target/analysis_unit 不得出现在 features 中，time_field 不得与 target、analysis_unit 或 features 重合。5C5F 只闭合了字段、类型、列角色和值域，没有把这些执行器跨字段关系提升到 Planner 共享合同。

此外，`/api/v2/analyze` 的异常分支只发送瞬时 `turn_failed` SSE，没有写 durable failed turn，因此刷新或独立 GET 无法恢复失败状态。

## 3. RED → 修复

RED：

- 5 个 Planner relation 用例失败；
- 1 个 plan-driven runtime failure durable-turn 用例失败。

修复：

1. 新增共享 scalar distinct 与 array exclusion 关系定义；
2. 数据集感知 tool schema 根据同一关系定义生成 fail-closed `not` 约束；
3. compiler 使用同一关系定义，失败 reason 为 `plan_parameter_relation_invalid`；
4. 诊断只记录受控的冲突字段名，不记录字段值；
5. analyze 异常分支写入 status=failed、空 blocks 和受控 request_context；
6. 若持久化本身失败，SSE 增加受控 `persistence_error_code`，不替换原始执行失败。

没有放宽合同、生成修复 plan、重放已消费 authorization 或增加 Provider retry。

## 4. GREEN

- relation RED matrix：`5 passed`；
- Planner + Plan Store + Preflight：`68 passed`；
- durable failed turn：`1 passed`；
- focused planning contracts：`102 passed`；
- V2/config：`313 passed`；
- compileall：PASS；
- `git diff --check`：PASS。

修正参数 `analysis_unit=unit_id` 的隔离确定性验证：Provider calls 0、HTTP 200、恢复 GET 200、4 个 final block delta、终态 `turn_completed`、持久化状态 `finalized`。

确定性证据：`docs/superpowers/evidence/2026-08-20-v2-5c5h-planner-runtime-relation-evidence.json`。

## 5. 证据边界

源码变化使 5C5G preflight 对当前源码失效。5C5G attempt 仍证明 digest `31026edb...` 上真实 Provider 首次规划成功且只调用一次，但不构成当前源码 PASS。

当前源码未提交，不生成可执行 preflight，不申请新的 Provider 调用，不签发真实 Provider PASS receipt，不宣称 Gate F 或产品完成，不切换根入口。

后续 token 预算核查见 `docs/superpowers/plans/2026-08-20-data-agent-v2-slice-5c5i-planning-token-budget-closure.md`。
