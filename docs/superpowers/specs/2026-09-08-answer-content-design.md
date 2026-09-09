# 回复内容完整性：开发设计

日期：2026-09-08｜版本：v0.3｜状态：CP1—CP5 设计已在独立优化分支落地；本地验收完成，真实 Provider 效果验证待 AC40 授权。

关联：[计划](../plans/2026-09-08-answer-content-optimization-plan.md)｜[验收](../validation/2026-09-08-answer-content-acceptance.md)｜[表达规范](2026-09-08-answer-presentation-contract.md)｜[实施记录](../../audit/2026-09-08-answer-content-implementation-record.md)。本文定义的发布绑定、FactGroup/detail_ref、需求生命周期、`answer-bindings.v1`、类型化派生量值和桌面端图文绑定已实现；自由文本中无法确定性定位的语义仍按设计标为 `unassessed`，不伪装为已证明。

## 1. 现有接口与设计边界

继续使用 AgentLoop、AnalysisSessionState、现有计划与 EvidenceRecord、结果详情文件、verification_reports、publication_packets、Flask/SSE 和 report。新逻辑以纯函数/现有字段的可选扩展实现，不增加第二套 planner、数据库或 LLM 审核服务。

| 已核对接口 | 问题/本次职责 |
|---|---|
| loop._maybe_inject_wrap_up / _prepare_publication_packet | 预览构建现在有持久化/注册收据副作用；分离预览与最终发布 |
| loop._render_terminal_publication / _render_finalized_publication | ready 包被复用；同步与流式终局统一新鲜度与正文检查 |
| loop._verify_before_publication | 已刷新证据/假设，但不等于发布包刷新；在快照之前完成 |
| AnalysisSessionState.add_publication_packet | 同 id 覆写，最多 20 包；最终身份必须内容寻址、避免预览挤占历史 |
| publication_synthesis.extract_publication_facts | 默认先裁到 10，业务结果被元数据挤占；改为类型化事实组与详情引用 |
| context.turn_receipt_ids / user_quality_requirements | 复用本轮来源和明确用户要求，不从确认响应文本重建全部业务需求 |
| tools.analysis_flow.record_analysis_plan / record_evidence_record | 复用输入 schema 与持久化；新增可选字段必须贯通所有入口 |
| tools.registry.ToolResult.data / tools.evidence_input | 结构化量值与来源绑定的适配边界，模型提出的字段仍需宿主验证 |
| prompts / synthesis_policy | 同一深度判定驱动两处，不再保留相互矛盾的固定模板 |
| app.js renderMarkdown / supplementalArtifacts、tools.report | 正文、图表、导出与来源说明绑定同一发布版本 |

## 2. 发布生命周期（CP1）

### 2.1 流程与状态

`工具结果可靠落盘 → 更新收据/证据 → 可选预览 → 候选回答 → 终局验证刷新 → 最终快照 → 正文检查 → 持久化发布绑定 → 发出最终文本与终态`。

预览只用于收敛提示，可缓存但必须带 preview 属性；不能作为最终收据注册给用户。终局无条件从当前状态重新构建快照，第一期优先采用“重新构建”而非复杂的增量缓存；未来优化必须保持同样语义。

复用现有本轮状态/互斥机制，在“最终快照—最终提交”间不再执行工具或接受同一轮状态变更。终局前按既有语义允许补充步骤，进入终局后只使用已计算结果；数据版本、证据或用户输入在提交前改变时取消旧候选并重新归属新轮，不能继续发布旧答案。不得自行新增后台补算。

候选问题沿用一次 publication recovery：汇总 coverage/numeric/scope 问题一次提交修订，不能各检查器分别重试。无剩余额度时保留独立验证结果并具体说明未完成项；只有能确定定位、且能重建语义完整的结果块才能局部替换。否则不做盲目删句，输出明确部分结果或既有失败终态。

### 2.2 快照身份

拟在现有 packet 中增加 `content_revision`、`snapshot_digest`、`phase`（preview/final）、`answer_sha256` 与可选 `supersedes_packet_id`；`schema_version` 使用新版本读取分支，旧 v1 不回写。

