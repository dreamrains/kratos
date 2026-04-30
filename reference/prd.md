# 数据分析专家型 Agent 需求文档

> **文档状态**：V9.0 分析质量与交互优化
> **目标开发平台**：Claude Code
> **核心定位**：具备业务分析师思维、可对话、可自动出报告、可监控的协作型分析专家
>
> **V9.0 变更摘要**：
> - **数据粒度自动识别**：`quick_profile` 新增 `_detect_grain()` 函数，自动推断数据粒度（individual/daily_aggregate/weekly_aggregate/monthly_aggregate/multi_dimension_aggregate/aggregate/unknown），通过 `grain` + `grain_hint` 字段输出，防止从聚合数据推导个体级结论
> - **粒度约束规则**：系统提示词新增"数据粒度约束"，要求分析前确认数据粒度，对粒度不匹配的分析采用软提示（告知限制 + 建议替代方向 + 用户坚持可继续但需标注限制）
> - **动态推荐方向**：替换固定 ABCD 四选项模板为基于 data_profile 动态生成分析方向的原则性指导，面向一般用户默认不推荐预测
> - **ask_user_question 多问题模式**：删除"每次只问一个问题"限制，LLM 可根据场景选择单问题或多问题模式（questions 参数，最多 4 个）
> - **数据加载附带上下文**：`load_data` 新增 `context` 参数，LLM 从用户消息中提取指标定义等补充说明保存到 workspace 元数据
> - **CLI 多行输入**：`_repl_input()` 支持 Ctrl+Enter 换行，Enter 提交
>
> **V8.0 变更摘要**：
> - **CHAT 模式（非分析对话）**：新增第四级意图分类，问候、知识问答、闲聊等非分析消息走轻量 prompt，不调用分析工具、不注入领域知识
> - **静默探查（数据加载自动画像）**：load_data 加载后自动执行 quick_profile 紧凑模式，结果以 [data_profile] 标签注入上下文，不主动展示
> - **交互式引导流程**：模糊意图（"分析一下"/"看看这数据"）时先问方向性问题，再逐步细化，每次只问一个问题
> - **模糊意图结构化输出**：FULL 模式"帮我看看这份数据"输出编号洞察列表而非完整报告
> - **领域知识 suggested_analyses**：电商/游戏模板各增加 5 条推荐分析方向
> - **JSONL 追加式持久化**：per-turn 写入 JSONL（低延迟），超 256KB 轮转为 JSON 快照，启动恢复支持增量合并
> - **压缩边界安全**：compact_history 切割消息时保证 tool_use/tool_result 对完整，防止孤立消息
> - **压缩续接前导语增强**：显式指令防止 LLM 重复确认上下文
> - **启动时恢复历史会话**：启动时展示最近 5 个会话，输入编号恢复或直接输入开始新会话
> - **会话分支**：/branch [name] 从当前会话分叉，/branches 列出分支，不修改父会话
>
> **V7.0 变更摘要**：
> - **任务系统回归简洁模型**：参考 `reference/task.py` 的设计哲学，Task 是持久化工作项，LLM 完全控制生命周期，系统只做存取和展示
> - **移除 activeForm / parent_id / result_summary / metadata / updated_at**：任务数据模型从 12 字段精简为 8 字段（id, subject, description, status, blockedBy, blocks, owner, created_at）
> - **删除 _auto_track_progress**：移除系统自动推断进度的机制，由 LLM 通过 `task_update` 显式控制任务状态
> - **删除 task_create_from_template**：Skill 的 task_template 仅作为方法论参考保留在 SkillLoader 中，不再自动创建任务
> - **双向依赖传播**：`addBlocks` 自动更新被阻塞任务的 `blockedBy`，`completed` 自动清理依赖链
> - **ID 内存计数器**：从每次 glob 扫描目录改为内存计数器，性能 O(1)
> - **TaskDisplay 简化**：删除树状层级和 activeForm spinner，改为扁平列表 + 状态图标 + 依赖提示
> - **系统提示词更新**：任务管理从"按阶段跟踪进度"改为"LLM 自主规划具体步骤"
>
> **V6.0 变更摘要**：
> - **报告结构重构为金字塔原理**：PART 1 核心结论与摘要 → PART 2 关键发现与建议 → PART 3 支撑证据与数据，替代旧的 Summary → Findings → Methodology 结构
> - **Markdown 正确渲染**：报告中的 summary、description 字段使用 mistune 库将 Markdown 转为 HTML，解决表格、列表、加粗等语法在 HTML 报告中以原始文本显示的问题
> - **图表自动嵌入报告**：新增 `get_chart_embed_html()` 函数，从 session charts 目录自动提取 Plotly 图表并嵌入报告 HTML，无需 LLM 手动传递 `charts_html` 参数
> - **置信度标签智能解析**：新增 `_parse_confidence()` 函数，将 LLM 输出的中英文混合置信度文本（如"高 - r²=0.9"）自动映射为标准 `high/medium/low` CSS 类名，修复标签样式失效问题
> - **Methodology 章节移除**：方法说明内联到对应洞察卡片，不再单独输出 Methodology 章节
> - **PDF 导出修复**：将 WeasyPrint（依赖 GTK，Windows 不可用）替换为 xhtml2pdf（纯 Python，零系统依赖）
> - **对话导出工具**：新增 `export_conversation` 工具和 `/export` 命令，支持将对话中的分析结果导出为 HTML 或 Markdown
> - **报告模板 Jinja2 化**：使用 Jinja2 模板引擎渲染报告，支持条件性 Plotly CDN 加载和动态内容组装
> - **Prompt 强化**：FULL 模式阶段 7 增加 insights JSON schema 约束、confidence 字段规则、金字塔结构指导
>> **V5.0 变更摘要**：
> - **工具按需加载**：工具分为 core/eda/ml/stats/report/clean/task/knowledge 八组，初始仅加载 core 组（23个），根据用户输入关键词和工具调用动态激活，每轮节省 ~56% tool definition tokens
> - **系统提示词三级**：QUICK（数据变换/汇总，~380 chars，只注入 project_rules）、STANDARD（单维度分析，~1045 chars）、FULL（完整报告，~3356 chars），根据用户输入自动选择模板
> - **新增 quick_profile 工具**：一次返回数据全貌（结构+类型推断+质量+就绪度+suggested_next），替代分别调用 describe + quality + readiness 的 3 轮开销
> - **transform_data 增强**：新增 resample 操作（W/M/Q/Y 重采样），group_aggregate 支持多列多函数聚合
> - **统计工具补全**：ab_test 增加 Shapiro-Wilk 正态性判断 + Levene 方差齐性检验；forecast 返回 MAPE/RMSE/季节性强度诊断；regression/classification 支持 cv_folds 交叉验证；correlation/distribution 增加 p-value 和正态性检验；causal DID 增加预处理期趋势对比警告
> - **时间序列自动推断**：analyze_time_series 的 date_col 和 value_col 可自动推断，减少一轮 preview
> - **数据操作血缘追踪**：workspace 记录变换 DAG，list_data 展示变换历史
> - **工具返回 suggested_next**：quick_profile、analyze_time_series、correlation_analysis、distribution_analysis 返回建议下一步
> - **工具输出精简**：describe_dataset 只返回摘要（shape+列名+类型+缺失率），统计量不再全部进入对话历史
>
> **V4.0 变更摘要**：
> - 三层知识架构重构：全局 + 对象 + 会话级知识，知识先落会话层，绑定时提升到对象层
> - 会话支持动态绑定/解绑/换绑对象，知识随会话迁移（通过 source_session_id 溯源）
> - 新增 CLI 命令 `/bind <object>` 和 `/unbind`，支持会话与对象的动态关联
> - `/resume` 恢复会话时自动重建对象上下文（workspace + 知识系统 + prompt 缓存）
> - Web GUI 暂停（原 FastAPI + React），后续计划迁移到 Flask + HTMX
> - 所有核心逻辑为纯函数/类方法设计，同时支持 CLI 和 Web GUI 调用
>
> **V3.1 变更摘要**（已合入 V4.0）：
> - 新增展示层抽象（CLI/Web 双端适配）
> - Agent Loop 支持暂停/恢复（ask_user_question 暂停机制）
> - 工具返回值结构化（ToolResult）
> - 命令系统改为注册表模式
> - 新增 assess_readiness 数据就绪度评估工具
> - Insight Engine 增加 competing_hypotheses（多假设竞争）
> - Intent Analyzer 增加指标口径查找与轻量快答分类
> - Report Generator 增加双风格输出（executive/detailed）
> - 经验提取增加过滤条件，衰减速率按领域可配置
> - 监控规则增加去季节性检测选项

---

## 一、需求背景与价值

### 1.1 背景
- 企业内部业务/运营/产品人员（A类用户）需要频繁进行数据分析，但多数人缺乏 Python/SQL 能力，依赖数据团队取数，响应慢、沟通成本高。
- 现有 AI 分析工具普遍是“辅助写 SQL/代码”或“简单图表生成”，缺乏完整分析思维链：从理解问题、清洗数据、选择方法、挖掘洞察到形成结论建议。
- 分析师工作中大量重复性探索（趋势、异常、归因）耗费时间，而真正有价值的洞察综合与业务建议常常被压缩。

### 1.2 核心价值
- 让业务用户通过**自然语言对话**即可完成专业级分析，获得可信、可解释的结论与方法说明。
- 支持**一键生成完整分析报告**，将分析师从重复劳动中解放，专注高价值决策。
- 提供**主动监控预警**，让数据异常不被遗漏，实现“分析不只在问时发生”。
- 架构具备自我迭代和领域适应能力，越用越聪明，越用越贴合企业实际业务。

---

## 二、需求目标与目标用户

### 2.1 需求目标
打造一个**数据分析专家型 AI Agent**，具备以下核心能力：
1. **双模式交互**：Chat 模式（问答探索）与 Report 模式（全自动报告）。
2. **完整分析流程**：意图理解 → 数据清洗 → 数据处理（建模、归因、回归、预测等）→ 洞察生成 → 报告输出。
3. **领域适应**：支持预设电商、游戏、供应链等分析背景，并能从对话中引导构建新领域知识包。
4. **主动监控**：可设置关键指标守护规则，自动检测异常并推送预警与初步归因。
5. **记忆与进化**：项目级记忆文件、会话上下文复用、分析经验迭代纠错。
6. **工具生态**：文件操作、数据加载、多格式输入、Python 脚本执行、MCP/Skill 扩展。

