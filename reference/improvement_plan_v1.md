# 数据分析 Agent 改进方案 V1

> **基于**：PRD V3.0 架构审视与讨论
> **前提约束**：所有设计需同时考虑 CLI 与 Web GUI 双端适配
> **状态**：待实施

---

## 一、架构级改动（影响整体骨架）

### 1.1 展示层抽象（Presentation Layer）

**问题**：当前设计假设用户交互通过 CLI 文本流完成。`ask_user_question` 为同步阻塞、工具返回值为纯字符串、命令为硬编码 if/else。这些假设在 Web GUI 下全部不成立。

**改动**：在 Agent Loop 与用户之间插入展示层抽象。

```
                    ┌──────────────────────────────┐
                    │      Presentation Layer       │
                    │                               │
                    │  CLIAdapter          WebAdapter│
                    │  - stdin/stdout      - REST   │
                    │  - 文件路径展示      - SSE/WS │
                    │  - 阻塞式确认        - 卡片渲染│
                    │  - 斜杠命令          - UI按钮 │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │      Command Registry         │
                    │  register(name, handler)       │
                    │  CLI: /command 触发            │
                    │  Web: API endpoint 触发        │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │       Agent Loop              │
                    │       (suspendable)            │
                    └──────────────────────────────┘
```

#### 1.1.1 Agent Loop 可暂停/恢复

当前 `agent_loop` 为纯同步循环。Web 场景需要 Agent 在 `ask_user_question` 处暂停，持久化状态，等用户回调后恢复。

**设计**：

```python
# Agent Loop 执行结果有两种：
class LoopResult:
    pass

class FinalResponse(LoopResult):
    """Agent 完成回答，直接输出"""
    content: str

class SuspendedForConfirmation(LoopResult):
    """Agent 需要用户确认，暂停等待"""
    suspension_id: str
    confirmation_request: dict  # question, options, context 等
    snapshot: dict              # messages + 执行上下文的序列化快照

def resume_loop(suspension_id: str, user_response: str) -> LoopResult:
    """用户回复后恢复 Agent Loop"""
    snapshot = load_suspension(suspension_id)
    # 将 user_response 作为 tool_result 追加，继续循环
    ...
```

**CLI 侧**：`SuspendedForConfirmation` 直接打印问题、读 stdin、调用 `resume_loop`。用户无感知。

**Web 侧**：返回 `SuspendedForConfirmation` 的 JSON 给前端，前端渲染为确认卡片。用户操作后通过 API 调用 `resume_loop`。

** Suspension 存储**：复用现有 `sessions/{id}/` 目录，新增 `suspension_{id}.json`。

#### 1.1.2 工具返回值结构化

当前工具返回 `str`。改为返回结构化对象，由展示层决定如何渲染。

```python
@dataclass
class ToolResult:
    summary: str                           # CLI 展示用
    data: dict | None = None               # Web 展示用（可选）
    artifacts: list[ArtifactRef] | None = None  # 输出物引用

    def to_cli(self) -> str:
        return self.summary

    def to_web(self) -> dict:
        return {"summary": self.summary, "data": self.data, "artifacts": self.artifacts}
```

**示例**：`create_chart()` 返回值

```
CLI 展示：📊 图表已保存至 sessions/abc/charts/DAU_trend.html
Web 展示：{data: {plotly_spec: {...}}, artifact_path: "...", type: "chart"}
          → 前端直接用 Plotly.js 渲染内嵌图表
```

**迁移策略**：工具核心逻辑不变，只在最外层包装。现有返回 `str` 的工具自动升级为 `ToolResult(summary=原返回值)`。

#### 1.1.3 命令注册表

将 REPL 中的硬编码命令抽取为注册表模式：

