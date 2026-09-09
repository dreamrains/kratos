# 分析价值保留：阶段记录

按 [总计划](../../superpowers/plans/2026-09-06-analysis-value-preservation-plan.md) 第 6 节的流程维护。每个阶段一段记录；详细验收结果按模板写入本文件，状态汇总同步回总计划第 7 节。

---

## P0：冻结范围与接口决策

阶段 / 状态：**passed**（2026-09-06）

### 1. 基线决策（对总计划第 3 节的更新）

- **实施基线切换为 `origin/main` = `36bca25a44a25c99ef8bb7bf56312bde05736ba2`**（提交 `feat: harden analysis runtime and rebuild offline regression`），依据用户 2026-09-06 明确指示："从远端的最新版本为基础，基于四份文档继续本次优化"。
- 工作分支：`vp-analysis-value`（自 origin/main 创建）。**本地 `main` 保留在 `93b1b6f` 不动**，作为原 35 个提交历史的存档；原工作区 7 个未提交文件（A06 矩阵工具链修改）保存在 stash `preserve: A06 matrix harness uncommitted changes before rebasing to origin/main 36bca25`，未丢弃、未提交。
- 诊断 D01—D10 的源码锚点在新基线**全部成立**：12 个被引用源码文件与诊断记录的 SHA-256 完全一致（`src/` 在两基线间仅 report.py/sandbox.py 有差异，均不在诊断范围内）。33 项探针观察在 `36bca25` 上重跑全部复现（`tmp/diagnosis-20260906/probe.py`，provider_calls=0，forbidden_client_attempts=0）。
- 新基线快照：[2026-09-06-vp-p0-baseline-36bca25.json](../../audit/2026-09-06-vp-p0-baseline-36bca25.json)（351 个受控文件，聚合 SHA-256 `2d471a05f8465176743267d60bf957ed9f5e1b860d0f88aee15150b9b79e6dd8`；逐文件哈希在同名 `-files.json`）。原规划快照（针对 93b1b6f）保留作历史对照，不再作为变更识别基准。

### 2. 与计划文档的偏差记录

| 计划原文 | 新基线现实 | P0 处置 |
|---|---|---|
| 验收矩阵 §14 引用 `scripts/acceptance/offline_test_runner.py` | 该目录在 36bca25 已整体退役；离线入口为 `scripts/testing/run_regression.py`（quick/full-offline/slow-offline，强制 Provider 禁用环境变量，run-dir 必须是 tmp/ 下新路径） | 后续所有阶段回归命令改用 `scripts/testing/run_regression.py`；矩阵 §14 的命令模板视为已被替代 |
| 验收矩阵 §13 引用 `tests/test_local_publication_acceptance.py` | 该文件在 36bca25 不存在 | N 系列用例全部映射到 `tests/test_publication_synthesis.py` 与 `tests/test_sse_publication_order.py`（见 §4） |
| 规划快照的 402 个受控文件清单 | 新基线 351 个（矩阵工具链、A06 审计件、replay fixtures 不在本基线） | 以 P0 快照为准 |
| 工作区"A06 未提交修改不得回滚"约束 | 基线切换使该约束的对象转入 stash，产品源码两基线一致 | stash 保留原样；本专项不再触碰这些文件 |

### 3. 输入基线验证

- quick 套件：`run_regression.py quick` → **184 passed**（tmp/vp-p0-quick-baseline）。
- 诊断探针重跑：33/33 观察组复现，0 Provider 调用。
- full-offline 套件（第一次，tmp/vp-p0-full-baseline）：**1 failed, 2392 passed, 3 skipped**。唯一失败为 `tests/test_test_suite_hygiene.py::test_retired_acceptance_harness_does_not_return`——该测试断言退役的 `scripts/acceptance/` 目录不存在，而基线切换时工作区遗留了未跟踪的 A06 文件 `freeze_matrix_a06r3.py`（该文件在任何分支中均未被跟踪，不属于新基线）。处置：移入 `tmp/a06-untracked-archive/` 保存（未删除），清空目录后该测试单独复跑 **7 passed**。
- full-offline 套件（清理后复跑，tmp/vp-p0-full-baseline-r2）：运行中，完成后按实际落盘 JUnit 在下方补记；补记前不得引用任何数字。

full-offline-r2 补记（2026-09-06）：**2396 tests, 0 failed, 0 errors, 3 skipped**（JUnit：tmp/vp-p0-full-baseline-r2/junit.xml，退出码 0）。3 个跳过为套件既有条件跳过，与 D01—D10 无关。输入基线判定为绿。

### 4. 验收矩阵用例 → 测试位置映射（84 项）

原则：优先落在矩阵 §13 列出的现有入口；新文件仅在现有文件主题不符时新建（新建项标注 ★）。

| 用例组 | 测试文件 | 说明 |
|---|---|---|
| I01—I06（意图快路径/复合/否定） | `tests/test_intent_classification.py` | RED 新增；I04/I06 的语义层路径在 `tests/test_llm_intent.py` 补 mock 路径 |
| I07—I10、I12（范围/粒度/阻断） | `tests/test_intent_refinement.py` + `tests/test_analysis_entry.py` | 两层各自断言：细化层过滤 scope、入口层保持现有 active_dataset 行为 |
| I11（不越宿主 scope） | `tests/test_project_intent_context.py` + `tests/test_analysis_entry.py` | 现有 scope 机制回归 + 新反例 |
| S01—S08（输出策略） | `tests/test_synthesis_policy.py` | 中文建议关键词等价、深度解耦、降级条件建议 |
| N01—N09、N11（正文发布检查） | `tests/test_publication_synthesis.py` | 主张定位、D30 类边界/补数/条件建议、跨源范围、检验元数据绑定 |
| N10、N12（修订/失败路径 + SSE/保存一致性） | `tests/test_sse_publication_order.py` | 一次受预算修订、失败不污染最终消息、流式与同步一致 |
| C01—C08（校准） | `tests/test_verification_layer.py` + `tests/test_stage3c0b_verification_compatibility.py` | n<30 一刀切移除、时间窗结构化、逐工具检验元数据；C08 加 `tests/test_system_data_analysis_quality_audit.py` |
| E01—E05、E09（发布包选择/覆盖/缓存失效） | `tests/test_publication_synthesis.py` | 先过滤后选择、事实组配对、省略记录 |
| E06—E08（压缩持久化/碰撞/二次压缩） | ★ `tests/test_compact_preservation.py`（新建） | 现有压缩断言分散在 test_analysis_quality/test_slice5 等，持久化语义需专门模块 |
| E10（预算耗尽部分完成） | `tests/test_execution_control.py` | 与既有预算保护合流 |
| H01—H12 | `tests/test_hypotheses.py` + `tests/test_trust_workflow_runtime.py` | H01—H05/H10 为 P1 RED；H06—H09/H11—H12 为 P5 |
| A01—A08 | ★ `tests/test_audience_adaptation.py`（P6 新建）+ `tests/test_phase4.py`（熟练度既有回归） | audience 与 proficiency 分离后新模块 |
| U01—U04（投影层） | `tests/test_slice6_workbench_minimal.py` + `tests/test_multifile_workbench_view.py` + `tests/test_trust_view.py` | 更新最简契约测试以匹配新产品原则（保留防升级与会话隔离断言） |
| U05—U08 | L3，归 Codex（B 场景驱动） | 本地准备投影层测试；浏览器验证不在本专项执行 |

### 5. 逻辑字段 → 现有字段映射冻结

依据实际读取的源码（非文档假设）：

| 设计逻辑字段 | 冻结为 | 现有载体 |
|---|---|---|
| 假设身份 | `id`（`{set_id}_h{n}`）+ `dataset` + `route`，P5 增量加 `plan_id` 绑定 | `hypotheses.py::_hypothesis`；set 级 `plan_id` 缺失即 P1/P5 要补的绑定 |
| hypothesis_relations | 保留 `supporting_evidence_ids` / `conflicting_evidence_ids`（扁平 id 列表，向后兼容）；P5 增加 `evidence_relations` 结构化列表（evidence_id、relation、basis、scope）逐项校验 | `hypotheses.py` |
| 假设状态枚举 | 现有 `proposed/inconclusive/supported/unsupported_by_data` 保留；P1/P5 增加 `refuted/contested/stale`，不重命名旧值 | `hypotheses.py::update_hypotheses_from_evidence` |
| claim_type | EvidenceRecord 增量可选字段 `claim_type`（observed/inferential/causal/predictive/hypothesis/conditional_action/limitation），宿主按 method 与 scope 校验，模型自报不生效 | `tools/analysis_flow.py::record_evidence_record` |
| scope_ref | 复用 EvidenceRecord 现有 `dataset`/`dataset_contract_id`/`plan_id` + 收据 `data_identities`；不新增自由文字字段 | `evidence_contracts.py`、`analysis_flow.py` |
| question_refs | 复用 `step_id`（stage3c0b 计划步骤）与 `claim_key`；无计划时不伪造 | `evidence_contracts.py` |
| coverage | 发布包增量字段 `coverage`（宿主生成：每子问题 answered/missing+原因） | `publication_synthesis.py` |
| omitted_refs | 发布包增量字段 `omitted_refs`（receipt_id/artifact 引用 + 原因 + 完整性摘要） | `publication_synthesis.py` |
| revision_issues | 发布校验返回结构化 `{code, span, reason, related_scope}` 列表；错误文案保持稳定 | `publication_synthesis.py::validate_final_narrative` |
| audience | `AgentContext` 增量字段 `audience`（general/business/analyst/manager），独立于 `user_proficiency`；`auto` 检测值缓存于 `context.detected_proficiency` 不回写 `user_proficiency` | `agent/context.py`、`loop.py::_build_system_prompt`、`prompts.py` |

不新增第二套 plan/evidence 身份；上述增量字段全部 optional，旧会话缺省可读（round-trip 由 P5/P6 测试覆盖）。

### 6. 已裁决设计事项（采纳总计划第 10 节推荐项）

| 事项 | 裁决 | 依据 |
|---|---|---|
| 待验证发现入口 | 正文就近说明 + 工作台默认折叠入口（推荐项） | 用户指示"按文档要求实施"；计划推荐 |
| 混合身份请求 | 同一事实集分视角展开；身份未知用通用默认（推荐项） | 同上 |
| 主张不可定位时的处理 | 按可定位条件选择：可定位→局部修订；不可定位→整份一次受预算重写或部分+缺口说明，不盲删句子（推荐项） | 同上 |
| 假设状态/字段命名 | 按 §5 映射冻结，复用现有枚举与字段，只增不改 | 设计 §9.3 要求 P0 冻结 |
| L3/L4 执行方 | B01—B06 与真实 Provider 对照由 Codex 执行；本专项负责 L0—L2 与交接材料 | 用户 2026-09-06 指示 |

### 7. 33 个探针 → 可断言测试的转化设计

探针（`tmp/diagnosis-20260906/probe-results.json`）不直接改写为绿灯；每个观察组转化为上表映射中的 RED 用例，其中：

- `synthesis_policy`×5 → S01/S02/S03 的 RED（中文建议、中文预测、详细诊断被压 light）。
- `intent`×7 → I01—I03、I05 的 RED（问候覆盖、否定报告、咨询覆盖执行；两个正例保留为回归）。
- `intent_refinement`×2 → I07/I09 的 RED（无关坏数据阻断、聚合留存误判）。
- `audience_proficiency`×3 → A01—A08 的 RED 基础（三身份同得 intermediate；auto 固化）。
- `publication_validation`×4 + `non_ab_inference_scope` → N01—N04、N08/N09 的 RED。
- `publication_selection`/`filter_after_slice`/`list_fact_selection` → E01—E04 的 RED。
- `hypothesis_*`×5 → H01—H05 的 RED（否定句、错 dataset、中文等价、过期支持、正例对照）。
- `workbench_selection` → U01/U02 的 RED。
- `medium_output_compaction` → E06/E08 的 RED。
- `descriptive_calibration`/`time_word_calibration` → C01/C05 的 RED。

