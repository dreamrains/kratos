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

## 7. 第二条 RED/GREEN：六源金额不在回执，须核对既有派生数据版本

进入基线 `main@508a580`。先只读查 R4 M03 原始结构：`synthesize_time_series` 的 102 facts/34 groups 是覆盖、日期、行数、来源和派生身份，**不含六源两日金额**；`preview_data(sources_combined)` 的金额只在文本 `result_preview`，`publication_facts=[]`。旧 EvidenceRecord 的金额/变化由模型填写，不能把它当宿主计算授权。源工具 `src/data_agent/tools/multifile.py` 已在 workspace 生成 `sources_combined` 的 copy-on-write 派生帧。因此下一步不是解析预览文本或补词表，而是仅在离线构包中读取这一**已有派生结果**并核对身份。

RED：新增 `test_phase6_offline_multisource_table.py` 三项初始失败，均为 `build_publication_packet()` 不接受 `offline_workspace`，说明现有 packet 无宿主所有的数值通道。结构替代：可选 `offline_workspace` 只在 `offline_trust_projection=True` 生效；必须有显式选中的成功综合回执、同 packet source/result hash、`multi_file_time_synthesis.v1` 与 descriptive 状态、六源/派生数据的完整当前 identity、派生帧实际 fingerprint、同序父版本、两日递增日期、覆盖窗口/行数和零缺失。仅从同版本现存派生帧读取每源两日值，用 Decimal 复算绝对/相对变化并纳入**同一 packet digest**。无 workspace、无 ID、任一源或派生版本改变、伪造身份/非有限值则不投影；首日为零时百分比为不适用。当前只处理 2—12 来源且恰好两日的有限表格，其他形状保留 `unassessed`，不静默做跨来源合计或单位换算。

预览原位显示每源日期、原始尺度金额、绝对/相对变化、源/有效行数及单位未确认，并标注“描述性预览，不自动授权已回答”；`accepted_claim_ids=[]`。这仍未给出用户子问题到 claim 的确定性绑定，也未恢复 R16 的方法解释或 M04 非闭合假设关系。**旧门尚未退役**：正式完整候选仍可能放行无绑定 99%；离线 packet 仍不能进入模型 prompt，AgentLoop、正式发布与 Shadow 调度均不变。R11/R16 正例、R4 部分轨迹、R7—R21 错误单位/版本/算术仍共同构成下一默认策略校准面，不以此六源样本代表总体完成。

当前三文件定向为 **21 passed**（含旧 R11/R16 边界、99%/审计动作及新增零分母/伪身份负例）。最终 fresh `tmp/tprb23` full-offline **2918 passed、1 skipped、16 warnings、0 failures**（186.00s），JUnit SHA256 `4D7B0B628E445EA60C09393B46519CD97B155D4D615C2F590F2EE7192B4B55F2`，runner `provider_calls=forbidden`；不能用前一 HEAD 的 `tmp/tprb22` 代替。真实 Provider initiated 0；E3/E4 未执行。

## 8. 跨历史复核后的架构提醒：不能无限叠加专用表格

同轮只读复查 **R16 完整真实批次中已通过的 M05**（`tmp/p08-real-provider-20260914-b833501-r1/sessions/58da9082dc02`）：它有 `transform_data(group_aggregate)` 的回执，事实字段仅为 operation、`rows=1`、派生数据集名和列名；旧终局 packet 的 `sources` 却仅有两条 `preview_data`、两者 `facts=0`。12/120 与方法表存在于旧自然正文和工作空间数据，不在旧 packet 的数值 fact 中。故六源专用表格虽然解决一个离线正例，却**不能单独满足** CP 的一般“结果与方法上下文保留”目标。R11 的正确 D7/无 D30 同形正例、R7—R21 的错误单位/算术/版本轨迹也不能用六源表推断已通过。

下一步在增加 `transform_data` 等第二张专用表之前，应先审查一个**通用的、仍在现有 packet 内的派生结果快照契约**：仅宿主已执行工具、同轮选中的回执与 current workspace 的派生 identity/父版本/结果摘要闭合时，才将受预算约束的数值结果和方法边界作为结构化数据投影；工具专属计算规则再决定哪些 claim 能被复算和授权。它不能从自然正文、`preview_data` 文本或模型 EvidenceRecord 回填，不能重建第二 planner/账本。此处是**设计建议，尚未实现或获准切正式路径**；在讨论和跨历史 RED 前，不继续照着每次失败新增一族表格。