```python
class CommandRegistry:
    _commands: dict[str, CommandHandler] = {}

    def register(self, name: str, handler: Callable, description: str):
        self._commands[name] = CommandHandler(handler, description)

    def execute(self, name: str, args: str = "") -> str:
        return self._commands[name].handler(args)

# 注册
cmd.register("/report", handle_report, "生成完整分析报告")
cmd.register("/skill", handle_skill, "技能管理")
cmd.register("/sessions", handle_sessions, "会话列表")

# CLI 触发：用户输入 /report → cmd.execute("report")
# Web 触发：前端点击"生成报告"按钮 → API POST /command/report
```

#### 1.1.4 任务状态事件流

Web 前端需要实时展示 Task DAG 执行进度。在现有 TaskManager 基础上增加事件发射：

```python
class TaskEventEmitter:
    def __init__(self):
        self._subscribers: list[Callable] = []

    def subscribe(self, callback: Callable):
        self._subscribers.append(callback)

    def emit(self, event: TaskEvent):
        """任务状态变更时发射事件"""
        for cb in self._subscribers:
            cb(event)

# CLI 侧：订阅后打印到 stdout
# Web 侧：订阅后通过 SSE/WS 推送给前端
# 事件类型：task_created, task_started, task_completed, task_failed, dag_progress
```

#### 1.1.5 实施范围评估

| 改动项 | 影响范围 | V1 CLI 是否必须 | 说明 |
|--------|---------|-----------------|------|
| Agent Loop suspendable | `agent_loop` 核心循环 | **是** | CLI 下对用户透明，但代码结构需改 |
| ToolResult 结构化 | 所有工具的返回值 | **是** | 即使 CLI 也不用改工具逻辑，只包装 |
| 命令注册表 | REPL 命令分发 | **是** | 重构成本低，收益高 |
| 任务事件流 | TaskManager | **V1 可选** | CLI 下暂不需要，但接口先定义好 |

**原则**：V1 实现 suspendable + ToolResult + 命令注册表。事件流先定义接口，V2 Web 时实现。

---

## 二、数据就绪度管道（Data Readiness Pipeline）

### 2.1 设计思路

将现有 `load_data → auto_clean → describe_dataset → detect_data_quality` 扩展为连贯管道，末尾增加 `assess_readiness` 步骤。**不合并为一个大工具**，保持每步职责单一。

```
load_data(source)
    │
    ▼
auto_clean(df)                     ← 现有 L1.5，格式修复
    │  输出：clean_report
    │
    ▼
describe_dataset(df)                ← 现有 L1，schema 理解
    │  输出：field_types, datetime_range, row_count, key_candidates
    │
    ▼
detect_data_quality(df)             ← 现有 L1，质量检测
    │  输出：missing_rates, outliers, duplicates
    │
    ▼
assess_readiness(df, intent=None)   ← ★新增，分析就绪度评估
    │  输入：前三步的结果 + 可选的 intent
    │  输出：readiness_report（不阻塞，仅报告）
    │
    ▼
LLM 判断 → 是否需要 ask_user_question
```

### 2.2 `assess_readiness` 检查项

| 检查项 | 触发条件 | 严重级别 | 输出示例 |
|--------|---------|---------|---------|
| 时间粒度一致性 | datetime 列间隔不均匀或存在混合粒度 | ⚠ Warning | `"时间列date间隔不一致：87%为日级、13%为周级，建议统一后再做趋势分析"` |
| 样本量充足性 | intent 含预测/分类，行数 < 最低阈值 | ⚠ Warning | `"当前87行，预测建模建议≥200行，结果置信度可能较低"` |
| 关键列缺失预警 | 目标指标列缺失 > 30% | 🔴 Block | `"目标列revenue缺失率42%，归因分析结果不可靠"` |
| 常量/准常量列 | 列唯一值 ≤ 1 或方差 ≈ 0 | ℹ Info | `"列country仅含1个值CN，无法用于维度拆解"` |
| 多表关系提示 | 加载了多个 DataFrame 但未指定关联键 | ⚠ Warning | `"检测到2个DataFrame(orders, users)，未发现显式关联键"` |
| 指标定义缺失 | intent 中提到的指标在 project_rules 中无定义 | ⚠ Warning | `"指标'活跃用户'未在项目规则中定义，建议确认口径"` |
| 数据时效性 | 最新数据距今超过阈值（默认7天） | ℹ Info | `"数据最新日期2026-04-15，距今12天"` |

