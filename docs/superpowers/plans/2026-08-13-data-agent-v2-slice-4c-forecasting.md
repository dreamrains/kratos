# Data Agent V2 Slice 4C：有回测约束的基线预测

- **日期**：2026-08-13
- **状态**：Implemented; pending commit
- **基线提交**：`2d42dd6`（`feat(v2): add calibrated historical trend slice`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标与边界

Slice 4C 只回答“在明确口径和预测期下，短期基线预测是什么”。它不是干预效果、因果推断、预算承诺或长期结构预测。

调用方必须显式提供：

- `time_field`、`metric`；
- `frequency: daily | weekly | monthly`；
- `aggregation: sum | mean`；
- `horizon`，正整数且不超过 30，同时不超过观测周期的四分之一；
- 用户问题与独立 Recommendation Policy 参数。

不从自由文本猜测粒度、聚合或预测期，不因“预测属于高级方法”请求许可。

## 2. 规则时间序列

- 复用 Slice 3 的日期语义检查和 Slice 4B 的规则周期口径；
- 歧义日期、不可无损解析和缺失规范周期均发布具体 `limitation`；
- 不补零、不插值、不随机打乱训练与验证顺序；
- 重复时间点只按用户明确的 `sum | mean` 聚合。

## 3. 候选基线与时间外回测

第一版只比较可解释、确定性的基线：

- `naive_last`：上一周期值；
- `drift`：用当时训练窗口首尾形成的平均漂移外推；
- `seasonal_naive`：数据覆盖至少两个完整季节时启用，日频周期 7、月频周期 12、周频周期 52。

候选方法只用验证点之前的数据做 expanding-window 一步预测。按验证 MAE 选择方法，同时报告 RMSE、MASE、相对 naive 的 skill 和验证点数。不得用同一序列的拟合残差冒充时间外回测。

## 4. 发布门与不确定性

- 历史长度必须支持最小训练窗、至少 6 个验证点和请求 horizon；
- MASE 不可计算、`MASE > 1.25`，或验证 MAE 已超过指标典型绝对量级时，发布 `limited: backtest_quality_below_threshold`，并记录实际诊断，不发布未来点估计；
- 可发布预测使用滚动时间外绝对误差形成经验预测区间；远期区间按 `sqrt(h)` 扩张；
- 区间是基线模型的经验误差范围，不是未来必然覆盖保证；
- 输出每个未来周期的时间、点预测、下界和上界，Finding 上限为 `predictive`。

## 5. Finding、图表与建议

- 一个 descriptive 历史序列摘要 Finding；
- 一个 `forecast | limitation` core Finding；
- core Commitment 不接受历史摘要，避免“完成度被断言”；
- 图表展示历史观测、预测点和预测区间，并绑定 core Finding；
- 正文先给 horizon 范围和预测端点，再解释回测质量、方法与区间边界；
- 行动意图最多生成带监控、情景范围和更新条件的调查/规划建议，不把预测写成干预效果。

## 6. 本切片不做

- Prophet、ARIMA 自动搜索或模型竞赛；
- 外生变量、层级预测、概率分布预测；
- 结构突变自动解释；
- 多序列联合预测；
- 真实 provider 调用、旧主页面接管或 Gate E/F 产品完成声明。

## 7. 验收重点

- 趋势、季节、不可预测噪声、缺失周期、歧义日期、horizon 越界均有 owner tests；
- 回测严格按时间顺序，无随机切分和未来泄漏；
- 低质量回测只发布限制，不生成伪精确未来曲线；
- 可发布预测包含时间外指标和经验区间；
- SSE、正文内联图表和刷新恢复走真实浏览器旅程；
- Slice 4C 通过不等于完整预测产品或整体 V2 已可替代旧主线。

## 8. 本切片验收记录

- 聚焦预测算法、运行时、投影、API 与页面回归通过；
- 真实浏览器旅程：上传 → SSE → 预测正文 → 内联区间图 → 建议降级 → 刷新恢复通过；
- 刷新前后均为 3 个答案块且图表 `data-chart-loaded=true`；
- 视觉复核确认普通视口、结果正文和图表布局正常；浏览器插件的 full-page 拼接异常不属于页面 CSS；
- 未调用真实 provider，未执行旧 Gate E/F，也不声明旧主页面或完整预测产品已经恢复。
