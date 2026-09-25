# Phase 9 完整真实矩阵 R1：M01 后的授权停止

状态：`executed_partial / authorization_blocked`，**不是** M01—M06 完整 E4 验收。原冻结批次不恢复、不局部重跑；如继续，须新隔离目录、完整矩阵和冻结后针对具体数据/端点的明确授权。

## 冻结及本地前门

- 源提交 `main@964694bf41d2c82fcf7b0c83ffa0bef882289d24`，启动前工作树 clean，`959ea6a` 之后仅有审计文档改动。定向回归 73 passed；fresh `tmp/phase9-full-offline-20260926-r1` 为 **3015 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `DC29B76B650FCFBBF0322D720D7420A8B7FB5EDB7F43022B6223881DECE78A8A`，Provider transport forbidden。当前运行时代码等价的完整 Provider-disabled E3 见前次 `tmp/trust-reset-stage-e3-20260925-r2`（16 会话、实际 Provider 0）。
- 零调用 `tmp/phase9-p08-real-20260926-r1/freeze.json` SHA256 `B6CBC0CC94F860F99F7CAC4C48FF6EA68ED82B7008896C206811716325510F68`：`p08.real_matrix.v2`、固定 M01—M06、十份合成 CSV、模型 `openai/deepseek-flash`、端点 `https://api.deepseek.com`、最多 **120** 次物理发起、one-shot/无重试，账本同目录 `provider-calls.jsonl`。合同文件 SHA256 `C0674E431D4D535E9CA16C4475E51B0D2AD74E6EB5A85026D1F78F74EAEED797`；完整提示、oracle、操作及夹具摘要均在冻结文件。冻结后账本和会话目录均为空。
- 原入口 `run_p08_real_matrix.py --authorized` 在端口 **5239** 启动，OS PID **12756**、Codex exec session **83373**；`/p08-freeze` 返回 200 并匹配 HEAD/模型/预算。仅用 Codex `iab` tab **8**，上传经可见标签及 `filechooser`，无其它浏览器栈。

## 实际执行与停止

| 场景 | 实际边界 |
| --- | --- |
| M01 | `b362e4f895dd`，12 行/总额 120/单位未知、范围和条件建议可见；run_state `completed`，刷新后正文保留。当前只读 auditor 的整篇数字仍 `unassessed`，`host_rendered_claims=0`、自由散文 `not_audited`；不得把其方法、置信度和行动建议自动升格为完整质量通过。 |
| M02 | 仅在新的 UI 草稿中附加本地合成 `M02-retention.csv`；发送冻结提示时自动审批拒绝，**消息未发送**、未建 M02 会话、无 M02 Provider 调用。拒绝理由：本轮用户笼统的提前授权未在冻结后明确覆盖这份 payload 发往外部 DeepSeek。未改用终端/API 等间接执行。 |
| M03—M06 | 未启动；不把旧归档、E3 或 M01 结果倒填为本批通过。 |

账本最终 **11 started / 11 dispatched / 0 failed**，最高 call_number 11，SHA256 `5821B29AD5EC54A2401F2F8FE13C0DAAE2ECA63305CA6708CAD010C8297C3A23`，无更多发起。浏览器 console warn/error 为 0；临时 tab 已关闭，同一 exec session 停止服务，端口 5239 无监听。M01 是有效的局部观察，但矩阵完成条件与总计划完成定义 #14 **未达到**。这次停止由自动审批造成，不表明 M02 产品逻辑失败。

## 后续门

在不改代码与固定矩阵的前提下，新建 fresh run-dir 和零调用冻结，逐项核对新 HEAD、SHA256、端点、十份合成夹具、六场景 prompts/oracles、120 上限及账本路径。因自动审批要求**冻结后具体授权**，在发送新批次第一条消息前，向用户展示完整身份并取得对这些合成数据经本地应用发往 `https://api.deepseek.com` 的明确授权。授权后按 M01—M06 完整执行；普通失败批末统一分析，账本、隔离、事件完整性或全局服务故障即停。正式默认发布和 Phase 5/C、Phase 6/D、Phase 7 退出状态保持原判。