### 2.2 目标用户
- **主要用户（A类）**：业务分析师、产品经理、运营专家。懂业务逻辑，编码能力较弱，需要结论+方法解释。
- **次要用户（B类）**：数据科学家/工程师。希望快速完成 70% 重复探索，保留干预和自定义能力。

---

## 三、用户故事（核心场景）

1. **快速问答**  
   运营问“最近一周 DAU 为什么下降了 12%”，Agent 在几轮对话内完成趋势计算、渠道下钻、归因，并返回带有方法说明的结论。

2. **自动报告**  
   产品经理上传一份 CSV，说“分析这个数据”，Agent 自动执行探索、趋势、维度拆解、异常检测、驱动分析，输出一份 6 章节完整报告，附图表和商业建议。

3. **连续追问**  
   业务人员追问“渠道 A 是什么问题？”Agent 自动复用上次分析上下文，直接做渠道 A 的下钻分析，不需重新加载数据或重新规划。

4. **主动预警**  
   运营设置“每日销售额波动超过 2 个标准差即预警”。第二天早上，Agent 自动推送消息：“昨日销售额异常下降 18%，初步归因：渠道 B 投放暂停贡献 70%”。

5. **知识积累与迭代**  
   分析多份游戏数据后，Agent 总结出“新手 7 日留存与关卡难度影响最大”，用户确认后成为领域知识的一部分；后续若出现矛盾则自动澄清。

6. **错误纠正**  
   用户在报告中指出某结论错误，Agent 溯源数据与工具链，自动将对应经验标记为废弃，并生成修正方案或从经验中降级该条知识。

7. **协同与安全**  
   团队成员在共享项目空间中看到分析历史，版本可追溯。敏感数据自动脱敏后再进入分析。

---

## 四、需求功能说明

### 4.1 核心名词定义

| 名词 | 定义 |
|------|------|
| **Analysis Session** | 一次完整的分析会话，可以包含多轮对话（Chat）或一次完整报告生成（Report）。 |
| **Conversation Agent** | Chat 模式的入口智能体，负责维持对话上下文，解析用户意图，并调度后续流程。 |
| **Intent Analyzer** | 意图分析模块，将自然语言转化为结构化的分析目标（分析类型、变量、约束等），并标记模糊点。 |
| **Planner (Analysis Planner)** | 分析规划器，根据意图生成 Task DAG（有向无环图），决定串行/并行执行策略。 |
| **Task DAG** | 分析任务的依赖图，节点为子任务，边为依赖关系，支持并行执行。 |
| **Execution Engine** | 执行层，负责调用工具和子 Agent 完成具体分析任务。 |
| **Insight Engine** | 洞察引擎，从执行结果中自动生成结构化的洞察卡片（趋势、异常、贡献、驱动），并附置信度、方法说明。 |
| **Report Generator** | 报告生成器，将洞察、图表按结构化模板组装成完整分析报告。 |
| **Session Context** | 会话上下文，存储已加载数据引用、中间结果、用户关注焦点，支持 Follow-up 复用。 |
| **Domain Pack** | 领域知识包，包含行业指标字典、常见分析偏好、阈值、业务背景，激活后增强分析专业性。 |
| **Project Context** | 项目级记忆文件，包括 `project_rules.md`、`domain_knowledge.yaml`、`experience_log.yaml`，记录规则、领域知识和经验。 |
| **Skill** | 一种可插拔的分析能力模块，封装特定分析流（如“电商促销归因”），未来可加载到 Planner 中当作模板。 |
| **Harness Layer** | 质量与演化层，提供评估、监控、反馈闭环、版本回滚等保障机制。 |
| **ask_user_question** | 与 Claude Code 对齐的用户确认工具，用于在关键节点阻塞等待用户决策。 |

### 4.2 整体架构图

```
┌──────────────────────────────────────────────────────┐
│  0. Presentation Layer ★New                          │
│  ┌────────────────────┐ ┌─────────────────────────┐ │
│  │ CLI Adapter         │ │ Web Adapter             │ │
│  │ - stdin/stdout      │ │ - REST API + SSE/WS    │ │
│  │ - 文件路径展示      │ │ - 图表内嵌渲染          │ │
│  │ - 阻塞式确认        │ │ - 卡片式确认            │ │
│  │ - /斜杠命令         │ │ - UI按钮触发            │ │
│  └────────────────────┘ └─────────────────────────┘ │
│  Command Registry (统一命令注册，双端共用处理器)       │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│                    Entry Modes                         │
│   Chat (Conversation Agent)  │  Full Report Mode      │
│   + 主动监控引擎 (Proactive Monitoring)               │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  1. Perception & Intent Layer                        │
│     Intent Analyzer · Ambiguity Detector · Domain R.  │
│     ★ 指标口径查找（未定义时触发确认）                  │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  2. Planning & Orchestration Layer                   │
│     Analysis Planner (Task DAG) · Parallel Strategy  │
│     Manual/Auto mode switch · Skill Template 融合     │
│     ★ 轻量快答 vs 完整DAG 自动分类                    │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  3. Executive Layer (Tools & Subagents)              │
│  ┌────────────────────────────────────────────────┐ │
│  │ L1 Data Understanding  L2 EDA  L3 Statistics   │ │
│  │ L4 ML                  L5 Viz   L6 Report      │ │
│  │ ★V5.0 quick_profile (合并3工具为1步)            │ │
│  │ ★V5.0 Tool Groups: core/eda/ml/stats/report... │ │
│  │ Underlying: File/Script/AutoClean/Artifact      │ │
│  └────────────────────────────────────────────────┘ │
│  工具返回值：ToolResult(summary, data, artifacts)      │
│  ★V5.0 suggested_next + 变换血缘追踪                 │
│  ★ ask_user_question 触发 Agent Loop 暂停/恢复       │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  3.5 Extension Layer ── ★New                         │
│  ┌────────────────────┐ ┌─────────────────────────┐ │
│  │ MCP Client Manager │ │ Skill Loader            │ │
│  │ stdio / SSE / HTTP │ │ SKILL.md + frontmatter  │ │
│  │ → Tool Bridge      │ │ → Prompt Injection      │ │
│  │ → Registry 透明注册 │ │ → Task Template         │ │
│  └────────────────────┘ └─────────────────────────┘ │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  4. Insight Synthesis Layer                          │
│     Insight Engine (Trend/Anomaly/Contribution/Driver)│
│     Hypothesis test · Conflict detection             │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  5. Memory & Knowledge Layer                         │
│  Session Context · Project Context                   │
│  Domain Packs · Experience Evolution Loop            │
│  Artifact Manifest (会话输出物追踪)                   │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  6. Collaboration & Governance                       │
│  Version Control · Privacy Mask · Knowledge Approval  │
└───────────────────────┬──────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────┐
│  7. Quality & Evolution (Harness) Layer              │
│  Structured Logging · Lifecycle · Error Recovery     │
│  Offline Eval · Online Monitoring · Feedback Loop    │
└──────────────────────────────────────────────────────┘
```

### 4.3 两种模式详细流程

#### 4.3.1 Chat 模式（探索对话）★V8.0 意图路由更新

```
用户输入
    ↓
Intent Analyzer 四级分类：CHAT / QUICK / STANDARD / FULL
    ↓ (CHAT)
轻量 prompt（无工具、无领域知识），友好简洁回答
    ↓ (QUICK)
直接执行工具，1-3 轮完成
    ↓ (STANDARD/FULL)
Conversation Agent 接收并更新 Session Context
    ↓
Intent Analyzer 提取意图 & 模糊检测
    ↓ (如模糊/缺少信息)
ask_user_question() 阻塞确认
    ↓
Planner 生成轻量 Task DAG (1~N 任务)
    ↓
Execution Engine 调用 L1-L5 工具执行
    ↓
Insight Engine 生成洞察卡片
    ↓
Conversation Agent 格式化回复：结论 + 方法说明 + 可选图表
    ↓
等待用户 Follow-up 或新问题 → 复用 Session Context
```

#### 4.3.2 Report 模式（自动完整报告）

```
用户上传数据并请求分析（或设定“全量分析”指令）
    ↓
Planner 加载默认全量分析策略（硬编码）：
   Data Exploration → Trend → Dimension Breakdown → Anomaly Detection → Driver Analysis
    ↓
生成 Task DAG，标记可并行的维度分析 Worker
    ↓
并行执行：
   Worker1: time_series + anomaly
   Worker2: channel/region/product breakdown
   Worker3: correlation + driver
   Worker4: segmentation (可选)
    ↓
Insight Synthesizer 聚合所有洞察
    ↓
Report Generator 按金字塔原理模板生成报告（★V6.0 重构）：
   PART 1: 核心结论与摘要（结论先行）
     - 核心摘要（Markdown 渲染，含指标表格和洞察概述）
     - Top 3-5 核心洞察卡片（结论 + 置信度标签）
   PART 2: 关键发现与建议（按分析类型分组）
     - 趋势分析 / 异常检测 / 驱动分析 / 贡献分析
     - 每条发现：标题、描述、方法（内联）、建议
   PART 3: 支撑证据与数据
     - 图表与可视化（Plotly 交互图表自动嵌入）
     - 详细数据表格、竞争假设
输出：完整报告（HTML/PDF/Markdown） + 内嵌交互图表
```

#### 4.3.3 主动监控预警流程

```
用户通过对话设定监控规则，例如：
“每天监控 sales 表，如果当日销售额低于过去 30 天均值的 2 个标准差，立即通知我并给出原因。”
    ↓
监控引擎注册规则：指标、数据源、检测频率、触发条件、通知方式
    ↓
定时任务（Cron）触发：
   - 从数据源加载新数据（或通过 MCP 取数）
   - 执行 describe + anomaly_detection
   - 若满足触发条件 → 进入微型分析流程
       Insight Engine 生成异常洞察 + 初步归因
       调用 report 推送（消息/邮件）
   - 若不满足 → 记录日志，静默
    ↓
用户收到预警后可点击“分析详情”转入 Chat 模式深入分析
```

### 4.4 核心模块详细说明

#### 4.4.1 意图分析器（Intent Analyzer）

**职责**：将自然语言转换为结构化意图对象，并识别模糊点，触发 `ask_user_question`。

**系统提示词设计要点**：
> 你是一个分析意图解析器。从用户的请求中提取：分析目标（趋势/归因/预测/比较/异常）、涉及的指标和维度、时间范围、约束条件、输出偏好。
> 若遇到指标名不明、多义、数据来源不确定、分析方法可选等模糊情况，标记为 "ambiguity"，并生成一个 `ask_user_question` 的建议。

