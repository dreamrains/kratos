# 需求对齐与必要澄清：开发设计

日期：2026-09-10｜版本：1.2｜状态：**设计已随 IC0—IC3 合入 `main`，IC4 本地验收通过；IC5 真实 Provider 批次已执行但未通过**。

关联：[计划](../plans/2026-09-07-intent-clarification-plan.md)｜[验收](../validation/2026-09-07-intent-clarification-acceptance.md)｜[P08 问题记录](../validation/2026-09-07-p08-browser-validation-issue-record.md)｜[诊断](../../audit/2026-09-07-intent-clarification-diagnosis.md)。下文逻辑字段必须在 IC0 映射到目标分支现有接口；不是现有 API 的声明。

## 1. 保留的架构与问题边界

保留 AgentLoop、AnalysisSessionState、工具 registry、QuestionCandidate/QuestionPolicy/ConfirmationService、事件存储、Flask/SSE、既有数据/证据/发布验证。沿用现有计划、步骤和数据身份，不新造并行任务系统。

拆开三件不同的事：

1. **计算能否执行**：由数据、方法适用性、工具参数、执行预算和权限决定。
2. **业务口径是否明确**：由请求、数据解释、适用范围内的历史决定和明确默认决定；无法确定且影响结果时问用户。
3. **结论能说到哪一步**：由收据、证据、识别设计、观察/验证范围和发布检查决定。

用户批准方法不能使缺失字段出现，也不能把相关性升级为因果。模型比较、回归或分类计算本身无需人为批准；真正的业务语义缺口继续阻止依赖该缺口的解释。

## 2. 当前入口与调整责任

| 模块/符号 | 已有行为 | 目标职责 |
|---|---|---|
| `method_playbooks.select_playbooks` | 长度达到 8 先尝试 LLM，失败后关键词回退 | 保留调用顺序/预算；记录来源和理由；区分整体目标与辅助指标 |
| `apply_selection_to_state` | 模板 requires_confirmation 加入 pending | 方法模板只提出分析能力/数据要求，不直接签发通用审批 |
| `question_need_detector.detect_question_need` | 文件、方向、字段、高风险词、时间、指标六类判断 | 每个问题都对应实质决定；去掉仅凭高风险类别的强制审批；查明已有值与影响 |
| `analysis_entry`、`confirmation_policy` | pending 优先限制分析/推荐 | 只消费仍有效的必要决定；排除已退役的通用审批，保留真正依赖 |
| `AnalysisFlowController.is_capability_blocked_by_confirmation` | spec 批准前封锁四类能力 | 不以方法批准位封锁安全计算；继续遵守实际数据/权限/未解决语义依赖 |
| `tools/interaction.ask_user_question` | 直接抛出 UserConfirmationRequired | 仍提供单/多问题工具；携带可校验的决定上下文，不能仅自报“必须问” |
| `confirmation/runtime`、`policy`、`service` | 构造候选、策略判断、状态和恢复 | 共用同一决定语义、范围绑定、复用与事件兼容 |
| `loop` 同步/流式/恢复路径 | 假定创建或复用后一定取得 record | 完整处理非阻塞 advisory/rejected 与已解决 reused，不把它们转换为异常或再次悬挂 |
| `workflow_projection`、任务状态 | 保存步骤 confirmation_policy | 元数据不等于逐步骤执行门控；不引入新的“模型执行审批” |
| 提示/加载工具/registry 恢复文案 | 存在“异常/工具失败就请求用户”的指导 | 问业务未知；可自行诊断的技术错误优先依现有恢复路径处理，不把排障转嫁给用户 |

最后一行需要检查 `agent/prompts.py`、`tools/data_io.py`、`tools/registry.py` 及 `project/skills/full_report/SKILL.md` 的产品内提示一致性；这里只是待修改的项目文件列表，不是在本规划任务调用该技能。

## 3. 决定上下文与宿主校验

