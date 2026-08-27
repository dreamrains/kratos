# 7 月大改系统性复查清单（Data Agent）

- **日期**：2026-08-13
- **基线**：`main` @ `e45c1e8`（M1 + M1.1 + M2-A/B/C 已合并）
- **复查窗口**：`04ef1c6`（2026-07-18）→ HEAD，共 100 commits，+24,790 行
- **方法**：以 `04ef1c6` 为界，对 `src/`（全量）+ web 层分 4 路并行深度审计（流程 / 质量 / 呈现 / 前端），每条结论均带 `file:line` 锚点，回归项用 `git show 04ef1c6:<path>` 比对过 7 月前行为。
- **目的**：产出分类清单 → 确认后按「流程→质量→呈现→前端雕琢」优先级逐项修（每项 TDD + 实测验证）。

---

## 0. 背景与已锁定标准（评审请先读）

**项目**：Data Agent —— 面向**缺乏数据科学知识的用户**的中文专业数据分析 Agent。CLI(REPL) 或 Flask Web GUI，经 litellm 接 LLM，提供 40+ 分析工具。Web GUI 端口 5001。

**已修复（无需再动，列在这里避免重复讨论）**：
- **发布瘫痪**：7 月的 publication/assurance gate 会**删除**通不过严格审计的有效 claim、注入"无法发布该数值"占位符。M1 已把发布改为**无条件非破坏**（live loop 恒走 transparent 模式，`evaluate_fatal` 只被离线 golden harness 调用，不在 live loop）。
- **scope/确认/推进阻断**：已解。
- **合成掐断**：M2-A 已移除 2400 字封顶、弱化"无目录证据则给部分答案"指令（改为数据为本规则）。
- **绑定/scope 竞态**：M2-B 已把 `current_task_dataset_unavailable` 改为 advisory，任务推进到终态不再中途杀掉 `create_chart`。
- **统计严谨性**：7 月后反而**增强**——样本量规则从"统一行数阈值 < 30"改为"按所选方法/设计评估"（`prompts.py:193`）。

**锁定目标**：服务非专业用户 → **严谨的结论 + 专业的流程 + 对非专业用户友好的表达**。
- **严谨是最高标准，不得过度声称**。
- **数据为本**：所有结论/证据须在用户实际数据范围内；超出数据的判断只能作为**降级的提示性内容且诚实标注**，不得伪装为数据支撑。
- 严格遵循**已定义的分析流程**（playbooks / method_plan / analysis_requirements）；若复查中发现已定义流程本身不合理，**先提出讨论，不擅自改流程**。

**锁定确认门禁标准**：会话内 copy-on-write 操作（raw 保留 + 每步版本化 + 可逆）**一律自动放行，仅记入 lineage，不打断用户**。包括：类型转换（含部分/空值/基数/置信/失配信号）、材料清洗（去重/删除/填充/截尾/异常值），**以及高风险分析能力（因果/预测/实验/分类）——它们是计算不是破坏，靠诚实标注兜底，不靠事前确认**。确认仅留给**真正不可逆或跨会话边界**的操作（删除数据集、覆盖外部文件、导出）。

**分析质量标尺**：(1) 基于对话+数据制定合理分析方法；(2) 给出严谨结论，含**方法说明 + 统计说明**（置信度、统计局限等）；(3) 由 **LLM 自主决定是否给可执行建议**（曾作为独立功能设计——需核查是否仍可用）；(4) 按**金字塔原理**输出，**图表恰当使用**（正文引用的图内联在相关内容旁；无正文引用的图附在末尾）；(5) 审视既有代码是否有更优标准。

---

## 1. 总览

瘫痪层已修。真正剩下的不是"瘫痪"，而是**三组跨层问题**，外加若干质量放松和前端打磨：

1. **图表**：① 流程层不创建（预算饿死 + 合成提示禁调 + 完成度测不到）→ ③ 呈现层内联空白。**三层必须成组修，单独修任一层无效。**
2. **实时流**：③ 呈现层服务端把分析答案缓冲到审计后才一次性吐 → ④ 前端进度信号被自家循环覆盖（FE2）/ 收集了但从不渲染（FE3）/ 渲染 O(n²) 卡顿（FE8）。用户体感=流式坏了、要刷新。
3. **确认门禁**：① 流程层高风险分析（F4）+ 类型转换（F5）仍中途打断，违反锁定标准。

