# Data Agent V2 Slice 5C5T：受控 needs-input 资格合同

## 目标

修复 5C5S 的共享 Planner 决策缺口：模型不能只凭自由文本声明需要澄清；服务端必须能够证明某个受支持方法缺少哪一项受控前提。该切片不调用 Provider，不增加 repair、重试或 fallback。

## RED 基线

聚焦回归在实现前稳定失败：

- 完整上下文中的 `needs_input/multi_finding_synthesis/missing analysis_unit` 被旧 compiler 作为 unexpected fields 拒绝，无法给出资格 reason code；
- 缺少 datetime 列的 time-trend 上下文无法表达 `pending_analysis_kind=time_trend` 与 `missing_prerequisites=[time_field]`；
- 旧 tool schema 既拒绝受控身份，又接受不带身份的自由 needs-input。

这三项证明缺口位于共享合同，不是 Provider transport 或单一响应样本。

## 实施范围

1. 从既有 required parameters、column role policies 和跨字段关系计算方法可执行性；
2. tool schema 对每个方法在 ready 与受控 needs-input 之间二选一；
3. compiler 重算资格并提供稳定 reason code；
4. 安全诊断仅增加受控 method/code 元数据；
5. Plan Ledger 与 HTTP 投影持久化 `pending_analysis_kind`、`missing_prerequisites`；
6. planner contract gate/preflight validator 接受数据集相关的 ready/needs-input 矩阵；
7. 更新 provider-neutral fixture、focused tests、设计记录和确定性证据。

## 明确边界

- 不保存或回显 Provider 原始响应、reasoning、参数值或问题文本到诊断；
- 不自动回答问题，不自动重新规划，不复用 authorization；
- 不把 column role 猜测升级为已确认业务行粒度；
- 不签发 real-provider、stability 或 human-semantic receipt；
- 不切换根入口、不删除旧系统、不提交、合并或推送。

## 验证

- Planner focused contract tests；
- Plan Ledger 与 planning HTTP focused tests；
- real-provider preflight 的纯确定性 validator tests；
- V2/config 全量确定性测试；
- compileall、`git diff --check` 与 release source digest。
