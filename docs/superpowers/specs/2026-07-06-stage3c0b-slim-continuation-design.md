# Stage 3C0B Slim Continuation Design

Date: 2026-07-06

## 1. 目的与范围

本设计定义 Stage 3C0B 的瘦身续作方向：**在不引入任何新执行期硬契约或硬门的前提下**，闭合多文件分析的 user-value 回路——用户加载多文件后，能看到①结构化数据理解 ②关系价值与风险 ③建议分析方向 ④结论覆盖，并用真实数据回归门证明单文件分析质量不下滑。

本设计**取代** `docs/superpowers/plans/2026-07-06-stage3c0b-realigned-continuation-plan.md`（以下简称"原 realigned plan"）的设计前提。后续 implementation plan 将基于本设计重写，并替换原 realigned plan 文件。

本设计遵循 `2026-06-29-multifile-analysis-stage-3c0b-design-delta.md`（以下简称"delta"）的边界：Stage 3C0B 只执行 `independent` 与 `synthesis` 两种模式。

## 2. 为什么瘦身（原 realigned plan 的问题）

原 realigned plan 及其引用的 `2026-07-01-multifile-data-understanding-and-analysis-opportunity-design.md` 试图把当前单 LLM 端到端 loop 改造成一条确定性 BI 管道。经评审判定存在以下问题：

**分析质量下滑的 4 个具体机制：**

1. **4 角色硬切分**（Interpreter/Planner/Executor/Synthesizer 各看不同上下文）：当前 `loop.py` 的 `_loop_impl` 是单 LLM 单 plan-act loop，跨阶段推理（执行时发现规划假设错误可立即调整）是其核心优势。硬切分会在每次角色切换时丢失上下文。
2. **synthesis 禁读原始数据且无补证据回路**：`execution_scope.py` 已对 `combination_mode=="synthesis"` 返回 `synthesis_cannot_read_raw_dataset`（L274-278、L335-339、L483-507、L555-593 等）——这本身是 delta 既有的正确安全约束，不是过度设计。真正的质量风险是"硬禁且没有 bounded evidence replenishment 回路"：LLM 缺证据时既不能读 raw、又无补证据途径，只能强凑结论。本设计 §5.4 的补证据回路是其配套（不是替代该约束）。
3. **魔法权重排序公式** `score = goal_match*0.30 + business_value*0.25 + feasibility*0.20 + relationship_confidence*0.15 + evidence_strength*0.10 − risk_penalty`：五个无经验依据的手调系数，会默默塑造每一次机会排序且无法调参。
4. **sufficiency 门用预注册 question_id 覆盖**：对探索性洞察有敌意——LLM 发现未预注册的有价值结论时，gate 仍报 `needs_more_analysis`。

**过度设计：**

- `AnalysisOpportunity` / `StrategyRecord` 重复已有能力：`route_capabilities.py`（554 行，可执行/探索性路线卡片 + confirmation gate）与 `multi_file_scope.py`（826 行，文件资质/决策/歧义分组）已覆盖"建议方向"。
- DAG 拓扑执行器 + 重规划状态机（`ReplanDecision` + `replace_active_plan` + `supersede_plan_exact` + 7 种 reason code）属投机性基础设施：当前 `blocks`/`blockedBy` 元数据 + LLM 多轮对话已能处理任务依赖与中途修正，且 delta 明确"Stage 3C0B does not introduce cross-task concurrency"。

**范围越界：**

- delta 第 61-64 行明确：`joint` / `aggregate_then_join` / DerivedDataset 创建**out of scope**（属 Stage 3C1A）。原 plan Task 1A 要做这些，并用"规划层可做、执行层属 3C1A"辩解，留下断层——joint task 投影后无法真正执行。

## 3. 设计原则

1. **复用优先**：已实现的确定性层（bundle / 关系验证 / evidence / verification / route_capabilities / multi_file_scope / synthesis_policy / execution_scope）不重写，只接线。
2. **LLM 主导**：机会排序、策略、重规划、充分性判断交给 LLM 对话轮次 + 现有轻量 guard，不建状态机或硬门。
3. **不引入新执行期硬契约或硬门**：新增工作限于接线、UI 重构、回归门、prompt 编排。`workbench_view.py`（读模型）与 `analysis_quality_rubric.py`（评估结构）是只读投影/评估，不约束执行期行为，不计为硬契约。不新增 AnalysisOpportunity / StrategyRecord / DataOperationRecord / 硬 sufficiency 评分等执行期硬契约。
4. **与 delta 边界对齐**：只执行 `independent` / `synthesis`；`joint` / `aggregate_then_join` / DerivedDataset 留给 3C1A。
5. **多文件价值的来源（核心锚点）**：Stage 3C0B 的多文件价值**不是 join**，而是 scope selection + relationship understanding + independent evidence + synthesis。关系验证的价值通过 Workbench"关系"象限展示，不需要 `joint` plan 模式。
6. **synthesis 与证据（核心锚点）**：synthesis 不直接读原始数据（`execution_scope` 既有约束），但**必须能在缺证据时触发 bounded evidence task 补证据**（§5.4），而不是强行总结。

