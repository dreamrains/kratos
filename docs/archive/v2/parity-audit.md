# v1→v2 功能对齐审计（2026-08-23）

方法：代码级盘点（工具注册面/agent 层/知识层/web 层四路，含一手精读 hypotheses.py、planner.py、v2 引擎），全部结论有 file:line 依据；v1 指 /legacy 入口（AgentLoop 系），v2 指根入口（v2 运行时）。v1 侧相关测试 419+259 全绿——**v1 功能完好，问题只在 v2 未继承**。

判定图例：✅ v2 已覆盖且更强 ｜ 🔶 部分覆盖 ｜ ❌ 退步待补 ｜ 🔄 理念沿用、按 v2 方言重建 ｜ ⏸ 有意不搬 ｜ 📋 扩容候选（遥测排序）

## 一、引擎层（v1 工具 → v2 kind）

| v1 能力 | v2 现状 | 判定 |
|---|---|---|
| describe/preview/quick_profile | descriptive | ✅ |
| analyze_time_series | time_trend（HAC/季节控制更强） | ✅ |
| ab_test | group_comparison（+B1.1 配对/聚合） | ✅ |
| correlation/attribution | factor OLS（+B1.5 双变量降级） | ✅ |
| top_n | B1.2 多组排序 | 🔶→✅ |
| compare_periods（环比/同比+可比性检查） | **无** | ❌ 高频，进 B2 |
| cohort_analysis（留存矩阵） | **无**（B1.3 曲线拟合只覆盖留存曲线） | 📋 |
| funnel_analysis | **无** | 📋（游戏/电商高频） |
| contribute_decomposition（贡献度分解） | **无** | 📋 |
| forecast（Prophet） | forecast（naive/drift/seasonal；更诚实但更弱） | 🔵 模型族可扩 |
| causal_analysis（DID 模板） | 无 | 📋（v2 因果边界更严，做则做真 DID） |
| segmentation/classification/regression/what_if | 无 | 📋 低优先 |
| transform_data/derive_field（通用变换/派生列） | 仅日期转换 | ❌ 与 B2 组合单位/多数据集相关 |
| run_python | L3 探索性沙箱（计划已含） | 🔄 |
| 数据清洗（clean_data 等） | B1.4 自愈（被动）；无显式清洗工具 | 🔶 |

## 二、agent 层

| v1 能力 | v2 现状 | 判定 |
|---|---|---|
| 意图分类（9 类两层 + 4 级人设 + 3 级熟练度） | 无 | 🔄 L0 已入计划；**熟练度 3 级语言分级（prompts.py:321,353-377）应并入 B3** 叙述生成器 |
| **推荐分析方向**（三层：auto_insight 扫描 data_io.py:482 / interpret_dataset.suggested_analyses data_understand.py:892 / 剧本推荐+双轨推荐模型） | 无 | 🔄 **Track1 进 B2**（v2 的 `_missing_prerequisites_for_kind` + 数据画像天然是 ready/needs_confirmation/blocked 计算器）；Track2 探索建议并入 B3 |
| method_playbooks（13 剧本，含业务方法知识） | planner schema（8 kinds） | 🔄 理念已合同化；剧本知识 = 引擎扩容需求清单（funnel/retention/causal…） |
| synthesis_policy（insight_depth/business_translation/wording_style/required_moves） | 模板 + B3 计划 | 🔄 维度设计直接搬进 B3 输入 |
| analysis_state（6 阶段/数据契约/验证报告） | commitment/outcome 事实投影 | ✅ 更强 |
| **假设集**（hypotheses.py） | 无 | 🔄 见下节专项结论 |
| verification.py claims 校验 | compile_answer（claim 上限/canonical 值/引用实存） | ✅ 更强 |
| 高风险能力门控 | 授权门 + claim ceiling | ✅ 更强 |
| 任务管理（task_manager，跨会话、依赖、计划字段） | 无 | ❌ B4 |
| 上下文压缩（compact/micro_compact/大输出落盘） | 无（v2 单轮） | B2 多轮后需要 |
| 中断恢复/确认挂起 | stop/steer/needs_input | ✅（形态不同，等价） |

