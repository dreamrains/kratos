# Phase 4 补充复核：关系提议不等于宿主有效关系

日期：2026-09-24。进入基线 `main@26c223dfa77c196ae49b8b354322df384fb21a0b`，工作树无列出的改动（本机 git 全局 ignore 与 `.pytest_cache` 有权限警告）。本切片纠正 Phase 4 原目标的漏门，不是 Phase 5 Shadow、Phase 6 默认策略或 Phase 7 退役。

## 原始需求与跨历史 RED

VP G5/P5 要求假设身份、证据关系、范围与状态可追踪；模型自报或文本相似不能升为有效支持。IC 要求内部技术问题不向用户追加确认；CP CR03/CR07 要求保留独立可信内容和明确缺口。因此校验只作用于**显式竞争假设任务**，未完成 task 仍不全局阻断普通任务；未决假设也不必伪装为支持。

| 样本 | 可复核结构 | 原错误判断 / 保留边界 |
| --- | --- | --- |
| R4 中断批次 M04 `f2db8a75de3d` | v2 plan `plan_b4456ac853`；EvidenceRecord 提议使用 `h_trend/h_level_shift`，真实假设 ID 带数据集/plan 前缀；两套假设均 `inconclusive: 4`、有效支持/反驳零条 | 旧 guard 仅检查关系数组非空，误认提议形状为审计闭合；R4 只证明提议被记录。 |
| 本次完整 E4 M04 `d4776ba7b746` | v1 无 plan，v2 有 `plan_0ed4828d6a` 和当前假设集，但两轮缺有效关系；模型在持久对话中明确指出 guard 所说 `<competing_hypotheses>` ID 未展示 | 需要展示既有真实 ID，不要求模型猜别名；显式任务的结构化审计要求不撤销。 |
| R21 M04 与 2026-09-21 目标校准 | 未完成 task 曾导致全局失败，耦合已退役 | 本修复不得恢复 task 全局许可证；有效关系可以与其他未决解释并存。 |
| R11 M02、R16 已通过 M05、R4 M03、独立 99% 负例及本次 E4 其他场景 | 正确 D7 边界、12/120 方法上下文、六来源表/图和未知单位仍各有价值；自由散文又可含无据范围/解释 | 这些不是关系门的通过分母。本切片不称其由可信核心等价重建，也不切换自由散文发布。 |

新增测试在原源码得到 **3 failed、33 passed**：R4 型错误别名、与测量方向冲突的关系提议均被旧门误放；`hypotheses_prompt_brief` 未输出实际假设 ID。这些是身份与既有宿主决策规则的结构反例，不是新词面正则用例。

## 结构替代与旧门

沿用 `analysis_plan`、`hypothesis_sets`、EvidenceRecord、`update_hypotheses_from_evidence` 和现有数据版本新鲜度过滤。发布前在**当前 plan** 的假设集和新鲜证据上重新执行宿主关系校验；只有至少一条有效关系才视为显式任务的结构义务存在。错误 ID、指标/方向冲突、过期证据或旧 plan 不能凭数组非空闭合。合法关系可与其他未决假设并存；未完成 task 不参与判断。

有界 `<competing_hypotheses>` 摘要现在显示真实 `hypothesis.id`。质量 guard 只引用当前 plan；无 plan 时明确先记录 plan。guard 后计划可能晚于一次性合成提示建立，所以在该显式修复轮次沿用既有 `maybe_create_hypothesis_set` 刷新同一宿主状态，下一轮动态系统提示显示新 ID，并去掉可能残留的旧 plan ID。不虚称 ID 已展示；没有新 planner、账本、浏览器路径、确认或 Provider 调用。

**退役的旧门**仅是“EvidenceRecord 任意非空 `competing_hypotheses` 数组 = 假设关系已闭合”。正式有效 binding 旁独立无据 99% 的误放仍属 Phase 6 A/D，不记在本切片。回执、单位、算术、版本门均保留。

## 验证及剩余限制

定向 `test_analysis_quality_guard_scope.py`、`test_hypotheses.py`、`test_stage3c0b_evidence_replenishment.py`、`test_publication_task_closure.py` 最终为 **45 passed**，含有效同 plan 关系、R4 别名、方向冲突、旧 plan 不展示、guard 后刷新以及未完成 task 非阻断。第一次过长隔离目录 `tmp/trust-reset-fo-20260924-hypothesis-audit-r1` 的 full-offline 为 **2966 passed/1 failed/1 skipped**，失败是 `test_golden_funnel_conversion_analysis` 报告落盘 `FileNotFoundError`，路径已超过 Windows 可用长度；同样长的隔离目录单文件复核又有两个同类报告落盘失败。因此没有为它改产品或 oracle。`tmp/tp4a1` 在发现 guard 后可能保留旧 ID 与缺少新 set 刷新时主动停止，**不计最终收据**。最终源码在短且全新的 `tmp/tp4a2` 完成 full-offline：**2969 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `FB56F3DDF2409BC8B2C301622747ED62E0DAAC472A3BB51C4D7F2A37926C42A0`；runner `provider_calls=forbidden`，实际真实 Provider initiated 0。这是 E2，不是 E3/E4。此前 `b70fbc3` 的 2964 通过不能充当本源码收据。

本切片只在现有宿主关系规则内验证提议，不证明模型填写的每一项 EvidenceRecord 测量本身都经工具原始回执复算；工具结果身份、版本和 claim 覆盖仍须 Phase 6 A 核对。尚无修改后完整 E3 或真实 E4，不能宣称自然模型 M04 已成功。Phase 5 真 Shadow、Phase 6 A/C/D、Phase 7 状态均不升级；新真实 Provider 批次须另精确冻结并获用户新授权。
