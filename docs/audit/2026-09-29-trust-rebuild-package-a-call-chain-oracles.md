# 可信发布重建：工作包 A 调用链、旧门与独立 oracle

日期：2026-09-29。实施树 `codex/trust-rebuild-20260927@4bb7f85`；供体 `main@b181646` 只读。本记录是[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)的包 A 证据，不是新的执行计划。检查时重建树有在途 `AGENTS.md`、`hypotheses.py`/测试和审计文件；未重置或覆盖。下述调用链是**实施前基线快照**，对应该 HEAD 加当时已有的 M04 工作树 diff；M01/M06 后续变更和局部旧门退役另见[同日收据](2026-09-29-trust-rebuild-m01-m06-described-facts.md)。

## 1. 实际链路与分叉

| 阶段 | 实际入口和状态 | 判定权及需要保持的边界 |
| --- | --- | --- |
| 用户输入和会话 | Web `/api/upload` 生成文件名/SHA 票据；`/api/chat` 经 AgentManager 进入 `AgentLoop.run_turn_structured`/`stream_turn`。`loop.py` 的 `run_turn`/`_stream_turn_impl` 建立当前轮。 | 上传可见、执行过、进入 packet、可由宿主核验是四种身份；票据不等于已执行。 |
| 意图、范围、确认 | `loop.py` 的 `_maybe_auto_suspend_for_required_question`、`_runtime_confirmation_checkpoint`、`_resolve_runtime_confirmation`；`analysis_entry`/`question_need_detector`、确认 runtime 和有效决定状态共同决定是否暂停/恢复。 | 只有真实业务口径进入确认；skip、方法许可、模型自报不签发事实。M06 B 选择只定成本范围，不能补缺失成本数值。 |
| 工具与计划/关系 | `_process_tool_calls`、`_record_turn_tool_result` 登记原始回执与结果身份；`_verify_before_publication` 刷新计划/假设并验证；显式竞争假设由 `_competing_hypothesis_quality_gaps` 按当前 plan、当前版本和带回执关系核对。 | M04 真实 hypothesis ID、plan ID、metric、版本和摘要回执是闭合依据；候选关系或任务 completed 不是。质量门可要求结构，却不应抹去独立正确观察。 |
| packet 和需求 | `_prepare_publication_packet` 调 `build_publication_packet`，按本轮来源、事实组、scope、要求和 snapshot digest 建快照；晚到回执在 `_render_terminal_publication` 重建最终包。 | CP 的明确子问题逐项回答或具体缺口；不能凭关键词、末轮数字或相邻散文算覆盖。旧资料不可反向补当前确认。 |
| 两条终局 | `_render_terminal_publication` 先试 `build_m02_host_claims`、`build_aggregate_host_claims`、`build_comparison_host_claims`，仅在无前述宿主部分且有 `run_python` 来源时试 `build_basic_summary_host_claims`。命中后形成 `answer_bindings.v1`、原位渲染并可选审核；未命中则 `_render_finalized_publication` 解析模型 bindings，**先** `validate_final_narrative`，**后**原位渲染并可选审核。 | M02/M03 有宿主事实；M05 可走聚合；M01 首轮/M06 在没有可匹配 builder 时回到散文门。当前比较已有宿主 block 仍可能把正确行动候选扣作 `withheld_pending_semantic_binding`。有回执却无 claim 不能由审核代替事实验证。 |
| 审核、终态和持久化 | `_review_prepublication_candidate` 仅在 `DATA_AGENT_SEMANTIC_AUDIT_TRIAL=1` 启用。流式 `_stream_analysis_loop` 与同步 `_loop_impl` 同样经过分析质量、确认检查；`_persist_accepted_answer`/`_commit_publication_packet` 将 answer SHA、packet、artifact、消息保存后才公开终态。 | 审核只处置可定位的开放解释/条件行动，不能增加或否决已核宿主事实；保存失败不能给 completed。SSE 单终态、会话持久状态、导出和刷新各自验收。 |

