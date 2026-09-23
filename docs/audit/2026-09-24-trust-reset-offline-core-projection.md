# A+B 离线准备：范围边界与同 packet 产物/假设投影

日期：2026-09-24。进入 HEAD：`main@39246fc6da3e71cdcafdb6699c97ab7fe221d090`。用户批准 A+B 离线准备后，又选择 **图表与假设关系先做默认关闭的同 packet 离线投影**；C Shadow 调度、D 正式处置和真实 Provider 均未授权。本文件是实施与未闭合清单，不把 E2 结果改写为 E3/E4。

## 历史背景与 RED

以双轨校准的正反集合为背景，而非只看中断 R4：R11 正确 D7/不预测 D30，R4 M03 六来源及图表、M04 竞争假设版本重判、R16 **已通过** M05 的 12/120/时间/未知量纲，以及有效绑定旁独立无据 99%。R7—R21 的版本、单位、CV 算术、同比例、任务权威与确认轨迹仍是回归约束。AC17 的“缺少分母”在既有夹具中未被宿主证明，不能算正确缺口 oracle。

本切片新增 RED：`render_trusted_core_preview` 在没有 typed 块时对 R11 观测范围与 R16 回执窗口/行数/未知单位输出空串（两用例失败）；离线 packet 选项缺失使图表/假设四个测试失败。结构化替代物只读既有 `publication_scope`，以及显式离线选项投影到**同一** `publication packet` 并参与 digest。既有正式构包路径不传该选项，离线 packet 被 `publication_packet_prompt` 拒绝，不能暗中调模型。旧门的退役目标仍是“一条有效绑定就整篇散文有事实权威”及从自然语言猜日期/单位/预测；本切片没有退役或切换正式门，回执、版本、数值硬门保留。

## 已实现的有限权威

1. 范围预览只接受与当前 source 的 receipt ID、工具名同时匹配的 `publication_scope`。有限观测 x 范围、有效 ISO 日期窗口、非负行数、单位未确认可原位显示；曲线回执仅说明观测外情景**未经验证、不作为预测**，不产生 D30 值。`inference_performed=False` 对 `run_python` 只写“该回执未证实统计推断”，不推断脚本完全未做统计检验。工具名是执行机制，不冒充分析方法结论。事实组仍是原始上下文，不授予 `answered`。
2. `build_publication_packet(..., offline_trust_projection=True)` 是默认关闭的纯离线选择，未接入 AgentLoop。图表须有本轮所选 `create_chart` 成功回执、同会话注册清单和实际 HTML，路径锁在本会话 charts 目录；投影带文件 SHA256，状态只能是 `artifact_only`。预览可显示现有 `[[chart:...]]` 引用，但明言它不证明图中业务结论。外会话、缺文件、未选回执不得进入。
3. 假设集须属于当前 plan，JSON artifact 限在本会话 tool_outputs，内容 ID/plan/dataset 与持久化 ref 相符且有哈希；EvidenceRecord 的所有回执和结果/数据身份要属于同 packet。更关键：**模型填的 `delta`、`method`、`p_value` 不作为权威。** 目前仅 `compare_periods` 的同指标 A/B/diff/窗口通过现有 `_comparison_binding_values` 宿主复算，且 `delta` 与其相等，才允许 `update_hypotheses_from_evidence` 给描述性关系支持/反驳。传给关系校验的 measurement 只保留复算指标/差额，method 固定为描述性工具；伪造因果方法或显著性 p 值不得升级。其他工具的关系保持未决，仍作为审计结构而非业务结论。

## 测试与剩余问题

定向发布/比较/假设/多来源等 **217 passed**。范围切片 `tmp/tprb18` **2909 passed、1 skipped、16 warnings**，JUnit `tests=2910/failures=0/errors=0/skipped=1`、SHA256 `F95412FFFF266FA6835F56BBE0BCC755EDEBD30D9A6EC216AAFB473DF5A21AA3`；随后增加默认关闭的投影。`tmp/tprb19` 全量离线 **2913 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2914/failures=0/errors=0/skipped=1`、SHA256 `3C4812DF580B04D638FB47D6CC46E16823EEBA2B9FFE5DB5D3E5B700C76C5FF3`；执行后又加上“无显式本轮 receipt IDs 则不投影”，故它也不是最终代码收据。**最终 fresh `tmp/tprb20`** 为 **2913 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2914/failures=0/errors=0/skipped=1`、SHA256 `1506832913636E32A2569E7C54D46149C60B806D7865F70100704DFE3025AA18`；runner `provider_calls=forbidden`，真实 Provider initiated calls=0。没有浏览器 E3、真实 E4、push 或部署。

本阶段改善了 R11/R16 的回执边界和 M03 图表**存在性**，以及 M04 在闭合比较回执下的假设关系审计；它仍**没有**证明旧 R4 M03 的六来源业务结论、M04 的 run_python/其他方法关系、R16 方法表与正确自然解释可从当前 packet 全量重建。旧会话/旧 artifact 若缺当前 plan/回执/决策规则，会被排除而非凭旧正文补齐。A 价值保留门与 B 真实审计处置门未完成；C/D 均独立，正式发布仍可能放行有效 binding 旁独立 99%，因此不得默认切可信核心、也不得称 Phase 6 已上线。下一步应对历史正反集合做离线输出对照，量化保留/漏检；若想把旧解释无证据地升级为事实，必须先与用户讨论目标取舍。