建议在现有候选/record 的 `resolution_params` 内使用版本化的决定上下文，尽量不扩张顶层 schema。IC0 冻结确切名称并验证 round-trip 与旧记录兼容。

| 逻辑内容 | 数据来源与用途 |
|---|---|
| decision_kind | metric_definition / time_window / file_scope / field_semantics / goal_choice 等；不得使用“高风险方法”作为充分理由 |
| subject_ref | 当前任务/子问题、指标或字段的稳定身份；优先复用既有 plan/step 身份 |
| missing_value | 究竟缺哪个业务值，不能只有“请确认方法” |
| known_values / consulted_refs | 已从当前请求、受控数据说明或有效回答得到什么；引用宿主能解析的来源 |
| affected_operations | 哪些计算、解释或输出依赖该值；不能默认所有工作都受影响 |
| alternatives / impact | 不同合理答案如何改变分母、窗口、数据范围或结论；无需捏造未计算的数值 |
| scope_binding | session、任务、相关 dataset/version、相关字段、时间/人群/指标/假设范围；只能由宿主解析 |
| default_resolution | 默认值、依据和适用边界；模型自报 safe_default 不具备放行权 |
| decision_revision | 业务语义决定的修订身份，独立于问题显示文本和消息计数 |

当前 `QuestionPolicy` 对 truthy `safe_default` 可直接降为 advisory；新接入不能直接信任模型填入的该字段。宿主先验证默认是否来自用户明确要求、可确定的表结构/已确认数据说明或明确可接受的探索口径。排除缺失值、选择分母、把 0 当未观测等影响业务含义的处理，不能仅因计算方便就成为默认。

自然语言语义无法全部确定性证明。模型可提出解析和候选，宿主校验已知身份、值域、作用域、依赖与事实。复用现有语义调用预算；不新增“审问另一个 LLM”来证明必要性。

## 4. 统一决策流程

在所有生产者进入持久确认之前执行：

1. 解析当前请求和可信数据范围；保留否定、整体目标、显式子问题和禁止事项。
2. 查找请求中已给出的值、有效历史回答、当前相关数据说明。不能把没有搜索到的信息直接说成用户未提供。
3. 判断是否存在具体未决值，且不同答案会实质影响当前任务。如果只是方法名称、技术工具选择或可自行恢复的错误，不产生确认。
4. 判断是否存在已验证适用的默认或可清晰标注的探索分支。不得把关键缺口强行解释成 ready。
5. 对确需用户判断的业务语义创建具体候选，并以范围绑定检查已解决决定的复用。
6. 数据/方法本身不支持时，给出缺口并继续独立可行部分；用户确认不能越过该限制。

| 策略结果（逻辑） | 用户可见行为 | 现有机制接入 |
|---|---|---|
| proceed | 执行，有必要时披露已采用口径 | 不创建确认记录 |
| advisory/default | 非阻塞说明假设/限制，继续可行工作 | `ADVISORY`，返回明确工具结果或内部说明 |
| reuse | 使用仍有效的业务答案 | `REUSED`；恢复答案，不重新展示 resolved record |
| clarify | 展示缺失决定及具体选项 | `CONFIRMATION`；现有事件/暂停/恢复 |
| unsupported/missing_data | 请求具体所需数据或解释当前能力边界 | 沿用数据要求/分析入口；不得转成方法审批 |
| malformed/out_of_scope | 拒绝无效候选或越界参数 | `REJECTED`；给出可恢复原因，权限/身份违规按已有安全策略处理 |

普通多指标综合分析不因“存在多个指标”就强迫选择一个指标。明确“全部指标”“购卡前后各 30 天”等需求应直接约束计划。文件引用只有在多个有效候选会改变任务范围时才需问，不恢复已退役的文件关系/连接通用审批。

## 5. 直接工具、自动提问与恢复的一致性

当前 `_suspend_for_confirmation_request` 与 `_suspend_for_required_question_payload` 在没有 record 时会抛异常。新策略若允许降级，必须一起修复这些消费路径，不能只改 `QuestionPolicy`。

