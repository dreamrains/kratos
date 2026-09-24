# 中文数据分析 Agent 可信发布重置：实施交接（2026-09-23）

## 0. 精确现场与授权边界

- 根工作树：`D:\Project\Daily\data-agent`；本次插入修复的基线为 `main@5c0e4b2f79a0bd6f0a9d9e095812d7b2c7405557`，比 `origin/main` 超前 50 个提交，没有 push。提交后的确切 HEAD 应以 `git rev-parse HEAD` 复核，不从这条基线推断。
- `git worktree list --porcelain` 已确认根工作树和八个隔离 worktree；本轮只在根工作树操作。
- 当时有两份用户原有未跟踪文件：`docs/superpowers/plans/2026-09-22-trust-architecture-restructure.md`、`tests/test_p08_trust_restructure.py`。本交接后的用户新授权允许删除；两份文件经精确身份核对后已删除，根工作树当时恢复 clean。历史离线回归确曾以 pytest `--ignore=tests/test_p08_trust_restructure.py` 排除后者，不能把旧收据改写成默认无条件全绿。
- 本轮没有真实 Provider 调用、push、部署或 staging/production 验证。历史 R4 最新批次曾被用户中途叫停，不能当成完整通过或唯一设计依据；以前授权、剩余额度和 Provider 会话不得复用。
- 每一阶段都按“历史/现行 RED → 结构化替代物 → 精确旧门退役”判断；不补自然语言关键词，不靠尾部免责声明抵消错误正文，不增加第二 planner、重复台账、浏览器框架或隐藏模型审核调用。

## 1. 已完成检查点与证据等级

| 阶段 | 提交/现状 | 实际完成与最强本轮证据 | 尚不能宣称 |
| --- | --- | --- | --- |
| Phase 0 | `docs/audit/2026-09-23-analysis-agent-trust-reset-phase0-review.md` | 根目录 AGENTS、总计划、三份原始计划、git/worktree、R4 与跨 R7—R21 历史复核；修正 M03 根因判断，并确认 R4 M03 既有 `answer_bindings.v1` 种子 | R4 完整通过 |
| Phase 1 | `cdfcc1a5d4d4ab82cee85b722d9423a2c3036a99` | canonical history snapshot/revision/hash/CAS；R4 M03 错误 split RED；fresh full-offline 2821 passed、1 skipped | 浏览器或 Provider 验收 |
| Phase 2 | `0952ba46f5072ba66e4fb02b22d7cbd9d048fc92` | 扩展既有 `answer_bindings.v1` 的 M02 情景 claim，宿主绑定回执重算并在正文位置渲染；错误 D30 拒绝、正确候选等价呈现；聚焦 234 passed、full-offline 2831 passed/1 skipped | 所有 claim 类型完成、E3/E4 |
| Phase 3 | `d0a261429c82ddadadc5a9377e719526fe1f4fbc` | 用户确认：模型直提无宿主风险的 `data_quality_confirmation` 为条件式 advisory；内部清洗 `risk_fields + affected_routes` 及成本/分母/窗口仍暂停。删除数据性质两极词表；聚焦 196 passed、full-offline 2844 passed/1 skipped | 自然模型永不误分型 |
| Phase 4 | `d5a28ce4faaab2a08fa996d2b985800d437eb18f` | 用户确认显式竞争假设保留 plan/假设/证据关系；R21 M02 scope 和 M04 未完成 task 阻断已有现存修复。receipt + publication packet + TaskManager 即事后事实源；214 项定向测试通过，无需另建 journal | 跨轮次继续任务全部正确或 E3/E4 |
| Phase 5 首切片 | `9ef6fbc2eaea4e43a42a38beaae4f8234c39a241` | 纯离线 `publication_audit.v1` validator：快照/答案身份、M02 typed claim 与自身 evidence 引用、封闭枚举，外来意见 advisory；Shadow 不改变发布。聚焦 178 passed、full-offline 2851 passed/1 skipped | 已调度审计 LLM、完成 Shadow 校准或可执行处置 |

Phase 5 最终 JUnit：`tmp/trust-reset-phase5-protocol-full-offline-1/junit.xml`，2852 tests、0 failures、0 errors、1 skipped，SHA256 `23AE5D209F471D1CCDEECA105F2359CB2E86488E425B8012AFC0662C3C67FA1B`，runner 为 `provider_calls=forbidden`。各阶段更细的 RED、源码范围、JUnit 与历史对照分别见 Phase 0/2/3/4/5 审查记录；不要只引用最后这一次计数解释架构。

## 2. 下一阶段的最小安全边界

1. **先扩展 typed claim 覆盖，再谈完整 Shadow。** 已插入简单数值 `observed_fact`、同工具事实身份授权的 `derived_metric`、无维度 `compare_periods` 的 `comparison`，以及仅限观测区间的 `descriptive_fit` 垂直切片（细节见本文第 5、8、9 节）；都沿用 `answer_bindings.v1` 唯一占位符及当前回执，宿主在正文原位渲染原始尺度。派生量还必须与同回执结果同值、重算运算并核对数据版本；EvidenceRecord 模型可填的标签不能单独授权。普通 legacy 块仍不具有 `answered` 权限；Phase 5 validator 目前仍故意只允许 M02 `scenario_extrapolation` 形成可行动建议，其他意见 advisory。带维度比较、明确缺口和自由散文高风险主张仍待结构性取舍，不新开传输/存储通道，也不应无穷枚举 claim 族。每一族先回放 R7—R21/R4 的正确与错误候选，验证单位、版本、强度、证据引用；不能用新的措辞词表代替 claim。派生切片详见 `docs/audit/2026-09-23-trust-reset-derived-claim-slice.md`。
2. **Shadow 调度必须显式且可记账。** 目前没有审计模型请求、后台 hook 或预算消耗。若实施调度，审计输入只含原问题、已确认决定、候选、current typed claims/裁剪回执、宿主确定性结果；上传内容/工具输出/候选均标不可信。审计结果只入已存在的发布审计资料或当前 packet，不新建第二账本；超时/格式错/无引用只能使审计 unavailable/advisory，不能拒绝已通过确定性检查的答案。
3. **仍不进入 Phase 6 处置。** 当前 `reason_untrusted` 仅是审查素材；`missing_requirements/contradictions` 首切片只接受空数组。尚未证明自由文本 reason 不会引入新事实，也未校准同模型共盲、正确候选误删率和高风险漏检率。即使 finding 建议 `remove`，Shadow 的 `publication_effect` 仍为 `none`。
4. **E3 与 E4 独立。** 集成修复后按根 `AGENTS.md` 的现有 Provider-disabled rehearsal 入口和内置 `iab` 浏览器完整矩阵执行，保留服务 PID/exec session、run dir、健康检查、会话和 runtime 收据，报告 initiated Provider 0；不局部重跑装作完整批次。真实 Provider 前须在新的精确 commit 上冻结模型、端点、fixture/prompt/oracle digests、矩阵、预算、账本路径并获得用户新显式授权，不能复用 R4/R21 凭证或额度。

## 3. 停止条件与待核事项

- 若下一步要取消显式竞争假设任务的结构化 plan 或关系证据门，已与用户裁决冲突，必须先讨论；若新 journal 开始规划未来工具/任务，立即停止。
- 若想让审计 LLM 成为随机总审批门、直接修改正文、整篇自由改写，或把 `overall=pass` 覆盖确定性失败，立即停止。
- Phase 4 尚需在未来集成测试中关注“成功发布时 `closed_by_publication` 对用户明确的跨轮次继续任务是否释放 scope 过早”；目前只是待核风险，不是已复现缺陷。
- 两份旧未跟踪文件已依用户新授权删除；其他修改仍只按精确文件名 stage。任何真实 Provider、push 或部署仍需要新的相应授权。后续审查另见 `docs/audit/2026-09-23-trust-reset-pre-shadow-architecture-review.md`：用户已明确裁决先修 CR03 覆盖误放与发布异常 fail-open；该插入切片并不关闭所有未绑定高风险散文，完整 Shadow/处置继续暂停。

## 4. 插入修复的可执行后续清单