### 8. P0 结论

- 退出门槛核对：无未说明的源码变化（本阶段未改任何产品代码/测试）；每个 D 编号有责任工作包（总计划 §5）与验收用例（§4 映射）；关键设计事项已裁决（§6）。
- 进入 P1。

允许回退的命名文件：`docs/audit/2026-09-06-vp-p0-baseline-*.json`、本记录文件；无源码改动需要回退。

---

## P1：阻止假设被错误升级

阶段 / 状态：**passed**（2026-09-06）

开始与结束 HEAD：`36bca25`（分支 `vp-analysis-value`，本阶段未发生提交，全部为工作区改动）。

本阶段命名修改文件：

- `src/data_agent/agent/hypotheses.py`：`build_hypothesis_set` 增加 plan 绑定（set_id 含 plan 后缀，payload 增加 `plan_id`）；`update_hypotheses_from_evidence` 重写为"先按 plan+dataset 过滤证据 → 重算候选关联 → 永不因文本重合产生 supported"；`_hypothesis` 增加 `related_evidence_ids`；`persist_hypothesis_set` ref 增加 `plan_id`；`_evidence_supports_claim` 更名 `_evidence_relates_to_claim`（语义降级为候选关联信号）。
- `src/data_agent/agent/trust_workflow_runtime.py`：`_find_hypothesis_set_ref` 增加 plan 维度（dataset+route+plan 三元匹配），旧 plan 的 ref 保留为历史。
- `tests/test_hypotheses.py`：H01—H05 新增负例；更新被固化的 `test_update_hypotheses_from_evidence_marks_supported_and_inconclusive`。
- `tests/test_trust_workflow_runtime.py`：H10 新增（新 plan 隔离 + 同 plan 复用两个方向）；更新被固化的 `test_runtime_refreshes_existing_hypothesis_set_from_evidence`。

采用/调整的设计决策：设计 §9.2 的第 4 项（可判定条件）在 P1 阶段一律不满足——文本重合只写入 `related_evidence_ids`，`supporting/conflicting_evidence_ids` 每次重算清零，structured 关系是唯一升级路径（P5 交付）。设计 §9.3 状态机中 `refuted/contested/stale` 推迟到 P5；P1 保持 `proposed/inconclusive/unsupported_by_data` 三个现有值。

契约变更记录（总计划 §6 要求）：

- 原需求：`update_hypotheses_from_evidence` 在 token 重合 ≥0.75 或整句包含时置 `supported` 并追加 `supporting_evidence_ids`（诊断 D08 判定为缺陷）。
- 已确认新需求（用户已接受的产品原则 + H01—H05/H10）：文本重合最多产生候选关联；支持判定必须来自结构化、宿主可验证的关系（P5）；旧 supporting ids 不跨证据快照存活；dataset/plan 不匹配的证据不参与关系。
- 保留的反例：`test_h02/h03`（跨数据/跨计划不关联）、`test_h01`（否定句不得 supported）、`test_h05`（过期支持不背书）、H10 两个方向（新 plan 不继承状态、旧 ref 不删除）。

RED 用例及失败机制（tmp/vp-p1-red，9 failed / 21 passed）：H01 失败于整句包含把 "It is false that …" 判为支持；H02/H03 失败于不校验 dataset/plan；H04/H05 失败于文本重合→supported 与追加式 supporting ids；H10 失败于 dataset+route 复用把旧 plan 状态带入新 plan。

GREEN 用例和源码身份：tmp/vp-p1-green（30 passed）；定向回归 tmp/vp-p1-regression（215 passed，覆盖 publication/evidence-receipts/analysis-state/slice5/slice6/trust-view/multifile-workbench/comprehensive-flow/sse-order）。

必测 ID -> 测试函数映射：H01→`test_h01_negated_claim_text_does_not_mark_supported`；H02→`test_h02_identical_text_from_other_dataset_is_not_related`；H03→`test_h03_same_dataset_evidence_from_other_plan_is_not_related`；H04→`test_h04_pure_text_overlap_stays_candidate_relation`；H05→`test_h05_stale_supporting_ids_do_not_survive_recompute` + `test_supported_hypothesis_demotes_when_evidence_becomes_unrelated`；H10→`test_runtime_h10_new_plan_creates_fresh_set_and_keeps_old_as_history` + `test_runtime_h10_same_plan_refresh_reuses_existing_set`。

passed / failed / skipped / blocked_not_started：定向范围 215/0/0；H06—H09、H11、H12 → blocked_not_started（属 P5）。

Provider 调用与隔离证据：全部用例经 `scripts/testing/run_regression.py` 执行（API_BASE=127.0.0.1:9，DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=0），Provider 调用次数 0。

本地工具/浏览器/真实模型证据等级：L1（纯函数与状态单测）+ L2（runtime 集成路径经 hydrate/persist 真实文件系统）。

未解决问题 / 下一阶段进入条件：`related_evidence_ids` 的结构化升级路径（supported/refuted/contested/stale 的判定谓词）留给 P5；旧会话中已存在的 supported 假设在下次刷新时会被降级为 inconclusive（重算语义，非删除），符合"旧状态不升级"原则。

允许回退的命名文件：上述 4 个文件的当前工作区改动（未提交，可直接 checkout 恢复）。

---

## P2：修复意图、范围和回答策略

阶段 / 状态：**passed**（2026-09-06）

本阶段命名修改文件：

- `src/data_agent/agent/request_language.py`：新增 `keyword_negation_state` / `keyword_group_state` 三态判定（affirmative/negated/ambiguous/absent）；`_NEGATION` 增补通用动词否定（不算/不计算/不分析/不统计/不预测/不估算）。`has_affirmative_keyword` 原语义不变（其消费方 method_playbooks、question_need_detector 仅获得更完整的否定识别）。
- `src/data_agent/agent/intent.py`：快路径重写——纯问候改为"剥离问候词/语气词/标点后为空"才触发；报告/操作/分析关键词改为否定感知；新增 `_EXECUTION_REQUEST_MARKERS`（执行祈使）与 `_CONSULT_QUESTION_PREFIXES`（疑问式咨询前缀），"执行＋咨询尾巴"保留执行主任务，"疑问式咨询＋执行祈使"或双重否定返回 None 交语义层。
- `src/data_agent/agent/intent_refinement.py`：签名增加 `active_dataset`；contracts 先 hydrate 再按 scope 过滤；用户级留存改为两级判定（显式用户粒度词肯定触发；泛化留存/cohort 词仅在无聚合标记时触发；否定不触发）；混合请求在 ambiguity 中增加 `partial` 说明聚合部分仍可用。
- `src/data_agent/agent/analysis_entry.py`：route 选择与 contracts 同样按 active_dataset 过滤（I11 修复：请求文本提及其他数据集不再扩大作用域）；`_mentions_retention` 委托给用户粒度感知判定。
- `src/data_agent/agent/trust_workflow_runtime.py`：`refine_turn_intent_with_state` 传递 `active_scope.active_dataset`。
- `src/data_agent/agent/synthesis_policy.py`：建议判定增加中英文等价且否定感知的 `_ADVISORY_MARKERS_ZH`；新增 `_explicit_depth_request`（详细/诊断等→standard 深度，摆脱固定 light）；terse/direct 分支在显式建议请求下不再吞掉建议（S04）；验证 fail 的 reason 在存在独立通过证据时说明"仅约束依赖失败证据的主张"（S07）。

契约变更记录：

- 原需求：问候关键词＋长度<15 即 simple_response；报告/操作关键词不做否定检查；"分析建议"等咨询子串优先于执行意图；`analytical` 模式一律 light 且抑制 decision_recommendation（诊断 D01/D05 判定为缺陷）。
- 已确认新需求：问候后跟明确任务时主任务不被覆盖；否定关键词不触发对应分支；执行＋咨询复合保留执行主任务；显式建议/预测请求（中英文）获得等价 advisory 策略且不抑制建议；显式深度请求解除固定 light；无关数据集问题不阻断目标任务（细化层与入口层共用 scope，兼容 compact ref）。
- 保留的反例：I04 双重否定交语义层不强标 clear；I06 冲突输入交语义层且不隐式重试；I07 目标数据 blocked 仍阻断；I12 no-data/缺列/高风险确认阻断由既有测试继续覆盖；S05 "只要公式，不需要建议" 保持 direct 不强加建议；S08 无证据不得伪装业务结论。

RED（tmp/vp-p2-red）：18 failed（I01—I06、I07—I10、I08、S01—S07、I11）。I11 揭示入口层 route 未按 scope 过滤的真实泄漏。

GREEN：tmp/vp-p2-green（271 passed）→ I11 断言修正（实际行为为合法的指标澄清门，改为断言"不得选中 other"＋正向对照）→ tmp/vp-p2-green2（347 passed）。定向回归 tmp/vp-p2-regression（652 passed，覆盖 intent/refinement/policy/entry/playbooks/question-need/phase4/prompt-system/comprehensive/quality/execution-control/slice5/publication/hypotheses/runtime/sse-order）。

必测 ID → 测试映射：I01→`TestValuePreservationP2Intent::test_i01_*`（3 个）；I02→`test_i02_*`（2 个）；I03→`test_i03_*`（2 个）；I04→`test_i04_double_negated_report_defers_to_semantic_layer`；I05→`test_i05_regular_operation_and_qa_unaffected`；I06→`test_i06_conflicting_consult_and_execution_defers`；I07→`test_i07_*`（2 个）；I08→`test_i08_compact_refs_hydrate_to_same_refined_intent`；I09→`test_i09_*`（2 个）；I10→`test_i10_mixed_aggregate_and_user_retention_notes_partial_capability`；I11→`test_i11_*`（2 个）；I12→既有 `test_decide_analysis_entry_does_not_execute_route_missing_required_data` / `test_pending_confirmation_blocks_direct_analysis_entry` / `test_blocked_quality_returns_blocked`；S01—S08→`test_s01_*`…`test_s08_*`。

passed / failed / skipped / blocked_not_started：定向范围 652/0/0；无跳过；无 blocked。

Provider 调用与隔离证据：全部经 `run_regression.py`（Provider 禁用），LLM 语义层在 I04/I06 用 mock `_try_llm_classify` 验证"调用一次、不隐式重试"，Provider 调用次数 0。

证据等级：L1（意图/策略纯函数）+ L2（入口/细化/ref hydration 走真实文件系统）。

未解决问题：策略层对英文建议词的否定（"no recommendation needed"）尚未感知（中文已感知）；受众适配（A 系列）与提示词级置信度规则一致性归 P6/P3。S07 的按主张粒度校验的完整实现归 P3（N 系列）。

允许回退的命名文件：上述 6 个 src 文件与 4 个 tests 文件的当前工作区改动。


---

## P3：按主张检查发布与校准

阶段 / 状态：**passed**（2026-09-06）

本阶段命名修改文件：