**指标口径查找规则**（★New）：
1. 解析用户意图时，提取目标指标（如"DAU""活跃用户""转化率"）。
2. 在 `project_rules.md` 的数据字典中查找定义。
3. 若找到 → 直接使用，在方法说明中注明口径来源。
4. 若未找到 → 通过 `ask_user_question` 询问用户定义口径，确认后自动追加到 `project_rules.md` 的数据字典中。后续分析永久生效。
5. 不作为独立子流程，嵌入意图分析的自然对话中。

**意图分类规则**（★V8.0 四级分类）：
- **CHAT**：无数据上下文关键词的问候（你好/hello）、感谢（谢谢/thanks）、纯知识问答（什么是X/解释一下X）、极短输入（<8字）且无分析意图。行为：纯对话，无工具调用
- **QUICK**：含"汇总/导出/筛选/排序/分组/计算"等操作关键词，且不含"分析/趋势/为什么"等分析意图。行为：直接执行，1-3轮
- **STANDARD**：单维度分析、趋势、分布、相关性等明确分析意图。行为：4步分析流程
- **FULL**：含"报告/完整分析/全面分析/出个报告"等关键词。行为：完整7阶段流程

**关键设计**：
- 知识问答检测（"什么是X"/"解释X"/"介绍X"）优先于分析意图，防止"什么是回归分析"被误判为 standard
- Quick 检测在 Chat 之前执行，防止"按月分组汇总"被误判为 chat

**输出结构示例**：
```json
{
  "intent": "attribution",
  "depth": "full",
  "target_metric": "DAU",
  "metric_defined_in_rules": true,
  "dimensions": ["channel", "region"],
  "time_range": "last_7_days",
  "constraints": [],
  "ambiguities": [
    {"field": "channel", "issue": "表中存在 channel_id 和 channel_name，需要确认使用哪个"}
  ]
}
```

#### 4.4.2 分析规划器（Analysis Planner）

**职责**：根据意图和当前数据 Schema，生成 Task DAG，决定执行步骤和并行策略。将领域知识和经验作为加权参考。

**系统提示词设计要点**：
> 你是一个分析规划专家。根据意图对象、可用工具列表和激活的领域知识，生成一个高层次的分析计划。
> 计划由任务节点组成，每个任务指定工具和依赖。尽量识别可并行的子任务（如不同维度的 EDA）。
> 所有任务均引用不可变的数据快照，除派生字段外不得修改原数据。
> 如果意图是”生成完整报告”，则启用默认全面分析流程。
> 引用经验日志中的相关模式，但若与项目规则冲突，以规则为准。
> **首次加载新数据集时**，在 DAG 第一阶段自动编排 `assess_readiness`，评估数据就绪度。

**轻量快答模式**（★V5.0 更新）：
当意图的 `depth` 为 `lightweight` 时，Planner 生成最小 DAG（1-2个工具），返回初步观察后询问用户是否深入：
```
轻量 DAG: quick_profile → 返回”初步印象” → 追问”是否需要深入分析？”
```

**Task DAG 示例**（Chat: “为什么 DAU 下降？”）：
```
T1: quick_profile（替代 describe + quality + readiness 三步）
T2: analyze_time_series (依赖 T1)
T3: correlation_analysis (依赖 T1)
T4: attribution_analysis (依赖 T2, T3)
```

#### 4.4.3 会话管理器（Conversation Agent & Session Context）

**Chat 模式专属**，维护跨轮次的上下文。

**Session Context 结构**：
```python
{
  "session_id": "...",
  "loaded_data": {"main": <snapshot_ref>},
  "derived_fields": [{"name": "ARPU", "expression": "revenue/users"}],
  "last_analysis": {
    "intent": {...},
    "task_dag": {...},
    "task_results": {"T2": {"output_refs": {...}, "insights": [...]}},
    "focus": ["channel A"]
  },
  "user_preferences": {"output_style": "conclusion_and_method"}
}
```

**Follow-up 处理逻辑**：
1. 解析新问题中的实体或引用。
2. 在 `last_analysis.task_results` 中查找匹配的数据子集。
3. 若找到 → 在该子集上直接调用轻量分析工具；若找不到 → 创建新任务下钻。
4. 始终带上前次分析的上下文摘要，让回复连贯。

#### 4.4.4 洞察引擎（Insight Engine）★核心价值

不仅是数据总结，而是能像分析师一样提炼洞察。输出偏向”结论说明 + 方法说明”。

**洞察卡片结构**：
```json
{
  “type”: “Trend | Anomaly | Contribution | Driver”,
  “title”: “过去7天DAU下降12%”,
  “description”: “DAU从10万降至8.8万，主要降幅发生在最近3天。方法：基于7天滑动平均趋势分解。”,
  “confidence”: “high”,
  “method”: “STL分解 + 趋势突变检测”,
  “competing_hypotheses”: [
    {
      “factor”: “渠道A流量减少”,
      “tested”: true,
      “contribution”: “65%”,
      “excluded”: false
    },
    {
      “factor”: “版本v2.3更新”,
      “tested”: true,
      “contribution”: “<3%”,
      “excluded”: true,
      “excluded_reason”: “版本更新前后DAU无显著差异(t-test p=0.72)”
    },
    {
      “factor”: “周末效应”,
      “tested”: true,
      “contribution”: null,
      “excluded”: true,
      “excluded_reason”: “已通过STL季节性分解校正”
    }
  ],
  “evidence”: {
    “data_ref”: “T2_output”,
    “chart_id”: “line_1”
  },
  “recommended_action”: “建议下钻分析渠道A的流量变化”
}
```

**`competing_hypotheses` 规则**（★New）：
- **Driver 和 Anomaly 类型洞察必须包含** `competing_hypotheses` 字段。
- 要求列出主驱动因子外，至少1个被检验但排除的候选因子，附排除理由。
- Trend 和 Contribution 类型洞察可选包含。
- 自然语言输出示例：
  > DAU下降12%主要归因于渠道A流量减少（贡献65%）。我们同时检验了版本更新（贡献<3%，无显著差异）和周末效应（已通过季节性分解校正排除），均非主要驱动因素。

**生成方式**：
- 每个分析工具（如 `analyze_time_series`）返回结构化结果数据。
- Insight Engine 应用规则（来自领域知识和项目规则）解释结果并生成自然语言洞察。
- 确保每条洞察包含**结论+方法说明**。
- **Driver/Anomaly 洞察必须包含多假设竞争与排除声明**。

#### 4.4.5 知识管理系统（三层体系）

知识管理采用三层结构，均由用户管理，Agent 自动加载并辅助维护。详见 **第6章**。

#### 4.4.6 自我迭代认知（经验演化闭环）

基于三层知识体系，经验演化遵循明确的生命周期，所有变动都记录在案，支持人工审计。详见 **第6章**。

#### 4.4.7 主动监控与预警引擎

- 用户通过对话设定监控规则。
- 定时加载数据并执行微型分析流程。
- 触发预警时推送包含初步归因的卡片，并提供转入 Chat 的入口。

#### 4.4.8 报告生成器（Report Generator）★V6.0 重构

**金字塔原理报告结构**（★V6.0）：

报告遵循金字塔原理（结论先行），使用 Jinja2 模板引擎渲染，分为三段式结构：

| 部分 | 内容 | 说明 |
|------|------|------|
| PART 1: 核心结论与摘要 | 核心摘要（Markdown→HTML渲染）+ Top 3-5 洞察卡片 | 结论先行，读者第一时间获取核心发现 |
| PART 2: 关键发现与建议 | 按类型分组（趋势/异常/驱动/贡献），每条含标题、描述、方法（内联）、建议 | 详细分析发现，方法内联到对应洞察 |
| PART 3: 支撑证据与数据 | Plotly 交互图表 + 数据表格 + 竞争假设 | 支撑结论的原始证据 |

**关键改进**（★V6.0）：
- **Markdown 渲染**：summary 和 description 字段使用 mistune 库转为 HTML，表格、列表、加粗等语法正确显示
- **图表自动嵌入**：从 session charts 目录自动提取 Plotly 图表嵌入报告，无需手动传递 charts_html
- **置信度智能解析**：_parse_confidence() 将中英文混合文本（如"高 - r²=0.9"）映射为标准 high/medium/low
- **方法内联**：移除独立 Methodology 章节，方法说明嵌入对应洞察卡片
- **条件性 Plotly CDN**：有图表时自动在 report head 加载 Plotly JS

**双风格输出**：

| 风格 | 目标用户 | 结构 |
|------|---------|------|
| executive | A类：业务/运营 | Executive Summary + Key Findings（最多7条）+ Visualizations |
| detailed | B类：数据科学家 | 完整三段式金字塔结构（PART 1/2/3），含竞争假设和详细图表 |

**导出格式**（★V6.0 增强）：
- HTML：交互式报告（Plotly 图表可交互）
- Markdown：结构化文本格式，图表以相对路径引用
- PDF：通过 xhtml2pdf 生成（纯 Python，无系统依赖）
- 对话导出：export_conversation 工具提取对话分析结果，支持 HTML/Markdown 格式

### 4.5 工具体系详细设计

#### 4.5.1 工具分层与命名

**L1 数据理解**
- `describe_dataset()` → 字段、类型、缺失率、分布概览。**V5.0 精简输出**：只返回 shape + 列名 + dtype + 缺失率，统计量不进入对话历史。
- `detect_data_quality()` → 缺失、异常、重复、常量列检测
- `preview_data(n=10)` → 返回样本
- `derive_field(name, expression)` → 安全派生新列，记录谱系
- `assess_readiness(dataset_info, quality_info, intent, loaded_tables)` → 数据就绪度评估。返回结构化报告，由 LLM 判断是否需通过 `ask_user_question` 介入。
- `quick_profile(name)` ★V5.0 New → **一次性返回数据全貌**：shape + 列类型推断 + 质量评估 + 就绪度 + warnings + suggested_next。替代分别调用 describe_dataset + detect_data_quality + assess_readiness 的 3 轮开销。prompt 中引导 LLM 默认使用 quick_profile。
  - ★V9.0 **粒度检测**：自动调用 `_detect_grain()` 推断数据粒度，输出 `grain`（枚举值：individual/daily_aggregate/weekly_aggregate/monthly_aggregate/multi_dimension_aggregate/aggregate/unknown）和 `grain_hint`（自然语言提示）。检测规则：ID列→个体级、日期列行数比+间隔→时间聚合、fill_ratio→多维聚合 vs 事件明细、聚合关键词→聚合数据。
  - ★V8.0 **compact 模式**：`quick_profile(name, compact=True)` 压缩列信息（正常列为 `col_name(type)` 字符串，有问题列保留详情），增加 summary 字段（numeric/category/date 计数），整体节省 50%+ token。load_data 静默探查使用紧凑模式，LLM 直接调用仍返回完整格式。