性质标注：`[回归]`=7 月引入　`[既有]`=7 月前就存在　`[设计]`=7 月有意为之。

---

## 2. ① 分析流程（Flow）

### F1　[P0] chart 步骤被探索预算饿死 — **chart 不执行的主因**
- **锚点**：`src/data_agent/agent/execution_control.py:93,184,352-355` + `src/data_agent/agent/loop.py:1187-1201`
- **性质**：`[回归]`
- **问题**：`create_chart` 不在 `_META_TOOLS`（`execution_control.py:20-33`），被当作探索工具消耗探索预算。chart 计划步骤（`method_playbooks.py:1088-1101`）在每个计划中**排在最后**。当 agent 到达它时，`exploration_budget_exhausted` 几乎必为 true。此时调 `create_chart` → `ensure_can_call` 抛 `BudgetExceeded` → loop 写入 `budget_exceeded` 并 `return` 结束回合（`loop.py:4183-4192`）。agent 观察到错误后以"正在生成图表"的叙述结束回合。
- **证据**：合成预留触发条件 = `remaining_phase_tokens("exploration") <= synthesis_reserve_tokens`（= `total*0.08`，`loop.py:1196-1201`）。`analysis` profile 下探索预算 = `70000*0.80=56000`，预留触发阈值 `≤5600`——即约 5 万 token 分析后图表即被锁死。7 月前（`04ef1c6`）无 `visual.chart` 计划步骤、无 phase-budget 机制。
- **方向**：让 `create_chart` 享受 meta 工具的豁免；或更彻底——**把当前计划中尚未绑定的非发布步骤排除出合成预留触发**。计划已声明作图为方法完整性的一部分，预算层应尊重。

### F2　[P0] 合成提示硬性禁止工具调用（第二杠杆）
- **锚点**：`src/data_agent/agent/synthesis_policy.py:264-270`
- **性质**：`[回归]`
- **问题**：合成预留触发后，`build_synthesis_instruction` 注入 `<synthesis_evidence_discipline>`，字面写：**"最终回答生成期间不要调用任何分析、计划或证据记录工具"**。即便预算放开，提示本身也鼓励 narrate 而非真正调 `create_chart`。
- **证据**：该段无条件追加到每个合成策略（`synthesis_policy.py:243-271`），未对 `visual.chart` 开例外。
- **注（待修时验证）**：字面只禁 analysis/plan/evidence 三类，`create_chart`（capability `visual.chart`）是否真被命中需在修时确认；F1 是硬阻断，此条为"加固"。
- **方向**：(a) 推迟进入合成相位，直到计划的 `visual.chart` 步骤已绑定/满足；或 (b) 软化该段，禁 analysis/证据工具但显式放行计划中待执行的 `visual.chart` 步骤。

### F3　[P0] chart 步骤对完成度检查不可见 — 无安全网
- **锚点**：`src/data_agent/agent/method_playbooks.py:1098` + `src/data_agent/agent/analysis_requirements.py:255-257` + `src/data_agent/agent/execution_control.py:664,905-911`
- **性质**：`[回归]`（M2-C 占位）
- **问题**：chart 步骤被赋予 `evidence_requirements: ["limitations"]`（代码注释承认"chart 不是注册类别"）。但 `"limitations"` 映射到 category `"limitation"`（`analysis_requirements.py:255-257`），属于 `_PUBLICATION_REQUIREMENT_CATEGORIES`（`execution_control.py:664`）。后果：(a) 若该需求未满足会被分类为 `publication_only` → **不可恢复** → 不触发续跑（`execution_control.py:905-911`）；(b) 更糟——**其它每个步骤都产出 limitations 证据**（capability-default map 把 `limitations` 附到 `data.describe`/`data.profile`/`analysis.top_n` 等，共 9 处），所以漏画图时 chart 步骤的需求**已被其它步骤满足、产生零未满足需求**。完成度评估器永远不会发出"图没画"的信号。
- **方向**：给 chart 步骤一个专属需求类别（如 `visualization`/`output.chart`），其满足依赖真实的 `visual.chart` 计算 ref；并把它排除出 publication-only 短路，使缺图可恢复。

