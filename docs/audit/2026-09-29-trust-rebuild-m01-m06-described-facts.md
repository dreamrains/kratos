# M01/M06 描述回执事实绑定与局部审核入口

日期：2026-09-29。实施树 `codex/trust-rebuild-20260927@4bb7f85` 加当前保留的未提交变更；固定供体 `main@b181646` 未写入。对应[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)联合包 B/C 的局部切片，不表示全局 R3/R4/R5 通过。

## 代码边界

- `build_publication_packet` 只从本轮选中的 `describe_dataset` 来源，或选中 EvidenceRecord 的**精确结果绑定**，取当前版本、结果摘要与同数据集身份；再从当前 workspace 重算记录数、唯一数值列原值合计和唯一日期列的含首尾日历天数。原始描述回执、已登记摘要、当前数据身份或字段不一致时不生成 `described_tables`。
- 仅在既有曲线/聚合/比较宿主部分未命中时，`build_basic_summary_host_claims` 把单个描述观察放入原 `answer_bindings.v1` 的 `observed_basic_summary`；renderer 二次核对 block 与 packet 同一观察。模型候选的错误数字、净收益和立即行动不参与宿主事实。
- 该宿主路径不再用 `validate_final_narrative_issues` 对整个模型段落投票，也不把通过词面检查的整段散文附在事实后。候选以 SHA/原文保存在同一 packet 的 `candidate_resolution=withheld_pending_semantic_binding`，现有 `publication_audit_view.v1` 可对当前嵌套回执和候选定位，`publication_effect=none`。旧散文门在无宿主 block 的其余路径仍在调用，不能称全族退役。
- 本切片只验证原始记录的值和日期。M06 选 B 仅是成本范围决定，`F-SALES` 无成本金额或增量效果；没有把净收益 120 当成已算。M01 当前条件行动及正确开放解释的正向发布仍未闭合。

## 本地正常 app 收据

控制路线事前选为 `local_http_api`，全程 Provider 禁用；浏览器 picker、视觉和刷新 oracle 均 `unassessed`。第一次 `tmp/m01m06-described-app-20260929-r1` 用现有聚合脚本，M01/M06 都由 `transform_data` 宿主 claim 正确交付 12/120，但未触发描述回执；该运行身份原样保留。`r2` 加描述情景后命中目标路径。审核视图接线改变代码后，用全新 `tmp/m01m06-described-app-20260929-r3`、端口 18753 完整重跑同一两情景；下列只以 r3 为本切片结果。

- 启动前核对 rebuild worktree/HEAD、`.venv/Scripts/python.exe`、既有 `run_p7_browser_rehearsal.py`、新目录不存在及端口未监听。既有 launcher SHA-256 `cf726fced6d5d8aceff6d5da2fe77e1cacfab284e770b44a3eff073fda39ec17`；有界 HTTP 控制器 `tmp/m01m06_describe_http_probe.py` SHA-256 `c6585b7f45ca0616e40dfb386c8a3af74b207fe23ed343e31543750e3655b126`。服务 exec session `11631`、listener PID `2440`；前后健康均 `ok=true/provider_enabled=false`，结束后服务已停止。
- M01 session `24c804ba996b`：上传票据文件名/SHA 与 `F-SALES.csv` 一致，单轮 SSE 一个 start/一个 `turn_end=completed`，持久状态一致。选中 EvidenceRecord 回溯当前 `describe_dataset`；`observed_basic_summary` 发布 12 行、`amount` 原值合计 120、2026-09-01 至 2026-09-12 含首尾 12 日，单位未确认。脚本候选称“11 天/立即扩大投放”，仅留在 packet，不进入导出。
- M06 session `a69a9289c50b`：同文件独立票据，确认问题先 `suspended`，只恢复含代金券及渠道成本的 B 选项，同会话后一轮 `completed`；各轮 SSE/持久终态一致。当前 `describe_dataset` 宿主发布相同 12/120/12 日，并说明成本、增量及净收益未绑定；脚本候选称“11 天净收益 120/立即扩投”，未进入导出。B 选择没有被当作数值来源。
- 同两条已持久会话只读构造现有 `publication_audit_view.v1` 和有界 `publication_audit_request.v1`：各 `ready`、1 个宿主 claim、1 个有精确 SHA/回执/12 行输入的扣留候选、`publication_effect=none`。篡改嵌套 EvidenceRecord 的结果 SHA 会使审核视图 `unavailable`，不扩大权威。没有发起 Shadow/Provider 调用，也没有把诊断 pass 当作发布许可。
- r3 `describe-http-result.json` SHA-256 `7c03b605545ef3477b318cf4027b495590764d270e0bac8afdbd9a71d407f622`；`runtime.jsonl` 26 条，SHA-256 `3125884517a5e6d924f18b34daecf23c0ad4b339b5afca371351e4207a0a00a8`，`forbidden_provider_transport=0`，实际 Provider initiated **0**。M01/M06 Markdown 导出 SHA-256 分别为 `f89dc47a198931f5ebcd4aa21c3efdef3ac821ab27b4186e5b5918f1c61b3e6c`、`1b82c076521b125fc0f93de47e399f07f07bf5235c8c095bfded08f5ed631bae`，两者均无错误候选正文。

定向 `test_basic_summary_binding.py`、`test_publication_audit_view.py`、`test_hypotheses.py` 为 33 passed。完整 E2 结果另记于唯一当前计划，不能替代自然模型或视觉验收。当前切片是 Provider 禁用正常 app 的 E3 局部证据，不是完整 M01—M06 矩阵。后续须让正确开放解释与完整条件行动在正例中可交付，同时让无据强断言仅局部受限；另冻结 Provider 批并获明确授权前不做真实调用。
