# Phase 5—8：R11/R16/M03/M04 宿主事实边界与下一结构方案

基线 `main@954ff239f3c6f1bfd7304b975be041e4ebc24c46`、根工作树干净。用户在 [Shadow R1](2026-09-27-shadow-natural-m03-r1-evaluation.md) 的 1/4 关键命中及两次宿主引用误报后裁决：正式默认与旧散文门不变，Shadow 仅诊断；先盘点宿主事实，再做正反价值方案。本轮只读检查归档与代码，**0 次新 Provider 调用、没有产品代码变更**。旧会话不倒填当前 claim/确认。

## 同一事实的四层身份

`已上传/可见`、`工具已执行`、`当前 packet 可引用`、`已在审计输入且有宿主验证`须分开。旧自然正文与模型填的 EvidenceRecord 是待核候选；`answer_coverage=unassessed` 不能反推数值未核验，也不能反推用户子问题已回答。数据行数、观察日期、业务指标映射分别需要不同来源。

| 轨迹 | 实际可得的宿主事实 | 当前断层与禁止升级 |
| --- | --- | --- |
| **R11 M02** `tmp/p08-real-provider-20260913-fe83160-r1/sessions/72b58ee16e69` | `curve_fitting` 回执 `tr_1536f8a2e4a5` 含 `day/retention` 输入、7 个已执行点，D7 的 **原始值 0.1**；scope 的 `observed_x_range=[1,7]`、`extrapolation_allowed=false`。数据理解列出 7 行。 | `day` 是数值横轴，不是日历日期覆盖。历史 `publication_packets=0`、`answer_requirements=[]`、确认快照无记录；无“留存 ↔ retention”及 fraction→百分比的有效业务决定。可保留 D7 原始观察与 D30 无验证边界，不能把旧“10%”倒填为当前 `answered`，也不能生成 D30 数值。 |
| **R16 M05** `tmp/p08-real-provider-20260914-b833501-r1/sessions/58da9082dc02` | 原数据的 data-pool/理解记录 12 行、日期最小 09-01/最大 09-12；`transform_data` 回执 `tr_fb774270b1c9` 有 `group_aggregate`、`order_id count/size`、`amount sum/mean/min/max` 参数及源→派生版本/指纹/表达式；其 `rows=1` 是**聚合帧行数**。现行默认关闭 `_confirmed_group_aggregate` 可在同版本真实确认后复算 12/120。 | 旧终局 packet 只选两条 facts=0 的 `preview_data`，旧确认快照无记录；已通过的旧自然答案是价值保护正例，非当前 typed 通过。`12 原始行`、`1 聚合行`、`非空 ID count` 与 `去重订单数` 不可混用。最小/最大日期不证明逐日连续；`amount` 单位未确认。订单记录数的业务映射仅由现有同版本单次确认决定。 |
| **M03 六源**：旧 R4 `tmp/p08-glm-operator-20260922-r4/sessions/50e734df7af7`；当前自然 P/N 重渲染 | R4 `synthesize_time_series` 回执 `tr_3e70ccb10380` 的 scope 对每来源给 2 行、2 有效行、09-01—09-02、2 个不同日期，且有六源/派生版本；金额不在该回执数值 facts。当前 P/N 的默认关闭 packet 从当前帧身份、完整帧长度、预览结果 SHA 核对后生成每来源 10→11 至 60→66 与 `publication_scope` 的两期各 1 行。 | R4 终局 packet **未选综合回执**，不能借它证明旧最终回答。当前 Shadow 请求只含每来源 `period_a/period_b/diff` 三个事实，未送已生成的日期/行数 scope；原 `preview_data` 回执 scope 为空，审计视图没有独立复核 packet 派生 scope。`preview n` 不是全量行数；即使当前帧恰好 2 行，也不能自动宣称“全部上传记录”或跨来源可加/相互独立。缺失率与全量覆盖须各有宿主证明。 |
| **M04 v1→v2** `tmp/p08-glm-operator-20260922-r4/sessions/f2db8a75de3d` | 同计划/版本的 `analyze_time_series` 原回执及 detail 可核 v2 3 个时间点、`amount` 均值 10、标准差 0、斜率 0、方向 flat；现行 `receipt_verified_hypothesis_measurements` 对原 detail SHA、数据身份、指标/值/方向重验。v2 假设 artifact 有 4 个真实 ID，均 `inconclusive`。 | 旧 EvidenceRecord 把目标写成 `h_trend/h_level_shift` 别名，未匹配 v2 真 ID；模型自填测量与跨版本 v1 证据不能使 v2 `supported/refuted`。保留平坦观察和现有结构关系审计，关系解释按用户已定边界保持 `unassessed`；不增 claim 类型或从文本反推因果。 |

以上四份 `analysis_state.json` 的 SHA256（按 R11、R16、R4 M03、R4 M04 顺序）为 `9D1DA8F82C0CEDE4109B693A583AA24CFF85BB2CDB06DAF3B583C10150C24F66`、`7E78DBCBD1814C4D43742F08D4E165F037AB8964DC62576068A7CB0857D1948C`、`9F488D922093CB55EA27BF2884F18CC53532D5A25E492F973D43BF850FFA1B63`、`02373BAF288ABCECC4B070FE00767DF2A39F5C264884D2B83F32E97BAB2AEBBD`；M04 v2 假设 artifact 为 `75AE0627115CC85BD8B3219A151CBD5C83161281508337659659F39A8B441ECB`。这些是旧归档身份，不是当前运行通过凭据。