## 4. 复用清单（已实现，不重写）

| 能力 | 现有实现 | 替代了原 plan 的什么 |
|---|---|---|
| 数据理解 | `agent/data_understanding.py`（449 行） | DataUnderstandingBundle（已实现） |
| 关系验证 | `agent/relationship_validation.py`（630 行） | RelationshipValidation（已实现） |
| 计划契约 | `agent/analysis_plan_contracts.py`（`SUPPORTED_MODES = {independent, synthesis}`） | 已实现，不扩 joint/aggregate |
| 证据与兼容 | `agent/evidence_contracts.py` / `evidence_compatibility.py` / `verification.py` | 已实现 |
| 中央数据边界 | `agent/execution_scope.py`（712 行） | 已实现 |
| 建议方向 / 路线卡片 / confirmation gate | `agent/route_capabilities.py` + `agent/multi_file_scope.py` | **取消新建 AnalysisOpportunity / StrategyRecord** |
| Workbench 视图基础 | `agent/trust_view.py`（718 行） | 在此基础上重构四象限 |
| 综合阶段 prompt 注入 | `agent/synthesis_policy.py` | **取消 4 角色切分** |
| 轻量质量 guard | `loop.py` `_is_analysis_quality_guard_candidate` | **取消硬 sufficiency 门** |
| 计划投影 | `agent/workflow_projection.py` | 复用，投影 independent/synthesis step |

## 5. 新增工作（4 块，0 新执行期硬契约/硬门）

### 5.1 load-time bundle + User Data Brief 接线

**改动：** `tools/data_io.py` 的 `load_data` 成功路径。

**行为：**
- 加载数据后刷新或创建 `DataUnderstandingBundle`，经现有 `AnalysisSessionState.add_data_understanding_bundle_ref()` 写入 `data_understanding_bundles`（注意：不是 `dataset_bundles`——后者是不同语义的旧字段）。
- 派生面向用户的 **User Data Brief**：文件含义、时间范围、粒度、总体可用性、可能关系及可信度、可答与不可答问题、主要质量风险、推荐分析路径、需补充或确认的信息。
- User Data Brief **不暴露**原始行、内部 artifact ID（作为主内容）、工具日志或大段字段类型；样例值敏感时脱敏。
- LLM 规划上下文增补：加载多文件后注入 bundle 摘要 + route_capabilities 方向卡片，由 LLM 据此规划（替代独立的 planner 角色）。

**复用：** `data_understanding.build_data_understanding_bundle`（已实现）、`route_capabilities`、`multi_file_scope`。User Data Brief 的派生函数若 `data_understanding.py` 尚未提供，在 5.1 内补一个面向用户的只读展示派生函数（bundle 的投影，非新契约）。

**不引入：** 新执行期硬契约。bundle 已是 `data_understanding.v1`。

### 5.2 Workbench 四象限重构（替换主视图）

**改动：** 新建 `agent/workbench_view.py`（读模型）；修改 `agent/trust_view.py`（接入）；修改 `web/templates/index.html`、`web/static/js/app.js`、`web/static/css/app.css`。

**行为：** Workbench 围绕四类用户问题组织，作为主视图**替换**现有 trust inspector 主视图（delta 已定调"不堆叠技术状态"）：
1. **数据理解**：业务对象、时间、粒度、指标、维度、质量、可回答问题。
2. **文件关系**：关系依据、字段、基数、覆盖率、验证状态、价值、风险。
3. **建议分析方向**：价值、数据、策略、预期证据、置信度、风险、是否已进入计划（来自 route_capabilities）。
4. **结论覆盖**：已回答、分析中、数据不足、存在限制、下一步。

每条建议可追溯到 route_capabilities / 关系验证 / EvidenceRecord，或显式标注为"下一步数据/行动建议"。技术细节（task ID、工具日志、artifact 计数、scheduler 状态）降级为下钻。

**失败翻译为用户语义：** `task_failed` → "尚无法从现有证据判断优惠券影响"；`measurement_incompatible` → "统计口径不同，不应直接比较"；`missing_required_evidence` → "该结论需要来自数据集 X 的证据，但未成功产出"。

