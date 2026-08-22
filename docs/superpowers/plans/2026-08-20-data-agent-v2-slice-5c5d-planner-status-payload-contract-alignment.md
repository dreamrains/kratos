# Data Agent V2 Slice 5C5D：Planner status/payload 合同对齐

- **日期**：2026-08-20
- **状态**：实现与确定性验证完成；未提交
- **基线提交**：`ec5e637e610b74fd6c198493bad9bbf037a47f51`
- **分支**：`codex/data-agent-v2`
- **当前未提交 source digest**：`sha256:ac33d746dbbce7ff2cd2d37352720f9d585140a40fc2e39cd595f934d3f24005`
- **真实 Provider calls**：0

## 1. 触发事实与分析边界

5C5C attempt 在恰好一次真实 Provider 调用后停止：Provider 返回一个 `submit_analysis_plan` 工具调用，arguments 为对象且顶层字段完整；本地 Planner 以 `plan_compilation / plan_status_payload_invalid` 拒绝。安全证据没有保存字段值，因此本切片不声称知道当次响应属于四种违规中的哪一种。

确定性核查发现可复现的共享合同缺口：对外 tool schema 只约束每个字段自身的类型和枚举，而 `_compile()` 额外要求 status 与 route/questions 的互斥关系。四个 provider-neutral RED case 均证明旧 schema 会接受本地编译器必拒绝的 payload。

## 2. 修复

### 2.1 单一 status/payload 合同

`submit_analysis_plan.parameters` 现在由三个互斥 JSON Schema `anyOf` variant 构成：

- `ready`：`analysis_kind` 必须是支持的方法，parameters 为 route，questions 必须为空；
- `needs_input`：`analysis_kind=""`、parameters 为空，questions 必须有 1–3 项；
- `unsupported`：`analysis_kind=""`、parameters 和 questions 都为空。

system prompt 表达相同规则。本地 `_compile()` 仍保留所有状态、参数、列存在性和列角色检查；没有增加自动 repair、隐式重试或合同放宽。

### 2.2 稳定、安全的细分诊断

保留历史 `plan_status_payload_invalid` 枚举以读取既有 Ledger，并新增：

- `plan_ready_questions_present`；
- `plan_needs_input_route_present`；
- `plan_needs_input_questions_missing`；
- `plan_unsupported_payload_present`。

Plan Ledger 可额外保存 `recognized_status`、`analysis_kind_present`、`parameters_empty_object`、`questions_present`。这些字段只包含受控枚举或布尔值；不保存问题文本、rationale、参数值、reasoning 或 Provider 原始响应。HTTP 公共投影继续隐藏详细 diagnostic。

## 3. RED → GREEN

RED 首次运行：`9 failed, 29 passed`。

覆盖：

- 旧 schema 接受 ready-with-questions；
- 旧 schema 接受 needs_input-with-route；
- 旧 schema 接受 needs_input-without-questions；
- 旧 schema 接受 unsupported-with-questions；
- 四类失败只能得到泛化 reason code；
- Ledger 拒绝新的受控 payload-shape 诊断。

修复后：

- Planner + Plan Store：`38 passed`；
- V2 planning/API/authorization focused：`36 passed`；
- V2/config 全量：`280 passed`；
- compileall：PASS；
- `git diff --check`：PASS。

确定性证据：`docs/superpowers/evidence/2026-08-20-v2-5c5d-deterministic-evidence.json`。

## 4. Provider 与 preflight 边界

本切片没有调用 Provider。离线候选 preflight validator 为 PASS、reason codes 为空、Provider calls 0、authorization issued false；当前规划估算为 329 input tokens，fits=true。但源码尚未提交且 `source dirty=true`，所以该候选输出不构成可执行 preflight 或调用授权。

[DeepSeek Tool Calls 官方文档](https://api-docs.deepseek.com/guides/tool_calls)说明 strict tool schema 需要 beta base 和 `strict=true`，且 strict 支持的 schema 关键字有限。本切片不切换 API base、不启用 strict beta；`anyOf` schema 与 system contract 用于消除我方公开合同漂移，本地 compilation 继续 fail closed。

## 5. Receipt 影响与停止条件

- 5C5B deterministic evidence：source-bound，已失效；
- 5C5C real-provider preflight：source digest 与 planning context 均已变化，已失效；
- 5C5C attempt：保留为历史失败事实，不是当前源码 PASS；
- 更早的 Gate E/F 或发布 receipts：不能迁移为当前源码 PASS；
- 当前没有 Gate F、真实 Provider journey 或产品完成声明；
- 当前没有新的 Provider authorization；
- 当前未切换 `/` 根入口，未删除旧系统。

形成 clean commit 后，才能基于提交后的相同 source digest 重新制作并独立验证 preflight。任何真实 Provider 调用仍需用户按模型、source digest、目的和精确次数另行授权。
