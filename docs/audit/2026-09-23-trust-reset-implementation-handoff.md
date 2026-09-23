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
