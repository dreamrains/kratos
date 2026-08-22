# Data Agent V2 Slice 4A：分组比较与独立建议决策

- **日期**：2026-08-13
- **状态**：Implemented; focused acceptance passed
- **基线提交**：`af07973`（`feat(v2): add semantic transformation slice`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 为什么先做 4A

上位设计的 Slice 4 同时包含时间序列、分组比较、预测、建议分级、多 Finding 综合和探索性 Python。一次实现会再次形成大 overlay。因此 Slice 4 拆成可独立验收的纵切：

- 4A：双组连续指标比较 + 建议分级 + 多 Finding 综合；
- 4B：时间序列；
- 4C：预测与探索性 Python 边界。

本文件只声明 4A。

## 2. 分析规范

调用方必须显式提供：

- `metric`：连续数值指标；
- `group`：恰好包含两个比较组的字段；
- `analysis_unit`：独立观测单位；
- `question`：用户问题；
- `recommendation_intent`：`none | investigate | act`；
- `action_risk`：`low | medium | high`；
- `reversible`：候选行动是否可逆。

关键统计语义不从自由问题文本中猜测。方法执行本身不需要用户许可。

## 3. 方法契约

- 非空完整案例上计算每组 n、均值、中位数和标准差；
- 主估计为“第二组均值减第一组均值”；组顺序稳定且在答案中显式说明；
- 使用 Welch t 区间与检验，不假设等方差；
- 输出 95% CI、Welch 自由度、p 值和 Hedges g；
- Mann–Whitney U 仅作分布敏感性诊断，不替代主估计；
- 每个分析单位必须只出现一次；重复单位在 4A 发布 `limited`，不把行误当独立样本；
- 不使用固定 `n < 30` 或单一正态性门槛；自由度、零方差和可识别性决定方法是否可用；
- 正向差异最多为 inferential，不得解释为组别导致结果变化；
- CI 跨 0 或 p 不达阈值时形成 `null_result`，仍发布效应估计、区间和组别描述。

## 4. Finding 设计

- 每组生成一个 descriptive `estimate` Finding；
- 可靠差异生成一个 `group_comparison` Finding；
- 无可靠差异生成 `null_result` Finding；
- 数据或设计限制生成 `limitation` Finding；
- core Outcome 只由 `group_comparison | null_result | limitation` 计算，不能被组均值 Finding 虚假推进；
- 箱线图绑定全部组描述和比较 Finding，正文邻近显示。

## 5. 独立建议决策

统计方法不写建议。Recommendation Policy 单独读取结构化输入：

```text
recommendation_intent
outcome_status
finding_kind / maximum_claim_class
action_risk
reversible
known limitations
```

输出：

- `none`：用户没要求建议，或证据不足；
- `investigative_next_step`：需要补充随机化、纵向或机制验证；
- `operational_action`：仅在用户明确要求行动、风险低、可逆且证据足以支持该具体动作时允许。

4A 的观察性组间差异不能支持“改变组别会改善指标”，因此即使用户请求行动，也最多给出有条件的低风险验证步骤，不给出因果式业务动作。Null result 不生成“没有差异所以无需行动”的越界结论。

## 6. 验收重点

- 强差异、零结果、重复单位、零方差和缺失值均有确定性测试；
- 组别顺序、差异方向、CI 和效应量身份一致；
- descriptive Finding 不能让 core comparison 虚假完成；
- 用户只问事实时无建议块；
- 请求行动时观察性结果只生成调查/验证建议；
- 建议块必须绑定 Finding，且 claim class 不超过支撑上限；
- 箱线图正文显示并可刷新恢复；
- SSE 先显示方法进度，再显示校准答案；
- 不调用真实 provider，不接管旧主页面，不生成 Gate E/F 产品完成凭证。

## 7. 验收记录

- 强差异、零结果、重复分析单位、非双组、小而可识别样本及缺失完整案例均有确定性覆盖；
- 两个 descriptive 组均值 Finding 不能完成 core comparison Commitment；
- 用户不要求建议时不生成建议块；请求行动时观察性差异只生成验证步骤；
- 浏览器实测通过上传、语义 SSE、Welch 结论、正文箱线图、建议降级及刷新恢复；
- 图表绑定两个组描述 Finding 与核心 comparison Finding，答案块绑定核心比较事实；
- 本阶段只完成 Slice 4A。时间序列、预测和 `run_python` 探索边界仍属于 4B/4C，未声明完成；
- 未调用真实 provider，也未生成 Gate E/F 产品完成凭证。
