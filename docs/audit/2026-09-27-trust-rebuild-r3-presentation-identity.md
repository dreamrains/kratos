# R3.5 表达追问的计划身份与未闭合行动子目标

日期：2026-09-27。基线：`codex/trust-rebuild-20260927@773e4b2`。只评估 Provider 禁用的正常 app HTTP 路线；视觉、自然模型、正式默认均未评估。供体 `main@b181646` 未改。

## 原始目标与根因

VP G2 要求正确结果不因摘要或局部拒绝消失；IC 要求方法模板不替代原任务，业务决定仅在同范围复用；CP CR03 要求每个明确子问题有结果或具体缺口。M01 B01 的 12 条源记录、amount 总额 120、非空计数 12、未知单位及行动建议的证据缺口已在首轮同包发布。B05 分析师、白话和技术表达追问复用同一回执，却失去原行动子目标。行动缺口消失不是用户撤回，也不是来源版本变化。

当前路径先将本轮语义输出写入 `answer_requirements`，再由 `prepare_turn` 对追问词句重新选择 playbook。只含 `presentation` 的追问因此重建 `analysis_spec.id`；最终 packet 又只使用 `turn_requirement_ids`，把原行动需求排除。技术表达的演练辅助分类器原先没有输出对应的 `presentation` 需求。三处问题彼此不同，不能用回答词面或复用最近文本来宣称原目标已保留。

## 本次局部实施与完整 app 证据

对有精确本轮 `presentation` 需求、前一份已发布 packet 的数据身份仍有效且与当前 plan ID 相同的追问，`AgentLoop` 保留原计划身份，避免新的 playbook 候选替换目标。演练分类器为冻结 B05 技术表达返回精确来源的 `presentation` 输出；这只修正演练语义输入，不授权产品凭词面推定用户意图。

批前固定控制路由 `local_http_api`，使用既有 `scripts/testing/run_p7_browser_rehearsal.py` 和 `tmp/r3_m01_http_probe.py`。第一批 `tmp/r3m01continuation1` 端口 5247、PID 18188、exec session 66832 已停；六轮同会话 `f33793ecc4fe` 均 completed、唯一 SSE `turn_end`，上传票据、持久状态和导出闭合。结果 SHA-256 `983B667F46F5528F36783C65DC6594CEA522D7AB4C4DE6E1BE9328E0B568B1E1`。它暴露了计划随每轮表达重建，行动缺口在第 3/5/6 轮丢失。

第二批 `tmp/r3m01continuation2` 用新目录和端口 5248、PID 16956、exec session 26677 已停；launcher SHA-256 `EEB4D9AAD192329B22BA0A6686192824B0412ADF333B0D084911CBC8BD53F908`，HTTP driver SHA-256 `1521D6272B358D432F8B7EE2A7C26BE0FD90CD7ECCFBCC774B4BCAF985ACFDBA`。六轮同会话 `e769df8f2bef` 均 completed、唯一 SSE `turn_end`、各轮持久状态一致，导出成功；源 12 行、派生 1 行、120/12、方法与未知单位均保留；健康 `ok=true/provider_enabled=false`，`runtime.jsonl` 无 `forbidden_provider_transport`，本批实际 Provider 发起 0。结果 SHA-256 `B9CE7F28DFC3685980929929EF7E97411241DD6C7F20AA980479AB2B1A81C423`。第 2→3 轮 plan ID 保持 `spec_421a9eb8b745`，第 4→5→6 轮保持 `spec_63e8632274a7`；第 4 轮含新行动子目标，仍重新选择计划。第 3/5/6 轮没有行动缺口或条件建议，故原 M01/B05 内容验收仍失败。