1. 基线 `5c0e4b2f79a0bd6f0a9d9e095812d7b2c7405557` 的五条确定性 RED 见 `tests/test_answer_content_coverage.py` 与 `tests/test_publication_synthesis.py`。修复只改已有 `publication_synthesis.py` 的 binding/coverage/原位 renderer 与 `loop.py` 的发布失败非成功状态；没有新 planner、模型审核调用或词表扩展。新增负例还覆盖同句缺口洗白与非数字回执；正例保留 AC17 的八项可信加一项 gap、M02 情景与后到回执快照。
2. 对此阶段的验收，五个定向文件 `test_answer_content_coverage.py`、`test_publication_synthesis.py`、`test_answer_numeric_consistency.py`、`test_scenario_claim_binding.py`、`test_publication_audit_shadow_contract.py` 本轮 180/180 通过。最终在**短且全新的** `tmp/tprb6` 跑现有 `run_regression.py full-offline`：2861 passed、1 skipped、16 warnings、0 failed；JUnit `tests=2862/errors=0/failures=0/skipped=1`，SHA256 `018702B8CB0DED188422723A423E9666569E346A490CE051D0C1D73FE5D87FF8`，runner 为 `provider_calls=forbidden`。长目录 `tmp/trust-reset-pre-shadow-pub-boundary-20260923` 的 2856 passed/1 skipped/1 failed 保留为环境失败收据；唯一 golden funnel 失败是发布收据写入 `FileNotFoundError`，整个 golden 文件在短目录 `tmp/tprb3` 5/5 通过。`tmp/tprb4`、`tmp/tprb5` 因增加同根未绑定数字回归主动中止，不是完整验收。不要把第一次结果写成 green，也不要把短目录单文件重跑冒充完整批次。
3. 完整 Shadow 前的后续 RED 包：单一问题未抽出 requirement、与明确子问题不同句的独立裸数字/无数值的过强结论、**带维度比较/描述拟合**中正确事实被散文门误删、错误事实借同快照不相关引用放行、多来源和数据版本切换、明确 gap 与独立正确 claim 共存。已抽出 requirement 同句的第二个裸数字和跨句 gap 洗白、工具已有事实身份的简单派生量、无维度时段比较以及无效 binding 后保留独立可信 claim 均有 RED/GREEN，不要重复做同一种词法特例。必须先在三份原始需求与 R7—R21/R4 历史候选上校准，不能只追最新被中断的 R4 单例。逐族给出“RED → 结构化替代物 → 将退役旧门”，检查正确 claim 保留率和拒绝原因；涉及语义取舍无法封闭证明时先向用户说明并确认，不靠词表或 `overall=pass`。
4. 浏览器 E3 只按根 `AGENTS.md` 现有 Provider-disabled rehearsal + `iab` 完整矩阵执行，不能局部重跑冒充完整批次。E4 仍需在新精确提交上完成零调用冻结与用户新授权。无 push/部署授权。

## 5. 派生 claim 后续检查点（Shadow 仍未启动）

用户确认模型可填的 EvidenceRecord `metric/claim_key` 不能单独授权 `answered`；仅同一当前工具回执的指标 fact 身份有效。第二个插入切片已沿用 `answer_bindings.v1` 增加 `derived_metric` 的工具 fact + derived ref + 宿主复算/版本/同值检查，并在占位符原位渲染原始尺度；版本核对只覆盖该派生真正引用的操作数，不因无关测量阻断。详细 RED、退役旧门及限制见 `docs/audit/2026-09-23-trust-reset-derived-claim-slice.md`。定向五文件 189 passed；`tmp/tprb7` 在最终作用域收窄前全量离线 2869 passed、1 skipped、16 warnings、0 failed，JUnit SHA256 `52B5AE03893D2ABD388A7C250DA44A77B7FCF1139495BAF66F958D38501B85E2`，只证明前一代码快照。最终实现 `tmp/tprb8` 完整离线为 **2870 passed、1 skipped、16 warnings、0 failed**，JUnit `tests=2871/errors=0/failures=0/skipped=1`，SHA256 `C573A466350818F1AFF8722DCDDB2C45ADDE9D13015B5C4F82251060D13A15DF`，runner `provider_calls=forbidden`。这仍是 E2；未跑浏览器、真实 Provider，也未把 Shadow 接入发布。后续继续从比较/拟合及单一问题覆盖的历史正反例推进，先给 RED/结构化替代/旧门退役，再改代码。

## 6. CR07 独立可信 claim 的失败后保留

第三个插入切片针对“有一条错误 binding，修订一次后仍失败，正确 claim 也被全局错误吞掉”的实测 RED。只在修订额度已用尽且当前候选失败时，宿主从同快照已通过 parser 的 typed blocks 逐条重新验证/渲染；无效块与自由原文不复制，未核验子问题保持 `unassessed` 并在正文原位列出，连一个可信块都没有则继续非成功。这个边界不会增加模型调用，也不把末尾免责声明当纠错。详细历史、三联门和限制见 `docs/audit/2026-09-23-trust-reset-partial-publication-slice.md`。相关六文件 205 passed；`tmp/tprb9` 最终完整离线 **2873 passed、1 skipped、16 warnings、0 failed**，JUnit `tests=2874/errors=0/failures=0/skipped=1`，SHA256 `4054E729530292EBF93DCA89172363813E2DEE5A7E6AE59CC34F8611293B1F90`，runner `provider_calls=forbidden`。浏览器 E3、真实 Provider E4、Shadow 调度/处置仍未启动。

## 7. 单项请求、真实会话与意图识别复核

用户补充提示本地真实会话及既有意图识别。本轮只读核对 `sessions/9810fe7bacf6`、`9959216b6a4a`、`8ddfa3029b15` 等不同形态，以及 `TurnIntent`/`llm_intent`：现有意图只输出粗粒度路由/歧义；`analysis_spec.metrics` 在真实会话里可为泛化 `retention` 或占位 `target_metric`，均不能担当指标身份。样本不当正确答案 oracle，也不只盯中断 R4。详细 RED、初版“请给出结论”误伤、用户第二次裁决、结构化替代与残余风险见 `docs/audit/2026-09-23-trust-reset-single-metric-intent-slice.md`。

用户最终裁决仅当前工具回执的唯一精确指标身份能把单项候选升级为可硬验 requirement；无匹配或多义时 `unassessed`，不自动输出指标缺口。初版直接句式自动缺口渲染因误伤已撤销，反例保留；CR07 局部发布也不能把软候选列为失败硬项。此切片沿用现有 requirement 与 `answer_bindings.v1`，不增加意图模型调用或新的词表；实现及测试提交 `75d5f87bed52b03281bf33d74b005b2505036f06`，未 push。定向五文件最终 **199 passed**。`tmp/tprb10` 的 2879 passed/1 skipped/16 warnings 仅证明局部发布边界再次收窄前的源码快照。最终 fresh `tmp/tprb11` 全量离线为 **2880 passed、1 skipped、16 warnings、0 failed**；JUnit `tests=2881/errors=0/failures=0/skipped=1`，SHA256 `0F35FBBAC0E71C1F9003846D5C46C742B15E8E7660B54F5F68198042C69A86BB`，runner `provider_calls=forbidden`。无同名回执时的自由散文无据数字仍是未关闭的通用 claim 发布缺口，不能把此切片记为完整 CR03/Shadow 通过。E3/E4 仍未做，真实 Provider 仍需新精确冻结和显式授权。

## 8. 时段比较 claim 垂直切片（2026-09-24）

在 `main@ff0d4e6c2cfe21a153beaef8ab6d5c58031a4afb` 基线上继续扩展既有 `answer_bindings.v1`，没有新通道。跨 R11/R14/R16 与 R7—R21 历史正反例、被中断的 R4 及本地真实会话作背景，不能把任一单轮失败当完整 oracle。真实 `compare_periods` 是嵌套 `metrics.<metric>.period_a/period_b/diff`，不是旧测试简化的顶层 `period_a.value`。先有 5 条 RED；现有 parser 无比较类型校验，无法封闭约束差额、同一指标/回执和窗口。

结构化替代物是现有 binding 中的 `comparison` block：一个 `compare_periods` 当前回执、同一指标 A/B/diff 三个精确 fact refs、当前 scope 日期和天数、有限值及四位舍入误差校验；宿主在唯一占位符原位渲染原始数值和宿主复算差额，单位未确认不转百分比，天数不同作就地提示。它不从模型散文反向抽比较事实，也不由模型标签把开放问题升级为 `answered`。错误或失效 binding 不发布；修订失败时已有局部发布路径只保留重新校验的独立可信块。详细 RED、退役旧门、定向用例与风险见 `docs/audit/2026-09-24-trust-reset-comparison-claim-slice.md`。六个相关文件定向 **208 passed**；fresh `tmp/tprb12` 全量离线 **2889 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2890/errors=0/failures=0/skipped=1`，SHA256 `C43989CEE262B1C674930D366DCBF05585150472646BC64D6541F1D422913084`，runner `provider_calls=forbidden`。

边界必须延续：本切片没有封闭所有自由散文数字、过强定性、带维度 `comparisons[]`、日均/百分比、显式问题的覆盖证明或因果/预测；尤其有效比较旁的另一个无绑定错误数字仍可能漏过。不能通过追加“同比/比较/日期”词表或尾部免责声明宣称关闭。下一步需再次对照三份原始需求和跨历史正确/错误候选，以 RED → typed 替代物 → 旧门退役推进一个具体 claim 族；若涉及无法从回执确定的语义身份先与用户讨论。Shadow 审计仍只作有界 advisory，不是随机总审批门。E3/E4 均未执行；真实 Provider、push、部署未经授权。

## 9. 观测区间描述拟合 claim 垂直切片（2026-09-24）

在 `main@a96fd18eeda02cf5441371fe1cdb6f2a96c8cfbf` 基线上处理“只要求解释已观察拟合，而不要求 D30”的正确候选，避免为了使用宿主表格虚构一个外推点。跨 R11/R14/R16/R21、被中断 R4 及三份原始需求校准；不把任何一次测试当完整 oracle。四条定向 RED 全失败：`descriptive_fit` 既没有 typed 接纳，也无专属错族/跨回执/伪造状态拒绝。

仍在 `answer_bindings.v1` 增加 `descriptive_fit`：唯一占位符、当前 `curve_fitting` receipt、全部回执模型族、描述级别、未确认单位、未验证状态。宿主按当前 scope 复核有效点数、观测范围、有限参数/R²，原位按回执排序渲染全部族并说明零值、单位和验证边界；不自报 `answered`，不把拟合写成预测。详细三联门、真实工具构包用例与剩余风险见 `docs/audit/2026-09-24-trust-reset-descriptive-fit-claim-slice.md`。七个相关文件最终定向 **216 passed**。`tmp/tprb13` 是最后一条终局路径用例前的完整回归快照（2896 passed/1 skipped）；`tmp/tprb14` 是完整但失败的收据（2896 passed/1 skipped/1 failed，唯一 `test_offline_tool_surface_smoke` 子进程 180 秒超时，未改阈值）；最终 fresh `tmp/tprb15` 全量离线 **2897 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2898/errors=0/failures=0/skipped=1`，SHA256 `63BB3C4378B329AC315922353FE637C084EC1B9F2830E20B249F9142EC2F349F`，runner `provider_calls=forbidden`。前两次的具体 JUnit SHA256 见阶段记录；不能合并改写为单次全绿。

