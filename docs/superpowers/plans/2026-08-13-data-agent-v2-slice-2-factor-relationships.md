# Data Agent V2 Slice 2：因素关系分析

- **日期**：2026-08-13
- **状态**：Implemented; focused acceptance passed
- **基线提交**：`26f4ab4`（`feat(v2): add calibrated chart message blocks`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标

建立一条最小但严谨的因素关系纵向路径，回答“哪些因素与目标存在可靠关系”，同时明确拒绝把模型相关性写成业务影响或因果作用。

```text
显式 FactorAnalysisSpec
→ 数据与分析单位诊断
→ 目标泄漏 / 数学恒等关系识别
→ 结构化多变量方法
→ feature-level Finding 或 null_result
→ 块级校准答案
→ 条件式系数图
→ 语义 SSE、持久化和刷新
```

## 2. 显式分析规范

Slice 2 不从自然语言猜测关键统计语义。调用方必须提供：

- `target`：目标数值列；
- `features`：候选因素列；
- `analysis_unit`：独立观测或聚类单位列；
- `question`：用户问题；
- `time_field`：存在重复观测或时间结构时提供，可为空。

如果单位重复但没有时间字段，系统发布 `limited` 诊断而不是默认把每一行当独立样本，也不自动发起用户许可式确认。

## 3. 方法边界

### 3.1 预诊断

- 目标、因素和单位字段存在且身份互异；
- 数值解析和完整案例范围明确；
- 常量因素排除；
- 与目标完全相同的特征排除；
- 识别目标由候选特征加、减、乘、除形成的近似数学恒等关系，并排除参与列；
- 共线性通过 VIF 显化，高共线因素不进入“可靠因素”结论；
- 有时间字段时加入时间趋势控制；
- 重复单位且有时间字段时使用按分析单位聚类的稳健标准误。

### 3.2 估计与不确定性

- 连续目标和连续因素使用标准化多变量 OLS；
- 独立行使用 HC3 稳健标准误；
- 重复单位使用 cluster-robust 标准误，并将唯一单位数作为有效样本语义；
- 输出标准化系数、95% 置信区间、原始与 Holm 校正 p 值、VIF、完整案例数和有效单位数；
- 样本充分性取决于模型自由度、有效单位和方法，不使用普遍 `n < 30` 规则；
- 多重比较后仍满足阈值且置信区间不跨 0 的因素才能形成正向 Finding。

### 3.3 结论等级

- 正向结果最多表述为“在当前模型与数据范围内，与目标存在调整后统计关联”；
- 不使用“影响、驱动、导致、提升会带来”等因果措辞；
- 没有可靠因素时生成 `null_result`，仍发布已测试因素、估计范围和限制；是否给出行动建议留给后续独立决策能力；
- 目标泄漏、共线性或重复测量问题是具体诊断，不是删除整篇答案的理由。

## 4. ResultContract 与 Finding

方法能力：`analysis.factor_relationship`。

每个可靠因素形成一个 Finding：

```text
finding_kind = association
metric_identity = target column
feature_identity = factor column
estimate = standardized coefficient
uncertainty = confidence_low / confidence_high / p_value / p_adjusted / vif
effective_sample = complete-case rows or unique clusters
maximum_claim_class = inferential
limitations = observational and model-specific boundaries
```

没有可靠因素时形成一个 `null_result` Finding，包含全部测试摘要和具体未满足条件。

## 5. 验收重点

- 强关联因素在稳健标准误和 Holm 校正后形成 Finding；
- 无信号样本形成可发布 `null_result`；
- 数学恒等关系和目标等价特征不会被称为因素；
- 高 VIF 特征不会形成可靠因素结论；
- 重复单位缺少时间字段时不伪装成独立样本；
- 不使用固定样本量 30 门槛；
- Answer Blocks 的 claim class 不超过 Finding 上限；
- 条件系数图绑定 Finding IDs，图表失败不阻断文本；
- SSE 进度、最终块、刷新上下文和 Artifact 关系在浏览器走通。

## 6. 本切片不做

- 不支持分类目标、生存分析、面板固定效应或自动非线性搜索；
- 不声称发现因果效应；
- 不从所有列自动选择因素；
- 不让模型自由生成统计代码；
- 不调用真实 provider；
- 不接管旧主页面或生成 Gate E/F 产品完成凭证。

## 7. 验收记录

- 强信号、无可靠因素、数学恒等关系、高共线、重复单位缺少时间、聚类稳健和小样本非固定门槛均由聚焦测试覆盖；
- 聚类推断使用小样本修正和 t 分布，并在有效聚类自由度不足时发布 `limited`；
- 浏览器实测通过全新上传、语义 SSE、首次图表 SVG、统计边界排版和刷新恢复；
- 浏览器验收曾检出“流未关闭就挂载 iframe”导致的首次空图，修复后图表只在 SSE 关闭后挂载；
- 本记录仅证明 Slice 2 canary，不等同于旧主流程、Gate E/F 或产品整体可用。
