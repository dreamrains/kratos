# R4.3 M01/M06 内容失落的根因与实施接口裁决

代码与证据身份：重建树 `codex/trust-rebuild-20260927@f5b3806`；供体 `main@b181646` 固定只读。本次只读复核原始 VP G2/G6、IC 业务确认原则、CP CR03/CR04，与目标树 `AgentLoop`、`publication_synthesis`、既有 Provider 禁用正常 app 收据；没有新模型或 Provider 调用。诊断脚本 `tmp/r4_m01_candidate_diagnose.py` SHA-256 `A937D4A093BFD8DE1EF58F94184754210C8ED599DE4CB70A343D4A22D88580B3`，读取 `tmp/r4trace2` 的 M01 当前包。历史完整批次的成功/失败仍属各自版本，不能代替此 HEAD 的证据。

## 已证实的链路缺口

1. **M01：生成了候选，却在宿主分支整体消失。** `AgentLoop._render_terminal_publication` 的聚合分支先从当前 `transform_data` 回执生成正确 `observed_aggregate`，随后无论候选内容如何，都只发布这个宿主块，并把不同候选记录为 `superseded_by_current_receipt_claims`。正常 app 会话 `tmp/r4trace2/sessions/9985e0ae0644` 的六轮正文 SHA 相同，保住源 12 行、派生 1 行、总额 120、数量 12、方法及未知单位，但丢掉受众表达和条件建议。这是组合接口缺失，不能靠尾注恢复。
2. **现有自由文检查不是开放建议的安全证明。** 使用该会话真实最终 packet，对演练模型的 B01 与 B05-BUSINESS/ANALYST/MANAGER/PLAIN/TECH 六份候选逐一运行 `validate_final_narrative_issues`，六份均返回 `[]`。其中 B01/B05-BUSINESS/MANAGER/PLAIN 用当前 12 天总额 120 作为“下周低于 120”投放动作阈值，窗口长度和投放效果证据均不支持。因此把比较分支的“通过当前校验即附加自由文”直接移到聚合分支会误放；不能增加一个词表来假装解决建议语义。
3. **M01 需求身份也不闭合。** `extract_explicit_requirements` 对原 B01 请求返回空；当前会话 state 中三个 `answer_requirements` 是 `请改成…表达` 被替换正则误认成的“业务负责人/分析师/管理者表达”，最终 packet 的 `requirements` 仍为空。它们既不是总额/方法/建议的可靠子目标，也没有当前包的回答覆盖。现有通用 `analysis_spec` 是数据理解模板，不能推导安全行动条件。禁止把检索词或这些伪需求标为已回答。
4. **M06：确认生命周期闭合，但恢复执行与内容契约不存在。** `tmp/r3contentbase1` 成本会话 `f9079cac11df` 中，业务范围选择“代金券及渠道成本”后同会话正常完成；原始用户请求与选择已传给恢复模型，但该模型只回复“已复用口径”。落盘 state 为 0 `tool_receipts`、0 `publication_packets`、0 `answer_requirements`，`analysis_spec/analysis_plan` 为空。`extract_explicit_requirements` 对原请求也返回空。终态在无回执时直接走原文返回路径，因此确认成功被误当成任务交付；宿主没有可合法发布的 120、成本或净收益数值。不能从文件或旧会话替模型补算。

## 同一发布链路的实现决定