建议引入窄的内部处理结果（确切类型名 IC0 决定），表达 `suspended`、`continue_with_answer`、`continue_with_advisory`、`invalid_request`。同步、流式、恢复和批量工具执行共同消费该结果。

- `clarify` 才发 `suspended`，使用真实运行时 confirmation_id/version。
- `advisory` 对原 tool_call_id 写入一次正常工具响应，说明已知信息/默认或为什么不需要审批；继续当前预算内的工具循环，不抛“record 不存在”。
- `reuse` 提供已验证适用的答案；不对旧 resolved record 再 checkpoint/悬挂，不重复应用旧副作用。
- 无效/纯方法审批的直接调用返回可理解的工具结果，引导模型继续或具体化缺口；不得合成用户回答。重复同类无效调用受现有执行预算/重复调用控制约束，不新增隐式重试。
- 多问题请求逐项评估：已回答的复用、无关的降级、真实未决的展示；保留每项答案归属，不能用一个确认批准全部问题。
- 确需暂停时保留已经完成的独立工作。先完成现有运行机制允许的独立安全工作，不为此新增并行执行器；如必须暂停整轮，明确依赖和已完成结果，不能执行未决分支。
- skip/cancel/rejected 不是批准。跳过后若没有合法默认，相关分支保持未决或明确缺口；不能继续输出确定业务答案。

CLI、Web、刷新后的状态和原 SSE 事件必须一致。工具响应顺序、未完成工具响应补齐、一次终态、重复 resume 的幂等和过期版本拒绝继续成立。

## 6. 决定复用与版本

保持现有 `decision_key`、`data_version`、`spec_version` 的职责边界，给本专题的新候选添加版本化绑定；不全局更改其他确认类型的复用语义。

推荐逻辑键：`session + task/subject + decision_kind + normalized_business_scope`。相关数据版本组成范围指纹；业务决定修订形成语义版本。保留 `related_spec_id` 作追踪，但不把整个 goal 的文本哈希作为唯一有效性判断。

复用必须同时满足：

1. 同会话、同决定主体与同业务含义；历史状态是真正 resolved，而非 skipped/cancelled/expired。
2. 相关数据身份/版本、指标分母、窗口、人群、成本范围和关键假设没有实质变化。
3. 当前明确要求没有覆盖旧值，答案依赖仍可恢复和核实。
4. 映射不确定时不盲目复用；先查上下文，确有未决且影响结果才问具体差异。

纯措辞/问题显示文案/消息序号变化不应失效；无关数据文件更新不应使决定失效。相关数据版本变化先使基于旧数据的决定不再自动复用，再检查新请求/数据是否已能确定，无须逢版本变化必问。

不实现通用“自然语言等价哈希”。使用明确结构化口径和已有值；否定词、数值、日期、单位、分母不能在规范化时丢失。没有可信结构化身份的旧答案不得仅凭同 playbook 复用。

## 7. 方法选择与计划覆盖

### 7.1 选择来源

保留 `select_playbooks` 的现有 LLM 优先入口与单次辅助预算。返回/审计区分 `llm`、`keyword_fallback`、`default`，另记 supporting 来源；主方法来自 LLM 而辅助方法来自规则是合法组合。

LLM 失败原因区分超时、传输错误、空响应、JSON/schema/未知 ID、显式禁用；保留已有 transport 记账，不额外发调用。记录 LLM 选择理由及最终校验/回退原因，不能只保存模板化“matches diagnostic”。不记录 API key 或完整敏感数据。

### 7.2 语义与回退

综合请求先识别整体目标和明确子指标；否定与强任务表达优先于局部词。规则只能在边界清楚的场景定路由，冲突时采用能够覆盖目标的保守分析主线并保留子问题，不能以“无法选一个模板”为由强制用户审批技术方法。

不能简单重排几条关键词以便两个案例通过；需覆盖否定留存、单纯复购、综合功能、纯收益、拟合/预测等对照。数据画像用于检验方法适用性，不因存在 user_id 就把汇总曲线任务升级成用户流失建模。