仍未解决的是自由散文中独立无绑定的高风险数字/过强结论，以及无可靠工具身份时的用户问题覆盖。当前比较夹具中的有效 binding 后接独立“另一结论为99%。”，实测 `binding_issues=[]`、`narrative_issues=[]`；下一发布边界的正反证据、可选路径和需用户裁决的价值取舍见 `docs/audit/2026-09-24-trust-reset-unbound-prose-decision.md`。后续不应陷入逐词补丁或无穷 claim 族清单；先就具体历史正反候选和原始价值目标决定结构性发布边界，再进入完整 Shadow/处置。E3、E4、push、部署均未执行；真实 Provider 仍须新精确冻结及授权。

## 10. 双轨离线校准：不能立即默认纯可信核心（2026-09-24）

用户已确认先离线比较完整候选与现有宿主可信核心，正式默认策略仍待后续裁决。只读首轮结果见 `docs/audit/2026-09-24-trust-reset-dual-track-calibration.md`：核心剔除了“有效比较绑定＋独立无据99%”中的错误数字，并保留 typed M02 三族/AC17 八事实；AC17 模型写的“缺少分母”变成通用未核验，但该夹具**未证明分母真的缺失**，不能把它当正确内容误删。R11 正确 D7/无 D30 散文、R4 M03 六来源表/图和 M04 竞争假设正文因尚无可接纳 typed 占位符会生成空核心。R16 完整真实批次中已通过的 M05（12/120、未知量纲、方法表）也无 typed 占位符，核心为空；另三份本地旧会话同样无 typed，占格式覆盖背景而非正确性 oracle。故不能以“立刻只发 fallback”解决误放，否则造成原始价值目标偏离；下一步须先设计同一回执/packet 上可重建的**有宿主证据的**具体 gap、多来源事实/产物、假设关系与方法上下文，并继续对照跨 R7—R21 正反证据。校准本身没有改变代码或正式发布，也没有浏览器/Provider 调用。

## 11. Phase 6 进入门与合并范围评估

用户随后选择保持正式发布不变、先补足可信核心，并询问能否与 Phase 6 一起推进。`docs/audit/2026-09-24-trust-reset-phase6-entry-assessment.md` 给出按阻碍范围划分的完整清单和四个有限门：A 可信核心合成、B 纯宿主离线 claim 级动作、C 显式 Shadow 调度及校准、D 经另次裁决后的受限发布处置与 E3。**A+B 可以合并开发为 `phase6_preparatory_offline`，但不能把当前只有纯协议 validator 的 Phase 5 或未校准的动作称为 Phase 6 已上线。**现行 `publication_audit.py` 仅绑定 M02 情景 finding；无绑定 99% 没有可操作 claim ID；旧 `render_verified_partial_answer` 对多来源/假设/方法的重建不完整。这是具体依赖，而非笼统“总是无法进入下一阶段”。E4 仍需新冻结/显式授权。

## 12. A+B 首个离线切片与剩余门（2026-09-24）

用户显式选择 **A+B 合并启动离线准备、C/D 另设门**。见 `docs/audit/2026-09-24-trust-reset-phase6-entry-assessment.md` 的 RED/结构替代/退役目标。当前代码新增纯预览 `render_trusted_core_preview`：复用已验证 typed claim 的宿主渲染，摘录与 packet `facts` 一致的跨来源原始事实组，另从宿主预算/扫描状态说明特定遗漏；事实组只作为未赋予 `answered` 的上下文，不把模型的“缺少分母”当真。`publication_audit.py` 对全部当前 typed 家族用同快照确定性校验绑定，再提供 `simulate_shadow_actions`：仅离线模拟 claim 级 keep/downgrade/mark_unassessed/remove 及定向修订 ID，不复制 `reason_untrusted`，不改变正式出版。错配指标、伪造情景、外来引用与过期审计均不得处置；独立可信 claim 应保留。旧 Shadow 伪夹具因此改成 R4 M02 等价有效结构，不能把仅有 ID/回执名当作有效 binding。

定向五组测试 **180 passed**；首轮 `tmp/tprb16` **2904 passed、1 skipped、16 warnings**，但执行中又收紧了审计身份检查，因此**不作为最终代码时点收据**。最终 fresh `tmp/tprb17` 全量离线 **2905 passed、1 skipped、16 warnings、0 failures**；JUnit `tests=2906/failures=0/errors=0/skipped=1`，SHA256 `41C04E855B46FE6DAD2E3E0ABC4FEBF839E5389902E8693E16206E50AA503954`，runner `provider_calls=forbidden`。这仅是 E2，本轮真实 Provider initiated calls=0，未启动浏览器 E3。根工作树存在本阶段待提交的文档/代码/测试，提交时只 stage 明名文件。

**不能切默认或称 A/B 完成**：R4 M03 六来源的结论/图表产物仍不等于原始字段，R4 M04 竞争假设关系尚无同快照权威投影，R16 M05 方法上下文及 R11 正确否定边界尚未达到当前 typed 核心的等价保留。独立 99% 的现行完整散文误放仍在，因为正式门有意未动。接下来应在历史正反矩阵校准中补齐这些宿主所有者，或遇无法从当前结构重建的关键解释时先请用户裁决；不能用 Shadow 随机总审或词表补丁兜底。C 的真实 Shadow 调度/成本/误删校准和 D 的正式处置/E3 必须分别另过门；E4 仍需新精确冻结与显式授权。无 push/部署。

## 13. A+B 第二离线切片：范围、图表产物、假设审计（2026-09-24）

用户确认“先做默认关闭的离线投影”。完整 RED、结构替代、旧门退役目标和限界见 `docs/audit/2026-09-24-trust-reset-offline-core-projection.md`。`render_trusted_core_preview` 现在从当前 source/scope 同回执匹配后展示 R11 型观测范围、R16 型日期/行数/未确认单位及“未证实统计推断”；没有 D30 自造值、百分比/币种换算或从 `run_python` 的 false 标志推断完全没做统计。显式 `build_publication_packet(..., offline_trust_projection=True)` 在**同 packet/digest**中记录当前会话已创建图表的 artifact-only 引用和当前 plan 的假设关系审计，默认 false；AgentLoop 未启用，`publication_packet_prompt` 对离线包直接拒绝。历史旧 artifact 无同快照条件则不投影，不创建第二 planner、账本或通道。

发现并阻止了模型自报 `delta/method/p_value` 的升级路径：假设状态只有同指标当前 `compare_periods` 回执的 A/B/差额与日期通过既有宿主复算、与记录变化相符时才可成为描述性支持/反驳。模型伪造因果方法和显著性字段被剥离；其他工具的关系留未决。图表仅证明同会话成功产物存在，不证明图中结论。**R4 M03 六来源业务结论、M04 非闭合比较方法的关系、R16 M05 旧方法表并未被本轮自动重建**，A 的历史价值校准仍未过门；正式 99% 误放仍在待退役发布门上，不能借离线代码当已修。

定向 **217 passed**。`tmp/tprb18` 为投影实现前范围切片完整离线 **2909 passed/1 skipped**，JUnit SHA256 `F95412FFFF266FA6835F56BBE0BCC755EDEBD30D9A6EC216AAFB473DF5A21AA3`；`tmp/tprb19` 在投影完成后 **2913 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `3C4812DF580B04D638FB47D6CC46E16823EEBA2B9FFE5DB5D3E5B700C76C5FF3`，但运行后又收紧了“无显式本轮 receipt IDs 不投影”。**最终 fresh `tmp/tprb20`** 为 **2913 passed/1 skipped/16 warnings/0 failures**，JUnit `tests=2914/failures=0/errors=0/skipped=1`、SHA256 `1506832913636E32A2569E7C54D46149C60B806D7865F70100704DFE3025AA18`，runner `provider_calls=forbidden`，真实 Provider initiated calls=0。E2 不等于 E3/E4，未做浏览器/真实 Provider/push/部署。下一步应做跨 R7—R21/R4/R16 的离线可信核心价值对照，明确哪些仍需结构化迁移或用户取舍；C/D 保持独立门。

## 14. 防上下文失焦检查点与下一离线 RED（2026-09-24）