### F4　[P1] 高风险分析仍被 method_confirmation 拦截
- **锚点**：`src/data_agent/agent/analysis_flow_controller.py:391-431` + `src/data_agent/agent/method_playbooks.py:420,451,509,596`
- **性质**：`[回归]`
- **问题**：锁定标准说 causal/forecast/experiment/classification 是**计算不是破坏**，应会话内自动放行。但 4 个 playbook（`retention_lifecycle`/`evaluation_causal`/`effect_evaluation`/`forecast_decision_simulation`）仍设 `confirmation_policy.requires_confirmation=True`，挂起 `method_confirmation`。`is_capability_blocked_by_confirmation` 随即**阻塞** `analysis.causal/forecast/experiment/classification`，直到用户显式 resolve `confirm_method`（`flow_controller.py:416-431`）。阻塞时 loop 写 `confirmation_required` 并 `return` 结束回合——一次中途打断。
- **证据**：`confirm_method` 需用户显式作答（`confirmation/runtime.py:284-288,329-349`），无自动批准路径；M1 的 `2bdb114` 只自动批准 derived dataset version，不含 method 确认。
- **方向**：要么从这些 playbook 去掉 `requires_confirmation`（靠 claim 级严谨上限兜底），要么会话内把 `method_confirmation` 自动 resolve 为 `approved` 并记入 lineage。

### F5　[P1] 类型转换确认门对会话内 copy-on-write 触发
- **锚点**：`src/data_agent/tools/data_clean.py:853-861,899-973`
- **性质**：`[回归]`
- **问题**：`apply_type_conversion` 操作的是版本化分析副本（raw 保留），但任一风险信号触发（`new_nulls>0`/`cardinality_loss>0`/部分转换/低置信/后缀解析）就 `requires_confirmation=True` 并 `_request_transformation_confirmation`，返回 `status: confirmation_required` 而**不落地转换**。按锁定标准，副本上的类型转换应自动放行并记入 lineage。此处操作悬空，下游用未转换数据或卡住。
- **方向**：会话内版本副本无条件应用候选，把风险信号+指纹记入 transformation record/lineage；确认门只留给真正跨会话操作（导出/删除/覆盖外部）。

### F6　[P3] `max_chart_calls` 预算字段是死代码
- **锚点**：`src/data_agent/agent/execution_control.py:65,113`
- **性质**：`[既有]`
- **问题**：`ToolExecutionBudget.max_chart_calls` 与 `TurnExecutionState.chart_calls` 声明且自增（`:404-405`）但从不校验，`ensure_can_call` 不查、无 profile 设默认。形似图量护栏实则无效，会误导修复。
- **方向**：删除，或真接成每回合图量预算。

### 已验证未坏（平衡记录）
- **M2-B 绑定/scope 竞态**：已修。`execution_scope.py` 一致把 `current_task_dataset_unavailable` 记为 **advisory** 并放行（`:418-420,489-492,674-692,751-757,818-825`）。
- **`create_chart`→`visual.chart` 绑定**：注册映射正确（`tools/registry.py:545`），若调用被允许，绑定本可工作。
- **提示鼓励 create_chart**（`prompts.py:50-54,97`）；缺口不是缺提示 nudge，而是预算+合成纪律覆盖。

---

## 3. ② 分析质量（Quality）

### Q1　[P1] `insight_depth` 封顶 light/standard，无 deep 档
- **锚点**：`src/data_agent/agent/synthesis_policy.py:164`（analytical）、`:136`（advisory）、`:81`/`:99`（direct/exploratory）
- **性质**：`[既有]` `[RELAX]`
- **问题**：分析路径（每个有证据的 `directed_analysis` 默认）发 `insight_depth="light"`；advisory/完整报告最多到 `"standard"`。全代码无 `"deep"`。连"完整分析报告"意图（基础提示 `prompts.py:223` 说应"多维度深度分析"）也只在 standard 下合成 → 深度封顶。
- **证据**：grep 确认仅 `none`/`light`/`standard`。7 月前 analytical 已是 `"light"`，是既有封顶非回归，但仍是恢复未触及的活跃质量杠杆。
- **方向**：加 `"deep"` 档，`comprehensive_report` 意图选用（可选：`len(evidence)>=N` 且验证通过时）。低风险——`insight_depth` 纯属 LLM 读取的属性，下游无分支依赖其值。