### 2.3 严重级别与后续行为

| 级别 | LLM 行为 | 是否阻塞分析 |
|------|---------|-------------|
| ℹ Info | 附在分析结果的方法说明中 | 否 |
| ⚠ Warning | 主动告知用户风险，继续分析 | 否（用户可选择中止） |
| 🔴 Block | 通过 `ask_user_question` 要求用户确认后继续 | 是（必须用户确认） |

### 2.4 与 Web GUI 的适配

- **CLI**：`assess_readiness` 输出直接打印为文本报告，LLM 用自然语言解读。
- **Web**：`readiness_report` 作为结构化数据返回前端，渲染为**数据就绪度仪表盘**：

```
┌─ Data Readiness ──────────────────────────┐
│ ✅ 数据加载完成          12,458 行 × 15列  │
│ ✅ 格式清洗              3列已自动修复     │
│ ⚠️ 时间粒度不一致        日级/周级混合     │
│ ✅ 关键列完整性          revenue 缺失率 2% │
│ ℹ️ 准常量列              country = CN     │
│                                           │
│ 综合评估：🟡 基本就绪（1项需关注）         │
└───────────────────────────────────────────┘
```

### 2.5 实施策略

- `assess_readiness` 作为独立的 L1 工具注册到 ToolRegistry。
- Planner 系统提示词中增加规则：**首次加载新数据集时，自动在 DAG 第一阶段编排 `assess_readiness`**。
- 后续对同一数据集的分析，跳过 `assess_readiness`（结果已缓存在 Session Context 中）。

---

## 三、功能级改进

### 3.1 Insight Engine：多假设竞争与排除声明 [P0]

**现状**：Driver 类型洞察只给出主驱动因子。

**改进**：对 Driver 和 Anomaly 类型洞察，要求列出被检验的候选因子及其排除理由。

**Insight Card 结构扩展**：

```json
{
  "type": "Driver",
  "title": "DAU下降12%主要归因于渠道A流量减少",
  "description": "...",
  "confidence": "high",
  "method": "SHAP归因分析 + 渠道维度下钻",
  "competing_hypotheses": [
    {
      "factor": "渠道A流量减少",
      "tested": true,
      "contribution": "65%",
      "excluded": false
    },
    {
      "factor": "版本v2.3更新",
      "tested": true,
      "contribution": "<3%",
      "excluded": true,
      "excluded_reason": "版本更新前后DAU无显著差异(t-test p=0.72)"
    },
    {
      "factor": "周末效应",
      "tested": true,
      "contribution": null,
      "excluded": true,
      "excluded_reason": "已通过STL季节性分解校正"
    }
  ],
  "evidence": {...}
}
```

**自然语言输出示例**：

> DAU下降12%主要归因于渠道A流量减少（贡献65%）。我们同时检验了版本更新（贡献<3%，无显著差异）和周末效应（已通过季节性分解校正排除），均非主要驱动因素。

**实现方式**：Insight Engine 的系统提示词增加指令，要求对 Driver/Anomaly 类型的洞察必须包含 `competing_hypotheses`。LLM 基于已有工具结果（correlation、attribution 等）推断候选因子。**不需要新增工具**。

**Web GUI 呈现**：洞察卡片增加可展开的"假设检验详情"区域。

### 3.2 Chat 模式轻量快答 [P1]

**现状**：所有问题都走完整的 Intent → Planner → DAG → Execute → Insight 流程。

**改进**：简单探索性问题先给"初步印象"，再问是否深入。

**实现**：在 Planner 系统提示词中增加规则：