- **需求生产**：从当前规范用户消息建立稳定任务/子目标引用，复用现有 `analysis_spec`/`answer_requirements` 与 `answer_bindings.v1`，由现有分析/最终化模型调用提供语义拆分，宿主只校验来源消息、目标身份、生命周期和不重复。不要建立第二 planner，也不要从文本检索命中宣称覆盖。表达请求只改变展示目标，不应取代原分析目标。
- **封闭结果**：继续由现有回执、数据版本及宿主 renderer 生产数值、方法、范围、图表。候选的数值/比较条件须以 `answer_bindings.v1` 中的当前 claim、指标、观测窗口、未来可比窗口和必要成本/效果输入为引用；宿主验证相同口径、粒度和窗口长度。没有可比窗口或任意阈值的动作不得变成发布建议。已核的独立事实不因该条件失败而消失。
- **开放解释**：候选表达、因果意义、行动语气保留其原位和精确引用，R4.2 的只读 trace 可供审核。现有确定性检查不能授予自由文语义通过；受限审核必须只针对证据绑定的具体片段，最多一次定向修订，不能加事实或覆盖数值/版本失败。历史 Shadow 1/4 关键风险命中且两次误报，在新校准前只诊断、不自动批准开放建议。未通过时保留宿主正确结果和可核局部解释，明确该交付项未完成，不能靠“待核”标签冒充验收。
- **确认恢复**：业务选择只确定净收益公式的成本范围，不提供成本金额，也不是方法许可。恢复轮沿原任务和同版本确认引用继续正常工具执行；有真实订单汇总回执才发布总额。若无计算回执，订单总额与净收益为 `not_computed`；若已知口径而缺成本或促销增量输入，净收益决策另记 `evidence_insufficient`。这些状态必须与用户原子目标、缺少的输入及正文位置绑定，不能是尾注或独立账本。未算不等于零，失败不抹掉其他当前独立已核结果。

## 下一实施顺序与停止条件

1. 先扩展现有任务/绑定协议的语义生产与身份校验，测试表达重述不替换原目标、M06 确认仍指原任务；再接聚合宿主块与原位候选的局部组合。不要先把旧 `validate_final_narrative` 的空问题当安全许可。
2. 在新的 Provider 禁用正常 app 目录跑 M01 六轮正反条件，以及 M06 缺失、有效确认后有/无计算回执、skip 与版本变化；核对 SSE 唯一终态、正文、packet/状态、规范历史、导出及 Provider 0。HTTP 视觉 oracle 单独标注；完整 E2 后再判断本地包。
3. 同根因已多轮出现；若结构化条件仍不能同时保留正确解释与阻止无据建议，直接记录受限发布决策和未满足的原 DoD，不追加第三轮关键词、正则、模板尾注或“待核”改名。真实 Provider、自然校准、正式默认和外部 Git 继续走独立授权门。

## R4.4 两批实施后的设计裁决（2026-09-27）

`tmp/r4goal1` 在正常 Provider 禁用 app 路径保留复合业务请求的分析目标；`tmp/r4goal2` 同路由将“促销净收益”及“已算、未算和缺少证据分开”按原话持久化到现有 `answer_requirements`，来源消息与任务保持一致。第二批定向 258 项通过；M06 缺失/真实成本范围确认/恢复的 SSE 终态唯一，上传票据、持久化及导出闭合，runtime 无禁止的 Provider transport，实际 Provider 调用为 0。恢复会话 `cdf323f5c561` 仍为 0 计算回执、0 发布包，终态 `completed`，正文仅承认成本口径；需求身份的修复没有使模型执行计算或提供逐项缺口。

同一根因已连续两批复现，停止增加意图词、提取字段或模板尾注。结构裁决：确认恢复后的结果子目标与当前回执在统一终态边界闭合；没有当前计算回执时拒绝“已交付”终态，利用现有一次恢复额度要求正常工具执行，仍缺失则失败并保留拒绝候选。只有实际回执才能产生数值与方法，只有相同版本的绑定才能发布解释或条件。此裁决先消除假完成，不将失败通知计为 M06 内容验收。下一批必须用新目录正常 app 验证该边界及原有独立正确结果，随后实现同包局部组合；若结构性恢复仍无法计算/交付，重新裁决执行能力，不再回到意图字段补丁。

结构修复后的 `tmp/r4guard1` 选择 `control_route=local_http_api`，视觉 oracle 未评估；服务端口 5236、PID 19512、保留 exec session 66092，健康检查 `ok=true/provider_enabled=false`。launcher SHA-256 `93862FF1CC85234275C36CB9DF7F9BA617237035F71E8CC6CFD39503B41A01EC`，既有 M06 HTTP driver SHA-256 `18482118288227F8EC18C82A4BD12668100284A89F7D827557CC2224ABCBFA50`，结果 JSON SHA-256 `DA09FDB8E394523B21492D0DF7D02C4F8B0804FFD87ADA20C219144BED9811F9`。缺失会话 `19948e081b45` 正常完成，确认会话 `d7f7b93c4324` 先 suspended、同会话恢复后 `failed`；SSE 每轮唯一终态与 run-state 一致，0 计算回执/发布包，两个被拒候选落盘，runtime 中 0 `forbidden_provider_transport`，实际 Provider 发起 0。服务已通过原 exec session 停止。结果是防假完成，不是 M06 净收益/缺口分层通过。