## 9. 第五离线切片：共用派生结果快照，仍不赋予 claim 身份

用户认可 §8 的通用设计后，从 `main@7d348ad4b85c663de1b81acaa6041036fd613a32`、clean 工作树开始实施。RED 为新增 `test_phase6_offline_derived_snapshots.py` 三项均因 `derived_snapshots` 不存在而失败（`KeyError`），不是靠候选文本措辞构造的误判。R4 M03 与 R16 已通过 M05 的共同结构根因均是工具生成了派生帧，但历史终局 packet 只有元数据或 facts=0 的预览；前者六源两日金额、后者 12/120 不应由旧自然正文或模型 EvidenceRecord 升权。R11 正确 D7/无 D30、R7—R21 的错误单位/版本/算术、有效 typed binding 旁独立 99% 的正式误放仍是双向校准面，不能因本切片的两种工具结果可见就宣布总体完成。

结构化替代物是现有 `publication_packet.offline_trust_projection.derived_snapshots`，不是新 planner、账本或发布通道。仅显式 receipt IDs、成功回执、同 packet source/result SHA、当前 workspace 原始/派生 identity、同序父版本及派生帧实际 fingerprint 全部闭合，才截取最多 16 行、16 列、单快照 16K/总计 32K 字符的 typed 原始单元格；当前覆盖 `synthesize_time_series` 与 `transform_data` 两类已执行工具。状态只为 `context_only`，单位不推断，也不把 operation/列名自动当作用户指标身份。已有两日六来源表改为消费这一共用快照后再按工具专属覆盖事实做 Decimal 复算，不再独立读取 workspace；R16 型 12/120 只作同版本原始字段预览，不宣称方法结论或 `answered`。快照与表同入既有 packet digest。缺 ID、过期父版本或无 workspace 均不投影；**身份已闭合但超出预算**则在同 packet 的 `snapshot_omissions` 记录受限原因，预览明示未纳入，不能静默当作已回答。离线 packet 仍不能进入模型 prompt。

本切片**没有退役正式旧门**。退役目标仍是“一条有效 binding 使整篇无绑定散文获得事实权威”；正式 AgentLoop、默认发布、Shadow 调度和审计处置保持原样。A 的 R11 正确边界、R16 方法解释、M04 非闭合关系和宿主证实的具体缺口尚未等价重建；B 仍只有 `publication_effect=none` 的离线动作。下一门先以同一历史正反矩阵评估快照的价值保留、敏感字段/预算/遗漏呈现、指标身份如何授权 claim，才能讨论 A 结束或 C/D。E3/E4、真实 Provider、push、部署均未获此次授权。