**Data Readiness Pipeline**（★V8.0 静默探查增强）：

`load_data → auto_clean → quick_profile(compact) → [data_profile]注入上下文` 构成精简管道。V5.0 之前需要 3 步（describe + quality + readiness），现在一步完成。V8.0 起 load_data 加载后自动执行 quick_profile 紧凑模式，结果以 `[data_profile]` 标签注入 LLM 上下文，不主动向用户展示，仅在意图模糊时用于推荐分析方向。

检查项与严重级别：

| 检查项 | 严重级别 | 说明 |
|--------|---------|------|
| 时间粒度不一致 | ⚠ Warning | datetime 列间隔不均匀或混合粒度 |
| 样本量不足 | ⚠ Warning | intent 为预测/分类时行数低于阈值 |
| 关键列缺失 >50% | 🔴 Block | 需用户确认后才继续分析 |
| 关键列缺失 30-50% | ⚠ Warning | 部分分析可能受影响 |
| 常量/准常量列 | ℹ Info | 无法用于维度拆解，附在方法说明中 |
| 多表未关联 | ⚠ Warning | 多个 DataFrame 加载但未指定关联键 |
| 数据时效性 | ℹ Info | 最新数据距今超过7天 |

LLM 根据严重级别决定后续行为：Info 附在分析结果中；Warning 主动告知风险但继续；Block 通过 `ask_user_question` 要求用户确认。

**L1.5 自动清洗（Auto-Clean Pipeline）** ★New
- `auto_clean(df)` → 数据加载后自动执行的清洗流水线
  - **高置信度自动转换**（无需确认）：datetime 格式识别、百分比字符串→浮点数、日期整数→datetime、布尔值标准化
  - **中置信度自动转换**（通知用户）：带后缀数值（如 "1.2K"）→数值、纯数字字符串→数值
  - **低置信度待确认**：通过 `ask_user_question` 请求用户确认类型（如是否为分类变量）
- `load_data()` 自动集成 `auto_clean()`，加载即清洗，返回清洗报告
- LLM 接收清洗报告后，对低置信度项使用 `ask_user_question` 与用户确认

**L2 EDA**
- `analyze_time_series(date_col='', value_col='')` → 趋势、季节性、突变点。★V5.0：date_col 和 value_col 可自动推断（留空即可），减少一轮 preview。返回 suggested_next。
- `correlation_analysis(columns, method='pearson')` → 相关系数矩阵，返回高相关性列表。★V5.0：返回 suggested_next，完整矩阵不再默认进入对话历史。
- `distribution_analysis(cols)` → 偏度、峰度、正态性检验（Shapiro-Wilk，n<5000）。★V5.0：附加 normality_test（test, p_value, is_normal），返回 suggested_next。
- `segmentation_analysis(features, method='kmeans')` → 分群+群体画像概要
- `cohort_analysis(time_col, event_col)` → 留存矩阵、生命周期

**L3 统计推断**
- `ab_test(group_col, metric_col, method='auto')` → t检验/Mann-Whitney U/卡方。★V5.0：auto 模式增加 Shapiro-Wilk 正态性判断（n<5000），非正态强制 Mann-Whitney；附加 Levene 方差齐性检验，根据结果选择 equal_var 参数。
- `causal_analysis(treatment, outcome, method='did')` → DID/PSM。★V5.0：DID 增加预处理期趋势对比，趋势差异>20% 返回 warning 提醒平行趋势假设可能不成立。
- `shap_analysis(model, data)` → 特征重要性/解释

**L4 机器学习**
- `forecast(target, horizon, method='auto')` → ARIMA/Prophet/简单统计。★V5.0：返回 diagnostics（mape, rmse, seasonality_strength）。
- `classification(target, features, method='auto', cv_folds=0)` → 流失预测等。★V5.0：新增 cv_folds 参数（默认关闭），启用时报告 cv mean ± std。
- `regression_analysis(target, features, method='auto', cv_folds=0)` → 线性/弹性网络/梯度提升。★V5.0：新增 cv_folds 参数。
- `attribution_analysis(target, features, method='shap')` → 渠道归因、特征归因

**L5 可视化**（★V6.1 增强）
- `create_chart(chart_type, data, params)` → 支持：line, bar, stacked_bar, scatter, box, histogram, heatmap, pie。默认使用 Plotly。
- 图表自动保存至**会话目录** `sessions/{id}/charts/`，并注册到 Artifact 清单。
- **★V6.1** 同时导出 PNG 静态图片（用于 PDF 嵌入），与 HTML 同名同目录。
- `get_chart_entries(session_id)` → 返回图表结构化条目列表（含 filename/title/html）。
- `match_chart(entries, keyword)` → 根据关键词子串匹配图表条目（支持中英文）。

**L6 报告**（★V6.0 重构）
- `generate_report(title, insights, charts_html, summary, style, data_scope)` → 金字塔结构 HTML 报告，Markdown 自动渲染，图表自动嵌入。insights 为 JSON 数组，confidence 必须为 high/medium/low 三选一
- `export_report_markdown(title, insights, summary)` → 导出 Markdown 格式（金字塔结构）
- `export_report_pdf(html_path)` → HTML 转 PDF（via xhtml2pdf，纯 Python，Windows 兼容）
- `export_conversation(title, format, include_charts)` ★V6.0 New → 将对话分析结果导出为 HTML 或 Markdown
- 报告自动保存至**会话目录** `sessions/{id}/reports/`，并注册到 Artifact 清单。
- **辅助模块**：`_markdown_to_html()`（mistune 渲染）、`_parse_confidence()`（置信度映射）、`get_chart_embed_html()`（图表提取嵌入）

**L0 底层支持工具**
- `read_file(path)`, `write_file(path, content)`, `edit_file(path, old, new)`, `list_files(pattern)` → 文件操作（**会话感知**：自动写入会话 output 目录）
- `execute_python(code, context_refs)`，`run_saved_script(path, args)`
- `run_python(code, timeout=30)` ★V5.0 修复 → exec 模式下正确返回 `result` 变量赋值。沙盒安全检查阻止 import os/sys/subprocess、open()、__import__ 等危险操作。可用 pd、np、get_dataset(name)。
- `load_data(source, format, context)` ★V9.0 → 加载数据并自动清洗，`context` 参数接收用户提供的指标定义/业务口径等补充说明（LLM 从用户消息中自动提取）。`export_data(ref, format, path)`，`sql_query(conn, query)`(预留)
- `transform_data(name, operation, params, save_as)` → ★V5.0 增强：
  - 新增 `resample` 操作：时间重采样（freq=W/ME/QE/YE，兼容旧写法 M/Q/Y 自动映射），支持多列多函数聚合（agg 为 dict 格式）
  - `group_aggregate` 增强为多列多函数聚合（agg 为 dict 格式，如 `{"col1": ["sum", "mean"], "col2": ["count"]}`）
  - 所有变换操作自动记录到 workspace 变换血缘日志
- `call_mcp_tool(server, tool, args)` → 直接调用 MCP 工具，`list_mcp_servers()` → 列出已连接服务器
- `load_skill(name)` → 加载技能模块，`list_skills()` → 列出可用技能
- `ask_user_question(question, options, multiSelect, freeInput, context, blockingLevel)` ★V9.0 支持多问题模式 → 详见 6.1。单问题模式用 `question` + `options`，多问题模式用 `questions` JSON 数组（最多 4 个问题依次提问）
- `task_create(subject, description)` / `task_update(task_id, status, owner, addBlocks, addBlockedBy)` / `task_get(task_id)` / `task_list()` — ★V7.0 简化为持久化工作项，LLM 完全控制生命周期

#### 4.5.2 工具注册表（Tool Registry）★V5.0 按需加载

工具注册表支持以下增强特性：

- **装饰器注册**：`@registry.register(name, description)` 自动注册函数为工具
- **超时控制**：`registry.set_timeout(name, seconds)` 设置工具超时，通过 `ThreadPoolExecutor` 执行（Windows 兼容）
- **来源追踪**：每个工具带 `origin` 字段（`native` / `mcp:{server_name}`），区分内置工具与 MCP 工具
- **自动发现**：启动时 `pkgutil.iter_modules` 自动扫描 `data_agent/tools/` 目录下所有模块，无需手动 import
- **统一调度**：所有工具（native + MCP）通过 `registry.execute()` 统一调度

**★V5.0 工具分组与按需加载**：

工具分为 8 个分组，初始只加载 `core` 组（~23 个工具），根据用户输入和工具调用动态激活：

| 分组 | 包含工具 | 触发关键词 |
|------|---------|-----------|
| `core`（始终可用） | load_data, list_data, export_data, describe_dataset, preview_data, transform_data, derive_field, run_python, ask_user_question, create_chart | — |
| `eda` | analyze_time_series, correlation_analysis, distribution_analysis, segmentation_analysis, cohort_analysis, quick_profile | 趋势/分布/相关性/探索/分析/为什么/原因/洞察 |
| `ml` | regression_analysis, classification, forecast, shap_analysis | 预测/回归/分类/建模 |
| `stats` | ab_test, causal_analysis, attribution_analysis | 比较/对比/A-B/归因/因果关系/显著性/为什么/原因 |
| `report` | generate_report, export_report_markdown, export_report_pdf, export_conversation | 报告/完整分析/全面分析/导出 |
| `clean` | suggest_column_types, apply_type_conversion, clean_data | 清洗/缺失值/异常值 |
| `task` | task_create, task_update, task_get, task_list | ★V7.0 简化：LLM 自主规划任务步骤，无模板创建 |
| `knowledge` | show_project_rules, update_project_rules, load_skill, list_skills 等 | — |

**激活机制**：

1. **关键词激活**：用户输入匹配分组关键词时自动激活（如输入"按周汇总"激活 core，输入"趋势分析"激活 eda）
2. **工具调用扩展**：LLM 调用某工具时，自动激活其所在分组
3. **未分组工具**：不在任何分组中的工具（如 MCP 工具、文件操作等）默认始终可用

**Token 节省效果**：52 个工具中初始只加载 ~23 个，节省 ~56% tool definition tokens/轮。

#### 4.5.3 工具调用协议

每个工具应有统一的输入/输出结构，并记录在结构化日志中（便于审计和回滚）。

**工具返回值结构**（★New）：

所有工具返回 `ToolResult` 结构化对象，而非纯字符串：

