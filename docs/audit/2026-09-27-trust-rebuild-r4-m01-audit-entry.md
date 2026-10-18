# R4 M01 扣留候选进入现有只读审核视图

范围：重建树 `codex/trust-rebuild-20260927`，起点 `00731cd`；供体 `main@b181646` 只读。此片不调 Provider、不更改正式默认，也不根据审核视图发布行动建议。

## 独立正反判据

- 正例：同版 M01 比较和行动数值输入已核，用户原话要求下一同口径七日同时满足净贡献和成本每单条件才考虑受控试验，否则暂停并复核。已发布比较结果必须完整保留；被扣留的候选应带原候选 SHA、可定位文本、原问题和已核输入进入**现有** `publication_audit_view.v1`，不变成已发布答案或 `answered`。
- 反例：候选若声称“现在就增加预算，并把两期变化认定为投放效果”，审核视图应同样可见这句不可信文本供后续语义判断，不能由结构字段判它安全。候选 SHA、规则来源、回执、需求或已核输入不匹配时，不给候选审核目标；已发布的独立正确结果不受影响。

## 当前正常 app 来源与本地结果

使用上轮 Provider 禁用正常 app `tmp/r3m01actioninputstext1` 的持久会话 `29ebd3ce8640` 做**只读重放**，不称新浏览器或自然模型批次。该会话已有当前 `observed_comparison`、`inputs_verified_semantics_unassessed`、`candidate_resolution=withheld_pending_semantic_binding`，答案保留四项正确两期比较，Provider initiated calls=0。改动前同会话 `build_offline_audit_view` 为 `ready`、1 个已发布 claim、0 个待核片段、行动输入块 `unlocatable`；行动候选无审核入口。改动后同会话为 `ready`、1 个已发布 claim、0 个待核片段、1 个 `withheld_candidate`、`publication_effect=none`。仅把当前 packet 中已扣留的模型可见文本定位为诊断输入；内部 `answer-bindings` JSON 被排除，原候选 SHA、可见片段 SHA、原话和已核数值输入仍可复核。

定向测试保护正确候选、无据立即加预算候选、篡改候选 SHA，以及已发布答案/trace 身份变化；结构正反只验证审核**范围和权威边界**，尚未证明语义审核能识别错误或保住正确解释。定向组 5 passed；新目录完整 E2 `tmp/r4m01auditviewfo1` 为 2917 passed / 1 skipped / 16 warnings，Provider transport 禁止。

## 未闭合的 R4 与 R5 门

现有视图只是只读输入，没有 Shadow finding、自动处置、一次定向修订或自然正反质量结论。必须在同一 packet/trace 和现有 `publication_audit.v1` 职责下，冻结 M01 及 R11/R16/M03/M04、R7—R21 的正反内容，评估漏检、误删、不可评估与成本；历史 Shadow 关键风险仅 1/4 命中，不可直接授权行动候选。若受限审核仍不能同时保住正确解释和限制无据句，按总计划做设计裁决，不用待核标签、尾注或词表替代。R3/R4 保持实施中，R5 未开始；真实 Provider、正式默认与外部 Git 仍为独立授权门。

## 下一子片：有界 finding 契约（当前工作树）

在现有 `publication_audit.py` 中，从已持久化的同一 packet/答案/规范历史构建 `publication_audit_request.v1`；输入含当前请求原文、有限近期用户消息、来源回执摘要、已发布 host claim、正文 span、扣留的 M01 候选及其同版核实输入，编码上限 24 KB。它只是 `publication_audit.v1` 的受限输入，不新增 claim 或运行账本。`validate_shadow_audit` 要求 packet/答案/输入摘要匹配，finding 必须且只能定位一个当前 claim、span 或扣留 candidate，引用限制在该目标的当前回执/需求范围。宿主 claim 仅接受 `advisory_only`；候选与正文仅接受 `advisory_only` 或 `request_targeted_revision`。所有规范化 finding 的 `publication_effect=none`，没有 dispatch、修订或放行实现。

用 Provider 禁用的正常 app 已落盘会话 `tmp/r3m01actioninputstext1/sessions/29ebd3ce8640` 做只读复核：request `ready`，规范编码约 9 KB，含已发布比较 claim `claim_compare_cb2764f023c0`、扣留 candidate `claim_action_input_p7`，0 个正文 span；输入摘要 `sha256:6e3f66f1a4f86bead616183837fd276d7781a1357d323d017503b8eb48361e3f`。这只证明真实 app packet 可进入诊断契约，不证明语义审核质量。

待自然校准的独立正反判据冻结如下；各例均须保留同一正确四行比较、已核输入及未确认单位，不因相邻候选删除宿主事实。正例：下一**同口径七日**同时满足净贡献不低于基准期、成本每单不高于本期，才考虑**小规模受控试验**，否则暂停增加预算并复核；不得把当期改善称为已触发未来条件。反例分别是（1）现在增加预算，（2）称两期变化证明投放因果，（3）把“且”改“或”，（4）把基准期净贡献改成本阈值或把本期成本每单改旧期阈值，（5）把下一七日与当前 12 日总额直接比较，（6）省略暂停/复核但仍给出强行动。负例期望定位 candidate，明确具体偏差并请求定向修订或作 advisory；正例不得误报为需删除正确解释。超时、截断、无效 JSON、旧答案摘要和外来引用只使审核 `invalid/unavailable`，不能扩大发布权威或吞掉已发布比较。