三项新增测试初始 RED 后，发布/离线投影/审计相关七文件定向 **192 passed**。第一次完整 `tmp/tprb24` 为 **2921 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `60F86AB2F5AFA98E8D1756004948206A9BD58BB84D9928239CA16E64776D4767`；其后审查发现预算超限静默遗漏，故这份收据**不是最终代码时点**。补入同 packet `snapshot_omissions` 与预览说明后，定向仍 **192 passed**；最终 fresh `tmp/tprb25` full-offline **2921 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2922/failures=0/errors=0/skipped=1`，SHA256 `06D71A3A7B812D80B5C98FE9E36D1C9D31296FF12D9731CF136801629E8A8900`，runner `provider_calls=forbidden`，本轮实际 Provider initiated calls=0。它仍只属 E2；没有完整 E3/E4 或生产验收。期间只读复核 R16 原始回执 `tr_fb774270b1c9` 的 `group_aggregate`、七列及父/派生版本链与夹具契约一致；没有把旧会话自然回答当作新 renderer 通过证据。

## 10. 第五切片后跨历史所有者复核：下一步不是第三张专用表

2026-09-24 从 `main@f2ea7e3db1da5d3263fd8a0859afa6c4cf355e75`、clean/ahead 65 只读复核。它是上一提交后的证据检查，不更改正式发布、离线代码或旧会话。重读三份原始 VP/IC/CP 的门：正确已执行分析不得因发布误拒消失；真实业务语义才暂停；明确子问题要可信结果或**有宿主证据**的具体缺口，同时独立无据事实不能借一个有效 binding 放行。R4 是中断批次，仍须以 R7—R21 及 R16 完整批次的正反结果为背景。

| 样本/当前保留 | 原始宿主所有者与欠缺 | 禁止的捷径 |
|---|---|---|
| R11 完整批次 M02：正确给出 D7=10%、拒绝 D30，旧散文被误拒；当前离线核心只保留观测 x=1—7 与未验证外推边界 | `tmp/p08-real-provider-20260913-fe83160-r1/sessions/72b58ee16e69` 的 `curve_fitting` 回执 `tr_1536f8a2e4a5` 有已执行参数 `x_col=day,y_col=retention`、同回执 `points[6].x=7, points[6].y=0.1`、当前数据版本与 descriptive/no extrapolation scope；该拒绝会话 `publication_packets=0`，没有可重用的终局包，且未提供可核验的百分比单位身份。可把 **0.1 原始尺度的 D7 观察**作为待校准结构候选，不能仅凭旧正文输出“10% 已回答” | 不从“D7”字面或模型自报标签反向猜指标，不把 0.1 自动乘百，不恢复旧散文原字节 |
| R16 完整批次 M05 **passed**：当前合成离线夹具可预览 12/120 原始字段、单位未确认，但方法表尚未重建 | `tmp/p08-real-provider-20260914-b833501-r1/sessions/58da9082dc02` 的 `transform_data` 回执 `tr_fb774270b1c9` 只有 `operation=group_aggregate`、一行、七个列名及 `M01-sales`→`M01-sales_totals` 父/派生身份；具体执行表达式留在同版本 workspace identity，旧终局 packet 仅两条 facts=0 的 `preview_data`。本轮没有把旧 pickle 载入新包作真实重放 | 不把列名或模型旧方法表当作方法验证；不说 R16 已在当前 HEAD 重新通过 |
| R4 中断批次 M03：合成六源两日帧离线可复算逐源数值，artifact-only 图表可投影 | 旧会话 `50e734df7af7` 的综合回执有版本/覆盖而无金额；金额在派生帧，历史终局只选 `record_evidence_record`。当前投影要求显式选中且 workspace 同版本，**尚未证明历史最终 receipt 选择已修** | 不把六源字段可见或模型 EvidenceRecord 数值算作全项 answered，不跨未确认单位的来源合计 |
| R4 中断批次 M04：旧正文解释 v1/v2，但当前离线关系投影只对同指标可复算的 `compare_periods` 闭合 | `f2db8a75de3d` 的 v2 `analyze_time_series` 回执 `tr_08de4cb55518` 给出 amount 均值 10、std=0、slope=0、direction=flat；v2 假设集的实际 ID 为 `hypotheses_m04_hyp_v2_..._h1` 等，而旧 evidence 的关系目标写 `h_trend`、`h_level_shift`，并不匹配这些 ID。即使值可信，关系授权仍缺假设身份/谓词的宿主闭合 | 不把模型 evidence 的 refutes 文本或旧 H1/H2 别名直接写为已反驳；不取消显式 plan 审计门 |
| 当前 typed 正反夹具：有效 claim 可保留，旁边独立无据 99% 可从离线核心剔除 | 现行正式完整候选仍可放行该 99%；R7—R21 还见错误单位、CV 算术、来源/版本混淆和正确 D30 否定句误拒 | 不用一个绑定给整篇散文授权，也不靠新词表或末尾免责声明兜底 |

**下一 RED（尚未执行）**应同组验证三类结果形状：`curve_fitting` 的执行参数＋点对、`transform_data` 的同版本派生帧、`analyze_time_series` 的趋势字段与假设 ID。正例分别是原始尺度点值、聚合字段、无趋势事实可见；负例是错列/错版本/错回执、未确认单位换算、假设别名错配、无据 99% 仍不进核心。对照旧通过项要分别记“原始值保留、方法边界保留、用户子问题 answered、正确缺口”，不能用正文长度或测试总数代替。

推荐的**结构化替代方向，待裁决后实现**：仍在现有 publication packet 和 `answer_bindings.v1` 内，抽象“已执行结果身份”（回执参数、输出 facts 或同版本派生帧、目标列/指标、单位状态、范围），把不同工具的结果映射为受预算的宿主拥有上下文；只有工具同名身份及可复核运算能进一步授权 `answered`，否则 `unassessed`。这比按 R11/R16/M04 各加一个专用 renderer 更接近 VP/CP 原目标。旧门退役目标仍是自由散文整体获权威，确定性回执/数值/版本门不退。该方向会扩展离线投影的结果类型，并触及任意 `transform_data` 小帧可能含敏感原始文本的披露策略；在隐私/粒度预算与单位授权未定前，**不把上一切片默认开启或接入 AgentLoop**。若要求同时恢复历史“10%”、R16 完整方法表及 M04 关系，但这些身份在旧回执中不足，必须请用户就继续 `unassessed` 与新增宿主契约作明确取舍，不能偷偷从旧正文回填。

## 11. 第六离线切片：已执行结果身份与文本默认遮蔽

用户已明确同意 §10 的建议，从 `main@c61ece7522b18a6fadd2354d7f05d79ba2ee094a`、clean 工作树进入实施；§10 的“待裁决”是上一检查点。RED：新增 `test_phase6_offline_executed_result_identity.py` 三项分别因 `executed_results` 不存在（两项 `KeyError`）和 `transform_data` 派生帧仍把 `secret@example.com` 文本单元格原样投影而失败；R16 型聚合方法参数测试也因 `method_parameters` 不存在失败。这些 RED 是同一结果身份/披露缺口，不是新增措辞词表。

结构化替代仍在**同一默认关闭 packet**：显式选中的成功 `curve_fitting`/`analyze_time_series` 回执，须同时匹配 packet source/result SHA、已执行参数中的数据集与列、当前 workspace identity 和帧实际 fingerprint，才投影受限数值。R11 型同回执 `points[i].x/y` 成对按**原始尺度**显示（例如 x=7、y=0.1），R4 M04 型 time-series 只显示均值/std/斜率/方向等描述字段；均为 `context_only`、`unit_status=not_confirmed`，不把 0.1 写成 10%，不从 flat 自动反驳旧假设别名。点数和字符预算超限在同 packet 明示遗漏。R16 型 `transform_data(group_aggregate)` 仅在已执行参数的 `group_by/agg` 与同版本派生 identity 的表达式严格一致时展示分组和聚合函数；只说明执行方式，不证明方法适当或用户子问题 answered。派生帧所有任意字符串单元格默认变为 `{type:redacted}`，保留有界数值/日期单元格；来源名和列名等既有元数据仍可能出现，**这不是完整 PII 识别或生产披露政策**。

退役旧门的目标未变：一条有效 binding 不应授权整篇自由散文。**正式旧门本切片尚未退役**；普通 packet、AgentLoop、真实 Shadow、审计处置和 Provider 不变。当前离线结构仍不能从历史旧会话直接生成新 typed binding；R11 百分比单位、R16 方法适当性、R4 M04 错别名关系和独立无据 99% 的正式误放保持未闭合。下一步须对跨历史正反候选分别记录原始值/单位/方法/关系/具体缺口的保留与误放；只有宿主验证过的指标身份才能给 `answered`。未做真实会话回写或旧 pickle 载入重放。

定向八文件最终 **197 passed**，包括曲线/趋势错版本和错列、任意文本遮蔽、超点数明确遗漏、聚合参数与执行表达式不一致不展示，以及既有六源/Shadow/正式发布边界。最终 fresh `tmp/tprb26` full-offline **2926 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2927/failures=0/errors=0/skipped=1`，SHA256 `C2C6027389668BD902FC96100509A98F81FB88D237C20E07BAF989C383711C17`；runner `provider_calls=forbidden`，实际 Provider initiated calls=0。仍仅 E2，不是当前 HEAD 的完整浏览器 E3、真实 Provider E4、staging/production 或旧会话重放。下一门不可再靠一个离线 fixture 的 100% 扩大适用范围；须把历史正确价值与错误结论分开校准，再讨论默认策略。

