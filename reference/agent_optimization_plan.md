# Agent 优化改进计划 v1.0

> 日期：2026-04-28
> 基线测试：内购数据.xlsx (248×13)，任务"按周/月汇总" → 25 轮、~110 万 tokens、RateLimitError 崩溃
> 目标：同等分析质量下，token 消耗降低 80%+，分析专业度显著提升

---

## 一、效率提升：工具按需加载 (P0)

### 1.1 工具分阶段加载机制

**问题**：51 个工具定义每轮发送，~3553 tokens/轮纯工具开销。

**方案**：将工具分为"始终可用"和"按需加载"两层。首轮发送核心工具集，后续根据 LLM 返回的工具调用意图动态补充。

```
始终可用（~12 个，~1500 tokens）:
  load_data, list_data, export_data      # 数据 IO
  describe_dataset, preview_data         # 数据理解（精简版）
  transform_data, derive_field           # 数据变换（增强版）
  run_python                             # 兜底
  ask_user_question                      # 交互
  create_chart                           # 可视化

按需加载（~39 个，分组激活）:
  eda:       analyze_time_series, correlation_analysis, distribution_analysis, ...
  ml:        regression_analysis, classification, forecast, shap_analysis
  stats:     ab_test, causal_analysis, attribution_analysis
  report:    generate_report, export_report_markdown, export_report_pdf
  clean:     suggest_column_types, apply_type_conversion, clean_data
  task:      task_create, task_update, task_get, task_list
  knowledge: show_project_rules, update_project_rules, ...
```

**激活规则**：
- 用户请求含"报告/完整分析/全面" → 激活 report + eda + task
- 用户请求含"预测/趋势" → 激活 eda + ml
- 用户请求含"比较/A-B/对比" → 激活 stats
- `describe_dataset` 发现数据质量问题 → 激活 clean
- 连续 2 次调用 `run_python` → 自动激活相关 eda/ml 工具

**实现**：
- 修改 `registry.all_definitions()` → `registry.active_definitions(phase, intent)`
- 修改 `AgentLoop._loop()` → 根据本轮 LLM 调用的工具自动扩展下一轮工具集
- 预期收益：每轮节省 ~40-56% tool definition tokens

**涉及文件**：
- `src/data_agent/tools/registry.py` — 添加分组和按需加载逻辑
- `src/data_agent/agent/loop.py` — _loop() 中调用 active_definitions 替代 all_definitions

---

### 1.2 系统提示词分级

**问题**：prompts.py 的 6 步思维链对简单任务过重，强制 describe + detect_quality + assess_readiness 至少 3 轮准备。

**方案**：系统提示词分三级，根据任务复杂度自动选择：

| 级别 | 触发条件 | Prompt 内容 | 预期轮次 |
|---|---|---|---|
| quick | 数据变换/查询/汇总/导出 | 精简版（~600 tokens）：工具选择规则 + 输出格式 | 1-3 轮 |
| standard | 单维度分析/趋势/分布 | 标准版（~1000 tokens）：4 步思维链 + 策略表子集 | 3-6 轮 |
| full | 完整报告/全面分析/归因 | 完整版（~1365 tokens）：7 阶段流程 + 任务管理 | 7+ 轮 |

**判断逻辑**（由 prompt 引导 LLM 自行判断，不额外消耗一轮）：
```
你是资深数据分析专家。根据用户请求复杂度选择执行模式：
- QUICK：数据变换、查询、汇总、筛选、导出。直接调用工具完成，不做准备性分析。
- STANDARD：单维度分析（趋势/分布/相关性）。先 describe，再分析。
- FULL：完整报告、全面分析、归因、预测。按完整 7 阶段流程执行。
```

**涉及文件**：
- `src/data_agent/agent/prompts.py` — 拆分为三个模板

---

### 1.3 工具输出精简 + 持久化

**问题**：`describe_dataset` 对 13 列数据返回 ~2000 chars，全部进入对话历史，后续每轮携带。