### Q2　[P1] `decision_recommendation` 分析路径无条件抑制 + 单一降级全局封禁
- **锚点**：`src/data_agent/agent/synthesis_policy.py:168`（analytical suppress）、`:295`（`_apply_verification_status` 全局 suppress）、`:104`（exploratory suppress）
- **性质**：`[既有]` `[RELAX]`
- **问题**：默认分析路径把 `decision_recommendation` 放进 `suppressed_moves`，即便数据明显支持也结构性禁止给可执行/决策建议。仅 advisory 路径（关键词命中 "recommend"/"should we"/"forecast"/"predict" 的 `_is_advisory_request:353`）留 `suppressed_moves=[]`。与质量标尺 (3)"LLM 自主决定是否给建议"相悖——把决策变成了结构性而非 LLM 驱动。更糟：`_apply_verification_status:290` 在最新验证状态为 `fail`/`pass_with_downgrades` 时把 `decision_recommendation` **全局**追加进整篇的 `suppressed_moves`——**单个弱/降级 claim 封禁整篇所有建议**。
- **方向**：(a) 从分析路径默认 `suppressed_moves` 移除 `decision_recommendation`，只保留验证状态路径；或 (b) 让 `next_step`（已 required）承载决策级建议。(c) `_apply_verification_status` 把抑制范围收窄到**自身检查失败的 claim**，而非整篇。

### Q3　[P2] `run_python` 永不升为结构化证据 → 其衍生 claim 永不 `verified`
- **锚点**：`src/data_agent/agent/loop.py:2060-2068`（`_fallback_resolution_for_tool_call`）+ `src/data_agent/agent/verification.py:1094-1142`（`_has_current_bound_computation`）
- **性质**：`[设计]` 需决策
- **问题**：成功的 `run_python` 只持久化 traceable `computation_ref`，永不产 `evidence_record.v2`（`provenance_status=="bound"` + 测量身份）。因此任何由 `run_python` 导出的数值/材料 claim 拿不到 `[[evidence:aeNN#amNN]]` 标记，过不了最终答案审计（`missing_evidence_identity`/`measurement_identity_missing`），永远只能是探索性。`run_python` 是文档化的逃生口（"仅当结构化工具无法满足时" `prompts.py:166`），故任何结构化工具表达不了的分析都被封在未验证的严谨上限下。
- **证据**：`measurement_evidence_binding_mode` 默认已 `"soft"`（`config.py:56`），soft/shadow 模式查 `_exact_exploratory_measurement_candidates`，但它要求 `_has_current_bound_computation`（需 v2+bound+plan-digest+step-digest+精确 dataset 版本），对纯 computation ref 是不可达门槛。transparent 模式下非致命（claim 透传，无删除、无脚注），但永不标 `verified`。
- **方向**：(a) 接受封顶+文档化+ nudge LLM 对材料 claim 配 `record_evidence_record`（KEEP）；或 (b) 当步骤计划绑定且输出为数值时，把 `run_python` 的 computation_ref 升为 bound v2 测量（给 run_python 分析一条通往 `verified` 的路）。

### Q4　[P2] transparent 模式不对探索性/未支撑 claim 做内联标注
- **锚点**：`src/data_agent/agent/answer_quality.py:1001-1086`（`_render_transparent_publication`）
- **性质**：`[设计]`（M1 权衡）`[RELAX]`
- **问题**：transparent 模式（生产默认）原样转发草稿（`text=body`,`:1071`），仅当存在实质性矛盾时追加聚合 `## 局限说明` 脚注。每声明动作仅供诊断用、永不内联呈现：被审计降级为 `exploratory` 的 claim **不加** `（探索性，未经独立校验）` 后缀；`unsupported` 的不移除/不标注。若 LLM 写了自信措辞、审计降级为探索性，读者看到的是原样自信措辞。tiered/strict 渲染器（`:1089+`）会内联标注+移除，但非默认。
- **方向**（可选）：transparent 模式对动作为 `exploratory` 的材料 claim 内联追加 `EXPLORATORY_CLAIM_SUFFIX`（常量已在 `answer_quality.py:28`）。非破坏（加标签不删除），在不重新引入删除的前提下补上诚实标注。

