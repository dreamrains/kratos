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

1. **先扩展 typed claim 覆盖，再谈完整 Shadow。** 已插入简单数值 `observed_fact` 垂直切片；随后按用户裁决增加同工具事实身份授权的 `derived_metric` 切片。两者都沿用 `answer_bindings.v1` 唯一占位符、同快照 requirement/fact 精确结构身份，宿主在正文原位渲染原始尺度。派生量还必须与同回执结果同值、重算运算并核对数据版本；EvidenceRecord 模型可填的标签不能单独授权。普通 legacy 块仍不具有 `answered` 权限；Phase 5 validator 目前仍故意只允许 M02 `scenario_extrapolation` 形成可行动建议，其他意见 advisory。后续要继续在同一 binding 通道扩展比较、拟合、明确缺口等 claim 的宿主校验，不新开传输/存储通道。每一族先回放 R7—R21/R4 的正确与错误候选，验证单位、版本、强度、证据引用；不能用新的措辞词表代替 claim。派生切片详见 `docs/audit/2026-09-23-trust-reset-derived-claim-slice.md`。
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
3. 完整 Shadow 前的下一个 RED 包：单一问题未抽出 requirement、与明确子问题不同句的独立裸数字/无数值的过强结论、比较/描述拟合中正确事实被散文门误删、错误事实借同快照不相关引用放行、多来源和数据版本切换、明确 gap 与独立正确 claim 共存，以及**无效 binding 经一次修订仍失败时如何保留其它独立可信 claim**。已抽出 requirement 同句的第二个裸数字和跨句 gap 洗白、工具已有事实身份的简单派生量均有 RED/GREEN，不要重复做同一种词法特例。必须先在三份原始需求与 R7—R21/R4 历史候选上校准，不能只追最新被中断的 R4 单例。逐族给出“RED → 结构化替代物 → 将退役旧门”，检查正确 claim 保留率和拒绝原因；涉及语义取舍无法封闭证明时先向用户说明并确认，不靠词表或 `overall=pass`。
4. 浏览器 E3 只按根 `AGENTS.md` 现有 Provider-disabled rehearsal + `iab` 完整矩阵执行，不能局部重跑冒充完整批次。E4 仍需在新精确提交上完成零调用冻结与用户新授权。无 push/部署授权。

## 5. 派生 claim 后续检查点（Shadow 仍未启动）

用户确认模型可填的 EvidenceRecord `metric/claim_key` 不能单独授权 `answered`；仅同一当前工具回执的指标 fact 身份有效。第二个插入切片已沿用 `answer_bindings.v1` 增加 `derived_metric` 的工具 fact + derived ref + 宿主复算/版本/同值检查，并在占位符原位渲染原始尺度；版本核对只覆盖该派生真正引用的操作数，不因无关测量阻断。详细 RED、退役旧门及限制见 `docs/audit/2026-09-23-trust-reset-derived-claim-slice.md`。定向五文件 189 passed；`tmp/tprb7` 在最终作用域收窄前全量离线 2869 passed、1 skipped、16 warnings、0 failed，JUnit SHA256 `52B5AE03893D2ABD388A7C250DA44A77B7FCF1139495BAF66F958D38501B85E2`，只证明前一代码快照。最终实现 `tmp/tprb8` 完整离线为 **2870 passed、1 skipped、16 warnings、0 failed**，JUnit `tests=2871/errors=0/failures=0/skipped=1`，SHA256 `C573A466350818F1AFF8722DCDDB2C45ADDE9D13015B5C4F82251060D13A15DF`，runner `provider_calls=forbidden`。这仍是 E2；未跑浏览器、真实 Provider，也未把 Shadow 接入发布。后续继续从比较/拟合及单一问题覆盖的历史正反例推进，先给 RED/结构化替代/旧门退役，再改代码。

## 6. CR07 独立可信 claim 的失败后保留

第三个插入切片针对“有一条错误 binding，修订一次后仍失败，正确 claim 也被全局错误吞掉”的实测 RED。只在修订额度已用尽且当前候选失败时，宿主从同快照已通过 parser 的 typed blocks 逐条重新验证/渲染；无效块与自由原文不复制，未核验子问题保持 `unassessed` 并在正文原位列出，连一个可信块都没有则继续非成功。这个边界不会增加模型调用，也不把末尾免责声明当纠错。详细历史、三联门和限制见 `docs/audit/2026-09-23-trust-reset-partial-publication-slice.md`。相关六文件 205 passed；`tmp/tprb9` 最终完整离线 **2873 passed、1 skipped、16 warnings、0 failed**，JUnit `tests=2874/errors=0/failures=0/skipped=1`，SHA256 `4054E729530292EBF93DCA89172363813E2DEE5A7E6AE59CC34F8611293B1F90`，runner `provider_calls=forbidden`。浏览器 E3、真实 Provider E4、Shadow 调度/处置仍未启动。

## 7. 单项请求、真实会话与意图识别复核

用户补充提示本地真实会话及既有意图识别。本轮只读核对 `sessions/9810fe7bacf6`、`9959216b6a4a`、`8ddfa3029b15` 等不同形态，以及 `TurnIntent`/`llm_intent`：现有意图只输出粗粒度路由/歧义；`analysis_spec.metrics` 在真实会话里可为泛化 `retention` 或占位 `target_metric`，均不能担当指标身份。样本不当正确答案 oracle，也不只盯中断 R4。详细 RED、初版“请给出结论”误伤、用户第二次裁决、结构化替代与残余风险见 `docs/audit/2026-09-23-trust-reset-single-metric-intent-slice.md`。

用户最终裁决仅当前工具回执的唯一精确指标身份能把单项候选升级为可硬验 requirement；无匹配或多义时 `unassessed`，不自动输出指标缺口。初版直接句式自动缺口渲染因误伤已撤销，反例保留；CR07 局部发布也不能把软候选列为失败硬项。此切片沿用现有 requirement 与 `answer_bindings.v1`，不增加意图模型调用或新的词表；定向五文件最终 **199 passed**。`tmp/tprb10` 的 2879 passed/1 skipped/16 warnings 仅证明局部发布边界再次收窄前的源码快照。最终 fresh `tmp/tprb11` 全量离线为 **2880 passed、1 skipped、16 warnings、0 failed**；JUnit `tests=2881/errors=0/failures=0/skipped=1`，SHA256 `0F35FBBAC0E71C1F9003846D5C46C742B15E8E7660B54F5F68198042C69A86BB`，runner `provider_calls=forbidden`。无同名回执时的自由散文无据数字仍是未关闭的通用 claim 发布缺口，不能把此切片记为完整 CR03/Shadow 通过。确切提交待本切片收尾后补记；E3/E4 仍未做，真实 Provider 仍需新精确冻结和显式授权。