- `src/data_agent/agent/publication_synthesis.py`：新增 `_split_claims`（句读＋转折连词切分主张）、`_curve_interpretation_issues`（原拟合解释检查迁移为按主张定位）、`_extrapolation_issues`（D30 类逐主张分类：边界说明/补数行动/条件动作/纯提及放行，数值断言与预测动词拦截；多来源取最大观测范围，B 的合法观测不被 A 的边界拒绝）、`_significance_issues`（无已执行检验→拒绝；有检验但主张未关联检验对象（inference_subjects）→拒绝，不再全局放行）、`validate_final_narrative_issues`（结构化 code/span/reason）与 `validate_final_narrative` 兼容包装（错误信息附违规位置）。`publication_contract` 增加 `args` 入参与逐工具 `_inference_performed`（ab_test/causal_analysis/regression_analysis 等按真实结果字段判定）与 `inference_subjects`（从工具参数提取检验对象）。
- `src/data_agent/agent/loop.py`：收据记录时把工具参数传入 `publication_contract`。
- `src/data_agent/tools/analysis_flow.py`：新增 `_infer_statistical_inference`（宿主分类主张类型：执行过的检验统计量/推断方法/主张中的显著性措辞 → 推断；纯记录内加总 → 描述；模型自报字段仍被弹出后由宿主重算）、`_observation_window_days`（结构化窗口解析：N天/N月/N周/N年/日期区间；不可解析返回 None 不编造）；`_auto_generate_limitations` 与 `_calibrate_confidence` 的 n<30 规则仅作用于推断类主张；新增描述性总体外推的自动边界；短观察期警告改为结构化窗口判定。
- `src/data_agent/agent/prompts.py`：置信度校准规则按主张类型收窄——n<30 与单源无交叉验证两条限定为推断/外推/因果主张，记录内描述性事实不受约束；新增描述性范围陈述条目。
- `tests/test_publication_synthesis.py`：N01—N09、N11 用例与 `_receipt_with_args` 夹具。
- `tests/test_verification_layer.py`：C01—C08 用例。
- `tests/test_analysis_quality.py`：契约更新——原 `test_small_sample_generates_limitation` 要求任何 n<30 都生成样本量局限（诊断 D10 判定为缺陷）；新契约为推断类触发 + 新增描述性加总不触发的负例（`test_small_sample_descriptive_total_not_flagged`）。

契约变更记录：原需求=外推检查对全文任何超范围 D/N 数字整份拒绝、n<30 一刀切降置信、"天"字即短观察期、任一 p 值为全轮显著性主张背书（D02/D10 缺陷）。新需求=按主张定位并分类（边界/补数/条件/断言）、否定不掩护转折后的断言、多来源各自绑定、显著性主张须关联实际检验对象、推断类与描述类分别校准、时间窗结构化读取、不可解析不编造。保留的反例：N03/N04/N06-a（无依据外推仍拒绝）、N07/N08-unrelated（未检验/未关联的显著性主张仍拒绝）、C04（大样本不掩盖方法问题）、C06（不可解析窗口不产生任何充分性/不足性判断）。

RED（tmp/vp-p3-red）：15 failed（N01—N11、C01/C02/C05）。GREEN（tmp/vp-p3-green2）：112 passed。广域回归（tmp/vp-p3-regression）：662 passed（含 SSE 发布顺序、stage3c0b 兼容、系统数据质量审计、evidence、slice3/5、golden、phase4、P1/P2 全部用例）。

必测 ID → 测试映射：N01—N05→`TestNSeriesPublication::test_n01…n05`；N06→`test_n06_other_source_with_valid_d30_not_blocked` + `test_n06_a_scope_still_blocks_when_b_absent`；N07→`test_n07_significance_claim_without_any_test_rejected`；N08→`test_n08_unrelated…` + `test_n08_bound…`；N09→`test_n09_causal_tool_metadata…`；N11→`test_n11_issues_carry_position_and_stable_code`；N10/N12→既有 `test_streaming_publication_rewrites_once_and_never_projects_rejected_narrative`（SSE 一次受预算修订、失败不发布、rejected 不外泄）与 `test_sse_publication_order.py` 全组；C01—C08→`TestCSeriesCalibration::test_c01…c08`。

passed / failed / skipped：广域 662/0/0（1 个 scipy 既有 warning）。

Provider 调用与隔离证据：`run_regression.py` 执行，Provider 调用 0。

证据等级：L1（校准与校验纯函数）＋L2（loop/SSE 修订路径、真实收据管线）。

未解决问题：显著性主张与检验对象的绑定基于对象名包含匹配，中文同义改写（"营收"vs"revenue"）依赖最终合成的模型绑定与 L4 验证；"描述性拟合解释"类检查的既有模式库未扩展（本阶段只迁移为按主张定位）。

允许回退的命名文件：上述 4 个 src 与 3 个 tests 文件的工作区改动。


---

## P4：保留关键证据与可恢复上下文

阶段 / 状态：**passed**（2026-09-06）

本阶段命名修改文件：

- `src/data_agent/agent/publication_synthesis.py`：`_walk_facts` 遍历完整候选集合（数组上限 100 项，不再固定前 3）；`extract_publication_facts` 改为事实组选择——同父路径的字段（组名＋数值、期间数值＋分母天数、口径）成组保留，预算压力丢弃整组而非拆散配对；`build_publication_packet` 重写：`_question_terms`（ASCII token＋CJK 二元组）与 `_select_sources`（问题相关来源优先、按时间序稳定输出、上限 8 个、不足 4 个按新近补足），evidence 先按本轮收据过滤再无截断进入（E02），每来源事实预算自适应 `max(4, 总预算//来源数)`（E01），新增 `omitted_refs`（超预算来源的 receipt_id＋result_sha256＋稳定原因）与 `coverage`（covered/missing 逐词项行，E05/E10），发布包 id 改为内容敏感种子（含所选收据 result_sha256 与 evidence 主张，E09）。
- `src/data_agent/agent/compact.py`：`persist_large_output` 与新增 `_persist_micro_output` 改为内容寻址文件名 `{id}__{sha256前10}.txt`（同 id 不同内容各自落盘，E07）；`micro_compact` 重写：120–15000 字符段先可靠持久化（写入后读回校验，失败返回 None）再替换为带文件引用的摘要；持久化失败不进行有损替换（E07）；已压缩消息跳过二次压缩（E08）。
- `tests/test_compact_preservation.py`：新建，E06—E08。
- `tests/test_publication_synthesis.py`：E01—E05、E09、E10。
- `tests/test_execution_control.py` / `tests/test_pipeline_comprehensive.py`：契约更新——原断言固定旧文件名 `{id}.txt`（该命名正是 E07 碰撞缺陷的载体）；新断言内容寻址文件名＋读回内容一致。

契约变更记录：原需求=只保留最近 4 个来源/每来源 10 事实、数组只看前 3、evidence 先切 4 条再过滤、120–15000 字符工具消息直接摘要不落盘、同 id 覆盖旧文件（诊断 D03 判定为缺陷）。新需求=问题覆盖优先的自适应选择、事实组完整性、省略有引用有原因、覆盖有缺口有说明、一切有损替换前先可靠持久化且校验、内容变化使发布包身份失效。保留的反例：E05 预算总量仍受控（≤80 事实）；E09 旧包不删除仅不再复用；E06 持久化失败宁可跳过压缩也不丢原文。

RED（tmp/vp-p4-red）：11 failed。GREEN（tmp/vp-p4-green2→regression2）：607 passed（E01 夹具修正为同语言词项——宿主确定性选择依赖词法覆盖，跨语言绑定属最终合成的模型侧职责）。

必测 ID → 测试映射：E01→`test_e01_all_primary_subquestion_sources_kept`；E02→`test_e02_current_evidence_not_sliced_before_filter`；E03→`test_e03_fourth_group_value_enters_facts_with_its_name`；E04→`test_e04_comparison_fields_kept_as_a_group`；E05→`test_e05_budget_omissions_are_recorded_with_references`；E06→`TestCompactPreservation::test_e06_medium_output_persisted_before_replacement`；E07→`test_e07_same_id_different_content_never_silently_reused`＋`test_e07_persistence_failure_skips_lossy_replacement`；E08→`test_e08_recompacting_compacted_message_keeps_original`；E09→`test_e09_packet_identity_changes_when_evidence_content_changes`；E10→`test_e10_uncovered_question_terms_become_explicit_gaps`（预算耗尽的停止行为由 test_execution_control 既有用例覆盖）。

passed / failed / skipped：607/0/0（6 个 scipy/statsmodels 既有 warning）。

Provider 调用与隔离证据：`run_regression.py` 执行，Provider 调用 0。

证据等级：L1（选择/分组/持久化纯函数）＋L2（真实会话目录文件系统、loop 收据管线）。

未解决问题：`coverage` 词项粒度为二元组，跨语言或同义改写的子问题绑定依赖最终合成（L4 验证）；`omitted_refs` 的恢复路径引用 receipt_id，前端不直接展示（设计允许）。

允许回退的命名文件：上述 2 个 src 与 5 个 tests 文件的工作区改动。


---

## P5：竞争假设的完整闭环

阶段 / 状态：**passed**（2026-09-06）

本阶段命名修改文件：

- `src/data_agent/agent/hypotheses.py`：模板假设增加 `claim_type`（primary→descriptive、alternative→causal、baseline→statistical）与 `evidence_relations` 字段；新增 `_measurement_direction`（由测量字段 delta/change/pct_change 符号确定性判定方向）、`_relation_proposals`、`_validate_relation`（校验：metric 存在于证据 measurements、声称方向与测量方向一致且非 unknown、主张类型可判定——描述性方向不能升级因果替代解释、基线变异主张需显著性统计量）；`update_hypotheses_from_evidence` 应用结构化关系：支持+反证并存→contested、仅支持→supported、仅反证→refuted、关系或关联存在但不满足判定→inconclusive；已判定假设在依赖证据全部消失时转 `stale`（保留历史语义，不静默退回候选）；文本重合仍只产生候选关联（P1 语义保留）。新增 `hypotheses_prompt_brief`（有界竞争假设简报：每假设带状态原词与中文标签、支持/反证 id、未决项的区分性证据字段；明确"不得虚构排除结论"）。
- `src/data_agent/agent/trust_workflow_runtime.py`：`maybe_create_hypothesis_set` 的复用条件更新——未判定且无证据的集合保持去重短路；已判定（存在结构化关系/支持/反证）的集合即使证据清空也重算（进入 stale 而非保留旧判定）。
- `src/data_agent/tools/analysis_flow.py`：`competing_hypotheses` 结构化条目提交时校验（hypothesis_id＋relation(supports/refutes)＋metric＋observed(increased/decreased/flat)，缺项或非法值返回稳定错误）；旧自由格式 dict 无 relation/hypothesis_id 键时仍接受为未验证注释（永不参与状态变更）。
- `src/data_agent/agent/loop.py`：`_maybe_inject_synthesis_policy` 在策略指令后附加竞争假设简报（hydrate 后注入，失败降级）；`_verify_before_publication` 在发布边界同时刷新假设状态（与验证同一证据快照）。
- `src/data_agent/agent/prompts.py`：H12——"列出至少1个被排除的替代解释"改为"列出竞争解释及其当前状态；未排除的必须标注未决并说明区分性证据，不得虚构排除结论"。
- 测试：`tests/test_hypotheses.py`（H06—H09、H12 简报）、`tests/test_trust_workflow_runtime.py`（H11 新证据改变状态、依赖证据消失转 stale）、`tests/test_analysis_flow_tools.py`（结构化关系 schema 校验）。

契约变更记录：原需求=假设状态只由英文 token 重合决定、competing_hypotheses 只查外层 list（D08/D09 缺陷）。新需求=结构化关系＋宿主判定谓词（metric/方向/主张类型门）是唯一状态转换路径；中文与英文证据经同一结构化判定得到一致结果；已判定状态在证据消失时转 stale；简报进入合成输入。保留的反例：H06 需完整结构化依据（缺任一要素不 supported）；H07 无关系不得 refuted；描述性方向不能支持因果替代；编造排除结论被提示词与简报双重禁止。

