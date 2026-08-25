# 7/13 能力保全台账（Gate A）

- 日期：2026-08-25
- 状态：Gate A 已确认；Slice 0 已按台账实施，等待收口验收
- 当前基线：rebuild @ 6ae6abe0a49d5c0d42b559645127b14a5ea7f9a2
- 7/13 基座：1d570617332103a04a1e944cc7f8be774901a938
- 基线关系：当前 HEAD:src 与 1d57061:src 均为 f3769ad16f903e644995ab8810031cec03f7e10b
- 目的：把“保留 7/13 全部能力”变成逐项可验证的替换合同，防止再次出现 V2 式无声删减

## 1. 决策规则

本台账记录的是用户能力，不要求保留旧内部结构。

| 决策 | 含义 |
|---|---|
| 保留并强化 | 用户结果保持，修复严谨性、稳定性或交互缺陷 |
| 合并实现 | 用户结果保持，只删除重复的模型工具或重复内部路径 |
| 内部化 | 不再让模型显式调用，由运行时自动记录或投影 |
| 完成产品化 | 底层原语存在，但 Web 或 Agent 路由尚未构成完整能力 |
| 删除 | 用户已明确不要，或已被证明确属有害/无消费者的内部机制 |

删除约束：

1. 未在本台账登记的能力不得因重构顺手删除。
2. “没有被当前 UI 使用”不等于“没有用户价值”。
3. 每个替换项必须先通过同入口、同真实场景的纵向对等测试。
4. 对等通过后立即删除旧内部路径，不保留长期兼容层。
5. 不允许新建第二个产品运行时、第二个根入口或双写会话。

## 2. 当前基线事实

### 2.1 源码与工作树

| 项目 | 当前事实 |
|---|---|
| 分支 | rebuild |
| HEAD | 6ae6abe0a49d5c0d42b559645127b14a5ea7f9a2 |
| HEAD tree | fbbe3df020692f5bb2955f2285c211177233d0aa |
| src tree | f3769ad16f903e644995ab8810031cec03f7e10b |
| 7/13 src tree | f3769ad16f903e644995ab8810031cec03f7e10b |
| 受控源码清单摘要 | sha256:c6aa82e6361db126cb0ad6adde4bb64ad4330bf3c9049ba0f0dd3553988f5500；Gate A 工作摘要，不冒充 release digest |
| 摘要选择范围 | Git 中的 src、tests、scripts、main.py、pyproject.toml、uv.lock、start.bat、start.sh，共 298 个条目 |
| 审阅开始时 tracked/index | 干净；本次只产生本计划列出的文档修改/新增，未修改业务源码 |
| 审阅开始前未跟踪资产 | artifacts/、tmp/；属于既存用户资产，本阶段不修改、不清理 |

### 2.2 测试真相

2026-08-25 的当前源码测试结果：

| 运行 | 结果 | 结论 |
|---|---|---|
| 全 tests，maxfail=5 | 1073 passed、12 skipped、5 failed，在 49% 停止 | 不能宣称基线全绿 |
| 排除首批 2 个陈旧数据契约文件 | 1146 passed、12 skipped、5 failed，在 53% 停止 | 仍有同根因失败 |
| 排除全部 8 个已定位的陈旧真实数据契约文件 | 1846 passed、3 skipped | 未受该漂移影响的核心源码基线稳定 |

已定位的 8 个陈旧测试文件：

- tests/test_analysis_quality.py
- tests/test_comprehensive_analysis_flow.py
- tests/test_mvp_real_data_fixtures.py
- tests/test_mvp_retrieval_budget_real_data.py
- tests/test_optimization_comparison.py
- tests/test_phase_comprehensive.py
- tests/test_pipeline_comprehensive.py
- tests/test_system_data_analysis_quality_audit.py

共同问题：

- 引用不存在的 省钱卡订单_20260507.xlsx；
- 引用不存在的 省钱卡用户最近流水_20260511.xlsx；
- 部分测试依赖 D:/Project/Daily/备用/... 仓库外绝对路径；
- “目录存在”被错误当成“所有必需文件存在”，导致应跳过或应明确报清单漂移的测试直接进入业务断言。

处理原则：Slice 0 先统一真实文件 manifest，再决定迁移测试语义；不通过复制旧文件名或保留外部绝对路径制造假绿。

## 3. Gate A 的 76 个模型工具能力与 Slice 0 后的 73 项工具面

