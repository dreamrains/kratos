# 核心能力、证据权威与实际入口分析

日期：2026-09-30；树：`C:/Users/duguy/.codex/worktrees/trust-rebuild/data-agent`；分支：`codex/trust-rebuild-20260927`；HEAD：`71e23d0ac26091365508ae1b50fa7dd88b238591`；供体 `b181646` 只读。

本记录从属[唯一总计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)，支持[产品 PRD](../product/data-agent-product-requirements.md)与[重构设计](../superpowers/specs/2026-09-30-trusted-answer-pipeline-redesign.md)。它是静态与局部运行分析，不能替代当前产品整体验收。工作树原有计划改动、控制复盘和真实批次收据均保留。

## 1. 分析范围与结论

核对 VP/IC/CP 三计划、设计与验收、历史能力账本、工作包 A 调用链、旧门退役记录，以及当前路由、计划/任务、确认、工具、回执、证据、假设、发布、工作台、规范历史、压缩、检索和导出边界。原验收 180 个定义编号已逐项列在[新验收契约](../superpowers/validation/2026-09-30-trusted-answer-pipeline-acceptance.md)。

产品不是只有“上传后生成分析报告”。知识问答、分析咨询、结果追问、数据准备和数据操作均是已设计能力。重构需要保留这些旅程，并改用实际入口与可见结果验收；不能因旧源码有函数便声明能力可达，也不能因六个场景未覆盖就删除其余工具。

## 2. 功能链与承接

| 链 | 实际源码与机制 | 可复用部分 | 缺口与目标责任 |
| --- | --- | --- | --- |
| 意图与咨询 | intent.plan_turn_intent → intent_refinement / analysis_entry → AnalysisFlowController | 九类意图、主目标/子问题、否定、已有结果续问、分层 prompt/budget | tool groups 叠加 core、状态与关键词激活；仅存在 conversation_query 不能证明无执行。CONS 需验证真实工具调用日志 |
| 方法与任务 | method_playbooks → analysis_plan_contracts → workflow_projection → TaskManager | 当前 plan/version、independent/synthesis、blockedBy/blocks、单一 in-progress、task scope | 基线 shape 校验未完整核查依赖引用和环；保持原 TaskManager，补契约边界 |
| 数据输入 | 上传票据 → data_io → Workspace 数据身份 → data contracts | 文件 SHA、会话范围、派生 lineage、原始数据不可变 | 工具存在不等于环境支持所有格式；输入/清洗/连接各有真实结果验收 |
| 工具执行 | ToolRegistry 定义/参数校验/timeout/hooks → ToolResult → 宿主 receipt | 成功/失败、tool_call_id、原输出、数据身份与执行预算 | 按真实注册入口验收，不能只 import 同名函数 |
| 结构证据 | record_evidence_record → evidence_input / contracts → result_reference / evidence_statistics → AnalysisSessionState | 当前执行回执、结果摘要、宿主覆盖统计字段、版本拒绝、测量合同 | 两套入参/旧名称回退需在新协议切换时退役；模型元数据不能补成事实 |
| 验证与工作台 | trust_workflow_runtime → verification → workbench_view | 当前计划过滤、报告 fingerprint、原结果引用、待核与已核类别 | 文本匹配和 confidence 不能授予 checked；投影改读唯一宿主验证结果 |
| 假设 | plan-scoped sets → 原 compare/time_series 回执 → hypotheses | 真实 ID、目标列、数值重算、方向、当前版本；因果/推断强度分开 | 正确结构状态需公开渲染；不从散文或标题反推关系 |
| 业务确认 | question_need / confirmation policy → ConfirmationService → runtime/continuation | 单生命周期、范围/版本、幂等、一次恢复、跳过非授权 | 新会话能力完整保留；旧运行迁移按本次只读历史决定替代 |
| 发布 | prepare packet → terminal builders 或 finalized prose path → 审核/渲染/commit | 宿主封闭事实、局部保留、产物和持久身份保护 | 两终局、逐族早返回、重复 coverage 和散文门整体替换 |
| 历史/压缩 | session.history → compact → preserved identity / obligations | 规范 revision、成对工具事件、尾部详情可恢复、需求变更 | 压缩摘要只提供上下文；新发布引用单一身份 |
| 知识与记忆 | knowledge.evidence.EvidenceStore → retrieval / memory candidates | 按会话/项目查找历史内容、拒绝草案排除 | 消息分类不是事实验证；已接受与待审核草案保持隔离 |
| 公开结果 | public_messages / workbench / Web / tools.report | 同一答案正文、图表、导出、刷新、任务进度 | 去除 latest/旧包猜测和工作台的独立事实批准 |