RED（tmp/vp-p5-red）：9 failed。GREEN（tmp/vp-p5-green→green3）：393 passed（H11 夹具两次修正：多指标触发指标澄清门、period_compare 需显式比较窗口——均与假设逻辑无关，改用 trend 路由）。

必测 ID → 测试映射：H06→`test_h06_valid_structured_relation_marks_supported`；H07→`test_h07_valid_refuting_relation_marks_refuted_and_no_relation_stays_open`；H08→`test_h08_simultaneous_support_and_refutation_is_contested`；H09→`test_h09_chinese_and_english_evidence_agree_via_structure`；H10→P1 的 `test_runtime_h10_*`（继续通过）；H11→`test_h11_new_evidence_changes_hypothesis_state_on_refresh`＋`test_h11_supported_hypothesis_becomes_stale_when_its_evidence_disappears`；H12→`test_h12_prompt_brief_marks_open_alternatives_without_fabricated_exclusion`＋提示词措辞；schema→`TestCompetingHypothesesSchema`（4 个）。

passed / failed / skipped：393/0/0。

Provider 调用与隔离证据：`run_regression.py` 执行，Provider 调用 0。

证据等级：L1（判定谓词纯函数）＋L2（runtime 持久化/重水化/发布边界刷新、loop 简报注入路径）。

未解决问题：结构化关系由模型在 record_evidence_record 中提交，宿主校验其可判定性但不生成关系；真实模型会不会按 schema 提交属 L4 验证内容。`_validate_relation` 的统计类门槛目前只认 p_value/z_score/significance 字段。

允许回退的命名文件：上述 5 个 src 与 3 个 tests 文件的工作区改动。


---

## P6：身份适配与渐进展示

阶段 / 状态：**passed**（2026-09-06；L3 浏览器验证归 Codex）

本阶段命名修改文件：

- `src/data_agent/agent/context.py`：`AgentContext` 增加 `audience`（general/business/analyst/manager，按轮次）与 `detected_proficiency`（auto 检测缓存）；`user_proficiency` 保持 "auto" 不再被检测结果覆盖写回（D07）。
- `src/data_agent/agent/prompts.py`：新增 `detect_audience`（仅凭本轮用户消息中的显式身份/汇报对象措辞识别；数据内容如"经理"列不构成身份；未声明 → general）、`resolve_proficiency`（显式设置优先，auto 每轮重检且不写回）、`_AUDIENCE_BASELINE`（数值、口径、范围、限制与证据等级对全部受众一致的共用底线）与四类受众指令块；`build_system_prompt` 增加 `audience` 参数并在 conversation/guidance/analysis 三个层级注入受众块。
- `src/data_agent/agent/loop.py`：`_build_system_prompt` 改用 `resolve_proficiency`（D07 的 auto→concrete 写回缺陷修复）与每轮 `detect_audience`，两处 `build_system_prompt` 调用传入 audience。
- `src/data_agent/agent/workbench_view.py`：投影增加 `verified_total`（真实总数；`verified_conclusions` 输出完整已验证集合，默认六条与展开由前端完成）与 `pending_findings`（来自假设集的 proposed/inconclusive/contested 项，含 status＋中文 status_label＋依据（相关证据 id）＋尚缺字段＋下一步区分性检验；有界 6 条；不与 verified 混合；不含 artifact_path/plan_id 等内部字段）。
- `src/data_agent/web/templates/index.html`：已验证结论标题显示"可见/总数"，默认 6 条＋展开其余/收起（复用既有 expandedListCounts 机制）；新增默认折叠（`<details>`）的"待验证发现"区，状态用文字标签（非仅颜色）。
- `src/data_agent/web/static/js/app.js`：新增 `verifiedTotal()`、`pendingFindings()`、`canCollapseList()`。
- 测试：新建 `tests/test_audience_adaptation.py`（A01—A08）；`tests/test_slice6_workbench_minimal.py`（U01—U04＋最简契约更新）；按新契约更新 `test_trust_view.py`、`test_multifile_workbench_view.py`、`test_trust_inspector_api.py`、`test_trust_inspector_ui.py`、`test_web_workbench_action_board.py` 的精确集合断言（保留防历史升级、指纹失效隐藏、会话隔离与移除面断言）。

契约变更记录：原需求=最简投影仅 `verified_conclusions`（精确集合断言×5 处）、熟练度 auto 首检后写回、无受众概念（D04/D07 判定为缺陷）。新需求=audience 与 proficiency 分离且每轮可变、共用底线保证事实一致、真实总数＋可展开、待验证发现独立折叠入口且带状态文字。保留的反例：U04 stale 指纹隐藏且不在任何区域升级；pending 不混入 verified；A07 数据内容不识别身份；移除面（action-board 等）不得回归。

RED（tmp/vp-p6-red）：9＋ImportError（A 系列 + 旧契约精确断言）。GREEN（tmp/vp-p6-regression）：532 passed / 2 skipped（跳过为既有条件跳过）。

必测 ID → 测试映射：A01—A03→`TestAudienceDetection::test_a01…a03`；A04→`test_a04_shared_baseline_present_for_every_audience`；A05→`test_a05_current_turn_request_wins_over_previous`；A06→`test_a06_plain_language_switches_proficiency_per_turn`；A07→`test_a07_no_identity_inferred_from_data_or_questions`；A08→`test_a08_mixed_request_keeps_per_turn_audience_and_shared_facts`；D07 写回缺陷→`test_auto_proficiency_is_not_overwritten_by_detection`；U01→`test_u01_eight_verified_conclusions_show_total_with_expansion_data`；U02→`test_u02_pending_findings_are_separate_from_verified`；U03→`test_u03_pending_findings_carry_status_text_basis_gap_and_next_step`＋`test_u03_supported_hypothesis_not_projected_as_pending`；U04→`test_u04_stale_fingerprint_hides_verified_and_upgrades_nowhere`＋既有 stale 断言；U05—U08→L3 归 Codex（本阶段交付其依赖的后端投影与前端渲染）。

passed / failed / skipped：532/0/2。

Provider 调用与隔离证据：`run_regression.py` 执行，Provider 调用 0；身份适配零额外模型调用（规则检测）。

证据等级：L1（检测纯函数＋提示词构造）＋L2（投影层＋Web test_client HTML/JS 契约）；浏览器实际交互未验证（明示"未做 L3"）。

未解决问题：前端展开/折叠/待验证区的真实浏览器行为（键盘操作、会话切换无残留）未验证——交接 Codex（U05—U08、B01—B06）；audience 检测为关键词规则，同义改写留待 L4。

允许回退的命名文件：上述 6 个 src/web 文件与 7 个 tests 文件的工作区改动。

---

## P7：完整离线回归与 L3 启动门核查（Codex，2026-09-06）

阶段 / 状态：**failed**。本节是 P0—P6 历史记录之后的复核结果，不改写其当时运行结果；当前阶段状态以总计划与 [P7 执行报告](2026-09-06-vp-p7-execution-report.md) 为准。

当前 HEAD=`36bca25a44a25c99ef8bb7bf56312bde05736ba2`，分支=`vp-analysis-value`；保留全部 P1—P6 未提交改动。已有 347 个 src/tests/scripts 文件内容核查未变化，新加 P7 独立反例 1 个测试文件。源码/测试哈希、Git 清单、JUnit 哈希及实际反例输出见 [执行收据](../../audit/2026-09-06-vp-p7-execution-receipt.json)。快照记录时点在首次完整离线结束后、P7 新测试加入前，不能用作 Provider 运行前冻结收据。

运行记录：

- `tmp/value-preservation-p7-full-01`：完整 tests，**2478 passed / 7 failed / 3 skipped**，约 158 秒。
- `tmp/value-preservation-p7-boundaries-01`：新增 9 个独立边界用例，**5 passed / 4 failed / 0 skipped**，约 2 秒。真实宿主函数，结构化夹具，L1；未 mock 检查结果。
- `tmp/value-preservation-p7-failure-triage-01`：原失败两个模块独立复跑，**81 passed / 7 failed / 0 skipped**，约 13 秒。同样 7 项复现；与全量结果重叠，不累计通过数。

原失败归类：3 个 Workbench 旧精确集合断言漏更新；1 个“谢谢你的分析”的纯礼貌语真实路由回归；2 个小样本旧测试未声明推断性主张；1 个样本频率被写成无范围“最受欢迎”的混合语义夹具需拆分，不能直接删除其总体推断保护。

关键停止证据：

1. P7-F01 / P3-N06：A 仅 D1—D7、B 有 D1—D30，同包下 A 的“D30 留存预计为 5%”被 validate_final_narrative 允许。只有 A 时同句会拒绝；B 的合法 D30 可发布。来源最大上界不能作为所有主张的范围。
2. P7-F02 / P5-H06/H07：对 revenue changed 假设，revenue delta=0＋supports 仍 supported；delta=10＋refutes 仍 refuted；orders delta=10＋supports 也能支持 revenue 假设。目标指标及目标谓词未检查，模型提议关系仍被直接用于最终状态。

证据限制：上述为 L1 宿主函数反例，不声称浏览器出现错误，也不声称假设 supported 等同于 Workbench verified。没有实际工具/SSE/持久化/浏览器全链收据。

### L3 执行记录（Codex）

**B01—B06 均为 blocked_not_started**。总计划 §8 规定“任一关键安全负例失败”即停止依赖工作；因此未启动本地浏览器、未生成截图、刷新/导出收据或脚本化模型通过记录。P6-U05—U08 仍缺真实浏览器证据。当前不能形成 P7 本地候选，P8 同样 blocked_not_started。

Provider：未启动真实 Provider；离线入口强制 dummy loopback、网络禁用与 completion 阻断。没有复用任何历史批次授权，没有 Git 提交/推送/部署。

跳过理由：1 个真实模型 live smoke 按离线要求禁用；2 个 Web 用例分别缺多会话/任一会话，排序和 rewind-info 端点未获验证，后续应补合成会话夹具。

后续顺序：先修 P3 来源绑定与 P5 目标谓词（不把最大上界机械改成最小上界，不靠提示词自律）；修纯礼貌语路由并按描述/推断拆分旧校准用例；新目录重跑新增反例、相关回归及完整 tests；全部必测通过后恢复 B01—B06。详细修复要求、通过标准和重现命令见 P7 执行报告 §7—§8。

本轮新增：P7 执行报告、JSON 收据、`tests/test_value_preservation_p7_boundaries.py`；更新：总计划当前状态、本交接链文档及本节记录。未修改产品源码或既有测试断言；RED 保留，未标 xfail。本节只证明 P7 已开始并被验收门阻断，**不证明已修复**。


---

## P7-R：Codex 复核阻断的修复（R1/R2/R3，2026-09-07）

阶段 / 状态：**R1/R2/R3 修复完成，离线全量复跑通过**。本节接在上方 Codex P7 复核记录之后，不改写其内容；B01—B06 浏览器验收仍归 Codex 按交接说明执行。

### R1：发布范围按来源绑定（修复 P7-F01）

- `publication_contract` 新增 `source_dataset`（从工具参数 name/data/dataset/source 提取）；`build_publication_packet` 的每个 `publication_scope` 条目携带 `receipt_id` 与 `source_dataset` 绑定身份。
- `_extrapolation_issues` 重写为按主张绑定：`_bind_claim_source` 取子句唯一提及的来源（`source_dataset` 名出现在子句中且恰有一个来源命中）；绑定时只按该来源的观测上界判定；未提及或多来源同名命中视为未绑定——未绑定的越界数值主张只能在被**所有**来源观测到时发布，否则以 `unbound_time_point_claim`（缺少来源绑定）进入既有一次受预算修订。不采用 min/max 一刀切。
- 边界说明、补数行动、条件动作、纯提及的放行逻辑不变（来源无关）。