试过的 packet 沿用候选两批均未把第 3/5/6 轮行动需求送到正式发布：预览和终态有不同构包入口，终态会重建并只带本轮需求。候选沿用代码已撤下，未以测试通过冒充成功。保留的计划身份代码及演练输入在撤下候选后通过定向 336 项，完整 E2 `tmp/r3planpreservefo1` 为 2909 passed、1 skipped、16 warnings。第二批 app 运行于撤下前的候选代码，足以定位并观察计划身份修复，但不记作撤下后代码的完整 app 验收。HTTP 路线的 picker、可视正文和浏览器刷新均为 `unassessed`。

## 设计裁决与后续顺序

同根因两轮完整 app 不收敛，停止第三轮“从最近 packet 拷需求”的同型补丁。后续 R3.5/CP3 必须在现有 `answer_requirements` 与 `answer_bindings.v1` 中给原结果/行动需求稳定的计划身份和来源消息引用，使预览与终态通过同一个构包边界；表达追问只增加本轮表达需求。继承必须核对原 packet 已发布、同会话/plan、同版本来源与活跃需求；新计算、新行动目标、撤回或版本变化不能借旧包获得覆盖。以同包正文和逐需求状态验证正反例，再用新身份完整 app 批次验证。不得新增 planner、账本、词表尾注或默认 Provider 调用。

M01 目前只有准确的行动证据缺口，没有原目标要求的真实有条件建议。M06 真实成本范围确认后的计算仍无当前回执，宿主 fail-closed 正确但净收益分层交付未完成。R4 受限语义审核未校准，旧门不可按清查直接删除；R5 保持未开始。真模型能力校准、正式默认和外部 Git 保持各自授权门。

## 结构修复后的新批次（2026-09-27）

上述两批失败后的设计裁决已落实到现有发布包构建边界：`AgentLoop` 只记录满足当前精确表达需求、已发布 packet、同计划和来源条件的候选；预览与终态都调用同一个 `build_publication_packet`，由它验证前包为已发布终态、答案和 bindings 摘要、同会话/计划/回执及数据版本身份，以及原行动需求仍活跃且曾在同包标记 `evidence_insufficient/checked`。通过后，原需求保留原消息引用，并把来源包和摘要记录在同一个 `answer_bindings.v1` 包内。新计算、新行动目标、撤回、计划或版本变化不会沿用。定向正反例 337 passed。

控制路由批前固定为 `local_http_api`，沿用既有 launcher/HTTP driver，未增加浏览器框架或账本。最终代码的新完整六轮批次为 `tmp/r3m01unified2`：端口 5250，PID 8484，exec session 61431 已停；launcher SHA-256 `EEB4D9AAD192329B22BA0A6686192824B0412ADF333B0D084911CBC8BD53F908`，driver SHA-256 `1521D6272B358D432F8B7EE2A7C26BE0FD90CD7ECCFBCC774B4BCAF985ACFDBA`，结果 SHA-256 `D0122468022CF582E0C35AEBF4EDBFF6BF87A9D380A586BB94F679D317C30591`。同一会话 `c52c8ee9b8c9` 六轮均 completed、唯一 SSE `turn_end`，上传文件名/SHA、持久状态、导出与前后健康检查闭合；`provider_enabled=false`，runtime 无 `forbidden_provider_transport`，实际 Provider 发起 0。六轮均保留源 12 行、派生 1 行、120/12、方法、未知单位和具体行动证据缺口；行动需求均 `evidence_insufficient/checked`，未冒称 `answered`。第 3/5/6 轮经来源校验沿用原需求 ID 与消息引用，第 2/4 轮使用本轮明确需求；B05 业务表达后直到技术表达的计划 ID 保持 `spec_421a9eb8b745`。HTTP 的 picker、可视正文和浏览器刷新仍为 `unassessed`。

最终代码全离线回归 `tmp/r3m01unifiedfo1`：2910 passed、1 skipped、16 warnings。此结果关闭表达追问导致原行动子目标消失的缺陷，不关闭 M01 条件建议本身；当前仍只能诚实报告行动证据缺口。M06 确认后执行和分层交付、R4 自然语义校准仍独立未完成，R5 不据此启动。