### 已确认 KEEP（无需动）
- **脚注范围已收窄**（M1.1）：`_TRANSPARENT_SUBSTANTIVE_FAILURE_CODES`（`answer_quality.py:51-68`）只在材料 claim 命中实质码时出脚注；记账码（`missing_evidence_identity`/`evidence_check_failed`/`*_not_found`/`*_not_bound`/`unmet_block_claim_requirement`/`claim_guard_blocked`）被排除。✓
- **审计修订循环有界不过度弱化**：`loop.py:2702-2737` 单次合成修订，明确要求"完整答案含发现/建议/局限"。✓
- **方法+统计解释强且 7 月后增强**：`method_note` 在 required_moves；样本量规则按方法评估。✓
- **数据为本规则在位**：`synthesis_policy.py:264-270`，旧 `<bounded_evidence_replenishment>` 已删。✓
- **`evaluate_fatal` 不在 live loop**；live 发布恒 transparent。✓
- **2400 字封顶已彻底删除**（全树无匹配）。✓

---

## 4. ③ 结果呈现（Presentation）

### P1　[P1] 内联图表空白 — iframe 高度修复只挂在附录 iframe
- **锚点**：`src/data_agent/web/static/js/app.js:2153-2161`（`_chartArtifactHtml`）vs `src/data_agent/web/templates/index.html:277-280`（唯一 `@load="injectChartPlotly"`）
- **性质**：`[既有]` 潜伏
- **问题**：首选放置（按标准）是在 `[[chart:...]]` 标记处**内联**。Plotly 图表 HTML 用 `<div class="plotly-graph-div" style="height:100%;width:100%;">` 且 bare `<body>`（无高度）——在 iframe 内算出 0px、渲染空白，除非注入 `html,body{height:100%}`。该注入逻辑在 `injectChartPlotly`，但 `@load` **只挂在 `index.html` 的附录 iframe 上**。`_chartArtifactHtml` 发出的内联 iframe 有 `style="height:450px"` 但**无 `@load`** → 无高度注入 → 450px 空白。无全局/委托 load 处理（grep 确认）。
- **证据**：commit `8def818` 只改了 `injectChartPlotly` 函数体，未给内联 iframe 加 `@load`。7 月前内联 iframe 也无 `@load`——长期潜伏 bug，M1 的"修复"未覆盖。测试 `tests/test_web_overhaul.py:118` 只断言类名 `inline-chart-artifact` 存在，抓不到。
- **方向**：给 `_chartArtifactHtml` 的 iframe 加 `@load="injectChartPlotly($event)"`（或 MutationObserver 监听 `.inline-chart-artifact iframe`）。一行接线，注入逻辑本身已正确。**一旦 F1-F3 让图真生成，这决定它是内联还是只能落附录。**

### P2　[P0] 分析答案不流式 — 审计门后才一次性吐
- **锚点**：`src/data_agent/agent/loop.py:2659-2660`（`_should_buffer_final_answer_text`）、`4385-4397`/`4473-4485`（缓冲+单次发）；消费端 `src/data_agent/web/static/js/app.js:2607-2616`
- **性质**：`[回归]`（与 ④ FE1 同源）
- **问题**：对每个分析意图（`directed_analysis`/`comprehensive_report`/`result_followup`——即主用例），`_is_final_answer_audit_candidate()` 为真 → `buffer_text_events` 缓冲**全部** `text_delta`。整篇审计后答案作为单个 `yield {"type":"text_delta","text":final_text}` 发出。用户实时看到 `analysis_progress` 标签和工具活动，但**合成+审计期间零答案文本**，然后整篇多段答案一次性弹出（且当帧重解析 markdown+重渲所有图）。
- **证据**：实时进度 feed 确实存在（`chat.py:88-98` 转发 `analysis_progress`；loop 发 `analysis_plan_ready`/`tool_started`/`completion_evaluated`/`audit_started`）。但答案文本被门缓冲。这是有意的 assurance 权衡。
- **方向**：(a) 草稿边到边流，审计后只重渲差异（难，因审计可重写正文）；或 (b) 保留 blob 但让"audit_started→答案"这段沉默可见（如确定式"整合可支持结论中…"标签），免得被误判为卡死。