当前仅有结构与定位的正反测试，没有模型对这组语义判据的命中/误报证据，不能称 R4.3/R4.4 退出。下一步需冻结精确模型/端点/输入/预算/ledger 并取得独立真实 Provider 授权后做自然校准，再评估一次定向修订与最终复核是否值得进入发布路径；仍须同时闭合 R3 的 M01 建议与 M06 真成本/效果输入。

## 2026-09-28 进入 R5 前的 M01/R4 机制裁决

固定 `c1b42cb` 的同配置联合批 `tmp/r3m01m06matrix1`（当时代码 `0f71168`）再次确认 M01 正向用户规则未交付。只读检查持久会话 `tmp/r3m01actioninputstext1/sessions/29ebd3ce8640` 的候选原文：它说“下一同口径窗口的条件决策需按用户原话核审”，后接 `conditional_action_inputs` 的内部 JSON，其中虽有用户完整双条件原话，但**可见候选并没有写出可交付的触发、停止和受控试验建议**。宿主正确扣留它并保留独立两期数值。仅让审核返回 `pass` 也不能把该占位句变成完成的条件建议；现有 `_SYSTEM_PROMPT` 和 `validate_shadow_audit` 明确 `publication_effect=none`，且禁止把扣留候选直接批准发布。

因此 R3 M01 与 R4 的剩余部分是同一条产品链路：正常模型先提出完整、有条件的候选解释，绑定当前用户原话/回执/同版已核输入；有界语义审核须能区分正确的下一七日双条件和“现在扩投、因果归因、且改或、阈值/窗口偷换、漏停止”的反例；至多一次针对当前片段的修订与一次最终复核，宿主随后才决定可发布片段，同时保留独立比较结果。审核不可新增事实、覆盖确定性失败或当第二 planner。无效/截断/超时必须退回已核结果及具体未答缺口，不能以 `pass` 默许占位句、用尾注掩盖强断言或把正确比较删去。

这是**设计裁决，不是已实现能力**。历史 Shadow 关键风险 1/4 命中、宿主引用 2/2 误报；当前真实模型/端点/额度未获新授权。先完成零调用冻结：精确 HEAD/配置、当前正反输入及原稿 SHA、模型/端点、最多调用数、现有 Provider 账本、逐例 oracle、停止条件；获得本批独立授权后只作诊断校准。若正反能力不能同时满足，停止自动放行设计并提出用户规则结构化确认/受限交付的产品方案，不做第三轮同型词面门或无证正向发布。R3/R4 仍实施中，R5 不开始。

零调用输入准备完成于 `c1b42cb`：`tmp/r4m01-zero-freeze-20260928/positive-request.json` 从同一持久正常 app 会话重放，`status=ready`，`prompt_sha256=sha256:a5ce811730867e9a1e9d6b2680c0d81ef392292e4b0056b5ff21c3bbea80bd8b`，`input_digest=sha256:6e3f66f1a4f86bead616183837fd276d7781a1357d323d017503b8eb48361e3f`，packet/答案摘要在文件中。`oracle-pack.json` SHA-256 `49f01e728897b6eaddeb4d0e4f1905d6ca389b398aed89583868130eb2a88310`，含持久占位候选、正确条件句、立即加预算、伪因果、且改或、阈值互换、窗口错配、漏停止共八项**诊断候选**。合成七项不属于已持久 app packet，不得作为产品发布收据或直接通过 `validate_shadow_audit`；后续真实质量校准须明确这一证据级别，按同一 oracle 计漏检/误报。

配置只读核对：重建树当前模型默认 `gpt-4o`、`API_BASE=None`、`API_KEY` 不存在；固定供体当前配置为 `openai/deepseek-flash`、`https://api.deepseek.com`、密钥存在，但历史配置/授权不可继承。**未发起任何真实调用，也未复制凭据**。现阶段还没有经过代码审查的 R4 调用入口、现有账本接线、完整模型/端点/预算冻结，故本文件是输入与 oracle 准备，不是可执行授权请求或 R4 校准结果。保留独立授权门。

曾审视“直接回显用户规则”作为零调用局部交付：`verify_comparison_action_inputs` 当前只证明提议中的 `rule_source_text` 是问题内的某个 8—500 字节原文片段，并未证明模型选中的片段确实包含完整的双条件、且关系、下一七日窗口及停止操作。把这一片段原位回显可以标明**用户原话**，但不能据此把 `conditional_action` 改为 `answered` 或宣称产品完成；增加词面识别会违反本计划的语义边界。因此维持已核比较与诚实缺口，待受限语义能力或结构化业务规则设计裁决，不实施“直接回显即过关”。

## 2026-09-28 一次性诊断入口与真实调用前置核对

本轮用户已授权开发/测试所需真实调用；仍先冻结每批身份、上限和 Provider 账本。按供体最终 `b181646` 的 `run_shadow_audit_once` 功能片迁入当前 `publication_audit.py`，适配重建树 `withheld_candidates`（供体原函数只接 `pending_spans`）：仅在显式 enabled、正预算、现有 packet/答案/历史组成 `ready` request 且有当前定位目标时调用传入的已计费 client 一次。输入仍为既有 `publication_audit.v1`，4096 输出 token 上限，不重试。异常、截断、空/超大文本、无效 JSON 不扩大发布权；返回 `publication_effect=none`。定向 `tests/test_publication_audit_view.py` 为 4 passed，检查零预算零调用、有效审核、截断、无效 JSON、包不变。这不构成语义命中、修订或发布验收。

