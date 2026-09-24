# 可信发布重置：Phase 5/C Shadow 设计与跨历史离线校准

日期：2026-09-24。进入 HEAD：`main@84ab7904f7aeedb3af7374267d58bc4ac2cf354c`，工作树无列出的改动（Git 对 `.pytest_cache` 有不可读告警）。用户只批准先做设计和跨历史**离线**校准；本记录不启动审计调度、不调用模型/Provider、不改变正式发布或 Phase 6 D。它继承 [三份原始需求](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md#1-三份原始需求仍是上位约束)、[Phase 5 首切片](2026-09-23-trust-reset-phase5-shadow-protocol.md)及 [Phase 6 四门](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md#phase-6受限处置与一次定向修订)，不把 C 的设计当作 C 的真实 Shadow 验收。

## 1. 本阶段三联门与目标

- **RED**：VP 要求有据的解释/条件建议且不误删正确边界，IC 不允许把方法许可变成业务暂停，CP CR03/CR07 要求子问题可信覆盖和独立正确内容保留。R11/R4 M02 有正确边界误拒，R16 M05 有已通过的多轮价值，R4 M03/M04 有产物/假设关系，R14/R16/R21 又有算术、来源、版本、单位、任务权威反例；中止的 R4 不可独占 oracle。现有 `validate_shadow_audit` 的 `claim_evidence_bound` 只验证引用归属：用合法 M02 typed packet，构造 `remove` finding 并把理由改成无依据的“已经留出回测”，结果仍是 `status=valid / binding_status=claim_evidence_bound / suggested_action=remove`，`simulate_shadow_actions` 给出 `claim_m02_d30: remove`。**实际发布影响为 none**。这是未来若把引用合法误当语义真实，就会误删正确 claim 的当前可复现 RED，不是一个新的自然模型调用结果。
- **结构化替代物**：沿用唯一 `answer_bindings.v1`、当前 publication packet、规范历史、既有工具回执与 `publication_audit.v1`；设计一个由宿主确定的只读 `audit_view`，包含同快照 claim ID/类型/状态、可核验 evidence refs、已接受答案的定位、原始用户子问题的可验证来源片段及明确的未知项。审计只对**可定位的开放语义**给出 finding；引用合法与语义正确是两个独立判定。宿主数值、单位、版本、执行状态、具体缺口和 `answered` 权限不交给审计器；不能凭模型自述或一个同名标签补出历史缺失的意图链。离线校准分别记可评估、误删、漏检、不可评估和理由无法证实，不把不可评估计入通过率。
- **未来退役的旧门**：有一条有效 binding 就让整篇自由散文获事实权威、对开放语义反向解析词面并整篇阻断，是逐族退役目标；回执/数值/版本/确认硬门保留。本轮**不退役**任何门，也不把 `overall=pass`、结尾免责声明或审计理由变成新总审批门。

## 2. 实际历史可校准性，而非测试夹具代替真实场景

只读检查下面八个已知会话的 `analysis_state.json`。`packets` 为归档中实际持久化条目数，`typed` 是其中同时有 `claim_id/claim_type` 的 `answer_bindings.v1` block 数，不把最终自然回答中的 JSON fence 当成当前 parser 已验收绑定。

| 分层样本 | 实际 packet / typed | 历史观察及语义目标 | 当前 Shadow 可评估性 |
| --- | ---: | --- | --- |
| R4 M02 `c3f4c190384c` | 0 / 0 | 两份正确的未验证 D30 情景候选被旧散文门误拒；R4 中断 | 无当前 packet/typed，不能直接计算审计误删率；只能做内容等价 typed 对照，另标非真实重放 |
| R11 M02 `72b58ee16e69` | 0 / 0 | D7 正确、D30 不预测的边界应保留 | 同上；且用户中文子问题不能由英文列名推断 answered |
| R4 M03 `50e734df7af7` | 1 / 0 | 六来源表/图和旧回答里的 `answer_bindings.v1` 种子；压缩摘要失实 | 旧终局 packet 无当前 typed block；图表存在不证明业务比较结论 |
| R4 M04 `f2db8a75de3d` | 2 / 0 | 有结构化 plan/证据/假设关系；旧解释需要版本和关系边界 | 关系可供宿主审计，旧正文仍不能成为 typed finding 的可行动对象 |
| R14 M05 `809883a02e5a` | 6 / 0 | `mean=10、std=0` 却写“CV 分母为 0”，还推断样例/账本来源；首轮求总额的提示/oracle 曾不完全对齐 | 算术由宿主确定性复核，来源开放语义可作 Shadow 风险分层，但旧答案无 typed 锚点 |
| R16 M05 `58da9082dc02` | 6 / 0 | 完整真实批次中 M05 已通过，12/120、未知单位、窗口和多轮方法上下文必须避免误删 | 对旧终局 packet 人工提交一个合法 digest、但虚构 `claim_m05_total` 的 `remove` finding，现有 validator 实测 `valid / unbound_advisory / advisory_only / publication_effect=none`；这是协议负例，不是历史模型输出 |
| R21 M02 `8885cd032ffe` | 1 / 0 | scope 权威降级，不能让正确 D1—D7 边界被 task/scope 全局吞掉 | 无 typed 可定位对象；旧失败已另有本地修复，不能重新记作当前 RED |
| R21 M04 `ef2694420c2e` | 0 / 0 | 未完成 task 不阻断独立可信 claim，同时保留显式竞争假设 plan 审计 | 无 packet/typed，不能计算 finding 质量；不能新建第二 planner/journal |

这八个**有目的的历史分层样本**合计 16 份归档 packet、0 个现行 typed block；不是仓库全体频率，也不是当前 HEAD 的真实模型回放。R7/R8/R10/R19/R20/R21 的提交、真实批次及既有修复继续是校准背景；R16 M01 无据来源/M06 缺失归零、R16 M03 “同比例”误判又是不同失败机制，不能拿 R4 一个误拒推导总体误报率。当前另有**人工构造的**有效 binding＋独立无据 99% 反例，可信核心能去掉 99%，但旧历史正确内容尚不能等价重建；两侧须分别计数，不能互相抵消。

## 3. 离线协议复核结果与 C 的输入边界

现有 `publication_audit.v1` 先检查 packet/answer digest，随后对有效 typed claim 和当前 fact/derived/receipt refs 做归属校验；外来/无引用 finding 降 `advisory_only`，`reason_untrusted` 不进入正文，`overall` 不影响发布。`simulate_shadow_actions` 是纯离线预览、最多一个定向修订 ID；它**会**对引用合法但理由错误的 `remove` 做模拟，这不能作为 D 处置准入证明。审计器尤其不能用自己的 finding 或理由把 `unassessed` 升为 `answered`，也不能撤销确定性失败。

拟议 `audit_view` 是**设计目标，不是本轮新增的运行时对象**：

1. 输入由宿主从同一个已验证 packet、正式 accepted candidate 和 canonical history 产生，并对 view/prompt 版本、packet/answer/history digest 做确定性标识。当前尚未持久化离线投影到真实旧 session，也没有自动产生单位确认记录；view 中这些项必须显式标 `unassessed/not_confirmed`，不得回填旧文本。
2. 每个可审核单元保留 `claim_id`、`claim_type`、精确答案定位和**该 claim** 允许的 fact/derived/receipt refs；用户子问题来源须有宿主可核验的消息/span 或明确 `unassessed`。粗粒度 `intent.py` 只作路由，不授权跨轮继承；旧 `answer_bindings` 的任意模型标签不授权事实身份。
3. 审计输出继续受 `publication_audit.v1` 的封闭 dimension/action 和引用限制。`reason_untrusted` 仅供离线人工比较，不能复制为披露或新事实；即使引用合法，也仅表示 finding 的**作用域**可定位，语义真实性与处置是否安全仍需独立校准。缺 claim/source 锚点的开放语义意见只能 advisory，不能借 `missing_requirements` 自由文本绕过绑定。
4. C 即使以后运行真实 Shadow，也默认不改正式可见答案；故障/超时/无可评估 claim 只记录 unavailable/unassessed，不回退到未经校验原文，不暂停正常确认流程。统一现有 Provider 账本与预算，不增第二调用路径、planner 或隐藏审计调用。真实调用须另冻结精确 commit、模型、endpoint、提示/fixture/oracle digest、矩阵、预算、账本并获用户显式授权。

## 4. 跨历史离线校准方案与本轮诚实分母

校准不是让某个测试文件规定产品行为。先冻结**机制分层**：正确观测/否定外推（R11/R4 M02）、多来源/产物（R4 M03）、版本/竞争解释（R4/R21 M04）、多轮方法与未知单位（R16 M05）、错误算术/来源/缺失归零（R14/R16）、有效 claim 旁独立无据 99%。每条保留真实会话/提交/收据定位、已知正确或错误的**具体断言**、宿主可证实的范围、旧回答不可直接迁移的原因；新 typed 对照必须标明“内容等价构造”，不能冒充旧自然模型输出。

对未来同 packet 的审计回复，逐 claim 记四个不同分母：①可定位且宿主确定性通过的 claim 数；②有人审查过语义 oracle 的 claim 数；③已知应提示的开放语义风险数；④已知正确且可能被误删的 claim 数。分别计算风险召回、误删/过度降级、动作定位准确、独立可信内容保留、不可评估率和超时/成本；`overall=pass` 不能替代任何分项。当前八个历史样本在**现行 typed 审计质量分母**里是 `0/8 可直接评估`，不是 `8/8 通过`，也不能算模型漏检。离线 M02 构造例只能证明合法引用可能带错误理由、以及发布影响仍为 none；不能估计自然模型真实误删概率。

本轮校准结论：C 的**设计与历史可评估性审查已做**；当前还不能开始声称真实 Shadow 质量。下一个实现门不是再堆 `unassessed` 选择器，而是先为真实候选建立可验证的 claim/用户子问题定位及最小 `audit_view`，并针对上述双向样本验证不丢 R11/R16/R4 的正确价值。若这一步需要模型判断开放语义，只能在显式 C Shadow 授权和账本内执行；若会改变正式发布，属于另行裁决的 D。Phase 7 仍须在每个旧门有结构所有者和双向回放后逐族退役。

## 5. 真 Shadow 进入门（本轮不执行）

在写任何运行时代码前，先冻结 `audit_view` 的字段/大小限制、独立版本化审计提示与输入 digest，以及历史校准集的真实来源、内容等价转换、人工 oracle 和四个分母。首个代码 RED 应证明：无显式开关、无同快照有效 claim、缺规范历史/证据或预算不足时**零审计调用、零发布影响**；获准开启后的客户端错误或超时只记录已发起调用及不可用状态，**零额外重试、零发布影响**。有开关时也只走现有 LLM 客户端/统一调用账本，不因审计增加隐式重试。模型输出经当前 `publication_audit.v1` 校验后，只存 diagnostic 和不可用原因，不能执行 `simulate_shadow_actions` 的建议，更不能让 `overall` 批准正文。不得把 R14 的宿主算术问题送到模型当开放语义裁决。

离线假回复只能验证故障/身份/限额机械门，不能证明模型语义能力；真实 Shadow 质量与成本仍需另一次精确 Provider 冻结和用户授权，并在不改变用户答案的前提下完整比较正确 claim 的误删意见与已知风险的漏检。若可行动样本仍为零、审计只会产出引用合法但无可裁决语义，停止 C 的运行时接线并回到 A 的真实身份生产者评审；不能为了走阶段而开一个空耗调用的新门。

证据等级：本机只读历史检查、现有纯函数离线调用；真实 Provider initiated 0，无 E3/E4/staging/production 结论。本轮未改源码、测试或正式发布。

## 6. 用户批准后的最小只读 `audit_view` 切片

从 `main@603dc115cc74664c1f062ca81547b8fbefb0a3ac`、根工作树无列出改动进入。范围仍为纯离线、默认关闭；没有把视图接入 `AgentLoop`、模型 prompt、Provider、发布或第二账本。实施前 RED：新增测试第一次收集时 `ImportError: cannot import name 'build_offline_audit_view'`。结构替代：`publication_audit.build_offline_audit_view` 只接受现有 `state.publication_packets` 中唯一的已提交 `pub_` 包，复核其 `ps_`/`pub_`/正文 SHA、当前规范历史的消息数与 SHA、同一助手消息的 packet/正文身份，以及包内全部来源与既有工具回执的 ID/工具/结果 SHA。然后沿用现有 typed binding 校验器及宿主 renderer，在**已接受正文**中寻找唯一的同文重建片段，返回 answer span、同 claim 的 evidence refs 和版本化 view digest；用户需求只在其已存 source ref 与规范历史中唯一逐字匹配时标 `verbatim_only`，不推断后续改写继承或 `answered`。无绑定、损坏身份、回执漂移、片段重复均无可行动 claim；返回始终 `publication_effect=none`。

这是一种**唯一内容重建定位**，不是新持久化的 renderer 插入位置收据；字段显式命名 `location_status=unique_host_reconstruction_match`。它依赖已提交包和助手消息的宿主契约，不能独立证明任意旧自然文本哪几个字节最初由占位符插入。独立自由散文（包括有效 claim 旁的无据 99%）不被赋予 claim 权威，视图标 `unbound_prose_status=not_audited`；这并未修复正式发布误放，未来 D 仍须确定性可信核心/发布策略裁决，不能把未进 view 的散文交给 Shadow `overall` 洗白。跨历史只读调用归档 R16 M05 的当前旧终局包，得到 `status=unavailable, claim_count=0, publication_effect=none`，与上文八会话 0 typed 的盘点一致；它不是 R16 价值保留通过。

将来要退役的旧门仍是“一个有效 binding 让整篇散文可信”和开放语义词表硬拦截；本切片未退役。下一门若要让真实 Shadow 使用 view，须先解决真实候选 typed 覆盖及上述定位的插入来源证明/等价边界，再单独冻结版本化提示、账本与预算；未经新精确冻结和用户显式授权，绝不发真实 Provider 调用。定向 audit-view/原 Shadow 协议/Phase 6 模拟测试 **26 passed**。源码与测试冻结后，fresh `tmp/tprb36` full-offline **2959 passed、1 skipped、16 warnings、0 failures**（435.29s），JUnit `tests=2960/failures=0/errors=0/skipped=1`、SHA256 `107BFC5CF046543704D01376CB4BD421AC6B746467B61FB54A1C5710AA91A073`；runner `provider_calls=forbidden`、真实 Provider initiated 0。仅 E2，不是新 HEAD 的完整浏览器 E3 或真实 Provider E4。

## 7. 当前发布候选的宿主原位渲染追踪（2026-09-24）

这一切片从 `main@0fd91d1818c04ea8f06c0503c0e646214433f594` 进入；仅原位渲染、同一已接受 publication packet 的审计元数据和默认无人调用的离线视图受影响。先有的 RED 是审计视图 §6 只能用全文唯一同文重建：两个独立 claim 渲染出相同文字时均无法定位；单个同文匹配也不能证明文本确实来自占位符替换。新增测试首次收集因缺少 `render_bound_claims_with_trace` 报 `ImportError`。这不是 R4 单例的词句修补：R11 正确 D7/无 D30、R16 已通过 M05、R4 M03 多来源/M04 关系和有效 binding 旁独立无据 99% 仍作为双向历史校准背景，旧自然会话没有新 trace，不能倒填为当前 typed 通过。

结构替代：沿用 `answer_bindings.v1`、现有 renderer、`pub_` packet、正文 SHA、规范历史和回执结果 SHA。宿主在替换每个已验证 typed 占位符的**当时**记录 claim ID、Python 字符串起止位置及渲染片段 SHA；组装结果须与原 renderer 字节相同。trace 连同同快照 digest/最终正文 SHA、自己的规范 JSON digest 写在同一个已接受 packet，不增加账本、模型调用或发布文本；后续候选会清除旧 trace。离线 `audit_view` 仅当已提交包、规范助手消息、回执和 trace 同时闭合时使用该位置；同文两处可区分，缺失、旧包或篡改退回 unavailable。用户原句仍只到 `verbatim_only`，覆盖和语义均 `unassessed`，`publication_effect=none`。恢复用的无 binding 部分答案目前没有可行动审计 trace，这是明确的可评估率缺口，不能补猜。

将来要退役的旧门依然是“一个有效 binding 授权整篇自由散文”及开放语义词表硬门，**本切片没有退役**；数值/版本/单位/回执硬门继续保留。尤其该 trace 只证明 typed 部分的插入来源，不审核旁边的 99%，不证明历史内容等价、真实 Shadow 质量或 Phase 6 A/D 可以切换。下一门应先用真实场景而非只用合成夹具校准 typed 覆盖、旧正确价值与独立误放，再冻结 Shadow 提示/输入 digest/统一预算账本和无调用故障门；如需真实 Provider，另向用户索取新精确冻结后的显式授权。

本切片定向 audit-view/Shadow 协议/Phase 6 模拟 **28 passed**；fresh `tmp/tprb37` full-offline **2961 passed、1 skipped、16 warnings、0 failures**（478.64s），JUnit `tests=2962/failures=0/errors=0/skipped=1`、SHA256 `CDBFEC1E100026895F0A3F43DE8FF44C40591331AC73E1568EC5DBBC64597B1E`。入口声明 `provider_calls=forbidden`，真实 Provider initiated 0；未运行本 HEAD 的 E3/E4、未切正式发布策略。

## 8. E4 后的跨历史可用性复核与下一实施裁决（2026-09-24）

本节在 `main@5b3c75c57c355d2d207acbc549163134e8870c9b`、工作树无列出改动时只读复核，不作新的 Provider 调用或发布策略变更。对照 §2 的 R4/R11/R14/R16/R21 历史分层，以及已完整执行但验收失败的 `tmp/trust-reset-p08-real-20260924-r1`，不能用最新中断 R4 或最新失败 M02 单独定义产品。

| 当前 E4 会话 | 已提交 publication packet / 现行 typed block / answer requirement | 可保留价值与不能升级的边界 |
| --- | ---: | --- |
| M01 `126c9f6a9d17` | 1 / 0 / 0 | `preview_data`、`describe_dataset`、`detect_data_quality` 有结果；无 typed claim/需求身份，不能由工具存在断言已回答全部问题。 |
| M02 `ffb95bc5a766` | 0 / 0 / 0 | 候选答复试写 `answer_bindings.v1`，但使用 `bindings` 而非 `blocks`、`C1/C2` 而非现行 claim ID，且 `fact_refs`/`derived_refs` 均空；单位未确认却呈现百分比。只放宽 JSON fence/parser 不会补出证据和单位授权。 |
| M03 `06a81b4d660c` | 1 / 0 / 0 | 同 packet 包含六次 `compare_periods` 和 EvidenceRecord，可供离线宿主重建两日比较；现行自然正文仍有错误“七天跨度”，成功发布不代表 typed 保护。R4 M03 曾在普通 JSON fence 中自发写出 `blocks + exact_text + fact_refs + derived_refs` 种子，但旧终局 packet 只选择 EvidenceRecord，现行 typed 计数仍为零。 |
| M04 `d4776ba7b746` | 0 / 0 / 0 | 有三条 EvidenceRecord，但真实假设关系未闭合；新 Phase 4 关系门尚未经过本会话重新运行，不能倒填通过。 |
| M05 `e7a6e6b17ee8` | 6 / 0 / 0 | 多轮 `run_python`/EvidenceRecord 结果和方法上下文仍须与 R16 已通过 M05 的 12/120、未知单位、窗口一起检验价值保留；不能由 packet 数量推断需求覆盖。 |
| M06 `4656c27b3f5a` | 1 / 0 / 0 | 数据概览回执可用，但单一路径旁出现额外路径；无 typed 对象可供当前 claim 级审计定位。 |

上述四个成功发布场景共有 9 份 packet、0 个现行 typed block，六个 E4 场景均为 0 条宿主持久化 `answer_requirements`。这是**刻意抽取的本批次**，不是全体模型输出率；加上 §2 的八个历史分层会话也不能合算为自然模型能力的总体统计。R4 M03 的旧种子说明可复用现有通道，不说明当前 schema/回执引用已通过。R11/R16 的旧正确边界、R4 六来源/假设关系与独立无据 99% 仍须分别核对正反损失。

另外，Phase 4 新门已能拒绝错误假设 ID、指标不在目标内、提议方向与 EvidenceRecord 测量方向不一致等关系；但 `hypotheses._validate_relation` 的方向来自记录内 `measurements`。`record_evidence_record` 对同轮回执、版本和结果摘要做绑定，`bind_computed_statistics` 投影工具结果，却**不逐值证明模型填写的每项 measurement 等于原工具数值**。因此“关系结构有效”与“测量值经回执复算”是两个不同断言；M04 的正式支持/反驳状态不能被当作后者已闭合。当前离线 A 投影仅对受约束的同指标 `compare_periods` 描述关系做过宿主复算，不可反向概括到所有正式 EvidenceRecord。

本轮的三联门：**RED** 是自然 E4 真实候选有成功 packet 却无可行动 typed claim/需求身份，M02 的失败又同时缺 refs/单位授权；R4 旧种子并未改变这个结论。**结构化替代物**应继续使用同一 `answer_bindings.v1` 与既有回执，在离线双轨中先证明一个跨历史可复核的宿主事实/具体缺口/方法或产物单元能保留正确价值且排除无据旁述；显式需求覆盖没有可核验身份时保持 `unassessed`，假设测量仅在原回执同身份复算后才能称“数值证实”。**拟退役旧门**仍是“一条 binding 授权整篇自由散文”以及相应散文词表硬判；本节没有退役任何门。

后续实施前需与用户裁决的是优先级与语义所有权，而不是添加 `blocks` 同义字段、更多 `unassessed` 选择器或新模型总审批：建议暂停新默认关闭协议字段，先在 A 范围内选取跨历史有真实工具身份的最小可信核心价值切片，保留未知覆盖；同时把 Phase 4 的关系状态明确分成结构有效与原始数值已证实。若原始 VP/CP 要求自然中文多子问题都能被证明 `answered`，当前 `answer_requirements=0` 的真实路径不能完成此目标，必须先确定可核验的上游语义身份生产者及其授权边界。C 的真实 Shadow 调度若仍没有可行动 claim，只会空耗调用；D 默认切换和 Phase 7 退役均不因此获准。修改正式关系状态、引入上游语义生产者或改变发布默认策略，须先讨论具体正反候选及原始需求取舍。

## 9. 已批准的 A/M03 价值预览与 Phase 4/M04 数值门（2026-09-24）

用户批准 §8 的最小方向：从 `main@3539067b5bb2a020fcf0b5615867b25f6e063fc5`、无列出改动进入；不把最新 E4 当唯一 oracle。对照 R4 的六来源 M03/M04、完整 E4 的 M03/M04、R11 正确 D7/无 D30、R16 已通过 M05，以及有效 binding 旁独立无据 99%，本次只解决两种可复核结构缝隙。历史自然答案仍没有当前 typed block/要求身份，不能以构造正例冒充它们已被重放。

| 切片 | 实施前 RED | 结构化替代及正反边界 | 旧门状态 |
| --- | --- | --- | --- |
| Phase 6 A：M03 时段数值 | 六份真实 `compare_periods` 回执已有两期事实，默认关闭的可信核心却没有通用数值行；新测试先因缺 `comparison_rows` 失败。完整 E4 成功正文还在正确两日数据旁误写“七天跨度”。 | 在同一离线 publication packet 中，复用现有 `comparison` binding 的事实校验，复核被选中回执的结果 SHA、单数据集身份、当前 Workspace 实际帧指纹、两期窗口/行数/原始数值，再给出逐来源原始尺度、差额与无量纲相对变化；不跨源求和。六源和伪造/过期回执有正反测试。`accepted_claim_ids=[]`、覆盖 `unassessed`、单位未确认、`publication_effect=none`；R11/R16 的缺失价值和正式独立 99% 误放**未**因此修复。 | “一条 binding 授权整篇自由散文”及词表硬门仍是未来退役目标；本切片没有触碰正式发布。它不是增加第三张来源专用表，而是既有时段比较事实形状的离线投影。 |
| Phase 4：M04 假设关系 | 模型在 EvidenceRecord 填入的测量值和方向，旧关系校验可据此把结构正确的关系升级 `supported/refuted`，未与原工具值逐项比对；新增模型自填数值 RED 先失败。 | 正式刷新只在同轮、同数据版本的既有 `compare_periods` 差值或 `analyze_time_series` 斜率，经原回执 detail 的 digest/数据身份核验且与模型测量数值相符时，允许描述性关系变成已验证；因果/显著性标签不凭描述工具结果升级。错误数值、过期数据、缺回执均保持未证实。真正假设 ID 下的未证实关系候选算作**已审计但未闭合**，允许任务交付 `inconclusive`，避免无穷修复；错 ID/指标/方向仍不算。 | 退役的是“模型自填 measurement 可单独授权关系状态”的隐式门；不是退役显式竞争假设的 plan/关系审计，也不是增一个模型审计审批。 |

最初 fresh `tmp/tp4a3` 全量离线收据为 **2969 passed/1 skipped/3 failed**：三处旧 H11/B04 生命周期夹具没有原始工具回执，却预设关系已获 `supported`，与新证据前提冲突；此收据不算最终通过。生命周期夹具随后显式注入宿主已验证测量，保留其状态/失效断言；真实回执 digest、版本、数值、因果过度声明另由独立测试验证。最终定向 **87 passed**，fresh `tmp/tp4a4` full-offline **2972 passed、1 skipped、16 warnings、0 failures**（441.81 秒）；JUnit `tests=2973/failures=0/errors=0/skipped=1`，SHA256 `4D2ED505DEC58C9C3929EC6900983E7389B50C4946FB1F00952A86356F576547`，runner `provider_calls=forbidden`、真实 Provider initiated 0。两次收据的先后和失败前提都保留，不能择一个结果隐去。

证据仅 E2：没有在新 HEAD 执行完整 E3；上一次官方 `iab` 桥接在矩阵前失败，不是本次功能场景结果。没有新 E4；旧真实 Provider 批次的授权已消费，旧候选仍不能倒填 typed/需求身份。Phase 5/C 真 Shadow、Phase 6 A 的跨 R11/R16 等价价值、B 的受限处置、D 默认发布与 Phase 7 逐族退役均未完成。下一步仍须以跨历史双向分母检验可信核心能否同时保留有用分析并排除旁侧无据结论；若必须改变正式策略或引入语义身份生产者，先呈报取舍、另行裁决。不要为使 E4 M03 的“七天跨度”测试变绿而加中文关键词，也不要让 Shadow 审批整篇散文。