### P3　[P2] 产出物加载失败回退文本乱码 + `</p>` 损坏
- **锚点**：`src/data_agent/web/templates/index.html:282-283`
- **性质**：`[既有]`（commit `a33189d`，7 月前）
- **问题**：fallback 含不可读乱码与损坏闭合标签。本应是"加载产出物失败。"/"在新标签页打开"，存为 `鍔犺浇浜у嚭鐗╁け璐ャ€?/p>` 和 `鍦ㄦ柊鏍囩椤垫墦寮€`。
- **方向**：重写为正确 UTF-8，恢复 `</p>`。

### P4　[P3] 金字塔结构纯靠提示，无渲染层保障
- **锚点**：`src/data_agent/agent/prompts.py:175,184-189`；渲染器 `src/data_agent/agent/answer_quality.py:1089-1307`
- **性质**：`[既有]`
- **问题**：金字塔原理是一条提示 bullet + 每结论 5 段模板；无确定性渲染器重排/检查/鼓励结论优先。合成指令的 `required_moves` 是软逗号列表，从不对产出文本校验。golden baseline（`artifacts/golden-quality/baseline/game_b_retention_depth.txt`）展示了预期富格式，但无任何东西保证线上答案匹配。
- **方向**：可接受为软标准。若要硬化：加廉价结构检查（如首非标题行须是结论而非表/方法）+ 提示侧 nudge，**不做发布门**。

### P5　[P3] artifact 注册表无去重、无损坏 manifest 容错
- **锚点**：`src/data_agent/session/history.py:532-560`
- **性质**：`[既有]`
- **问题**：`register_artifact` 恒 append——重跑图产重复 manifest 条目（客户端仅按 `path` 去重，manifest 膨胀）。`list_artifacts` 直接 `json.loads(...)` 无 try/except，截断/损坏的 `artifacts.json` 会冒泡打断 `/api/artifacts/<session_id>`。注意：live 回合图表浮现路径**不依赖** manifest（客户端从 `tool_result.web.artifacts` 取），故影响限于 modal 和 reload。
- **方向**：`register_artifact` 按 `path` 去重；`list_artifacts` 读取包 try/except 失败返回 `[]`。

---

## 5. ④ 前端交互（Frontend）

### FE1　[P0] 答案不流式（同 P2）
- 服务端把分析答案缓冲到审计后才吐。SSE 管道本身没问题（`fetch('/api/chat')`+ReadableStream `app.js:2484` 正确解析帧；`EventQueue` `event_bus.py` 后台线程→SSE）。回归在管道**之上**：分析回合内容被有意不发。

### FE2　[P1] 服务端进度标签被客户端循环动画覆盖
- **锚点**：`app.js:1005-1013`（timer）vs `2591-2606`（`analysis_progress` handler）；渲染 `templates/index.html:258-264`
- **性质**：`[回归]`
- **问题**：7 月加的 `analysis_progress` SSE 事件（服务端标签如"整理可支持的结论"）是对丢失文本流式的部分缓解——但该标签约 2s 内被客户端循环 timer（轮换"思考中…/分析数据…/生成洞察…"）覆盖。
- **证据**：`analysis_progress` handler 设 `turn.thinkingText=data.label`（`app.js:2603`）但不停循环。`llm_call_start`（`app.js:2582`→`_startThinkingCycle`）启动的 timer 持续覆盖同字段：
  ```js
  this._thinkingTimer = setInterval(() => {
      this._thinkingStateIndex = (this._thinkingStateIndex + 1) % this._thinkingStates.length;
      turn.thinkingText = this._thinkingStates[this._thinkingStateIndex]; // 覆盖 data.label
  }, 2000);
  ```
- **方向**：收到 `analysis_progress` 标签时停/抑制循环 timer，把 `thinkingText` 钉在服务端标签，直到下一个 `tool_call`/`text_delta`；或把 `turn.analysisProgress.label` 渲染到专属元素（见 FE3）而非共用 `thinkingText`。

### FE3　[P1] 工具步骤与 analysisProgress 在 JS 里跟踪但从不渲染
- **锚点**：`app.js:2617-2648`（tool_call/tool_result push 到 `state.activeSteps`）、`2597-2602`（设 `turn.analysisProgress`）；模板 `index.html` grep：`activeSteps`=0、`analysisProgress`=0
- **性质**：`[既有]`
- **问题**：进度数据被计算并 push 到 state，但模板从不读取 → 对话里无内联每工具/每步进度，只有（被覆盖的）单行 thinking。
- **方向**：在助手回合下渲染内联步骤列表（`activeSteps` 数组已维护）：工具名→running/done+耗时；把 `analysisProgress.label` 渲染为钉住的状态 chip。

