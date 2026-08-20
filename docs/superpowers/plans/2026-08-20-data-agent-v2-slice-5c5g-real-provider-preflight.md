# Data Agent V2 Slice 5C5G：Planner 参数合同闭环后真实 Provider 预检

- **日期**：2026-08-20
- **状态**：精确逐次授权已执行并消费；Planner ready；已停止
- **提交**：`ca20a81581f64f080c4384dffcb8eec8d6a9fff7`（`fix(v2): enforce planner parameter contract parity`）
- **分支**：`codex/data-agent-v2`
- **Source clean**：true
- **Provider calls**：1
- **Automatic retries**：0
- **Authorization**：consumed；不可复用

## 1. 冻结身份

- source digest：`sha256:31026edbfad63ff84265a08aa7a0c8b757286f400a612892ef73a4afcf7fb3a5`；
- 场景：`unified_analysis_entry`；
- 目的：`analysis_planning`；
- 模型：`openai/deepseek-v4-flash`；
- Provider host：`api.deepseek.com`；
- fixture：`tests/fixtures/v2_slice4d_combined.csv`；
- dataset fingerprint：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`；
- request fingerprint：`sha256:3e892e4bc09a0a1d4991af963c4498bb83abb67ba89a93bac4e9308e13fd9b5b`。

问题：`销售如何变化，不同渠道是否存在可靠差异？请给出严谨结论、统计不确定性、方法局限，并仅在上下文支持时给出建议。`

## 2. 确定性门禁

- estimated input tokens：348；
- context window：1,000,000；
- reserved output tokens：8,000；
- available input tokens：992,000；
- fits：true；
- planner contract gate：PASS；
- schema fingerprint：`sha256:ccb98eb96b90a0a1745f0ca42ca829a361b0a7fdc016393fe4e72066624766b0`；
- ready variants：7；
- total status variants：9；
- 保存文件与当前源码重新构建结果：逐字段一致；
- Provider calls observed：0。

## 3. 精确调用边界

本 preflight 不签发 authorization，也不调用 Provider。若获得对上述精确 source digest、模型、场景和目的的授权，只允许恰好 1 次 Provider 调用，并允许把上述 fixture 派生规划元数据发送至 `api.deepseek.com`。

失败、Provider error、Planner contract error、unsupported 或 needs_input 时立即停止，不自动重试，不执行后续确定性分析。needs_input 的任何 follow-up 都必须重新估算并取得新授权。

本阶段不宣称真实 Provider journey PASS、Gate F 或产品完成；不切换根入口，不删除旧系统。

证据：`docs/superpowers/evidence/2026-08-20-v2-5c5g-real-provider-preflight.json`。

## 4. 已授权尝试结果

用户随后对本文件绑定的 source digest、模型、场景、目的、数据出境范围和恰好 1 次调用完成确认。执行结果：

- upload：HTTP 200，Provider calls 0；
- planning estimate：HTTP 200，Provider calls 0；
- authorization issue：HTTP 201，Provider calls 0；
- analysis planning：HTTP 201，Provider calls 1；
- automatic retries：0；
- authorization：`provider_auth_636c49c0469b40a486b85808b42597bf`，状态 `consumed`；
- plan：`plan_5249748d6540f9985e5c551e`，状态 `ready`；
- analysis kind：`multi_finding_synthesis`；
- questions：0；
- Planner invocations：1；
- downstream deterministic analysis：未执行。

Ledger 独立复核得到 1 条 authorization 和 1 条 plan；模型均为 `openai/deepseek-v4-flash`，plan 记录的 Provider calls 为 1，error 与 diagnostic 均为空。attempt 证据不复制原始 Provider 响应、reasoning 或 Planner rationale，也不包含 API key。

本次授权已经完全耗尽。该结果证明当前源码上的真实 Provider 首次规划合同成功，但尚不构成完整真实 Provider analysis journey、PASS release receipt、Gate F 或产品完成。未授权也未执行第二次 Provider 调用、根入口切换或旧系统删除。

Attempt 证据：`docs/superpowers/evidence/2026-08-20-v2-5c5g-real-provider-attempt.json`。

## 5. 后续确定性执行发现

对 ready plan 的本地确定性续跑没有调用 Provider，但执行器拒绝 `group=channel` 与 `analysis_unit=channel` 的重复字段身份，并产生 `turn_failed`。该事实证明 5C5F 尚未覆盖执行器跨字段关系；同时失败 turn 当时未持久化，独立 GET 返回 404。

5C5H 已通过纯离线 RED 回归修复共享关系合同和失败 turn 持久化。源码变化使本文件 preflight 对当前源码失效；本文件 attempt 仅保留为 digest `31026edb...` 上的历史 planning 成功事实。

后续记录：`docs/superpowers/plans/2026-08-20-data-agent-v2-slice-5c5h-planner-runtime-relation-closure.md`。

## 6. Token 预算后续核查

5C5I 证明 LiteLLM 对当前模型的 native messages+tools 计数没有完整覆盖 tool schema；本文件记录的 348 tokens 不能继续被描述为完整请求估算。实际请求仍远低于 1,000,000 context window，没有越界事实，但该缺口进一步确认本 preflight 与 attempt 不能升级为 PASS receipt。

后续记录：`docs/superpowers/plans/2026-08-20-data-agent-v2-slice-5c5i-planning-token-budget-closure.md`。