Gate A 静态扫描得到 76 个注册工具，下表覆盖其全部去向。Slice 0 已按确认决策删除 `generate_report`、`generate_analysis_brief`、`generate_formal_report`，当前真实进程注册 73 项工具；这不是能力无声删减，而是用主回答合成 + `export_conversation` 保留用户结果后的显式替换。

### 3.1 数据输入、理解与导出

| 能力 ID | 当前工具 | 决策 | 必须改进 | 最低验收 |
|---|---|---|---|---|
| CAP-DATA-01 | load_data、load_sql | 保留并强化 | Slice 0 将当前真实可用且声明一致的格式固定为 CSV、TSV、Excel、JSON、JSONL；环境未声明/安装 pyarrow，因此不再宣称 Parquet/Feather 可用。后续若新增格式，必须先补依赖、启动和真实上传契约 | 每种已声明格式契约测试；真实 Excel 浏览器上传；错误不得伪装为完成 |
| CAP-DATA-02 | list_data | 保留并强化 | 返回会话内全部逻辑数据集、活动版本和血缘，不能只返回最后一个数据集 | 多文件上传后所有数据集可见 |
| CAP-DATA-03 | preview_data、describe_dataset、quick_profile | 保留并强化 | 统一列角色、缺失、范围、单位、粒度和采样披露，避免三套互相矛盾的画像 | 相同版本的关键 schema 一致 |
| CAP-DATA-04 | detect_data_quality、assess_readiness | 保留并强化 | 质量诊断与转换动作分离；缺失、异常、重复、常量、时间不完整、依赖缺失分别报告 | 诊断本身不修改数据、不触发无意义确认 |
| CAP-DATA-05 | interpret_dataset | 保留并强化 | 保留业务语义、分析信号和推荐路径；推荐必须区分 ready、需语义输入、不可用 | 任一真实文件均产生有依据的可执行方向或明确原因 |
| CAP-DATA-06 | export_data、export_output | 合并实现 | 保留数据导出结果，只保留一个模型可见的数据导出工具；建议保留 export_data，删除 export_output 包装层 | CSV/Excel/JSON 导出；中文与数值往返；无双接口 |

### 3.2 数据转换与派生

| 能力 ID | 当前工具 | 决策 | 必须改进 | 最低验收 |
|---|---|---|---|---|
| CAP-TRANSFORM-01 | transform_data、derive_field、derive_features | 保留并强化 | 原始版本不可变；筛选、聚合、表达式和特征派生生成新版本；多父输入可表达 | 每次转换有父版本、参数摘要、内容指纹和可恢复结果 |
| CAP-TRANSFORM-02 | suggest_column_types、apply_type_conversion | 保留并强化 | 建议与执行分离；无歧义安全转换自动生成分析版本；材料损失或语义歧义进入 needs_input | 脏数值列可分析，转换损失显式，不中断安全路径 |
| CAP-TRANSFORM-03 | clean_data | 保留并强化 | 去重、填补、截尾、异常处理必须是 copy-on-write；材料性选择不得由模型静默猜测 | 原始数据不变；敏感性比较；用户可重跑不同选择 |

### 3.3 EDA 与业务分析

| 能力 ID | 当前工具 | 决策 | 必须改进 | 最低验收 |
|---|---|---|---|---|
| CAP-EDA-01 | analyze_time_series、compare_periods | 保留并强化 | 时间粒度、完整边界周期、同比/环比可比性、训练/观察窗口和有效样本显式化 | 不完整周期不产生误导趋势；period 场景有口径 |
| CAP-EDA-02 | correlation_analysis、distribution_analysis | 保留并强化 | Pearson/Spearman、缺失策略、有效样本、异常敏感性和关联边界显式化 | 数值 oracle + 关联不冒充因果 |
| CAP-EDA-03 | segmentation_analysis、top_n | 保留并强化 | 多组聚合、排序口径、分母、组合分析单位和描述性边界 | 游戏互推真实文件可完成组合单位排序 |
| CAP-EDA-04 | cohort_analysis、funnel_analysis | 保留并强化 | cohort 粒度、观察窗、截断；漏斗步骤、分母和顺序必须明确 | Agent 路由可达，非只做函数单测 |
| CAP-EDA-05 | contribute_decomposition | 保留并强化 | 贡献可加性、残差、基期和方向显式；不与因果归因混淆 | 分解和原指标可对账 |

### 3.4 统计、机器学习与模拟