## 12. 第七 A+B 离线切片：模型提议目标、宿主核对结果身份

用户批准后从 `main@83dac2fb3d97c8d45c7a704517b4de31f4763577` clean 工作树进入。跨历史动机不是单一 R4 失败：R11 完整批次的 `curve_fitting` 同回执确有 `day=7, retention=0.1`，但旧正确自然句“10%”缺百分比单位身份；R16 已通过 M05 的原始值及方法仍不能由一个工具标签全量恢复；R4 M03/M04 的派生帧和错误假设别名要求版本/关系硬边界；有效绑定旁独立 99% 的正式误放尚在。R7—R21 的错单位、错版本、错算术和正确否定句误拒也保留为后续双向校准面。

本切片 RED：新增选择器测试初跑因 `validate_offline_target_selectors` 不存在而在导入阶段失败。结构化替代物没有另建通道，而是离线解释现有 `answer_bindings.v1.blocks[]` 的提议字段 `target_selector={receipt_ref,dataset_version_id,x_column,y_column,x_value,expected_y}`。宿主要求 packet binding digest 一致、字段和状态闭合，并在同一默认关闭的 `executed_results` 中找到唯一 `curve_fitting` 结果，再核对回执 ID、结果 SHA、数据版本、输入列、点对以及原 source 的 `points[i].x/y`。错列、错点、错数值、跨回执、旧版本、旧 digest、投影/原事实不一致均拒绝。通过只产出原始尺度数值、`unit_status=not_confirmed`、`target_status=verified_result_identity`、`answer_coverage=unassessed`、`publication_effect=none`；未建立独立可信的用户子问题关系，不允许模型自报 requirement 变成 `answered`。正式 `parse_answer_bindings` 仍拒绝试验字段，普通 packet/AgentLoop/用户可见发布、Shadow 和 Provider 均不使用它。