```python
@dataclass
class ArtifactRef:
    path: str           # 文件路径
    type: str           # "chart" | "report" | "file" | "analysis"
    description: str    # 简要描述

@dataclass
class ToolResult:
    summary: str                        # CLI 展示用（纯文本）
    data: dict | None = None            # Web 展示用（结构化数据）
    artifacts: list[ArtifactRef] | None = None  # 输出物引用
```

展示层根据运行环境选择渲染方式：
- **CLI**：使用 `summary` 纯文本显示
- **Web**：使用完整 `data` + `artifacts` 进行富渲染（图表内嵌、卡片展示等）

### 4.6 交互确认机制 (`ask_user_question`)

参考 Claude Code 的 `askUserQuestion` 设计，使用统一工具进行结构化确认。

- **参数**：
  - `question`: 描述清晰问题
  - `options`: 预置选项列表（含 label, description）
  - `multiSelect`: 默认 false
  - `freeInput`: 默认 true
  - `context`: 触发阶段与背景
  - `blockingLevel`: 当前统一为 "blocking"
- **触发时机**：意图模糊、数据质量问题、方法选择分歧、高风险操作前、指标口径未定义。
- **示例**：
```
ask_user_question(
  question = "数据表中 ‘revenue’ 和 ‘income’ 高度相关。哪个代表’主营业务收入’？",
  options = [
    { label: "revenue", description: "总收入（含税）" },
    { label: "income", description: "净收入（退款后）" }
  ],
  multiSelect = false,
  freeInput = true,
  context = "销售趋势分析前",
  blockingLevel = "blocking"
)
```

**Agent Loop 暂停/恢复机制**（★New）：

当 Agent 调用 `ask_user_question` 时，Agent Loop 不是同步阻塞，而是**暂停并持久化状态**，返回 `SuspendedForConfirmation` 结构：

```python
@dataclass
class SuspendedForConfirmation:
    suspension_id: str        # 唯一标识
    question: str             # 待确认问题
    options: list[dict]       # 预置选项
    context: str              # 触发背景
    snapshot: dict            # messages + 执行上下文序列化快照
```

- **CLI**：`SuspendedForConfirmation` 直接打印问题、读 stdin、调用 `resume_loop()` 恢复。用户无感知。
- **Web**：返回 `SuspendedForConfirmation` 的 JSON 给前端，前端渲染为确认卡片/表单。用户操作后通过 `POST /api/resume` 调用 `resume_loop()` 恢复。
- **Suspension 存储**：`sessions/{id}/suspension_{sid}.json`，支持跨会话恢复。

### 4.7 任务系统（★V7.0 重构）

参考 `reference/task.py` 的设计哲学：**Task 是持久化工作项，LLM 完全控制生命周期，系统只做存取和展示。**

**核心设计原则**：
- LLM 自主决定任务粒度和步骤拆分，系统不做 auto-tracking
- 任务数据模型极简：`{id, subject, description, status, blockedBy, blocks, owner, session_id, created_at}`
- 状态生命周期：`pending → in_progress → completed`；另有 `deleted` 状态（删除 JSON 文件）
- 依赖图通过 `blockedBy` / `blocks` 双向传播：`addBlocks` 自动更新被阻塞任务，`completed` 自动清理依赖链

**工具接口**：

| 工具 | 参数 | 说明 |
|------|------|------|
| `task_create` | subject, description | 创建任务 |
| `task_update` | task_id, status, owner, addBlocks, addBlockedBy | 更新状态和依赖 |
| `task_get` | task_id | 获取任务详情 |
| `task_list` | — | 列出所有任务 |

**终端显示（TaskDisplay）**：
- Rich Panel 扁平列表，无树状层级
- 状态图标：`[x]`（completed）、`[>]`（in_progress）、`[ ]`（pending）、`[-]`（deleted）
- blocked 任务显示 `(blocked by: [...])` 标记
- 进度统计：`N/M completed`
- 使用 Rich Live 实现原地更新（`task_display.py`）；`format_list()` 提供纯文本格式

**LLM 使用指引**（系统提示词）：
- 复杂分析（3+步骤）时，先用 `task_create` 规划分析步骤
- 每个任务是具体目标（如"分析收入趋势"），不是流程阶段
- 执行时用 `task_update` 标记 `in_progress`，完成后标记 `completed`
- 任务粒度和数量由 LLM 根据问题复杂度自行决定

**与 Skill 的关系**（★V7.0 变更）：
- Skill 中的 `task_template` 保留作为方法论参考，SkillLoader 仍可解析
- 但不再提供 `task_create_from_template` 工具，LLM 基于 Skill 指令自主规划任务
- Skill 的分析策略指导 LLM 的思维过程，不直接映射为任务创建

### 4.8 安全与隐私

- 自动脱敏：身份证/手机/邮箱等模式替换。
- 沙箱执行：`execute_python` / `run_python` 隔离，无网络（除 MCP 白名单），资源限制。自动扫描文本列中的间接提示词注入模式并发出警告。
- 文件操作二次确认。

### 4.9 质量保障（Harness 层）

- **离线评估**：10+ 标准数据集+问题+预期洞察，用于回归测试。
- **运行时监控**：数据漂移检测、工具调用异常率。
- **反馈闭环**：每条洞察附”👍/👎”，数据用于降权或确认经验。
- **版本回滚**：知识文件、经验、Skill 均带版本，可回滚。

### 4.10 MCP（Model Context Protocol）支持 ★New

支持通过 MCP 协议接入外部工具服务器，扩展 Agent 的工具能力。

#### 4.10.1 架构概览

```
┌───────────────────────────────────────────────────┐
│ Agent Loop                                        │
│   ↓ tool call                                    │
│ Tool Registry (统一调度)                           │
│   ↓ native tool → 直接执行                        │
│   ↓ mcp tool → MCPToolBridge                     │
│       ↓                                          │
│ MCPClientManager (后台 asyncio EventLoop 线程)     │
│   ↓ stdio / SSE / streamable-http                │
│ MCP Server 1 ─ MCP Server 2 ─ MCP Server N       │
└───────────────────────────────────────────────────┘
```

#### 4.10.2 传输协议

| 传输方式 | 配置项 | 适用场景 |
|----------|--------|----------|
| `stdio` | command, args, env | 本地 MCP 服务器（如文件系统、数据库） |
| `sse` | url, headers | 远程 MCP 服务器（Server-Sent Events） |
| `streamable-http` | url, headers | 远程 MCP 服务器（HTTP Streaming） |

#### 4.10.3 配置文件

MCP 服务器配置位于项目目录 `mcp_servers.yaml`：

```yaml
servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: [“-y”, “@modelcontextprotocol/server-filesystem”, “/tmp”]
    enabled: true

  - name: remote_api
    transport: sse
    url: http://localhost:8000/sse
    enabled: true
```

#### 4.10.4 核心组件

- **MCPServerConfig**：Pydantic 模型，校验传输协议与必填字段
- **MCPClientManager**：
  - 后台 `asyncio.EventLoop` 线程解决 MCP SDK 的异步需求（项目主体为同步代码）
  - `_run_async(coro)` 通过 `asyncio.run_coroutine_threadsafe()` 桥接同步/异步
  - **熔断器**：连续 3 次调用失败后标记服务器为 degraded，避免连锁超时
  - `discover_tools()` → 列出所有已连接服务器的可用工具
  - `call_tool(server, tool, args)` → 调用指定工具
  - `health_check()` → 检查服务器连接状态
- **MCPToolBridge**：
  - 将 MCP 工具透明注册到 ToolRegistry
  - 工具名格式：`{server_name}__{tool_name}`，origin 标记为 `mcp:{server_name}`
  - 对 AgentLoop 而言，MCP 工具与原生工具完全一致

### 4.11 Skill（技能模块）系统 ★New

支持可插拔的分析能力模块，封装特定分析流程（如”电商促销归因”）。

#### 4.11.1 Skill 文件格式

每个技能以目录形式存放在 `project/skills/<name>/SKILL.md`，采用 YAML frontmatter + Markdown body：

```markdown
---
name: ecommerce_promotion
description: “电商促销归因分析模板”
version: “1.0”
trigger_keywords: “促销,大促,活动,折扣”
tools_required:
  - describe_dataset
  - correlation_analysis
  - attribution_analysis
task_template:
  - id: T1
    tool: describe_dataset
    params: {name: main}
    depends_on: []
  - id: T2
    tool: attribution_analysis
    params: {name: main, target_col: revenue}
    depends_on: [T1]
---
# 电商促销归因分析

## 分析步骤
1. 数据质量检查
2. 渠道维度归因
...
```

#### 4.11.2 核心组件

- **SkillLoader**：
  - 启动时扫描 `skills/` 目录，解析所有 `SKILL.md` 的 frontmatter 和 body
  - `discover()` → 发现所有可用技能
  - `load(name)` → 加载技能，将指令以 `<skill name=”...”>` XML 标签注入系统提示
  - `unload(name)` → 卸载技能，从提示中移除
  - `get_task_template(name)` → 获取技能的预设分析流程（★V7.0：仅作方法论参考，不再自动创建任务）
  - `get_prompt_injections()` → 返回已加载技能的 XML 包装指令
  - `format_list()` → 格式化显示可用/已加载技能列表

- **SkillDef**：数据类，包含 name, description, version, trigger_keywords, tools_required, task_template, instructions, path

#### 4.11.3 Planner 集成（★V7.0 更新）

Skill 的 `task_template` 作为分析方法论参考注入系统提示，LLM 参考 Skill 指令自主规划任务步骤：

```
加载 Skill → 注入指令到系统提示 → LLM 参考 Skill 方法论自主创建任务
不再通过 task_create_from_template 自动批量创建
```

### 4.12 会话输出物追踪（Artifact Tracking） ★New

每个会话生成的文件（图表、报告、用户输出）自动注册到会话清单，建立文件与会话的关联。

#### 4.12.1 会话目录结构

```
sessions/{session_id}/
├── meta.json              # 会话元数据（ID、时间、模式、标签、object_name）
├── conversation.json      # 对话记录
├── artifacts.json         # 输出物清单（追踪所有生成文件）
├── knowledge/             # ★V4.0 会话级知识（三层架构）
│   ├── experience_log.yaml
│   ├── domain_knowledge.yaml
│   └── project_rules.md
├── analyses/              # 分析归档
│   └── ana_{timestamp}_{id}.json
├── charts/                # 图表文件
│   └── {title}_{id}.html
├── reports/               # 报告文件
│   ├── report_{title}_{ts}.html
│   ├── report_{ts}.md
│   └── report_{title}.pdf
└── output/                # 用户输出文件（write_file 工具）
    └── {user_path}
```

