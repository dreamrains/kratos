# R3.5 多轮计划身份与独立目标隔离

代码基线 `65b5db6`；目标树 `codex/trust-rebuild-20260927`。本轮控制路线在批前选定 `local_http_api`，用正常 Provider 禁用 app 的上传、聊天、SSE、持久会话及导出接口；浏览器 picker、视觉渲染和刷新均为 `unassessed`。没有真实 Provider、默认策略或外部 Git 操作。

## 机制与设计裁决

此前每轮 `select_playbooks` 从完整新输入生成 `analysis_spec.id`，即使是同一目标继续，也会替换当前计划。B04 的持续竞争假设和版本证据因此可能被新计划身份切断。改动让现有意图分类在有当前计划时提出 `continuation_of_plan_id`；宿主只接受与当前 ID 完全相同的引用，并在明确需求版本变化时清除延续提议。`apply_selection_to_state` 在有效延续时保留原计划、目标和任务身份，未引入第二 planner 或新模型审核调用。

初批 `tmp/r3plancont1` 因演练分类替身误从上下文历史匹配 B04 标记，第二轮生成另一计划。修正替身仅识别本轮 `用户输入` 后，完整 B04 批 `tmp/r3plancont2` 13 轮同计划，但同会话追加独立 B01/F-SALES 后仍挂旧 B04 计划。这是不同的产品根因：明确 `data_operation` 绕过 playbook 计划选择，普通 EvidenceRecord 又自动绑定当前 `analysis_plan.id`。裁决是在现有 `analysis_spec` 接口下，让已有分析计划后的独立数据操作取得新当前计划身份；旧证据和假设记录保持原计划 ID。没有用 B01/B04 词面、尾注或删除正确解释解决。

## 最终正常 app 批次

- 新目录 `tmp/r3plancont3`；入口 `scripts/testing/run_p7_browser_rehearsal.py` SHA-256 `60A2DDA79EF85971B0CC99D55D70F0963CB5E9E250418F9805F64DF6022E6765`；端口 5234、监听 PID 24996、长时 exec session 2765，批后在同一 session 停止。启动前核对 worktree、`.venv`、入口、空目录及端口；健康 `ok=true, provider_enabled=false`。
- B04 HTTP 控制脚本 `tmp/r3_m04_http_probe.py` SHA-256 `B3F885F5B7C13CE790281A02877F02A6E48159EBB0F055455318A11DF943D70B`。`F-HYP.csv` 与 `F-HYP-FLAT.csv` 在冻结顺序上传，票据文件名与 SHA-256 核对；会话 `cb3504c030bd`，13 轮各有唯一 `turn_end`、durable completed、相同当前计划 `spec_d443bcb10ccd`。原 v1 竞争解释保留，v2 后旧证据变 stale；描述性原值可从结果/导出看到。结果 `m04-http-result.json` SHA-256 `FC1B699ED35B4A9E9AA744B27B496F11198C54DB4095659145CA0FB262999CC4`。
- 同批同会话 B01 新目标控制脚本 `tmp/r3_plan_new_goal_probe.py` SHA-256 `5D7FEAD7D93911A9C7E180064F022844E36FB91871096AA1C78A8B4543DA76B1`。`F-SALES.csv` 票据身份核对后，独立订单数/金额请求得到唯一 `turn_end`，durable completed，当前计划 `spec_ec2129de15aa`。旧 B04 三条证据与假设集仍指 `spec_d443bcb10ccd`；新 B01 证据与核验只指新 ID，验证报告 `pass`、claim_count 1。现有会话/导出接口均成功，正文交付 12 条订单、amount_sum 120、amount_count 12、方法和业务单位未知边界。`new-goal-http-result.json` SHA-256 `D2AC9E0297DCC499637634D809D60E454D7BCEFD98BC48797DB2E8AFF4053DB1`。
- `runtime.jsonl` 中 `forbidden_provider_transport` 为 0，实际 Provider initiated calls 为 0。以上只证明脚本模型下的本地 app 路径，不是自然模型、浏览器视觉、真实 Provider、生产或部署验收。

定向回归最终 240 passed。首次 full-offline `tmp/r3plancontfo` 2887 passed / 8 failed / 1 skipped；八项均是 `tests/test_execution_control.py` 中二参意图分类替身不接收新增可选 `current_plan_id` 所致的 `TypeError`，没有运行到对应产品断言。替身签名更新后该文件 34 passed；新目录最终 full-offline `tmp/r3plancontfo2` 为 2895 passed / 1 skipped / 16 warnings / 0 failed，JUnit SHA-256 `868590FF23D0EC21C9314F3CFB46337E2CFCA01195DA2D30D6CC5EC1F9F3FC2D`。runner 禁止 Provider 调用，实际 Provider initiated calls 为 0。

R3.5 仍未完成：M01 表达与条件建议、M06 结果和局部缺口分类及 R4 解释边界需要后续同一产品链路交付；当前通过不代表 M01—M06 整体通过。
