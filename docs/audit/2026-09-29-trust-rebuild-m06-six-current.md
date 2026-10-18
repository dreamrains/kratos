# M06 当前重建树六路径统一批

日期：2026-09-29。此文是[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)包 B/C 的独立收据。批前固定实施树 `codex/trust-rebuild-20260927@4bb7f858151d9e03dce0a78ec7316968d166b090` 加保留的未提交实现，供体 `main@b181646` 只读；`control_route=local_http_api`，Provider 禁用，run dir `tmp/m06-six-current-20260929-r1` 事前不存在，端口 18775 事前无监听。HTTP picker、视觉和刷新 `unassessed`。

## 批前固定输入与独立判据

现有 launcher SHA-256 `cf726fced6d5d8aceff6d5da2fe77e1cacfab284e770b44a3eff073fda39ec17`。三段现有控制器依序运行：`tmp/r3_m06_http_probe.py` SHA `9819c630e84f1c562439e1d53e61cb2ebd0819d9f1fc8e9477b0881ca1768826`，`tmp/r3_m06_data_http_probe.py` SHA `78167a1ccfb6ed1e927495b38f8ea53cc6a1169c776c72344b5d3165975c1ea8`，`tmp/r3_m06_negative_http_probe.py` SHA `032831a3723da4fe3661128eb044750a69c0f6a3d111df079cea1464c7599a7c`。`F-SALES.csv` 预期 SHA `1e6629876a79225fceac0b2dc0f1d16071e532ca989b842c0489afc082f8e59d`，`F-PROMO.csv` 预期 SHA `5fcc5baa350131fc427fb0e6957b0b0976e3c7491505714efa91ef883503ca1d`；运行时仍逐票据核对。提示与选择原样固定在控制器源码中。

执行顺序固定：缺数据、旧普通成本、仅券、双成本、skip、旧确认版本；每条独立会话，确认与恢复保持同会话。独立 oracle 沿用[原六路径判据](2026-09-27-trust-rebuild-r3-m06-available-input.md)：缺数据无数值或完成宣称；旧成本当前 120/含首尾 12 日、净收益未算；仅券账面 96；双成本账面 86；skip 不把未选成本填零或授权净收益，保留独立已核原值；旧版本拒绝授权。逐路径记录上传票据、唯一 SSE 终态、持久态、导出、当前需求覆盖与 Provider 禁用迹线。普通场景失败记录后继续，隔离/事件/服务失败才停止。本批不代替全 M01—M06、自然模型或浏览器视觉验收。

## 执行结果

现有服务 exec session `93659`、监听 PID `15040`。批前、分组前和批末健康均 `ok=true/provider_enabled=false`，批后已停止且端口释放。生成的两份 fixture SHA 与批前值逐字一致。四份控制结果 SHA-256 依冻结顺序为 `360b066bf84810d7ce0247e0a6f8b28eaf484c7e3bb571be7b271aba1369208f`、`b4bee7288b4b530d454a4673c854f33ec116fa7d25315b77a931e27849029821`、`4fe3fc57609954799f465afa91dc04cee2020416a1de0ed330ef456f074a9d4f`、`0cbb9b0f4f2f6ec16fed81e187b710ebe607f569dea571d7c33b03a1ac4c7f44`。`runtime.jsonl` 69 条，SHA-256 `387bd2178f894330ae599f49c33dec59019bdae8f5be5984056857a4954c90ef`，禁用 Provider 传输 0，实际 Provider initiated **0**。

| 冻结情景 | 会话与终态 | 当前答案及事实/需求判据 |
| --- | --- | --- |
| 缺数据 | `8073091f496c` completed | 指明 `missing_orders` 不存在，未发布计算数值或完成宣称，给出先加载数据的具体下一步。 |
| 旧普通成本 | `64004a183a11` suspended→completed | 原始 12 行、`amount_sum=120`、非空 12；真实 B 选择只有成本范围，没有成本金额，净收益 `not_computed/checked`，具体输入缺口 `answered/checked`。**同版答案缺少含首尾 12 个日历日，未满足批前 oracle。** |
| 仅券 | `cea81f813215` suspended→completed | 已确认 `metric_scope_formula.v1` 仅 `coupon_cost`，当前回执重算 `110−14=96`；四个原/续 result/gap 均 `answered/checked`，单位与因果仍未知。 |
| 双成本 | `e93017ca3de0` suspended→completed | 已确认 `coupon_cost` 和 `channel_cost`，当前回执重算 `110−14−10=86`；四个原/续 result/gap 均 `answered/checked`，单位与因果仍未知。 |
| skip | `27a85cc37a6d` suspended→completed | 原始 4 行、`order_amount_sum=120` 及四个输入列原值仍在；跳过未签发成本范围，净收益 `not_computed/checked`，具体缺口 `answered/checked`，没有把未选成本填零。 |
| 旧确认版本 | `3108509af4aa` suspended→failed | 恢复请求用 `expected version 1`，实际版本 2；明确拒绝，无授权净收益答案。 |

