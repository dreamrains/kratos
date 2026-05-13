# Data Agent 全面优化计划（详细实施版）

## 问题全清单

### 一、会话设计（3 个问题）

| # | 问题 | 严重度 | 阶段 |
|---|------|--------|------|
| S-1 | 意图分类过于依赖关键词匹配，覆盖不了自然语言 | 高 | Phase 1 |
| S-2 | conversation 模式无工具，无法查询 evidence_records | 中 | Phase 3 |
| S-3 | 会话恢复时 analysis_state 与 project_name 可能不一致 | 低 | Phase 4 |

### 二、工具设计（4 个问题）

| # | 问题 | 严重度 | 阶段 |
|---|------|--------|------|
| T-1 | 工具参数大量使用 string 类型传递 JSON | 高 | Phase 2 |
| T-2 | 工具描述不够 LLM-friendly | 中 | Phase 2 |
| T-3 | 工具粒度不均匀，缺少轻量自动探索工具 | 中 | Phase 2 |
| T-4 | ToolCapability 元数据设计完善但几乎未被利用 | 中 | Phase 1 |

### 三、工具调用（3 个问题）

| # | 问题 | 严重度 | 阶段 |
|---|------|--------|------|
| C-1 | 错误恢复策略机械重复 | 高 | Phase 1 |
| C-2 | 工具执行是串行的 | 低 | Phase 4 |
| C-3 | 工具分组激活过于保守 | 中 | Phase 1 |

### 四、数据分析流程（4 个问题）

| # | 问题 | 严重度 | 阶段 |
|---|------|--------|------|
| F-1 | Playbook 选择用关键词匹配 | 高 | Phase 3 |
| F-2 | 分析流程缺乏自适应回退 | 中 | Phase 3 |
| F-3 | 数据加载后缺少主动洞察 | 高 | Phase 2 |
| F-4 | 分析结果缺乏可信度校准 | 中 | Phase 3 |

### 五、提示词设计（3 个问题）

| # | 问题 | 严重度 | 阶段 |
|---|------|--------|------|
| P-1 | prompt 信息注入过多，信噪比低 | 中 | Phase 1 |
| P-2 | AGENT_ANALYSIS 和 AGENT_ANALYSIS_ENGINE 信息重复 | 低 | Phase 1 |
| P-3 | 缺少用户技术水平自适应 | 低 | Phase 4 |

### 六、Agent 能力（4 个问题）

| # | 问题 | 严重度 | 阶段 |
|---|------|--------|------|
| A-1 | 缺乏主动性和预判能力 | 中 | Phase 2 |
| A-2 | 缺乏跨会话学习能力 | 中 | Phase 4 |
| A-3 | 多数据集支持薄弱 | 中 | Phase 4 |
| A-4 | 输出格式控制不足 | 低 | Phase 4 |

---

## Phase 1：架构层地基

### 1.1 意图分类升级 [S-1]

**目标文件：** `src/data_agent/agent/intent.py`, `src/data_agent/agent/llm_intent.py`

**当前问题：**
- `plan_turn_intent` 中 ~90 个关键词做 if-elif 链匹配
- `_try_llm_classify` 只在所有关键词都不匹配时才触发
- 无法覆盖自然语言表达的多样性

**改造方案：**

1. **重构 `plan_turn_intent` 为分层架构：**

```python
def plan_turn_intent(user_input: str, session_context: str = "") -> TurnIntent:
    text = (user_input or "").lower().strip()
    data_state = infer_data_state(session_context)

    # Layer 1: 快速规则 — 只处理明确、无歧义的模式
    fast_result = _try_fast_path(text, data_state)
    if fast_result is not None and fast_result.clarity == "clear":
        return fast_result

    # Layer 2: LLM 语义分类 — 处理所有模糊/不明确的输入
    llm_result = _try_llm_classify(text, session_context)
    if llm_result is not None:
        intent_type, ambiguities = llm_result
        return TurnIntent(
            intent_type=intent_type,
            clarity="vague" if ambiguities else "clear",
            data_state=data_state,
            analysis_stage=_stage_for(intent_type, data_state),
            recommended_action=_action_for(intent_type, data_state),
            reason="LLM语义分类",
            ambiguities=ambiguities,
        )

    # Layer 3: fallback — 保留快速规则中 vague 的结果，或默认兜底
    if fast_result is not None:
        return fast_result
    return _default_fallback(data_state)
```