```
分析意图分类规则：
- 如果用户问题为探索性描述（如"看一下最近的数据""DAU怎么样"），
  且不包含明确的归因/预测/比较请求，
  则生成轻量 DAG（describe_dataset + preview_data 或 analyze_time_series），
  返回初步观察后询问"是否需要深入分析？"
- 如果用户明确要求归因、预测、比较，或追问"为什么"，
  则生成完整 DAG。
```

**Web GUI 适配**：轻量快答渲染为"分析速览"卡片，附带"深入分析"按钮。

### 3.3 Report 模式双风格输出 [P1]

**现状**：报告输出为统一风格（结论+方法说明）。

**改进**：Report Generator 增加 `style` 参数，生成两种风格的输出物。

| 风格 | 目标用户 | 结构 |
|------|---------|------|
| `executive` | A类：业务/运营 | 1页执行摘要 + 关键发现 + 行动建议。方法说明极简（"基于SHAP归因"一句话带过） |
| `detailed` | B类：数据科学家 | 完整6章节。方法论附录含参数、诊断结果、局限性讨论 |

**实现**：同一组 Insight Cards 和图表，由两套不同的报告模板渲染。共享数据和图表，只是组织方式和详细程度不同。

**Web GUI 呈现**：报告页顶部提供 "Executive / Detailed" 切换标签，实时切换视图而不重新分析。

### 3.4 指标口径确认嵌入知识体系 [P2]

**现状**：`project_rules.md` 可定义指标口径，但 Agent 不会主动发现"未定义的指标"并引导用户定义。

**改进**：将口径确认嵌入 Intent Analyzer，而非独立的子流程。

**规则**：
1. Intent Analyzer 解析用户意图时，提取目标指标（如"DAU""活跃用户""转化率"）。
2. 在 `project_rules.md` 的数据字典中查找定义。
3. 若找到 → 直接使用，在方法说明中注明口径来源。
4. 若未找到 → 生成 `ask_user_question`：
   > "我在项目规则中没有找到'活跃用户'的定义。请问它的统计口径是？"
   > 1. 日登录用户（含重复登录）
   > 2. 日登录用户（去重）
   > 3. 自定义定义
5. 用户确认后 → 自动追加到 `project_rules.md` 的数据字典中。后续分析永久生效。

**Web GUI 适配**：口径确认渲染为指标定义卡片，附带"保存为项目规则"的选项。

### 3.5 经验提取过滤 [P2]

**现状**：PRD 设计为"每次分析完成后提取经验"，可能导致经验库被平庸发现淹没。

**改进**：增加提取过滤条件。

**过滤规则**（满足任一才提取）：
- 效应量超过阈值（Cohen's d > 0.5 或相关系数 > 0.6）
- 与已有 `confirmed` 经验矛盾
- 用户明确要求"记住这个发现"
- 涉及 Domain Pack 中标记为"关键指标"的分析

**实现**：Insight Engine 的经验提取步骤中，在写入 `experience_log.yaml` 前增加过滤判断。

### 3.6 监控异常检测去季节性 [P2]

**现状**：监控规则使用原始值的 `std_dev` 检测异常，不区分季节性波动。

**改进**：监控条件增加 `deseasonalize` 选项。

```yaml
monitoring_rules:
  - id: mon_001
    metric: "daily_sales"
    condition:
      type: "std_dev"
      window: 30
      std_multiplier: 2
      deseasonalize: true        # ★新增：先去季节性再检测异常
      deseason_method: "stl"     # stl / moving_average
```

**实现**：监控引擎在执行异常检测前，先调用 `analyze_time_series` 的 STL 分解获取季节性成分，对残差序列做 `std_dev` 检测。

### 3.7 置信度衰减可配置 [P3]

**现状**：经验衰减为统一参数（6个月后每月衰减 0.05）。

**改进**：衰减速率作为 Domain Pack 的可配置参数。