`snapshot_digest` 对规范化 JSON 计算 SHA-256，至少包括：session/turn、有效 plan/scope、完整需求版本、可发布来源的 id+result hash+structured result hash+执行状态、dataset/version/fingerprint、证据正文及 measurements/limitations/验证状态、相关验证报告、事实选择/省略清单、提取器与策略版本。排序规则确定；排除生成时间、artifact id、自身 digest 等非语义或递归字段。

相同收据 id 但数值/限制/版本发生变化，digest 必须变化；数据版本相同但验证由 pass 变 fail 也必须变化。`packet.id` 基于此快照生成，`answer_sha256` 在正文冻结后附加，不参与造成自引用的 hash。新正文修订另用发布绑定 revision，不能覆盖历史答案关联。

最终包、正文、来源说明 artifact、导出保存同一 `packet_id + snapshot_digest + answer_sha256` 绑定；重复回调只幂等复用同一发布，不增添重复来源说明。先完成宿主持久化，再发最终 delta/turn_end。若文件写失败，不以完整成功终态承诺来源说明已落地。

SSE 保留当前过程事件与进度；最终候选不在校验前以正式答案向用户暴露。核查当前流式缓冲机制并复用它，不扩大阻断到无数据普通对话。断流后以持久化绑定恢复，不能通过重新生成正文制造第二份答案。

## 3. 事实组与受控恢复（CP2）

### 3.1 事实组结构

现有收据身份和详情文件不变。拟新增业务事实组：

```json
{
  "group_id": "g_receipt_hash_path",
  "kind": "comparison",
  "receipt_id": "tr_example",
  "source_path": "metrics.retention",
  "scope_ref": "existing_scope_ref",
  "requirement_refs": ["rq_1"],
  "fields": [{"key": "d7", "value": "0.051", "unit": "ratio", "display_precision": 3}],
  "limitations": ["descriptive_only"],
  "detail_ref": {"path": "tool_outputs/example.json", "sha256": "...", "pointer": "/metrics/retention"},
  "evidence_status": "unassessed"
}
```

数值使用十进制字符串或等价的精确类型序列化；unit 不可推断为货币。group_id 由来源内容与稳定路径生成。示例仅展示结构，不是可用于真实发布的证据。

最小完整组：分组名＋指标＋数值＋分母/单位/窗口；比较对象＋前后值＋同口径差值；拟合族＋公式参数＋观测范围＋误差；敏感性口径＋结果差异＋局限。可共享的范围指向同一受控 scope，不机械复制到每格。

### 3.2 提取顺序与工具适配

1. 先保存完整 ToolResult.data 和摘要及内容哈希。受控读取器只解析本会话已计算结果，不执行其中指令。
2. 适配 curve_fitting：候选族比较、最优参数、真实/拟合点、误差、有效 n、零值政策与未知语义分开；不再只挑 fits[0]。
3. 适配 compare_periods、分组/Top N：对象、数值、单位、分母、窗口绑定。全量候选按原始序号/业务排序键稳定排序，不能按字符串路径把 10 排在 2 前。
4. 适配 run_python：优先使用宿主可验证的结构化 result/measurements；replay/code/hash/risk 信息留审计层。自由 stdout 按完整段落/表格分页保留，不能用正则猜业务语义后自动标 verified。末尾结果必须可恢复，缺结构时为 unassessed。
5. 通用 fallback 保留非执行元数据的完整组与详情引用，记录 extraction_status；不能返回空列表并宣称没有业务发现。

不要求一次重写全部分析工具。第一批覆盖诊断相关工具，其他工具走透明 fallback；若扩展 record_evidence_record 的 measurements 输入，须同时更新工具 schema、解析验证、历史反序列化和测试。不要只改提示要求模型输出不存在的字段。

### 3.3 选择与预算

抽取层不先按全局 10 字段破坏候选。详情层保存全量；prompt 层按“必答/必要口径 → 会改变解释的已计算对照 → 可选背景”选择完整组。支持完整请求时，相关范围内全量来源及组进入详情清单，正文如何展开由表达规范决定。