六个 session ID 唯一；每轮恰一 `turn_start` 与一 `turn_end`，终态与持久 run state 对齐；有上传的五条路径均逐票据核对 filename/SHA，确认/恢复保持同会话，各会话与 Markdown 导出可读取。**本批六路径未通过**：旧普通成本缺日期跨度。随后已在当前聚合源版本及 claim 中封闭绑定唯一 datetime 列的起止和含首尾天数，定向聚合/比较/摘要测试 34 passed；代码修正后须新目录完整六路径再验，不能单独重跑失败会话充当整批。

## 修正后完整复验的批前身份

仍用上述三个未改的控制器、fixture、六情景顺序和独立 oracle；控制路线仍是 `local_http_api`，Provider 禁用。新 run dir `tmp/m06-six-current-20260929-r2` 事前不存在，端口 18776 事前无监听。原 r1 保持失败记录，r2 独立评估，不合并 session 或结果。

修正后服务 exec session `31537`、PID `14168`，批前/分组前/批末健康 `ok=true/provider_enabled=false`，结束后已停止。六个独立 session ID、票据核对、每轮单一 SSE 终态、持久 run state 和导出均按同一控制器验证。`runtime.jsonl` 69 条，SHA-256 `a75dc617e4309ab164bc35bfbeb761f1448abf322d9fa189b7db454c5051c6f7`，`forbidden_provider_transport=0`，实际 Provider initiated **0**。四份控制结果 SHA-256 依顺序为 `4251a5aeb93ff3e15f300e4d2289ad0eab21be5698fa6a3aea0b111c2a624d3e`、`d431514fa7cd371f76c8f0fe2ff110b8bcee6cbf64e2ef5ecd24d327910fbd5d`、`9f9c9b385dd4bbf742fabd7d42054d7b804b98ccef2cccd989c80cb4563fde17`、`a8cec06b90e543d255ed2250fb4e76bc866a22b6a2a0fd325aca3769e8c84dc0`。

| 冻结情景 | 会话/终态 | 复验判据 |
| --- | --- | --- |
| 缺数据 | `7d0c13d0e8bc` completed | 无计算数值或完成宣称，提示先加载数据。 |
| 旧普通成本 | `e1c611321a36` suspended→completed | 同版宿主 claim 给出源表 12 行、`amount_sum=120`、非空 12，日期 2026-09-01 至 2026-09-12 **含首尾 12 个日历日**；确认 B 仅定范围，净收益 `not_computed/checked`，具体缺口 `answered/checked`。 |
| 仅券 | `a1ea74d45dd0` suspended→completed | 账面 `110−14=96`；四个原/续 result/gap 均 `answered/checked`，因果与单位未获授权。 |
| 双成本 | `f8da8b82a1f8` suspended→completed | 账面 `110−14−10=86`；四个原/续 result/gap 均 `answered/checked`，因果与单位未获授权。 |
| skip | `832f3ab3b242` suspended→completed | 保留 4 行/120 及输入列原值，净收益 `not_computed/checked`，未把未选成本填零。 |
| 旧确认版本 | `2c143ebf15fa` suspended→failed | `expected version 1, current version is 2`，无授权净收益。 |

按批前六项非视觉 oracle，**r2 完整批通过**。r1 的日期缺失仍保留为失败证据。该结论仅为脚本模型的 Provider 禁用本地 app 路线；自然模型、picker/视觉/刷新和全 M01—M06 仍未通过。

2026-09-30 完成新目录完整零 Provider E2 `tmp/trust-rebuild-e2-20260929-r4`：**2967 passed / 1 skipped / 16 warnings**，exit 0，Provider transport 禁止。