### R2：假设目标谓词与指标判定（修复 P7-F02）

- 假设模板新增 `decision_rule`（`_decision_rule`）：`metrics`＝该假设的目标指标集（必填 metric/rate_metric 字段）；`predicate`＝"changed"（period_compare/trend 的主假设主张“发生变化/趋势”），由模板主张文本确定性推导。
- `_validate_relation` 改为返回 `(validated, reason)`：新增目标指标门（`metric_not_target`——其他指标的运动不能判定本假设）与谓词一致性门（`relation_predicate_mismatch`——changed 谓词下非零可比 delta 蕴含 supports、零 delta 蕴含 refutes，模型标签必须一致）；方向门保留且 `_measurement_direction` 拒绝非有限 delta（NaN/inf → unknown）。
- `update_hypotheses_from_evidence` 将被拒的合法格式提议保留为 `relation_candidates`（含 evidence_id/relation/metric/observed/reason），不强制改写为反向结论。
- 模型提交 schema（`competing_hypotheses` 逐项校验）与运行时刷新/发布边界刷新路径不变。

### R3：常规回归缺口关闭

- `tests/test_multifile_regressions.py`×3：精确字典断言对齐新投影契约（verified_total/pending_findings 空态），保留“确认信息不进投影、空态无已验证结论”语义并新增 `"confirm" not in` 断言。
- 纯礼貌语路由：`_CHAT_KEYWORDS` 增加整句礼貌模板（“谢谢你的分析”等 11 条）；`_is_pure_chat` 改为**按长度降序**剥离（短词“谢谢”先消费会残留“你的分析”劫持主任务——“谢谢你的分析”整句剥离后为空 → simple_response；“谢谢，请继续分析收入趋势”剥离后仍有任务 → 分析路由）。
- 校准旧测试拆分：`test_high_confidence_small_sample_downgraded` 明示推断方法（ab_test）保留降级断言＋新增描述性加总不降级负例；`test_record_evidence_auto_downgrades` 改为推断性主张（显著性措辞＋ab_test）＋同测试内描述性不降级对照；真实数据“最受欢迎商品”拆为未限定（总体推断→降级）与“在这5条记录内”（描述性→不降级）两支。
- 宿主侧配套：`analysis_flow` 新增 `_unscoped_population_superlative`（未限定范围的“最受欢迎/最热门”类最优断言视为总体推断；含“记录内/样本内/这批”等限定词则保持描述性）；总体边界自动限制同时覆盖显式总体措辞与未限定最优断言。
- `tests/test_web_overhaul.py`×2：不再跳过——排序测试种子两个合成会话并把旧会话 `saved_at` 显式改早以真实检验倒序；rewind-info 测试种子一个合成会话后断言 200。

### 验证结果（全部新 run-dir）

- Codex oracle（`tests/test_value_preservation_p7_boundaries.py` 原 9 例）＋R1/R2 补充反例（新增 10 例：交换顺序×2、未指明来源、混合边界预测、同名不同范围、NaN/inf delta、候选保留原因×3、因果证据不足）：`tmp/vp-p7r-boundaries-final` → **19 passed / 0 failed**。
- 原失败模块＋关联面（multifile_regressions、phase_comprehensive、web_overhaul、boundaries、publication、hypotheses、verification、intent）：`tmp/vp-p7r-r3-check2` → **446 passed / 0 failed**（原 2 个跳过项实际运行）。
- 完整离线回归：`tmp/vp-p7r-full-offline` → **2509 tests / 0 failures / 0 errors / 1 skipped**（JUnit sha256 前缀 `d7a495bbfe19752c`；唯一跳过为按离线边界禁用的真实 Provider live smoke）。对照修复前：2478/7/3＋边界 5/4。

### 剩余边界（不变）

- B01—B06（L3 浏览器）与 U05—U08 仍 `blocked_not_started`，归 Codex 按交接说明执行；修复后的发布边界与假设判定应作为 B02/B03/B04 的重点核对项。
- P8 未启动，无新授权。
- 本轮改动仍未提交（同 P1—P6，提交等待授权）。

本轮修改文件：`src/data_agent/agent/publication_synthesis.py`、`src/data_agent/agent/hypotheses.py`、`src/data_agent/agent/intent.py`、`src/data_agent/tools/analysis_flow.py`；`tests/test_publication_synthesis.py`（N06 夹具带来源身份＋B 存在时 A 仍拒绝的反例）、`tests/test_value_preservation_p7_boundaries.py`（补充反例）、`tests/test_multifile_regressions.py`、`tests/test_phase_comprehensive.py`、`tests/test_web_overhaul.py`。

---

## 提交记录

- 2026-09-07：P0—P6 与 P7-R 的全部改动（产品源码、测试、文档）经用户授权提交至分支 `vp-analysis-value`；A06 矩阵未跟踪产物与 tmp/ 运行收据不纳入。此后用户已授予持续性提交授权（推送/部署仍需单独授权）。

---

## L3 执行记录（Codex，2026-09-07）

阶段 / 状态：**failed**。B01—B06 已在本地真实浏览器完成；B03、B04 与 B06 未满足交接中的必过断言。因此不形成 P7 本地候选，也不改变 P8 未授权、未启动的结论。

### 隔离与运行身份

- 源码基线：`c30720d7f9cd4ae70470a6100b87e38a258ece4b`（`vp-analysis-value`）；运行器为 `scripts/testing/run_p7_browser_rehearsal.py`。它经普通 Flask Web、SSE、`AgentLoop`、真实工具、会话持久化、Workbench 投影、页面刷新与导出执行；仅模型响应为脚本化。
- 所有有效 run-dir 使用 loopback `API_BASE`、禁用网络/MCP/skill 自动发现，并将主模型与 `llm_intent`、`llm_playbook`、`quality_judge` 的懒加载客户端统一替换为脚本化客户端。每份有效 `runtime.jsonl` 的 `forbidden_provider_transport=0`；没有真实 Provider 调用。
- 运行器为浏览器覆盖补充了 B03 六来源夹具、B04 结构化支持/反证夹具、B05 两种表达切换和 B06 工具/预算场景。未替换 `validate_final_narrative`、持久化、Workbench 投影或 SSE 消费链。

### 当前场景矩阵

| 场景 | 状态 | 已有可核验事实 | 尚缺通过条件 |
|---|---|---|---|
| B01 | passed | `tmp/p7-browser-rehearsal-08`、会话 `61190a2fd893`：页面和 Workbench 的已验证结论均为当前 12 条订单金额合计 120；正文保留条件建议、停止条件和“不能外推”限制。刷新后内容仍在；浏览器回复 Markdown 导出保留同一安全正文。状态含 1 条证据、1 份验证报告、1 个假设集，Provider 账本为 0。 | 无。 |
| B02 | passed | `tmp/p7-browser-rehearsal-07`、会话 `e908e8895ba5`：页面发布 D7=10%、不能预测 D30 与补数建议；越界候选只留作带 `publication_rejected=true` 的内部修订上下文，页面不可见。2 个 curve 收据、2 个 publication packet，浏览器触发回复导出；会话 Markdown 导出不含越界候选。 | 无。 |
| B03 | failed | `tmp/p7-browser-rehearsal-10`、会话 `d0f73be7450d`：12 条工具收据覆盖六个来源，发布包的 `publication_scope` 有六个 source dataset，`omitted_refs=0`，早期压缩输出可在内容寻址文件恢复。 | 浏览器“产出物”显示“暂无产出物”，会话 Markdown 导出仅含对话，不含六来源、收据或 `omitted_refs`；因此“展开/导出完整”失败。 |
| B04 | failed | `tmp/p7-browser-rehearsal-15`、会话 `0e8eb079bd2e`：浏览器先显示结构化支持，再显示反证；持久化假设从 `supported` 转为 `contested`，并保留 supports/refutes 证据。 | 当前 UI 没有“清空证据但保留假设”的生命周期操作；现有 reset 会同时删除证据与 hypothesis set，不能获得要求的 `stale` 状态或刷新收据。 |
| B05 | passed | `tmp/p7-browser-rehearsal-10`、会话 `5a9b99cc0b78` 与 `tmp/p7-browser-rehearsal-11`、会话 `51ed1cf6d685`：业务、分析师、管理层表达分别变化，120、12 条、范围与不可外推限制保持一致；“大白话”当轮生效，下一轮技术表达恢复 `f_sales_total`、`group_aggregate` 与 `amount_sum=120`。刷新后连续对话仍在。 | 无。 |
| B06 | failed | 新的独立运行 `tmp/p7-browser-rehearsal-19`（旧 B06 额度中断结果作废）：工具失败会话 `d4e29d2fa1ca` 页面明确提示未找到数据集且未发布计算结论，状态没有 publication packet；Provider 账本为 0。 | 预算会话 `b96b85e8c94a` 真实执行了 206 次非元工具调用、产生 206 条真实收据，未产生 `budget_exceeded` 收据且未阻止调用。页面的“已触及预算”来自脚本化最终文本，不能视为守卫生效。保存失败、发布修订失败、pending confirmation 尚未获得同一 B06 生命周期收据；预算断言失败时不应补作通过。 |

### 后续修复范围

1. B03：让“产出物”与 Markdown 导出保留可展开的发布包来源、收据引用及 `omitted_refs`，并补浏览器回归。
2. B04：提供证据失效而假设保留的真实生命周期操作，使 `stale` 可在页面、刷新和持久化中验证。
3. B06：修复同一轮 `TurnExecutionState` 的工具预算守卫，先用浏览器验证真实 `budget_exceeded` 和无后续工具执行，再分别补保存失败、发布修订失败与 pending confirmation 收据。

P8 仍要求 B01—B06 全部通过、源码冻结与用户的新真实 Provider 授权，当前不得启动。


---

## L3-R：Codex 浏览器演练阻断的修复（B03/B04/B06，2026-09-07）

阶段 / 状态：**修复完成，离线全量复跑通过**。接在上方 L3 执行记录之后，不改写其内容；B01—B06 浏览器复验仍归 Codex。

### B06：单轮工具预算守卫失效（产品缺陷，根因修复）

- 根因：`_prepare_analysis_turn` 先装配 `TurnExecutionState`，末行调用 `AnalysisFlowController.activate_tool_groups` → `registry.reset_groups()` → `ctx.reset_turn_state()` 把刚装配的预算状态清成 None。**整个 loop 路径上预算守卫与证据收据门从未生效**（`if turn_state is not None` 静默跳过）；Codex 的预算会话 206 次非元调用全部执行、无 budget_exceeded 即为此所致，此前所有"预算通过"类证据都不可信。
- 修复：`AgentContext` 新增 `reset_tool_groups()`（仅清分组路由）；`registry.reset_groups` 改用窄接口，不再连带清 `turn_state`；预算状态整轮存活。
- 连带修复：流式 `_process_tool_calls` 中 `_flow_controller` 缺失时 `regression_msg` 未绑定的潜在 UnboundLocalError（初始化为 None）。
- 契约更新：`test_loop_injects_synthesis_policy_before_final_answer` 的 stub 此前依赖"守卫已死"路径（无收据也接受证据）；修复后 stub 先真实执行 `run_python` 再记录证据。
- 新增回归：`test_prepare_analysis_turn_keeps_execution_budget_armed`（预算状态在 prepare 后存活）＋`test_streaming_loop_enforces_tool_budget_and_stops_execution`（205 次脚本化调用被真实 budget_exceeded 阻止：错误事件＋budget_exceeded 工具消息＋执行数 ≤ 上限）。

### B03：产出物面板与导出保留发布包来源