## 3. 证据系统的具体裁决

1. **回执是来源锚点。** `record_evidence_record` 在正常运行上下文要求成功工具回执，匹配声明工具、结果 SHA 和当前数据身份；统计量由 `evidence_statistics` 从精确结果加载，模型自报统计移为 reported annotations。保留这些保护，不能退回仅信任模型 JSON。
2. **形状与兼容性不等于真实性。** `evidence_contracts` 验证字段和封闭派生算术，`evidence_compatibility` 核对指标/定义/单位/粒度/窗口/总体；若操作数本身来自模型，这些检查仍不能授予事实权威。新 facts 必须先解析真实回执。
3. **旧验证规则仍共存。** `verification._find_evidence` 可在无显式 ID 时按文本相似度关联；`_check_claim` 以关联记录开始构造 passed，并使用 confidence 表示强度。这是源码确认的残留决定权；不据此宣称已复现所有端到端误放。删除前为错值/相同文本错版本/模型 confidence 建立行为负例。
4. **未知身份不能当当前。** `trust_workflow_runtime._split_evidence_by_data_freshness` 对确定不一致做过滤，但缺少身份不能由“不发现过时”推成“已验证当前”。`workbench_view` 的按名称推断旧版本逻辑也需改为真实身份。
5. **测量绑定有可用实现。** `hypotheses` 已对 compare 差分与时间趋势原值、目标指标、inferred_columns、有限值和重复测量做核验；描述方向满足谓词才支持/反驳。因果或推断需要相应证据，用户同意和模型说 supported 均不够。保留并统一公开投影。
6. **Python 和高级工具要分别承接。** `evidence_statistics` 对受限结构值做有界解析；未支持方法产生具体缺口。不能为了通用化把任意 JSON 数字当已核统计，也不能让高级工具成功结果在发布层全部消失。计算工具原结果与验证边界均保留。
7. **检索不是验证。** `knowledge/evidence.py` 索引消息和工具事件，标签含 MESSAGE/TOOL_CALL/ANALYSIS_RESULT/USER_CORRECTION；该标签供检索。已有 publication_rejected 排除应扩展到新草案生命周期，但不能重建第二套事实库。
8. **任务完成不等于回答完成。** TaskManager 的进度与 evidence 完成关系只代表执行；CP 覆盖必须从最终接受内容产生。M04 内部关系正确但正文缺失正是独立反例。

## 4. 静态工具清单

对当前 `src/data_agent/tools/*.py` 的注册装饰器做 AST 核对，不 import 执行工具。基线 77 个装饰器、76 个唯一原生注册名；forecast 有重复装饰器，后一个正式入口覆盖前面的辅助函数注册。动态 MCP/Skills 不包含在这一原生数量中。

下表记录本轮修正后的静态绑定，**不宣称每个工具已当前验收**。同一行多个函数表示重复注册，需单独清理；用户能力应保留到新链。源码行号随修改变化，以工具注册名定位。