保留已有安全资源界限。新增预算以序列化 token/字符成本核算，并在 CP0 测量后确定常量；不宣称固定 80 facts 一定满足上下文。单组过大时分页整行/完整对象，不能截断数字、分母或限制。扫描上限到达要记录 `scan_incomplete` 与未扫描数量/未知数量，不能冒充扫描全量。

拟新增 `omitted_groups`，包含 group/source id、数量、原因（budget/optional/superseded/invalid/unavailable）、detail_ref、是否影响必答项；来源省略沿用 omitted_refs。selected、omitted、unavailable 应覆盖候选全集，不能把 superseded 旧事实当新发现补字数。

读取路径须复用现有 file_ops 的会话隔离与边界校验；核对哈希/版本再恢复。文件缺失、hash 不符、越界、序列化错误分别记录；不自动回退跨会话路径，不重算原始数据掩盖失败。micro_compact 保持先保存再压缩，补充保留必答事实/详情引用，不能将保存了文件等同于模型已读到内容。

## 4. 需求覆盖（CP3）

### 4.1 需求来源与持久化

复用当前计划/step id 和已提取用户质量要求。可选增加 `requirement_refs`：`id, original_text, source_message_ref, priority, scope_ref, requested_output`。显式编号清单可以确定性保留；自然语言由现有规划调用提出映射，不新增语义审核调用。宿主不得把未理解的句子静默删掉，解析不确定记录 unresolved。复杂语义仍须人工验收，不能号称全自动分解正确。

当前用户修正优先于旧要求；恢复确认时关联原始请求，不能把“同意”当成任务全文。压缩保留完整需求引用及修订关系；已解决/撤回项不再计入必答分母。未知或多义需求按既有必要澄清规则处理，不新增通用格式审批。

### 4.2 三种覆盖不能混用

| 字段（拟新增逻辑） | 语义 |
|---|---|
| evidence_coverage | 对该需求是否有同范围、有效且可用的结果/证据 |
| context_coverage | 相关事实是否已送入最后综合上下文，或只保留文件引用 |
| answer_coverage | 最终正文是否实际包含对应结果，或明确且具体的缺口 |

保留旧关键词 coverage 仅作为检索信号；不能驱动完成状态。模型提出的 requirement→block/fact 映射属于候选，宿主检查原句、来源、字段值、版本和最终正文定位后再接受。

答案状态采用 `answered / evidence_insufficient / not_computed / unresolved`，另有 `coverage_check = checked / unassessed / invalid`。前三种都要求正文中有结果或具体原因；unresolved 不能计入已覆盖。证据缺失与时间/预算未算不同，禁止统一包装成“数据不足”。

第一期可确定性核验表格/事实块：稳定 block id、实际渲染内容 hash、对应 facts/requirements。自由 Markdown 用定位和候选映射辅助核验；仅字符串出现不足以判定语义正确，无法确定时 unassessed。最终回答不必为契约改成僵硬五段模板。

正文缺必答结果但证据已存在时，在同一修订机会中要求补入对应事实；可以用宿主已验证数据生成完整表格补足数值答案，但不能自动生成未验证业务解释。状态表在审计详情而不在正文时，不算回答覆盖。

### 4.3 候选映射的传输与解析

CP3 第一版采用同一综合响应末尾的专用 `answer-bindings` JSON代码块承载可选映射，不新增工具调用或要求Provider支持新的response_format。拟定字段为 `schema_version, packet_digest, blocks`，每块包含 `exact_text, requirement_refs, fact_refs, derived_refs`；exact_text必须对应本次候选Markdown的实际连续片段。模型填的status/verified字段不接受。

宿主在正式Markdown渲染、普通工具标记检测与候选持久化发布之前，解析并移出这段内部块：要求只出现一次、JSON/schema有效、体积受既有响应预算限制、引用属于宿主提供的当前快照、片段存在且可唯一定位。含重复片段无法唯一确定位置时标unassessed，不猜偏移。模型回显旧digest不能证明快照新鲜，必须与终局重建结果比较。

内部块保存在既有候选审计/最终packet的可选字段中，正式content只保存移除后的Markdown；不得通过SSE、刷新、单条导出或复制回答泄漏。不能对用户消息/工具数据中的同名块执行这套控制协议，它们仍是引用数据。