- `publication_synthesis.render_publication_receipt_markdown`：引用级收据渲染——每来源（工具＋收据 id＋source_dataset＋事实数）、omitted_refs（省略原因）、coverage 缺口行、已验证总数、待验证发现（状态文字＋尚缺＋下一步）；不含 rejected 候选、内部路径或原始证据 JSON。
- `loop._prepare_publication_packet`：packet ready 时把渲染结果写为 `publication_receipt` 类型产出物（每 packet id 一次，重复准备不重复注册）——浏览器"产出物"面板有可打开的收据文件。
- `report._publication_appendix`：会话 Markdown/HTML 导出追加同一收据附录（状态读取失败降级为无附录，不影响导出）。

### B04：数据版本变化 → 证据失效 → 假设 stale 的生命周期

- `trust_workflow_runtime` 新增 `_workspace_data_identities`（当前工作区数据身份）与 `_split_evidence_by_data_freshness`（纯函数：result_bindings 指纹与当前仍加载数据集**确实不一致**才排除；数据集不在当前工作区/无绑定 → 保守保留）。排除不删除证据记录，`evidence_exclusions`（含两侧指纹）随假设集持久化供审计。
- `maybe_create_hypothesis_set` 刷新时使用新鲜证据：版本变化后已判定假设按既有 P5 语义转 `stale`，假设集保留为历史。
- 工作台 `pending_findings` 增加 `stale` 状态（标签"失效（依赖证据已过期，历史结论）"），不进入已验证区。

### 验证（新 run-dir，Provider 禁用）

- B06/B03/B04 定向：`tmp/vp-l3-b04-green2` 94 passed、`tmp/vp-l3-b03-green5` 39 passed、`tmp/vp-l3-b06-regression` 424 passed。
- 完整离线回归（tmp/vp-l3-r-full-offline，JUnit sha256 前缀 `69e0f9d2b4a87c4e`）：**2518 tests / 0 failures / 0 errors / 1 skipped**（唯一跳过为按离线边界禁用的真实 Provider live smoke）。

### 浏览器复验要求（Codex）

- B06：重跑预算场景，断言真实 `budget_exceeded` 收据/错误事件与后续调用被阻止（脚本化"已触及预算"文本不算）；补保存失败、发布修订失败、pending confirmation 的同域收据。
- B03：产出物面板出现 `publication_receipt` 条目且可打开；Markdown 导出含来源/收据引用/omitted_refs/待验证标签。
- B04：以"同名数据集内容变更重载"驱动——支持 → 反证/版本变化 → 刷新后 `stale` 且以"失效"历史性质出现在待验证区。

---

## L3-R 浏览器复验（Codex，2026-09-07）

阶段 / 状态：**failed**。本节为 `7b9916e` 的新源码浏览器结果；此前各 run-dir 的通过结果不被用于替代本节中被修改链路的复验。

- 运行身份：`tmp/p7-browser-rehearsal-20`（B03）与 `tmp/p7-browser-rehearsal-22`（B04/B06）；普通 Flask Web、SSE、`AgentLoop`、真实工具、持久化、Workbench 和导出均在路径内，只有模型回答脚本化。所有 run 的 `runtime.jsonl` 均为 `forbidden_provider_transport=0`。
- 离线定向回归（本轮复跑）：`tests/test_execution_control.py`、`test_export_conversation.py`、`test_publication_synthesis.py`、`test_slice6_workbench_minimal.py`、`test_trust_workflow_runtime.py` → **101 passed**（唯一 warning 为 `.pytest_cache` 无写权限）。

| 场景 | 状态 | 浏览器与持久化事实 |
|---|---|---|
| B03 | passed | 会话 `33fd4eb42c5d`：产出物面板出现并可打开 `publication_receipt`（“计算来源说明”）；12 条收据、六个 `src_1…src_6` 来源、`omitted_refs=0`。浏览器触发的 Markdown 导出含“计算来源与省略说明”和全部六来源。 |
| B04 | failed | 会话 `fd2963b2c1f1`：同一计划内完成 supports → refutes，状态为 `contested`；再刷新仍非 `stale`。根因不是 freshness 判定函数，而是实际 `load_data` 明确拒绝已有名称的数据集（`数据集 'hyp' 已存在`），页面/API 没有替换当前版本的操作；三条证据的 data identity 指纹保持相同。离线测试以注入的当前身份覆盖了判定函数，未证明真实“同名重载”可达。 |
| B06 | failed | 工具失败会话 `d1d913b405b8` 保持“未发布计算结论”，无 verified/publication packet。预算会话 `fcd22e7b40c7` 在页面显示真实 `Tool call budget reached`；131 条收据（130 次 transform），含 75 条 `budget_exceeded` 工具消息，后续工具被阻止。保存失败、发布修订失败与 pending confirmation 没有新的同源码浏览器收据，不能把 B06 记为通过。 |

后续最小修复：为当前会话提供受审计的数据集版本替换/重载操作（保留旧版本身份、让已绑定证据可被 freshness gate 比对），并扩展 B06 演练为真实保存失败、发布修订失败和 pending confirmation 三条收据路径。P8 仍不可进入。

---

## L3-R2：受审计重载与 B04/B06 浏览器验收（Codex，2026-09-07）

阶段 / 状态：**passed（本地、Provider 禁用）**。本节只更新本地浏览器验收，不改变真实 Provider、部署或生产验证的证据边界。

### 实现

- `Workspace.archive_version` 将旧活动数据集转为唯一的 `<name>__history[_N]` 历史名称：保留 dataframe、`data_identity`、派生血缘和原始来源元数据，并写入 `archive_version` 血缘事件；它不删除或改写任何既有证据。
- 新工具 `reload_data` 只用于用户明确要求的同名版本更新。它先归档旧活动版本，再创建新的 raw 快照与同名分析版本，并持久化新版本、raw 快照和归档版本。普通 `load_data` 仍拒绝同名覆盖。
- B04 离线测试从注入 fingerprint 改为真实工作区版本操作；浏览器夹具使用 v1 的两个真实时间窗产生 `supports`（10→20）与 `refutes`（20→20），随后以 `reload_data` 重载平坦 v2。B06 夹具新增受限的保存失败注入，只覆盖 `【B06-SAVE】`，用于验证真实 Web/SSE 的 fail-closed 终止路径。

### 回归

- `tests/test_execution_control.py`、`test_export_conversation.py`、`test_publication_synthesis.py`、`test_slice2_workspace_versions.py`、`test_slice6_workbench_minimal.py`、`test_trust_workflow_runtime.py`：**111 passed**。唯一 warning 是受权限限制无法写入 `.pytest_cache`。
- 新工具经 `tests/support/tool_surface_manifest.json` 审查并纳入 76 项注册工具表面；完整离线回归 `scripts/testing/run_regression.py full-offline`：**2518 passed / 1 skipped / 16 warnings**。唯一跳过为禁用的真实 Provider smoke；warnings 为既有统计边界与 JUnit 属性兼容提示。
- `test_reload_data_archives_the_previous_active_version_without_rewriting_it` 断言历史 `orders__history` 的 dataframe、fingerprint 和版本号不变，新活动版本 fingerprint 不同，并存在会话备份。
- `test_b04_version_change_turns_supported_hypothesis_stale` 在实际 `Workspace`/`AgentContext` 中完成 archive→new active version，断言旧证据不删除、假设集保留、状态转为 `stale`。

### B04：支持 → 冲突 → 版本更新 → stale

- `tmp/p7-browser-rehearsal-23`，会话 `873fee8b13f2`：真实浏览器经 Flask/SSE/AgentLoop 执行 v1 加载、两次 `compare_periods`、结构化 supports/refutes、`reload_data(F-HYP-FLAT.csv, hyp)`。
- `workspace_meta.json` 保留 `hyp__history`（v1 fingerprint `sha256:041dd9…`）与新活动 `hyp`（v2 fingerprint `sha256:839744…`）；归档版本仍指向 F-HYP，活动版本指向 F-HYP-FLAT。
- 持久化假设集最终为 `stale`；三条原证据均在 `evidence_exclusions` 以 `data_version_changed` 保存 bound/current fingerprint。页面回复明确说明历史假设需以 stale 保留；刷新时触发并成功恢复了真实 `file_scope_selection` 确认，事件序列为 requested→suspended→response_received→applying→resolved。

### B06：四类失败边界

| 子场景 | 浏览器/持久化证据 | 结论 |
|---|---|---|
| 工具失败 | `tmp/p7-browser-rehearsal-23`，会话 `123c537a6150`：页面显示“未能找到所需数据集，未发布计算结论”；0 receipt、0 publication packet。 | passed |
| 预算 | 同 run，`e59b54a31774`：页面同时显示真实 `Tool call budget reached`；131 条 receipt（load_data + 130 transform），预算错误阻止其余请求，0 publication packet。 | passed |
| 发布修订 | 同 run，`4cc7dc3c164f`：浏览器不显示 D30=5% 候选；`conversation.json` 仅保留内部 `publication_rejected=true` 和一次受控修订，页面发布“只有 D1 至 D7，不能预测 D30”。 | passed |
| pending confirmation | 同会话两次方法确认在浏览器挂起并选择答案恢复；`confirmations/events.jsonl` 均为 requested→suspended→response_received→applying→resolved。 | passed |
| 保存失败 | `tmp/p7-browser-rehearsal-25`，会话 `0e51265d6402`：受限注入 `OSError` 后页面显示“执行状态无法完整保存，请勿将本轮视为分析完成”；`run_state.json` 为 `status=unknown`、`reason=OSError`，未将回答作为完成结果持久化。 | passed |

### 隔离与下一门

- 有效 run 的 `runtime.jsonl` 没有 `forbidden_provider_transport` 事件；`API_BASE` 为 loopback，Provider 网络、MCP 和自动 skill 发现均禁用。脚本化模型只替换模型传输，未替换 Web、SSE、AgentLoop、工具、持久化、发布或确认实现。
- 本节以当前源码完成 B04 与 B06；B01、B02、B03、B05 的浏览器通过证据属于此前源码基线，不能与本提交拼接为单一 digest 的 B01—B06 全量验收。若需要以本提交进入 P8，须在冻结源码上重跑这四个场景，并重新计算身份后取得用户对真实 Provider 的明确新授权。不得复用任何历史 Provider 授权。

---

## L3-R3：B01/B02/B03/B05 当前提交浏览器复验（Codex，2026-09-07）

阶段 / 状态：**B01、B02、B05 passed；B03 failed（本地、Provider 禁用）**。本节在 `156f0b46064f0b41a2939ef625015005bd9bd71b` 上执行；运行目录为 `tmp/p7-browser-rehearsal-26`。脚本化模型仅代替模型传输，真实 Flask Web、SSE、AgentLoop、工具、确认、持久化、Workbench 和导出均在验收路径内；`runtime.jsonl` 的 `forbidden_provider_transport` 计数为 0。

