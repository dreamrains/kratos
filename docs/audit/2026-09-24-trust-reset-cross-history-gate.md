# A+B 下一门：跨历史价值与发布安全双轨校准

日期：2026-09-24。检查点 `main@b7e1f981b395a3a5007998013422886b8958487e`；工作树复核时无 tracked/untracked 改动。本记录用于上下文压缩后的实施续接，不是 E3/E4 验收或正式发布策略批准。上位约束是 [重置计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md) 及其三份 VP/IC/CP 原始计划；当前 A+B 只在默认关闭的离线准备范围内，C/D 另设门。

## 1. 为什么不能只追最近 R4

| 历史面 | 已证实的价值/失败 | 本阶段对照目标 |
|---|---|---|
| R7—R21 跨完整与部分真实批次 | M02 正确边界多次被散文门误拒；M03 相邻日期“同比例”、六来源/导出；M04 版本/假设及 task 权威；M05 CV、单位与方法；M06 成本缺失归零 | 正确边界不能因改核心消失；错误单位/版本/算术/来源不能从旧文本获权威；未完成 task 不吞独立可信 claim |
| R11 正例 | D7=10% 且拒绝无验证 D30 的边界内容正确，旧散文无当前 typed 占位符 | 新结构可重建 D7 和观测范围；不从旧原文原字节放行，也不自造 D30 |
| R16 完整真实批次 | M05 **通过**，保留 12/120、未知单位、窗口与方法上下文；其他五项失败 | 保留已证实数值和未知单位，不把 `run_python` 工具名当方法结论；解释层缺权威时显式记 `unassessed` |
| R4 中断真实批次 | M01/M02/M03/M04 与 M05 前三轮有可用轨迹，M06 未执行，另有取消的 M02 误启动 | 只作分项正反回放，不报完整矩阵；M03 六来源表/图、M04 假设审计不能以“R4 通过”替代当前快照身份 |
| 三份旧本地会话 | 格式无 typed 占位符，不是正确性 oracle | 检查旧会话兼容/价值风险，不把模型自然回答自动列作可信事实 |
| 当前 typed 负例 | 有效比较 binding 后独立“另一结论为99%。”在正式校验中 `binding_issues=[]`、`narrative_issues=[]` | 核心应移除无绑定数字；现行发布未切换，故这是**仍在的风险** |

历史数量与精确来源见 [首轮双轨](2026-09-24-trust-reset-dual-track-calibration.md)、[Phase 0 复核](2026-09-23-analysis-agent-trust-reset-phase0-review.md)、[R16 整合记录](2026-09-09-answer-intent-integration-record.md)。`tmp/tprb20` 的 2913 passed/1 skipped 是本 HEAD 的 E2；不能与旧 R16 M05 E4 通过或 R4 中断结果合并成当前 E4。

## 2. 新发现的具体结构缝隙：结果存在不等于入包

只读检查 R4 M03 `sessions/50e734df7af7/analysis_state.json`：`tr_3e70ccb10380` 的 `synthesize_time_series` 回执有 102 个 `publication_facts`、34 个 `publication_fact_groups`，绑定 `sources_combined` 及六个源的版本/指纹，`publication_contract.observation_window` 也逐源写出两日各两行。然而该会话的最终 `publication_packets[-1].sources` 只有 `tr_4ee00ec935b1`（`record_evidence_record`）；它的 facts 是统计细节缺口与证据 ID，不是六来源两日金额表。旧 evidence 的 claim/measurement 写有六来源数值，但由模型填写，不能凭此直接授权可信核心。当前构包器按 `receipt_ids` 先过滤可选回执，再 `_select_sources`；因此若当前轮/终局 receipt selection 没有综合回执，新增 renderer 再强也无法从该 packet 重建六来源。

这是可离线验证的**入包/回执选择问题**，不是“补一句提示词”或“让 Shadow 批准旧证据”。当前 `loop.py` 的 `_SUBSTANTIVE_TOOLS` / `_PUBLICATION_EVIDENCE_TOOLS` 均不含 `synthesize_time_series`，而 `_prepare_publication_packet` 依该集合调用构包器；所以即使调用方显式选了该综合回执，也会在工具集合门被排除。R4 历史最终包是否还有其他同轮追踪问题仍未证明。不能为解决它偷偷从全会话挑任意旧回执：必须限定本轮显式 receipt IDs、scope/版本、结果 digest 和显式需求，且保留预算/遗漏清单。也不能从上传原始文件静默重算，绕过已有工具/收据。

## 3. 下一离线切片的可执行边界