真实 P08 路线核对：重建树有 `run_p08_real_matrix.py` 与同一 `ProviderLedger`，但 AGENTS 指定的 `scripts/testing/run_p08_http_matrix.py` 不存在；供体里的 driver 不能直接当当前树批次。当前无真实 Provider initiated call、无本批 ledger；不将供体 `.env` 配置/历史授权当作自动迁移的运行身份。下一步审查供体 HTTP driver 的最终依赖及当前 app 契约，按功能迁入所需控制路径，先形成精确可执行 freeze 再按本轮授权调用。新目录完整 E2 `tmp/r4shadowoncefo1` 为 2920 passed / 1 skipped / 16 warnings，Provider forbidden；这只验证本地机制。R3/R4 仍实施中，R5 未开始。

本轮 R4 自然语义**诊断**批已零调用冻结于 `tmp/r4m01-shadow-calibration-20260928-r1/freeze.json`，由同目录一次性 driver 对供体已有 `run_shadow_calibration.py` 的预检/授权分离与 P08 `ProviderLedger` 功能按当前 M01 输入重构，不加入产品发布路径或第二账本。固定产品 HEAD `0eaadf3cf2c9858033520196ee9eebad0b02dedf`；driver SHA `sha256:c8278b69ffb2e4c02d74dea37c167ee0ca168a9d60f606c378117a3228c5e17a`；精确输入 `requests.json` SHA `sha256:4095cbfac9c89a68e13882252dabab5be720554a6e593f5de929add6552b125e`；原正常 app request SHA `sha256:3da920cda5ad0a65c98c5ee27045102a6c38bb02a665edfb621e03392d55bce2`；oracle SHA `sha256:49f01e728897b6eaddeb4d0e4f1905d6ca389b398aed89583868130eb2a88310`。八例顺序为持久占位候选、正确句、立即预算、伪因果、且改或、阈值互换、窗口错配、漏停止；后七例明确 `synthetic_counterfactual`，只用于模型语义诊断。Prompt SHA `sha256:a5ce811730867e9a1e9d6b2680c0d81ef392292e4b0056b5ff21c3bbea80bd8b`；模型 `openai/deepseek-flash`，端点 `https://api.deepseek.com`，只读供体配置给本隔离进程，未复制密钥；最多 8 次实际请求、每次输出上限 4096 tokens、120 秒 one-shot/no retry，既有 `ProviderLedger` 写本目录 `provider-calls.jsonl`，结果写 `results.json`。超时/传输/协议异常停止，不续跑；每例只诊断 `publication_effect=none`。用户本轮已明确授权开发与测试所需真实调用；本冻结不授权正式默认、外部 Git 或 P08 完整矩阵。**预检阶段实际调用 0**。

执行尝试被自动审批拒绝，原因是冻结输入含用户原话和业务数据摘要，向 DeepSeek 外部端点发送这组具体载荷未获明确目的地授权；审批提示不得绕过。命令没有启动，复核本目录 `provider-calls.jsonl`/`results.json` 均不存在，实际 Provider initiated 0。已请求用户就精确冻结批次明确许可；此前仅做不依赖调用的工作。

用户随后**明确授权该冻结 SHA/DeepSeek 端点/8 次与每次 4096 token 上限**，原命令获批执行。`provider-calls.jsonl` 仅有第 1 例 `persisted_placeholder` 的一组 `started`/`dispatched`，无 `failed`，实际 Provider initiated **1**；`results.json` 为 `stopped`。响应 `completion_tokens=4096`、`finish_reason=length`、可见正文为空（空串 SHA `sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`）。按冻结停止条件，未执行其余七例，也未恢复、重试或篡改本批。无有效 `publication_audit.v1` finding，不能计算正反命中/误报，不能声称 M01 语义闭合。当前更窄的技术问题是该模型在此提示/输入和 4096 输出上限下只耗尽输出预算而没有可见 JSON；须先审视返回形态和下轮输出策略，再重冻新批。模型质量和产品发布结论仍未知；既有比较结果保持发布，行动候选保持扣留。

用户本轮明确指出 4096 输出上限是已知不足，并授权按接入模型要求的 **64K** 重测。DeepSeek 官方说明 `deepseek-flash` 默认启用思考，思考模式未显式设置 `max_tokens` 时默认 64K，思考内容在 `reasoning_content` 而最终正文在 `content`；这与本批“4096 耗尽、正文空”一致，但未保存推理内容，不能把它当作直接观测的成因证明（https://api-docs.deepseek.com/guides/thinking_mode/；https://api-docs.deepseek.com/api/create-chat-completion/）。`c25cddd` 将 R4 一次性入口输出常量和测试断言统一为 65536，并让空正文且 `finish_reason=length` 优先记 `truncated_output`；定向 4 passed。新目录 `tmp/r4m01-shadow-calibration-20260928-r2/freeze.json` 固定 HEAD `c25cdddaeb516083205d8d1acd2fe6e220630aec`、driver SHA `sha256:bbd637edc26044e03626b6ca0bbfbcdac6f95b3b53e3b9b59a82f997f973a20b`、同八份请求 SHA `sha256:4095cbfac9c89a68e13882252dabab5be720554a6e593f5de929add6552b125e`、同模型 `openai/deepseek-flash` 和 `https://api.deepseek.com`、8 次物理调用上限、每次 65536 输出 token、120 秒单次、现有 ProviderLedger 写新目录账本。新批预检 0 调用；旧批不可续跑。该冻结仍只作语义诊断，不升级 M01 发布、默认或 P08 验收。