### 7.3 计划质量契约

复用现有计划/步骤或目标分支已有的子问题覆盖结构。没有某个历史 memory 中的 schema 时不得照搬名称；在现有 plan 内添加最少的覆盖元数据，明确 schema 校验与持久化。

计划应给每项显式需求关联“计划步骤/已支持答案/具体数据或方法缺口”，不得只自报 coverage=true。实际完成与证据验证仍沿用现有工具收据/发布检查。

- 省钱卡：整体主线为功能/效果与行为分析，可选择 `product_feature_analysis` 或 `effect_evaluation`，不把两者之一当唯一正确标签；收益、复购、购买偏好、频次、ARPU、人均/日均/单次金额、金额分布逐项保留。连续付费与因果问题分别表达，缺对照时只能报告观察/关联和识别缺口。
- 留存拟合：计划比较适用曲线、估计参数、报告误差/范围；不默认要求 entity_id/event_time，也不强制增加流失分类模型。0 值、未成熟 cohort、权重等若实质不明，具体解释或澄清，而非通用确认。
- 预测请求：区分运行模型与发布预测有效性；具备合法数据和前提时计算，无有效外推证据时限定结果，不用一个批准按钮解决。

## 8. 旧记录与迁移

不批量编辑原始 sessions，不删除 confirmation events，不把历史 pending 标成用户 approved，不覆盖旧报告。

新策略需要同时覆盖旧 pending 列表、durable record、checkpoint、关联 task 和 UI 投影：

1. 用明确的旧生产者来源、模板形状、动作和缺少具体语义依赖识别纯通用方法审批；不能对所有 `method_confirmation` 一刀切清空。
2. 纯通用审批在恢复时通过既有事件状态转换退役（例如取消/过期并记录 policy-retired 原因），保留原历史，移除当前阻塞投影；exact transition 在 IC0 依现有合法状态机冻结。
3. 真正的指标/窗口/字段/文件语义请求保留或转换成等价的新候选；无法识别的旧记录不得自动批准或静默丢弃，先复核实际依赖，必要时提出具体澄清。
4. 每次迁移有策略版本和幂等标记；跨加载/刷新不得重建同一旧问题或重复创建确认任务。
5. 新旧语义版本不能意外共用旧消息哈希决定键。其他确认类型的版本/权限保护原样保留。

回滚要区分代码回滚与数据回滚：不可用旧 snapshot 覆盖新事件。验证目标旧版本能读取新增可选元数据；不能读取时需明确拒绝不支持版本或进行向前兼容修复。保留已完成结果和审计链。

## 9. 可观测性、边界与决策事项

记录选择来源、辅助来源、原因、有效范围摘要、提问生产者、策略结果、复用/失效原因、关联确认与任务、是否真的发出 suspended。统计使用固定验收集，分别报告必要提问命中率、不必要暂停数、重复询问数、覆盖缺失数；不以两个案例估计生产频率。

必须保留：数据/路径授权、真实收据、版本绑定、因果/预测范围、发布审计、预算、transport 闭合、无额外 Provider 调用。通用能力审批移除后，要用安全负例证明真正约束仍在，不能把移除审批等同于解除验证。

IC0 可自行冻结字段名、小模块位置、既有状态映射和测试位置。若目标分支缺少关键前置机制、需要新建执行器/数据库、改变用户可见原则、扩大真实调用预算，提交明确差异和选项后再讨论；不得因常规实现选择反复要求用户批准。

## 10. P08 问题修复设计

本章将 P08 真实浏览器样本转为可离线实现和验证的设计。它覆盖 P08-01 至 P08-05；P08-06 导出文件落地和 Provider 请求账本按问题记录约定留到下一轮真实浏览器、真实调用测试。修复目标是让已明确的分析直接完成，同时保留数据、证据、范围、版本和权限约束。

### 10.1 失败、根因证据和实施顺序