| 能力 ID | 当前工具 | 决策 | 必须改进 | 最低验收 |
|---|---|---|---|---|
| CAP-METHOD-01 | ab_test | 保留并强化 | 自动识别配对/独立、单位聚合、效应量、区间、多重比较；计算不因“高风险”确认 | 配对省钱卡场景命中正确路径 |
| CAP-METHOD-02 | causal_analysis | 保留并强化 | DID 前提、处理/对照、时间、平行趋势和因果上限；不能只保留工具名 | Provider-neutral 路由 + 方法 oracle |
| CAP-METHOD-03 | attribution_analysis、regression_analysis | 保留并强化 | 恒等式、共享分子分母、时间趋势、共线性、依赖结构、稳健误差和零结果降级 | 因素场景可产生可信主结果或有信息量降级 |
| CAP-METHOD-04 | classification | 保留并强化 | 切分、泄漏、类别不平衡、校准、阈值和适用总体 | Agent 路由测试 + 固定 fixture |
| CAP-METHOD-05 | forecast | 保留并强化 | 候选模型、回测、基线、区间、边界周期、预测窗和失败降级 | 真实时间文件 canary + 离线 oracle |
| CAP-METHOD-06 | shap_analysis | 保留并强化 | 必须绑定已训练模型、数据版本和模型版本；解释不等于因果 | 回归/分类后可达，单独调用明确失败 |
| CAP-METHOD-07 | what_if_simulation | 保留并强化 | 假设、参数范围、外推和不确定性显式；不得伪装成预测事实 | Agent 路由和边界测试 |

### 3.5 Agent 开放能力、交互与图表

| 能力 ID | 当前工具 | 决策 | 必须改进 | 最低验收 |
|---|---|---|---|---|
| CAP-AGENT-01 | run_python | 保留并强化 | 保留探索能力；只有确定性重放成功的结果才能晋升为已验证结论，其余永久标注探索性 | 白名单、超时、无网络/任意文件 IO；重放成功/失败两条路径 |
| CAP-AGENT-02 | tool_search | 保留并强化 | 动态工具子集和发现；不能因默认组过窄让高级工具事实不可达 | 每类保留能力都有 provider-neutral 路由用例 |
| CAP-AGENT-03 | ask_user_question | 保留并收窄 | 仅用于用户独占的语义选择；不可用于安全计算、方法运行或可逆转换许可 | 无数据、歧义口径、歧义连接三类；安全计算零确认 |
| CAP-CHART-01 | create_chart | 保留并强化 | 图表条件触发；必须绑定精确数据版本、结果和持久化 artifact；工具成功不等于页面显示成功 | 趋势/比较/分布/关系/诊断；刷新后仍显示；不适合图表时不强制 |

### 3.6 分析流程元工具

| 能力 ID | 当前工具 | 决策 | 理由与处理 | 最低验收 |
|---|---|---|---|---|
| CAP-RUNTIME-01 | record_data_requirement、record_analysis_spec、record_analysis_plan | 内部化 | 用户需要专业计划，不需要模型花轮次写三份重叠 JSON；由回合运行时从用户问题、数据和工具义务生成最小内部记录 | 模型工具面删除；用户问题覆盖与义务仍可审计 |
| CAP-RUNTIME-02 | record_evidence_record | 内部化 | 证据必须由工具结果和服务端身份自动投影，不能由模型自证 | 证据生成零额外模型调用；工具失败不产 verified |
| CAP-RUNTIME-03 | get_analysis_summary | 保留并强化 | 这是结果追问和会话查询能力，不是记账仪式 | 压缩、刷新和结果追问后仍返回当前轮正确摘要 |

Slice 0 已删除 `record_insight_record` 在 registry、prompt、execution-control 等位置的残留引用，没有创建兼容实现；静态扫描测试禁止该死引用重新出现。

### 3.7 报告、产出与导出

| 能力 ID | 当前工具 | 决策 | 理由与处理 | 最低验收 |
|---|---|---|---|---|
| CAP-OUTPUT-01 | export_conversation | 保留并强化 | 用户明确要求保留产出与导出；支持完整会话 HTML/Markdown、中文、图表引用和稳定文件名 | Web 与工具入口一致，刷新后可下载 |
| CAP-OUTPUT-02 | generate_report、generate_analysis_brief、generate_formal_report | 已删除模型工具，保留用户结果 | Slice 0 已一次删除 registry、prompt、实现、旧路由和专属测试引用；正式分析由对话合成，持久化/导出由统一输出服务完成，不保留别名 | 静态工具面精确 73 项；旧 `/report` 路由为 404；主回答+HTML/Markdown 导出继续通过 |