### FE4　[P1] 任务列表面板自动展开 + 折叠后弹回，挤开内容
- **锚点**：`app.js:1604-1608`（`loadTasks`）、`templates/index.html:183-219`
- **性质**：`[既有]`（7 月前行为相同，但与报告症状一致）
- **问题**："任务"栏在 `#messages-container` 之上的正常文档流里。任一任务 `in_progress` 时，每次 `loadTasks()` 强制 `tasksExpanded=true`。由于 `loadTasks` 在 5s 轮询**且**每个 `analysis_progress`/`tool_result`/`task_update`/`turn_end` 事件都重跑（经 `_debouncedLoadTasks` 300ms），用户折叠后零点几秒弹回，把对话往下挤。
  ```js
  if (this.activeTasks.some(t => t.status === 'in_progress')) {
      this.tasksExpanded = true;                 // 覆盖用户折叠
  } else if (this.activeTasks.length > 0 && this.activeTasks.every(t => t.status === 'completed')) {
      setTimeout(() => { this.tasksExpanded = false; }, 3000);
  }
  ```
- **方向**：默认折叠；轮询/事件永不自动展开，只更新计数徽标+摘要。执行中若要详情，把进行中任务渲染为 **overlay/popover**（绝对定位）而非文档流块。自动展开需用户显式开"跟随执行"开关。

### FE5　[P2] Stop 按钮可用但每次都需确认框
- **锚点**：`app.js:1996-2018`（`interruptTurn`）、`templates/index.html:474-477`
- **性质**：`[既有]`
- **问题**：send 按钮在 `isLoading` 时正确切红为 stop（`index.html:474` `x-show="isLoading || hasActiveConfirmation"`），服务端协作中断可用（`chat.py:243-255`→`loop.request_interrupt()` `loop.py:887`，`loop.py:4091,4514` 轮询）。但每次 stop 都需确认 modal（"停止当前对话？此操作无法撤销。"，`app.js:1998`）。常规"停止生成"多了往返摩擦，与 ChatGPT/Claude 一键停止不一致。
- **方向**：纯生成中 stop 去掉确认（可逆——重发即可）。确认只留真正破坏性动作。另：`hasActiveConfirmation`（回合**挂起**而非运行）时红钮语义模糊，考虑单独"取消提问"入口。

### FE6　[P2] 工作台/分析状态在 xl 断点以下不可达
- **锚点**：`templates/index.html:505` `<aside class="hidden xl:flex ... workbench-panel ...">`
- **性质**：`[既有]`
- **问题**：整个"分析工作台"侧栏（结论/行动板、证据、产出、导出 `index.html:504-590`）`hidden xl:flex`，平板/手机（≤1280px）无任何 UI 路径到达分析状态/结论/证据。无抽屉/兜底。
- **方向**：加移动入口——如头部按钮在 xl 以下把工作台作为 slide-over 抽屉打开。

### FE7　[P3] 生成中 composer 锁定，无法边等边起草
- **锚点**：`templates/index.html:466`（`:disabled="isLoading || hasActiveConfirmation"`）、`app.js:1697`
- **性质**：`[既有]`
- **问题**：响应生成时 composer 全 disabled，用户在（因 P2 而）漫长的等待中无法起草下一问。
- **方向**：加载中保持 textarea 可编辑（只拦提交）；ChatGPT/Claude 允许提前输入，发送排队到当前回合结束。

### FE8　[P3] `renderMarkdown` 每 token 重解析整篇 → O(n²) 卡顿
- **锚点**：`templates/index.html:267`（`x-html="renderMarkdown(turn.content, turn)"`）、`app.js:2184-2199`
- **性质**：`[既有]`
- **问题**：每个 `text_delta` 改 `turn.content` 并对**整篇**累计文本重跑 `renderMarkdown`（marked.parse+KaTeX 提取+Plotly JSON 提取+正则）再替换 innerHTML。长答案 O(n²)、明显卡顿/主线程阻塞。
- **方向**：流式活跃期渲染纯文本（或廉价部分解析），完整 markdown/KaTeX/Plotly 渲染推迟到 `turn_end`（`app.js:2771-2800` 的 observer 已在 `isLoading` 时跳过 mermaid/plotly）。

