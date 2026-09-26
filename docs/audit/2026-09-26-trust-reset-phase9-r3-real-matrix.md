# Phase 9 R3：真实模型 HTTP 控制矩阵与阶段复核

状态：`executed_complete / not_accepted`。六场景按冻结顺序执行完毕，**不是**完整浏览器 E4 通过，也不是 Phase 5—8 退出。本文只读复核该批证据；不倒填历史批次或改正式发布。

## 冻结、授权与核算

- 源 `main@0b8469f3b1528e6981de2c0b5cce5073da43a9b3`，启动前工作树无列出改动。`tmp/p9h2` 的 fresh 全量离线回归为 3017 passed、1 skipped、0 failed；修正确认恢复的 `turn_start` 校验后，定向 launcher/上传测试 24 passed。
- 用户在看到精确身份后确认执行 `tmp/phase9-p08-real-20260926-r3/freeze.json`，SHA256 `81C893BCA7A657B7EE80CAC1487C6FAE1E679FD730F40A991E97F5AFA1EB3144`。协议 `p08.real_matrix.v3`，模型 `openai/deepseek-flash`，端点 `https://api.deepseek.com`，十份合成 CSV、M01—M06 原提示/oracle，one-shot 无重试，最多 120 次物理调用。实际控制路径是同一应用的 `/api/upload`、`/api/chat`、SSE 和会话 API，不是浏览器点击。
- 隔离服务端口 5248、OS PID 13604、Codex exec session 52736；驱动 exec session 12860。服务端 `/p08-freeze` 与本地冻结的 commit、driver digest、模型和预算一致。运行后已停止，端口无监听。
- 权威账本 `tmp/phase9-p08-real-20260926-r3/provider-calls.jsonl`：**90 started / 90 dispatched / 0 failed / 0 denied**，最高 call_number 90，SHA256 `10C9933F995D3B8C5CBEEB582199734035428FF99F57E8449D545D8B102A2F27`。HTTP 控制证据 `http-matrix.jsonl` SHA256 `E9517CF7ABB266AD27850594AF885253D399210D1AB694B6C85E098D62836AC6`；六个独立会话、13 轮，每轮唯一 `turn_end` 与持久 `run_state` 相符。该控制文件不是第二 Provider 账本。
- 现有 `p08_scenario_audit.py` 结果 `scenario-audit.json` SHA256 `C64E4CFCB0907A685EC5706FFEEF38E7C282F34C85CBF34861B18D44E5F7EE6E`：覆盖与调用核算通过；总判定 `failed`，execution/transfer failed，evidence/value unassessed，declaration passed。审计器的非零退出是验收失败判定，不是脚本未运行。

## 六场景结果

| 场景 | 会话与终态 | 证据支持的判断 |
| --- | --- | --- |
| M01 | `ebaa8c3199ea`，completed | 正文保留 12 行、合计 120、未知单位、观察窗口和条件建议；但将平坦描述扩大成“所有趋势/对比都不成立”，猜测数据可能是演示样例，并自加 `>30%` 缺失停止阈值。初稿在否定列表中提到“同比”即触发 `unsupported_yoy_label` 修订，说明旧散文门仍误拒正确限制语境。宿主原位 claim 0，整篇语义未验收。 |
| M02 | `7f0b6c7dc96c`，failed | 工具已有 D1—D7 原始值和三族拟合；多次 `stage3c0b_current_task_missing` 使任务/图表调用失败。候选把未确认的 `retention` 尺度写成“留存率 0–1”，含未绑定的 D30/拟合占位；一次修订仍留 `[[claim:d30_scenario]]`，最终只有失败通知。R11/R4 的正确观测与情景边界没有作为用户可见结果保住。 |
| M03 | `c2f5f4f69007`，completed | 六来源两日金额 10→11 至 60→66、总 210→231、绝对/相对变化与记录数完整可见，API 压缩和导出成功。自然答案保留方法/限制；但宿主原位 claim 0，旁侧解释与建议未审计，不能将表格正确直接升格为整篇可信。 |
| M04 | `70ef73e80cb3`，同会话 v1/v2 两轮均 failed | v1/v2 数据均按冻结顺序上传。模型提出假设及描述性测量，但 v2 关系提议用 `metric=amount`，证据测量却为 `trend_slope`、`daily_avg_diff`，宿主候选理由为 `metric_missing_in_evidence`；当前计划没有宿主核验的关系。模型仍尝试 `refuted` 表述，另一次候选 `answer_bindings` 快照过期；最终被 `analysis_audit_incomplete` 阻断。保留此阻断所保护的版本/关系边界，不把失败改写为通过。 |
| M05 | `df62590400bd`，六轮 completed | 12 条记录、amount 合计 120、未知单位、时间范围和计算方法跨六种表达基本保留；API 导出存在。这是 R16 正向价值的当前自然模型证据。宿主原位 claim 仍为 0，模型自称 `high` 不是宿主核验身份。 |
| M06 | `dd25b1dde3f0`，第一轮 completed、第二轮 suspended | 缺失数据集未编造；真实成本口径问题和 A/B 选项已生成，且声明成本列缺失。选项 B 实际文字为“口径B：净收益 = 促销收入 − 代金券成本 − 渠道成本”，HTTP 驱动只接受旧的 `B. 代金券成本 + 渠道成本`，因此未恢复；这是**测试控制失配**，不能归因于产品无确认。首轮单一步骤后又补一句“也可改用 M01-sales”，是否违反单一下一步仍需价值判断。M06 后半路径未评估。 |