### 3.8 任务、知识、文件、MCP 与 Skills

| 能力 ID | 当前工具 | 决策 | 必须改进 | 最低验收 |
|---|---|---|---|---|
| CAP-TASK-01 | task_create、task_get、task_list | 保留并强化 | 保留多阶段任务与查询；任务只读投影当前分析义务 | 任务与当前 session/project 隔离 |
| CAP-TASK-02 | task_update | 收窄并内部化完成语义 | 模型可更新备注或用户任务，但不能任意写 completed；完成由真实义务、证据和产物计算 | 任意工具成功不得推进不相关步骤 |
| CAP-KNOWLEDGE-01 | show_project_rules、update_project_rules | 保留并强化 | 规则范围、来源和冲突显式；外部写入按副作用策略确认 | 跨会话正确注入，不污染其他项目 |
| CAP-KNOWLEDGE-02 | create_knowledge_item、search_knowledge | 保留并强化 | 正式知识生命周期、来源和冲突检测 | Web 管理、Agent 检索和跨会话引用 |
| CAP-MEMORY-01 | create_memory_candidate、confirm_memory、extract_memory_candidates、list_memory_candidates | 保留并强化 | 候选与确认分离；不得从模型文本直接升级为事实 | 会话 A 确认、会话 B 使用；冲突披露 |
| CAP-KNOWLEDGE-03 | retrieve_knowledge_context | 保留并强化 | 预算、来源、冲突和当前问题相关性 | 长上下文压缩后来源不丢失 |
| CAP-FILE-01 | read_file、list_files | 保留并强化 | 限定工作区和明确错误，不把任意路径内容泄露给模型 | 路径边界、Unicode、缺失文件 |
| CAP-FILE-02 | write_file、edit_file | 保留并收窄 | 用户结果保留；覆盖外部文件属于需确认副作用；会话内新产物可自动写入 | 路径边界、原子写入、覆盖确认 |
| CAP-MCP-01 | call_mcp_tool、list_mcp_servers、add_mcp_server、enable_mcp_server、disable_mcp_server、delete_mcp_server | 保留并强化 | 调用能力与管理能力分离；删除/外部副作用明确确认；MCP 工具进入动态 registry | Web 管理和 Agent 调用各有回归 |
| CAP-SKILL-01 | load_skill、unload_skill、list_skills、enable_skill、disable_skill、delete_skill | 保留并强化 | 加载/启停/删除生命周期一致；删除需确认；技能工具依赖可检查 | Web 管理、Prompt 注入和跨会话状态 |

## 4. 非工具的 Agent 能力

| 能力 ID | 当前能力 | 决策 | 验收重点 |
|---|---|---|---|
| CAP-INTENT-01 | 9 类两层意图、闲聊、知识问答、分析咨询、结果追问 | 保留并强化 | 闲聊不进入分析；无数据不死路；结果追问携带当前轮摘要 |
| CAP-PERSONA-01 | 4 级人设、3 级熟练度和 wording style | 保留并强化 | 同一结论按 beginner/advanced 表达，不改变事实 |
| CAP-PLAYBOOK-01 | 方法剧本与问题类型路由 | 保留用户价值，简化实现 | 义务由问题和数据决定，不使用中央巨型 requirements 编译器 |
| CAP-HYPOTHESIS-01 | 主假设、替代解释、基线解释 | 保留纪律，删除文本重叠实现 | 核心推断必须给竞争解释和区分所需证据 |
| CAP-CONTEXT-01 | 大工具输出落盘、micro compact、LLM compact | 保留并强化 | 工具调用配对、数据版本、证据、未完成义务和知识来源不得在压缩后丢失 |
| CAP-INTERRUPT-01 | 后台执行、停止、确认挂起与恢复 | 保留并强化 | 一键停止、幂等恢复、失败终态、不能复活旧任务 |
| CAP-MODEL-01 | LiteLLM 多模型 | 保留并强化 | 模型能力 profile、thinking 策略、空正文检测、调用台账和测试零重试 |
| CAP-CLI-01 | CLI REPL | 保留并强化 | 与 Web 共用同一回合语义和分析结果，不另建运行时 |

## 5. Web 与产品能力