用户要求把新进展写回主计划，避免只盯最近中断的 R4 或因上下文压缩反复做词表修补。主计划 §0.1、Phase 6 四门、§9 完成定义和历史交接边界已同步更新；完整跨历史矩阵与下个 RED/结构替代/退役目标见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md`。本次只读核对 `main@b7e1f981b395a3a5007998013422886b8958487e`、clean/ahead 60，R4 目录仍在；不把原计划 §2.3 的两份旧未跟踪文件说成现存用户 dirty。

新的结构缝隙不是某一个措辞：R4 M03 历史 `synthesize_time_series` 回执有 102 facts/34 groups 和六源版本身份，但最终 packet 只选择 `record_evidence_record`，故当前可信核心即使能渲染 packet 也拿不到那些金额。此为**历史证据**，须在当前 HEAD 以同轮/同版本/后到证据回执的最小夹具先复现；若当前已闭合就不改代码。下一切片仅属 A+B 离线：先验证入包/遗漏是否保留当前综合事实与跨轮旧版本隔离，再对照 R11/R16 正例、R4 分项及无据 99% 负例；不让原始字段/模型 EvidenceRecord 标签自动成为 `answered`。正式发布路径、Shadow 调度、审计处置、E3/E4 均未获此次文档更新授权。

## 15. A+B 第三离线切片：显式综合回执可进入预览包（2026-09-24）

阶段 RED/结构替代/旧门边界见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §6。当前 `_SUBSTANTIVE_TOOLS` 与 `_PUBLICATION_EVIDENCE_TOOLS` 排除了 `synthesize_time_series`，故即使构包时给出该 ID，综合事实也先被工具集合门排除。新增测试 RED 为 `StopIteration`；最小修复仅在 `offline_trust_projection=True` 且调用方传了显式 receipt IDs 时，允许同一构包器纳入该成功回执的 fact groups/省略项和 digest。普通包、AgentLoop、模型 prompt、正式发布没有改变；预览显示原始字段但 `accepted_claim_ids=[]`。这不是从旧模型 claim 中恢复六源业务结论，也不证明调用方 ID 与当前 workspace 版本同一。

两文件定向 **17 passed**；`tmp/tprb21` full-offline **2914 passed、1 skipped、16 warnings、0 failures**，但在最后一条 digest 测试断言前，不作为最终树收据。**最终 fresh `tmp/tprb22`** 为 **2914 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `D689F1C2FD27A52EC7098B051DCA55884A66F8CAC7939FE74E71B3D9E490030D`，runner `provider_calls=forbidden`、真实 Provider initiated 0。E3/E4 仍未做；A 的六源同版本计算/渲染、R11/R16 正确价值保留与无据 99% 的正式发布边界未闭合，B 仍为离线模拟，C/D 仍独立授权门。下阶段先把可复算的六源结果与原始字段区分，再决定是否需要窄的宿主表格；不能把工具集合放宽当成完成 CR03/CR04。

## 16. A+B 第四离线切片：同版本派生帧的两日描述表（2026-09-24）

跨历史 RED、结构替代与旧门状态详见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §7。R4 M03 综合回执的 102 facts/34 groups **并无两日金额**，金额只在既有 `sources_combined` 派生数据，旧 preview 是文本、旧 EvidenceRecord 是模型自报；因此不能从回执元数据直接称六源数值已保留。新的 `offline_workspace` 参数仅用于默认关闭的离线 packet，须显式选择该综合回执，逐一核对六源和派生数据的当前 identity、父版本及派生帧实际指纹，再从现有派生帧读取恰好两日的逐源值并用 Decimal 复算变化。单位未确认，首日为零则百分比不适用；不跨源合计，不标记 `answered`。无 workspace、漏选、旧源版本、派生版本错配或伪造身份都不投影；此数据进入同一 packet digest，离线包仍不能被模型 prompt 使用。

初始三项 RED 为未支持 `offline_workspace`；最终三文件定向 **21 passed**。fresh `tmp/tprb23` 全量离线 **2918 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `4D7B0B628E445EA60C09393B46519CD97B155D4D615C2F590F2EE7192B4B55F2`，runner `provider_calls=forbidden`，真实 Provider initiated 0。正式发布、AgentLoop、Shadow C、处置 D、E3/E4 均未改变。下一阶段仍须校准 R11/R16 的正确解释/方法价值、R4 M04 非闭合关系与有效 binding 旁无据 99% 的误放；不能把这个特例表格升格为 A 门完成。

## 17. 跨历史反查后避免“专用表格循环”

R16 完整批次 M05 已通过，但其 `transform_data(group_aggregate)` 回执只有派生数据集名/列名/行数等元数据，旧终局 packet 只有两条 facts=0 的 `preview_data`。这与 R4 M03“已生成结果在 workspace、发布包没有数值”的根型相似；继续为每个工具写一张特殊离线表会使重置退化为另一类逐例补丁。具体只读证据与下一通用派生快照契约建议见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §8。这个建议还没有代码或正式发布授权；下一实施切片先和用户校准通用边界、跨历史正反 RED 与旧门退役，再决定是否扩展 A+B。现有六源预览维持默认关闭，不能被误读为 R16 方法语义或 CR03/CR04 一般完成。

## 18. A+B 第五离线切片：共用派生快照（2026-09-24）

用户已认可 §17 的方向并授权实施，旧句“建议还没有代码”是上一检查点。精确 RED、结构替代与旧门状态见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §9。当前默认关闭的离线 packet 内增加 `derived_snapshots`：显式选中的成功 `synthesize_time_series`/`transform_data` 回执、packet result SHA、原始/派生版本、父版本、实际帧指纹闭合后，才截取受行列/字符预算约束的 typed 单元格；身份闭合后若超预算，`snapshot_omissions` 在同 packet 明示原因。原六源两日表改为消费同一快照、再按综合回执专属覆盖事实复算；R16 型 12/120 可作为原始字段预览，但 `status=context_only`、`unit_status=not_confirmed`、`accepted_claim_ids=[]`，不能假装已经确认指标身份、方法解释或用户问题覆盖。普通 packet 与 AgentLoop/正式发布未接入；离线 packet 仍禁止进模型 prompt。没有新 planner、journal、浏览器框架、审核模型或 Provider 调用。

这不是 A/B 或原始 VP/IC/CP 的完成证明。R11 正确 D7/无 D30、R4 M03 图表/M04 非闭合假设、R16 完整 M05 方法表、R7—R21 错误单位/版本/算术及独立无据 99% 误放仍必须双向对照；尤其不能为补价值而从模型旧正文回填事实或让 Shadow 总审批。C 的真实 Shadow 调度、D 的默认发布切换、E3/E4 各需独立门。下一次续接先复核 HEAD/dirty、§9 和主计划 §0.1/Phase 6 四门，再检查定向与最新 full-offline 收据，不以本段取代历史矩阵。

本切片最终 E2 收据：定向七文件 **192 passed**；fresh `tmp/tprb25` full-offline **2921 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `06D71A3A7B812D80B5C98FE9E36D1C9D31296FF12D9731CF136801629E8A8900`，`provider_calls=forbidden`、实际 Provider initiated 0。`tmp/tprb24` 也全绿，但在预算遗漏说明补入前运行，不能替代最终收据。未经新精确冻结/显式授权，不启动真实 Provider；未运行浏览器 E3、push 或部署。

## 19. 第五切片后跨历史所有者复核与下一裁决

从 `main@f2ea7e3` clean 状态只读核对 R11 完整 M02、R16 已通过 M05、R4 中断 M03/M04 和当前独立 99% 正反夹具；事实、未闭合身份与拟议 RED/替代物/旧门见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §10。关键区别：R11 的 D7=0.1 有 `curve_fitting` 回执参数 `day/retention` 和成对点值，但无确认百分比单位，旧会话也没有终局 packet；R16 的聚合数值在派生帧、执行方法细节未进出版 facts；R4 M04 的新版本趋势事实有工具回执，却不能凭旧 evidence 的 `h_trend`/`h_level_shift` 别名授权真实假设 ID 的反驳。当前共用派生快照只对其中一类结果形状提供上下文，因此**不能因为 E2 全绿就切默认核心**。

下一步建议先裁决是否扩展同一 packet 的默认关闭“已执行结果身份”离线契约，并限定文本/行粒度的敏感字段披露、单位未证实只显示原始尺度、错误假设 ID 保持 `unassessed`。这不是新 planner/账本或模型审核；但它超出上一切片的派生帧快照类型，故先说明权衡再写代码。正式门的独立 99% 误放、C/D、E3/E4 仍原样未授权。

## 20. A+B 第六离线切片：回执执行身份与敏感文本遮蔽

用户已确认 §19 的通用离线方向。精确 RED、结构化替代/旧门及跨历史限界见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §11。当前 `offline_trust_projection.executed_results` 只在显式选中成功回执、source/result SHA、执行参数数据集/列、当前 workspace identity 与实际指纹闭合时，保留 `curve_fitting` 点对或 `analyze_time_series` 描述性数值；原始尺度、单位未确认、`context_only`、无 `answered`。R16 型聚合方法参数还须与派生 identity 的执行表达式严格一致，错误参数不冒充方法记录。所有任意文本单元格在派生快照中默认遮蔽，预算遗漏仍显式。无新 planner、账本、词表发布门或模型审核调用；普通 packet/AgentLoop/正式正文保持不变。**列名/数据集名仍可能含敏感信息**，尚不能把此离线预览当成生产披露审查通过。

R11 的历史正确 10% 仍只可在新离线结构展示为原始 0.1（单位未确认）；R4 M04 旧 evidence 的假设 ID 错配仍 `unassessed`；R16 旧会话没有在新 HEAD 重放。三份原始需求的价值保留与无据内容剔除双门尚未过，不能把本切片的 E2 当作 A+B 结束或默认发布授权。最终测试收据见跨历史记录 §11 的后续补记。

最终 E2：八文件定向 **197 passed**；fresh `tmp/tprb26` full-offline **2926 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `C2C6027389668BD902FC96100509A98F81FB88D237C20E07BAF989C383711C17`，`provider_calls=forbidden`、真实 Provider initiated 0。E3/E4、正式发布策略切换、push 和部署均未进行；下次续接先核实精确 HEAD/dirty 及跨历史记录 §11，不得凭旧 §17/§19 的“待裁决”反向撤销用户现已批准的离线工作。

## 21. 第七 A+B 离线切片与 Phase 6→7 接续门

用户已批准基于现有 `answer_bindings.v1` 的离线 typed 目标选择器。进入基线 `main@83dac2fb3d97c8d45c7a704517b4de31f4763577`、clean/ahead 67。RED、结构替代物、旧门和跨历史边界详见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §12。实现仅提供纯离线 `validate_offline_target_selectors`：回执/版本/列/点/原始值及同 source 事实闭合，可记已验证的**结果身份**，但用户子问题覆盖仍 `unassessed`；正式 parser 拒绝该字段，AgentLoop 不调用。没有真实 Provider、模型 Shadow 调用、正式策略切换或浏览器 E3。定向七文件 **188 passed**；fresh `tmp/tprb27` full-offline **2930 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `0790E1759F31306768DBA9456465834080DD7DD592C9F2E7F10A4D9ABCBED1B0`，Provider transport forbidden、initiated 0；仍仅 E2。

继续顺序：先对 R11 正确边界、R16 已通过 M05、R4 M03/M04 分项与 R7—R21 正反候选做同 packet 离线双轨，逐项标出可信值/方法/具体宿主缺口/关系的来源和无法恢复原因；随后才能评估 A 的价值保留与独立 99% 剔除是否同时满足。B 仍须验证 claim 级动作、故障回退、一次修订预算但保持 `publication_effect=none`。C 需独立 Shadow 调度、版本化提示/digest、统一 Provider 账本/预算、超时降级及误删/漏检校准；任何真实 Provider 执行前另做精确冻结并取得新的显式授权。D 的默认切换、受限处置、确定性复核和完整 Provider-disabled E3 还需用户单独裁决；E4 再另冻另授。Phase 7 只在旧检查族已有结构化所有者和回放证据后逐族启动，绝不能一次性删光散文门。**此时不能称 Phase 6 已完成或 Phase 7 已进入。**

给后续规划的粗估：在 A 的信息缺口不需要新增上游工具契约、C 的 Provider 冻结/授权及时取得、E3 未发现新系统级故障的前提下，A/B 跨历史校准及补齐约 1–2 周，C 的调度/离线校准及受控真实验证约 1–2 周，D 的裁决后接入/完整本地验收约 1–2 周，合计 **约 3–6 个工程周才可能进入 Phase 7**。这是工作量级估计，不是已获授权的日历日期；外部授权等待、原始需求价值无法从现有宿主证据重建、或 E3/E4 失败会延长。若 A 出现“可信且有用”不可同时实现的结构缺口，先向用户呈报取舍，不靠新词表或 Shadow 总审批抢工期。

## 22. B 门一次修订预算及 A 门待决证据（2026-09-24）

从 `main@3d5f6eaf0bec63826555a2d23ba38d2177cbc9eb`、clean/ahead 68 进入。现有纯离线审计动作可因两个均证据绑定的 finding 返回两个待修订 claim；RED/修复及跨历史 R11 复核见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §13。最小修复将 `targeted_revision_claim_ids` 限为首个有效 claim，仍只模拟、`publication_effect=none`；不调模型、不进入 AgentLoop、不接入正式处置。相关两文件 **20 passed**；fresh `tmp/tprb28` full-offline **2931 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `72B8C65B0ACED19F647B5AE7C346CA47472E0AAE3F7D0C3A5FC35DE64FE8F289`，Provider transport forbidden、initiated 0。

更重要的 A 门发现：R11 完整批次 M02 的旧 `answer_requirements` 与终局 `publication_packets` 都为空；当前提取器对真实复合请求也返回空，尽管同回执提供 day=7/retention=0.1。上一切片只能核验工具结果身份，不能把模型意图/旧自然句升为用户子问题权威，更不能将 0.1 无据换算为 10%。继续默认关闭的跨历史离线校准；先寻找已有宿主可验证的用户子问题及单位契约，若确实不存在，应与用户讨论新增上游契约或接受 `unassessed` 的价值损失，不能靠句式词表与 Shadow 总门填空。Phase 6 A/C/D 和 Phase 7 状态不因 B 的预算收紧而改变。

R16 M05 真实会话进一步显示多轮继承义务：首轮问订单记录数与 amount 总额，后续五轮是要求改变表达而不改变数字/范围/证据，末轮不再重复指标；其 `answer_requirements=[]`。下一 A 门复核必须检查既有 canonical history 是否已有可宿主验证的子问题继承及单位身份，不能仅从末轮文本或模型当前意图重建。详见跨历史记录 §13；若需新增此权威契约，先与用户对照三份原始需求裁决。

## 23. 第八 A+B 离线切片：canonical 来源锚点原型

用户已批准默认关闭的上游指标/单位身份契约原型，并要求以真实分析流程约束测试设计。进入基线 `main@93b652e176ddb3ebc2752f17be8281a7b226ea3c`、clean/ahead 70。RED、真实 R11/R16 限界、结构化替代及退役目标详见跨历史记录 §14。仅扩展现有离线 `validate_offline_target_selectors` 的可选 canonical history 校验：已有宿主持久化要求的来源消息哈希、稳定 ID/active 状态与同名工具列/点值闭合时，返回消息/列锚点和历史 SHA/revision；始终 `answer_coverage=unassessed`、单位未确认、`publication_effect=none`。普通 packet/AgentLoop/正式发布、确认政策、Shadow 和 Provider 均不接入。定向三文件 **173 passed**；`tmp/tprb29` 在最终 revision 检查前启动，不作最终收据，`tmp/tprb30` 因补真实 R16 多轮负例而主动停止；最终 fresh `tmp/tprb31` full-offline **2935 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `12F55B0200DF5AA216CF1EC5FF67C44B0A2C138B5B2AFE00356F522A46D4B049`，Provider transport forbidden、initiated 0。

不要把这个协议正例解释为 R11/R16 真实旧会话修复：两者旧 `answer_requirements=[]`；R11 的来源契约无百分比尺度，R16 的多轮风格任务没有可复核的要求继承关系。Workspace metadata 可由工具写入，不能作为单位确认。下一步若要赋予 `answered` 或单位转换，须先找到/建设真实生产链：来源元数据或已确认业务决定的版本化身份、用户子问题与指标/聚合/范围的关系、跨轮撤销条件；没有该链只能继续 `unassessed`。此项可能改变三份原始计划的价值/确认权衡，应先给用户看实际正反场景和设计取舍，不为某个测试夹具开新词表或隐藏模型审核。

## 24. 第九 A+B 离线切片：上游单位/尺度契约续接点

用户再次明确批准默认关闭的数据理解/确认记录契约切片，并提醒测试流程不得倒逼真实功能。精确 RED、历史 R11/R16 负例、结构替代、旧门与未验证来源路径，详见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md` §15。实现只扩展既有 `data_understanding.v1`：`_record_data_understanding_bundle` 的 `offline_measurement_scope=False` 默认不变；显式打开才由当前 Workspace 帧指纹、列和行数添加数据版本/源指纹；纯离线 `project_offline_measurement_contract` 再依据同 session/版本/列且已解决的类型化用户决定重建 `measurement_mappings`。普通工作区 `unit/context`、列名、数值范围、旧 bundle 自填映射、模型 EvidenceRecord 均无授权。冲突决定不按最新时间猜测，整列保持未确认。