这解释 `p08rb8` 的分叉：M01 正确比较数值受宿主保护，但正确开放片段被局部审核误伤、行动不闭合；M04 因回执实际推断列不在调用参数中而无法闭合当前描述关系；M06 成本确认完成后仍由散文写出含首尾“11 天”。M02 的回执 claim 已有宿主入口；M03 的多来源块可进入宿主入口；M05 的聚合可进入宿主入口。它们不自动证明相邻自由解释已安全。

## 2. 十类旧正文检查的处置

`publication_synthesis.validate_final_narrative_issues` 仍由 `_render_finalized_publication` 调用；`basic_summary` 宿主路径也用其对**整个**候选解释作一次拒绝判断。`validate_final_narrative` 是前者的错误汇总，不是另一套独立 oracle。下表说的是主链决策权；封闭的绑定身份、数字计算与工具标记保护仍保留。

| 当前检查函数 / code | 当前入口与问题 | 处置及独立依据 |
| --- | --- | --- |
| `_curve_interpretation_issues` / `unverified_curve_interpretation` | 在自由散文上猜零值/曲线解释，可误拒正确边界。 | **替换**为曲线回执的零值语义、范围和 typed claim；开放解释交局部审核。 |
| `_extrapolation_issues` / `extrapolated_time_point`、`unbound_time_point_claim` | D30 等词和数字从句反推是否预测；曾误拒合法 M02 边界。 | **替换**为曲线回执重算、确认和观测窗 claim；无授权未来点保持 unknown。 |
| `_significance_issues` / `significance_without_test`、`significance_unbound` | 从措辞识别显著性，既依赖词面也可能漏同义强断言。 | **替换**为推断检验回执的检验类型/目标/结果 claim；其余强断言局部审核。 |
| `_currency_unit_issues` / `unconfirmed_currency_unit` | 对正文货币词判定单位。 | **替换**为单位确认和来源列元数据；未知单位不得由模型散文授予。 |
| `_future_window_issues` / `incorrect_future_window_label` | 词面识别未来窗口，不能可靠处理 M01 当前/下一七日。 | **替换**为结构化起止日、窗口身份和 action 条件绑定。 |
| `_period_label_issues` / `unsupported_yoy_label` | 只对某些同比词面召回，已列为 revision-only。 | **退役其发布决定权**；跨年/期间关系从同范围回执产生；开放解释审核。 |
| `_arithmetic_issues` / `arithmetic_mismatch`、`coefficient_variation_denominator_mismatch` | 在整段散文匹配算式，可把日期/引文混入。 | **替换**为绑定操作数与宿主运算；M06 日期含首尾天数尤其不得补日期正则。 |
| `_unsupported_data_semantics_issues` / `unsupported_data_origin_inference` | 来源性质词面召回，目前 revision-only，既误拒也漏无据变体。 | **退役其发布决定权**；来源分类需显式已核 claim，开放来源解释交局部审核。 |
| `_missing_value_zero_issues` / `missing_value_coerced_to_zero` | 从否定、代词猜缺失成本是否归零。 | **替换**为来源值的 missing/zero 分离及算式操作数闭合；M06 选口径不构成值。 |
| `_binding_numeric_issues` / `derived_display_mismatch`、`scenario_label_missing` | 已有绑定时仍从 placeholder 散文提数字和情景标签。 | **保留封闭派生值核对，改为宿主渲染**；移除对任意自然句尾数字与情景词的许可作用。 |

另需**保留** `empty_final`、`unexecuted_tool_markup`、`parse_answer_bindings` 的 schema/digest/引用身份校验、回执版本/确认/作用域校验、`render_bound_claims_with_trace` 的原位可追溯性、保存与 SSE 单终态检查。`render_verified_partial_answer` 是耗尽修订后的局部保留路径；统一终局后应与各 host builder 的局部缺口合并，不能让整篇旧门失败吞独立正确值。`drop_revision_only_issues` 随相应散文门退役后删除。当前未证明任一十类函数已无调用；不得直接批量删除。

