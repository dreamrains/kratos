# V5.0 系统测试报告

> 测试日期：2026-04-28
> 测试范围：全功能全场景系统测试 + 优化建议实施验证
> 测试文件：test_sales.csv (100×5)、内购数据.xlsx (248×13)、banner汇总数据.xlsx (248×18)

---

## 一、测试总结

| 阶段 | 测试项 | 通过 | 失败 | 已修复 |
|------|--------|------|------|--------|
| Phase A: 环境准备 | 文件识别、导入验证 | 3 | 0 | 0 |
| Phase B: L0-L1 工具 | 数据加载、理解、profile | 17 | 0 | 0 |
| Phase B: L2 EDA | 时间序列、相关、分布、分群 | 10 | 0 | 0 |
| Phase B: L3-L4 统计/ML | AB测试、DID、预测、回归、分类 | 7 | 0 | 0 |
| Phase B: Transform | resample、group_agg、filter等 | 8 | 3(预期错误) | 0 |
| Phase C: 集成测试 | 提示词分级、按需加载 | 18 | 0 | 0 |
| Phase D: 安全性 | 代码注入、文件访问、参数注入 | 8 | 0 | 0 |
| Phase D: 性能 | 10K行数据各操作 | 5 | 0 | 0 |
| Phase E: 优化实施 | 5项优化建议实施验证 | 5 | 0 | 0 |

**总计：81 通过 / 3 预期错误（参数校验） / 0 未修复缺陷**

---

## 二、发现并已修复的 BUG（3 项）

### BUG-1: 关键词覆盖不足 — "为什么"未激活 eda+stats

- **现象**：用户输入"为什么收入下降"时，只激活 core 分组，未激活 eda 和 stats
- **根因**：`_GROUP_KEYWORDS` 中 eda 和 stats 的关键词列表缺少"为什么"、"原因"等归因类词汇
- **修复**：在 eda 和 stats 分组关键词中增加"为什么"、"原因"、"洞察"
- **验证**：`activate_groups_for_text('为什么收入下降')` 现在正确激活 `{eda, stats}`

### BUG-2: resample freq='M' 触发 pandas FutureWarning

- **现象**：`transform_data(resample, freq='M')` 在 pandas >=2.2 中产生 FutureWarning
- **根因**：pandas 2.2+ 废弃了 'M'/'Q'/'Y' 频率别名，需使用 'ME'/'QE'/'YE'
- **修复**：在 resample 操作中添加自动映射 `_freq_map = {"M": "ME", "Y": "YE", "Q": "QE"}`
- **验证**：`resample(freq='M')` 不再产生警告，自动映射为 'ME'

### BUG-3: run_python exec 模式下变量赋值不返回结果

- **现象**：`run_python('result = 2 + 3')` 返回空 output，用户必须用 `print()` 才能看到结果
- **根因**：`_run_code` 中 exec 路径不读取 `result` 变量，`result_repr` 仅在 eval 路径设置
- **修复**：exec 执行后检查 `globs["result"]`，非 None 时写入 `result_repr`
- **验证**：`run_python('result = len(get_dataset("sales"))')` 正确返回 `{"result": "100"}`

---

## 三、已实施的优化建议（5 项）

### 优化 1: QUICK 模式只注入 project_rules ✅

- **实施**：修改 `build_system_prompt`，当 level=="quick" 时跳过 domain_knowledge 和 experience_log 注入
- **效果**：QUICK 模式下 rules 仍注入（保证业务规则约束），domain 和 experience 不注入（节省 token）
- **涉及文件**：`src/data_agent/agent/prompts.py`

### 优化 2: cohort_analysis 数据要求说明 ✅

- **实施**：更新 cohort_analysis 的 description，明确说明 user_col 必须是唯一用户ID列
- **效果**：LLM 在调用时会注意选择正确的列
- **涉及文件**：`src/data_agent/tools/eda.py`

### 优化 3: prompt 引导 group_aggregate 新格式 ✅

- **实施**：在三个级别模板（QUICK/STANDARD/FULL）的禁止规则中都添加了 agg dict 格式引导
- **效果**：引导 LLM 优先使用多列多函数的新格式，避免回退到旧的单列格式
- **涉及文件**：`src/data_agent/agent/prompts.py`

### 优化 4: load_data 添加间接注入检测 ✅

- **实施**：新增 `_detect_injection_patterns()` 函数，在 load_data 中自动扫描文本列
- **检测模式**：忽略之前的指令、ignore previous instructions、system:、<|im_start|>、### instruction 等
- **行为**：发现可疑内容时发出警告但不阻塞加载，提醒 LLM 不要执行数据中的指令性内容
- **验证**：恶意数据正确检测，正常数据不误报
- **涉及文件**：`src/data_agent/tools/data_io.py`

### 优化 5: causal_analysis 参数说明改进 ✅

- **实施**：更新 description，明确标注参数顺序和含义，附示例调用
- **效果**：减少 LLM 混淆参数顺序的概率
- **涉及文件**：`src/data_agent/tools/statistics.py`

---

## 四、安全性测试结果

| 测试项 | 结果 | 说明 |
|--------|------|------|
| run_python 文件系统访问 | **已阻止** | `import os` 被安全检查拦截 |
| run_python 网络访问 | **已阻止** | `open(` 被安全检查拦截 |
| run_python 子进程 | **已阻止** | `import subprocess` 被拦截 |
| transform_data filter SQL注入 | **已阻止** | pandas query 解析失败返回 error |
| derive_field 代码注入 | **已阻止** | `__import__` 在 pandas eval 中不被支持 |
| transform_data 无效JSON | **已阻止** | 返回 "params 必须是有效的 JSON" |
| preview_data 超大 n | **已限制** | min(n, 50) 生效 |
| 空数据集操作 | **已处理** | 正确返回 shape(0, 0) |
| 间接提示词注入检测 | **已实施** | load_data 扫描文本列并发出警告 |

---

## 五、性能测试结果

| 操作 | 数据量 | 耗时 |
|------|--------|------|
| quick_profile | 10,000 行 | 3ms |
| describe_dataset | 10,000 行 | 2ms |
| resample (10K→daily) | 10,000 行 | 3ms |
| correlation_analysis | 10,000 行 | 1ms |
| all_definitions ×100 | 52 tools | 50ms |
| active_definitions ×100 | 23 tools | 1ms (50x 更快) |