| 优先级 | P08 现象 | 当前代码证据 | 设计结论 | 实施顺序 |
|---|---|---|---|---|
| P1 | D7/D30 被“方法计划确认”阻塞 | `select_playbooks` 将模板 `confirmation_policy.requires_confirmation` 原样映射为 `PlaybookSelection.requires_confirmation`；`apply_selection_to_state` 因此创建 `source=method_playbook` 的 pending 项；控制器再以同一字段封锁高风险能力 | 已证实的静态审批链，必须移除其阻塞作用 | 1 |
| P1 | 明确的竞争性假设被要求选择 `trend` 或 `period_compare` | `detect_question_need` 只要 intent 标为 vague/guide_analysis 且存在多路线就直接返回 `route_selection`；它没有识别“提出/检验竞争性假设”是明确任务 | 已证实的规则缺口，必须加入任务明确性优先级 | 1 |
| P1 | D7/D30 的安全边界判断未正常结束 | `run_python` 设定 `pending_fallback_resolution`；除少数记录/确认工具外，所有后续探索都被拒绝。发布检查正确拒绝未绑定的 D30 数值 | 已证实守卫存在，尚未证明是模型未记录结果、循环次序错误或最终发布路径漏接；先做最小可复现再定补丁 | 2 |
| P1 | 数据版本重载后 Provider 报孤立 `tool` 消息 | 循环会保存 `assistant.tool_calls` 和 `tool.tool_call_id`；但 `_serialize_messages()` 当前只持久化 `role` 与 `content`，恢复后会丢失这两个关联字段。该缺失能形成孤立工具结果，是有代码佐证的主要假设 | 先以隔离恢复/重载测试确认，再修复续传消息的成对保留与送往 Provider 前校验 | 3 |
| P2 | 无数据答复包含过多未来路线 | 无数据路径可安全拒绝，但本轮输出同时给出多路线和额外背景问题 | 收敛恢复文案和路由提示；不放宽无数据结论边界 | 4 |

P08-02 与 P08-04 不允许用“清除错误”“跳过验证”“扩大工具预算”修复。前者必须继续阻止无来源的外推数值，后者必须保留原始会话审计和有效工具结果。

### 10.2 统一确认策略的落点（P08-01）

#### 目标状态

方法模板只声明可用方法、数据要求、证据要求和结论限制；它不再自行产生用户确认。确认记录只能来自一个可说明的业务语义缺口，例如：

| 可以确认 | 不得单独确认 |
|---|---|
| 净收益的成本范围、复购的分母、比较窗口、人群口径、多个同名文件的范围 | 留存/预测/因果/ROI/分类的方法名称、模型名称、内部工具路线、D30 或 forecast 关键词 |

对数据不足的预测请求，系统直接完成可支持部分，并说明 D30 缺少观测范围、验证窗口、训练信息或可识别前提；确认不会把缺失证据变为可发布预测。

#### 修改边界

1. `method_playbooks.select_playbooks`
   - 保留当前 LLM 优先与关键词回退、playbook ID、数据要求和分析 spec。
   - 不再把模板级 `confirmation_policy.requires_confirmation` 直接写入 `PlaybookSelection.requires_confirmation`。模板的历史风险说明可保留作审计/提示元数据，但不能成为 pending 的签发权。
   - 若已有真实业务语义确认由其他入口生成，selection 只携带该确认关联所需的 spec/scope，不创建“确认方法”的替代问题。

2. `method_playbooks.apply_selection_to_state`
   - 删除或退役由 `selection.requires_confirmation` 创建的 `source=method_playbook` pending 项、固定问题和“按此方法继续”选项。
   - 不删除已有的 `analysis_spec`、推荐路径、数据要求或计划步骤。它们仍是执行与审计依据。
   - 旧函数名若被测试或调用方依赖，可暂时保留为兼容空操作；移除前先用调用搜索确认没有外部扩展直接依赖。

