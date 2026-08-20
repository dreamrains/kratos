# Data Agent V2 Slice 5C5B：Planner 安全诊断与 Authorization 消费绑定

- **日期**：2026-08-20
- **状态**：Implemented；待用户检查，未提交
- **基线提交**：`0131c6c`（`test(v2): issue unified deterministic receipts`）
- **分支**：`codex/data-agent-v2`
- **真实 Provider 调用**：0

## 1. 触发原因

5C5A 在一次、无重试的真实 `analysis_planning` 调用后得到 `PlannerContractError`，但持久化事实不足以区分 Provider response shape 拒绝与本地 plan compilation 拒绝。同时，authorization 虽保存 planning context，消费合同只重新绑定数据、问题和 planning input，没有比较实际模型与重新估算后的完整 context。

本切片修复共享合同和根因，不根据一次模型输出推测模型能力，也不放宽 `submit_analysis_plan`。

## 2. RED 回归

先增加 provider-neutral 回归，并在生产修改前确认失败：

- 无工具调用、多个工具调用、错误工具名、非法 JSON、非对象参数；
- 未允许顶层字段、非法 status、错误列角色；
- Ledger 必须持久化安全诊断，但公共 HTTP plan 投影不得暴露详细诊断；
- model、estimated input、context window、reserved output、available input 漂移必须拒绝消费；
- API 在 fit 仍为 true 的 token estimate 漂移和实际 Planner model 漂移时，必须在调用 Planner 前返回冲突并保持 authorization 为 `issued`；
- HTTP Planner 合同失败必须返回稳定、有限、安全的错误身份。

RED 首次运行在测试收集阶段因生产代码缺少 `PlannerFailureStage` 失败；这不是通过旧行为制造的假红。

## 3. 实施

### 3.1 Planner 失败分类

新增有限 `PlannerFailureReason` 与两个失败阶段：

- `provider_response_shape`
- `plan_compilation`

Provider response shape reason code 覆盖缺少工具调用、调用数量错误、工具名错误、参数 JSON 失败和参数非对象。Plan compilation reason code 覆盖额外字段、status/payload、analysis kind、参数 schema/value 和列绑定错误。

共享 LLM client 继续执行恰好一次 `chat_once`，只增加 `arguments_parse_error` 结构标记，不增加 repair 或重试。

### 3.2 安全诊断与 Ledger

允许持久化的诊断字段固定为：

- `failure_stage`
- `finish_reason`
- `tool_call_count`
- `tool_names`
- `tool_argument_types`
- `argument_top_level_fields`
- `metadata_truncated`

工具调用最多保留 8 个名称/类型，参数顶层字段最多保留 32 个，每个文本元数据最多 64 字符。Ledger 写入和读取都校验该 schema。模型正文、reasoning、参数值、API key 和完整原始响应均不持久化。

HTTP 失败返回 `planner_contract_error`、稳定 reason code 和失败阶段；公共 plan JSON 不包含详细 `diagnostic`。服务器端 append-only Ledger 保留诊断供确定性证据和事故分析使用。

### 3.3 Authorization 绑定

运行时字段由模糊的 request fingerprint 改为 `runtime_authorization_fingerprint`，绑定：

- purpose、filename、source fingerprint、question；
- planning input identity；
- 实际 `model_id`；
- 完整 planning context：model、estimated input、context window、reserved output、available input 和 fits。

签发前保存以上身份；消费前使用当前数据、问题、配置和完整 Provider prompt 重新估算并严格比较。实际 Planner 实例模型还必须等于该估算模型，Planner 结果模型必须等于已授权模型。任一漂移都在 Provider 调用前 fail closed。

5C5A v1 预检 JSON 中历史字段 `request_fingerprint` 的真实职责在本阶段文档中明确命名为 release preflight identity fingerprint。它绑定 source digest 与发布场景，不是运行时 Provider permission，不能替代代码中的 `runtime_authorization_fingerprint`。为保留 5C5A 未提交成果，本切片没有改写其证据 schema 或实现文件。

## 4. 明确边界

- 真实 Provider 调用：0；
- 自动重试：0；
- repair call：0；
- 未放宽 Planner schema；
- 未接回旧 Agent loop；
- 未签发 `real_provider_analysis_journey` PASS；
- 未声明 Gate F 或产品完成；
- 未切换 `/`，未删除旧系统；
- 未提交、合并或推送。

## 5. 证据与后续

确定性证据写入：

- `docs/superpowers/evidence/2026-08-20-v2-5c5b-deterministic-evidence.json`

源码变化后，旧 5C4D source-bound receipts 均 stale；5C5A preflight/attempt 只保留为旧摘要上的历史事实，不能复用其 authorization 或作为新摘要 PASS。完成确定性验证并计算新 source digest 后，代码具备重新制作 5C5A preflight 的条件，但本切片不生成新授权，也不调用 Provider。

## 6. 最终确定性结果

- Planner / authorization / Plan Ledger / planning API focused：`61 passed`；
- 当前仓库 53 个 `test_v2_*.py` 与 2 个实际 config 文件合计：`272 passed`；
- `compileall`：PASS；
- `git diff --check`：PASS；
- 新 source digest：`sha256:ce17634adf292aeab07d9a8b7063793372cdaa86be1d02451dd89870a5e5a719`；
- Provider calls：0。

旧交接中的 `312 passed` 只是历史参考；当前 HEAD 不存在 `tests/test_config.py`，实际配置测试文件为 `tests/test_config_judge_model.py` 和 `tests/test_workspace_config.py`。本切片按当前仓库实际文件运行并报告结果，不沿用旧计数。
