# 可信发布重置：Phase 1—5 架构回顾与 Pre-Shadow 停止门

日期：2026-09-23。审查基线：`main@5c0e4b2f79a0bd6f0a9d9e095812d7b2c7405557`。这是只读源码/历史/离线诊断，不是产品修复或 E3/E4 验收。已按用户明确授权删除两份原有未跟踪文件；操作前验证了绝对路径、普通文件和 untracked 状态，删除后根工作树 clean。它们不在 Git 中，不能用 `git restore` 恢复。

## 1. 对照三份原始需求及全历史的结论

Phase 1 canonical history、Phase 2 M02 回执渲染、Phase 3 确认类型化均有对应历史 RED、结构化替代和离线回归；Phase 4 没造第二 journal，显式竞争假设的 plan/关系审计门按用户裁决保留；Phase 5 目前只是纯离线协议，未产生隐藏模型调用或发布影响。整体方向没有改成词表补丁或第二 planner，但审查时发布边界存在两类已复现的架构性误放，与原始 CP 的 CR03/CR07 和总计划 §4.3—4.5 冲突，因此先插入确定性修复，不直接升级完整 Shadow/处置。

审查不是围绕最近被叫停的 R4 单一批次。历史 R8/R11/R14/R16/R21 表明：散文门会误删正确内容，模型/任务结构会缺闭环或卡死，旧词法门也未阻止未知单位、缺失归零和无依据来源推断。R4 M02 给出新的正确候选误拒和 `answer_bindings.v1` 种子，但不能单独定义所有修复。既有 2181、2393、2585/2569/2644/2713、2812 至当前 2851 项全量离线绿灯，均不能替代以下现行反例的边界判断。

## 2. 现行 RED A：明确子问题可被无关事实“覆盖”

`publication_synthesis._answer_coverage_issues()` 看到 requirement label 后，只要邻近正文有数字或“缺少/未计算”等标记，就写 `answer_coverage=answered/not_computed/evidence_insufficient`。`apply_answer_binding_coverage()` 也仅据 binding 里的 requirement_ref 和片段文字标记写状态；`parse_answer_bindings()` 对普通块只检查 fact/derived ID **在当前 packet 中存在**，没有验证它是否支持被引用的 requirement，也没有核对 fact 数值与片段数值。

只读离线复现：packet 的唯一 fact 是“收入=100”，用户 requirement 是“复购率”。正文“复购率为20%。”在**没有 binding**时 `validate_final_narrative_issues()` 返回 `[]` 且把 requirement 标为 `answered`；再把同一片段绑定到当前 packet 中的收入 fact，`parse_answer_bindings()` 仍返回 `issues=[]`，最终正文校验仍为 `[]`。这不是旧版本 ID 或算术误差，而是缺少 requirement→claim→相关证据的语义所有权。现有 AC16—AC21 测试覆盖“关键词无答案”、未知 fact ID 等较窄负例，未覆盖“当前但不相关 fact + 错误数字”。这正违反 CR03 的“不把关键词出现、任务 completed、模型自报当覆盖证明”。

## 3. 现行 RED B：宿主发布校验失败时原文可直接放行

- 已有 `status=ready` 的 packet 时，强制让 `validate_final_narrative()` 抛异常，`AgentLoop._render_finalized_publication()` 的外层 `except` 对无 `answer-bindings` 的散文返回 `(原始候选, None)`。离线复现使用“复购率为20%，但没有任何复购回执。”，实际得到候选正文和无错误。
- 对有可发布工具证据的回合，若 `_prepare_publication_packet()` 因异常返回 `None`，`_render_terminal_publication()` 随后同样返回 `(原始候选, None)`。离线复现让证据标志为真、packet 构建为 `None`，实际返回“复购率为20%。”和无错误。
- 发布修订次数已有 `_turn_publication_recovery_used` 限定；未发现这里会无限循环。真实风险是**fail-open**，或把修复粗暴改成全局 fail-stop 后重演“独立可信内容被一条错误吞掉”。需要在确定性边界上分离可验证 claim 与无 packet 的候选，不能靠末尾声明抵消已显示的不实数字。

## 4. 用户已确认的插入阶段三联门

用户已明确选择“先修发布边界”，因此完整 Shadow/处置继续暂停。以下不是对所有 claim 类型的完成宣称，而是本次确定性修复边界。

- **RED**：将上述两个离线诊断固化为基线 HEAD 的测试；另加跨历史正例：已有正确收入/留存结论、明确但未计算的子问题、R4 M02 正确情景、多来源/版本变化，确保安全修复不重现 R8—R21 误删与 R21 task 死锁。错误数值与不相关 fact 必须拒绝其 `answered` 权限；不能凭普通同义表达擅自声明事实归属。
- **结构化替代物**：沿用 `answer_bindings.v1`、当前 packet 的 requirement/fact/derived refs 和数据身份。逐 claim 核验 requirement 与证据的所有权，来源事实或派生量由宿主重算/渲染；无绑定的明确子问题标为 typed gap/unassessed，已核实的独立 claim 仍可发布。对 packet/validator 的内部异常，返回明确、有限恢复的非成功状态；仅允许仍可从**当前**权威快照验证的 claim 被保留，不能返回未经校验原文。
- **旧门退役**：退役“label 旁边有数字/缺口词就算覆盖”及“当前 packet 中随便一个 fact ID 就支持任意 requirement”的放行；移除或降级发布异常时的 raw-prose fail-open。不能补自然语言关键词、增加第二事实库/规划器，也不能让 Shadow `overall` 替代这两个确定性判定。