**方案**：工具返回分为"摘要"（返回给 LLM，<500 chars）和"详情"（持久化到磁盘，不进 messages）：

```python
# Before
return json.dumps(result, indent=2)  # ~2000 chars 全部进入 messages

# After
summary = _summarize(result)           # ~300 chars
detail_path = _persist(result)         # 持久化到 session/tool_outputs/
return json.dumps({"summary": summary, "detail_ref": str(detail_path)})
```

**精简规则**：
- `describe_dataset`：只返回 shape + 列名列表 + dtype + 缺失率，统计量持久化
- `detect_data_quality`：只返回 issue 数量和等级，详情持久化
- `correlation_analysis`：只返回 high_correlations 列表，完整矩阵持久化
- `distribution_analysis`：只返回偏度/峰度/正态性，分位数持久化

**LLM 需要详情时**：通过 `read_file(detail_ref)` 获取（但这会明确是一轮有目的的调用）。

**涉及文件**：
- `src/data_agent/tools/data_understand.py` — describe_dataset 输出精简
- `src/data_agent/tools/eda.py` — correlation/distribution 输出精简
- `src/data_agent/tools/_utils.py` — 添加 persist_detail 辅助函数

---

## 二、工具能力增强 (P1)

### 2.1 transform_data 增加 resample 和多列聚合

**问题**：`group_aggregate` 只支持单列单函数，"按周汇总内购数据"无法一次完成。

**方案**：新增 `resample` 操作，支持多列多函数聚合：

```python
# 新增 operation: resample
transform_data(
    name="内购数据",
    operation="resample",
    params=json.dumps({
        "date_col": "日期",
        "freq": "W",              # W=周, M=月, Q=季, Y=年
        "agg": {                  # 每列可不同聚合函数
            "活跃用户": "sum",
            "新增用户": "sum",
            "内购收入": "sum",
            "内购arpu": "mean",
            "付费人数": "sum",
        }
    }),
    save_as="周汇总"
)
```

同时增强 `group_aggregate` 支持多列多函数：

```python
transform_data(
    name="内购数据",
    operation="group_aggregate",
    params=json.dumps({
        "group_by": "月份",
        "agg": {
            "内购收入": ["sum", "mean"],
            "付费人数": ["sum", "count"],
        }
    }),
    save_as="月度汇总"
)
```

**涉及文件**：
- `src/data_agent/tools/data_transform.py` — 新增 resample、增强 group_aggregate

---

### 2.2 合并 describe + quality + readiness → quick_profile

**问题**：三个工具功能重叠，LLM 三个都调用浪费 3 轮。

**方案**：新增 `quick_profile` 工具，一次返回数据全貌：

```python
quick_profile(name="内购数据") → {
    "shape": [248, 13],
    "columns": [{"name": "日期", "dtype": "object", "likely_type": "date", ...}],
    "quality": {"missing": 0, "outliers": 3, "duplicates": 0},
    "readiness": "ready",
    "warnings": ["列 '付费率' 是百分号字符串，建议转换"],
    "suggested_next": ["apply_type_conversion", "transform_data(resample)"]
}
```

**保留原工具**：`describe_dataset`、`detect_data_quality`、`assess_readiness` 不删除，但降级为"高级按需使用"，prompt 引导 LLM 默认用 `quick_profile`。

**涉及文件**：
- `src/data_agent/tools/data_understand.py` — 新增 quick_profile
- `src/data_agent/agent/prompts.py` — 引导优先使用 quick_profile

---

### 2.3 统计工具补全显著性检验

**问题**：Q9/Q10/Q11/Q13 — 多个工具缺少关键统计检验。

**修改清单**：