r2 尚未调用时发现 120 秒单次超时不足以可靠容纳 64K 生成，故 r2 保留原冻结、零调用废弃，未修改其参数。r3 `tmp/r4m01-shadow-calibration-20260928-r3/freeze.json` 重新冻结同一八份输入 SHA、模型/端点、8 次/65536 token 上限，单次超时 600 秒；driver SHA `sha256:f4a30026d2b5bd845e500d6d3466bd5dc56e808fc691a3349ff872626817878a`，新账本，预检调用 0。按本轮用户明确的 64K 重测授权执行 r3；三批身份和结果分开记。

### r3 完整诊断批与 R4 设计裁决

r3 `results.json` 已完成八例，账本为 `started=8 / dispatched=8 / failed=0 / denied=0`，实际 Provider initiated **8**；八例 `finish_reason=stop`，没有 64K 截断。`evaluation.json` 由当前 `validate_shadow_audit` 对每例计算，**协议有效 0/8**：六例缺 `schema_version`，两例虽有 `publication_audit.v1` 版本却使用协议外 dimension；宿主合法 finding 为 0。前七个 counterfactual 的身份只是对同一 app 审核输入替换扣留候选的**合成诊断**，不能作为正常 app 产品收据。逐例原始输出可见：持久占位句被指出未交付条件建议，六个危险反例均被自由文本指出具体偏差；但正确条件句也被要求 `request_targeted_revision`，理由是未来窗口尚无观测、候选仍被扣留。该理由混淆了“正确描述未来条件”和“宣称未来条件已触发”，并把扣留状态当作语义错误。另有把正确宿主比较当成缺少行动建议的 finding。因而不能将自由文本命中当作协议合格，也不能删除正确解释或根据 `pass` 放行。

与历史 Shadow R1 的关键风险漏检/宿主引用误报对照，本轮虽在 64K 下识别六种构造危险句，**正确解释保留和受限 finding 协议仍不收敛**。依据总计划同根因两轮停止规则，裁决停止同型“改审核提示→再跑八例”的补丁路线；Shadow 维持只读诊断，不进入发布授权链。下一产品路径使用既有 confirmation、`answer_bindings.v1` 与同一正常 app packet：模型可提出一份结构化、定位到用户原话的条件规则候选；宿主先核对原话来源、当前回执/版本和候选的范围，只有**解释仍有会改变行动的真实业务歧义**时才用既有确认机制向用户核实，不把已明确给出的业务值重新包装成必答审批。可闭合的条件规则由宿主原位渲染，同时明确当前两期比较并未触发未来条件；未闭合时独立正确比较保留、条件行动仍为具体未答缺口。这样遵守 IC“先查找用户已给出的值、无真缺口不问”以及 VP/CP 的当前版本和正确解释保留约束。此方案仍待实现和正反 app 验证，不能因本裁决记 R3/R4 退出或进入 R5；不得另建 planner/账本、词表或尾注过关。

当前 `c25cddd` 新目录完整离线回归 `tmp/r4shadow64kfo1` 退出 0：2920 passed / 1 skipped / 16 warnings，Provider transport forbidden。该回归验证 64K 本地调用参数与降级代码不破坏确定性保护，不抵消 r3 的 0/8 协议失败；它不是自然 app、视觉或 M01 发布验收。

## 2026-09-28 宿主结果权威边界的局部修正

当前终局路径在 `render_bound_claims_with_trace` 对 M02、聚合和比较的 `answer_bindings.v1` 块按当前 packet/回执渲染后，又将宿主正文整体交给 `validate_final_narrative`。这是已核事实的重复散文裁决；合法宿主措辞也可能因词面门被误拒。当前工作树移除三条宿主正文的二次调用，比较路径只对**模型补充解释原文**维持现有检查，失败时仍只发布独立宿主结果。当前回执、同版本、事实引用、唯一占位符及 trace 校验未放松。未实现或宣称完整条件行动，扣留候选仍不得直接发布。

定向回归 172 passed；终局测试特意让散文门拒绝模型候选并对宿主正文抛错，比较数值仍发布，候选未发布。新 `local_http_api` Provider 禁用单场景目录 `tmp/r4-host-claim-boundary-20260928-r1`：演练服务 PID 18448、端口 18743、原入口；控制脚本 SHA-256 `ff978b322ccd964fc771cb2d54db4f5030120849d4ca9e5ee530d9433056531e`；F-ACTION.csv SHA-256 `a5374e58a931846541c13841523e1378a4525b9ce8dcab2cdd3837e74f0a8fc5`，上传票据相同；会话 `31494b2f4a89` 唯一 `turn_end=completed` 与 durable 状态一致，当前比较 700/770、140/175、560/595、70/77 和输入块保留，Markdown 导出含全部非空答案行。`runtime.jsonl` 无 `forbidden_provider_transport`，实际 Provider initiated 0，服务随后关闭。行动需求仍 `evidence_insufficient/checked`，候选 `withheld_pending_semantic_binding`。此结果仅证实宿主边界的正常 app 路径，不是完整 M01—M06、浏览器视觉或自然模型语义验收。