2. **精简 `_try_fast_path`：** 只保留高置信度规则
   - 问候/致谢/确认语（短输入精确匹配）
   - "报告"/"完整分析"等明确指令
   - "导出"/"汇总"等明确操作词
   - 移除中间灰色地带的规则（交给 LLM 处理）

3. **升级 `llm_intent.py`：**
   - 改为中文 prompt（与系统 prompt 语言一致）
   - 增加 8-10 个 few-shot 示例覆盖常见场景
   - 增加超时到 8s（语义分类需要更多推理）
   - 增加输入长度校验（超短输入直接走快速规则）

4. **触发条件变更：**
   - 快速规则返回 `clarity="clear"` → 直接使用，不调 LLM
   - 快速规则返回 `clarity="vague"` 或未命中 → 调 LLM

**验证方式：**
- 单元测试：准备 50+ 条中文测试输入，覆盖各种意图
- 对比测试：新旧版本对比分类准确率
- 回归测试：确保现有会话流程不受影响

---

### 1.2 Prompt 架构重构 [P-1, P-2]

**目标文件：** `src/data_agent/agent/prompts.py`

**当前问题：**
- `AGENT_ANALYSIS` 和 `AGENT_ANALYSIS_ENGINE` 有信息重复（工具选择规则、分析流程）
- Mermaid reference 无论是否需要可视化都注入
- knowledge 三个块分开注入，标签噪音多

**改造方案：**

1. **合并 `AGENT_ANALYSIS` + `AGENT_ANALYSIS_ENGINE` 为 `AGENT_ANALYSIS_CORE`：**

```
AGENT_ANALYSIS_CORE = """
角色定义 + 分析流程5步（合并去重）
分析策略表（从 ENGINE 移入）
多视角思考（从 ENGINE 移入）
工具选择规则（合并两处）
输出质量要求
回复格式
复杂度自适应
上下文复用规则
数据粒度约束
模糊意图引导
任务规划规则
"""
```

2. **提取共享策略块 `AGENT_STRATEGY_TABLE`：**
   - 供 analysis 和 guidance 模式共享
   - guidance 模式注入策略表用于推荐分析方向
   - analysis 模式注入完整策略表 + 角色定义

3. **按需注入优化：**
   - Mermaid reference：只在 analysis/quick/guidance 模式注入，conversation 不注入
   - knowledge 块：rules + domain + experience 合并为单个 `<project_knowledge>` 块
   - skill_instructions：只在有 loaded skills 时注入

4. **`build_system_prompt` 重构：**
```python
def build_system_prompt(...):
    # 1. 选择基础模板
    # 2. 注入共享策略（guidance/analysis 模式）
    # 3. 按需注入 context 块
    # 4. 注入 turn_intent prompt
```

**验证方式：**
- 对比重构前后的 system prompt 长度（目标减少 20-30%）
- 功能回归测试：确保四种模式行为不变

---

### 1.3 错误恢复体系 [C-1, T-4]

**目标文件：**
- `src/data_agent/tools/registry.py`（格式化错误结果）
- `src/data_agent/agent/execution_control.py`（增强 recovery_hint_for_error）
- 各工具文件（补充 recovery_hint 和 fallback_tools）

**改造方案：**

1. **工具级 recovery_hint 补全：** 在 `@registry.register` 中为每个工具添加

```python
# 示例：为 analyze_time_series 添加
@registry.register(
    name="analyze_time_series",
    description="...",
    recovery_hint=(
        "时间序列分析失败时：\n"
        "1. 检查 date_col 是否为日期类型（用 describe_dataset 查看）\n"
        "2. 检查 value_col 是否为数值类型\n"
        "3. 确保数据非空且已排序\n"
        "4. 如果数据点太少（<3），使用 distribution_analysis 替代"
    ),
    capability=_cap(
        ...,
        fallback_tools=["distribution_analysis", "run_python"],
    ),
)
```

需要补充的工具列表（按优先级）：
- `analyze_time_series` — 检查日期/数值列
- `correlation_analysis` — 检查数值列数量
- `compare_periods` — 检查时间范围
- `transform_data` — 检查操作参数
- `load_data` — 检查文件路径和格式
- `create_chart` — 检查图表参数
- `forecast` — 检查数据量和时间列