| 工具 | 补充内容 |
|---|---|
| `correlation_analysis` | 每对相关系数附加 p-value；high_correlations 附加 `significant: bool` |
| `distribution_analysis` | 每列附加 `normality_test: {test: "shapiro", p_value, is_normal}` (n<5000 时) |
| `ab_test` | auto 模式增加正态性判断（Shapiro-Wilk 当 n<5000），非正态强制 Mann-Whitney；附加 Levene 方差齐性检验 |
| `regression_analysis` / `classification` | 新增 `cv_folds` 参数（默认 5），启用时报告 cv mean ± std；默认关闭以兼容 |
| `causal_analysis` (DID) | 增加预处理期趋势对比，如趋势差异 >20% 则返回 warning |
| `forecast` | 返回 `diagnostics: {mape, rmse, seasonality_strength}` |

**涉及文件**：
- `src/data_agent/tools/eda.py` — correlation_analysis, distribution_analysis
- `src/data_agent/tools/statistics.py` — ab_test, causal_analysis
- `src/data_agent/tools/ml.py` — forecast, regression_analysis, classification

---

### 2.4 analyze_time_series 自动推断列名

**问题**：Q3 — 要求手动指定 date_col 和 value_col，LLM 可能多一轮 preview_data 确认列名。

**方案**：
- `date_col` 为空时，自动选择第一列 `datetime64` 或可被 `pd.to_datetime` 成功转换的列
- `value_col` 为空时，自动选择第一个 `int64/float64` 列（排除 ID 类低 nunique 列）
- 自动推断后，在返回结果中明确标注 `inferred_columns: {date_col: "日期", value_col: "内购收入"}`

**涉及文件**：
- `src/data_agent/tools/eda.py` — analyze_time_series

---

## 三、Prompt 工程优化 (P1)

### 3.1 工具选择决策树

**问题**：Q7 — LLM 面对任务不知道该用 transform_data 还是 run_python。

**方案**：在系统提示词中添加明确的工具选择优先级：

```
## 工具选择规则（按优先级，优先使用排在前面的）

1. 数据加载/导出 → load_data / export_data
2. 数据概览 → quick_profile（不要分别调用 describe + quality + readiness）
3. 数据变换 → transform_data
   - 筛选/选择列/重命名/排序 → transform_data(filter/select/rename/sort)
   - 分组汇总 → transform_data(group_aggregate)
   - 时间重采样 → transform_data(resample)（不要用 run_python）
   - 透视/合并 → transform_data(pivot/merge)
4. 字段派生 → derive_field
5. 类型转换 → apply_type_conversion
6. 时间序列分析 → analyze_time_series（不要用 run_python）
7. 统计检验 → ab_test / correlation_analysis
8. 预测 → forecast
9. 报告 → generate_report
10. run_python → 仅当以上工具确实无法满足需求时使用

禁止：
- 不要用 run_python 完成已有工具能做的事（groupby、resample、describe 等）
- 不要连续调用 describe_dataset + detect_data_quality + assess_readiness，用 quick_profile 代替
```

**涉及文件**：
- `src/data_agent/agent/prompts.py`

---

### 3.2 工具返回值附加 suggested_next

**问题**：Q5 — 工具只返回原始数据，LLM 不确定下一步，可能导致多余调用。

**方案**：关键工具返回结果附加 `suggested_next` 字段：

```python
# quick_profile 返回
{
    ...,
    "suggested_next": [
        "apply_type_conversion(auto=true) 转换日期和百分比列",
        "transform_data(resample, freq='W') 按周汇总"
    ]
}

# analyze_time_series 返回
{
    ...,
    "suggested_next": [
        "correlation_analysis 检查哪些指标与内购收入相关",
        "distribution_analysis 检查收入分布特征"
    ]
}
```

**注意**：不是强制 LLM 执行，只是提供选项。LLM 可以根据用户意图选择忽略。

**涉及文件**：
- `src/data_agent/tools/data_understand.py` — quick_profile
- `src/data_agent/tools/eda.py` — analyze_time_series

---

## 四、架构优化 (P2)

### 4.1 工具分组注册

**问题**：当前所有工具平铺注册，没有分组概念。