本切片将来要退役的旧门仍是“一条有效 binding 为整篇自由散文背书”，而不是当前已退役任何词表门或削弱回执/版本/数值硬门。它**没有**让 R11 0.1 自动变成 10%，也没有修复正式 99% 误放、R16 方法解释或 M04 非闭合假设。后续 A 门需用历史正反候选审查可信结果、具体宿主缺口、产物与解释保留；如果身份不足，保留 `unassessed` 并讨论工具契约，而非从旧正文回填。B 的动作仍只纯离线；C 真 Shadow 调度与校准、D 正式策略及完整 E3/E4 各自独立。

本切片定向七文件 **188 passed**；fresh `tmp/tprb27` full-offline **2930 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2931/failures=0/errors=0/skipped=1`、SHA256 `0790E1759F31306768DBA9456465834080DD7DD592C9F2E7F10A4D9ABCBED1B0`，runner `provider_calls=forbidden`，真实 Provider initiated 0。没有 E3/E4、旧会话实际重放或正式发布策略切换；该试验不是 Phase 6 完成或 Phase 7 启动证据。

## 13. B 门一次修订预算与 A 门复合请求证据缺口

从 `main@3d5f6eaf0bec63826555a2d23ba38d2177cbc9eb` clean/ahead 68 进入。跨历史目标仍同时包括 R11 正确 D7/不预测 D30、R16 已通过 M05、R4 M03/M04 分项，以及 R7—R21 错单位/版本/算术和正式独立 99% 误放；不能把一个模拟器边界修复记作整套价值校准。B 门 RED 是两个不同、均 `claim_evidence_bound` 的 finding 各请求定向修订时，原纯函数返回两个 `targeted_revision_claim_ids`，违反 Phase 6 最多一次定向修订的预算。结构化替代仍是现有 `publication_audit.v1` 归一化结果和纯宿主 `simulate_shadow_actions`：只接纳 finding 顺序中的首个有效请求，不做未来任务规划，`publication_effect=none`，无真实模型调用。将来退役的旧门仍是整篇散文因单条 binding 获权威；本切片**没有**退役任何正式检查器或改变回执/数值硬门。单测 RED 为该断言失败并展示返回两个 ID；修复后审计/处置两文件 20 passed。

并行只读核对 A 门：R11 完整批次 M02 `tmp/p08-real-provider-20260913-fe83160-r1/sessions/72b58ee16e69/analysis_state.json` 的 `goal` 明确要求 D1—D7 留存、判断 D30、区分已算结果与缺口；旧 `answer_requirements=[]`、`publication_packets=[]`。其 `curve_fitting` 回执 `tr_1536f8a2e4a5` 有 `x_col=day,y_col=retention` 及 `points[6].x=7,y=0.1`；当前 `extract_explicit_requirements` 对该复合句返回 `[]`，而对单一直接请求可产生候选。故上一切片的选择器只能核验结果身份，不足以把“用户问的 D7 留存”与该点闭合为 `answered`，也没有百分比单位证据。不能为 R11 新增拆句/同义词硬门、把 `analysis_spec` 模型指标标签升权或要求 Shadow 作总审批；依已裁决的无匹配保持 `unassessed`、原始尺度展示。若要让原始 VP/CP 的完整正确价值可由结构化核心保留，后续须先核对现有上游是否已有宿主可验证的子问题/单位契约；若没有，再向用户呈报范围和取舍，未经确认不改正式默认策略。

R16 完整批次 M05 的会话 `58da9082dc02` 还证明这不是 R11 单句特例：同会话先由用户要求订单记录数与 amount 总额，随后连续五次要求改写受众/风格并明确“不改变数字、范围、限制和证据等级”，末轮要求恢复技术表达。旧 `answer_requirements=[]`，末轮没有重新写指标名；若只看末轮词句或模型当前意图，正确的 12/120 和方法边界会在可信核心中失去关联。该路径应借既有 canonical history 与宿主可核验的继承关系评估，而不是新造多轮关键词门。三份原始计划分别要求正确可复算结果不因措辞丢失、不能靠关键词缩窄原请求、子问题与方法上下文有可信覆盖；当前只读证据表明这三者在 A 门尚未同时达成。

当前源码已核对所有者边界：`session.history.load_canonical_history` 提供消息字节、revision 和 SHA 身份，不解释子问题语义；`loop` 的 `update_requirement_lifecycle` 只保存 `extract_explicit_requirements` 的确定性结果，R11 复合句及 R16 首轮自然请求均未留下要求记录。旧归档早于当前 lifecycle 实现，不能据它单独断言当前多轮行为必败；但当前提取器对 R11 真实文本返回空已复现。`analysis_spec.metrics` 等模型字段仍只是线索。下一步若要补“事实结果 ↔ 用户子问题”的权威关系，应先定义由谁确认语义、如何在多轮继承和版本变化时撤销，再做当前 HEAD 的最小 RED；不可把 canonical history 的字节正确性误当语义覆盖已解决。

R11 的旧 `dataset_contract_detail.json` 还显示 `field_roles.metrics=[day,retention]`、`rate_metrics=[]`，`data_understanding.v1` 仅列出两列类型与七行，没有百分比单位定义；不能把列名 `retention` 或 0.1 的数值范围当作“10%”授权。此处需要的是上游可验证的指标/单位身份，不是发布时按名字或大小猜单位。旧归档只作缺口定位，不替代当前 HEAD 的 E3/E4。

## 14. 第八 A+B 离线切片：已有子问题记录的消息来源锚点

用户批准默认关闭的上游指标/单位身份契约原型，并特别要求测试设计服从真实分析场景，而不是为夹具造功能。从 `main@93b652e176ddb3ebc2752f17be8281a7b226ea3c` clean/ahead 70 进入。真实约束先于测试：R11 复合请求有 day=7/retention=0.1 回执，但旧 `answer_requirements=[]`、数据契约无百分比单位；R16 已通过 M05 的会话先问订单数与 amount 总额，再连续改写风格，旧 `answer_requirements=[]`；两者不能靠当前提取器、模型意图或末轮句式补成权威。已有 `session.history` 给消息内容/revision/SHA，`update_requirement_lifecycle` 给已识别要求的 `source_message_ref`/稳定 ID/生命周期；普通 Workspace metadata 可由工具写入，不是可信单位来源。

这一切片的校准面没有收缩为两条正例：R4 M03 的六源金额仍需同版本派生帧，旧自发 `answer_bindings.v1` 种子不含当前占位符和合法 fence；M04 的假设别名与真实 ID 不一致，消息锚点不修关系；R7—R21 的错单位、来源/版本和 CV 算术仍由原有回执/复算硬门约束；正式有效 binding 旁独立 99% 的误放仍待默认策略门。新锚点不应改变这些状态。本次没有把那些旧会话重新执行在当前 HEAD，不能把协议测试当作历史全矩阵通过。

本切片 RED：在现有 `answer_bindings.v1` 的离线目标选择器附上一条已持久化要求，并传 canonical history，三项测试均因函数没有该输入而失败。结构化替代物**不新建要求账本或发布通道**：在既有默认关闭 `validate_offline_target_selectors` 里，可选读取 `CanonicalHistorySnapshot`，重算完整消息 SHA/数量、核对 revision，核对最后用户消息与当前 packet 问题、唯一来源用户消息的 `msg_` 内容哈希、要求的稳定 ID/原文/active 状态，并要求 label 与同版本工具实际 y 列标识符完全同名。结果只增加 `request_anchor_status=verified_source_and_column`、`request_history_sha256` 与 `request_history_revision`；点值仍须逐项核对回执事实，`answer_coverage=unassessed`、`unit_status=not_confirmed`、`publication_effect=none`。这个锚点证明历史消息和列标识符，并**不**证明跨轮语义仍适用、聚合方式正确、中文别名相当于英文列，或数值可以换算百分比。

生产路径可行性也已只读复核：`AgentLoop.run_turn`/structured/stream 三个入口均先把同一 `user_input` 作为 user 消息加入 `self.messages`，`_prepare_analysis_turn` 再对该字符串计算 `msg_` 内容哈希；因此正例的消息锚点不是测试夹具凭空设计的另一个 ID 算法。但本次没有把 canonical history 传入正式发布，也没有证明旧会话能补出缺失的要求记录。

正式接线前还要让 history SHA/revision 与 publication packet 在同一原子快照中绑定，并定义后到用户消息、撤回或数据版本变化时如何失效；当前纯函数只校验传入的 canonical snapshot 自洽并把身份写入离线结果，不声称该 snapshot 是发布瞬间的最新历史。因此不能凭此结果直接放行 `answered`。

负例包括伪造/过期历史 SHA、外来历史、已撤回要求、R11 无要求记录却由模型补 ID、R16 首轮明确问订单数/amount 且末轮只改风格却仍无要求记录，以及把 `unit=percent` 随意写进 Workspace metadata；均不授予新权威。正例仅是已有宿主要求记录的同名列跨表达改写，可证明协议可行，**不是** R11/R16 真实旧会话通过。现行正式 parser 继续拒绝试验字段；普通 packet、AgentLoop、确认系统、用户可见发布、Shadow 和 Provider 路径不变。旧门将来退役的目标仍是一条 binding 给整篇自由散文授权；当前没有退役任何正式门，也没有把 `analysis_spec` 或模型 EvidenceRecord 升为真。

现有来源数据契约没有可验证的单位/尺度字段；confirmation 的 `metric_definition` 记录也未提供通用的“数据版本＋列＋单位/尺度”已确认结构。不能为了让正例变绿而发明上传侧元数据或把可写 Workspace metadata 当来源授权。下一步应把单位/业务决定的真实生产者、版本撤销和需要用户确认的条件单独设计并用实际正反流程校准；在此之前 R11 只可显示原始 0.1 与单位未确认，R16 的 12/120 仍是已投影原始结果而非完整方法/子问题等价保留。若完整 VP/CP 价值目标与这条证据门发生冲突，先与用户讨论；不追加中文拆句词表或 Shadow 总审批。

本切片定向三文件 **173 passed**；`tmp/tprb29` full-offline **2934 passed/1 skipped/16 warnings/0 failures**，但在 revision 和 R16 负例补入前启动，**不是最终代码收据**；`tmp/tprb30` 因测试文件增加真实多轮负例而主动停止，不计最终结果。源码与测试随后冻结，最终 fresh `tmp/tprb31` full-offline **2935 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2936/failures=0/errors=0/skipped=1`、SHA256 `12F55B0200DF5AA216CF1EC5FF67C44B0A2C138B5B2AFE00356F522A46D4B049`，runner `provider_calls=forbidden`、真实 Provider initiated 0。E3/E4、正式默认切换均未运行。