2. **Registry 级异常匹配增强：**

在 `registry.py` 的 `format_result` 方法中：

```python
def format_result(self, name: str, result: ToolResult) -> str:
    output = result.to_cli()
    if output.startswith('{"error":'):
        # 1. 尝试工具级 recovery_hint
        tool = self._tools.get(name)
        if tool and tool.recovery_hint:
            return f"{output}\n[恢复建议] {tool.recovery_hint}"

        # 2. 降级到异常类型匹配
        error_type = _classify_error(output)
        hint = _ERROR_HINTS.get(error_type, _DEFAULT_RECOVERY_HINT)

        # 3. 添加 fallback 工具推荐
        if tool and tool.capability and tool.capability.fallback_tools:
            fallbacks = ", ".join(tool.capability.fallback_tools)
            hint += f"\n替代工具: {fallbacks}"

        return f"{output}\n{hint}"
    return output
```

3. **异常类型分类器：**

```python
def _classify_error(error_json: str) -> str:
    """从错误 JSON 中提取异常类型"""
    try:
        data = json.loads(error_json)
        msg = data.get("error", "").lower()
    except:
        msg = error_json.lower()

    if "not found" in msg or "不存在" in msg or "missing" in msg:
        return "missing_data"
    if "column" in msg and ("not" in msg or "不" in msg):
        return "missing_column"
    if "type" in msg or "类型" in msg or "cannot" in msg:
        return "type_mismatch"
    if "timeout" in msg or "超时" in msg:
        return "timeout"
    if "parameter" in msg or "参数" in msg or "invalid" in msg:
        return "invalid_parameter"
    return "unknown"
```

4. **移除 loop.py 中的通用硬编码恢复建议：**

`loop.py` 中 `_process_tool_calls` 和 `_loop_impl` 中重复的 4 条建议块
→ 改为调用 `registry.format_result(name, tool_result)`

**验证方式：**
- 单元测试：模拟各种错误类型，验证恢复建议正确性
- 集成测试：故意传入错误参数，确认 LLM 收到有用的恢复建议

---

### 1.4 工具分组与激活策略 [C-3]

**目标文件：** `src/data_agent/agent/analysis_flow_controller.py`

**改造方案：**

1. **协商阶段增加工具可见性：**

```python
# intent_negotiation 模式当前只激活 knowledge
# 改为同时激活 eda 的轻量工具
elif intent.intent_type in ("intent_negotiation", "data_requirement"):
    groups.update({"knowledge", "eda"})
```

2. **基于数据特征动态激活：**

```python
def _activate_from_data_signals(self, registry, state, dataset_profile: str) -> None:
    """根据已加载数据的特征激活相关工具分组"""
    profile_lower = dataset_profile.lower()
    if any(kw in profile_lower for kw in ("date", "时间", "time")):
        registry.expand_from_tool_call("analyze_time_series")  # 激活 eda
    if any(kw in profile_lower for kw in ("dimension", "维度", "category")):
        registry.expand_from_tool_call("compare_periods")
    if any(kw in profile_lower for kw in ("funnel", "漏斗", "conversion")):
        registry.expand_from_tool_call("funnel_analysis")
```

**验证方式：**
- 测试协商阶段能否访问 quick_profile / detect_data_quality
- 测试数据特征驱动的工具激活

---

## Phase 2：工具层能力提升

### 2.1 工具参数类型升级 [T-1]

**目标文件：**
- `src/data_agent/tools/interaction.py`
- `src/data_agent/tools/data_transform.py`
- 其他需要补充 description 的工具文件

**改造方案：**

#### 2.1.1 `ask_user_question` 参数结构化

```python
parameters={
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "要问的问题（单问题模式）",
        },
        "options": {
            "type": "array",
            "description": "预置选项列表，2-4 个",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "选项标签"},
                    "description": {"type": "string", "description": "选项说明"}
                },
                "required": ["label"]
            }
        },
        "multi_select": {
            "type": "boolean",
            "description": "是否允许多选",
            "default": False
        },
        # ... 其他参数保持不变
    },
}
```