1. **RED 与双向 oracle**：在同一 current-turn、同版本 synthetic fixture 中同时提供六源综合回执、后到 `record_evidence_record` 和图表回执；检查最终 packet 是否保留两日金额/记录数的当前综合事实或可恢复省略引用。负例是跨轮次/旧版本/不同会话综合回执不得入包。另保留 R11 D7/无 D30、R16 12/120/未知单位和有效 binding＋独立 99% 的当前正反基线；不把旧自然句当新 parser 合法格式。
2. **结构化替代**：只沿用 `turn_receipt_ids`、现有 `publication_packet`、fact groups、版本和 detail refs；若 RED 成立，只调整当前轮确定性收据选择/入包或遗漏说明。数值/日期/相对变化若要成为 answered，须由同指标当前工具 fact/可复算运算绑定；原始字段和图表仍只是上下文/产物，不借模型 evidence 的 `metric/claim_key` 授权。
3. **退役旧门**：目标仍是“一个有效 binding 即整篇自由散文可信”与从中文子句反向猜事实；本离线切片不退役正式门、不改变 AgentLoop 发布、不接审计模型。回执、算术、单位、版本和同会话身份硬门一律保留。
4. **GREEN/回归**：按字段记录六来源两日金额、绝对/相对变化、记录数、图表 artifact-only、旧版本隔离、当前假设关系、R11/R16 价值保留与 99% 剔除的各自结果；先定向，再 fresh fail-closed full-offline。正确事实保留率和错误事实剔除率分别报告，未知/不适用分母不计作通过。E3/E4 不在此切片。

若诊断表明本轮选择逻辑已能正确入包，下一步转向已入包事实的**结构化计算/原位渲染**，而非改选源。若唯一可用材料仍是模型自述 business claim、旧方法表或没有同快照身份的关系，保持 `unassessed` 并与用户讨论价值取舍，不能降低硬证据标准或靠词表/尾注/Shadow 总审批兜底。

## 4. 四门与停止条件

- A 目前只部分完成：可信核心预览保留有限边界和 artifact-only/闭合描述性关系，但未达到六来源结论与旧解释等价保留；不能默认发布。
- B 是纯函数模拟，`publication_effect=none`；审计理由不进入正文，外来/过期 finding 不处置；不能声称 Phase 6 运行时生效。
- C 仍无真实 Shadow 调度/成本/故障收据；D 仍无用户对正式策略切换的裁决。两者不因本文件获授权。
- 一旦需要新增词表硬门、第二 planner/journal、自由散文整体放行、隐藏审计 Provider、从模型自述假设升级因果/显著性，立即停下讨论。真实 Provider、push、部署仍须各自新授权。

## 5. 续接时先核实

重读根 `AGENTS.md`、主计划及三份原始计划；`git worktree list --porcelain`、`git rev-parse HEAD`、`git status --short --branch`；只读核对 R4 目录和 R16/R11 历史收据；阅读 [实现交接](2026-09-23-trust-reset-implementation-handoff.md) 第 10—13 节及 [离线投影记录](2026-09-24-trust-reset-offline-core-projection.md)。旧文档中的 `main@5176c41`、两份未跟踪文件和“只做 Phase 0”是历史快照，不得用来覆盖当前状态。提交仅 stage 明名文件，不删改用户新 dirty；当前没有完整 E3 或新 E4。

## 6. 第一条 RED/GREEN：仅离线纳入显式选中的综合回执

进入代码基线 `main@ac84dd8`。`test_current_six_source_synthesis_facts_enter_only_explicit_offline_packet` 的 RED 为 `StopIteration`：普通与离线 packet 都无法在 `sources` 找到显式选中的 `tr_six`。结构替代只在 `offline_trust_projection=True` **且调用方传了显式 receipt IDs** 时把 `synthesize_time_series` 加入构包可选工具；仍使用原有成功回执、fact group/预算、省略清单、packet digest，不触碰 AgentLoop 的普通工具集合或模型 prompt。六个源的原始字段可在可信核心预览，但 `accepted_claim_ids=[]`；不存在显式 ID、或 ID 未选中时不进入。此离线 API 本身尚不证明所传 ID 与当前 workspace 版本一致，不能用它授权业务结论。正常 packet 仍刻意不含它，离线 packet 仍被 `publication_packet_prompt` 拒绝。

因此旧门**尚未退役**，本切片也没有声称六来源业务比较已经 `answered`。独立 99% 的正式误放和 R11/R16 的旧方法解释损失仍是双轨校准项。定向两文件 17 passed；`tmp/tprb21` 全量离线 **2914 passed、1 skipped、16 warnings、0 failures**（182.43s），JUnit SHA256 `DE7FCF4CB7FE6CBDD39590B644FB371615A8AAC1CC0DA74DF08F7AA38BD742B0`，但其后增加了 packet digest 测试断言，故它不是最终树的收据。**最终 fresh `tmp/tprb22`** 全量离线 **2914 passed、1 skipped、16 warnings、0 failures**（183.99s），JUnit SHA256 `D689F1C2FD27A52EC7098B051DCA55884A66F8CAC7939FE74E71B3D9E490030D`，runner `provider_calls=forbidden`。本轮真实 Provider initiated 0；未运行 E3 或 E4。下一步须验证同快照六源两日金额/行数的宿主计算身份及版本，再决定如何原位渲染；只凭字段入包、图表或模型 evidence claim 不能升格。
