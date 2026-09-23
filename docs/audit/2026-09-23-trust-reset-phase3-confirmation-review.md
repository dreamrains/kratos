# 可信发布重置 Phase 3：确认类型化跨批次开工审查

日期：2026-09-23。基线：`main@0952ba46f5072ba66e4fb02b22d7cbd9d048fc92`。本文件记录跨批次开工审查、用户裁决与 Phase 3 离线实现；未调用 Provider。

## 1. 三份原始需求的共同边界

- 价值保留：现有可核算事实不能因模型提出“这是不是示例”而消失；来源未证实时只能条件式说明，不可推定数据是模板或真实总体。
- 意图澄清：只把会改变数值、范围或业务解释且无法从现有证据确定的选择交给用户；方法名、模型许可、纯数据性质猜测不构成暂停。真实成本边界、分母、窗口、文件范围和会改变计算的清洗选择仍必须能暂停，用户同意不替代证据。
- 回答内容：已计算/未计算/证据不足严格分离；缺口只影响依赖它的 claim，不得用一次泛化确认清空全部可信观察。

## 2. 历史事实与代码机制

| 证据 | 说明 | 不应推出 |
|---|---|---|
| IC0—IC4 与 9/9—20 本地/浏览器 | 已有稳定语义决定 key、同范围复用、窗口变化重问、skip 不授权；成本/分母/窗口正例通过 | 真实自然模型不再误分型 |
| R8/R11/R16 等 M06 | 成本范围真缺口曾正确暂停并只恢复一次；R10 成本问题误标 `method_confirmation` 又漏暂停 | 所有确认都该拦，或所有直接提问都不该拦 |
| Codex M01 `a3e5bd3e8eb3`、R20 数据性质 | 已观察到最终内容可发布却因“示例/真实/抽样”提问挂起；词表降级能缓解已见措辞 | 开放措辞空间已被两极词表覆盖 |
| R4 M01 `5df75d57da84` | 问“占位/演示、真实值常量、取数有误”，持久化 `decision_kind=field_semantics`，最终 resolved；现有真极词表未认出“真实值” | 应再给词表加“真实值” |
| 内部路由/问题检测器 | `route_confirmation_gate` 和 `question_need_detector` 产生 `data_quality_confirmation` 时同时携带具体 `risk_fields`、受影响路线/能力；是真正计算/清洗依赖 | 可把所有 `data_quality_confirmation` 一律降为 advisory |

当前 `confirmation/decision.py::is_data_nature_question()` 用“非真实极 + 真实/覆盖极”的选项或问题文本正则；`QuestionPolicy.evaluate()` 先用它决定 advisory，再验证业务缺口。R4 漏判证明该门并非可收敛的结构化语义判定。`decision_context_from_payload()` 会把 `data_quality_confirmation` 映射为 `field_semantics`，并可能从问题文本填 `missing_value`；直接模型提问的 `operation=direct_user_question` 与 `blocking_surfaces=agent_turn` 又足以让泛化问题被认为影响操作。仅有这些字段不能证明回答会改变计算。

## 3. 已确认的类型化替代边界

建议将确认资格按**来源和可核验的影响**判定：

1. 模型直接发出的泛化 `data_quality_confirmation`，若没有宿主可核验的计算影响/具体风险字段，仅返回条件式来源未知指引，不暂停；不阅读选项措辞极性，不补关键词。
2. 内部确定性生产者已给出具体 `risk_fields` 与受影响路线/能力的字段语义、清洗决定，继续可暂停。
3. 明确的成本口径、分母、时间窗口、文件范围等已有结构化 `decision_kind + missing_value + affected_operations` 仍可暂停；同范围复用与变更重问不改。
4. 若未来直接模型要暂停字段语义缺口，必须有宿主可核验的具体字段/计算依赖；模型自报“会影响分析”不是证明。不得新增 LLM 审核调用、审批数据库或第二 planner。

用户裁决：模型直接提出 `data_quality_confirmation` 但没有宿主可核验的计算影响时，降为条件式指引，不暂停；内部带 `risk_fields` 的清洗门和明确成本/分母/窗口等业务缺口仍暂停。此裁决只针对数据质量类型的暂停资格，不把已有业务语义确认一律降级。

## 4. RED → 结构化替代 → 旧门退役

- RED：新增 `tests/test_confirmation_typed_gap.py` 首次执行 10 项，4 项失败。Codex/R20 两种旧措辞本已降级，但 R4 的“真实值常量”以及无极词的同类请求错误暂停；模型自报 `risk_fields/decision_context` 也错误暂停；内部没有风险字段的泛化请求错误暂停。这个对照说明根因是把模型问题文本回填为 `missing_value`、默认 `agent_turn` 后当作计算依赖，而非 R4 漏一个同义词。
- 替代：`question_need_detector` 从清洗日志与路线推导的 `risk_fields + affected_routes` 贯穿 loop → candidate，适配层只为这一确定性生产者记录 `host_risk_fields + host_affected_routes`。策略对 `data_quality_confirmation` 仅在上述宿主证据存在、且仍满足原有业务缺口合同的情况下暂停。模型直接给出的同名字段不能自证风险；不具证据的提问返回来源/覆盖未知的条件式指引，保留已核实观察。
- 退役：删除 `is_data_nature_question()` 与“示例/真实/抽样”两极正则门；不加新词。保留既有 stable decision key、resolved reuse 优先、skip 不授权和明确 `metric_scope/time_window` 等类型的暂停合同。`route_confirmation_gate` 在分析入口仍独立使用其宿主清洗风险，不被这次候选策略改动替换。
- GREEN：聚焦与跨历史确认/路由回归 196 passed；覆盖 R4/Codex/R20、模型伪造风险、内部风险正反例、成本/分母/窗口、检测器到 loop 元数据传递，以及既有确认复用/续轮与入口/路由用例。最终新目录 `tmp/trust-reset-phase3-full-offline-2` 的 fail-closed `full-offline` 为 2844 passed、1 skipped、16 warnings（JUnit 2845 tests、0 failures、0 errors、1 skipped；SHA256 `C96DE690BE28CF424AB5E36B7441771CC0D40DB6B1D5BA42D0AC58D2F0B7AA65`）。入口显示 `provider_calls=forbidden`；运行期间排除了用户原有未跟踪的 `tests/test_p08_trust_restructure.py`，未改动该文件。首次运行目录 `tmp/trust-reset-phase3-full-offline-1` 是测试形状强化前的收据，不作为最终基线。

## 5. 证据边界与后续

本阶段未做 Provider-disabled 浏览器整矩阵、真实 Provider、staging 或 production 验证。直接模型触发真实提问的概率和不同措辞覆盖，仍需未来按既有完整矩阵及授权门检验；不能从离线正例推出已解决全部自然模型行为。Phase 4 只允许事后 journal，不能借此给确认门增加前瞻规划或新审批通道。