函数签名改为接收 list 类型：
```python
def ask_user_question(
    question: str = "",
    options: list | None = None,  # 从 str 改为 list[dict]
    multi_select: bool = False,
    ...
)
```

#### 2.1.2 `transform_data` 参数结构化

从 `operation + params(string JSON)` 改为 `operation + 具体参数`：

```python
@registry.register(
    name="transform_data",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "数据集名称"},
            "operation": {
                "type": "string",
                "enum": ["filter", "select", "rename", "sort",
                         "group_aggregate", "resample", "pivot", "merge"],
            },
            "save_as": {"type": "string", "description": "保存为新数据集名称"},
            # filter 参数
            "condition": {"type": "string", "description": "筛选条件（pandas query 语法）"},
            # select 参数
            "columns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要选择的列名列表",
            },
            # rename 参数
            "rename_mapping": {
                "type": "object",
                "description": "重命名映射 {旧列名: 新列名}",
                "additionalProperties": {"type": "string"}
            },
            # sort 参数
            "sort_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "排序列名",
            },
            "ascending": {
                "type": "boolean",
                "description": "升序/降序",
                "default": True
            },
            # group_aggregate 参数
            "group_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "分组列名",
            },
            "aggregations": {
                "type": "array",
                "description": "聚合规则",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "functions": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["sum","mean","count","min","max","median","std"]},
                        }
                    },
                    "required": ["column", "functions"]
                }
            },
            # resample 参数
            "date_col": {"type": "string", "description": "时间列名"},
            "freq": {
                "type": "string",
                "enum": ["D", "W", "ME", "QE", "YE"],
                "description": "重采样频率",
            },
            "resample_agg": {
                "type": "object",
                "description": "重采样聚合 {列名: 聚合函数}",
                "additionalProperties": {"type": "string"}
            },
            # merge 参数
            "other_name": {"type": "string", "description": "要合并的数据集名"},
            "merge_on": {"type": "string", "description": "合并键列名"},
            "merge_how": {
                "type": "string",
                "enum": ["inner", "left", "right", "outer"],
                "default": "inner"
            },
            # pivot 参数
            "pivot_index": {"type": "string", "description": "pivot 索引列"},
            "pivot_columns": {"type": "string", "description": "pivot 列名字段"},
            "pivot_values": {"type": "string", "description": "pivot 值字段"},
            "melt_id_vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "melt 操作的 ID 变量列",
            },
            "melt_value_vars": {
                "type": "array",
                "items": {"type": "string"},
                "description": "melt 操作的值变量列",
            },
            # 向后兼容
            "params": {"type": "string", "description": "[兼容旧版] JSON 格式参数"},
        },
        "required": ["name", "operation"],
    },
)
```

函数内部逻辑按 operation 分发到各参数，同时保留 `params` 的向后兼容。

#### 2.1.3 其他工具 schema 补全

为所有工具的自动生成参数补充 description：
- `load_data`: source → "数据文件路径（CSV/Excel/JSON）"
- `analyze_time_series`: name → "数据集名称"
- `create_chart`: 补充 chart_type 的 enum
- 所有 name 参数统一描述为 "数据集名称"

---

### 2.2 工具描述优化 [T-2]

**改造原则：** 从"功能介绍"改为"决策规则"

改造模板：
```
description=(
    "{一句话功能描述}。"
    "使用场景：{什么时候用}。"
    "不适用场景：{什么时候不用}。"
    "参数说明：{关键参数的简要说明}。"
    "常见错误：{最容易出错的地方}。"
)
```

优先改造高频工具（按调用频率排序）：
1. `load_data`
2. `transform_data`
3. `analyze_time_series`
4. `create_chart`
5. `quick_profile`
6. `compare_periods`
7. `correlation_analysis`
8. `top_n`

---

### 2.3 数据加载主动洞察 [F-3, A-1]

**目标文件：** `src/data_agent/tools/data_io.py`, 新增 `src/data_agent/tools/auto_insight.py`

**改造方案：**

1. **新增 `auto_insight.py` 模块：**

