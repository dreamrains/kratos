# Data Agent V2 Slice 5C5E：status/payload 修复后真实 Provider 预检

- **日期**：2026-08-20
- **状态**：Authorized attempt completed；Planner parameter contract failure 后已停止
- **基线提交**：`11e4287a328831e0fe65bfd0c97aea5336639cac`（`fix(v2): align planner status payload contract`）
- **分支**：`codex/data-agent-v2`
- **Source clean**：true
- **Provider calls**：1
- **Authorization**：consumed；不可复用

## 1. 目的

在 5C5D 对齐 Planner tool schema、system contract 与本地 status/payload compilation 后，为统一分析入口重新冻结真实 Planner 首次请求身份。该步骤只构建实际请求、计算 token、记录 source-bound 身份并运行 validator；不签发运行时 authorization，不调用 Provider。

## 2. 冻结身份

- source digest：`sha256:ac33d746dbbce7ff2cd2d37352720f9d585140a40fc2e39cd595f934d3f24005`；
- commit：`11e4287a328831e0fe65bfd0c97aea5336639cac`；
- 场景：`unified_analysis_entry`；
- fixture：`tests/fixtures/v2_slice4d_combined.csv`；
- dataset fingerprint：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`；
- 模型：`openai/deepseek-v4-flash`；
- Provider host：`api.deepseek.com`；
- 问题：`销售如何变化，不同渠道是否存在可靠差异？请给出严谨结论、统计不确定性、方法局限，并仅在上下文支持时给出建议。`；
- release preflight request fingerprint：`sha256:b6df6b8c0e4c1939a7a7c5c893e7a4947d58493b11ece2055e520a7cfed11155`。

## 3. Token 预检

```text
estimated_input_tokens = 329
model_context_window_tokens = 1,000,000
reserved_output_tokens = 8,000
available_input_tokens = 992,000
fits = true
```

该估算来自 5C5D 修复后的实际 Planner request。没有设置回答字符上限或任意成本阈值。

独立验证结果：

- 保存的 preflight 与重新构建结果逐字段一致；
- preflight validator：PASS；
- reason codes：空；
- Provider completion 守卫：未触发；
- Provider calls observed：0；
- authorization issued：false；
- source dirty：false。

## 4. 调用边界

本 preflight 自身不是调用授权。若用户授权下一次真实尝试，授权必须逐项指定：

- 当前 source digest；
- `openai/deepseek-v4-flash`；
- `unified_analysis_entry`；
- `analysis_planning`；
- 恰好 1 次 Provider 调用；
- 允许把已披露的 fixture 派生规划元数据发送到 `api.deepseek.com`；
- 失败、Provider error、Planner contract error 或 unsupported 时立即停止，不重试；
- needs_input 时只保存问题并停止，任何 follow-up 必须重新估算并取得新授权。

## 5. 非声明

- 不构成 `real_provider_analysis_journey` PASS；
- 不构成 Gate F 或产品完成；
- 不授权 `/` 根入口切换；
- 不授权删除旧系统；
- 不复用已消费的 5C5C authorization；
- 不把历史 5C5C attempt 提升为当前源码证据。

证据：`docs/superpowers/evidence/2026-08-20-v2-5c5e-real-provider-preflight.json`。

## 6. 已授权尝试结果

用户随后针对本文件冻结的 source digest、模型、场景、数据出境范围、目的和精确 1 次调用完成授权。执行结果：

- upload：HTTP 200，Provider calls 0；
- planning estimate：HTTP 200，Provider calls 0；
- authorization issue：HTTP 201，Provider calls 0；
- analysis planning：HTTP 502，Provider calls 1；
- authorization：`consumed`；
- plan：`plan_f2f4578fd41fa8d4fb278407`，状态 `failed`；
- error：`PlannerContractError`；
- reason：`plan_parameter_contract_invalid`；
- failure stage：`plan_compilation`；
- automatic retries：0；
- downstream deterministic analysis：未执行。

脱敏诊断确认 Provider 返回一个 `submit_analysis_plan` 工具调用，status 已识别为 `ready`，analysis kind 存在、parameters 非空、questions 为空。因此 5C5D 修复的 status/payload 分支已通过，本次失败发生在更深的本地参数合同校验。

当前有限 reason code 同时覆盖“不允许的参数名”和“缺少必需参数名”，安全诊断没有保存 parameters 的字段名或值。现有记录不能区分这两种情况，不能据此猜测具体 analysis kind、字段或放宽合同。

Attempt 证据：`docs/superpowers/evidence/2026-08-20-v2-5c5e-real-provider-attempt.json`。

本次逐次授权已完全耗尽。没有签发真实 Provider PASS receipt，没有宣称 Gate F 或产品完成，也没有授权根入口切换。任何后续真实调用都必须在修复、提交、重算 source digest 和重新制作 preflight 后另行授权。

## 7. 5C5F 测试策略修正

后续确定性分析确认，5C5E 调用前的 ready schema 对 parameters 仍只声明 `type=object`，没有表达七种 analysis kind 各自的必需/可选字段、列角色和值域。因此真实调用仍被错误地承担了发现下一层合同漂移的职责。

Slice 5C5F 已在本地把 ready schema 拆成七个数据集感知的方法分支，增加安全精确参数诊断，并把 schema/compiler parity fingerprint 纳入 preflight v2 gate。源码变化使本文件的 5C5E preflight 对当前源码失效；attempt 继续保留为历史失败事实。

后续记录：`docs/superpowers/plans/2026-08-20-data-agent-v2-slice-5c5f-planner-parameter-contract-parity.md`。