#### 4.12.2 Artifact 清单

`artifacts.json` 记录每个输出物的元数据：

```json
[
  {
    “path”: “sessions/{id}/charts/DAU_trend_a1b2c3.html”,
    “type”: “chart”,
    “description”: “DAU趋势分析”,
    “registered_at”: “2026-04-27 14:30:00”
  },
  {
    “path”: “sessions/{id}/reports/report_sales_analysis_20260427_143000.html”,
    “type”: “report”,
    “description”: “Sales Analysis Report”,
    “registered_at”: “2026-04-27 14:35:00”
  }
]
```

#### 4.12.3 自动注册时机

| 操作 | 注册类型 | 存放目录 |
|------|----------|----------|
| `create_chart()` | `chart` | `sessions/{id}/charts/` |
| `generate_report()` | `report` | `sessions/{id}/reports/` |
| `export_report_markdown()` | `report_md` | `sessions/{id}/reports/` |
| `export_report_pdf()` | `report_pdf` | `sessions/{id}/reports/` |
| `export_conversation()` | `conversation_html` / `conversation_md` | `sessions/{id}/reports/` |
| `write_file()` | `file` | `sessions/{id}/output/` |

### 4.13 结构化日志系统 ★New

替代 `print()` 输出，提供生产级可观测性。

- **JSONFormatter**：结构化 JSON 格式，包含 timestamp, level, logger, message, extra_data
- **ConsoleFormatter**：终端彩色输出
- **日志分类**：`data_agent.loop`（对话轮次）、`data_agent.registry`（工具调用+耗时）、`data_agent.mcp`（连接/断开）、`data_agent.skills`（加载/卸载）
- **配置**：支持 log_level（默认 INFO）和 log_file（文件输出）

### 4.14 Agent 生命周期管理 ★New

有序的初始化和关闭流程，确保资源正确分配和释放：

**启动顺序**：配置校验 → 日志初始化 → 工具自动发现 → MCP 连接启动 → 技能发现

**关闭顺序**：保存会话 → 停止 MCP 客户端 → 刷新日志

```python
class AgentLifecycle:
    def initialize(self): ...  # 有序启动
    def shutdown(self):    ...  # 有序关闭
```

### 4.15 错误恢复机制 ★New

Agent Loop 内置错误恢复策略：

- **LLM 重试**：对 `RateLimitError`、`APIConnectionError` 进行指数退避重试（最多 3 次）
- **工具错误恢复**：检测工具返回的错误响应（`Error:` 前缀），自动向 LLM 追加恢复提示，引导其选择替代方案
- **MCP 熔断器**：MCP 服务器连续 3 次调用失败后标记为 degraded，停止调用并通知用户

### 4.16 命令系统 ★Updated

采用命令注册表模式，CLI 和 Web 共用处理器：

```python
class CommandRegistry:
    def register(name, handler, description, aliases)
    def execute(name, args) -> ToolResult
```

**命令列表**：

| 命令 | CLI 触发 | Web 触发 | 说明 |
|------|---------|---------|------|
| `help` | `/help` | 帮助按钮 | 显示帮助信息 |
| `report` | `/report` | "生成报告"按钮 | 对当前数据生成完整分析报告 |
| `compact` | `/compact` | 设置菜单 | 手动压缩上下文 |
| `clear` | `/clear` | 新对话按钮 | 清空对话历史 |
| `data` | `/data <path>` | 文件上传 | 预加载数据文件 |
| `bind` | `/bind <object>` | 拖拽到项目 | ★V4.0 绑定当前会话到对象（支持换绑，自动迁移知识） |
| `unbind` | `/unbind` | 从项目移除 | ★V4.0 解除当前会话的对象绑定 |
| `tasks` | `/tasks` | 任务面板 | 列出项目任务（跨会话） |
| `skill` | `/skill` | 技能管理页 | 列出/加载/卸载技能 |
| `mcp` | `/mcp` | 设置页 | 列出 MCP 服务器状态 |
| `save` | `/save [tag]` | 自动保存 | 保存当前会话 |
| `sessions` | `/sessions` | 会话列表 | 列出已保存的会话（支持按对象过滤） |
| `resume` | `/resume [id]` | 点击历史会话 | 恢复会话（自动重建对象上下文和知识层） |
| `artifacts` | `/artifacts` | 输出物面板 | 查看当前会话的输出物清单 |
| `object` | `/object` | 对象管理页 | 对象管理（create/list/switch/info/archive） |
| `inbox` | `/inbox` | 切换到收件箱 | 切换到无归属模式（同 /unbind） |
| `migrate` | `/migrate <file>` | 文件迁移 | 将 inbox 文件迁移到当前对象 |
| `export` | `/export [markdown]` | 导出按钮 | ★V6.0 导出当前对话分析结果（默认 HTML，支持 Markdown） |
| `branch` | `/branch [name]` | — | ★V8.0 从当前会话创建分支（继承消息和上下文，不修改父会话） |
| `branches` | `/branches` | — | ★V8.0 列出当前会话的所有分支 |
| `exit` | `/exit` | 关闭页面 | 退出并自动保存 |

#### `/resume` 交互模式

与 Claude Code 对齐的会话恢复体验：
1. 输入 `/resume` 无参数 → 显示带编号的会话列表表格（含对象归属列）
2. 用户输入编号选择要恢复的会话
3. 自动恢复对话历史、数据文件引用
4. **★V4.0** 调用 `restore_object_context()` 重建对象上下文：设置 workspace 活跃对象、更新知识系统活跃对象、失效 prompt 缓存
5. 同步图表/报告的 session_id，确保后续输出物归入正确会话

#### ★V8.0 启动时恢复历史会话

启动 REPL 时不再直接创建空会话，而是展示最近 5 个历史会话：
1. 调用 `list_sessions()` 获取最近会话列表
2. `_format_recent_sessions()` 格式化为带编号的列表
3. 用户输入数字 → 恢复对应会话（复用 `load_session` + `restore_object_context`）
4. 用户输入非数字文本 → 创建新 session 并将该文本作为第一条输入处理
5. 无历史会话 → 直接创建新 session

#### ★V8.0 会话分支

```
/branch [name]
  → branch_session(session_id, branch_name)
    → 复制父会话消息到新 session（新 session_id）
    → meta 中记录 forked_from + branch_name
    → 复制对象绑定（如有）
    → 不修改父会话

/branches
  → list_branches(session_id)
    → 列出所有 forked_from == 当前 session_id 的会话
```

使用场景：用户想在某个分析节点尝试不同方向，分支保证原始分析路径不受影响。

#### ★V8.0 JSONL 追加式持久化

会话持久化从全量 JSON 重写改为 JSONL 追加模式：

| 操作 | 函数 | 说明 |
|------|------|------|
| Per-turn 追加 | `push_message(sid, msg)` | 追加一行 JSONL，写入失败不影响内存 |
| 批量追加 | `push_messages(sid, msgs)` | 追加多行 JSONL |
| 轮转合并 | `_rotate_jsonl(sid)` | JSONL > 256KB 时合并到 conversation.json 并删除 JSONL |
| 权威快照 | `save_session(msgs, sid)` | 写入 conversation.json 后删除 JSONL |

`load_session()` 自动检测 JSON/JSONL 格式并合并（先读 JSON 旧消息，再追加 JSONL 新消息）。向后兼容旧格式。

```
/bind <object_name>
  → bind_session_to_object(session_id, object_name)
    → 如果已绑定其他对象：先从旧对象迁移知识（migrate_between_objects）
    → 如果首次绑定：将会话知识提升到对象（promote_to_object）
    → 更新 meta.json 的 object_name
    → 更新对象的 sessions 列表
    → 设置 workspace 活跃对象
    → 失效 prompt 缓存

/unbind
  → unbind_session_from_object(session_id)
    → 更新 meta.json 的 object_name 为 null
    → 从对象的 sessions 列表移除
    → 清除 workspace 活跃对象
    → 知识保留在对象中（不删除）
    → 失效 prompt 缓存
```

### 4.17 展示层抽象与双端适配 ★Updated V4.0

Agent 架构从 V1 起即考虑 CLI 与 Web GUI 双端适配。核心原则：**业务逻辑层与展示层分离**。

**★V4.0 Web GUI 状态**：原 FastAPI + React 方案已暂停（代码移至 `reference/web_fastapi/` 备用）。后续计划采用 **Flask + Jinja2 + HTMX** 方案，实现服务端渲染 + 轻量交互，快速验证。所有核心逻辑已设计为纯函数/类方法，Flask 路由仅需薄壳封装即可。

**适配器模式**：

```
                    ┌──────────────────────────────┐
                    │      Presentation Layer       │
                    │                               │
                    │  CLIAdapter          WebAdapter│
                    │  - stdin/stdout      - Flask  │
                    │  - 文件路径展示      - HTMX   │
                    │  - 阻塞式确认        - SSE    │
                    │  - /斜杠命令         - UI按钮 │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │      Command Registry         │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │       Agent Loop              │
                    │       (suspendable)            │
                    └──────────────────────────────┘
```

**API 预留设计（P1）**：

所有核心功能已实现为可调用的纯函数，供 CLI 命令和未来 Flask 路由共用：

```python
# session/history.py
bind_session_to_object(session_id, object_name) -> dict
unbind_session_from_object(session_id) -> dict
list_sessions(object_name="") -> list[dict]

# knowledge/*.py
promote_session_knowledge(session_id, object_name) -> dict
migrate_session_knowledge(session_id, from_obj, to_obj) -> dict

# 未来 Flask 路由只是薄壳：
# @app.route("/api/sessions/<id>/bind", methods=["POST"])
# def bind(session_id):
#     return jsonify(bind_session_to_object(session_id, request.json["object_name"]))
```

**各模块的双端适配要点**：

| 模块 | CLI 表现 | Web 表现 |
|------|---------|---------|
| ToolResult | `summary` 纯文本 | `data` + `artifacts` 富渲染 |
| ask_user_question | 阻塞读 stdin | 返回确认卡片，回调恢复 |
| 命令 | `/斜杠命令` | UI 按钮 + REST API |
| 会话绑定 | `/bind <object>` | 拖拽会话到项目 |
| 图表 | 文件路径，用户自行打开 | Plotly.js 内嵌渲染 |
| 报告 | HTML 文件路径 | 内嵌报告阅读器 + 风格切换 |
| 任务进度 | 文本日志流 | 进度仪表盘（SSE/WS） |
| 数据就绪度 | 文本报告 | 可视化仪表盘 |

