# Data Agent V2 Slice 1B：块级校准与图表消息块

- **日期**：2026-08-13
- **状态**：Implemented，尚未提交
- **基线提交**：`263796f`（`feat(v2): add fact-driven slice 1 canary`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 本切片目标

在不接回旧 assurance overlay 的前提下，完成两个用户可见且相互关联的能力：

1. 一个答案块校准失败时，不删除或扣押其他已支持块；
2. 图表成为可验证、可持久化、可刷新恢复的 Artifact 和 Message Block，而不是 Markdown marker 或临时路径。

## 2. 块级校准契约

`Typed Answer Compiler` 逐块给出以下结果：

- `supported`：原块通过确定性校验并发布；
- `replace_with_diagnostic`：材料性块存在证据等级、数值或支撑引用问题，只替换该块；
- `omit_optional`：无支撑的可选图表、建议或补充块省略，不影响其他答案块。

本切片不实现 LLM 的一次结构化修订；`revise` 和 `exploratory` 保留为后续 Publisher 能力。确定性校准不能被模型覆盖。

## 3. Chart Artifact 契约

每个图表保存以下服务端字段：

```text
chart_id
title
chart_type
dataset_version_ids
finding_refs
x_field
y_fields
purpose
relative_path
content_fingerprint
```

硬约束：

- `evidence` / `insight` 图表必须引用 Evidence Ledger 中已存在的 Finding；
- HTML 内容必须匹配 `sha256` 指纹，同 ID 不允许覆盖；
- Answer Block 的 `chart_refs` 必须属于本轮持久化 `artifact_ids`；
- 未被正文块消费但属于本轮的 Artifact 保留给末尾 supplemental 区；
- HTML 只使用本地 Plotly 资源，不依赖 CDN；
- iframe 只有检测到内部 Plotly SVG 后才标记为加载完成。

## 4. 适图判定

Slice 1B 只增加一个受控趋势变体：

- 问题明确表达趋势、走势、随时间变化等视觉模式；
- 指标至少有两个有效数值；
- 数据中恰好有一个可识别且至少包含两个不同值的时间维度；
- 通过共享 `chart_contract` 的折线图语义校验。

“平均值是多少”不会生成图表。趋势问题调用一个结构化 `analysis.describe_trend` 方法，发布首尾值、绝对变化、百分比变化、有效时间点与局限。图表失败属于可选增强失败，Execution Journal 记录 `artifact_failed`，核心文本结论继续发布。

## 5. 消息与刷新

turn 在 `turn_completed` 前原子持久化：

- Answer Blocks；
- `artifact_ids` 和可恢复 Artifact 元数据；
- `filename`、`metric`、`question` 请求上下文。

刷新后恢复原问题、指标、关联文件、答案块、正文内联图表和 supplemental 图表，不从工具文本或 Markdown marker 重建关系。

## 6. 本轮验证

- V2 聚焦测试 47 项通过，覆盖块级替换、可选块省略、图表证据引用、不可变内容、适图判定、趋势 Finding、图表失败降级、SSE、Artifact serving 和刷新上下文；
- 相邻 chart contract 21 项、chart semantics 与本地静态资源 31 项通过，`node --check` 通过；
- 真实浏览器完成上传、趋势分析、Artifact 进度、正文内联、Plotly SVG 就绪和刷新恢复；
- 浏览器控制台无 error / warning；
- 未调用真实 provider，未生成 Gate E/F 或产品完成 receipt。

## 7. 明确未完成

- 通用图表 Planner 和多图排序；
- 分组、分布、关联等其他图表类型；
- LLM 一次结构化修订；
- 真实 Agent/LLM 接入；
- 旧主页面切换；
- real-provider analysis journey 与人工语义评分。

下一切片应先讨论是继续扩展 Slice 1 的图表类型，还是进入 Slice 2 因素关系分析。不能因为本切片浏览器通过就宣称产品已经恢复可用。