这个协议尚缺**真实生产者**：当前上传格式不提供已解析的列单位声明；现有确认运行时也不自动产生 `host_measurement_mapping.v1` 问题。单测构造的 resolved record 只验证字段和失效规则，真实 R11/R16 确认快照均 `records={}`，不得宣称 0.1→10%、R16 12/120 的单位或正式 `answered` 已恢复。投影也不做百分比换算、自动暂停、Shadow 或发布接线。正式完整候选的独立无据 99% 风险、R4 M03/M04 价值、R16 方法上下文、R11 多轮/复合子问题关联仍属 A/D 双门未完成；C 真实 Shadow 调度与 Phase 7 旧门逐族退役均未获本切片授权。

后续先查真实上传是否存在明确机器可读的单位/尺度声明或实际用户已确认决策；若找不到，不为测试造 sidecar 或推断中文/英文单位。若要新增宿主确认生产者，应明确触发条件、用户可见数据集版本＋列、冲突/重载撤销和与 IC 原始需求的暂停边界，并在接正式发布前另行讨论。定向 **302 passed**；最终 fresh `tmp/tprb34` full-offline **2949 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `5D3F003C4B54F46221B0227746CBFD24D6038643C22D34DB6E162CFFA01051E7`，Provider transport forbidden、真实 initiated 0；仍仅 E2，详见跨历史记录 §15。`tprb32` 是补充生产者边界前的旧收据，`tprb33` 主动中止，不能冒充最终通过。续接时仍先核实 HEAD/dirty，别把本段写时状态当实时状态。