3. `AnalysisFlowController.is_capability_blocked_by_confirmation`
   - 不再根据静态 `analysis_spec.confirmation_policy.requires_confirmation` 封锁 `analysis.forecast`、`analysis.causal`、`analysis.experiment`、`analysis.classification`。
   - 只在存在**当前可操作且范围匹配**的语义确认，并且该确认的 `affected_operations` 覆盖该能力时封锁依赖分支。
   - 数据字段缺失、权限、预算、证据和发布检查仍分别由原有路径执行；本改动不把能力门控改成“所有工具放行”。

4. `question_need_detector.detect_question_need`
   - 删除“高风险关键词 + 未批准 method_confirmation”这一硬门控。
   - 保留时间窗、指标、字段清洗、文件范围等现有门控，但要求它们给出具体缺失值和对结果的影响。
   - 对直接工具 `ask_user_question` 的同类“是否使用留存/预测方法”请求，复用统一策略返回非阻塞说明和一次工具响应，不能绕开自动检测器重新悬挂会话。

#### 新的最小契约

为避免各入口再次各自判断，确认候选在写入持久层前必须至少满足下列结构（字段优先放入现有 `resolution_params`，IC0 冻结最终名字）：

```json
{
  "decision_kind": "time_window | metric_definition | denominator | file_scope | field_semantics | goal_choice",
  "missing_value": "具体未确定的业务值",
  "affected_operations": ["依赖该值的能力或输出"],
  "scope_binding": {"session": "...", "dataset_or_version": "...", "subject": "..."},
  "reason": "不同答案如何改变当前结论"
}
```

以下候选必须在写入前降级为 `advisory` 或拒绝：`decision_kind=method_confirmation`、只有方法名/风险词、没有 `missing_value`、没有可解析范围、或没有受影响操作。降级不是伪造“用户已同意”；工具循环必须收到一次正常的非阻塞响应并继续。

#### 状态迁移与旧会话兼容

新会话不会再写入纯 `method_playbook` 审批。恢复旧会话时：

1. 识别来源为 `method_playbook`、固定方法选项、没有具体业务决定依赖的旧 pending。
2. 按现有合法事件状态机以 `policy_retired` 原因退役，保留原始 record、event、checkpoint 与历史 UI；不写成 `approved`。
3. 从当前 pending 投影和 confirmation task 中移除其阻塞效果，再让正常的语义检测器重评估当前请求。
4. 旧记录若实际携带窗口、字段或分母依赖，或来源/范围无法判定，绝不自动退役；继续保留或转换为等价的具体问题。
5. 迁移使用策略版本和幂等标记，刷新、恢复、重复 resume 都不能再次创建问题或重复任务。

### 10.3 明确任务优先于内部路线（P08-03）

#### 判定规则

在 `_is_vague_route_request(intent)` 之前增加一个窄的 `has_explicit_analysis_task(user_input)` 判定。它只消除技术路线选择，不自动解决真实的业务歧义。

下列情况视为明确任务：

- 明示竞争性假设、提出假设、检验/验证假设、比较解释、证据支持或反驳；
- 明示唯一业务动作和对象，例如“仅描述 D7 留存”“按已给口径计算复购率”；
- 明示多个要求均应保留，例如“分别分析 A、B、C”。

下列情况仍可进入路线/语义澄清：

- 只有“帮我分析”“看看数据”等泛化指令，且多个数据支持路线会产生不同业务结论；
- 请求了期间对比但未给出可安全推断的时间窗；
- 多个指标、人群、文件或成本定义都合理且未给出选择。

实现采用少量肯定任务词和现有意图字段的合取规则，不用“只要出现假设就一定清晰”的宽松关键词规则。显式竞争性假设请求进入一个可自动选择的假设检验主线：输出至少两种解释、每种的支持/反驳/未决状态、样本与识别限制；它不能借此输出未观测的因果结论。

#### 伪代码

```python
if file_scope_is_materially_ambiguous(state, user_input):
    return clarify_file_scope(...)

explicit_task = has_explicit_analysis_task(user_input)
if is_vague_route_request(intent) and not explicit_task and len(routes) > 1:
    return clarify_route(...)

route = infer_route_or_choose_internal_default(user_input, routes)
if route_has_real_semantic_gap(route, user_input, state):
    return clarify_specific_semantic_gap(...)

return proceed_or_advisory(...)
```