最终代码 E2 `tmp/r4guardfo2` 为 2904 passed / 1 skipped。再次以新身份运行完整同场景 `tmp/r4guard2`，控制脚本只增加成本组前健康检查，SHA-256 `9819C630E84F1C562439E1D53E61CB2EBD0819D9F1FC8E9477B0881CA1768826`；服务端口 5237、PID 9916、exec session 54063，启动与成本组前健康均为 `ok=true/provider_enabled=false`。结果 JSON SHA-256 `944E3739B468A80BCD73C08BCD82423D8551617DE47B8E985E6E406DEC7A4689`：缺失会话 `4be72f415733` completed，成本会话 `69445dd75652` suspended 后同会话恢复 failed；每轮 SSE 唯一终态等于持久状态，原话需求 2、计算回执/发布包 0、被拒候选 2，导出可读，runtime 禁止 Provider transport 0，实际 Provider 发起 0。服务已通过原 exec session 停止。该批为本地 HTTP 应用链路，不评估上传 picker、视觉正文、刷新或真实 Provider。

代码审查发现确认恢复后，若旧 ready 包仍可用于展示，包选择可能先于无回执检查，因此将同一目标/回执条件移至所有旧包选择之前，新增“旧 ready 包不能充当新口径结果”的定向回归。最终代码 E2 `tmp/r4guardfo3` 为 2904 passed / 1 skipped。新 app 批次 `tmp/r4guard3`，端口 5238、PID 8824、exec session 75932，启动和成本组前健康均通过，launcher/driver digest 与上批相同；结果 JSON SHA-256 `30DC38752BECCDD3D8AAD4286C211D82BE0E6D7ED61BB7EA5A115413357E11E5`。缺失会话 `267f00d09ee1` completed；成本会话 `6bf48b6b32bf` suspended、同会话恢复 failed；每轮 SSE 唯一终态等于落盘 run-state，原话子目标 2、计算回执/发布包 0、拒绝候选 2、导出可读、禁止 Provider transport 0、实际 Provider 发起 0。原 exec session 已停止。防假完成本地闭合；净收益分层内容与 M01 表达/条件建议仍未通过。

## R4.5 M01 表达局部组合及条件建议能力裁决（2026-09-27）

对 `61c137b` 的完整同会话 M01 基线 `tmp/r4m01base`，六轮都是 SHA-256 `33e0aceaa852` 开头的正确聚合正文；表达和建议没有进入正文，且旧替换正则产生三个伪需求。实现将本轮语义表达原话保存在现有 `answer_requirements`，通过本轮消息引用、原文片段与 `answer_bindings.v1` 的 `requirement_refs`/`presentation_style` 绑定到当前 `observed_aggregate`；宿主在数值与方法块内按表达目标渲染局部解释，只对已渲染绑定记覆盖。无旧需求时的“改成”不再制造替换项。取前轮聚合结果作重述时重建当前问题/需求包；显式空的本轮需求 ID 不引入旧表达。

