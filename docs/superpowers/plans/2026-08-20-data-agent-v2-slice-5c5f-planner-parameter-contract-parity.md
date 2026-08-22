# Data Agent V2 Slice 5C5F：Planner 参数合同确定性闭环

- **日期**：2026-08-20
- **状态**：实现与确定性验证完成；未提交
- **基线提交**：`11e4287a328831e0fe65bfd0c97aea5336639cac`
- **分支**：`codex/data-agent-v2`
- **当前未提交 source digest**：`sha256:31026edbfad63ff84265a08aa7a0c8b757286f400a612892ef73a4afcf7fb3a5`
- **本切片真实 Provider calls**：0

## 1. 效率问题与根因

5C5C 用一次调用发现 status/payload schema 漂移；修复后，5C5E 又用一次调用发现 ready parameters schema 仍比 compiler 宽。继续沿用这一节奏，会让真实调用成为串行 schema fuzzing，既低效也无法保证下一次不会只暴露更深一层的模糊错误。

代码事实：5C5E 调用前的 `ready` variant 只要求 `parameters` 是对象，而 `_validate_parameters()` 按 analysis kind 检查 required、optional、未知字段、列存在性、列角色和有限值域。Provider 可以返回通过 tool schema 但必被 compiler 拒绝的 parameters。

## 2. 修复

### 2.1 七种逐方法 schema

对以下七种自动方法分别生成 ready variant：

- descriptive；
- factor_relationship；
- date_transformation；
- group_comparison；
- time_trend；
- forecast；
- multi_finding_synthesis。

每个 parameters schema 明确 required、optional 和 `additionalProperties=false`。列绑定来自当前 DatasetPlanningContext：metric/target/features 只能选数值列，time_field 只能选日期列，其余可绑定字段只能选现有列；frequency、aggregation、horizon、recommendation policy 和 reversible 也使用与 compiler 相同的类型和值域。提交前审查进一步消除了 schema 与 compiler 中重复手写的列策略和值域：两侧现在消费同一组服务端参数策略定义，并由完整字段集合 invariant fail closed。

### 2.2 一次失败即可诊断

保留历史 `plan_parameter_contract_invalid`，新增：

- `plan_parameter_fields_missing`；
- `plan_parameter_fields_unexpected`。

安全诊断新增：

- `recognized_analysis_kind`；
- `recognized_parameter_fields`；
- `missing_required_parameter_fields`；
- `unexpected_recognized_parameter_fields`；
- `unknown_parameter_field_count`；
- `invalid_parameter_fields`；
- `parameter_metadata_truncated`。

字段名只允许来自服务端有限参数 allowlist；未知模型字段只计数，不保存名称。所有参数值、rationale、reasoning 和原始 Provider 响应仍不进入失败证据。HTTP 公共 plan 投影仍隐藏 diagnostic。

### 2.3 Preflight parity gate

preflight 升级为 `v2_real_provider_journey_preflight.v2`，并绑定：

- `v2_planner_contract_parity.v1`；
- tool schema fingerprint；
- 7 个 ready variant；
- 9 个总 status variant；
- parity passed=true。

validator 会拒绝 gate 缺失、失败、fingerprint 格式错误或 variant 数量不一致的 preflight；保存的完整 gate 还必须与当前源码重新构建结果逐字段相等。

## 3. RED → GREEN

已记录的首轮 RED：`13 failed, 37 passed`，覆盖七种方法的缺失/额外参数、三类错误列角色、两种参数 reason 合并和 Ledger 诊断拒绝。随后在实现前增加受控 invalid field 定位用例。

Preflight gate RED：`2 failed`，证明旧 preflight 没有 parity gate。

修复后：

- Planner + Plan Store + Preflight：`62 passed`；
- Planning/API/authorization/preflight focused：`34 passed`；
- V2/config 全量：`305 passed`；
- compileall：PASS；
- `git diff --check`：PASS。

确定性证据：`docs/superpowers/evidence/2026-08-20-v2-5c5f-deterministic-evidence.json`。

## 4. 离线候选 preflight

当前未提交源码上的离线候选结果：

- source digest：`sha256:31026edbfad63ff84265a08aa7a0c8b757286f400a612892ef73a4afcf7fb3a5`；
- source dirty：true；
- preflight version：v2；
- estimated input tokens：348；
- fits：true；
- contract gate：PASS；
- schema fingerprint：`sha256:ccb98eb96b90a0a1745f0ca42ca829a361b0a7fdc016393fe4e72066624766b0`；
- request fingerprint：`sha256:3e892e4bc09a0a1d4991af963c4498bb83abb67ba89a93bac4e9308e13fd9b5b`；
- Provider calls：0；
- authorization issued：false。

因为源码尚未提交，该输出不是可执行 preflight，也不是调用授权。

## 5. 停止边界

在本切片提交并重新生成 clean preflight 前，不再申请真实 Provider 调用。即使随后 clean preflight 通过，真实调用仍需用户按模型、source digest、目的、数据出境范围和精确次数另行授权。

本切片不宣称真实 Provider journey、Gate F 或产品完成，不切换 `/` 根入口，不删除旧系统。
