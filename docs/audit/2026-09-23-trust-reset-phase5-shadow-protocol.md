# 可信发布重置 Phase 5：受 claim/evidence 约束的 Shadow 协议首切片

日期：2026-09-23。开工 HEAD：`main@d5a28ce4faaab2a08fa996d2b985800d437eb18f`。本文件仅记录离线协议切片，不宣称已执行 LLM Shadow 调用或真实 Provider 验收。

## 1. 历史 RED 与决策边界

跨 R7—R21/R4 和三份原始需求看，正确候选与高风险候选都存在：R4 M02 两份 D30 未验证情景候选被散文门误删；R11/R16 M04 曾缺结构化竞争假设闭环；M05/M06 历史出现未知单位或缺失成本归零；R16/R21 M01 出现无依据来源推断。不能用一个自由形式“模型说 pass/fail”替代宿主算术、回执、版本、单位和确认合同。

本阶段实施前明确三联门：

- **RED**：离线 `test_publication_audit_shadow_contract.py` 首跑因尚无 `publication_audit` 协议模块，在测试收集阶段 `ModuleNotFoundError`。语义反例覆盖 R4 M02 的绑定情景、假审计 `overall=pass` 覆盖确定性失败、外来 claim/receipt、陈旧 answer hash、未知 dimension/action，以及未受约束的额外业务断言。
- **结构化替代物**：仅接受 `publication_audit.v1`、当前 `snapshot_digest + answer_sha256`；finding 的 claim_id 必须来自当前 `answer_bindings.v1` 已验证的 typed 情景 claim，evidence_refs 必须属于该 claim 的当前回执/事实/派生引用。无有效绑定的意见只能 `advisory_only`。宿主封闭 dimension/severity/action 枚举、数量/长度与重复 ID，返回纯诊断结果。
- **旧门退役**：Shadow 首切片不退役任何确定性发布门，也不将新审计变为总审批门。`overall` 只是模型自报字段，不改变发布；无效审计只使审计失效，不使已接受答案失效。`reason_untrusted` 是审查素材，不是新数值或业务事实来源，不能被复制进正文/宿主披露。

## 2. 实施范围与证据

`src/data_agent/agent/publication_audit.py` 是纯函数验证器；不连接 `AgentLoop` 发布决策、不调用模型、不写第二账本、不创建 planner 或浏览器路径。当前 typed claim 只有 Phase 2 的 `scenario_extrapolation`；普通 legacy `answer_bindings` 块没有 claim_id，故即使模型为其杜撰 ID，也只能 advisory。`missing_requirements`/`contradictions` 在首切片仅允许空数组；尚无宿主验证它们与 requirement/claim 关系的协议，不能让自由文本绕过引用边界。任何模型建议的 `remove` 等动作在 Shadow 均不执行。

最终 GREEN：新增协议用例 7 passed；跨情景 claim、发布合成、答案合同、来源修订和任务关闭的聚焦回归 178 passed。新目录 `tmp/trust-reset-phase5-protocol-full-offline-1` 的 fail-closed `full-offline` 为 2851 passed、1 skipped、16 warnings；JUnit 2852 tests、0 failures、0 errors、1 skipped，SHA256 `23AE5D209F471D1CCDEECA105F2359CB2E86488E425B8012AFC0662C3C67FA1B`。入口显示 `provider_calls=forbidden`，并显式排除用户原有未跟踪测试 `tests/test_p08_trust_restructure.py`；该文件未修改。原始不可信审计解释可以供离线校准，但输出明确标记 `reason_untrusted`，后续若要执行处置，须先解决其“不得新增事实”的确定性约束与目标 claim 定位，不得把当前首切片误升为 Phase 6。

## 3. 后续门

完成真正 Shadow 还需要：更多 claim 类型的宿主验证边界、固定历史候选的误删/漏检校准、显式审计调度及统一调用账本/预算、故障降级和逐次受控修订。当前没有审计调度或自动调用；任何真实 Provider 调用必须先冻结精确 commit、模型、端点、提示/fixture/oracle digest、矩阵、预算与账本，再获新的显式授权。本阶段证据只能记为 offline protocol，不是 E3/E4、staging 或 production。