Provider-disabled 正常 app 选 `control_route=local_http_api`，视觉上传、正文、刷新 oracle 为 `unassessed`。`tmp/r4m01style1` 的第 2 轮因词面覆盖失败而中断；`tmp/r4m01style2` 六轮完成但演练分类器读到上下文中的旧 B05 标记，仅业务样式生效。这两批均不算 M01 接受。修复演练分类器只读本轮输入后，完整新批 `tmp/r4m01style3` 使用端口 5242、监听 PID 25064、exec session 55679；启动/批前/批后健康均为 `ok=true, provider_enabled=false`。launcher SHA-256 `73B9DC7AEE85C11F8E8FD3521F02809BF9B0B599A61FDAEF8DECE27FD642EFFC`，已有 HTTP driver SHA-256 `1521D6272B358D432F8B7EE2A7C26BE0FD90CD7ECCFBCC774B4BCAF985ACFDBA`，结果 SHA-256 `97FB69DE964051D6EB1F80275E473092F67CC89AD91E7772265B40D232856EF8`。上传 `F-SALES.csv` 票据及文件 SHA-256 同为 `1e6629876a79225fceac0b2dc0f1d16071e532ca989b842c0489afc082f8e59d`。会话 `e772ae3cb7ea` 六轮均 completed、各唯一 `turn_end` 与持久状态一致、无 error event；19 条规范消息、6 个发布包、导出成功，服务已由原 exec session 停止。六轮均保留原始 12 行、派生 1 行、amount_sum=120、amount_count=12、方法及未知单位；业务、分析师、管理者、大白话四轮正文各不相同，第六轮回到技术方法表述。runtime 中 `forbidden_provider_transport` 为 0，本批 app 实际 Provider initiated calls 为 0。

**局部通过，不算 M01 完成。** 本轮包只有 `transform_data` 聚合行值、源/派生版本与方法；没有可比的下周窗口、成本或投放增量效果回执。B01 的有条件建议没有发布，B05 也无法保留未交付的触发/停止条件。原演练候选把 12 天总额 120 当作下一周阈值，现有自由文检查对该候选返回空问题，直接附回会误放。表达模板只能展示已证的事实与限制，不能代替结构化行动条件或开放语义审核。按同根因两轮不收敛规则，停止第三轮文案/词面补丁；后续先在现有 packet/`answer_bindings.v1` 裁决行动主张需要的指标、可比窗口、成本/效果输入与局部缺口，再以正常 app 复核。M06 计算与分层缺口也仍未通过。

本轮在诊断中有一次未显式传 stub 的默认 LiteLLM 分类器尝试，输出 LiteLLM 错误；它不属于上述 Provider-disabled app 批次，也不是自然模型证据。该尝试没有独立账本，不能从 app 的零传输记录推断其物理调用数。此后仅使用显式 stub/Provider-disabled 路径。

审查还发现聚合正文中的“投放/订单”适用于 M01，但对任意数据集会带入无来源行业语义；已改成通用对象/行动措辞，单位说明由实际聚合操作列名产生。该代码变化后的全新完整六轮 app 批次为 `tmp/r4m01style4`，端口 5243、PID 3816、exec session 39333 已停，launcher/driver 摘要同上，结果 SHA-256 `A83E50282EDE63DDDD8311463B101D0F8BBC01369B70981E2258A1C897E833B6`，会话 `7ffe6858fd5b`。六轮均 completed、各唯一 `turn_end`、无 error event、导出成功；每轮原始 12 行、120/12 与方法保持正确，业务/分析师/管理者/大白话四种原位表达不同，第六轮恢复默认技术方法；六份正文均无凭空“投放/订单”语义或跨窗口 120 阈值。批前/批后健康 `ok=true, provider_enabled=false`，runtime 禁止 Provider transport 0，本批 app 实际发起 0。视觉及自然模型仍未评估。此批仅证明表达局部组合与事实保护，不证明 B01 条件建议交付。

下一实现边界：在原 `answer_requirements` 保留 B01 `conditional_action` 子目标与本轮消息身份；在原 `answer_bindings.v1` 内给行动主张引用当前结果 claim、指标与单位、观测窗口和拟比较窗口、成本/效果输入及触发/停止条件。宿主先验证引用、版本、粒度、窗口可比性和输入齐备，再允许该主张进入正文；缺任一项时保留当前 `observed_aggregate` 与已核解释，把该子目标记录为未完成及具体输入缺口。现有 M01 `aggregate_observations` 没有这些窗口/效果字段，不能从 `amount_sum=120` 反推。开放行动语气仍需经独立校准的受限语义审核，不能由 `_answer_coverage_issues` 的字面命中或 `validate_final_narrative_issues` 的空数组授予安全。确认恢复的 M06 应复用同一个局部交付边界；无当前计算回执不得声称已算。这是下一结构实施入口，不是本批已交付能力。