最终 fresh `tmp/tprb28` full-offline **2931 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2932/failures=0/errors=0/skipped=1`、SHA256 `72B8C65B0ACED19F647B5AE7C346CA47472E0AAE3F7D0C3A5FC35DE64FE8F289`，runner `provider_calls=forbidden`、真实 Provider initiated 0。本切片没有 E3/E4、旧会话回写或正式处置。

## 15. 第九 A+B 离线切片：版本＋列＋单位/尺度的上游契约（默认关闭）

用户明确同意默认关闭的上游契约切片，限定来源明确声明或用户已确认的映射，不能新增自动暂停、正式发布接线，也不能用为测试制造的正例声称真实会话可用。本切片从 `main@5f0480bc5f9d590ea80e0d74af2a29bbbbcc290e` clean/ahead 71 开始，继续以 VP/IC/CP 和 R7—R21、R11、R16、R4 M03/M04、独立 99% 为共同背景。直接历史负例：R11 M02 的真实 `data_understanding.v1` 只有 `day/retention` 类型和 7 行，`workspace_meta` 的原始及分析版本均无单位元数据；确认快照 `records={}`。R16 已通过 M05 的数据理解也只有列/类型，其确认快照同样 `records={}`。R4 中断批次和旧散文不能补出缺失的结构化用户决定。此阶段没有找到可核验的真实“列单位已由用户确认”正例，**单位升级的实际生产链仍未验证**。

RED：现有 `load_data.context` 和普通 `Workspace.set_metadata` 可写，列名、0.1 数值范围、`field_roles`、模型指标标签都不是单位/尺度权威；旧 bundle 缺 `dataset_version_id`，单做 schema 校验还可能接受手写的 `confirmed` 字段。定向测试初跑进一步暴露：旧 bundle 行数/列名相同而数据变更时无法识别过期；仅有形状校验不能认证确认事件。不能用这一表面 GREEN 宣称 R11 的 0.1 已是 10%。

结构化替代：在**既有** `data_understanding.v1` 的 dataset 项上，增加仅由显式 `offline_measurement_scope=True` 才生成的 `dataset_version_id/source_fingerprint` 锚点；默认 `_record_data_understanding_bundle` 调用保持原样。新的纯离线投影先核对当前帧实际 fingerprint、行列与原 bundle 身份，再从既有 `ConfirmationRecord` 中重建 `measurement_mappings`：只接受同 session、同版本、同列、已解决、有 response ID、可见选项的类型化 `host_measurement_mapping.v1` 决定；旧 bundle 无生成时版本锚点、泛化/未解决/过期/标签不匹配记录、冲突决定都不给单位。输入 bundle 自写映射即使形状合法也被重建清空。`scale` 只记录 `raw/fraction/percentage_points`，不做百分比换算，不授予 `answered`。本切片没有创建自动确认提问者；历史没有该 host 类型化决定，协议单测的正例只是形状校准，**不是**真实正例。

源文件路径目前支持 CSV/TSV/XLSX/JSON/JSONL，但现有 `load_data` 不读取可信的列单位声明；本切片不新造 sidecar/上传协议，也不把 Excel/列名启发式当作来源明确声明。因此“来源声明”分支尚未实现，应先找到真实输入规格或与用户讨论。确认记录来源标识本身也不是生产级认证；未来若要接正式路径，须由宿主生产者创建并从确认 store 完整事件链重验，而非接受任意外部构造的 `ConfirmationRecord`。没有这一步，投影只能用于离线协议校准。

提交后又做了范围明确的只读历史确认扫描：仅遍历 `tmp/p08-real-provider-*` 的 **15 个**运行目录下 `sessions/*/confirmations/snapshot.json`，得到 **51** 份快照、**8** 条记录、其中 **6** 条 `resolved`；按记录结构分类为 **3 条** `scope_confirmation/goal_choice` 与 **3 条** `metric_definition/metric_definition`，类型化 `host_measurement_mapping.v1` 为 **0**，这 6 条已解决记录的 `data_version` 均为空。该扫描不包含所有旧本地会话或其他命名的真实 Provider 目录，不能推断全仓库从未有过用户单位声明；但足以证明所扫的历史确认不是本切片的真实正例，也不能把旧 `metric_definition` 自动映射到列尺度。

旧门未退役：正式候选中有效 binding 旁独立无据 99% 仍可能误放；本切片没有修改 AgentLoop、发布默认、自动暂停、Shadow 调度或 claim 级处置。仍需分别验证 R11 正确原始尺度与具体缺口、R16 12/120 和方法上下文、R4 六源/假设关系，以及 R7—R21 的错单位/算术/版本。此次不能算 A 门完成，更不能进入 Phase 7。定向数据理解/确认/发布七文件 **302 passed**。`tmp/tprb32` 为生产者边界和畸形确认负例补入前的历史全绿，不是最终收据；`tmp/tprb33` 在约 9% 时因发现非字符串确认参数可能抛异常而主动停止，不计结果。**最终 fresh `tmp/tprb34`** full-offline **2949 passed、1 skipped、16 warnings、0 failures**（307.70s），JUnit `tests=2950/failures=0/errors=0/skipped=1`、SHA256 `5D3F003C4B54F46221B0227746CBFD24D6038643C22D34DB6E162CFFA01051E7`，runner `provider_calls=forbidden`、实际真实 Provider initiated 0。该收据仍仅 E2，不包含浏览器 E3、真实 Provider E4 或旧会话真实重放。