**不受展示层影响的模块**：知识系统、Insight Engine、Planner、工具核心逻辑、会话持久化、对象管理。

### 4.18 未来扩展点

- **★V4.0 Flask Web GUI**：基于 Flask + Jinja2 + HTMX 的 Web 界面，优先级最低，CLI 核心功能稳定后启动。技术栈：Flask 服务端渲染、HTMX 局部更新、SSE 流式聊天、Tailwind CDN 样式。
- **多数据源连接**：SQL 直连、更多 MCP 服务器集成。
- **团队协同**：项目空间、权限、评论、审核流。
- **主动监控引擎**：定时分析 + 异常预警推送。
- **经验演化闭环**：自动从分析结果提取经验模式。

---

## 五-A、改进记录（★V9.0）

**V9.0 已完成改进**：

| # | 优化项 | 改动文件 | 实现方式 | 状态 |
|---|--------|----------|----------|------|
| 1 | 数据粒度自动识别 | data_understand.py | 新增 `_detect_grain()` 函数，通过 ID 列、日期列行数比、聚合关键词、fill_ratio 等规则推断数据粒度，`quick_profile()` 在 compact 和 full 模式下均输出 `grain` + `grain_hint` | ✅ 已完成 |
| 2 | 粒度约束规则 | prompts.py | STANDARD 和 FULL 模式新增"数据粒度约束"段落，采用软提示：告知限制 + 建议替代方向 + 用户坚持可标注限制后继续，禁止粒度偷换（如将"83%的天数"偷换为"83%的用户"） | ✅ 已完成 |
| 3 | 动态推荐方向 | prompts.py | 替换固定 ABCD 四选项（趋势/对比/异常/预测）为基于 data_profile 动态生成推荐的原则性指导，推荐原则包括：优先趋势 > 维度对比 > 异常检测 > 仅数据量>200且有时间特征才推荐预测 > 禁止推荐粒度不支持的方向 | ✅ 已完成 |
| 4 | ask_user_question 多问题模式 | prompts.py, interaction.py | 删除"每次只问一个问题"限制，新增使用策略指导 LLM 按需选择单问题或多问题模式；工具 description 增加多问题模式 JSON 示例 | ✅ 已完成 |
| 5 | 数据加载附带上下文 | data_io.py, workspace.py | `load_data` 新增 `context` 参数，LLM 从用户消息中提取指标定义等补充说明；`Workspace` 新增 `_metadata` 存储 + `set_metadata()` / `get_metadata()` 方法；`list_datasets()` 包含元数据；`remove()` 自动清理元数据 | ✅ 已完成 |
| 6 | CLI 多行输入 | repl.py | `_repl_input()` 新增 Ctrl+Enter（`c-j`）键绑定插入换行，Enter 保持提交，ESC 中断功能保留 | ✅ 已完成 |

**关键设计决策**：
- **粒度检测 fill_ratio**：通过"实际行数 / 预期行数（日期数 × 维度值数）"的比值区分多维聚合（ratio 0.5-2.0）与事件明细数据（ratio << 0.5 或 >> 2.0）
- **时间粒度判断顺序**：days ≤ 2 为日聚合，≤ 8 为周聚合，≤ 35 为月聚合，避免周数据被月条件先匹配
- **软提示而非硬拒绝**：粒度不匹配时告知用户限制并建议替代方向，但用户坚持可继续（结论中标注限制），平衡安全性与灵活性
- **上下文提取由 LLM 负责**：不增加交互步骤，LLM 从用户消息中自动提取指标定义传入 `load_data` 的 context 参数

---

## 五-B、改进记录（★V7.0）

**V7.0 已完成改进**：

| # | 优化项 | 实现方式 | 状态 |
|---|--------|----------|------|
| A | 任务数据模型精简 | 移除 activeForm/parent_id/result_summary/metadata/updated_at，从 12 字段精简为 8 字段，对齐 reference/task.py | ✅ 已完成 |
| B | 删除 _auto_track_progress | 移除 _TOOL_PROGRESS 映射和 _auto_track_progress 方法，LLM 通过 task_update 显式控制状态 | ✅ 已完成 |
| C | 双向依赖传播 | addBlocks 自动更新被阻塞任务的 blockedBy，completed 自动清理依赖链 | ✅ 已完成 |
| D | ID 内存计数器 | 从每次 glob 扫描改为内存计数器 _alloc_id()，O(1) | ✅ 已完成 |
| E | TaskDisplay 简化 | 删除树状层级和 activeForm spinner，改为扁平列表 + 状态图标 + 依赖提示 | ✅ 已完成 |
| F | 删除 task_create_from_template | Skill task_template 保留为方法论参考，不再自动创建任务 | ✅ 已完成 |
| G | 系统提示词更新 | 任务管理从"按阶段跟踪"改为"LLM 自主规划具体步骤" | ✅ 已完成 |

---

**V6.0-6.1 已完成改进**：

| # | 优化项 | 实现方式 | 状态 |
|---|--------|----------|------|
| A | 图表与洞察关联 | insights JSON 增加 `chart` 字段（图表标题关键词），`match_chart()` 自动匹配并嵌入对应洞察卡片，未关联图表归入 PART 3 | ✅ 已完成 |
| B | PDF 嵌入静态图表 | `create_chart` 创建时同步导出 PNG（kaleido），`export_report_pdf` 读取 PNG 以 base64 嵌入 PDF | ✅ 已完成 |
| C | data_scope 自动提取 | `_extract_data_scope()` 从 workspace 主数据集自动提取日期范围和行列数，generate_report 中 data_scope 为空时自动调用 | ✅ 已完成 |

---

**V8.0 已完成改进（共 10 项，分三阶段实施）**：

### 第一阶段：独立、低风险、即时见效

| # | 优化项 | 改动文件 | 实现方式 | 状态 |
|---|--------|----------|----------|------|
| 1 | CHAT 模式 | prompts.py, loop.py | 新增 AGENT_CHAT 模板，`_classify_task()` 增加 chat 检测路径（问候/知识问答/极短输入），`build_system_prompt()` chat 分支不注入工具和领域知识 | ✅ 已完成 |
| 2 | 领域知识 suggested_analyses | domain.py | 电商模板增加 5 条推荐分析方向，游戏模板增加 5 条，`get_for_prompt()` 自动包含 | ✅ 已完成 |
| 3 | 压缩边界安全 | compact.py | 新增 `_find_safe_boundary()` 函数，扫描分割点确保 tool_use/tool_result 对完整 | ✅ 已完成 |

### 第二阶段：核心体验改进

| # | 优化项 | 改动文件 | 实现方式 | 状态 |
|---|--------|----------|----------|------|
| 4 | 静默探查 | data_io.py, prompts.py | load_data 加载后自动执行 quick_profile(compact=True)，结果以 [data_profile] 标签注入上下文；STANDARD/FULL prompt 增加"数据加载后行为"指令 | ✅ 已完成 |
| 5 | 交互式引导 | prompts.py | STANDARD/FULL prompt 增加"模糊意图引导流程"，先问方向性问题再逐步细化，每次只问一个问题 | ✅ 已完成 |
| 6 | 模糊意图结构化输出 | prompts.py | FULL 模式"帮我看看这份数据"策略表改为输出编号洞察列表 + 追问，不生成完整报告 | ✅ 已完成 |
| 7 | 压缩续接前导语 | compact.py | user 消息含显式指令"不要重复确认上下文"，assistant 消息精简为"好的，继续。" | ✅ 已完成 |

### 第三阶段：架构升级

| # | 优化项 | 改动文件 | 实现方式 | 状态 |
|---|--------|----------|----------|------|
| 8 | 启动时恢复历史会话 | repl.py | `run_repl()` 启动时展示最近 5 个会话，输入编号恢复或直接输入开始新会话，新增 `_format_recent_sessions()` 辅助函数 | ✅ 已完成 |
| 9 | JSONL 追加式持久化 | history.py, loop.py | 新增 `push_message()`/`push_messages()` 追加 JSONL；超 256KB 轮转为 JSON 快照；`load_session()` 自动检测并合并 JSON+JSONL；向后兼容旧格式 | ✅ 已完成 |
| 10 | 会话分支 | history.py, repl.py | 新增 `branch_session()` 复制父会话消息到新 session（记录 forked_from），`list_branches()` 列出分支；REPL 新增 `/branch [name]` 和 `/branches` 命令 | ✅ 已完成 |

**关键设计决策**：
- **compact profile 格式**：正常列压缩为 `col_name(type)` 字符串，有问题的列保留完整信息，整体节省 50%+ token
- **知识问答 vs 分析意图**：`is_knowledge_q` 检测（"什么是X"/"解释X"/"介绍X"前缀）优先于分析关键词匹配，防止误分类
- **Quick 优先于 Chat**：检测顺序 Full → Quick → Chat → Standard，避免"按月分组汇总"等操作被误判为 chat
- **JSONL 写入容错**：写入失败不影响内存状态，load_session 合并时容忍损坏行

---

## 五、核心模块提示词设计草案

### 5.1 Agent 系统提示词（★V8.0 四级模板）

系统提示词分为四个级别，根据用户输入自动选择：

| 级别 | 触发条件 | Prompt 长度 | 预期轮次 | 内容 |
|------|---------|------------|---------|------|
| `CHAT` ★V8.0 | 问候/知识问答/闲聊/极短输入 | ~200 chars | 1 轮 | 纯对话模式，无工具，注入 session_context |
| `QUICK` | 数据变换/查询/汇总/导出/计算 | ~380 chars | 1-3 轮 | 工具选择规则 + 简洁回复格式 |
| `STANDARD` | 单维度分析/趋势/分布/相关性 | ~1045 chars | 3-6 轮 | 4 步分析流程 + 策略表子集 + 置信度 |
| `FULL` | 完整报告/全面分析/归因/预测 | ~3356 chars | 7+ 轮 | 完整 7 阶段流程 + 多假设竞争 + 任务管理 |

**推断逻辑**（★V8.0 更新）：
1. 输入含"报告/完整分析/全面分析" → FULL（优先级最高）
2. 输入含"汇总/导出/筛选/排序/按周/按月"且不含"分析/趋势/为什么" → QUICK
3. 输入无数据上下文关键词 + 含问候/知识问答关键词 → CHAT
4. 其他 → STANDARD

**CHAT 模式行为规则**（★V8.0）：
- 友好、简洁地回答用户问题
- 不调用分析工具（tool_list 为空）
- 不注入 domain_knowledge 和 experience_log
- 仅注入 session_context（保留数据上下文以便结合回答）
- 如果用户的问题实际需要数据分析，建议用户明确描述分析需求