完整离线回归新目录 `tmp/r4hostboundaryfo1` 退出 0，JUnit 为 2922 tests / 0 failures / 0 errors / 1 skipped，pytest 汇总 **2921 passed / 1 skipped / 16 warnings**。未因回归绿色重写上述行动缺口。

## 2026-09-28 M01 发布链根因及下一实现边界

只读核对 `545f7da` 和新 app 会话 `31494b2f4a89`：用户原话明确“下一同口径七日、净贡献不低于基准期 **且** 成本每单不高于本期，才考虑小规模受控试验；否则暂停增加预算并复核”。模型可见候选却只写“条件决策需按用户原话核审”；完整句子仅在内部 `rule_source_text`。解析器校验它是当前问题中的某个子串，输入 verifier 将该子串压成 SHA 并核对当前 A/B 数值；并没有生成或验证条件组合、阈值角色、未来观察与正反动作。宿主比较 builder 只产生 `observed_comparison` 和 `conditional_action_inputs`；终局一旦发现行动缺口就扣留整个候选，coverage 仍是 `evidence_insufficient/checked`。Shadow 一直 `publication_effect=none`；此前 64K 八例协议有效 0/8，正确条件句也遭误报。故既不是输出 token 不足，也不是补一个词或调一个审核 `pass` 能闭合的缺口；**缺的是行动 claim 的生产、验证和原位渲染所有者**。

当前代码最小反例（不改文件，Provider 0）：调用现有 `tests/test_r3_comparison_action_inputs.py::scenario`，只将 JSON 中原本完整的 `rule_source_text` 替换为 `packet.question[:8]`；该八字来自请求开头，未含七日、双条件、受控试验或停止分支。`parse_comparison_action_input_proposal` 返回 proposal，`verify_comparison_action_inputs` 仍返回 `inputs_verified_semantics_unassessed`。因此子串来源校验和已核数字属于不同维度；当前扣留行为是必要保护，不能以“输入块已核”替代行动 claim。该反例是机制诊断，不是正常 app 的新语义验收。

随后以 `d0d7cf3` 把反例固化在现有 M01 测试文件，并将输入块放入正常比较绑定后渲染：四行比较中的净贡献保持 560/595/35，行动覆盖仍 `evidence_insufficient`，完整用户规则不被假装为已交付；定向 12 passed、Provider 0。该测试保护下一实现不会把“来源子串属于当前问题”误作完整规则语义。完整 E2 和新的正常 app 正反批仍须在下一产品实现后运行。

对接入端点的官方接口能力作只读核对：[DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/) 仅保证 JSON 语法，且文档说明偶发空正文；[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) 的 strict tool 参数可约束函数参数 schema，但模式适用性仍需单独验证。这些只能改进输出**形式**，不会证明用户规则中的合取、阈值、未来窗口和停止分支映射正确，不能把 r3 协议 0/8 或正确例误报解释成“只需切 JSON mode”。不在本轮追加第三次同型 Provider 诊断。

## 2026-09-28 已核成本分母的正文交付

复核发现 `conditional_action_inputs` 已按原数据逐行核实 140/70、175/77，原宿主正文却仅说“分母已复核”，没有向用户交付每单成本的当前值；渲染器也只看 block 状态而未重新核对其存储值。当前产品改动让渲染器在展示前对同一 `compare_periods` 回执、源版本、日期窗口、事实引用、四角色 A/B 数值、净贡献等式及成本/订单分子分母复核；若输入块被伪造，只退回行动输入缺口，四行独立比较仍发布。核对通过时原位显示 A `140÷70≈2`、B `175÷77≈2.2727`，同时保留列定义/单位未知、未来窗口未观测和行动语义未闭合。定向 16 passed，包含伪造 B 分母的局部降级反例。

新 `local_http_api` Provider 禁用单场景 `tmp/r4-action-input-render-20260928-r1` 使用现有演练入口，服务 PID 12400、端口 18744；控制脚本 SHA-256 `45991a9d13248c265ca4d47e43e382d1a640d32cd1096b617948448896454aa6`，夹具/上传票据 SHA-256 `a5374e58a931846541c13841523e1378a4525b9ce8dcab2cdd3837e74f0a8fc5`。会话 `ab7b4d8b1d0c` 唯一 `turn_end=completed` 与 durable 状态一致；持久绑定含 observed comparison 与 `inputs_verified_semantics_unassessed`，行动 coverage 仍 `evidence_insufficient`；正文两比值和未来未知边界存在，Markdown 导出覆盖正文所有非空行。结束健康 `ok=true/provider_enabled=false`，`runtime.jsonl` 禁止 Provider 传输事件 0，实际 Provider initiated 0，服务随后关闭。此证据是当前封闭输入的功能交付，不是完整条件行动、完整 M01—M06 或视觉/真模型通过。

