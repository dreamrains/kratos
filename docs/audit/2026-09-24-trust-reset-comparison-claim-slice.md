# 可信发布重置：compare_periods 比较 claim 垂直切片

日期：2026-09-24。实施基线：`main@ff0d4e6c2cfe21a153beaef8ab6d5c58031a4afb`。本切片只扩展现有 `answer_bindings.v1` 与发布包；没有新 planner、账本、浏览器框架、审核模型调用或真实 Provider 调用。

## 为什么选择这一族，而非全局散文数字正则

三份原始需求要求保留可复算的比较与必要口径，同时不让“同比”“显著”“变化”之类散文标签授权未执行的推断。历史 R11 的正确 M02 边界曾被散文门误删，R14 M05 有 CV 算术矛盾，R16 M03 有“同比例”误判与样例推断；R7—R21 的测试量上涨并未证明这些开放语义门可收敛。R4 是中途停止的部分证据，不当成唯一反例。本轮还只读查看了旧真实会话中长篇多指标、拟合和 LTV 请求，不把旧答复当正确 oracle。

真实 `compare_periods` 工具的无维度输出是 `metrics.<metric>.period_a/period_b/diff`，另有 `period_a/period_b.range`、日历天数及 `comparability`；先前顶层 `period_a.value` 只是简化夹具。新增测试既按真实工具源码的完整结构构包，也直接调用该工具函数，避免按单一旧夹具设计协议。

## RED → 结构化替代物 → 将退役的旧门

- RED：现有 parser 将 `claim_type=comparison` 当普通 binding，唯一占位符仍被判 `unbound_claim_placeholder`；错差额、跨回执拼接、字段顺序错和单位/窗口不符均无专属拒绝。五条聚焦 RED 为 5 failed。
- 结构化替代物：`answer_bindings.v1` 中的 `comparison` block 只含唯一无数值占位符、`computed` 状态、`not_confirmed` 单位状态、一个当前 `compare_periods` 回执 ID 和**按 A/B/diff 排序**的三个 fact ID；`requirement_refs=[]`，不擅自给用户子问题 `answered`。宿主限定三个事实来自同一 source、同一嵌套指标，校验有限数值与四位舍入上界内的差额，复核该回执的两个 ISO 日期窗口及日历天数，并在占位符原位渲染 A/B/宿主复算差额。不同天数在同一表格附近注明仅为原始数值比较。未知单位保持原始尺度，不转换百分比；不渲染模型自报的同比、显著性、因果或预测状态。渲染前再次校验，避免 parse 后快照变化。
- 旧门退役范围：这类比较结果不再由模型散文中的数值、时段和“同比”字样反向拼装权威表格；现有其他开放语义检查没有被整体删除或另添措辞词表。一次修订后如其它散文失败，独立可信 `comparison` 可由原有局部发布路径保留。

## 证据与剩余边界

新增测试覆盖真实工具输出、错差额、跨回执/字段顺序、窗口/单位、零值与四位舍入、不同天数披露、渲染前变更、局部发布保留。六个相关文件的定向离线回归为 **208 passed**。fresh `tmp/tprb12` 全量离线为 **2889 passed、1 skipped、16 warnings、0 failures**；JUnit `tests=2890/errors=0/failures=0/skipped=1`，SHA256 `C43989CEE262B1C674930D366DCBF05585150472646BC64D6541F1D422913084`，runner `provider_calls=forbidden`。这只能称 E2，不能称 E3 浏览器或 E4 真实 Provider。

此切片**没有**关闭无绑定自由散文中的数字或过强定性结论：有效比较占位符旁仍可能出现另一个未经 claim 授权的数值。不能靠追加比较/日期关键词或末尾免责声明掩盖；后续应继续按 claim 族扩大宿主渲染与确定性边界，并用正确候选保留率检查误伤。带维度的 `comparisons[]`、日均值/百分比、显式子问题的覆盖证明、已确认单位、多回执指标选择与开放因果语义均未纳入本次硬验；Shadow 仍是离线协议，不是发布总门。真实 Provider 仍须新的精确冻结和用户显式授权。