## 25. 第十 A+B 离线切片：多轮原文片段—工具列身份，非语义继承

用户选择先做多轮身份离线契约而不升级单位。精确历史 RED、结构替代、将来退役旧门及跨历史限界见跨历史记录 §16。既有 `intent.py` 可路由轮次，但不能证明用户在后续改写轮继续要求哪个旧指标；R16 首轮/末轮的真实文本在当前 requirement 提取器均为空。新纯离线 `validate_offline_multiturn_metric_links` 只验证旧请求逐字 span、源消息 hash、当前 canonical history 严格包含旧历史、已有旧 packet 与已执行回执/同名列、当前全部涉及数据版本/帧指纹。只从已有 `executed_results` 或 `derived_snapshots` 读取执行身份；不会把模型标签、中文近义词或用户“不要改变数字”推理成指标覆盖。可识别 R16 型 `amount` 字面列及工具函数列表，但始终 `answer_coverage=unassessed`、延续意图未评估、单位未确认、`publication_effect=none`；正式 parser 拒绝新增的离线提议字段。

重要续接事实：生产运行尚不持久化默认关闭的离线 packet，R16 旧终局包也没有该投影；测试用真实六轮文字和同形宿主结果验证协议，**不是**旧 R16 当前 HEAD 的真实通过。若下一步仍只是增加更多只返回 `unassessed` 的选择器，而没有真实用户子问题语义/继承的权威生产者，必须先停下与用户讨论，不要让 Phase 6 变成无限协议原型循环。正式独立无据 99% 误放、R11/R16 完整价值、R4 M03/M04、Shadow C、处置 D、Phase 7 均保持未闭合。定向 **168 passed**；最终 fresh `tmp/tprb35` full-offline **2953 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `6700C53EE3CD3FE89B335E1DD2C358935D939C3C31750BC6FC39A0ED0ADFBA90`，Provider transport forbidden、真实 initiated 0，仍仅 E2。详见跨历史记录 §16。

## 26. Phase 5/C 设计与离线校准：引用合法不等于语义真实

用户认可暂停增加 `unassessed` 选择器，先做 Phase 5/C 设计和跨历史离线校准；范围明确**没有真实 Shadow 调度、Provider 调用或正式发布影响**。完整 RED→结构替代→未来旧门及八会话实际 packet 盘点见 `docs/audit/2026-09-24-trust-reset-phase5c-shadow-design-calibration.md`。R4 M02/M03/M04、R11 M02、R14 M05、R16 M05、R21 M02/M04 归档合计 16 份 packet、0 个当前可行动 typed block，不能将其报成当前审计模型质量通过率。现有离线协议对合法 M02 claim/receipt 但虚假回测理由仍标 `claim_evidence_bound`，模拟可建议移除正确 claim，实际 `publication_effect=none`；真实 R16 旧 packet 的虚构 claim 则降 `advisory_only`。这两个结果只证明作用域校验和当前 Shadow 不影响发布，**不证明**语义 finding 正确。

后续先完成真实候选的同快照 claim/答案/用户子问题/回执定位和宿主只读 `audit_view` 设计评审；语义判断不可反向授予数值、单位、`answered` 或覆盖确定性失败。跨历史校准须分别计算误删正确 claim、漏检风险、独立可信内容保留与不可评估率；旧自然文本仅作为内容等价对照，不是当前 typed 回放。C 真实调度与预算/账本另设精确冻结和显式 Provider 授权，D 默认切换及 Phase 7 逐族退役仍独立。此设计记录没有修改运行时代码，不能据此声称 Phase 5/6 完成。

## 27. 已接受答案的默认关闭审计视图，不是 Shadow 调度

用户批准最小 `audit_view` 后实施了 `publication_audit.build_offline_audit_view`。它核验已有 `pub_` 包/正文 SHA、规范历史中同一已接受助手消息、同一包的工具结果 SHA，再用现有 typed parser/renderer 对每个 claim 重建唯一正文片段；只返回 claim/evidence/answer span 与逐字用户来源锚点，`answer_coverage=unassessed`、`publication_effect=none`。没有真实模型调用、AgentLoop 接线或正式发布变更。原 R16 M05 旧终局包离线实测仍是 unavailable/0 claim，不能把结构迁移的测试正例算成历史自然模型成功。该定位证明当前宿主重建文本与接受正文唯一同文，**未新增原位插入 span 持久化**，不能把它夸大为旧自然文本的完整来源证明；独立无据 99% 也尚未被正式门关闭。RED、限界、定向 **26 passed**、最终 fresh `tmp/tprb36` full-offline **2959 passed/1 skipped/16 warnings/0 failures**、JUnit SHA256 `107BFC5CF046543704D01376CB4BD421AC6B746467B61FB54A1C5710AA91A073` 详见 Phase 5/C 校准记录 §6。Provider transport forbidden、真实 initiated 0，仍仅 E2。C 真调度和 D 处置仍须独立门，Provider 仍须新冻结和显式授权。

## 28. 原位 trace 缩小 Phase 5 输入来源缺口，未推进到真 Shadow

从 `main@0fd91d1818c04ea8f06c0503c0e646214433f594` 进入，先复核两个相同宿主渲染 claim 无法靠全文唯一匹配定位，且 §27 的单个匹配不是插入来源证明。新增 RED 为 `render_bound_claims_with_trace` 缺失。最小改动复用原 renderer，在 typed 占位符原位渲染时捕获 claim ID、字符位置和片段 SHA，核对整个答案仍与旧 renderer 字节一致；把 trace 与最终正文 SHA、快照 digest 和规范 JSON digest 放进同一 `pub_` packet。旧候选重试先清掉 trace；离线视图只对已持久化的同包、同规范历史、同工具回执的 trace 赋予位置，允许相同文本在不同位置，缺失/篡改则 unavailable。没有改可见正文、没有接审计调度、没有 Provider 调用、没有第二账本或新 planner。详见 Phase 5/C 校准记录 §7；这不是 R4 的单例措辞补丁。

状态不升级：Phase 5 有协议、校验和默认无人调用的视图，但无版本化真 Shadow 调度/质量/成本证据。Phase 6 的 A 仍缺 R11/R16 正确价值、R4 M03/M04 分项的内容等价保留和独立无据 99% 正式剔除；B 仅纯离线一次修订预算模拟；C 真 Shadow 和 D 正式处置均未通过独立门。进入 Phase 7 前，先对 R7—R21/完整 R16/中断 R4 及本地真实会话做双向可评估率与正误损失校准，确定 A 的可信且有用边界；再完成 C 的版本化提示、同一 Provider 账本/预算、显式开关/超时/零调用保护和真正 Shadow 质量校准；D 需另获正式发布策略裁决、确定性复核和完整 Provider-disabled 内置浏览器 E3。只有每族旧散文门已有结构所有者和双向回放才可逐族开始 Phase 7，真实 Provider E4 另做新冻结并获显式授权。不能把本次 trace 的测试全绿解释为这些门已过。

本切片定向 **28 passed**；最终 fresh `tmp/tprb37` full-offline **2961 passed/1 skipped/16 warnings/0 failures**，JUnit `tests=2962/failures=0/errors=0/skipped=1`、SHA256 `CDBFEC1E100026895F0A3F43DE8FF44C40591331AC73E1568EC5DBBC64597B1E`。入口 `provider_calls=forbidden`、真实 Provider initiated 0；仅 E2，未做 E3/E4、push 或部署。

## 29. 当前 HEAD 的完整 Provider-disabled 浏览器批次与真实冻结前停止门

在 `main@e05d957b85b2f42e6643c20e578c1156dfb933b9`、无列出的工作树改动下，按根 `AGENTS.md` 的唯一 rehearsal 入口和 `iab` 单 tab 执行 B01—B06、IC-B01—B06、CONTENT-B03/B07 全批。目录 `tmp/trust-reset-e3-20260924-e05d957-r1`，PID 12452、端口 5227、保留 exec session 86678；服务已按原会话停止，证据未删除。16 个会话最终 run_state 为 14 completed、预期 B06-BUDGET failed、预期 B06-SAVE unknown；六源与富内容的压缩/刷新/导出、741 像素无整页溢出、控制台 0 warn/error 均有记录。`runtime.jsonl` SHA256 `3C40959DD22A97C01BE1CAF1EF4C822461460665F08A358CCF5BC57ED5EB2ABF`、`forbidden_provider_transport=0`、真实 Provider initiated 0。逐轮 SSE terminal 没有独立持久化轨迹，不能把 UI/run_state 收口夸写成终态事件唯一证明；这也不是自然模型或 Phase 6 D 的验收。完整会话映射、证据和限制见 `docs/audit/2026-09-24-trust-reset-current-head-browser-rehearsal.md`。