### FE9　[P3] `_yieldAfterVisibleSSEMutation` 限制 token 吞吐
- **锚点**：`app.js:2477-2482,2526-2528`
- **性质**：`[既有]`
- **问题**：每个 `analysis_progress`/`text_delta` 帧后 reader await `setTimeout(0)` 宏任务。一个 TCP chunk 内多帧时，逐 token 序列化让出，封顶吞吐，使（P2 后的）答案 dump 也呈可见阶梯。
- **方向**：批处理——每读 chunk 让出一次（或在 requestAnimationFrame 边界），而非每 token。

---

## 6. 跨层故事（拆开修无效，须成组）

### 故事一：图表端到端
- ① 流程层（F1 预算 + F2 合成提示 + F3 完成度）让 `create_chart` **被真正调用**。
- ③ 呈现层（P1 内联 iframe `@load`）让内联图**不空白**。
- 附录图路径在图生成后即工作（P1 只影响内联）。

### 故事二：实时流
- ③ 呈现层（P2 服务端取消分析答案缓冲，边草拟边流）。
- ④ 前端（FE2 不覆盖标签 + FE3 真渲染进度 + FE8/FE9 渲染性能）。
- 管道本身未坏；问题在管道之上。

### 故事三：确认门禁
- ① 流程层（F4 高风险分析 + F5 类型转换）自动放行，符合锁定标准。

---

## 7. 建议修复批次（按优先级 流程→质量→呈现→前端，含跨层依赖）

每批 TDD + 实测验证，分支 per fix，逐个合 main。

- **批次 A（流程·图表执行）**：F1 + F2 + F3 —— 让 `visual.chart` 成为不被探索预算饿死、不被合成提示禁调、且完成度可检测的一等执行义务。
- **批次 B（流程·门禁）**：F4 + F5 —— 按"会话内 copy-on-write 自动放行"放开高风险分析与类型转换（靠诚实标注兜底）。
- **批次 C（质量放松）**：Q1（加 `deep` 档，报告意图选用）+ Q2（分析路径放开 `decision_recommendation`，把"单一降级全局封禁"收窄到具体 claim）。Q4 内联标注可选。
- **批次 D（呈现·图表内联）**：P1 内联 iframe 补 `@load`（+ 顺手 P3 乱码、P5 manifest 容错）。
- **批次 E（呈现+前端·流式）**：P2 服务端取消分析答案缓冲、边草拟边流 + FE2/FE3 真渲染进度 + FE8/FE9 渲染性能。FE4 任务列表默认折叠+overlay、FE5 去确认框顺带做。

---

## 8. 待决策点（需用户拍板）

1. **F4 高风险分析自动放行**：锁定标准（m2d 记忆）明确把 causal/forecast/experiment/classification 列为"计算、自动放行"。但更早记忆曾留"部分高风险确认可能值得保留——需用户输入"。**建议按 m2d 放开，靠每声明诚实标注兜底。** 确认？

2. **Q3 run_python 严谨上限**：(a) 接受封顶+文档化+nudge LLM 对材料 claim 配 `record_evidence_record`；或 (b) 给 run_python 一条升为 bound v2 证据的路径（让结构化工具表达不了的分析也能 `verified`）。**建议先 (a)，(b) 列为后续。**

3. **范围**：清单中不少是 `[既有]` 老 bug（FE4 任务列表、P1 内联空白、P3 乱码、P5 manifest）。指令是"7 月大改复查"，但目标是好的终态、且它们正是报告的症状。**建议把直接影响"图表/流式/任务列表"体验的既有 bug 一并修**（FE4、P1、P3、P5），其余纯打磨（FE6/7/8/9、P4）按需。同意？

---

## 附：评审可独立验证的方法

- 边界 commit：`04ef1c6`（2026-07-18）。比对 7 月前行为：`git show 04ef1c6:<path>`；查文件史：`git log --oneline -- <path>`。
- 当前基线：`main @ e45c1e8`。
- 实测样例：Web GUI 端口 5001（`python -m data_agent.web.entry`），用 `最强砖块记录.xlsx` + 提示"哪些因素是人均确认的显著影响因素"验证流式/图表/任务列表。
- 离线测试：`uv run pytest tests/ -q`；分析发布契约：`uv run python scripts/run_analysis_release_gates.py --profile deterministic`。