## 3. VP/IC/CP 到 M01—M06 的独立正反 oracle

| 场景 | 正向必须交付 | 相邻负例和所有权 |
| --- | --- | --- |
| M01 | VP 当前 `F-SALES` 2026-09-01—12 含首尾 12 日、12 行、`amount` 合计 120、单位未知；`F-ACTION` 两段同口径 7 日 700/770、成本 140/175、净贡献 560/595、订单 70/77。CP 保留不同受众的正确解释，以及“下一七日且双条件才考虑受控试验，否则暂停复核”的可逆建议。 | 不能把 12 日 120 直接当下一周阈值、把未来条件代入当前、把“且”变“或”、自加停止线或来源/因果；正确值不得随行动审核失败丢失。 |
| M02 | VP 真实 D7 观测、已核拟合和范围；IC Q13 直接交付 D30 缺观测/无预测授权。若比例单位未经确认保留原值 0.1；真实 fraction 确认后才宿主显示 10%。 | 无数据的 D30 数字、同词合法拒答的误拒、未确认 0.1 被改写为 10% 都失败。 |
| M03 | VP/CP 六来源每源独立 day1=`10n`、day2=`11n`、差值/行数、图表与导出；规范历史和压缩后仍可恢复。 | 漏源、混源、默认求跨源总量、只凭 preview n 推断全上传覆盖或相邻自由散文升级为事实均失败。 |
| M04 | VP/IC Q14 当前 plan 真实 ID 的至少两竞争假设；v1 当前工具回执可核的描述性支持/反证，v2 加载后旧关系 stale、当前平坦值 10/10/10 与未决边界；内部路线不弹方法审批。 | 错 metric、模型 `trend_slope` 替代 `amount`、旧版/旧 plan、因果或显著性提议不能升级。当前 `inferred_columns.value_col` 只有与摘要回执、版本、目标一致才签发描述性方向。 |
| M05 | CP/VP 源 6 行与派生 3 行分开；A/B/C `sum=20/5/null`、`count=2/2/0`、`size=3/2/1`、`nunique=2/1/0`；零分母和缺值分别表达。 | 不能把 null 当 0、源行数当派生行数、未知单位当货币、局部失败吞其它组。 |
| M06 | IC Q04/Q10/R07 成本定义只确认一次，选 B 后同会话恢复；有独立 `F-SALES` 回执时显示 12 笔/120、2026-09-01—12 含首尾 12 日，成本/增量未算各列具体缺口；有已核促销列时仅券 96、双成本 86 只按所选口径重算。 | 选项 B 不提供成本金额；“11 天”、缺失成本归零、跳过授权、跨窗口借旧值、自报因果或把缺失数据写成已完成均失败。 |

横向出口：CP AC01—07/16—29/36—40 要求终局快照、逐问题覆盖、封闭算术、局部保留、SSE/持久化/导出一致；IC R01—R10/S01—S06 要求确认范围/版本与一次恢复；VP P08 的图、方法、关系和正确解释不能因旧门误拒丢失。每个 oracle 用冻结输入与独立预期评估，不从候选答案抽末轮数字子串决定通过。HTTP 路线的 picker、视觉和刷新单列 `unassessed`。

## 4. 包 A 结论与下一切片

包 A 已确认决定权重复点：`_render_terminal_publication` 的宿主分流与 `_render_finalized_publication` 的整篇散文门；`build_*_host_claims` 的多 builder 顺序；`render_verified_partial_answer` 与 host 分支局部缺口；试验审核对无绑定开放片段的单独处置。包 B/C 应把选择、绑定、局部缺口、原位渲染与审核排成一次终局流程，在**原** `answer_bindings.v1` 内先补 M01/M06 封闭事实，再逐族撤旧门决定权。M04 在途代码先做 Provider 禁用正常 app 的实际推断列、错指标和旧版正反收据；E2 全绿不能替代它。