**各级模板共同包含的指令**：
- **工具选择决策树**：明确工具优先级（transform_data > derive_field > analyze_time_series > run_python），禁止用 run_python 完成已有工具能做的事
- **quick_profile 优先**：禁止分别调用 describe_dataset + detect_data_quality + assess_readiness
- **技能注入**：已加载的 Skill 指令以 `<loaded_skills>` 标签注入系统提示末尾

**FULL 级别包含**：
- **身份与定位**：数据分析专家 Agent，服务业务/运营/产品人员
- **分析思维链**：理解问题 → 评估数据 → 选择方法 → 执行分析 → 验证结论 → 业务翻译
- **分析策略表**：定义常见分析类型的推荐工具链
- **完整报告流程**：7 阶段管道（数据探索 → 清洗 → 描述统计 → 趋势分析 → 维度拆解 → 驱动分析 → 洞察综合）。★V6.0 阶段 7 增加金字塔原理约束：insights JSON schema 强制 confidence 为 high/medium/low，方法内联不单独输出，图表自动嵌入
- **任务管理**（★V7.0 更新）：复杂分析时先用 task_create 规划步骤（每个 task 是具体目标，不是流程阶段），再用 task_update 标记进度。LLM 自主决定任务粒度
- **多假设竞争**：Driver/Anomaly 洞察必须包含排除的候选因子
- **行为准则**：遇模糊时用 ask_user_question 确认；不虚构数据
- **回复格式**：直接结论 + 使用方法 + 关键数据 + 置信度 + 建议

### 5.2 `ask_user_question` 使用模板

```
我在分析过程中遇到问题：
[清晰描述]

请您选择或补充：
1. [选项1] - [说明]
2. [选项2] - [说明]
3. 自行输入
```

---

## 六、知识积累与演化规则（详细设计）

### 6.1 三层知识文件体系

★V4.0 重构：知识管理采用**三层架构**（全局层 + 对象层 + 会话层），每层包含三类知识文件（project_rules、domain_knowledge、experience_log）。

#### 存储位置

```
project/knowledge/                          ← 第一层：全局知识（始终可见）
  ├── project_rules.md
  ├── domain_knowledge.yaml
  └── experience_log.yaml

objects/{name}/knowledge/                   ← 第二层：对象知识（绑定该对象时可见）
  ├── project_rules.md
  ├── domain_knowledge.yaml
  └── experience_log.yaml

sessions/{id}/knowledge/                    ← 第三层：会话知识（该会话始终可见）★V4.0新增
  ├── project_rules.md
  ├── domain_knowledge.yaml
  └── experience_log.yaml
```

#### 知识流向

```
知识生成 → 先写入会话层 sessions/{id}/knowledge/
绑定对象 → promote_to_object() 合并到 objects/{name}/knowledge/
换绑对象 → migrate_between_objects() 从旧对象迁移到新对象（通过 source_session_id 精确定位）
解绑     → 知识保留在对象中，会话层保留副本
```

#### 知识可见性

Agent 的系统提示词构建时，合并所有可见层：
```
active view = 全局知识 ∪ 当前对象知识 ∪ 当前会话知识
```

#### 第一层：项目规则文件 `project_rules.md`

项目的”分析宪法”，**强制约束**所有分析。内容包括：
- 数据字典：字段业务含义、取值范围、单位、特殊值（如 0 表示缺失）。
- 分析规范：显著性阈值（默认 0.05）、相关性方法偏好（Pearson/Spearman）、模型选择优先级、输出风格（结论+方法说明）。
- 业务逻辑规则：如”订单状态为 REFUND 行必须排除”、”ARPU 分母为月活跃用户”。
- 安全规则：需脱敏的列名或模式。

Agent 在意图分析前**必须读取**此文件，注入 Planner 和 Insight Engine 提示。用户可通过对话修改，例如”修改项目规则：显著性阈值改为 0.01”，Agent 更新文件并立即生效。

#### 第二层：领域知识文件 `domain_knowledge.yaml`

领域知识包的文件载体，提供**推荐做法**和业务背景，激活时生效。结构：
```yaml
domain: ecommerce
indicators:
  GMV:
    description: “总交易额”
    formula: “商品数量 × 单价”
    exclude_conditions: “order_status = 'CANCEL'”
  conversion_rate:
    description: “购买转化率”
    formula: “下单用户数 / 访问用户数”
analysis_rules:
  - “归因分析优先使用SHAP值，并解读最相关特征的业务意义”
  - “时间序列预测默认周期7天，月度数据自动调整为月度模式”
common_pitfalls:
  - “数据中 channel 前缀为 'test_' 的为测试渠道，需排除”
learned_patterns:   # 由经验回路自动填充，可手动管理
  - pattern: “促销结束后3天内复购率异常下降”
    confidence: 0.8
    source: “2025Q2大促分析”
    status: “confirmed”
```

#### 第三层：经验日志文件 `experience_log.yaml`

经验演化的”记忆库”，Agent 自动写入，**用户可审核/编辑/删除**。每一条经验：
```yaml
- id: exp_042
  created: “2026-04-10”
  domain: “gaming”
  pattern: “新手7日留存与关卡3通关率呈强正相关(Spearman 0.75)”
  evidence:
    analysis_id: “session_2026_04_10_001”
    method: “correlation_analysis + segmentation”
  confidence: 0.7
  status: “draft”          # draft / confirmed / deprecated
  confirmed_by: null
  corrections: []
  source_session_id: “sess_abc123”  # ★V4.0 溯源标记
```
Agent 只采用 `status=confirmed` 且 `confidence > 0.5` 的经验作为分析参考。

#### 6.1.1 三层关系与边界
- **全局知识**：强制约束，最高优先级，所有会话始终可见。
- **对象知识**：绑定对象时可见，对象级深度合并到全局之上。
- **会话知识**：当前会话始终可见，合并到全局+对象之上。**★V4.0新增**。
- **优先级**：会话 > 对象 > 全局（同 key 时高层覆盖低层）。

#### 6.1.2 用户管理接口
- 对话式管理：”记住：ARPU = revenue/active_user” → 写入项目规则。
- 直接编辑文件，Agent 检测后自动重载。
- 标记经验：”这个发现很重要，保存到领域知识” → 提升为领域知识。
- **★V4.0** `/bind <object>` → 将会话知识提升到对象知识，后续其他会话绑定该对象时也可见。
- **★V4.0** `/unbind` → 知识保留在对象中，会话回到自由模式。

### 6.2 经验生命周期与迭代规则

知识迭代遵循“生成→验证→固化→纠错”生命周期，由 Agent 驱动，用户决定。

#### 6.2.1 生成（Draft）

- 每次报告/分析完成后，Insight Engine 附加”经验提取”步骤。
- 选择具有统计显著性、非平凡、可能跨数据复用的发现。
- 以 `status: draft` 写入 `experience_log.yaml`，初始 `confidence` 基于效应量和显著性（0.5~0.8）。

**提取过滤条件**（★New）：

并非所有发现都值得提取。仅当满足以下**任一**条件时才写入经验日志：
- 效应量超过阈值（Cohen's d > 0.5 或相关系数 > 0.6）
- 与已有 `confirmed` 经验矛盾
- 用户明确要求”记住这个发现”
- 涉及 Domain Pack 中标记为”关键指标”的分析

#### 6.2.2 验证与积累

- 同一模式在不同分析中再次出现，Agent 自动提高 `confidence`（+0.1，上限 0.9）。
- 当 `confidence ≥ 0.7` 时，Agent 在分析中主动引用该经验，并注明出处。
- 超过 6 个月未验证，`confidence` 每月衰减 0.05。

**衰减速率可配置**（★New）：

衰减参数作为 Domain Pack 的可配置参数，不同领域使用不同衰减策略：

```yaml
# domain_knowledge.yaml
experience_decay:
  grace_period_months: 3        # 前3个月不衰减
  monthly_decay: 0.08           # 每月衰减0.08（电商变化快）
  retire_threshold: 0.3         # 低于0.3自动废弃
```

未配置时使用默认值：grace_period=6, monthly_decay=0.05。

#### 6.2.3 固化（Confirmed）

- 用户直接确认：说“记住这个结论” → `status` 改为 `confirmed`，`confidence` 提升至 0.95。
- 三次独立点赞（👍）同一经验 → Agent 提议“是否固化为项目知识？”，用户确认后生效。
- 手动在 `experience_log.yaml` 中将状态改为 `confirmed`。

#### 6.2.4 纠错与淘汰

- 用户指出错误（例如“退款率上升与促销无关，因为支付系统故障”）：
  1. 原经验 `status` 改为 `deprecated`。
  2. 创建纠正经验，`confidence` 0.8，关联原 ID。
  3. 降低依赖该经验的后续洞察权重。
- 冲突检测：新自动经验与已有 `confirmed` 经验冲突时，立即触发 `ask_user_question`，列出冲突双方，由用户裁决，禁止自行覆盖。

#### 6.2.5 跨领域处理

- 经验默认记录所属领域。切换领域时，旧领域经验仅作背景参考，Agent 会说明“在 XXX 领域曾出现类似模式，但当前领域可能不同”。
- 用户可将领域改为 `general` 使其跨领域生效。

#### 6.2.6 安全限制

- 自动提取经验不得包含原始数据记录或个人身份信息，仅保留统计模式和结论。
- 所有经验变动都记录在文件版本历史中，支持回滚。

---

## 七、附录：监控规则配置模板

用户在对话中设定监控规则时，Agent 将其转化为如下结构：
```yaml
monitoring_rules:
  - id: mon_001
    name: "销售异常波动预警"
    data_source: "sales.csv"  # 或 SQL 连接字符串 (预留)
    metric: "daily_sales"
    frequency: "0 9 * * *"   # 每天9点
    condition:
      type: "std_dev"
      window: 30            # 过去30天
      std_multiplier: 2     # 2个标准差
      deseasonalize: true   # ★New：先去季节性再检测异常
      deseason_method: "stl" # stl / moving_average
    notification: ["email", "in_app"]
    enabled: true
```

**去季节性检测**（★New）：

当 `deseasonalize: true` 时，监控引擎在执行异常检测前，先调用 `analyze_time_series` 的 STL 分解获取季节性成分，对残差序列做 `std_dev` 检测。避免将周期性波动（如周末DAU天然下降）误判为异常。

监控引擎根据规则触发微型分析流程，生成预警卡片推送。