最终代码定向回归 192 passed；新目录完整 E2 `tmp/r4m01stylefo2` 2907 passed、1 skipped、16 warnings。E2 只证明既有确定性/离线回归，不能替代 M01 条件建议、M06 内容、视觉或自然模型验收。

## R4.6 行动子目标的局部缺口（2026-09-27）

在原 `answer_requirements` 中接纳语义分类给出的当前用户原文 `conditional_action`，并在原 `answer_bindings.v1` 的当前 `observed_aggregate` 块中引用该需求。宿主只对已渲染、同快照且来源为本轮消息的块记录 `coverage_check=checked, answer_coverage=evidence_insufficient`；正文在聚合结果位置说明当前主张没有绑定可比窗口、成本及效果测量，无法给出有据的触发与停止条件。它没有把缺口记成 `answered`，也没有把候选中的“12 天 120 作为下周阈值”附回。正确聚合值与方法仍独立发布。此项是准确缺口交付，不是行动建议验收。

首批 Provider-disabled 正常 app `tmp/r4actiongap1` 选择 `control_route=local_http_api`，端口 5244、PID 24796、exec 17655 已停；launcher SHA-256 `220A399E42165EB15D2083C77B5843F56587782938187F7AF9C36CD2DCEF08FF`，既有 HTTP driver SHA-256 `1521D6272B358D432F8B7EE2A7C26BE0FD90CD7ECCFBCC774B4BCAF985ACFDBA`，结果 SHA-256 `06C3C7B0833DFFC3D73B6117BB3BE7BC23582A9CE8AB9D069B46372DCD1F024B`。会话 `f31bdbe967f4` 六轮均 completed/唯一 `turn_end`，B05 业务/管理轮有真实绑定缺口，B01 首轮没有：清晰复合请求被意图快速路径归为 `data_operation` 后直接返回，绕过语义输出拆分。这是批后统一诊断出的执行路由缺口，并非回执或上传问题。

修复保持快速路径的主意图、执行准备和确认决策；仅当正常 AgentLoop 已明确注入辅助客户端时，对清晰 `data_operation`/分析请求用现有语义分类器补取最多六个精确原话输出。无辅助客户端的默认 `plan_turn_intent` 仍不因此增加模型调用。`data_operation` 的原话输出也写入同一个现有需求通道；非法或非本轮片段仍被解析层拒绝。该候选改变了有辅助客户端时清晰分析/数据操作的调用数，未来任何真 Provider 批次要重新冻结并纳入调用预算，不得沿用旧 120-call 账本假设。

同为六轮 M01，演练 trace 的 `auxiliary_call` 由 R4.5 `tmp/r4m01style4` 的 17 次增至 R4.6 `tmp/r4actiongap2` 的 20 次；这是脚本客户端调用记录，只说明本地候选路径的调用增量，不是新真模型调用或其预算估计。

新身份完整 app `tmp/r4actiongap2` 端口 5245、PID 23668、exec 91616 已停；同一 launcher/driver SHA，结果 SHA-256 `E4268B7F1EDC0E5D152389E083B8ACC78AF0E13BEB44ECC49FA21700E5FCB00C`，会话 `751f52b41155`。批前/批后健康 `ok=true, provider_enabled=false`；六轮 completed、各唯一 `turn_end`、无 error event、持久状态一致，导出成功。B01 与 B05 第 2/4 轮的行动子目标均在各自当前包中记为 `evidence_insufficient/checked`，并在正文原聚合块给出具体缺口；六轮均保留源 12 行、派生 1 行、120/12、方法和未知单位，无“低于 120”阈值。runtime 禁止 Provider transport 0，本批 app 实际 Provider 发起 0；HTTP 路线的上传 picker、视觉正文与刷新未评估。