**方案**：`ToolRegistry` 支持分组元数据：

```python
@registry.register(
    name="analyze_time_series",
    group="eda",              # 新增
    phase="analysis",         # 新增: understand | transform | analysis | ml | report
)
```

`active_definitions(phase)` 根据当前阶段只返回对应 phase 的工具 + 始终可用的 core 工具。

**涉及文件**：
- `src/data_agent/tools/registry.py`

---

### 4.2 数据操作血缘追踪

**问题**：Q6 — transform 生成新数据集但不记录操作历史。

**方案**：workspace 记录变换 DAG：

```python
# workspace 变换记录
workspace.transform_log = [
    {"from": "内购数据", "op": "resample(W)", "to": "周汇总", "timestamp": "..."},
    {"from": "周汇总", "op": "select(columns=[...])", "to": "周汇总_clean", "timestamp": "..."},
]
```

LLM 可通过 `list_data()` 看到变换历史，避免重复操作。

**涉及文件**：
- `src/data_agent/session/workspace.py` — add transform log

---

## 五、实施计划

### Phase 1：效率救急（预期 token 节省 70%+）

| # | 任务 | 涉及文件 | 预期效果 |
|---|---|---|---|
| 1.1 | 工具按需加载：分组注册 + active_definitions | registry.py, loop.py | 每轮 -40~56% tool tokens |
| 1.2 | 系统提示词三级（quick/standard/full） | prompts.py | 简单任务 -50% prompt tokens |
| 1.3 | 工具输出精简 + 持久化 | data_understand.py, eda.py, _utils.py | 对话历史 -40% 增长 |
| 1.4 | prompt 添加工具选择决策树 | prompts.py | 减少 run_python 滥用 |

### Phase 2：分析质量提升（不改效率，改专业度）

| # | 任务 | 涉及文件 | 预期效果 |
|---|---|---|---|
| 2.1 | transform_data 增加 resample + 多列聚合 | data_transform.py | 消除"汇总需求转 run_python" |
| 2.2 | 新增 quick_profile 合并工具 | data_understand.py | 3 轮准备 → 1 轮 |
| 2.3 | 统计工具补全显著性（Q9/Q10/Q11/Q13） | eda.py, statistics.py, ml.py | 分析结论可标注统计显著性 |
| 2.4 | analyze_time_series 自动推断列名 | eda.py | 减少一轮 preview |

### Phase 3：架构优化（长期可维护性）

| # | 任务 | 涉及文件 | 预期效果 |
|---|---|---|---|
| 3.1 | 工具分组元数据（group/phase） | registry.py + 所有工具文件 | 为更精细的按需加载打基础 |
| 3.2 | 数据操作血缘追踪 | workspace.py | LLM 可查询变换历史 |
| 3.3 | 工具返回 suggested_next | 各工具文件 | 减少 LLM 决策不确定性 |

---

## 六、预期收益量化

### "按周汇总内购数据" 场景

| 指标 | 改进前 | Phase 1 后 | Phase 1+2 后 |
|---|---|---|---|
| LLM 轮次 | ~25 | 2-3 | 1-2 |
| 每轮 overhead | ~4944 tokens | ~2585 tokens | ~2165 tokens |
| 总 token 消耗 | ~110 万 | ~2 万 | ~1 万 |
| 节省比例 | — | 98% | 99% |
| 分析质量 | 因崩溃无输出 | 完成 | 完成 + 自动类型转换 |

### "完整分析报告" 场景

| 指标 | 改进前 | Phase 1 后 | Phase 1+2 后 |
|---|---|---|---|
| LLM 轮次 | ~30-40 | ~15-20 | ~10-15 |
| 每轮 overhead | ~4944 tokens | ~2985 tokens | ~2799 tokens |
| 总 token 消耗 | ~150-200 万 | ~50-70 万 | ~30-40 万 |
| 统计严谨性 | 无 p-value | 同前 | 显著性标注+正态检验 |