| 场景 | 状态 | 当前浏览器与持久化事实 |
|---|---|---|
| B01 | passed | 会话 `73a985ea91e3`。页面发布“当前 12 条订单金额合计为 120”，且同时给出可验证行动阈值和“不能外推总体”的限制；刷新后会话仍完整存在。3 条工具收据、1 个发布包，并由浏览器生成计算来源收据与 Conversation Export。 |
| B02 | passed | 会话 `43fedbfeedf8`。页面先进入真实 method confirmation；选择“仅做描述性探索”后恢复，发布“D7 留存为 10%，当前不能预测 D30，建议继续收集至 30 天”。刷新后会话、2 条收据、1 个发布包和两份 Markdown 产出均保留。 |
| B03 | failed | 会话 `9a76617ea035`。六个来源都真实执行并持久化（12 条工具收据，`src_1…src_6` 数据版本均存在），页面也可打开 `publication_receipt` 和 Conversation Export；但发布包只展开 `src_3…src_6`。`src_1`、`src_2` 被写入 `omitted_refs`，导出仅保留其 receipt id 和“可恢复”说明，未保留金额或记录数。原因是来源选择只按问题文本与英文/结构化 receipt 文本的字面匹配排序；本场景的中文“六个来源/保留全部”没有命中各来源，随后回退到最近四条。该行为不满足“保留全部来源”的验收目标，不能用可恢复的内部收据替代公开产出中的来源内容。 |
| B05 | passed | 会话 `0c16b12e658a`。同一会话先建立受限的订单结论，随后业务、分析师、管理层、大白话和技术表达分别按受众改变表达；分析师/技术回答保留 `f_sales_total`、`group_aggregate`、`amount_sum=120`、`amount_count=12`，大白话不泄露技术措辞，切回技术表达后恢复。刷新后全部五段回答仍在，浏览器生成 Conversation Export。 |

### 验收判断与后续门槛

- B01、B02、B05 已补齐当前提交的本地浏览器、刷新和 Markdown 导出证据。
- B03 是内容保留链路的产品缺陷，而不是演练夹具或浏览器读取误差；在它修复并以相同场景复验前，B01—B06 不能记录为全量通过，P8 仍不可进入。
- B04、B06 的浏览器证据来自 L3-R2 中与本提交相同的产品实现；本提交相对其运行时的产品差异仅为工具表面清单和验收文档。它们仍是本地、Provider 禁用的证据，不能推导为真实 Provider、部署或生产验收。

---

## L3-R4：B03 全来源发布与导出修复（Codex，2026-09-07）

阶段 / 状态：**passed（本地、Provider 禁用）**。本节替代 L3-R3 中 B03 的 failed 结论；其余场景的历史证据边界保持不变。

### 根因与修复

- 根因：`_select_sources` 已有 `_SOURCE_CAP = 8`，但在词项无命中时仍错误使用历史 `_MAX_SOURCES = 4` 回填。B03 的“六个来源/保留全部来源”是中文集合要求，而各 `compare_periods` 收据是结构化/英文指标，词法匹配未命中；因此最近四条入包、前两条仅以 `omitted_refs` 留存。
- 修复：普通回填统一采用 `_SOURCE_CAP`；用户明确要求“所有/全部/全量/完整/逐一/每个/各个”来源、数据源、渠道或分组时，全部本轮成功来源进入发布包，不以内部收据引用替代公开内容。
- 导出修复：`publication_receipt` 与 Conversation Export 逐来源渲染已选且已受预算约束的事实（字段和值），仍不渲染原始工具 JSON、内部路径或被拒绝候选。

### 回归与浏览器复验

- 新回归 `test_b03_explicit_all_sources_request_retains_every_source_with_facts` 覆盖中文“保留全部来源”、六来源入包、无 `omitted_refs` 与导出事实逐项可见；发布/导出定向回归 **39 passed / 1 warning**。
- 完整离线回归：`scripts/testing/run_regression.py full-offline`，目录 `tmp/test-runs/20260907T072828Z-915f062e`，**2519 passed / 1 skipped / 0 failures / 0 errors**。唯一跳过为禁用的真实 Provider smoke。
- 浏览器：`tmp/p7-browser-rehearsal-28`，会话 `5e96deb9a279`。真实 Flask/SSE/AgentLoop、工具、持久化、Workbench、Markdown 导出与刷新路径执行完成；12 条收据、6 个发布来源、0 个 `omitted_refs`。`src_1…src_6` 各有 10 项已发布事实，导出的两个 Markdown 文件均包含六个数据集、金额前后值（10→11 至 60→66）和六个 `combined.row_count=2`。刷新后会话和 Conversation Export 仍在；`forbidden_provider_transport=0`。

### 当前门槛

- B03 的“全部六个来源进入发布包、第四组及之后数值保留、导出完整”本地验收通过。
- 本轮没有真实 Provider、部署或生产调用。进入 P8 前仍须冻结待验源码、重新计算身份，并获得用户对该次真实 Provider 执行的明确新授权；历史授权不得复用。


---

## P08-R：P08 浏览器验证问题修复（P08-01—P08-05，2026-09-08）

阶段 / 状态：**修复完成，离线全量复跑通过**。依据 [P08 问题记录](2026-09-07-p08-browser-validation-issue-record.md) 与 [意图澄清设计 §10](../specs/2026-09-07-intent-clarification-design.md)。B 场景复验归 Codex；P08-06（导出文件落地核对）与 Provider 请求账本按问题记录约定留到下一轮真实浏览器验证。

### P08-01：退役通用方法审批（静态确认链根因修复）

- 根因链（设计 §10.1 已证实）：`select_playbooks` 把模板 `confirmation_policy.requires_confirmation` 映射进 `PlaybookSelection` → `apply_selection_to_state` 创建 `source=method_playbook` pending → controller 以同一静态位封锁四类能力 → detector 的高风险关键词门。M02 的“Forecast & Decision Simulation 方法确认”即此链产物。
- 修复：`PlaybookSelection.requires_confirmation` 恒为 False（模板风险说明降为 `template_risk_note` 审计元数据）；`apply_selection_to_state` 停发方法 pending（spec/推荐路径/数据要求照常写入）；`is_capability_blocked_by_confirmation` 重写——能力名称不再是确认理由，只有**当前可操作且 `affected_operations` 明确覆盖该能力**的语义确认才阻塞；detector 删除“高风险关键词＋未批准 method_confirmation”硬门（时间窗/指标/字段/文件范围等具体缺口门保留）。
- 旧会话兼容（L01—L03）：`confirmation_policy.retire_method_approval_confirmations` 在 `prepare_turn` 幂等退役纯方法审批（status=retired＋retired_reason=policy_retired，不伪批准、保留审计）；带语义字段（missing_value/affected_operations/decision_kind）或来源不明的记录不动。
- 契约更新：11 个固化旧审批行为的测试改写为新正反例（历史需求在注释中说明）；新增 `tests/test_p08_confirmation_convergence.py`（Q13 三层不门控、Q14 四例、L01—L03 四例）。

### P08-03：显式任务优先于内部路线选择

- `question_need_detector.explicit_task_reason`：窄合取判定（假设任务动词短语/竞争假设对象＋任务动词/“分别分析”枚举）；“帮我看看”仍是可澄清泛化指令。
- detector 的 vague-route 门与 entry 的路线澄清都加 `not explicit_task_reason` 旁路；明确任务时 entry 取内部默认路线并在决策 reason 记录 `explicit task (...)` 供审计，不把 trend/period_compare 选择交给用户。

### P08-02：边界结论正常终结（先复现后补丁）

- 离线复现（`tests/test_p08_boundary_finalization.py`，真实流式 loop＋真实工具）：守卫与发布链本身工作正常——探索调用被 fallback-resolution 正确拦截、干净边界答复（“D7 为 10%；不能预测 D30，缺少 D8—D30 观测”）成功发布。真实失败为模型侧行为＋错误文案像终态。
- 补丁（按设计 §10.4 第 1/3 行）：fallback-resolution 拦截后追加 `<fallback_resolution_guidance>` 系统消息，指明两条合法继续路径（记录证据／直接发布带边界的终稿，“带证据边界的拒答是有效完成状态”）；**通过发布检查的最终答复清除 `pending_fallback_resolution`**；流式与同步两条路径一致。
- S02 反向保护保留：curve_fitting 观测范围下的无依据 D30 数值仍被拒绝（负例走 curve 变体——run_python 无范围元数据，宿主不可判）。

### P08-04：工具消息协议完整性

- `compact.validate_tool_message_sequence`（纯函数：tool 必有 tool_call_id、须对应未闭合 assistant 调用、无重复结果、assistant 调用须全有结果）＋ `drop_orphan_tool_messages`（投递副本剔除孤立 tool 消息，原始历史不删）。
- loop 两条 LLM 轮路径投递前经 `_provider_messages()`：剔除＋校验，仍有违规则本地可恢复诊断（`invalid_tool_message_sequence`），不把非法序列发给 Provider。
- `_serialize_messages` 保留 `assistant.tool_calls`（id/type/function，参数截断 2000 字符）与 `tool.tool_call_id`——只写 role/content 会在恢复后制造孤立 tool 消息（M04 BadRequest 的主要假设来源）。
- 回归：`tests/test_p08_tool_message_integrity.py` 七例（单测四例＋M04 版本重载端到端一轮恢复＋序列化保真）。

### P08-05：无数据最短恢复

- `_build_system_prompt` 在工作区无数据时注入 `<no_data_recovery>`：说明缺少数据＋一个明确上传/选择入口；不列未来路线菜单、不追问无关业务背景、不推测答案。有数据时不注入。E1 两例。

### 验证（新 run-dir，Provider 禁用）

- 定向（确认栈全家＋P08 三个新文件＋受影响模块）：`tmp/vp-p08-targeted` **309 passed / 0 failed**。
- 完整离线回归（tmp/vp-p08-full-offline-r2，JUnit sha256 前缀 `b7a8a33df91a10d5`）：**2543 tests / 0 failures / 0 errors / 1 skipped**（唯一跳过为按离线边界禁用的真实 Provider live smoke）。第一次全量（tmp/vp-p08-full-offline）1 failed：无数据提示用例在套件顺序下被进程级 workspace 单例残留数据干扰——测试改为显式 monkeypatch `list_datasets` 返回空，与执行顺序无关；产品行为无问题。

### 交接（Codex 复验重点）

- Q13/Q14 浏览器复验：D7/D30 请求不得出现方法确认卡；竞争假设请求直接产出假设与证据状态。
- M04 复验：版本重载后无 Provider 400；（可选）注入孤立 tool 消息验证本地恢复。
- M06 复验：无数据回复简短＋单入口。
- P08-06 导出文件落地与 Provider 账本按原计划留待下轮。

---

## P08-R2：独立本地浏览器复验与工具协议回归修复（Codex，2026-09-08）

阶段 / 状态：**P08-01—P08-05 在 Provider 禁用的本地浏览器矩阵中通过；P08-06 与真实 Provider 请求账本仍未验收。** 本节验证用户提交 `aeddceb` 后的当前工作树。脚本化模型只代替模型传输；Flask、SSE、AgentLoop、真实工具、会话持久化、版本重载和发布链均实际执行。运行目录为 `tmp/p08-browser-rehearsal-verify-r2`；其 `runtime.jsonl` 仅记录 `server_start`、`auxiliary_call`、`scripted_round`，没有 `forbidden_provider_transport`，因此本次 Provider 发起调用为 0。

| 场景 | 状态 | 复验事实 |
|---|---|---|
| M01 / B01 | passed | 会话 `98bf86124959` 发布 12 条、金额合计 120，并说明条件性行动与不可外推限制。 |
| M02 / B02 | passed | 会话 `4fec9ba4204b` 直接发布 D7=10% 与“不能预测 D30”的证据边界，未出现方法确认卡。 |
| M03 / B03 | passed | 会话 `ad13ccbdab48` 保留并汇总全部六个来源。 |
| M04 / B04 | passed | 会话 `ec2d285e59b4` 对显式竞争性假设不要求选择内部路线；完成支持、反驳和 `reload_data` 后，历史假设保留为 `stale`，刷新后会话正常恢复。 |
| M05 / B05 | passed | 会话 `d622e18aa2ad` 的业务、分析师、管理者、通俗和技术表达有明确差异，核心事实均保持 120、12 条和不可外推。 |
| M06 / B06 | passed | 会话 `f05bf304caae` 在无数据时只说明未找到数据集、未发布计算结论，并给出一个加载数据入口。 |

### P08-04-R：已完成工具调用 ID 的跨轮复用