`choose_internal_default` 必须产生内部理由（例如“竞争性假设需要先检查时间变化，再比较替代解释”），供日志/审计使用；该理由不作为用户确认卡片展示。

### 10.4 回退 Python 结果的收敛设计（P08-02）

现有 `TurnExecutionState` 的 `pending_fallback_resolution` 是正确的安全目标：执行了自由 Python 后，不应继续无边界探索。修复只改变“怎样满足已解析”，不取消该目标。

#### 先复现，再选择最小补丁

新增一个隔离测试，按 M02 复制以下序列：描述性 D7 证据、一次 Python/拟合结果、D30 超出观察范围、最终答复只发布 D7 与“不能预测 D30”的证据缺口。测试记录：

1. Python 结果是否被转换为结构化 evidence/limitation；
2. 解析工具是否返回成功、是否调用 `record_tool_success`；
3. 守卫拒绝的是哪一个后续工具；
4. 最终发布检查是在 Python 结果解析前、后还是未执行；
5. 终态是否有最终答复、单一 `turn_end` 和可追溯限制。

根据复现结果选择下列唯一对应补丁：

| 复现结论 | 最小修复 |
|---|---|
| 模型/计划没有发起解析工具 | 在当前提示/计划收敛规则中明确：每个 Python 结果须记录为证据或限制；为“仅发布边界结论”提供已有的 limitation 记录路径。 |
| 解析工具成功但未清除标志 | 修复该工具结果到 `record_tool_success` 的映射，并新增回归，禁止以手工清零替代。 |
| 终态已有合格、来源绑定的边界结论，但守卫仍阻断 | 在最终化前运行受限的终态解析/发布校验；只有验证通过才清除待解析状态并结束。不得允许继续普通工具探索。 |
| 最终文字含无绑定 D30 数值或预测词 | 保持拒绝并进入已有受限修订路径；不因“用户请求预测”或“已确认方法”放行。 |

最终化前，允许的解析结果只能是 `evidence_record`、`limitation_record`、`task_state`、有效的具体语义确认，或通过发布检查的最终答复。自由分析工具、再次 `run_python`、无关预览和普通探索仍被阻断。这样既能完成“不能预测”的可信答复，也不会制造预算逃逸通道。

### 10.5 版本重载与模型工具消息完整性（P08-04）

#### 不变量

对发送给 Provider 的每一条历史，满足：

1. `role=tool` 必须有 `tool_call_id`；
2. 它必须对应此前尚未完成的 `assistant.tool_calls[].id`；
3. 每个工具调用至多有一个结果；
4. 一组 assistant tool calls 与其 tool results 在压缩、暂停、恢复和重载时原子保留或原子从**Provider 投递副本**排除；
5. 原始持久化历史和审计收据不得为修复协议而删除或改写。

#### 已知缺口与补丁设计

当前 loop 会将含 `tool_calls` 的 assistant 消息及含 `tool_call_id` 的 tool 消息加入内存历史；而 `_serialize_messages()` 仅写入 `role` 与 `content`。因此暂停/恢复路径可能丢失关联字段。该现象足以解释 Provider 所见的孤立 `tool` 消息，但仍须以最小测试确认实际 M04 重载路径是否经过该序列化器。

修复包括：