剩余能力缺口明确：本批没有可以绑定的可比未来窗口、成本及效果测量，所以无法形成原 M01 所求的有条件行动主张；B05 中未明确复述建议的轮次也尚未由稳定任务身份继承该子目标。局部缺口不能冒充原 M01 建议已交付。M06 的确认后计算与分层内容仍需独立实现和正常 app 验证。

R4.6 定向 344 passed；最终代码在 `tmp/r4actiongapfo1` 完整 E2 为 2909 passed、1 skipped、16 warnings。测试通过不改变上述 M01/M06 产品判据。

## 当前 HEAD 的 M06 执行能力复核（2026-09-27）

在 `31ed279` 用原有 M06 HTTP 控制器新身份复跑：`control_route=local_http_api`，`tmp/r4m06audit1`，端口 5246、PID 24388、exec session 96212 已停；launcher SHA-256 `220A399E42165EB15D2083C77B5843F56587782938187F7AF9C36CD2DCEF08FF`，driver SHA-256 `9819C630E84F1C562439E1D53E61CB2EBD0819D9F1FC8E9477B0881CA1768826`，结果 SHA-256 `D48E6FDEB31110F483F8B4445A589807B1E67E6739ED0C716BDB87C5E9F17384`。缺失会话 `514e0872ada6` completed；成本会话 `6c044c2029c8` suspended，选择“代金券及渠道成本”后同会话恢复为 failed。三轮各唯一 `turn_end` 与持久状态一致，两会话导出成功，健康 `ok=true/provider_enabled=false`，runtime 禁止 Provider transport 0、本批 app 实际 Provider 发起 0；视觉未评估。

恢复路径带原任务与确认回答进入原 `_loop`，但演练模型给出散文而未调用数据工具；已有一次定向恢复提示后仍无计算。因此成本会话保持 0 计算回执、0 发布包，原话结果/缺口需求 2 条仍在，宿主在任何旧包复用之前拒绝 `confirmed_result_without_receipt`。这与 `r4guard2/r4guard3` 同根因且连续不收敛。设计裁决：维持该失败边界，不再加第三轮意图词、模型提示或由宿主新建计算 planner；不能把“确认已复用”当作订单总额、成本或净收益交付。若未来以能够执行工具的模型恢复，仍须通过当前回执/版本/需求绑定和正常 app 完整路径；真模型能力评价走独立冻结授权。R5 可先处理不依赖此能力的旧门，M06 原内容 DoD 留为未满足。

## `ec4a595` 后的 M01 行动条件复核（2026-09-27）

M06 在 `ec4a595` 已由同一正常 app 路径完成“确认后聚合值 + 未算净收益”的局部交付，详见独立 M06 审计；这不改变 M01 行动建议的证据门。对最终代码前一个完整六轮 M01 包 `tmp/r3m01unified2/sessions/c52c8ee9b8c9` 只读复核：每轮可用来源仍是 `transform_data` 与 `record_evidence_record`，聚合仅有 `amount_sum`、`amount_count`，一行派生表；`publication_scope.v1.observation_window={}`，没有同口径第二窗口、成本或行动效果测量，也没有图表产物。B05 追问的原行动需求经 `825376b` 已稳定留在 packet，并获 `evidence_insufficient/checked`，所以“需求丢失”不再是本轮主要根因。

在这个输入上，基于 12 天的 120 设下一周触发/停止阈值不可核，且不能将未测成本或效果当作已知。宿主可以保留 120/12、方法、范围限制和具体补证步骤；若要把未来同口径窗口的测量条件写成建议，应明确它是**待获取证据后的条件方案**，不能标成当前已验证的行动规则。原 M01 所要求的有条件建议、指标和停止边界尚无可绑定的正向条件回执；不再为这一个夹具加词表/模板来把 `evidence_insufficient` 改名 `answered`。下一结构实施需先以正向可比窗口和成本/效果输入建立独立 oracle，定义指标关系、窗口长度/粒度/版本与停止边界，再让候选 action 引用既有 `answer_bindings.v1` 并由宿主核封闭关系；开放行动语气仍需 R4 的证据绑定语义审核与校准。若没有此输入或审核能力，保持局部结果并明确原 DoD 未满足；不把该缺口推给 R5 删除旧门。