| 模块 | 注册名 → 函数 | 处理 |
| --- | --- | --- |
| [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | record_data_requirement → record_data_requirement | 保留用户能力；待相应整链验收 |
| [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | record_analysis_spec → record_analysis_spec | 保留用户能力；待相应整链验收 |
| [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | record_analysis_plan → record_analysis_plan | 保留用户能力；待相应整链验收 |
| [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | record_evidence_record → record_evidence_record | 保留用户能力；待相应整链验收 |
| [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | get_analysis_summary → get_analysis_summary | 保留用户能力；待相应整链验收 |
| [curve_fitting.py](../../src/data_agent/tools/curve_fitting.py) | curve_fitting → curve_fitting | 保留用户能力；待相应整链验收 |
| [data_clean.py](../../src/data_agent/tools/data_clean.py) | suggest_column_types → suggest_column_types | 保留用户能力；待相应整链验收 |
| [data_clean.py](../../src/data_agent/tools/data_clean.py) | apply_type_conversion → apply_type_conversion | 保留用户能力；待相应整链验收 |
| [data_clean.py](../../src/data_agent/tools/data_clean.py) | clean_data → clean_data | 保留用户能力；待相应整链验收 |
| [data_io.py](../../src/data_agent/tools/data_io.py) | load_data → load_data | 保留用户能力；待相应整链验收 |
| [data_io.py](../../src/data_agent/tools/data_io.py) | reload_data → reload_data | 保留用户能力；待相应整链验收 |
| [data_io.py](../../src/data_agent/tools/data_io.py) | load_sql → load_sql | 保留用户能力；待相应整链验收 |
| [data_io.py](../../src/data_agent/tools/data_io.py) | export_data → export_data | 保留用户能力；待相应整链验收 |
| [data_io.py](../../src/data_agent/tools/data_io.py) | export_output → export_output | 保留用户能力；待相应整链验收 |
| [data_io.py](../../src/data_agent/tools/data_io.py) | list_data → list_data | 保留用户能力；待相应整链验收 |
| [data_transform.py](../../src/data_agent/tools/data_transform.py) | transform_data → transform_data | 保留用户能力；待相应整链验收 |
| [data_understand.py](../../src/data_agent/tools/data_understand.py) | describe_dataset → describe_dataset | 保留用户能力；待相应整链验收 |
| [data_understand.py](../../src/data_agent/tools/data_understand.py) | detect_data_quality → detect_data_quality | 保留用户能力；待相应整链验收 |
| [data_understand.py](../../src/data_agent/tools/data_understand.py) | preview_data → preview_data | 保留用户能力；待相应整链验收 |
| [data_understand.py](../../src/data_agent/tools/data_understand.py) | derive_field → derive_field | 保留用户能力；待相应整链验收 |
| [data_understand.py](../../src/data_agent/tools/data_understand.py) | quick_profile → quick_profile | 保留用户能力；待相应整链验收 |
| [data_understand.py](../../src/data_agent/tools/data_understand.py) | assess_readiness → assess_readiness | 保留用户能力；待相应整链验收 |
| [data_understand.py](../../src/data_agent/tools/data_understand.py) | interpret_dataset → interpret_dataset | 保留用户能力；待相应整链验收 |
| [derive_features.py](../../src/data_agent/tools/derive_features.py) | derive_features → derive_features | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | analyze_time_series → analyze_time_series | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | correlation_analysis → correlation_analysis | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | distribution_analysis → distribution_analysis | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | segmentation_analysis → segmentation_analysis | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | cohort_analysis → cohort_analysis | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | compare_periods → compare_periods | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | top_n → top_n | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | contribute_decomposition → contribute_decomposition | 保留用户能力；待相应整链验收 |
| [eda.py](../../src/data_agent/tools/eda.py) | funnel_analysis → funnel_analysis | 保留用户能力；待相应整链验收 |
| [file_ops.py](../../src/data_agent/tools/file_ops.py) | read_file → read_file | 保留用户能力；待相应整链验收 |
| [file_ops.py](../../src/data_agent/tools/file_ops.py) | write_file → write_file | 保留用户能力；待相应整链验收 |
| [file_ops.py](../../src/data_agent/tools/file_ops.py) | edit_file → edit_file | 保留用户能力；待相应整链验收 |
| [file_ops.py](../../src/data_agent/tools/file_ops.py) | list_files → list_files | 保留用户能力；待相应整链验收 |
| [interaction.py](../../src/data_agent/tools/interaction.py) | ask_user_question → ask_user_question | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | show_project_rules → show_project_rules | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | update_project_rules → update_project_rules | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | create_knowledge_item → create_knowledge_item | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | search_knowledge → search_knowledge | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | create_memory_candidate → create_memory_candidate | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | confirm_memory → confirm_memory | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | extract_memory_candidates → extract_memory_candidates | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | list_memory_candidates → list_memory_candidates | 保留用户能力；待相应整链验收 |
| [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | retrieve_knowledge_context → retrieve_knowledge_context | 保留用户能力；待相应整链验收 |
| [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | call_mcp_tool → call_mcp_tool | 保留用户能力；待相应整链验收 |
| [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | list_mcp_servers → list_mcp_servers | 保留用户能力；待相应整链验收 |
| [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | add_mcp_server → add_mcp_server | 保留用户能力；待相应整链验收 |
| [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | enable_mcp_server → enable_mcp_server | 保留用户能力；待相应整链验收 |
| [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | disable_mcp_server → disable_mcp_server | 保留用户能力；待相应整链验收 |
| [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | delete_mcp_server → delete_mcp_server | 保留用户能力；待相应整链验收 |
| [ml.py](../../src/data_agent/tools/ml.py) | forecast → forecast | 当前正式回测入口保留；无调用旧函数/被覆盖装饰器已精确退役 |
| [ml.py](../../src/data_agent/tools/ml.py) | classification → classification | 保留用户能力；待相应整链验收 |
| [ml.py](../../src/data_agent/tools/ml.py) | regression_analysis → regression_analysis | 保留用户能力；待相应整链验收 |
| [ml.py](../../src/data_agent/tools/ml.py) | attribution_analysis → attribution_analysis | 保留用户能力；待相应整链验收 |
| [multifile.py](../../src/data_agent/tools/multifile.py) | synthesize_time_series → synthesize_time_series | 保留用户能力；待相应整链验收 |
| [registry.py](../../src/data_agent/tools/registry.py) | tool_search → tool_search | 注册错位已局部 RED→GREEN 修复 |
| [report.py](../../src/data_agent/tools/report.py) | export_conversation → export_conversation | 保留用户能力；待相应整链验收 |
| [sandbox.py](../../src/data_agent/tools/sandbox.py) | run_python → run_python | 保留用户能力；待相应整链验收 |
| [simulation.py](../../src/data_agent/tools/simulation.py) | what_if_simulation → what_if_simulation | 保留用户能力；待相应整链验收 |
| [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | load_skill → load_skill | 保留用户能力；待相应整链验收 |
| [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | unload_skill → unload_skill | 保留用户能力；待相应整链验收 |
| [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | list_skills → list_skills | 保留用户能力；待相应整链验收 |
| [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | enable_skill → enable_skill | 保留用户能力；待相应整链验收 |
| [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | disable_skill → disable_skill | 保留用户能力；待相应整链验收 |
| [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | delete_skill → delete_skill | 保留用户能力；待相应整链验收 |
| [statistics.py](../../src/data_agent/tools/statistics.py) | ab_test → ab_test | 保留用户能力；待相应整链验收 |
| [statistics.py](../../src/data_agent/tools/statistics.py) | causal_analysis → causal_analysis | 保留用户能力；待相应整链验收 |
| [statistics.py](../../src/data_agent/tools/statistics.py) | shap_analysis → shap_analysis | 保留用户能力；待相应整链验收 |
| [task_tools.py](../../src/data_agent/tools/task_tools.py) | task_create → task_create | 保留用户能力；待相应整链验收 |
| [task_tools.py](../../src/data_agent/tools/task_tools.py) | task_update → task_update | 保留用户能力；待相应整链验收 |
| [task_tools.py](../../src/data_agent/tools/task_tools.py) | task_get → task_get | 保留用户能力；待相应整链验收 |
| [task_tools.py](../../src/data_agent/tools/task_tools.py) | task_list → task_list | 保留用户能力；待相应整链验收 |
| [visualization.py](../../src/data_agent/tools/visualization.py) | create_chart → create_chart | 保留用户能力；待相应整链验收 |

## 5. 首个实际入口缺陷与修复收据

`tool_search` 的装饰器在基线挂在 `_tool_search_haystack(tool)` 上，真实 `tool_search(keyword)` 未注册。已有测试直接调用后者，因此通过；另一个分组测试含 `or True`，不能验收能力。实际 model schema 需要 `tool`，正常 `keyword` 调用被 JSON schema 拒绝。

- RED：`tmp/trust-prd-tool-entry-red-20260930-r1`，4 passed / 2 failed；失败明确为 properties={tool} 及 keyword 调用缺 required tool。
- 修改：将同一装饰器移到真实 `tool_search`；保留一个注册入口，不加别名、兼容、关键词或分支。将无效断言替换为模型可见 schema 与 registry.execute→结果→分组激活的行为。
- GREEN：`tmp/trust-prd-tool-entry-green-20260930-r1`，相关 11 passed，Provider 禁止。此证据仅覆盖注册搜索及相关完整性回归，不能算 E3/E4 或发布重构完成。

## 6. 旧代码收缩与尚需核验

- `publication_synthesis.py`、旧 audit 和 loop 两终局是确定需要替换的 live 代码；不能称全部死代码。原保护通过新行为接管后才删除。
- `ml.py` 中旧 forecast 注册与 `_legacy_forecast` 属历史路径；当前公开 forecast 已走 backtesting。只凭重复装饰器不能报预测产品失效，也不能把旧代码删除算成发布重构完成。需核对引用和新预测行为后独立退役。
- 当前分析计划合同已有数量、模式、输入、目标与证据要求校验；缺少完整依赖校验会使引用丢失或循环计划看似 executable。本轮已补在原 validator，不增加第二规划系统。
- 咨询是否严格禁止执行、所有高级方法的事实适配、旧会话所有 continuation 入口、UI/导出身份均需新行为收据；源码清单只确定责任边界。
- 历史自然批次摘要保留；开始重放前必须实际定位原 ledger、session、candidate 与结果文件并核摘要。摘要本身不能作为原始重放输入。

本次采用“要求→真实入口→行为结果→证据”追溯，不再用函数存在、私有测试绿或内部状态代替产品完成。

## 7. 计划依赖约束实施收据

新行为要求来自 PROD-T02 / SCOPE-DAG。基线会把缺失引用、自依赖和环标为 executable，且会将非列表/空 ID 依赖静默移除。注册工具入口可把这类计划写入产物和任务系统。

- RED：`tmp/trust-prd-plan-dag-red-20260930-r1`，9 passed / 7 failed，包含真实 registry.execute 入口写入前的拒绝要求。
- 修复：在既有 `validate_analysis_plan_contract` 中检查引用结构、当前计划内存在性及无环性；允许步骤列表的前向引用和合法独立分支汇合。校验不重排计划，不改变 TaskManager 执行，不另建 DAG runtime。
- GREEN：`tmp/trust-prd-plan-dag-green-20260930-r1`，计划合同、投影、执行范围、任务版本与隔离共 83 passed。完整离线回归 `tmp/trust-prd-full-offline-20260930-r1` 完成：**2991 passed / 1 skipped / 16 warnings，197.22 秒，Provider initiated 0**。JUnit 记录 tests=2992、failures=0、errors=0、skipped=1；SHA-256 `4942099092eb386278d4a7d65538039e4b1f666502e83617a983d716ea70d43d`。16 项警告涉及已有退化统计样本和 JUnit record_property 配置，不把它们报成已修复。
- 文档检查：5 份新增文档本地链接无缺失，10 个 Mermaid 图块及所有代码围栏配对，180 个原编号完整。未把静态 Markdown 检查报告为浏览器视觉验收。
- 原始自然批次材料：本轮用具有访问权限的 Python 检查重建树与供体树下所记录的 `tmp/trust-rebuild-p08-real-71e23d0-r1`，两处目录均不存在。当前只能核读已保留摘要；尚未执行自然原收据重放。没有删除或重建这些历史目录，后续应定位原归档位置后核 SHA。此项不阻断其余本地合同开发。

## 8. PRD/入口核查当时的交接（后续状态见唯一计划）

已完成：5 份新文档与唯一计划更新；10 个流程/DAG/时序/状态图；180 原验收编号映射；76 原生工具静态登记；tool_search 注册修复；原计划依赖校验；完整离线通过。没有新增 Provider 调用、运行服务、部署、外部 Git、提交或暂存；原 dirty/untracked 保留。

未完成：answer_bindings.v2 及统一 publication service、事实验证/工作台/导出统一权威、旧会话只读入口和旧发布模块退役；对应 E3、视觉与自然 E4；历史原始收据定位及重放。当前 HEAD 仍为 71e23d0，修改在工作树；不可拿此旧提交身份发起新 Provider 批次。

继续时先读唯一计划第 0 节及 PRD，核 HEAD/dirty/环境。以新预期行为驱动 P2/P3，不回到按 M01/M04/M05/M06 增加 builder 的旧工作方式。


## 9. 新发布核心后续来源核查

后续 P2 已建立未接入的 publication 核心，[实施收据](2026-09-30-trusted-publication-contract-implementation.md)记录合同、实际回执文件、一次局部审核与最终需求投影。复用现有 result_reference 时发现受限 workspace 下的当前身份误拒，已用现有只返回相等性的 `_receipt_identity_matches` 修正；没有开放原数据或另造验证权威。新 fixture 隔离现有 TaskManager，scope 行为仍单独正反验证。

模块承接、代码增长/删除门与原始自然材料缺失均按唯一计划继续；本页能力清单不将 P2 核心 pass 改为九类自然意图/全部工具族 pass。


## 10. 当前源码入口复核（2026-10-02）

第6/8/9节是核查当时状态。当前app/scripts已使用唯一publication.v2，未import旧synthesis/audit；旧两源码尚在且仍被部分旧测试调用，不算完成退役。rehearsal终稿已迁v2、分支按用户选择仅继承聊天并局部验收，咨询控制保留原方案待办与必要提问，不能因纯咨询禁算而丢失原能力。

本轮原生23族实际调用验收发现preview结构结果、profile列、训练/测试/CV字段以及SHAP的错误AND前置要求；沿原入口与同一适配表修正，联合122通过。SHAP由其现有模型/目标/当前数据身份校验决定可用，不靠“曾执行两个训练工具”授权。证据见同一切换收据7.6；全模式/自然语义、完整180 oracle和P4 app矩阵仍待核。


截至本轮7.11，原比较/行动/审核旧门目标已用实际原工具、一次定位审核及持久接受对象逐项承接；旧依赖仅两个测试文件，清单current-legacy-imports-20261002-r3.json。比较重复交付和相邻同purpose覆盖错误各有实际RED/GREEN，见切换收据7.10/7.11。旧核心未删除、净行数+567仍未收缩；测试依赖减少不等于全部能力/180 oracle完成。


截至切换记录7.13，原聚合14函数全部脱离旧import，综合92函数中本轮7项原精度/范围/Python行为承接；原106函数名全部保留。旧依赖仅综合测试文件，静态清单current-legacy-imports-20261002-r4.json。两旧核心仍原SHA，R5合并净+597，不因测试迁移减少而称源码已收缩。原聚合源粒度/类型化日期、比较combined以及不相关facts挤占局部审核预算各有实际RED与358项联合GREEN；固定审核不证明自然质量，完整180oracle与P4仍待核。


综合文件AST原函数闭包仍70项/6本地helper依赖旧核心；remaining-synthesis-function-map-20261002-r1.json不是验收通过。完整r12暴露三旧断言遗漏本轮新增合并范围/精确审核引用，原业务字段/公式/错误散文及公开facts保留，联合56通过；新r13冻结重新完整复验，不倒填r12。详见切换收据7.14。


当前7.15原聚合正文派生表名/行数已承接，新增三行原适配循环标签/计数单位，不另加事实族；157联合通过。新包1600、R5合并净+600，line-accounting-20261002-r6.json。r13完整3269通过冻结已核，后改标签的当前r14正在新冻结上完整复验；70旧函数及两旧核心删除边界未变。


最新7.16：r14完整3265通过/4失败来自同一单位断言，原确认/金额/映射/旧源/伪CNY保护保持；仅测试精确区分实际记录单位后167联合通过。当前r15重新完整复验，产品源码相对r14不变，R5+600、70旧测试依赖与两旧核心边界不变。


最新7.17：完整r15为3269 passed /2 skipped /16 warnings，371冻结摘要无变化；结束后无源码/测试改动。70原函数/6helper及两旧核心未退役，R5+600不变，180oracle/P4/P5仍未完成。r12/r14失败保留；绿色不作为完整能力签收。


## 10. 当前P1/P3本地出口核对（2026-10-02）

以上第2—6节是原审查身份，不能把旧发布入口、文本验证残留或forecast重复注册当现行路径。当前唯一发布为runtime→HostSnapshot/native→PublicationService→accepted answer/CAS commit；sync/stream、工作台、指定答案导出与规范历史读同一权威。旧synthesis/audit已按精确授权删除，旧import0；verification无散文猜测授予事实批准。原证据来源/假设测量/确认/知识检索能力保留，模型reported annotation仍不能改宿主claim。

现行AST inventory为76装饰器/76唯一原生工具名；forecast只绑定正式forecast，后者及其他ML函数AST不变，现行有序留出/实际预测已局部核。删除仅无外部引用的_legacy_forecast与被覆盖装饰器168行；没有删除用户预测/分类/回归/归因能力。原77装饰器清单仍为历史基线，机器清单 `tmp/p123-retirement-review-r1/current-native-tool-bindings-20261002.json` 记录当前身份。

原综合92函数（含类方法）与全部parametrize装饰器保留，70最后旧依赖迁入真实工具/当前单链；原开放N文本只验编排，不签收自然语义。P1完成入口/责任与原功能承接分析，所有模式整链行为仍按180原oracle归P4/P5，表中“待相应整链验收”并未批量改passed。R5合并净-5864，仅代码收缩通过；R3/R4完整联合出口仍需app/视觉及自然价值。当前完整r16和详情见[同一切换收据7.18—7.20](2026-10-01-p123-single-publication-cutover.md)。


## 11. P4准备清理及咨询来源实际缺口（2026-10-02）

现役10个scripts逐文件职责/摘要见 `tmp/p4-preparation-20261002-r2/retained-script-inventory.json`，没有仅按“历史”名字删除现有Provider冻结/账本/隔离回归能力。tests中两处无调用helper16行精确移除，其他AST及原测试名保留。无额外工具名或事实适配器；原76工具名和0旧发布import不变。

CONS实际演练新增13个空数据/已加载数据/中英文/源答案/混合计算用例；346联合通过，r3真实RED证实无原答案presentation误标answered，现由同一typed intent和snapshot原来源合同处理局部缺口，具体源/断言层次与失败见切换收据7.22。代码合并净-5803。完整r17尚在运行；10种程序保留及局部控制不签收所有180原场景、自然路由/审核质量或视觉。


当前完整r17为3284 passed /2 skipped /16 warnings，369摘要无变化，见切换收据7.23；第11节运行中状态保留当时记录，当前仅E2签收、app/视觉/自然未评估。