1. 将续传序列化改为保留并校验 `assistant.tool_calls` 的 ID、名称/函数和参数，以及 `tool.tool_call_id`；不要将这些结构化字段压成内容字符串。
2. 为续传反序列化增加 schema 兼容：旧序列化记录缺少关联字段时，原记录照常可读，但只将可配对消息组成的块送往 Provider。不可配对的旧工具消息保留在审计/恢复诊断中，不伪造 assistant tool call，也不悄悄当作成功结果。
3. 在 `client.chat` 前构造临时 `provider_messages`，以纯函数 `validate_tool_message_sequence` 校验。发现孤立结果时，终止该轮的 Provider 投递并走可恢复的本地诊断；禁止把不合法序列直接发出。
4. `compact._find_safe_boundary` 与重载/恢复代码共用同一“完整 tool block”判断，避免压缩器和续传器各自定义配对规则。
5. 版本重载仅更新 dataset/version 绑定和分析状态；它不能重置、截断或重排仍未闭合的工具块。若确有未闭合块，先以既有循环终态处理，再允许重载进入下一轮。

#### 回归场景

- 合法 assistant tool call + tool result：序列化、恢复、压缩后字节结构仍可通过 Provider 前校验。
- 一次 assistant 含多个 tool calls：结果可乱序到达但 ID 都被保留，恢复后仍完整。
- 旧记录含孤立 tool：不发送给 Provider，不篡改原 event，并返回可诊断的本地恢复结果。
- M04 v1 分析、重载 v2、再请求竞争性假设：版本历史可查、v2 成为活动数据、Provider 前消息通过校验、得到最终答复。

### 10.6 无数据恢复提示（P08-05）

无数据时不请求方法确认、不生成未来路线菜单，也不让模型推测业务答案。入口生成固定的最短恢复上下文：当前没有可分析数据、需要上传或选择一个数据集、收到数据后可执行用户已描述的任务。若用户在同一句明确了真正影响结论的业务语义，可在数据到位后再评估；当前轮不同时追问多个假设问题。

验收只检查回复含“缺少数据”和一个明确下一步，不要求固定中文措辞。该改动应位于无数据/意图恢复路径或其提示构造处，不通过删减最终回答验证器来实现。

### 10.7 文件、测试、发布边界

| 改动域 | 候选文件 | 最低测试 |
|---|---|---|
| 模板确认退役与能力门控 | `agent/method_playbooks.py`、`agent/analysis_flow_controller.py`、`agent/confirmation_policy.py` | Q03、Q07、Q13，旧 pending 迁移 L01--L03 |
| 任务明确性和直接工具策略 | `agent/question_need_detector.py`、`agent/analysis_entry.py`、`agent/confirmation/*`、`agent/loop.py` | Q09--Q14、R07--R10 |
| Python 收敛 | `agent/execution_control.py`、调用/最终化路径、`agent/publication_synthesis.py` | M02 重现、S02、既有 execution-control 反例 |
| 消息完整性 | `agent/loop.py`、`agent/compact.py`、续传存储/恢复模块 | M04 重现、L04、工具消息序列单测 |
| 无数据恢复 | `agent/intent.py`、相应入口/提示构造 | M06 无数据 E1/E2 |

测试按以下层次递进：纯函数和状态机 E1 → 隔离 session、真实 AgentLoop/HTTP/SSE 且 Provider 禁用 E2 → 本地真实浏览器 E3。每一阶段只在前一阶段核心用例通过后进入。真实 Provider、请求账本、导出文件下载和完整 P08 矩阵仍是修复后的独立后续验证，不能用本设计或离线通过替代。

### 10.8 完成判定与回滚

本设计完成的条件：

1. Q13 在不点击方法卡片的情况下发布 D7 描述性结论，并把 D30 限制表达为证据不足；
2. Q14 直接生成竞争性假设及证据状态，不出现技术路线选择；
3. 真正的成本、分母、时间窗、字段和文件范围缺口仍产生具体且范围绑定的确认；
4. M02 的 Python 收敛测试无探索循环、无无绑定外推、存在正常最终答复；
5. M04 的版本重载测试无孤立工具消息，且不破坏历史、版本和刷新恢复；
6. P2 无数据用例简洁恢复；全量离线回归通过。

若任一安全负例退化，回滚本次新策略代码与新增元数据解释，但不回滚或覆盖确认事件、会话历史、版本快照和验收记录。真实 Provider 测试发现的新问题时，新建一条问题记录，不以修改本次离线结论掩盖差异。