```python
def auto_insight_scan(df: pd.DataFrame, name: str) -> dict:
    """数据加载后自动洞察扫描"""

    rows = len(df)

    # 自适应采样
    if rows > 1_000_000:
        sample_df = df.sample(frac=0.01, random_state=42)
        scan_mode = "sampled_1pct"
    elif rows > 100_000:
        sample_df = df.sample(frac=0.1, random_state=42)
        scan_mode = "sampled_10pct"
    else:
        sample_df = df
        scan_mode = "full"

    result = {
        "scan_mode": scan_mode,
        "data_identity": _identify_data(sample_df, name),
        "field_semantics": _classify_field_semantics(sample_df),
        "data_health": _assess_health(sample_df),
        "business_observations": _generate_observations(sample_df, scan_mode),
    }
    return result
```

2. **数据身份识别 `_identify_data`：**
   - 调用已有的 `_match_theme` 推断行业
   - 调用已有的 `_detect_grain` 推断粒度
   - 调用已有的 `_detect_time_range` 推断时间范围
   - 新增：数据新鲜度评估

3. **字段语义分类 `_classify_field_semantics`：**
   - 复用已有的 `_classify_columns` 逻辑
   - 输出结构化分类：ID / 时间 / 维度 / 指标 / 标签

4. **数据健康度 `_assess_health`：**
   - 关键列缺失率（>20% 标记警告）
   - 数据量级评估（是否满足统计最低要求）
   - 常量列/重复率/异常值占比

5. **业务级观察 `_generate_observations`：**
   - 时间趋势方向（有数值+时间列时）
   - TOP 维度贡献度（有维度+数值列时）
   - 分布特征（偏度、集中度）
   - 最多 3 条，每条格式：观察 + 数据支撑 + 建议关注点

6. **集成到 `load_data`：**

```python
# 在 load_data 的 report_parts 构建中，替换现有的
# quick_profile + interpret_dataset 为：
try:
    from data_agent.tools.auto_insight import auto_insight_scan, format_auto_insight
    insight = auto_insight_scan(df, name)
    report_parts.append(f"\n[data_insight]\n{format_auto_insight(insight)}\n[/data_insight]")
except Exception:
    pass  # 洞察失败不影响数据加载
```

7. **输出格式示例：**

```
📊 数据快速洞察（2,450 行 × 12 列）

数据身份：电商行业，日级聚合数据
时间范围：2024-01-01 ~ 2024-03-31（91天）
关键指标：gmv, order_count, avg_price
维度：channel, region, product_category

数据健康：
  ✅ 关键指标无缺失
  ⚠️ region 列缺失 8.2%
  ℹ️ 数据已更新至 31 天前

值得关注：
  1. gmv 整体呈上升趋势（月环比 +15%），但最近 7 天出现明显下滑（-8%）
  2. channel_A 贡献了 62% 的 gmv，集中度较高，建议关注渠道风险
  3. order_count 与 gmv 高度相关（r=0.94），客单价相对稳定
```

**验证方式：**
- 准备不同规模的测试数据集（100行/10K行/1M行）
- 验证自适应采样正确触发
- 验证洞察内容准确性和实用性
- 验证加载时间增量在可接受范围内

---

## Phase 3：分析流程强化

### 3.1 Playbook 语义化选择 [F-1]

**目标文件：** `src/data_agent/agent/method_playbooks.py`, 新增 `src/data_agent/agent/llm_playbook.py`

**改造方案：**

1. **新增 LLM playbook 选择模块 `llm_playbook.py`：**
   - 输入：用户文本 + 数据特征（从 interpret_dataset 提取）
   - 输出：primary_playbook_id + supporting_ids + selection_reason
   - 使用主模型，超时 8s
   - 提供 playbook 列表作为 few-shot 上下文

2. **修改 `select_playbooks`：**
   - 保留关键词快速路径（funnel/forecast 等明确场景）
   - 模糊场景走 LLM 选择
   - LLM 结果与数据特征交叉验证（避免推荐数据不支持的方向）

3. **引入"复合 playbook"概念：**
   - 用户意图可能匹配多个 playbook
   - 允许 primary + 2 个 supporting 的组合
   - supporting 的权重根据数据特征动态调整

### 3.2 分析流程自适应回退 [F-2]

**目标文件：** `src/data_agent/agent/analysis_state.py`, `src/data_agent/agent/analysis_flow_controller.py`

**改造方案：**

