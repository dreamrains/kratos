# \`ddb9daa\` 真实 Provider M01—M06 批次与批后修正

日期：2026-09-30。实施树 \`C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent\`，分支 \`codex/trust-rebuild-20260927\`；供体 \`D:\Project\Daily\data-agent@b181646\` 保持只读。本收据从属[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。

## 精确冻结与授权

候选提交固定为 \`ddb9daa9b3491793af08994324aa36ced9a25ac5\`，新目录 \`tmp/trust-rebuild-p08-real-ddb9daa-r1\`，控制路线 \`local_http_api\`，模型 \`openai/deepseek-flash\`，端点 \`https://api.deepseek.com\`，M01—M06 顺序执行，调用上限 120，\`one_shot\`，语义审核关闭。上传 picker、可视正文/图表和浏览器刷新为 \`unassessed\`。

冻结文件 SHA-256 为 \`c38899b2444d3d461bb87198242c8685a50944b0f0aa348487931b1641273e65\`；HTTP driver 为 \`sha256:640c70c392496ccb28a58c83c1fbae430f142c2b6f4a2fa4b03bd7f3f36805d7\`；合同为 \`sha256:c4afd69178ea07166d0ca9001dc047c4f2d7757f30dd64b4cc29ce30e7d857f3\`；矩阵计划为 \`sha256:24b70af71f16396e69bf0df1059004c9a14ac0213b2250a1bcda4b106fa58043\`。

用户随后精确授权：向该端点发送 \`ddb9daa\` 的 M01—M06 冻结输入，最多 120 次 Provider 调用。服务端口 18787，监听 PID 22316；批次按冻结顺序一次执行，没有重试或局部续跑，服务在证据收集后关闭。

## 账本与场景结果

\`provider-calls.jsonl\` 记录 91 started、91 dispatched、45 completed、46 stream_exhausted，0 denied、0 failed、0 stream_failed、0 stream_closed；所有 started 均有唯一结束记录。账本 SHA-256 为 \`f4ee7e27c44724c291ed9b23575c7d649ea98186fe63d08b22f42564ac493898\`，HTTP 矩阵 SHA-256 为 \`ecd9e20d02788bed377b198fb59a7b88881e0e8fad67c7bce57ff15a6990031b\`。

| 场景 / 会话 | 结果与独立 oracle 判断 |
| --- | --- |
| M01 \`3a403c1a12e8\` | 两轮及持久重载 completed，累计 17 调用。比较轮保留 700/770、140/175、560/595、70/77、AND 条件、未来未观测和非因果边界。首轮同时出现正确的 12 行/120/单位未知和错误的“跨 11 天”散文；同 packet 中存在 Python 来源时，基础摘要 builder 错误地让 Python 路径压过更强的 \`describe_dataset\`，且该 Python 结果使用 \`amount_total\` 而不是旧 builder 预期的 \`amount_sum\`。M01 因封闭日数仍落回模型正文而不通过。 |
| M02 \`8568a5c2bd40\` | completed、导出和持久重载成功，累计 30 调用。D1—D7 原始值、D7 \`0.1\` 单位未知、模型族/R²以及 D30 无真实观测、无 holdout/backtest/external 验证的边界均保留；该批的非视觉 oracle 满足。 |
| M03 \`8d2f7005ee60\` | 六源比较值在工具阶段已产生，随后宽表 pivot 把日期值变成 pandas \`Timestamp\` 列名，workspace/回执 JSON 边界抛出 \`TypeError\`；没有唯一正常终态，持久状态为 unknown，累计 40 调用。M03 不通过。 |
| M04 \`d7903d35b1e5\` | v1、v2 两轮及持久重载 completed，累计 58 调用；当前描述关系和版本变化链路可执行。该批没有暴露新的 transport/session 问题；完整自然假设 oracle 仍以持久分析状态和后续整批签收为准。 |
| M05 \`4fd2b9c7daf1\` | 六轮均 completed、导出和重载成功，累计 79 调用。答案保留 12/120/日期范围/单位未知，但均由自由正文写成 11 天；\`run_python\` 返回 \`order_count\`、\`amount_sum\`、日期上下界而没有通用 \`rows\`，旧 builder 未生成宿主 block。M05 不通过。 |
| M06 \`f36f3e3a094c\` | 第一轮缺数据回答给出“上传缺失数据”或“改分析 M01”两个动作，违反唯一下一步；第二轮正确发出成本口径确认并暴露稳定值 \`voucher_only\`、\`voucher_plus_channel\`，冻结 driver 却按易变标签前缀 \`B.\` 定位，安全拒绝恢复，最终 suspended，累计 91 调用。M06 不通过。 |

**批次结论：不通过 R3/R4/R5 联合自然验收，也不构成完整浏览器 E4。** M03、M05、M06 有明确失败，M01 仍有封闭日期算术漏放；M02 的局部通过和 M04 的正常执行不能折算为整批通过。

## 批后结构修正

修正保持原 \`answer_bindings.v1\` 为唯一发布绑定：

1. 宽表 pivot 在持久化前把列名规范为字符串，使日期列可穿过 workspace/回执 JSON 边界。
2. 基础摘要优先使用同 packet 的已核 \`describe_dataset\`；Python 路径缺少 \`result_data.rows\` 时，由宿主从同版本当前 frame 重读行数，并继续核验已有 sum/date facts；日期范围由宿主计算和复核含首尾日数。
3. 缺失数据集要求使用精确当前命名绑定；\`list_data\` 回执与当前 workspace 清单共同生成 \`missing_dataset_gap\`，宿主只发布一个具体上传动作，不把模型的替代分析建议并入正文。
4. M06 driver 以确认选项的稳定 \`value\` 精确匹配；合同冻结 \`voucher_plus_channel\`，不再解析可变显示标签。

这些改动没有加入散文词表或第二 claim/planner/账本，也没有让模型正文覆盖结构化事实。

## 批后本地证据

Provider 禁用针对性批次 \`tmp/trust-rebuild-post-real-fixes-pd-r1\`、端口 18788：

- M03 pivot 会话 \`386f74011b4a\` completed 并持久化；
- M05 会话 \`8060f83e24d0\` 由宿主发布 12 行、120、2026-09-01 至 2026-09-12，**含首尾 12 个日历日**；
- M06 缺数据会话 \`58779329fef3\` 由宿主发布唯一上传动作。

三会话均有唯一 completed 终态。30 条 runtime 事件中 \`forbidden_provider_transport=0\`、Provider initiated 0；结果 SHA-256 \`6d0e62aded83a0c480743f5cb66ebbb37f63f29431029e6f34dd9084e075621a\`，runtime SHA-256 \`364517870755834164639f49dfbda41d85552ef7d8f0082b516f75929d5d7a94\`，服务已关闭。

定向相关测试 **98 passed**。新目录完整离线 \`tmp/trust-rebuild-e2-20260930-r5\` 为 **2982 passed / 1 skipped / 16 warnings**，JUnit 2983 tests、0 failures、0 errors，SHA-256 \`0aa290f2e9c64c001a1a70b37af941e944d998ef5183ca2241d7222119a4dc98\`。

这些是批后 E1/E2 和 Provider 禁用 E3 证据，不能倒填 \`ddb9daa\` 的失败 E4。下一次真实 Provider 必须先把命名修正和本收据整理为新的干净候选提交，再重新冻结精确输入、driver/合同、模型、端点、预算和新账本，并取得新的明确授权。正式默认与外部 Git 仍分别授权。