E4 **尚未**执行预检冻结或真实调用。现有 P08 contract 把 M02 D7 硬写成 `10%`，与用户已经裁决的“原始 0.1 尺度、单位未确认；仅有明确单位证据时转换”冲突；M04 failed-v2-upload 硬断言却无对应 frozen action。先与用户确认这两项契约修订，再在修订后的新 HEAD 上通过既有零调用 preflight 精确冻结 model/endpoint/prompts/fixtures/oracles/budget/ledger/run-dir，另获显式真实 Provider 授权。不得沿用 R4/R16 的模型、端点、额度或授权；更不得为赶阶段把 Shadow 当总审批门。Phase 5 真调度/质量、Phase 6 A 的双向价值保留与正式无据 99%、C/D 独立门、Phase 7 逐族退役仍未闭合。

后续授权更新：用户已明确同意上述 M02 原始尺度和 M04 主矩阵范围修订，并授权**这一次**在修订提交、零调用精确冻结和可行性核对通过后直接执行真实 Provider 完整矩阵，不必再为相同冻结等待重复授权。若模型、端点、调用上限、提示/夹具/oracle、源提交或账本路径不一致，仍先停止；该授权不扩大到追加场景、局部重跑、push 或部署。原段的“另获授权”是此前时点，不能覆盖本段新用户裁决。

M04 后续协议裁决：用户同意仅 M04 分两阶段上传；v1 首轮前、v2 在首轮终态后同会话第二轮前，两个阶段各走可见标签与一次 filechooser。其余场景仍一次上传。此规则须写入冻结 contract；不能预加载 v2 冒充后来换版本。旧 `1f4327e`/`r2` 离线收据仍是修订前时点，最终身份以新提交和新收据为准。

## 30. 修订后真实 P08 全批已执行、验收失败；下一门仍是双向结构校准

`main@b70fbc35e212ed4d5389205d1a3ee9d801e2065f`、完整 clean 源码及最终 E2 后，既有 P08 runner 零调用 preflight 精确冻结成功。按用户对本批的真实 Provider 授权与 M04 两阶段上传裁决，在 Codex `iab` 单 tab、端口 5228、隔离目录 `tmp/trust-reset-p08-real-20260924-r1` 顺序执行 M01—M06，未中途改代码/提示/夹具/oracle、未局部重跑。M06 口径 B 的浏览器提交先被权限审查拦截；用户随后**另对会话 `4656c27b3f5a` 的 B 提交明确授权**，同卡片原按钮提交并只恢复一次。最终 82 started/82 dispatched/0 failed，低于 120 上限；服务同 session 停止且端口关闭。完整 freeze SHA、账本/审计 SHA、六个 session ID、报告导出、确认记录与人审差异见 `docs/audit/2026-09-24-trust-reset-p08-real-batch-r1.md`。

**E4 判定 `executed_failed / not_accepted`，不是未执行也不是 6/6。** 既有审计器阻断 M02 的未绑定占位符/无成功 publication 导出、M04 的结构化假设审计失败；M02 原始尺度的数值项按修订契约为 `unassessed`，人审确认候选仍误写百分比。M01/M03/M05/M06 最终 run_state 为 completed，但 M03 的两日事实旁错写“七天跨度”，M06 缺失数据集的单一下一步旁再给第二路径；M05 和 M06 还有未证业务解释需逐句核对。四个成功 packet 的 `answer_render_trace.entries=[]`，不能把未走 typed claim 的自然正文当已受 claim 审计。工具消息配对均闭合、浏览器 console 0 warn/error；没有持久化逐条 SSE terminal 序列，不能独立宣称事件恰好一次。

下一实施门暂不接正式发布/Shadow：先把本批与 R7—R21、R11 正确 D7/无 D30、R16 完整通过 M05、R4 中断的六源/假设及独立 99% 双向校准，分别计正确价值保留和无据事实剔除。新 RED 至少含 M02 schema 围栏/ID 与单位不符、M03 可信表格旁错误范围、M04 guard 引用未展示假设 ID 且 R4 关系别名未被真实宿主接受、M06 单步路径和 `amount` 业务口径。结构化替代仍须复用既有 packet/receipt/`answer_bindings.v1`/宿主假设状态；拟退役门是自由散文借单条合法 binding 获整篇权威，不是削弱单位/版本/算术硬门。每个代码切片前先给 RED→替代物→旧门和跨历史正反分母；若必须让可信核心删掉 R11/R16/R4 已证价值，或只能让 Shadow 做整篇随机审批，应停下与用户裁决。Phase 5 真 Shadow、Phase 6 A/C/D 及 Phase 7 仍未完成，本次授权不能用于再跑 Provider、push 或部署。

## 31. Phase 4 纠偏：关系提议须按现有宿主规则闭合

`main@26c223d` 后重读重置总计划及 VP/IC/CP 三计划，跨 R21 的 task 非阻断正例、R4 M04 别名负例与本次完整 E4 M04 缺 ID/缺关系，定位 Phase 4 遗留结构漏洞：旧完成门只看 `competing_hypotheses` 非空，R4 的 `h_trend/h_level_shift` 从未匹配持久假设 ID；`hypotheses_prompt_brief` 也未显示真实 ID。这不是新措辞误判，不能要求模型猜 ID 或撤销显式假设的审计义务。

最小修复沿用既有 hypothesis validator，对当前 plan 和新鲜 EvidenceRecord 重算关系后才认可结构完成；有界摘要及 guard 后续轮次展示当前真实 ID，晚到的 plan 仍用既有宿主生产者刷新。未完成 task 仍不阻断，普通任务和正式自由散文发布不变。详细 RED（3 failed/33 passed）、替代物、退役旧门、最终定向 45 passed、Windows 长路径导致的非产品 full-offline 失败和剩余风险见 `docs/audit/2026-09-24-trust-reset-m04-validated-relation-correction.md`。最终 fresh `tmp/tp4a2` full-offline 为 **2969 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `FB56F3DDF2409BC8B2C301622747ED62E0DAAC472A3BB51C4D7F2A37926C42A0`、Provider forbidden/initiated 0。Phase 4 状态由“笼统完成”改为“task 边界完成，关系审计 E2 纠偏；E3/E4 待验”，不提前进入 Shadow/D/Phase 7；R11/R16/R4 正确价值与独立无据 99% 仍是 A 的双向门。真实 Provider 授权已用完。

`main@5467897` 的 Provider-disabled E3 尝试在矩阵前因官方 `iab` 浏览器桥接 `Unable to load browser request-header policy` 阻断；本地服务 PID 18572/端口 5229/exec session 59389 曾健康且 `provider_enabled=false`，现已停止，`tmp/tp4e3r1/runtime.jsonl` 只有启动事件、真实 Provider 0。未导航、上传或执行场景；恢复官方绑定后须新目录完整矩阵。详见 M04 纠偏记录末节，不能把此次记为 E3 失败场景或通过，也不能换自动化栈。

## 32. A/M03 通用比较数值与 Phase 4/M04 原值证实

用户批准在 `main@3539067b5bb2a020fcf0b5615867b25f6e063fc5` 后做两处最小实现，完整跨历史 RED→结构化替代→退役旧门、测试失败前提和结果见 `docs/audit/2026-09-24-trust-reset-phase5c-shadow-design-calibration.md` §9。A 仅在显式 `offline_workspace` 的同一个默认关闭 packet 中，按已选 `compare_periods` 回执、源事实 SHA、数据身份与当前帧指纹复算逐来源两期值、差额、相对变化、记录数；原始尺度、单位未确认、`answer_coverage=unassessed`、`publication_effect=none`。这帮助保留 R4/E4 M03 的可核验数值形状，但旧自然正文的“七天跨度”及旧 packet 仍非 typed 正例，R11/R16 完整正确价值未等价重建。

Phase 4 现在将模型 EvidenceRecord 的 measurement 视为候选：只有同数据版本且经原 `compare_periods` 或 `analyze_time_series` 回执 detail digest 和指标数值验证的描述性测量，才能赋予正式假设关系 `supported/refuted`；因果/统计推断不可借描述工具的模型标签升级。真正假设 ID 下的未证实关系会留在 `relation_candidates`，作为可审计的 `inconclusive` 交付而不反复要求同一种无从补证的关系；错 ID/指标仍触发 guard。它收紧权威，不取消显式竞争假设 plan 审计，也不另建 planner 或模型门。

最终定向 **87 passed**；fresh `tmp/tp4a4` full-offline **2972 passed/1 skipped/16 warnings/0 failures**，JUnit SHA256 `4D2ED505DEC58C9C3929EC6900983E7389B50C4946FB1F00952A86356F576547`、真实 Provider initiated 0。先前 `tp4a3` 的 3 个旧无回执夹具失败已按新前提修正，不能引用它作为最终通过，也不能隐藏。此切片仅 E2，没有当前 HEAD 的完整 E3 或新 E4；正式自由散文旁侧 99%、Phase 5 真 Shadow、Phase 6 A/B/C/D 的完整验收及 Phase 7 均未获本收据授权。继续时先核对新 HEAD/dirty、三份原始需求和 §9 的跨历史分母；若必须改变默认发布或新增语义身份生产者，先和用户确认，真实 Provider 必须新精确冻结和新授权。

## 33. Phase 2/M02 回执生产到宿主渲染的默认关闭离线切片