**约束：** 不创建与 chat 冲突的第二路由选择界面（delta）。

### 5.3 真实数据回归门 + 质量 rubric

**改动：** 新建 `agent/analysis_quality_rubric.py`；新建 `tests/real_data/test_multifile_real_data_scenarios.py`、`tests/real_data/test_multifile_analysis_quality.py`、`tests/real_data/scenario_manifest.json`、`scripts/run_multifile_quality_scenarios.py`。

**真实数据场景（`reference/test_doc`）：**
- 游戏 A banner / 内购 / 激励视频：独立分析、指标兼容、证据综合。
- 省钱卡用户流水 + 订单：候选键、基数、覆盖率、时间/粒度兼容验证；**不执行 join**；输出关系价值、风险、是否建议进入 3C1A。
- 无可靠关系的文件组合：避免因同名字段或偶然重叠错误 join。
- 故障注入：重复键、缺失键、时间错位、M:N 膨胀触发降级或 partial 答案。

**质量 rubric 维度：** 用户问题覆盖率、证据引用率、指标口径完整性、不支持结论数、关系验证正确性、单文件分析质量回归、洞察深度与专业 usefulness、可行动性、Workbench 决策价值。

**评估硬度（用户决策，两层）：**
- **不阻塞开发合并**：rubric 记录 before/after 对比与评分，软性的合理 hedged 结论不被误杀。
- **阻塞"宣称可交付/验证通过"**：`unsupported_claim` / `invalid_join` 一旦出现，该批次不得宣称可交付，必须先修正或降级为 partial 答案 + 缺数据说明——避免对用户输出不可信结论。

### 5.4 综合前证据补齐回路（bounded evidence replenishment）

**目标：** synthesis 不读原始数据是 `execution_scope` 既有的正确安全约束（见 §2 第 2 条）。本回路**不替代该约束**，而是补上它缺失的配套——让 LLM 在缺证据时发起有界 `independent` task 采集规范化 evidence 再综合。这样既保留"evidence 是综合唯一合法输入"的安全属性，又给 LLM"回读数据补证据"的有界能力；同时取代原 plan 的"硬 sufficiency 门"极端。

**机制：**
- **触发主体**：LLM 主导。综合前由 `synthesis_policy.py` 注入的 prompt 指令让 LLM 自检"当前结论是否有规范化 EvidenceRecord 支撑"。**不是确定性 gate**，无 question_id 覆盖检查、无魔法阈值。
- **动作**：当 LLM 发现某结论缺规范化证据（或想验证某模式/数字），它**不直接读原始数据**，而是发起一个 **bounded `independent` step**：绑定相关数据集，走现有 `workflow_projection` 投影为 task，受 `execution_scope` 约束，产出规范化 `EvidenceRecord`（经 `record_evidence_record`），再回到综合。
- **有界（bounded）含义：**
  - 受 delta 硬上限约束：`MAX_EXECUTABLE_STEPS_PER_BATCH = 12`。
  - 补完仍不足 → 走 `blocked_by_missing_data` 语义：返回 **partial 答案 + 明确缺数据说明**（不强凑结论），而非无限补。
  - 单个补证据 task 失败只影响依赖该证据的 claim，不阻塞无关结论（delta 失败隔离原则）。
- **synthesis 本身仍不直接读原始数据**：evidence 仍是综合的唯一合法输入，安全/可追溯不丢。

**复用，不引入新执行期硬契约：** `workflow_projection.project_plan_to_workflow_tasks` / `execution_scope` / `evidence_contracts` / `record_evidence_record` / `task_manager.complete_matching_tasks_from_evidence` 全部现成。改动仅在 `synthesis_policy.py` 的 prompt 注入增加"综合前证据自检 + 缺则发起 bounded independent task"指令，以及在 `loop.py` 综合前点允许 LLM 通过现有工具发起该 task。

**这是 delta 里 `needs_more_analysis` 路径的轻量、LLM 主导实现。** 要砍掉的是"基于 question_id 覆盖的硬评分门 + 魔法阈值"，不是这个回路本身。

## 6. 砍掉清单

| 原 plan 内容 | 处置 | 替代 |
|---|---|---|
| 4 角色 prompt 切分（Task 2C） | 砍 | `synthesis_policy` 阶段感知注入 |
| AnalysisOpportunity 契约（Task 2A） | 砍 | `route_capabilities` |
| StrategyRecord 契约（Task 2B） | 砍 | `route_capabilities` + plan step 已有字段 |
| 魔法权重排序公式 | 砍 | LLM 自主排序 |
| DAG 拓扑执行器（Task 2D） | 砍 | `blocks`/`blockedBy` 元数据（现状） |
| 重规划状态机（Task 2E） | 砍 | LLM 对话轮次 + 现有 `_maybe_replan_after_data_load` |
| 硬 sufficiency 评分门（Task 2F） | 砍 | 5.4 bounded evidence replenishment + 现有轻量 guard |

