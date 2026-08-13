# Data Agent V2 Slice 4B：时间序列趋势

- **日期**：2026-08-13
- **状态**：Implemented; pending commit
- **基线提交**：`7ed929a`（`feat(v2): add calibrated group comparison slice`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标与边界

Slice 4B 回答“历史指标是否存在可靠趋势”，不提供预测，也不把时间先后解释为因果。

调用方必须显式提供：

- `time_field`：时间字段；
- `metric`：连续数值指标；
- `frequency`：`daily | weekly | monthly`；
- `aggregation`：`sum | mean`；
- `question`；
- 独立 Recommendation Policy 所需的意图、风险和可逆性。

系统不得从自由问题文本猜测求和还是平均，也不得静默填补缺失时间段。

## 2. 日期与聚合

- 已是 datetime 或 ISO/唯一无损格式时可在分析副本自动解析；
- DMY/MDY 等真正歧义返回 `limited: date_semantics_require_confirmation`，交由 Slice 3 确认，不在 4B 重建确认权威；
- 按明确频率落入规范周期，重复时间点按明确 `sum` 或 `mean` 聚合；
- 保存源行数、有效数值行数、观测周期数、起止时间和聚合口径；
- 规范周期之间存在缺口时不插值、不补零，发布 `limited: missing_time_intervals`。

## 3. 趋势方法

- 主估计为每个周期的线性平均变化；
- OLS 使用 Newey–West/HAC 协方差和 t 分布有限样本推断；
- 日频且跨度足够时控制星期效应；月频且至少覆盖两个完整年度时控制月份效应；
- 输出趋势系数、95% CI、p 值、HAC lag、滞后 1 自相关和 Kendall 趋势敏感性诊断；
- 模型自由度决定是否可估计，不使用通用 `n < 30` 门槛；
- 无可靠趋势生成 `null_result`，不表述为“指标稳定不变”；
- 常量序列、缺失周期、日期歧义和模型自由度不足生成具体 `limitation`。

## 4. Finding 与发布

- 一个 descriptive series-summary Finding；
- 一个 `time_trend | null_result | limitation` core Finding；
- core Commitment 只接受后三类，series summary 不能虚假完成趋势问题；
- 折线图显示真实聚合序列；只有可估计时叠加线性拟合，图表绑定全部 Finding；
- 正向趋势最多为 inferential，且明确仅描述历史数据范围；
- Recommendation Policy 对观察性趋势最多给验证步骤，不把趋势外推成预测或行动效果。

## 5. 验收重点

- 有趋势、无趋势、常量、缺失周期、歧义日期、重复时间聚合和小而可识别序列均有测试；
- 日频星期季节控制与月频月份控制有明确触发条件；
- 正文说明单位是“每周期变化”，而不是模糊增长；
- 用户未要求建议时不生成建议块；要求行动时只生成验证性建议；
- 趋势图正文显示、首次加载和刷新恢复通过；
- 不调用真实 provider，不声明预测、因果、旧主页面或 Gate E/F 已完成。

## 6. 本切片验收记录

- 聚焦契约、运行时、API、页面与投影回归：`26 passed`；
- 真实浏览器旅程：上传 → SSE 进度 → 三个答案块 → 正文内联图表 → 刷新恢复均通过；
- 刷新前后图表均为 `data-chart-loaded=true`，恢复状态为“已从持久化消息块恢复”；
- 行动意图被 Recommendation Policy 限制为调查性验证步骤；
- 未调用真实 provider；未执行旧 Gate E/F，也不以本 canary 代替产品完成判定。