用户在只读重定界后批准先保留 M02 已执行曲线的封闭结果，并在缺少可信中文子问题身份时继续标 `unassessed`；未批准改变正式发布或调用真实 Provider。从 `main@3d71bfaefb6c88bf1ea947ea22117d479c3962aa`、工作树无列出改动进入。当前完整 E4 的 M02 `ffb95bc5a766` 留有 `curve_fitting` 回执 `tr_d593c760494c`，却没有成功 packet：模型候选使用普通 `json` 围栏、`bindings` 数组和 `C1/C2`，引用为空，且把原始 `0.10` 写成未获单位授权的 `10%`。R11 的正确 D7/无 D30 旧正文、R4 被误拒的正确情景、R16 已通过 M05 与六来源/假设正例，以及独立无据 99% 仍是双向校准背景；旧自然输出不能倒填为现行 typed 通过。

- **RED**：新增 `tests/test_m02_receipt_claim_production.py` 的首轮定向是 `3 failed`，均因缺少宿主生产者；它要求当前回执可形成有效 typed blocks、原位渲染和 trace，错/缺回执不能形成候选。不是新增中文措辞词表。其后扩展归档 E4 回执只读重放、单位/时间点、数据版本和旧路径负例。最后针对畸形 `fact_refs=[{}, {}]` 再固定 `1 failed`（旧代码抛 `TypeError`），修为校验不通过而非异常逃逸。
- **结构化替代**：`produce_m02_receipt_claim_candidate` 只在调用方显式选中同 packet `curve_fitting` 回执时生成既有 `answer_bindings.v1` 候选；`descriptive_fit` 可携带同一回执的 `points[i].x/y` 事实引用，宿主按当前源 SHA、同数据集版本 ID/指纹、观测末端、有限数值及原拟合契约核验后渲染 `x=7 / 0.1` 原始尺度。仅在显式传入区间外整数时另生成 `scenario_extrapolation`，由原 renderer 复算族参数、R² 和未验证披露。测试调用现有 `AgentLoop._render_finalized_publication`，同 packet 得到 2 个 accepted typed blocks 和 2 条原位 trace。这里的 `x=7` 不推断中文 D7 指标身份，`requirement_refs=[]`，覆盖继续 `unassessed`。函数没有接入普通 AgentLoop 调用点，正式发布默认保持原样。
- **正反边界**：归档 E4 真实回执重放可保留原始 `0.1`、未知单位及可选 D30 情景；单独无据 99% 不进入宿主候选。外来/缺少回执、缺 x/y 点对、缺版本指纹、错单位状态、区间内或布尔情景点、旧 packet digest 均 fail closed。现行完整自然候选仍可能误放独立 99%，R11/R16 的旧多轮语义价值也未被本切片等价重建；**没有退役旧散文门**，未来目标仍是逐族移除“单条 binding 授权整篇散文”，不削弱数值、单位、版本或回执硬门。
- **收据**：受影响五文件定向最终 **46 passed**。第一次 fresh `tmp/tp2m1` full-offline 是身份锚点加入前的 **2977 passed/1 skipped/16 warnings/0 failures**；`tmp/tp2m2` 为畸形引用 RED 前的 **2978 passed/1 skipped/16 warnings/0 failures**，两者都不能作为最终源码收据。最终 fresh `tmp/tp2m3` 为 **2979 passed/1 skipped/16 warnings/0 failures**，JUnit `tests=2980/errors=0/failures=0/skipped=1`、SHA256 `556C9948FA84F7D932108EFD8B67E998341023935879F623CC3542BC34E5418A`，runner `provider_calls=forbidden`、实际 Provider initiated 0。没有新 E3/E4、Shadow 调度、正式处置、push 或部署；Phase 2 仅补一条默认关闭的生产路径重放，不可标为自然模型闭环完成，也不升级 Phase 5/6/7。

## 34. Phase 5/C Shadow 请求身份的纯离线准备

从 `main@9932118317ce347e6582b7c891290a7ed3d3da54`、无列出改动进入。用户要求继续实施至 Phase 6；此前对正式默认发布的目标取舍和真实 Provider 的精确冻结/单次授权仍是独立门。A 的 R11/R16 语义价值、正式独立 99% 误放及旧 E4 的 0 typed block 没有因本切片消失。

- **RED**：已接受回答虽有宿主原位 trace，尚无可复核、版本化且受预算的 Shadow 请求构造边界。新测试先因 `build_shadow_audit_request` 不存在而在收集期失败；不能用旧自然会话或模型自报 claim ID 代替落盘 trace。
- **结构化替代**：沿用 `build_offline_audit_view` 的同 session 持久 packet、canonical history、当前回执和原位 trace 校验，只把定位成功的 typed claim、回执引用、逐字用户片段锚点与未评估覆盖组成 `publication_audit_input.v1`。固定 `publication_audit_shadow.v1` 指令、prompt SHA、精确输入 SHA、view digest 和 24 KB 输入上限；自由散文不进入 claim 处置对象，旧/篡改/无定位包返回 unavailable。请求仅是纯函数结果，`publication_effect=none`，没有 Provider 调度、额外账本或发布变更。
- **退役目标与边界**：将来退役的仍是“一个合法 binding 授权整篇自由散文”；本切片未退役正式散文门，也没有证明审计语义理由真实。即使引用合法，模型凭虚假理由建议 remove 正确 M02 claim 的旧 RED 仍存在；C 需要真实 Shadow 的正反质量/成本校准，D 还需用户对默认发布和受限行动的裁决。测试中的单个可定位合成 claim 不能当作 R4/R11/R16 旧会话已可审核；真实 Provider 0、E3/E4 未运行。
- **收据**：初始导入 RED 后，定向审计/准备三文件 **30 passed**；fresh `tmp/tp5c-request-r1` full-offline **2981 passed、1 skipped、16 warnings、0 failures**（353.98 秒），JUnit SHA256 `38DE6ED00B1C50D205A95EC22607165DF59FF4C884E3E71DDB0308B7989F6338`，runner `provider_calls=forbidden`、实际 Provider initiated 0。只属 E2；尚无审计调度、成本/误删率收据或新 E3/E4。

## 35. 上游真实业务映射确认生产链（仍不改发布默认）

用户明确选择：**只有会改变结果的真实业务映射歧义，才用既有确认流程问一次；同一数据版本复用，skip 保持 `unassessed`**。R11 的中文“留存”↔`retention`、原值 0.10 的尺度，及 R16“订单记录数”↔行数/去重 ID 提供双向背景；旧会话没有该类型决定，不能倒填为通过。进入 HEAD `main@3df2591999d86e8147591f2f5fab3efe64a29e2a`、无列出改动。

- **RED**：现有 `host_measurement_mapping.v1` 仅是人工构造的离线确认记录；无真实提问生产者。新测试先因 `build_measurement_mapping_candidate` 不存在而收集失败。随后发现同 scope 被用户 skip 后，新轮请求复用了同一个 confirmation ID 却有不同 turn ID，既有服务正确拒绝冲突；修为每次提问不同 ID、同业务与数据版本共用决定 key，已解决记录仍只复用一次。现有 AgentLoop workspace 是 scope-enforcing proxy，最初按裸 `Workspace` 判型导致宿主入口 fail closed；测试定位后允许官方 proxy 并在真实 context scope 内验证。
- **结构化替代**：模型仅可通过现有 `ask_user_question.measurement_mapping` 提议三个指针（用户逐字片段、数据集、数值列）。宿主重算 canonical history、唯一用户原文来源、当前 Workspace 的版本/源指纹/实际帧指纹及列类型，覆盖模型的提问文本/选项，生成面向业务的四个选择：小数比例、百分数原值、对应但尺度未确认、不对应/无法确认。无多问题拼接；伪 span、外来列、异常身份均不暂停也不授权。原 `QuestionPolicy`/`ConfirmationService` 持久化；同版本已解决决定复用、已 skip 决定不再重复暂停且保持未评估，数据版本变化才可重问。`project_persisted_measurement_contract` 从现有确认事件存储读已解决记录，重建同一宿主 candidate 并核对历史、选项、问题、版本、决定 key；只有明确选择 fraction/percentage_points 才投影当前列单位，raw/unconfirmed/skip 不证实单位。没有第二确认账本或新模型调用。
- **退役与停止门**：本切片没有退役“一条 binding 授权整篇散文”的正式旧门，也没有让确认记录自动生成 `answer_requirements`、`answered` 或 M02 typed 观察 claim。真实 R11/R16 历史无此决定，R16 行数/去重口径也不由这项列尺度确认自动解决。模型何时提出真实歧义、确认展示/恢复的 E3、自然 Provider 行为及成本仍待后续验收；D 正式默认、C 真实 Shadow 和 E4 独立门未动。确认仅能证明用户选择的映射，不能替代工具数值/版本/方法证据。
- **收据**：定向确认/映射/发布相关 **120 passed**；加入同版本 skip 不重问规则后定向 **93 passed**。`tmp/tp2-semantic-confirm-r1` 在发现重复提问风险后主动中断，不作完成收据。最终 fresh `tmp/tp2-semantic-confirm-r2` full-offline **2987 passed、1 skipped、16 warnings、0 failures**（478.57 秒），JUnit SHA256 `2C158DBA311FA75B9BBCD9615020C5321356A4380A4FA0096BA59440F2186A63`，runner Provider transport forbidden、实际 Provider initiated 0。仅 E2，不等于新 E3/E4 或阶段退出。
