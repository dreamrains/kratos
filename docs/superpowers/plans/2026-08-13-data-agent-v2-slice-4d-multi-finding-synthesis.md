# Data Agent V2 Slice 4D：多 Finding 综合与金字塔发布

- **日期**：2026-08-13
- **状态**：Implemented; pending commit
- **基线提交**：`cc08270`（`feat(v2): add backtested baseline forecast slice`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标与场景

Slice 4D 验证同一用户问题下，系统能否对同一分析副本同时回答：

1. 指标在历史范围内是否存在可靠趋势；
2. 两个用户指定组别之间是否存在可靠差异；
3. 两类证据合并后，能否给出不超过证据上限的综合回答与条件建议。

调用方显式提供时间字段、指标、频率、聚合、双组字段、分析单位和问题。系统不从自由文本猜测这些方法参数。

## 2. 单轮事实边界

- 一次 raw 注册和一次 analysis 副本；
- 两个 core Commitments：`historical_trend` 与 `group_comparison`；
- 每个方法独立写 Execution Event 和 core Finding；
- Run Projection 一次性从全部事实计算两个 Outcomes；
- 任一 core 只能由自身接受的方法和 Finding kind 完成；
- 运行时不得调用 Slice 4A/4B 的完整发布流程并拼接其 Markdown。

## 3. 失败与限制隔离

- 两个 Commitment 均达到 `supported | null_result | limited | unavailable` 后才正常发布；
- 一类分析受限时，发布具体限制块，但不得删除另一类已经支持的 Finding、图表或方法说明；
- 图表失败只影响对应 artifact，不改变该分析 Finding；
- `system_failed` 不得包装成分析限制。

## 4. 金字塔与图表编排

默认顺序：

1. 综合直接回答：只说明哪些问题已得到支持、零结果或限制，不引入超出最低共同证据上限的新数字；
2. 历史趋势核心发现，后接趋势图；
3. 分组比较核心发现，后接组间分布图；
4. 统一的方法、不确定性与共同边界；
5. 用户要求时生成条件建议；
6. 未在正文消费的有效图表由前端补充区兜底。

每个数字块只绑定产生该数字的 Finding。综合块可同时引用两个 core Findings，但其 claim class 不得超过二者最低上限。

## 5. 建议决策

- 用户未要求建议：不生成建议块；
- 任一分析受限：建议先解决对应语义、分析单位或数据条件；
- 两类结果可用但均为观察性证据：最多建议检查时间与组别构成的交互、混杂和低风险验证；
- 不把历史趋势与组间差异的同时存在写成“组别导致趋势”或干预效果。

## 6. 本切片不做

- LLM 自由生成整篇综合 Markdown；
- 多文件、连接、因果识别或预测与趋势的自动联合；
- 自由 `run_python` 结果升级为 verified Finding；
- 主页面接管、真实 provider 调用或 Gate E/F 完成声明。

## 7. 验收重点

- 两个 supported、趋势 supported + 分组 limited、一个图表失败三类路径有测试；
- 单个 summary Finding 或单个工具成功不能虚假完成整个问题；
- SSE 展示两个方法的真实执行进度；
- 两张图分别邻接自身 Finding，刷新后保持引用关系；
- 综合块无虚构数字、无因果升级、无内部 evidence marker；
- 浏览器切片通过不等于旧主页面或产品整体可替代。

## 8. 本切片验收记录

- 聚焦多承诺、块级隔离、API、页面与图表回归：`36 passed`；
- 全量 V2 回归：`127 passed`；
- 真实浏览器旅程按顺序显示趋势与双组工具事件，最终发布 5 个答案块与 2 张邻接图表；
- 刷新前后均为 5 个答案块，两张图均为 `data-chart-loaded=true`，图表标题与 Finding 邻接关系保持不变；
- 强制双组图失败时，趋势图、趋势 Finding、双组 Finding 和最终答案仍正常发布；
- 未调用真实 provider，未执行旧 Gate E/F，也不声明旧主页面或产品整体已经恢复。