没有内部块的旧模型回复沿用兼容路径，结构化表格仍可由宿主做精确匹配，自由文本为unassessed；不能把“缺元数据”直接等同于“所有内容错误”。格式损坏与已知数值/需求错误合并使用既有一次修订。CP3必须同步添加提示说明、受限解析器、宿主校验、状态读写、SSE缓冲及导出不泄漏测试，禁止只加提示而无接收实现。

## 5. 数值与单位校验（CP4）

### 5.1 检查范围

在现有 measurements/来源引用之上，拟增加可选 `derived_measurements`：`id, operation, operand_refs, result, unit, scale, rounding, scope_ref`。可支持 sum、difference、product、ratio、percent_change、percentage_point_change；明确除零、缺失、负基数语义。不接受 eval/任意 Python 表达式。运算输入只允许同范围的有效测量或明确标注的情景假设，假设结果不得升级为观察事实。

正文数字绑定 fact/derived id 与精确 span/块；模型可建议绑定但不能自报校验通过。宿主重算派生值并核验显示值的单位、百分比/小数、千/万缩放与舍入误差。容差依显示精度计算，不使用能掩盖 10 倍错误的宽泛相对阈值。

例：22400 × 0.051 = 1142.4，人数字段显示“约1142人”可通过，“约1.14万人”失败；0.00277 的比例差为 0.277 个百分点，不能写成 0.277% 的相对提升。旧零值政策 exclude 与语义 unknown 必须并存，不能由运算检查推出“未到期”。

### 5.2 判定与恢复

- 明确绑定且错误：invalid，稳定错误码、位置、输入引用、期望单位/值，阻止该错误进入正式答案；并保留其他独立可信块。
- 未绑定自然语言数字：unassessed，不能在审计中计为 verified；对作为核心结论的新派生数值，要求同一修订补绑定/去掉未验证推算并明确限制。日期、编号、版本号、用户输入原文引用不是自动算术目标。
- 数据范围或币种不一致：先处理 scope/unit 冲突，不能只让算式凑对。运算正确不等于统计/因果正确。
- 非核心、无法确定语义的文本：如实记录未覆盖的检查能力，不普遍阻断整篇。验收须人工检查样本全部核心数值，不用“未绑定”规避已知错误。

## 6. 兼容、持久化与故障

新 optional 字段必须贯通工具 schema→接收→state→save/load→Workbench/导出。旧记录没有字段时为 legacy/unassessed，不批量迁移、不重写旧 final 文本；新轮引用旧结果须重新检查当前范围与详情可恢复性。

现有 publication_packets 上限 20 保留，但正式答案所引用的包必须有独立受控 artifact/绑定可恢复；不能删除仍有正文引用的唯一证据包。CP0 先核对现有报告注册持久化路径，再选择保留绑定所需最小扩展，不创建第二个证据库。

故障不得被宽泛 except 包装成完整成功。详情不可恢复→该事实 unavailable；核心快照构建失败→不能发布“已完整验证”的答案；已验证独立结果可以部分发布并说明缺口。持久化失败→终态为明确失败/可恢复未完成，不能悄悄丢失审计后宣布成功。普通无分析对话不强制要求 packet。

回退优先撤回具体阶段补丁，保留历史记录和未知字段读取能力。已保存新格式的 reader/最小绑定不能先于依赖它的 writer/投影撤回。发布与执行安全门不能通过 feature flag 默认关闭来回退。

## 7. 可观测性与性能

记录 packet digest、来源/事实组数量、必答/缺口/未评估计数、压缩与读取字节、numerical checked/invalid/unassessed 数、问题码与修订消耗、final artifact id。日志不输出完整业务数据、密钥或用户所有原始文件。

CP0 在固定合成小/中/大结果集记录候选规模、构建耗时和最终 prompt 大小；CP2/CP6 使用同一 fixture 比较。正常路径新增 Provider 调用必须为 0；最终 prompt 不得超过既有上下文预算，大结果必须走分页详情。出现二次完整复制/无界扫描需先修复再验收。

以上设计不能保证“所有自由文本都可被确定性证明”；能证明的是绑定量值、来源版本、结构化必答项及受控渲染的一致性，其他部分通过明确状态与独立内容评审补足。