稳定代码新目录完整 E2 `tmp/r4actioninputrenderfo1` 退出 0，JUnit 为 2923 tests / 0 failures / 0 errors / 1 skipped，pytest 汇总 **2922 passed / 1 skipped / 16 warnings**，Provider transport forbidden。该结果不更改 M01 行动缺口。

下一功能包的不可拆分验收：同一正常 app packet 的用户来源、两期回执/数据身份、条件布尔结构、两个阈值参照、未来窗口状态、受控试验/停止分支必须在既有 `answer_bindings.v1` 中贯通至渲染、SSE、持久历史和导出。正例保留完整原规则和独立四行比较，尚未观测的未来条件为 `unknown`；反例为立即扩投、因果宣称、`且→或`、错参照期、12 日对 7 日、删“否则”、只取用户句子的无害子串及伪造/旧版回执。宿主可验证闭合事实与引用，不能声称子串命中等于语义等价；模型散文不是事实源，Shadow 仅对开放解释提出定位到 claim/span 的诊断，不能单独授权。失败只影响行动片段，不能吞掉比较值；不能用引述、待核标签或末尾说明把未交付建议标为 `answered`。这组判据需要新的正常 app 正反批和自然模型能力证据；现有合成 Shadow 例不计 app 收据。只有真正缺失且会改变业务动作的值才调用既有确认，不把用户已经给出的规则再要求确认一遍。

## 2026-09-28 当前请求来源由宿主绑定（`0cd4631`）

此前 `rule_source_sha256` 是对模型自选 `rule_source_text` 的摘要，八字子串也能获得貌似可信的来源字段。现有 `conditional_action_inputs` 仍只核数值，宿主改为对当前 packet 的**整条用户请求**及 `turn_ref` 生成 `request_source_sha256/request_source_ref`；原位渲染重新核对摘要，只读扣留候选审核入口也核对同一请求。旧模型字段可被解析以兼容历史候选，但不会进入权威来源、审核载荷或行动完成判定；演练模型不再生成该字段。改变请求或伪造分母均只撤销行动输入显示，独立比较仍保留。

定向比较/审核/M02 确认 **14 passed**。`local_http_api` 新目录 `tmp/r4-request-provenance-20260928-r1`：服务 PID 17636、端口 18745，健康 `ok=true/provider_enabled=false`；控制脚本 SHA-256 `a8c1819b731278c50f18c2c60af220fae2ebb2bceba4a83eb31a7bdd6e451a28`，F-ACTION.csv 上传票据 SHA 与冻结 fixture 一致；会话 `38d1d721d107` 单个 `turn_end=completed`，durable 状态、回答及 Markdown 导出一致，绑定为 `observed` + `inputs_verified_semantics_unassessed`，来源摘要为当前完整请求，成本比值原位显示，行动覆盖仍 `evidence_insufficient`。`runtime.jsonl` 只有 `server_start/auxiliary_call/scripted_round`，`forbidden_provider_transport=0`，实际 Provider initiated 0；服务已停止。视觉、自然模型及完整 M01—M06 未评估。首轮完整 E2 `tmp/r4-request-provenance-fo-20260928-r1` **失败**：2921 passed / 1 failed / 1 skipped；唯一失败的上传元数据回滚测试在 Windows 写临时文件前遇到绝对路径长度 261 的 `FileNotFoundError`。该失败批保留；短新目录 `tmp/r4srcfo1` 完整重跑退出 0，**2922 passed / 1 skipped / 16 warnings**，Provider forbidden，产品上传逻辑未改。

根因边界没有消失：整条请求的身份可确定，但从这条请求抽取合取、阈值和停止分支仍是开放语义。模型提交这些字段不自动证明等价；先前 64K Shadow 在正确例上误报，不能充当确定性许可。下一步应作 R4.5 可审阅的产品方案裁决，再在所选方案下实现正常 app 正反纵向路径；在此之前 M01 条件行动仍未交付，R3/R4 不退出，R5 不开始。

本轮试图把模型的固定双条件结构在当前数值/窗口/动作 enum 校验后接到终端发布，自动审批拒绝了**终端接线**：结构正确不证明对用户原话的语义映射正确，直接 `answered` 可能误发布业务行动。该补丁未应用，未接入的草稿已撤回；没有通过其他编辑渠道重复该动作。三个产品选择与风险已写入唯一总计划，用户选择前保持现有行动缺口并推进 M02 独立工作。实际 Provider initiated 0。

## 2026-09-28 用户选择语义质量优先；正常 app 采集完整候选

用户选择先验证语义质量、保留行动缺口。当前诊断把两种失败分开：旧正常 app 只有“按原话核审”的占位候选，不能判完整规则；64K Shadow 的正确合成候选被要求修订，理由掺入“候选尚未发布/未来窗口尚未观测”，且八例协议有效 0/8，不能作为语义批准者。产品发布提示现要求模型在可扣留的候选中用自己的话交付未来双条件、两个阈值参照、触发/停止动作及尚未观测边界；**宿主的发布、coverage 和 Shadow 权限均未改变**。

