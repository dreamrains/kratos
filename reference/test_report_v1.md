# 全面测试报告 V1

**测试时间**: 2026-04-27
**测试数据**: `reference/workspace/内购数据.xlsx` (248 rows x 13 cols) + 自建测试数据

## 测试范围

### 已实现改进功能（本次新增）
- A1: ToolResult 结构化返回
- A2: CommandRegistry 命令注册表
- A3: Agent Loop suspendable（CLI/Web 双模式）
- A4: assess_readiness 数据就绪度评估
- B1: 多假设竞争（Prompt 层面）
- B2: 轻量快答模式（Prompt 层面）
- B3: 报告双风格输出（detailed/executive）

### 已有功能验证
- 数据工具: describe_dataset, detect_data_quality, preview_data, clean_data, load_data, transform_data, derive_field, export_data
- 分析工具: analyze_time_series, correlation_analysis, distribution_analysis, segmentation_analysis, attribution_analysis, regression_analysis, classification, ab_test, causal_analysis
- 报告工具: generate_report, export_report_markdown, export_report_pdf
- 任务工具: task_create, task_update, task_list, task_get
- 知识工具: show_project_rules, show_domain_knowledge, show_experience_log
- 沙盒: run_python

---

## 测试结果

| # | 测试项 | 状态 | 说明 |
|---|--------|------|------|
| 1 | 模块导入 | PASS | 所有7个核心模块可正常导入 |
| 2 | ToolResult 构建 | PASS | summary, data, artifacts, from_str, to_cli, to_web |
| 3 | Registry ToolResult 返回 | PASS | execute() 均返回 ToolResult（需先 _auto_discover_tools） |
| 4 | describe_dataset | PASS | 真实数据: 248 rows x 13 cols |
| 5 | detect_data_quality | PASS | 发现 8 issues（outliers） |
| 6 | assess_readiness | PASS | overall=ready（修复后） |
| 7 | analyze_time_series | PASS | 趋势/突变点/季节性检测正常（修复后） |
| 8 | correlation_analysis | PASS | matrix + high_correlations |
| 9 | distribution_analysis | PASS | 分位数、偏度、峰度 |
| 10 | segmentation_analysis | PASS | KMeans 聚类 3 clusters |
| 11 | clean_data | PASS | 去重+填充缺失值 |
| 12 | transform_data (filter/select/sort) | PASS | 修复 sort 的 ascending 参数 |
| 13 | generate_report (detailed) | PASS | 6 章节完整报告 |
| 14 | generate_report (executive) | PASS | 精简摘要 |
| 15 | export_report_markdown | PASS | MD 格式导出 |
| 16 | derive_field | PASS | 派生列正常 |
| 17 | run_python | PASS | 沙盒 pd/np/get_dataset 可用 |
| 18 | task_create/task_list | PASS | 任务创建与查询 |
| 19 | CommandRegistry | PASS | 注册/执行/别名/列表 |
| 20 | Suspension 机制 | PASS | 模式切换/SuspensionManager/序列化 |
| 21 | Prompt 内容验证 | PASS | 多假设/快答/任务/报告/确认规则均存在 |
| 22 | regression_analysis | PASS | 模型训练 + feature importance |
| 23 | classification | PASS | 多分类 + metrics |
| 24 | ab_test | PASS | ttest/mannwhitneyu（修复后） |
| 25 | attribution_analysis | PASS | 相关性 + GBDT 归因 |
| 26 | 知识工具 | PASS | rules/domain/experience 正常读取 |

---

## 发现并修复的 Bug（6个）

### Bug 1: assess_readiness Timedelta.clip() 不存在 [已修复]
- **文件**: `tools/data_understand.py:210`
- **原因**: `pd.Timedelta` 对象没有 `.clip()` 方法
- **修复**: 改为 `max(median_diff, pd.Timedelta(seconds=1))`

### Bug 2: assess_readiness 缺失率 50% 边界条件 [已修复]
- **文件**: `tools/data_understand.py:233`
- **原因**: `> 50` 导致恰好 50% 缺失率被降级为 warning 而非 block
- **修复**: `>= 50`

### Bug 3: analyze_time_series numpy.bool_ JSON 序列化 [已修复]
- **文件**: `tools/eda.py:61,98`
- **原因**: `p_value < 0.05` 返回 `numpy.bool_`，`json.dumps` 无法序列化
- **修复**: `bool(p_value < 0.05)`

### Bug 4: ab_test / causal_analysis numpy.bool_ JSON 序列化 [已修复]
- **文件**: `tools/statistics.py:69,76,86,164`
- **原因**: 同 Bug 3
- **修复**: `bool(...)` 包裹

### Bug 5: transform_data sort ascending 参数类型错误 [已修复]
- **文件**: `tools/data_transform.py:119`
- **原因**: JSON 解析的 `ascending` 为 Python bool，调用 `.lower()` 报错
- **修复**: `str(ascending_raw).lower() == "true"`

### Bug 6: 报告双风格输出缺失 [已修复]
- **文件**: `tools/report.py`
- **原因**: 改进计划中定义了 B3 但代码未实现 `style` 参数
- **修复**: 添加 `style` 参数，支持 "detailed" 和 "executive" 两种模式

---

## 发现但未修复的问题（需讨论）

### P1: 工具参数名不一致
部分工具的参数命名风格不统一，LLM 调用时容易用错参数：
- `analyze_time_series`: 用 `date_col`/`value_col`
- `forecast`: 用 `date_col`/`target_col`
- `attribution_analysis`: 用 `target_col`/`features`
- `correlation_analysis`: 用 `columns`（逗号分隔字符串）
- `distribution_analysis`: 用 `columns`

**建议**: 统一命名规范，如统一用 `target_col` 而非混用 `target`/`value_col`

### P2: 工具模块未自动发现
`registry.tool_names` 在只导入 `registry` 模块时为空，需要显式调用 `_auto_discover_tools()` 或通过 `AgentLoop.__init__` 触发。如果直接使用 registry 而不经过 AgentLoop，工具不可用。

**建议**: 在 `tools/__init__.py` 中添加自动发现逻辑，或在 `registry.py` 中惰性加载

### P3: Prophet 兼容性
`forecast` 工具依赖 Prophet，但 Prophet 在某些环境下有兼容性问题（`'Prophet' object has no attribute 'stan_backend'`）。这不影响核心功能，但应增加 fallback 机制。

**建议**: 增加简单线性预测作为 fallback

### P4: Excel 编码
读取中文 Excel 文件时需要 `-X utf8` 标志，否则列名显示为乱码。这在 Windows 环境下尤其明显。

**建议**: `load_data` 工具内部强制使用 UTF-8 编码处理

### P5: 任务 ID 残留
task_manager 是内存级单例，测试间任务 ID 会累加，不影响功能但可能影响测试可重复性。

### P6: list_skills 返回 "Skill system not initialized"
Skill 系统需要在 AgentLoop 初始化后才可用。独立调用 `list_skills` 会失败。

**建议**: 改为返回空列表或友好提示

---

## 安全审查

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 沙盒代码执行 | OK | 安全检查阻止危险操作，超时保护 |
| JSON 注入 | OK | 所有 JSON 构建使用 json.dumps |
| 路径遍历 | OK | load_data 搜索限定在项目目录 |
| 命令注入 | OK | filter 使用 df.query()，无直接 eval |

## 性能观察

- 248 行数据集的全工具链测试在 30 秒内完成
- ML 工具（regression/classification）需要额外时间训练模型，在 100 行数据上约 5-10 秒
- 报告生成即时完成
- 未发现明显的性能瓶颈