1. **在 `AnalysisSessionState` 增加回退条件检测：**
```python
def check_regression_triggers(self, tool_name: str, tool_result: str) -> str | None:
    """检查是否需要回退到前一个阶段"""
    # 数据质量问题 → 回退到 scope
    if tool_name == "detect_data_quality" and '"severity": "block"' in tool_result:
        self.stage = "scope"
        return "数据质量问题严重，需要重新定义分析范围"

    # 数据不支持所选方法 → 回退到 plan
    if "insufficient" in tool_result.lower() or "数据点太少" in tool_result:
        self.stage = "plan"
        return "数据不支持当前方法，需要调整分析计划"

    return None
```

2. **在 controller 的 `prepare_turn` 中检查回退信号**

3. **在 `analysis_state_summary` 中暴露回退历史**

### 3.3 可信度校准 [F-4]

**目标文件：** `src/data_agent/agent/prompts.py`, `src/data_agent/tools/analysis_flow.py`

**改造方案：**

1. **在 ANALYSIS prompt 中增加校准规则：**

```
## 置信度校准规则（强制）
- 样本量 < 30：置信度必须标"低"，并注明样本不足
- p > 0.05：必须标注"统计不显著"，不得使用"显著"等词
- 无对照组/无随机化：禁止因果性断言，只能使用"相关性"表述
- 数据为聚合粒度：禁止个体级结论
- 缺失率 > 20% 的列参与分析：必须标注数据限制
```

2. **在 `record_evidence_record` 工具中增加自动校验：**
   - 检查样本量是否满足最低要求
   - 检查置信度声明是否与统计量一致
   - 不一致时自动降级置信度并添加警告

### 3.4 Conversation 模式增强 [S-2]

**目标文件：** `src/data_agent/agent/prompts.py`, `src/data_agent/agent/analysis_flow_controller.py`

**改造方案：**

1. **conversation 模式允许访问只读查询工具：**
   - 新增工具组 `conversation_query`，包含 `get_analysis_summary`
   - `get_analysis_summary`：读取当前 analysis_state 的 evidence_records + insight_records，返回结构化摘要
   - 不暴露任何写入或分析工具

2. **在 `build_system_prompt` 中 conversation 模式增加：**
```
可用工具：get_analysis_summary（查看已有分析结果摘要）
```

---

## Phase 4：Agent 能力补全

### 4.1 会话恢复修复 [S-3]

**目标文件：** `src/data_agent/agent/loop.py`

在 `restore_object_context` 中：
```python
if obj_name:
    # 同步刷新 analysis_state
    from data_agent.agent.analysis_state import load_analysis_state
    self.context.analysis_state = load_analysis_state(self.session_id, obj_name)
```

### 4.2 多数据集支持增强 [A-3]

- 增强 `interpret_dataset`：检测多数据集时自动推荐关联分析
- 改善 `transform_data` merge 操作的工具描述，引导 LLM 主动使用
- prompt 中增加多数据集分析策略

### 4.3 跨会话学习 [A-2]

- experience_log 自动提取（不依赖用户确认）
- 只提取"数据特征 → 推荐分析方法"的模式，不包含具体结论
- 下次加载类似数据时自动注入推荐
- 长期迭代方向，Phase 4 只做基础框架

### 4.4 输出格式自适应 [A-4, P-3]

- 在 AgentContext 中新增 `user_proficiency: str` 字段
- 通过用户提问中的术语使用频率自动检测水平
- prompt 中根据水平调整输出详细度
- report 工具支持 `detail_level` 参数

### 4.5 工具并行执行 [C-2]

- 在 `_loop_impl` 中检测独立工具调用
- 使用 ThreadPoolExecutor 并行执行
- 结果按 tool_call_id 顺序组装
- 设置合理的并行度上限（3-4）

---

## 实施顺序总览

```
Phase 1（架构层）→ Phase 2（工具层）→ Phase 3（流程层）→ Phase 4（能力层）

每阶段内部按依赖顺序实施：
  Phase 1: 1.1 → 1.2 → 1.3 → 1.4
  Phase 2: 2.3 → 2.1 → 2.2（先做 auto_insight，再做参数和描述改造）
  Phase 3: 3.1 → 3.2 → 3.3 → 3.4
  Phase 4: 4.1 → 4.2 → 4.3 → 4.4 → 4.5

每个子项完成后独立运行测试验证。
```