## 下一验收顺序与最小实现门

1. **先验 Phase 6.A 的用户价值，暂不改 Shadow。** 复用现有默认关闭 typed/分区、`publication_scope.v1`、packet/回执、原位 trace、确认 store，在同版本 R11/R16/M03/M04 正反样本逐项对照本表：事实、具体缺口、正确解释、方法、关系和产物各是否可见，独立无据句是否仍被明确标待核。旧真实会话只作 oracle，不回填新结构。若现有代码已能承载，就停止添加字段，直接记录 A 的剩余价值差距。
2. **仅对可复现的来源缺口做结构化替代。** 若 M03 等正例确需全帧行数/日期，优先复用已核的原回执 scope 或 packet 生成时的全帧身份；`preview n` 不能冒充全量。原回执已有 scope 的 R11 曲线、R4 综合和 M04 时间序列按 receipt ID、结果 SHA、版本及原字段核对。M03 `preview_data` 的 packet 派生 scope 须证明与生成时全帧身份/原回执及持久 packet 一致；事后无法独立复核时仍 `unassessed`。不另建“审计事实表”，不为当前两例补特例。
3. **Phase 5/C 输入修正放在 A 之后。** 现行 `publication_audit_input.v2` 已给模型宿主渲染文本和每来源三个数值 facts，却没有全帧行数/覆盖的可核来源；同时送入 `request_anchor/answer_coverage=unassessed`，模型在两例 finding 中明确把它误读成宿主数值未核验。A 的宿主事实范围通过正反门后，才评估在现有 `build_offline_audit_view/build_shadow_audit_request` 中受限复用，减少模型侧无用覆盖字段与重复摘要。要求覆盖状态仍留在宿主视图与 Phase 8 报告，绝不因删模型输入而变为 `answered`。这只是减少错误上下文的候选，不能保证修好 3 个语义漏检；需另获新冻结自然校准，不能接自动处置。
4. **拟退役边界。** 此切片可减少的是送给 Shadow 的冗余覆盖字段与重复摘要，**没有一个正式旧散文门获准退役**。只有某一门族同时通过正确解释/方法/产物保留、独立无据句局部限制和当前自然正反回放，才逐族删除该门及镜像测试。`_curve_interpretation_issues`、`_extrapolation_issues`、`_future_window_issues` 等仍处理未绑定正文；封闭的数值、单位、版本、算术与关系 ID 校验始终保留。不能用“待核”标签或末尾说明替代正文局部正确性。

## 预先固定的双向验收与停止条件

| 家族 | 必须保留 | 必须拒绝升级或局部标待核 |
| --- | --- | --- |
| R11/R7—R21 M02 | 同版本 D7 原始 0.1、观测范围及无验证 D30 的正确解释 | 未确认的 10% 尺度、D30 具体值、把横轴 1—7 当日历日期、错误 9.9% |
| R16/M05 | 经当前真实单次业务确认后的 12/120、聚合方法、未知单位、日期范围及多轮改写后的价值 | 未确认历史倒填、聚合帧 `rows=1` 当订单数、`count/size/nunique` 混用、最小最大日期当连续覆盖、过期版本 |
| M03/R4 与自然 P/N | 六个逐来源数值、正确两日算术/方法/单位限制、N 对 99%/七天/独立性的正确否定、图表/导出引用 | 独立 99%、共享原因或来源独立、任意 9/14 天硬阈值、“全部上传/无缺失”无来源证明、把两日观察方向与长期趋势混为一谈 |
| M04/R7—R21 | 当前 v2 flat 观察、真实假设 ID、已核验关系或明确 `inconclusive`，v1 审计可见但不升到 v2 | 旧别名、跨版本测量、模型自报支持/反驳、因果/显著性越权；未完成任务不吞独立可信观察 |

第一轮 RED 是现有默认关闭答案在四族中失去正确方法/产物，或把旧未确认单位、错误关系、预览截断、过期版本提升为可信事实；GREEN 只证明当前代码的宿主来源、可见价值和默认关闭路径。只有 A 的确切缺口需要 scope 改动时，再做“packet 有范围但输入缺失”“错误 receipt/ID 不得进范围”的第二轮 RED。本地 E2/Provider-disabled HTTP 或浏览器 E3 不替代自然语义准确率。若下一次**新冻结并单独授权**的自然 Shadow 仍漏掉预标高风险建议或误伤受保护解释，维持 advisory，不接 Phase 6.C 自动动作；不按词句追加补丁。Phase 6.A 的完整跨历史价值、Phase 6.D 正式默认、Phase 7 退役和 Phase 8/9 整体 E4 分别验收，不能由本方案记作退出。

本方案仍遵守 [VP](../superpowers/plans/2026-09-06-analysis-value-preservation-plan.md) 的有效分析与待验证解释保留、[IC](../superpowers/plans/2026-09-07-intent-clarification-plan.md) 的真实业务歧义一次确认、[CP](../superpowers/plans/2026-09-08-answer-content-optimization-plan.md) 的子问题/事实/图表完整性；没有修改三者的目标或总计划退出条件。