本批没有可审计的上传按钮、视觉原位渲染或浏览器刷新操作，这三项保持 `unassessed`。用户手工验证上传可用是背景信息，不作本批自动化收据。API 导出/持久会话的通过也不替代视觉验收。

批后仅修复 M06 测试控制：以本批真实“口径B：净收益 = 促销收入 − 代金券成本 − 渠道成本”选项作 RED，旧驱动返回 `None`；现驱动只在唯一 B 选项同时明确包含两项成本时提交该选项的实际 `value`。定向 launcher/上传测试 **25 passed**。这是下一批驱动的离线修复，**不回写 r3、不恢复 M06、不增加 r3 调用**；新驱动 digest 使旧冻结不能再使用。

## 对总计划的含义与后续顺序

1. **先收敛现有失败，不追加门。** M02 的 Stage 3C0B 任务作用域在模型正常多工具调用中阻断内容；M04 的模型关系字段与宿主可核测量身份不一致。先以 R11/R16、R4、R7—R21 和当前会话做正反 RED，复核旧任务/关系门哪些是唯一安全边界、哪些应改成显式 `unassessed` 与可见的具体缺口；保留同版本、回执、数值、单位和假设 ID 硬核验，不用词表或尾注放行错误正文。
2. **Phase 6 A 未退出。** 当前普通路径 M01/M03/M05 都有有用自然答案，但 `host_rendered_claims=0`；M02/M04 的原位绑定失败和 M03 邻接散文未审计显示 typed 生产→回执绑定→宿主渲染还不是普通路径稳定闭环。先验证价值保留与局部处置，再讨论正式默认 D；不因 M03/M05 completed 就将 A/D 记为通过。
3. **Phase 5/C 与 Phase 7 未退出。** 普通 AgentLoop 的真实 Shadow 调度、自然 claim 分母与误删/漏检/成本校准仍无本批证据。M01 否定语境误拒与未经核验的来源猜测同时出现，证明旧散文门既误删又漏检；不能因一个模型答案变差就叠新词表，也不能在无局部替代时整族删除旧门。
4. **Phase 8/9：矩阵已执行但未验收。** E2 与先前 E3 维持原身份；本批是真实 Provider + 应用 HTTP 系统证据，六例总判定失败且 UI 维度未评估。下一次完整真实批次须先修复并离线核验 P1 根因、修正 M06 测试控制，重新提交/冻结/取得新授权；本 r3 不恢复、不局部重跑。

停止条件：若修复需要给模型关系自述或旧版本证据授予 `supported/refuted`、把缺失成本当 0、把 0.10 自动换成 10%、整篇借一个 binding 获权威、靠末尾说明抵消错误正文、新增 planner/账本/浏览器框架或隐藏审计调用，停止实现并回到重置总计划复核。