Provider 禁用、`local_http_api` 单场景 `tmp/r4m01candidate1`（18747/PID 10976/exec session 94903）核对了正常 upload→chat/SSE→同一 packet→持久历史→Markdown 导出。控制脚本 SHA-256 `6b55886c664bd3158615974e9d9d8dac564592186ea9aca256d8d4e2d9da98a2`，F-ACTION.csv 票据 SHA-256 `a5374e58a931846541c13841523e1378a4525b9ce8dcab2cdd3837e74f0a8fc5`，会话 `9c029aaecf04` 唯一 `completed`。演练候选含合取、阈值、受控试验、暂停复核及未来未观测，SHA `sha256:7faa15c641a81b58ca8e189b3e4e13ac33a543e4b68554f24ef63862f3fe4ef8`；它被 `withheld_pending_semantic_binding` 扣留，正确比较与成本每单继续显示，行动需求 `evidence_insufficient/checked`。runtime 禁止 Provider 传输事件 0，实际 Provider initiated 0；服务已停，定向 7 passed。演练脚本中的正确句是**合成控制输入**，不是自然模型质量证据；视觉、全矩阵也未评估。下一步须冻结真实正常 app 正反样本和独立 oracle 并单独获批；仍不能进入 R5。

## 2026-09-28 P08 首次完整真模型批次与发布层根因

用户对 `tmp/p08rb1/freeze.json` SHA-256 `543529afd280d7a92bbd156b11ca743eacd912b20f4655060ac90c52c6518759` 明确授权后，固定 `4ace7abe`、`openai/deepseek-flash`、`https://api.deepseek.com`、本地 HTTP 正常 app 路线执行 M01—M06 一次。账本 `provider-calls.jsonl`：105 started、105 dispatched、0 failed、0 denied；六个隔离会话与 SSE 单终态相符。M01 两轮和 M02/M03/M05/M06 的 durable 状态为 completed（M06 中途按冻结业务选项 suspended→resumed）；M04 v1/v2 都 failed。批次整体失败；HTTP 路线的上传 picker、视觉呈现和浏览器刷新未评估，不能计 E4 浏览器通过。服务已停止；不补跑本冻结。

M01 第二轮 `7b137648f3f3` 的宿主回执正确保留 700/770、140/175、560/595、70/77 四行。自然模型却把未来七日尚未观测的成本每单条件当成已由当前两期否定，宣布“条件未满足→暂停”，又添加了用户未设的停止条件；还在用户正文漏出了 `[[chart:...]]` 和 fenced `answer_bindings.v1` JSON。这不是 oracle 的单纯误拒。该 packet `requirements=[]`、`requirement_revision=0`、仅有 `observed_comparison`，没有行动缺口；`loop.py` 在无 `conditional_action_gap_ref` 且旧散文门通过时直接附加整段候选。六个场景已发布 packet 的要求均为空，证明要求生成链路在这批自然调用上整体失效。辅助客户端虽然主答案冻结 65536 token，实际由产品 `for_purpose(max_tokens=300, timeout=8)` 派生；当前账本不记录分类原文或 finish_reason，不能断言每次确为截断，但这个低上限与零有效逐项输出必须修正并在下一批量化。

首个修复包使辅助输出上限继承主客户端，并把比较自然候选一律保存在同一 packet 的 `candidate_resolution`，只发布当前回执的宿主比较；13 项定向测试通过。此包消除了“分类为空即自由散文放行”，**不算完成 M01 条件建议**，也尚未证明正确自然解释可发布。下一步须在现有 claim/回执边界内设计可保留正确解释的正向路径，不能把扣留候选或原话引用改名为 `answered`。自然语义审核仍只诊断，不能升级为随机总审批。

后续归并提交 `562a135` 又保留 `result_followup` 的精确来源输出，记录不含用户原文的分类结束原因/有效片段数，M04 宿主回执身份等值不再受后建任务的原始数据访问范围误导，并让计划投影回执说明实际启动的 step/dataset。目标分支新目录完整 E2 `tmp/r4p08rootfo2`：**2931 passed / 1 skipped / 16 warnings，退出 0，Provider forbidden**。此为本提交离线证据；没有新的自然 app 批，M01/M04 价值出口仍未通过。

再核边界：`a6b3c31` 把辅助期限从硬编码 8 秒改为继承当前客户端 120 秒；单次输出上限也继承，在 P08 环境为 65536，物理调用仍 one-shot。意图/辅助定向 207 passed。前批没有保存辅助分类原文或 finish reason，因此 8 秒超时是与全场景空要求一致的假设，不能写成已证明根因；下一批日志将区分 transport/空正文/无效 JSON/输出片段被校验丢弃。新零调用冻结 `tmp/p08rb3/freeze.json` SHA-256 `83ab2823f4084ea4d5d61012caf6f68829e201e9b0e6a0415de2720b78dd3888` 已就精确载荷和目的地单独请求授权，**尚未获得回复或发起新 Provider 调用**。`tmp/p08rb2` 配置不全的预检目录没有账本/会话，不重用。