| 能力 ID | 当前能力 | 决策 | 当前缺口/验收 |
|---|---|---|---|
| CAP-WEB-01 | 新建、列表、搜索、切换、删除会话 | 保留 | 真实浏览器进程；会话隔离；删除需确认 |
| CAP-WEB-02 | 回退并重发 | 保留并强化 | snapshot 唯一 ID；回退后数据、任务、证据和图表一致 |
| CAP-WEB-03 | branch_session/list_branches 底层原语 | 完成产品化 | 当前未发现对应 Web API/UI；Gate A 后决定是否补入口，不能误称已完整可用 |
| CAP-WEB-04 | 项目创建、绑定、改名、解绑、删除 | 保留 | 不再保留 object_name 等兼容别名；迁移后统一 project |
| CAP-WEB-05 | 任务面板 | 保留并重做投影 | 默认折叠、用户折叠不被轮询覆盖、状态来自义务而非工具数量 |
| CAP-WEB-06 | 上传和会话内数据集 | 保留并强化 | 多文件、重复上传、格式错误、未上传状态；不得用“上传失败”描述未上传 |
| CAP-WEB-07 | SSE、进度、工具事件、最终答案 | 保留并强化 | 服务端进度不被客户端动画覆盖；正文不被 progress 覆盖；最终块先持久化再 turn_end |
| CAP-WEB-08 | 停止、确认卡、恢复 | 保留并强化 | 生成停止无需确认；确认只用于语义/副作用；刷新恢复同一卡片 |
| CAP-WEB-09 | slash command、手动 compact、token 环 | 保留 | 命令真正可执行；长会话压缩后语义不漂移 |
| CAP-WEB-10 | Markdown、代码、表格、KaTeX、Mermaid、Plotly | 保留并强化 | 本地 vendor；长回答不卡死；内联图和刷新恢复 |
| CAP-WEB-11 | LLM 配置与模型列表 | 保留并强化 | thinking、timeout、能力 profile 和密钥错误不泄露 |
| CAP-WEB-12 | Skills/MCP 能力管理 | 保留 | 启停、删除、错误和依赖状态真实 |
| CAP-WEB-13 | 知识、记忆、证据管理中心 | 保留 | CRUD、检索、来源、冲突、跨会话 |
| CAP-WEB-14 | Workbench 当前分析 | 删除非目标内容 | 只保留“已验证结论”；删除仍不确定、建议下一步、可信度摘要、分析范围、完整叙述、数据理解/关系下钻和确认 banner 的 Workbench 投影/UI |
| CAP-WEB-15 | Workbench 产出与导出 | 保留 | HTML/MD、产物列表、稳定链接、中文、刷新后可用 |
| CAP-WEB-16 | 响应式核心路径 | 保留并强化 | 桌面全旅程；窄屏至少上传、提问、停止、回答、已验证结论、产出和导出可达 |

Workbench 删除边界只影响右侧工作台。主对话必须继续保留完整回答、建议、方法、不确定性、数据范围和局限。

## 6. 数据与会话资产能力

| 能力 ID | 目标 | 决策与约束 |
|---|---|---|
| CAP-STORE-01 | 原始数据不可变 | 引入会话内逻辑数据集和版本；不覆盖 raw |
| CAP-STORE-02 | 分析版本与多父血缘 | Parquet+pyarrow 方案需在 Slice 0 做安装/启动预检；当前依赖清单没有 pyarrow，未通过前不能作为既成事实 |
| CAP-STORE-03 | 会话数据生命周期 | 数据属于会话，不因任务完成失效；旧绑定不得推进新轮次 |
| CAP-STORE-04 | 历史迁移 | 一次迁移、先备份副本、逐项计数和引用校验；缺原文件的历史会话只读 |
| CAP-STORE-05 | 产物身份 | UUID/内容身份；禁止秒级时间戳作为唯一身份；manifest 去重和损坏容错 |

## 7. Gate A 通过记录

用户已确认以下实施边界；后续切片仍必须逐项遵守：

1. 用户确认保留、合并、内部化和删除边界；
2. 76 个工具名全部有去向；
3. 16 个 Web 产品能力全部有验收；
4. Workbench 删除不影响主对话完整回答；
5. branch 产品化、pyarrow 依赖和历史迁移时点获得明确决策；
6. 每个后续纵向切片引用本台账中的能力 ID；
7. 任一保留能力回归时，当前切片立即停止，不进入下一切片。
