# Data Agent V2 Slice 5C5U：分析单位语义确认合同

## 目标

关闭 5C5T 明确保留的业务行粒度缺口：粗粒度 column role 和字段兼容性不能证明哪一列代表独立观察单位。需要把用户显式确认的分析单位作为服务端拥有、可持久化、可恢复且可绑定授权的语义上下文，而不是让 Planner 根据列名猜测。

本切片不调用 Provider，不自动选择列，不增加 repair、重试或 fallback。

## RED 基线

实现前的聚焦回归证明了三个共享缺口：

1. 完整列角色上下文仍会把所有非 datetime/unknown 列暴露为 `analysis_unit` 候选，无法要求显式业务确认；
2. Planning Input Ledger 不能持久化受控语义解析，刷新和派生请求无法证明使用了同一份选择；
3. answers HTTP 会丢弃 `semantic_resolutions`，estimate、authorization 和 Planner 无法共享同一语义上下文。

## 实施范围

1. `DatasetPlanningContext` 增加唯一的 `confirmed_analysis_unit_column`，只接受当前数据集中的非 datetime/unknown 列；
2. analysis-unit 相关方法在未确认时使用受控缺口 `analysis_unit_semantics`，schema 不再向 Planner 暴露未确认列；
3. compiler 独立要求 Planner 的 `analysis_unit` 与用户确认列完全一致；
4. Planning Input Ledger 以受控 `prerequisite_code/column` 结构持久化不可变语义解析，并为历史事件提供空缺省值；
5. answers API 严格要求提交的语义代码与 source plan 缺口集合一致，并在写 Ledger 前验证列；
6. estimate、authorization issue、authorization consume 和 Planner 从同一个 `planning_input_id` 恢复语义上下文；数据、问题、问题块或语义解析漂移均 fail closed；
7. Workbench 显式显示候选列选择器，不自动选列；保存、重新估算和刷新恢复保持同一选择；
8. planner contract gate 升级为 v3，real-provider preflight 升级为 v4，并用数据集相关 ready/needs-input 矩阵绑定新 schema。

## 明确边界

- 列角色过滤只排除确定不合法的 datetime/unknown；最终业务含义必须来自用户确认；
- 语义选择不从列名、Provider 文本或历史失败输出自动推断；
- 未确认的统一 fixture 预检可以证明哪些方法受阻，但不能假装这些方法已经 ready；
- 不签发 real-provider、stability 或 human-semantic PASS receipt；
- 不切换根入口、不删除旧系统、不合并或推送。

## 验证

- Planner、Planning Input、Plan Ledger、planning HTTP 和 preflight focused tests；
- provider-neutral Workbench 浏览器旅程：needs-input、显式选择、无模型 estimate、刷新恢复；
- V2/config 全量确定性测试；
- compileall、JSON parse、`git diff --check` 与 release source digest。
