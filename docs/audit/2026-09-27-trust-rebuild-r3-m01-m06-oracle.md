# R3.4 M01/M06 正常 app 基线与待决设计

日期：2026-09-27。重建树 `codex/trust-rebuild-20260927@0eb5c36`，供体 `main@b181646` 固定只读。R3.4 在 R3.3 本地切片之后启动；本文件只记录本轮实测，未把 Provider 禁用 HTTP 路线称为可视或真实 Provider 验收。

## M01 独立判据及 A 批

`F-SALES.csv` 的独立输入为 2026-09-01—12 共 12 行，每行 `amount=10`，因此 `amount_sum=120`、`amount_count=12`；金额业务定义和单位未知。聚合派生表只有 1 行，不能与源记录数混同。六轮同会话依次请求事实与有条件建议、业务负责人、分析师、管理者、大白话、技术表达；每轮需保留正确数字/方法/范围，不推断数据来自真实交易或代表总体，表达请求本身应有实际变化。任何触发或停止阈值还须与当前窗口和证据可比；不能把 12 天总额作为下一周的无解释基线。

控制路线在批前选为 `local_http_api`，使用现有 Provider 禁用 `run_p7_browser_rehearsal.py`、`/api/upload`、`/api/chat`、SSE、持久会话和 Markdown 导出；控制器 `tmp/r3_m01_http_probe.py` SHA-256 `CD607059FCFD3C10415E273188B928FD74F45FBCF6FD953EFC747FB7C8EF9BED`。工作树/入口/空目录/端口已核，服务健康 `ok=true/provider_enabled=false`。

A 批 `tmp/r3m01a`，监听 PID 10936、exec 99161、端口 5234，会话 `fbe09661d5e2`。上传票据 SHA 与文件一致；六轮均 `completed`、单一 `turn_end`、均包含源 12 行/派生 1 行、amount_sum=120、amount_count=12、非空原值求和方法、业务单位/定义未知及描述性限制。所有六轮答案 SHA-256 均为 `33e0aceaa852ba429eb1d27af2499cc34d5fcd31923d4cd0faea1bb111b87466`，因此五种重述没有实际生效；会话只有一个 ready publication packet，候选解析为 `superseded_by_current_receipt_claims`。六轮正文均进入导出；无 pending confirmation，`runtime.jsonl` 无 `forbidden_provider_transport`，真实 Provider initiated 0。结果 JSON SHA-256 `230742360731fa2a54e12b89737ee9b27d4390d3cc537ff46125dd195664a0c0`。服务已按 exec session 停止。

这批是**数值/方法保护通过、表达与建议交付失败**，不能称 M01 全过。候选自由文中“下周金额低于 120 则复核投放”等规则将 12 天窗口与下一周比较，且没有可验证的投放效果；不能直接附回宿主数字答案。后续需要在既有 publication packet / `answer_bindings.v1` 中对表达和有条件建议明确允许的结构、证据范围、时间可比性与失败时的局部保留方式，再由正常 app 验证。不得用词表、尾注、待核标签或删除正确事实凑通过；开放解释的审核边界与 R4 协同。

## M06 独立判据及 B 批

独立情景为 `missing_orders` 不存在时不给数值、不宣称完成、只给一个具体下一步；另一情景是用户选择“仅代金券成本”或“代金券及渠道成本”会改变净收益口径，需真实业务确认一次。选择后仍应把已算订单总额 120、未计算促销增量/成本/净收益和缺少数据导致的证据不足分别呈现；用户选择不替代成本数据，skip 不授权，技术方法审批不得阻塞。

B 批预先选 `local_http_api`，仍用同一 Provider 禁用演练服务，但新目录 `tmp/r3m06b`、端口 5234、PID 5212、exec 48786；控制器 `tmp/r3_m06_http_probe.py` SHA-256 `18482118288227F8EC18C82A4BD12668100284A89F7D827557CC2224ABCBFA50`，固定 HEAD `0eb5c36`。两个独立会话按顺序执行，未将其冒充正式 M06 两轮同会话矩阵。

- 缺失会话 `aac89af653f6`：脚本真实调用不存在的工具目标，收到工具结果后以 `completed` 单终态回复“所需数据集未找到，未发布计算结论；请先加载可用数据后再分析”。没有编造金额或完成分析；下一步动作只有先加载数据。
- 成本会话 `27505718ff83`：上传 `F-SALES.csv` 票据 SHA 匹配。`metric_scope` 的真实业务问题以 `suspended` 终态给出两种成本范围；控制器只选择“代金券及渠道成本”，以原 confirmation ID/version 和一次 idempotency key 调用 `/api/chat/resume`，同会话 `completed`。确认快照 `integrity_status=ok`、`decision_kind=metric_definition`、`status=resolved`、响应 ID 与本批一致，5 个事件；方法许可没有阻塞。两个会话的最终回复均进入各自 Markdown 导出，SSE 与 run state 终态一致。
- 该成本会话没有数据工具回执或计算结果；恢复正文只说口径回答已复用，没有交付 120，也没有把未计算净收益与缺少成本数据的证据不足分开。故**确认生命周期通过，M06 内容未通过**。用户选择并未提供成本金额，不能把未算项当 0。`runtime.jsonl` 无 `forbidden_provider_transport`，实际 Provider initiated calls 0。结果 JSON SHA-256 `8768a6a724af2d5acbe8176bbf4fc56613cfa497a696f09947b83b956b32b303`；服务已按 exec session 停止。

M01/M06 共同暴露：宿主当前数值保护有效，但开放的表达、条件建议和缺失项交付没有可信结构；不能用已有候选散文直接追加，也不能用空泛“待核”遮盖。下一步与 R3.5 需求状态及 R4 受限解释一起设计同一 packet 内的可核数值、明确未算、证据不足和可比条件；保持现有确认内核和正常 app 路径。两批均为 Provider 禁用 HTTP app，视觉、自然模型、正式 P08 与外部发布未评估。