## 5. 本次实现与尚未关闭的边界

- 新增十条边界离线测试：无绑定数字、缺口措辞洗白同句/跨句错误数字、合法 typed claim 旁的第二个裸数字、当前但无关 fact、正确 fact 搭配错误自由数值、非数字回执、可保留的匹配 typed 事实、validator 异常、当前回执 packet 丢失。最初五条在修复前实测 RED；跨句与第二数字两条也在扩展规则前实测 RED，其余负例按同一原理补强，正向 typed 测试随实现加入。既有 AC17 的八项可信加一项具体缺口继续保留。
- 扩展现有 `answer_bindings.v1`，仅 `observed_fact` 的 `claim_id + observed 状态 + 无数值占位符 + 一个 requirement_ref + 一个 fact_ref` 可以为简单观测指标赋予 `answered`。宿主要求 fact 路径有与指标名完全相同的结构化路径段，或同一回执为精确 `metric/value` 对；然后在占位符位置渲染原始数值并标注单位未确认。匹配不确定时保留未评估/明确缺口，不能由模型的数字或同一 packet 任意 ID 补齐。多项中八项独立可信、一项具体缺口的 AC17 正例保留。
- 每次正文校验重算 requirement coverage，防止先前候选的 `checked` 状态污染下一候选；凡明确子问题所在子句含标签和已验证占位符之外的裸数字，直接产生 `unbound_requirement_numeric`，即使另一句给出 gap 或同一项已有可信 claim 也不能洗白。裸数字检测是结构边界，不新增自然语言词表；gap 子句本身若夹带裸数字也不能授权 coverage。发布 validator 抛错或本轮有证据但 packet 未 ready 时，返回非成功错误而不是原文。恢复仍是既有一次定向修订，没有引入新的回环或模型调用。
- 这不是所有高风险自由散文的完工：**已抽出的明确子问题**旁的第二个裸数字已被阻断，但对未抽取为 requirement 的问题、与该子问题不在同句的独立数字、无数值的过强结论，现有非全量数值/语义检查仍可能漏掉。`extract_explicit_requirements()` 对某些单一问题不产出 requirement，因而本次覆盖门对该类问题不提供完整保护。通用 `comparison/derived_metric/descriptive_fit` 等 typed 宿主渲染尚未实现；复杂同义指标也可能因无法证明 exact 结构身份而降级。当前子句级数字边界也会保守拒绝包含未绑定日期/窗口数字的正确表述，下一阶段应通过结构化范围引用恢复内容，不能为了少一次误拒而临时放开错误数字。后续须先用跨 R7—R21 与 R4 的正反候选冻结精确范围，再决定是对未绑定数值统一定向修订，还是逐 claim 族扩展宿主渲染；不能临时加词表或把这一缺口交给 Shadow 随机裁决。

## 6. 审查范围和剩余风险

Phase 5 `publication_audit.v1` 当前完全不接入发布，因而不会制造随机总审批门；但它只认识 M02 typed claim，普通块无稳定 claim_id，尚不能覆盖 CR03。`reason_untrusted` 还不是可执行处置依据。Phase 3 内部清洗风险与成本/分母/窗口正例仍由已有回归保护；本次未发现需要修改确认类型策略的证据。

本审查及其插入阶段没有运行浏览器或调用真实 Provider。修复后的离线证据必须与原有 Phase 1—5 记录分开表述；即使完整离线回归通过，也不能声称 E3/E4、所有高风险 claim 或 Shadow 校准已完成。

离线运行环境备注：第一次整批使用较长目录 `tmp/trust-reset-pre-shadow-pub-boundary-20260923`，结果 2856 passed/1 skipped/1 failed；唯一失败为 golden funnel 的发布收据文件 `FileNotFoundError`，路径长度/目录名影响已通过短目录 `tmp/tprb3` 的整个 golden 文件 5/5 通过交叉验证。第一次失败保留为环境收据，不能抹成通过。随后 `tmp/tprb4`、`tmp/tprb5` 因补入同根的未绑定数字绕过回归而中途主动停止，不作为验收收据。最终新短目录 `tmp/tprb6` 的 `full-offline`：**2861 passed、1 skipped、16 warnings、0 failed**；JUnit `tests=2862/errors=0/failures=0/skipped=1`，`junit.xml` SHA256 `018702B8CB0DED188422723A423E9666569E346A490CE051D0C1D73FE5D87FF8`，runner 明确 `provider_calls=forbidden`。定向五文件 180 passed。此证据只到 E2；未运行浏览器或真实 Provider。