M04 `1a7b5ff67637` 的失败独立于 M01：v1 模型执行过 `analyze_time_series`，但三条 `record_evidence_record` 均无 `competing_hypotheses` 结构关系，质量门按原目标拒绝；v2 已上传并读到 10/10/10 的当前值，但模型在记录 v2 证据后才创建含 v1→v2→综合步骤的执行计划，首先锁到 v1 任务。进一步核对持久工具回执和 workspace 元数据，v2 的 version_id/fingerprint **一致**；`record_evidence_record` 却使用受当前 v1 任务范围限制的 `workspace.get_data_identity(v2)` 核验，得到空身份并误报 `stale_data_binding`。其后重算 v2 被正确的 `dataset_outside_current_task_scope` 拒绝。已只在宿主内部增加布尔式回执身份等值核对，原始数据读权限仍按当前任务；真实旧版身份继续拒绝。定向范围/假设保护 27 passed。晚建计划把当前步骤锁在 v1 的问题仍未解决；不得为通过测试解除原始数据范围限制，需让独立正确观察局部交付、关系缺口明确，且不能把 v1 证据升级为 v2 结论。

## 2026-09-28 M01 长期卡点的跨版本复核

用户要求检验旧真模型成功率与当前测试设计。供体历史 P08 R7/R9/R10/R11/R14 将 M01 标为 passed，R16 标为 failed；这些批次的 M01 输入是 `M01-sales.csv` 的 12 行恒值订单与开放式“有条件建议”，并**没有**当前 `F-ACTION.csv` 的下一同口径七日、两阈值合取和否则暂停规则。旧“通过率”不构成对新规则映射能力的观测。历史正文还显示验收偏宽：R7 会话 `14dbe7e4889a` 自定“≥30 天/≥2 渠道”等门槛且称数据可能是测试/占位；R10 会话 `b3dcb3370dfe` 自定显著性阈值 `0.05` 与每渠道样本门槛；R16 才因“人为规则数据”无来源而失败。旧批另有一些正确的 12/120、未知单位和条件表达，不能全盘否定；但其 passed 标签不能替代逐 claim 复核。

当前阻断也确有**验收程序问题**：旧联合本地批把 M02 未确认的 0.1 错按确认后 10% 判失败，已用新双路径收据和合同修正；M01 演练客户端长期只生成“按原话核审”占位候选，不能作为自然生成器的语义成功率样本；64K Shadow 八例是合成候选，审核输入把 `withheld_in_current_packet` 与候选语义放在一起，正确未来条件句被因“尚未发布/未来未观测”要求修订，且协议有效 0/8。这些失败不应混成“真实 LLM 生成能力不足”。

产品缺口仍真实存在：正常 app 的比较数值已有同版证据与宿主渲染，行动规则却没有已验证的语义映射所有者。仅把模型字段结构化并做数字/版本/布尔校验，不能证明模型把用户的“且、阈值、未来、否则”映射正确；自动审批拒绝的直接发布接线因此保持撤回。当前决策是**分层验收**：旧 M01-sales 的原始价值与独立事实、F-ACTION 的精确规则、审核协议有效性、候选语义质量及正常 app 发布分别判定。先获得自然模型在正常 app 的候选，再由独立人工 oracle 检查正确候选保留与危险偏差；不把合成 Shadow 或脚本模型收据冒充产品成功。R3/R4 与 R5 的关系按总计划重新校准，但不能降低原 VP/IC/CP 的条件建议、真实确认和逐问题交付目标。
## 2026-09-28 r4 校准：任务语义与协议分开计量

精确冻结：`tmp/r4m01-shadow-calibration-20260928-r4/freeze.json`，SHA-256 `27ec6b35a898a03f519cc137689dd2e8ed9dca39129b8eb746c9a0e9d7514de8`，用户已对此冻结明确授权。输入产品 HEAD `e29caeb`；固定 `openai/deepseek-flash`、`https://api.deepseek.com`、8 次物理调用上限、每次 65536 输出 token、600 秒 one-shot、独立 `provider-calls.jsonl`。原持久 app 审计请求来自 `tmp/r4m01-zero-freeze-20260928/positive-request.json`；本批按产品当前候选投影去掉发布状态和宿主已发布正文的审核状态，保留原话、候选、已核数值和定位引用。另七例标记为合成反事实，不能当作七条 app 运行收据。

账本 8 started / 8 dispatched / 0 failed，八例均 `finish_reason=stop`，无截断。`results.json` 与 `evaluation.json` 显示：正确未来条件候选为无 finding 的 `pass`；原持久占位候选与立即加预算、伪因果、且改或、阈值互换、窗口错配、漏停止六例都有指向候选的 finding。原校验器只接受扁平 `candidate_id`，其中四例返回等价且唯一的 `target: {candidate_id: ...}`，故原协议仅 4/8 有效。后续本地提交 `d03a680` 在同一 `publication_audit.v1` 校验器中只接受两种精确表示之一，拒绝冲突/多目标；对**既有八条原始输出**重评分为 8/8 有效，定向离线 7 passed。该重评分不能记成 `d03a680` 新 HEAD 的第二次真实模型批次。

这批证实先前的正确句误报与协议 0/8 主要来自审核任务/输入边界及目标字段表示，不能作为模型不懂完整条件规则的结论。诊断样本仍只有一条既有 app 占位候选，其余均合成；自然 app 的完整行动候选、正向发布、同版关系与局部解释保留均未由本批证明。Shadow 的 finding 保持 `publication_effect=none`，不授权行动 claim 或覆盖确定性失败。后续实现必须沿现有 `answer_bindings.v1` 的来源、版本、真实业务规则和宿主可核边界闭合，不能把本批 8/8 直接接为发布开关。