```yaml
# domain_knowledge.yaml
domain: ecommerce
experience_decay:
  grace_period_months: 3        # 前3个月不衰减
  monthly_decay: 0.08           # 每月衰减0.08（电商变化快）
  retire_threshold: 0.3         # 低于0.3自动废弃
```

```yaml
# 另一个领域
domain: finance_risk
experience_decay:
  grace_period_months: 12       # 金融模式较稳定
  monthly_decay: 0.03
  retire_threshold: 0.3
```

**默认值**：未配置时使用当前参数（grace_period=6, monthly_decay=0.05）。

---

## 四、优先级与实施路线

### 阶段一：架构基础（所有后续改进的前置条件）

| 序号 | 改进项 | 工作量 | 说明 |
|------|--------|--------|------|
| A1 | ToolResult 结构化 | 2天 | 包装现有工具返回值，不影响逻辑 |
| A2 | 命令注册表 | 1天 | 重构 REPL 命令分发 |
| A3 | Agent Loop suspendable | 3天 | 核心改动，CLI 下对用户透明 |
| A4 | Data Readiness Pipeline (`assess_readiness`) | 2天 | 新增 L1 工具 + Planner 集成 |

### 阶段二：核心体验提升

| 序号 | 改进项 | 工作量 | 依赖 |
|------|--------|--------|------|
| B1 | Insight 多假设竞争 [P0] | 2天 | 无（纯 prompt 改动） |
| B2 | Chat 轻量快答 [P1] | 1天 | 无（Planner prompt 改动） |
| B3 | Report 双风格输出 [P1] | 2天 | ToolResult 结构化（A1） |
| B4 | 指标口径确认 [P2] | 2天 | suspendable（A3） |

### 阶段三：完善与打磨

| 序号 | 改进项 | 工作量 | 依赖 |
|------|--------|--------|------|
| C1 | 经验提取过滤 [P2] | 1天 | 无 |
| C2 | 监控去季节性 [P2] | 2天 | 依赖监控引擎实现 |
| C3 | 置信度衰减可配置 [P3] | 1天 | 依赖多领域实际使用反馈 |

### Web GUI 阶段（独立于上述改进）

| 序号 | 改动项 | 依赖 | 说明 |
|------|--------|------|------|
| W1 | WebAdapter 实现 | A3 | REST API + SSE |
| W2 | 任务事件流 | A3 | TaskEventEmitter 的 Web 订阅者 |
| W3 | 前端组件 | W1, A1 | 图表内嵌、确认卡片、就绪度仪表盘、报告视图切换 |

---

## 五、对 PRD V3.0 的具体修订点

以下为需要在 PRD 中更新/新增的章节：

| PRD 章节 | 修订内容 |
|----------|---------|
| 4.2 架构图 | 在"Entry Modes"下方新增"Presentation Layer"层 |
| 4.4.1 Intent Analyzer | 增加"指标定义查找"步骤，未定义时触发 ask_user_question |
| 4.4.2 Planner | 增加"分析意图分类规则"（轻量 vs 完整 DAG） |
| 4.4.4 Insight Engine | 洞察卡片结构新增 `competing_hypotheses` 字段 |
| 4.4.8 Report Generator | 新增 `style` 参数（executive / detailed） |
| 4.5.1 L1 工具 | 新增 `assess_readiness()` 工具说明 |
| 4.5.1 工具返回值 | 新增 ToolResult 结构说明 |
| 4.6 ask_user_question | 新增 Suspension 机制说明 |
| 4.7 Task DAG | 新增 TaskEventEmitter 说明 |
| 4.16 REPL 命令 | 改为命令注册表模式说明 |
| 6.2.1 经验生成 | 新增过滤条件（效应量阈值、关键指标、矛盾检测） |
| 6.2.2 经验验证 | 衰减参数改为 Domain Pack 可配置 |
| 7. 附录 监控规则 | condition 新增 `deseasonalize` 和 `deseason_method` 参数 |
| ★新增章节 | 展示层抽象与双端适配规范 |