## 三、知识/记忆/证据系统（v1 最大资产）

v1 完整体系：KnowledgeLibrary + MemoryStore（候选→确认）+ EvidenceStore + KnowledgeRetrievalService（每轮检索注入系统提示 loop.py:732-748，知识/记忆冲突检测 retrieval.py:275-308）+ 管理面板（management.py）。**v2 完全没有这一层**——v2 的 findings/commitments 是会话内证据，跨会话知识/记忆无任何承载。判定：❌ 整层缺失，需要独立批次（设计先行：v2 的 finding/claim 体系与 EvidenceStore 的关系、检索注入点在哪层）。

## 四、web/产品层

v1 web 十类功能 vs v2 workbench：会话管理（列表/搜索/切换/**回退重发**/分支）❌、项目管理❌、任务看板❌（v2 仅活动流）、多文件上传❌（v2 单文件）、斜杠命令/压缩❌、知识管理面板❌、能力展示❌、图表（内联 Plotly JSON/Mermaid/补充图区/导出）🔶、KaTeX/token 环❌、自由多轮对话+确认卡❌（v2 表单化单轮）。v2 独有且应保留：授权门/估算/两段式规划确认/needs_input 卡/刷新恢复/steer/结构化块+calibration 标注。判定：B4 清单已具体化（见计划引用）。

## 五、两个具名功能的专项结论

### 推荐分析方向 —— v1 正常，v2 全无，**可高保真低成本重建**
v1 三层机制完好（测试绿）：加载时自动洞察扫描、interpret_dataset 输出 suggested_analyses（direction/tools/priority/reason）、意图触发剧本推荐 + 双轨推荐模型（Track1 严格可执行 / Track2 探索带条件声明）。**沿用方式**：v2 的确定性前提检查（`_missing_prerequisites_for_kind`）+ 列角色画像可直接计算"当前数据能跑什么/缺什么"——Track1 比 v1 的信任状态更准；Track2 并入 B3 叙述层（探索建议+数据缺口声明）。零 LLM 成本即可先落地 Track1。

### 竞争性假设对抗式验证 —— 存在且测试绿，但**成色有限；理念沿用、代码不搬**
一手精读 agent/hypotheses.py 结论：实现是**确定性模板假设集**——每路线生成 1 主假设+2 替代+1 基线（"正常波动"）；状态更新靠**文本 token 重叠 ≥0.75** 判 supported（:298-314）；设计中的 weakened（被证据削弱）状态**从未实现填充**；无 LLM 对抗辩论环节。触发条件：directed_analysis/comprehensive_report 且已有证据（loop.py:1216-1245）。
**沿用判断**：文本重叠匹配不值得移植；值得继承的是三条纪律——①**呈现纪律**：结论必须面对竞争解释（进 B3：替代解释段强制）；②**统计对抗**：让引擎真比（B1 已在做：零结果vs双变量、配对vs独立、曲线多族对比、共线性诊断）；③进阶可选：planner 在 unsupported/单路线时披露"竞争路线"（进 B2 范围披露块），findings 层增加 competing_explanations 结构。

## 六、沿用总清单（→ 批次映射）

| 批次 | 新增沿用项 |
|---|---|
| B2 | Track1 确定性推荐；period_comparison kind；派生列/通用变换（组合单位依赖）；planner 前轮上下文（结果追问） |
| B3 | 熟练度 3 级语言分级；替代解释段强制；insight_depth/business_translation 维度；Track2 探索建议 |
| B4 | web 对齐清单（会话管理含回退重发/任务看板/图表增强/导出/斜杠命令/KaTeX） |
| B7（新增） | 知识/记忆/证据系统接入 v2（设计评估先行，含管理面板与检索注入点） |
| 📋 遥测候选 | funnel/cohort/contribution/DID/segmentation/what_if/Prophet 增强——按 L4 遥测频率排序进 B1 类扩容 |
| ⏸ 不搬 | run_python 自由执行（L3 替代）、报告生成器（对话内合成）、破坏性发布门（架构上不存在） |