- 首次复演发现 `compact.validate_tool_message_sequence` 将所有历史结果 ID 记录为全局已见；P7 脚本模型在**前一轮已完整闭合**后再次使用 `p7-1-compare_periods`，被误判为 `invalid_tool_message_sequence`。这不是 Provider 拒绝，也不代表同一未闭合调用出现重复结果。
- 修复后，调用 ID 仅在当前未闭合的 assistant tool-call 块内唯一；完成匹配后可被后续独立轮次复用。`drop_orphan_tool_messages` 也改为按顺序配对，避免早期孤立结果因未来同 ID 调用而被错误保留。
- 新增两项回归覆盖“已闭合 ID 可跨轮复用”和“未来同 ID 不得挽救早期孤立结果”。定向回归为 **118 passed**；完整离线回归 `tmp/test-runs/20260907T171940Z-b88daacb/junit.xml` 为 **2544 passed / 1 skipped / 0 failures / 0 errors**（共 2545 项）。

### 证据边界与后续

- 本节证明当前代码在 Provider 禁用、脚本化模型的真实 Web/SSE/AgentLoop 路径可完成 B01—B06 主流程；它不证明真实模型接受度、真实 Provider 请求账本、浏览器下载文件落地、部署或生产行为。
- P08-06（导出文件落地）和请求账本依原优先级保留至下一次获明确授权的真实浏览器、真实 Provider 测试；不得将本次 0 Provider 调用外推为该类验收。

---

## P08-R3：真实 Provider 矩阵首次启动（Codex，2026-09-08）

阶段 / 状态：**全局阻断，批次未验收；M01 failed，M02—M06 blocked_not_started。** 用户对本批作出新的真实调用授权后，先完成零调用预检，再通过真实浏览器上传隔离夹具并发送 M01。未重试、未切换模型或端点，也没有发送其余矩阵场景。

### 冻结身份与已完成浏览器事实

- 冻结：`tmp/p08-real-provider-20260908-r2/freeze.json`；源码提交 `19eb2b4b956be6d7dd6128b670091fbcdc2e3e69`，启动器摘要 `sha256:61b948875ff812c43502b31417216e7899ad53df408e8b2f182b53ea8d6ffe88`，模型 `openai/deepseek-v4-flash`，端点 `https://api.deepseek.com`，M01—M06，调用上限 120。
- 浏览器实际创建会话 `d609704788e0`，并通过页面上传 `M01-sales.csv`。`uploads/*/upload.json` 记录 `status=loaded`、sha256 与冻结夹具一致；会话的 `analysis_state.json` 记录 12 行、4 列数据已加载。故本次失败不能归因为夹具未上传、会话隔离或本地数据加载。
- 页面在真实调用期间停留于“调用工具中 / 分析数据”，没有模型正文、工具收据、发布包或结论。终止操作后 `run_state.json` 为 `status=cancelling`；这是失败状态证据，不得标记为完成。

### 调用账本与停止理由

- 权威账本为 `tmp/p08-real-provider-20260908-r2/provider-calls.jsonl`。它记录 **8 次 `started`，8 次对应 `failed`，错误类型均为 `InternalServerError`**，无 `dispatched` 事件。账本只能证明本地已发起八次调用并收到该错误，不能推断 Provider 侧计费或配额结算。
- M01 的首次辅助调用发生默认四次重试；其后第二条辅助路径又发生四次重试。根因尚不能从已落盘错误类型确定为模型名、端点、凭据、Provider 服务或请求体；禁止以同一授权补发探针来猜测。
- 这同时暴露验收控制缺陷：当前启动器仅记录物理调用，但未将默认 `RequestPolicy(max_attempts=4)` 收敛为单次尝试。后续仅可在**新的代码冻结、零调用预检和新的明确授权**后运行，并须先让主与辅助 LLM 客户端都使用 one-shot 策略。
- 因连续真实调用在第一场景即全部失败，属于 P08 的账户/基础服务或请求路径全局不可用情形。本批立即停止；M02—M06 不得用本地演练结果代替，也不得复用本批授权或目录。
- 后续控制修复已加入验收启动器，并由 `tests/test_p08_real_matrix_launcher.py` 在无网络条件下验证：即使调用方显式给出其他策略，验收进程也强制 `ONE_SHOT`。该源码变更使 R3 冻结失效，未使用它发起任何新的 Provider 请求。

---

## P08-R4：one-shot 冻结下的真实 Provider 复验（Codex，2026-09-08）

阶段 / 状态：**全局阻断，批次未验收；M01 failed，M02—M06 blocked_not_started。** 这是用户对当前 `18c3330`、模型 `openai/deepseek-v4-flash`、端点 `https://api.deepseek.com` 和 120 次上限作出新授权后的独立批次。冻结目录为 `tmp/p08-real-provider-20260908-r3`，其中 `request_policy=one_shot`；其零调用预检与 `tests/test_p08_real_matrix_launcher.py` 均通过。

- 真实浏览器会话 `70d93eea2686` 通过页面上传 `M01-sales.csv` 后发送 M01。`upload.json`、`analysis_state.json` 与 `workspace_meta.json` 均显示夹具已加载、会话隔离完好；页面最终显示 `provider_request_failed`，具体链为 `InternalServerError ... OpenAIException - Connection error`，`run_state.json` 为 `status=failed`。
- 权威账本 `provider-calls.jsonl` 记录 **4 次 `started` 与 4 次 `failed`，无 `dispatched`**：前三次为 `stream=false`，第四次为 `stream=true`。这证明同一会话的辅助与主路径均无法建立 Provider 请求；由于每个 `LLMClient` 已被强制 one-shot，这四次不是同一客户端的重试循环。
- 账本当前未记录调用 purpose，不能仅由 `stream` 字段判定前三次分别属于哪一个内部决策步骤；但它能确定调用次数、模型、流式属性和错误终态。不得将 4 次未调度成功的本地记录外推为 Provider 实际计费。
- 该错误覆盖辅助和主路径，属于 P08 的 Provider 连通性/基础服务全局异常。服务与浏览器已关闭，未切换模型/端点、未补发诊断请求，也未执行 M02—M06。当前授权已消耗；后续只有在明确定位配置或 Provider 可用性后，以新的冻结与新授权才能启动完整矩阵。


---

## IC0—IC3：需求对齐与必要澄清专项实施（2026-09-08）

阶段 / 状态：**IC0—IC3 完成，全量离线复跑通过**。依据 [意图澄清计划](2026-09-07-intent-clarification-plan.md) 与 [开发设计](../specs/2026-09-07-intent-clarification-design.md)。IC4 的 E3 浏览器（B01—B06）与 IC5 真实 Provider 仍归 Codex / 另行授权。

### IC0：契约映射（记录）

- 生产者→策略：`question_need_detector` 六类门、`ask_user_question` 直接询问、multi_file_scope；`method_playbooks` 生产者已在 P08-01 退役。
- 消费者：`ConfirmationService.request`（经 `QuestionPolicy`）→ loop `_suspend_for_confirmation_request` / `_suspend_for_required_question_payload` / `_maybe_auto_suspend_for_required_question`；`AnalysisFlowController.is_capability_blocked_by_confirmation`（能力门，P08-01 已重写）。
- 复用键既有缺陷确认：`decision_key` 含 `message_version`/`turn_id`（同问题再问必为新键）；`data_version=messages:N` 随消息数变化——R01/R02 在结构上不可能成立。本阶段以稳定语义键修复。
- 冻结字段位置：决策上下文放 `resolution_params`（decision_kind/missing_value/affected_operations/business_scope/default_origin/scope_data_version）；`UserConfirmationRequired` 增加 `decision_context` 载体；旧记录兼容由 `retire_method_approval_confirmations`（P08-01）与既有事件状态机承担。

### IC1：统一决定策略核心

- 新模块 `agent/confirmation/decision.py`（纯函数）：决策上下文规范化（gate 类型→decision_kind 映射，含 file_scope_selection）、方法形状判定（仅许可式动词＋方法名词合取，"分析方法"不命中）、宿主可验证 default_origin 集合、业务范围规范化（保留否定与数字）、稳定复用键（session+decision_kind+范围+选项值）、最小业务缺口契约（decision_kind＋missing_value＋affected_operations 三要素）。
- `QuestionPolicy` 重写：REUSED 先行；方法形状→ADVISORY；`safe_default` 仅宿主可验证来源可降级（Q12：模型自报不信任）；非业务缺口→ADVISORY；复用匹配兼容稳定键。
- 回归键语义（R01—R05）：同义改写复用、消息数不换键、范围变化不复用、相关数据版本变化阻断复用、无关文件变化不影响未版本化决定；仅 RESOLVED 可复用（R08）；无语义范围的候选保持逐次键（不可验证的不复用）。

### IC2：入口接通与恢复

- `runtime._build_question_candidate`：决策上下文注入（gate 载荷 risk_fields/affected_routes/blocked_surfaces→三要素；`decision_context` dict 载体优先）；稳定键替换逐次键；`data_version` 改为 scope_data_version（空＝未版本化）；`safe_default` 字段映射；`_resolution_params_for` 透传决策上下文字段。
- loop 两条挂载路径（同步/流式）＋直接询问：ADVISORY/REJECTED→一次正常工具响应并继续本轮（`_nonblocking_confirmation_response`）；REUSED→返回既有答案文本，不对旧 resolved record 再悬挂；`_maybe_auto_suspend_for_required_question` 在旧 pending 被降级时贯穿到本轮新检测的真实语义问题（方法审批让位）。
- 契约更新：6 个固化"方法 pending 优先/阻塞"的测试改写为新正反例（历史需求注释保留）；确认栈夹具补决策上下文。

### IC3：方法选择与计划覆盖

- `PlaybookSelection` 增加 `primary_source`（llm/keyword/default）与 `supporting_source`（llm/rule）审计字段（O01/O02：主方法来自 LLM＋辅助来自规则是合法组合，不谎报失败）。
- 复合整体目标优先（M01/M02）：`_is_composite_feature_goal` 合取判定（功能/效果/行为 × 收益/复购/付费价值词同时肯定）→ product_feature_analysis 主线，子指标进 supporting，不被"复购"等子指标关键词抢占主方法。
- 否定邻接修复（M06 根因）：`has_affirmative_keyword` 增加紧邻前缀"不/没/无"判定——"不预测 D30"在分句截断后不再把"预测"当肯定词，不再误选 forecast_decision_simulation。
- M03/M04 由既有否定感知（P2 套件）＋新合取规则覆盖；新增 `tests/test_method_selection_coverage.py`（M01—M04、M06、O01—O02）。

### 验证（新 run-dir，Provider 禁用）

- 确认栈定向（policy/runtime/service/models/continuation/session_api/actions/interaction/decision + P08 三件套 + execution_control/method_playbooks/question_need_detector/analysis_entry/method_selection）：`tmp/vp-ic2-full3` 起多轮收敛至 **285+ passed**；意图/策略族 268 passed（`tmp/vp-ic3-m3`）。
- 完整离线回归（tmp/vp-ic-full-offline，退出码 0）：**2569 tests / 0 failures / 0 errors / 1 skipped**（唯一跳过为按离线边界禁用的真实 Provider live smoke）。

### 交接（Codex / 后续）

- IC4 的 B01—B06（E3 浏览器）与 S 系列既有反例复验、IC5 真实 Provider 对照按验收矩阵执行；本阶段离线用例为 E1/E2。
- Q09—Q11 的 E2 层由 `TestLoopDirectAskIntegration`（advisory 工具响应/REUSED 答案恢复/真语义悬挂）与既有 confirmation_runtime 套件覆盖；R06—R10 中跨会话/幂等既有测试继续通过。
