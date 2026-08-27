# Slice 1 R07 冻结与本地 Web 闭环收据（已完成，Provider 除外）

## 边界

- 基线提交：`b2f97f9574efb9d6cb84ae8defd86b774cd0ffb0`（Slice 0）。
- 场景：D03 `savings_card_orders`，唯一输入为 `reference/test_doc/省钱卡订单.xlsx`。
- 本文记录离线确定性契约与当前源码的本地 Web 浏览器收据；不是实际 Provider、预发布或发布通过收据。
- Provider 消耗：0。
- 当前受控源码摘要：`sha256:30c6215898764fda9430ad343308751b4d2abfea61ea3676dea935db21ac1e9b`（311 条；提交前的 Slice 1 源码与测试）。

## 冻结问题与 oracle

问题：`请分析省钱卡订单的购买趋势、异常和产品结构，并生成日收入趋势图；说明口径与限制。`

口径固定为支付时间、售价、商品名称；按日完整自然日历（包含零订单日）聚合。可复算 oracle 位于
`tests/real_data/slice1_r07_oracle.json`：

- 71 笔订单、63 位用户、总收入 2502；
- 2026-04-07 至 2026-05-06，共 30 个自然日，26 个有订单日；
- 零订单日：2026-04-19、2026-04-28、2026-04-29、2026-05-05；
- 前 15 天收入 1818，后 15 天收入 684；峰值为 2026-04-08（339，9 笔）；
- 产品收入：月卡 2250、周卡 252。

这些是描述性聚合结果，不支持“某因素导致收入变化”的因果结论；观察窗口短且样本量有限。

## 已实现的公共契约

1. **持久化先于发布。** LLM 文本按轮缓冲。最终答案会先归档并保存，再向浏览器发送文本；SSE `turn_end` 前也执行持久化。中间工具轮的可见文本同样先保存。
2. **图表不是自证。** `purpose=evidence|insight` 的图表必须来自已注册会话数据集，且全部 `evidence_ids` 必须解析到当前 `AnalysisSessionState.evidence_records`；模型拼出的 `data_json` 只能作为 exploratory 图。
3. **数据身份随图表持久化。** 图表元数据记录当前数据集、派生父集、原始路径与源指纹。
4. **已确认结论是 source-bound。** Workbench 仅投影当前证据指纹对应的验证报告中 `passed_evidence_ids`。缺少验证、报告陈旧、失败或降级的项不会显示为“已确认”。
5. **执行 receipt 绑定。** 每个成功工具调用会生成带工具名、参数摘要、结果 SHA-256、结果预览、数据集引用和调用 ID 的 session receipt。EvidenceRecord 将其 `tool_calls` 解析为本轮 receipt；引用未在本轮成功执行的工具会失败，而不是由模型自证。
6. **R07 最小闭环。** 测试以 D03 真实文件生成补零日趋势表，创建具方法/样本/窗口/限制且绑定 receipt 的 EvidenceRecord，绑定证据图，运行确定性验证，并验证该记录才可进入 confirmed projection。

## 仍未完成，不能提前宣称

- 成功工具结果到 receipt、EvidenceRecord 到 receipt 的绑定已经实现；但工具结果到“自动生成可读 EvidenceRecord”的映射尚未实现。当前仍要求模型选择并说明主张、口径与限制，系统只保证它不能引用本轮没有执行的工具。自动映射需要逐工具定义语义，不能把任意 JSON 结果粗暴升格为结论。
- 未运行真实 Provider；不能据离线 oracle 推断模型规划、工具选择或回答表达已达标。
- Workbench 的 UI 删除属于 Slice 6；本 Slice 仅收紧它当前的“confirmed”投影语义。

## 当前验证结果

- 离线回归：receipt + analysis flow + analysis state + execution control 为 **109 passed, 1 warning**；D03 R07 oracle 为 **4 passed, 1 warning**；SSE + trust/workbench + chart 为 **61 passed, 1 warning**；可隔离 Web 回归为 **128 passed, 1 warning**。
- 前端语法：`node --check src/data_agent/web/static/js/app.js` 通过。
- 当前源码真实浏览器（本地 Flask `127.0.0.1:5127` + 本地 OpenAI-compatible stub）：在用户逐项授权后上传真实 D03 `.xlsx`；完成后显示受控长回答、补充图表、1 条已验证证据和 `pass`；刷新后以 URL session ID 恢复相同正文与已确认结论；HTML 导出返回 `exported` 且“产出与导出”显示 2 个产物；本地延迟响应下点击停止后显示“已停止。”与 `Turn interrupted by user`；控制台 **0 error**。
- 该浏览器旅程验证的是上传、会话、工具执行、证据/图表/已确认投影、刷新、产出与停止的实际本地 Web 链路。回答文本由本地受控桩提供，只能证明流程与数值绑定，不能证明真实 Provider 的规划或表达质量。
- `tests/test_web_gui.py` 不是可隔离 pytest 测试：导入时直接访问固定端口 `5001` 并运行整套脚本，在当前环境把错误响应当会话列表解析，收集阶段失败。它不能作为本次失败或通过的证据，需在 Slice 6/7 改造成受控进程测试。

## 下一个受控步骤

进入 Slice 2：以 D04、D05 的真实数据和冻结 oracle 审阅脏数据、配对分析、版本与确认边界；仍不消耗 Provider。自动 evidence projection 仍需逐工具定义语义，不能使用通用字符串抽取伪造“自动化”。