> 注：synthesis 不读原始数据是 `execution_scope` 既有的正确安全约束，**保留不动**（不在砍掉清单）；§5.4 是它缺失的配套回路，不是对该约束的软化。

## 7. 推迟到 Stage 3C1A（单独计划，不得在本续作实现）

- `joint` / `aggregate_then_join` plan 模式
- DerivedDataset lineage
- 可执行 `DataOperationRecord` 生命周期
- 操作审批 / 确定性 resume / 事务性 join / rollback

**消除原 plan 的断层：** 不再做"规划层 joint 但执行层属 3C1A"的中间态。关系价值在 Stage 3C0B 通过 Workbench"关系"象限 + `relationship_validation` 结果展示，不需要 `joint` plan 模式。

## 8. 关键设计决策（已确认）

1. **Workbench 主视图替换**（非叠加）：与 delta"不堆叠技术状态"一致。
2. **回归门两层硬度**：rubric 不阻塞开发合并；但 `unsupported_claim` / `invalid_join` 阻塞"宣称可交付/验证通过"。
3. **综合前证据补齐回路**：synthesis 不直接读原始数据；缺证据时由 LLM 主导发起 bounded `independent` task 补证据再综合；补完仍不足则 partial 答案 + 缺数据说明。
4. **不引入新执行期硬契约或硬门**：核心瘦身约束（`workbench_view` / `quality_rubric` 等读模型/评估结构不计为硬契约）。

## 9. 验收门

- **单文件质量回归**：`tests/test_analysis_quality.py` + `tests/test_system_data_analysis_quality_audit.py` 全绿，单文件洞察深度不低于现状。
- **多文件真实数据**：`reference/test_doc` 场景全过——独立游戏文件分析、省钱卡关系验证、防假 join、故障注入降级。
- **Workbench 可追溯**：四象限每条建议指向 route_capabilities / 关系验证 / EvidenceRecord，或显式标注为下一步建议。
- **证据补齐回路**：演示一个"综合前缺证据 → 发起 bounded independent task → 补 EvidenceRecord → 综合"的端到端用例，且单 task 失败隔离生效。
- **非越界自检**：`rg "AnalysisOpportunity|StrategyRecord|DataOperationRecord|safe_to_execute|join preflight|operation_id"` 在新增 src 中无命中（关系验证、derived lineage 等已实现部分除外）。
- **非越界自检（执行期硬契约）**：新增工作未创建上述被砍契约（AnalysisOpportunity / StrategyRecord / DataOperationRecord / 硬 sufficiency 门）的任何新执行期模块；`workbench_view` / `quality_rubric` 作为读模型/评估结构存在，但不约束执行期行为。

## 10. 非目标

- 不自动连接所有存在共享字段的数据集。
- 不让 LLM 绕过确定性关系验证。
- 不在一个 prompt 中同时完成数据理解、计划、执行和综合。
- 不为旧 Stage 3C0B 部分执行路径保留兼容双轨。
- 不要求用户确认每一个低风险、高置信的分析步骤。
- 不在本续作实现任何 Stage 3C1A 能力（joint 执行 / DataOperationRecord / 事务性 join）。
- 不引入硬性 sufficiency 评分门或魔法权重排序。

## 11. 与现有文档的关系

- **取代** `docs/superpowers/plans/2026-07-06-stage3c0b-realigned-continuation-plan.md` 的设计前提；后续 implementation plan 将替换该文件。
- **遵循** `2026-06-29-multifile-analysis-stage-3c0b-design-delta.md` 的边界与 stop gate。
- **不依赖** `2026-07-01-multifile-data-understanding-and-analysis-opportunity-design.md` 的 4 角色 / AnalysisOpportunity / StrategyRecord / DAG / 重规划 / 硬 sufficiency 等扩张性内容；该 spec 中已被 `data_understanding.py` / `relationship_validation.py` 实现覆盖的部分（bundle、关系验证）继续有效。
- 已实现的 `data_understanding.py` / `relationship_validation.py` / `analysis_plan_contracts.py` / `evidence_contracts.py` / `verification.py` / `execution_scope.py` / `workflow_projection.py` / `route_capabilities.py` / `multi_file_scope.py` / `synthesis_policy.py` / `trust_view.py` 作为本设计的安全底座，不在本续作重写。
