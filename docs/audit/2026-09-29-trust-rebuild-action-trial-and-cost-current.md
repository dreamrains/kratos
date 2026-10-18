# M01 试验审核正反与 M06 当前成本输入复核

日期：2026-09-29。实施树 `codex/trust-rebuild-20260927@4bb7f85` 加保留的未提交改动；供体 `main@b181646` 只读。对应[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)包 B/C 的下一局部切片。所有 app 批次控制路线事前选为 `local_http_api`，使用既有 Provider 禁用演练入口；HTTP 上传 picker、视觉、浏览器刷新为 `unassessed`。

## 实施决定

- M01 的 `conditional_action_inputs` 仍仅证明当前两期数据、逐行 `gross−cost=net`、订单分母及来源版本，不能自行批准行动语义。试验审核仅在开关 `DATA_AGENT_SEMANTIC_AUDIT_TRIAL=1` 下审当前可定位候选；正确候选通过既有 `publication_audit.v1` 审核并实际进入最终答案后，才将同一 packet 中对应的**当前**行动需求标为 `answered/checked`。发布前再次核对 typed block 的当前需求顺序、回执、fact refs 和封闭两期输入；错误引用或审核 finding 不升级覆盖。
- `publication_packet_prompt` 把有当前 `compare_periods` 回执的条件行动 typed 提案从可选措辞改为明确要求，仍容许在 receipt、metric roles 或需求引用无法精确识别时说明具体缺口。该提示不把模型解释当事实，也不以词表/正则反向猜散文。默认审核开关和正式发布默认均未更改。
- M06 的可用成本计算已由现有 `metric_scope_formula.v1`、真实确认与 `observed_aggregate` 宿主重算实现；本轮复核该既有功能，没有创建第二条计算/确认链。文件给定的 `incremental_revenue` 列仍只可作为用户确认后的账面输入，不证明促销因果或货币单位。

## 本轮正常 app 结果

**M01 试验正反，独立运行身份** `tmp/r4trial-action-coverage-20260929-r1`，端口 18770，exec session `1338`，监听 PID `21508`，批前/批末健康均 `ok=true/provider_enabled=false`，服务已停止。沿用旧有界控制器的运行目录副本，SHA-256 `b48dc6c52d4c12a29fdaba497480e6fd65c378cfa717d408b7799c038a958ee6`；既有 launcher SHA-256 `cf726fced6d5d8aceff6d5da2fe77e1cacfab284e770b44a3eff073fda39ec17`。三情景独立上传同一 `F-ACTION.csv`，票据 filename/SHA 核对、各一 `turn_start`/`turn_end=completed`、durable 状态和最终答案 SHA 一致，均已导出。

| 冻结情景 | 会话与独立判据 | 结果 |
| --- | --- | --- |
| 正确未来双条件 | `fcd68dbc5e97`；宿主比较和输入块各 1，审核无 finding 后，完整“下一同口径七日且双条件→受控试验；否则暂停复核”、未来未观测及非因果边界进入正文。 | 候选 `semantic_review_passed_trial`，三个当前行动片段 `answered/checked`；比较四行原值保留。 |
| 引用顺序错误 | `3a70addc79cb`；模型 typed block 的需求引用顺序与当前 packet 不同。 | 输入块 0，候选扣留；三个行动片段仍 `evidence_insufficient/checked`，比较原值保留。 |
| 行动语义风险 | `b69f623be54e`；脚本候选把本期成本每单误作下一窗口条件已触发。 | 审核定位高风险候选，未放行；三个行动片段仍 `evidence_insufficient/checked`，比较及已核输入保留。 |

结果 `control.json` SHA-256 `f458d0b59bdde12cb4909107e2d8bcca8e8b0a652089e37119076ba08b3eefd2`；`runtime.jsonl` SHA-256 `e60374cf925af88bdeb9cf2af3d7f3542f314e349baea4ebeeb9d56a4e2be9ed`。脚本审核 transport 3 次，`forbidden_provider_transport=0`，实际 Provider initiated **0**。这只验证机制及脚本正反，不能证明自然模型提交 typed block 或自然审核的漏检/误报率；历史 `tmp/p08rb8` 的自然 M01 候选没有 typed block，且把未来规则误套到本期，仍是未通过的产品证据。

**M06 当前成本输入，独立运行身份** `tmp/m06-available-current-20260929-r1`，端口 18771，exec session `56672`，监听 PID `15596`；两组前后健康 `ok=true/provider_enabled=false`，服务已停止。既有 HTTP driver `tmp/r3_m06_data_http_probe.py` SHA-256 `78167a1ccfb6ed1e927495b38f8ea53cc6a1169c776c72344b5d3165975c1ea8`，依赖既有 stream helper SHA-256 `9819c630e84f1c562439e1d53e61cb2ebd0819d9f1fc8e9477b0881ca1768826`。两情景独立上传 `F-PROMO.csv` 并核对票据；首次真实业务问题 `suspended`，只恢复选定选项，同会话终轮 `completed`，SSE 与持久态一致并导出。

- 仅券会话 `7f654150d5c3`：现有 aggregate block 有真实确认引用，同版重算 `110−14=96`；四个当前 result/gap 需求均 `answered/checked`。结果 SHA-256 `0db1351d6fe32a0236f5dccbad797bc7a58dfa1b695ea4e6144cd5169fbd8a59`。
- 双成本会话 `1d7561c429cb`：同口径重算 `110−14−10=86`，覆盖同上；结果 SHA-256 `6d955284a4af190a7c28d4b2214ad844007426f9c8cc88911133ab8a99155630`。
- `runtime.jsonl` 29 条，SHA-256 `1924f0d5b13852c027f2288fb9275d518d569ba1d1b6786542c5eea5f4450f3c`；`forbidden_provider_transport=0`，实际 Provider initiated **0**。缺失、skip、旧确认版本等负向情景已有旧 HEAD 的六路径收据；本轮未把两正例称为全六路径或全 M01—M06 矩阵。

定向 action/audit/comparison 测试 30 passed。新目录完整 E2 `tmp/trust-rebuild-e2-20260929-r2` 为 **2964 passed / 1 skipped / 16 warnings**，Provider transport 禁止。R3/R4/R5 联合出口仍需自然模型正反、完整 Provider 禁用矩阵、视觉 oracle 与逐族旧门退役；新真实 Provider 批次须另作精确冻结并取得明确授权。
