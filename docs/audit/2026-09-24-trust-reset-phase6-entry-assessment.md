# Phase 6 进入评估：可信核心重建与受限处置能否合并

日期：2026-09-24。进入基线：`main@a47b281a513af93936f7c689118d18203ef2beee`。用户先裁决**保持正式发布策略不变，先补足可信核心，再决定默认切换**，后明确批准 **A+B 合并启动离线准备，C/D 另设门**。本文件记录评估和首个实施切片，不开启审计模型调用或 Phase 6 发布处置。

## 结论先行

**可以合并“可信核心重建”与 Phase 6 的离线、纯宿主处置底座；不能合并为一次上线。** 现在不是被 Phase 0—4 卡住：canonical history、M02 情景、确认类型化、事后任务权威和多个 typed claim 切片均已有 E2 收据。真正不能直接启用 Phase 6 的是：仍有有效 binding 旁独立无据 99% 的现行误放，现有局部 renderer 对 R11/R4 M03/M04/R16 M05 正确或重要内容重建不足，Phase 5 仅有离线审计回复 validator、**没有实际 Shadow 调度/账本/成本校准**。这三类问题不同，不能通过再加一个 claim 家族、宽泛词表或审计 `overall=pass` 消除。

## 当前剩余项按“阻碍什么”划分

| 项目 | 当前证据/所有者 | 阻碍范围 |
| --- | --- | --- |
| 无绑定独立数字可随有效 binding 放行 | 当前比较夹具 `binding_issues=[]`、`narrative_issues=[]`，另有 99%；见双轨校准 | 阻碍把现有完整散文当安全发布，不能交给随机 Shadow 总审批 |
| 可信核心不能重建历史正确内容 | R11 正确 D7/无 D30 核心 `None`；R4 M03 六来源表/图、M04 假设答复和 R16 已通过 M05 均无可接纳 typed 占位符；AC17 的“缺少分母”由模型自述而**非宿主证明** | 阻碍立即把当前 `render_verified_partial_answer` 设为默认；须保留正确事实、产物与**可证实**的缺口 |
| 审计协议覆盖不足 | `publication_audit.py::_typed_claim_evidence()` 只认可 `scenario_extrapolation`；新增 observed/derived/comparison/descriptive_fit 的 finding 仍落 advisory；`reason_untrusted` 不得进入正文，`missing_requirements/contradictions` 只能为空 | 阻碍 Phase 6 对所有当前 typed claim 执行动作；不能从自由文本理由制造新事实 |
| Shadow 只存在纯函数 validator | 没有 loop 调度、独立提示/输入 digest、统一 Provider 账本成本及故障降级的运行证据；真实调用仍未获新冻结/授权 | 阻碍宣称 Phase 5 完整或启用审计影响发布；不阻碍离线实现宿主底座 |
| 修订/局部保留已有但尚非 Phase 6 | `AgentLoop` 已有一次 publication recovery 和失败后 `render_verified_partial_answer`；它只按当前有效 typed blocks 输出，未执行审核 finding 的 claim 级动作 | 可以复用调用/循环上限，不能把它重命名为 Phase 6 已完成 |
| E3/E4 | 最新为全量离线 E2；Provider-disabled 完整浏览器尚未在新 HEAD 跑，E4 需新冻结及用户授权 | 阻碍阶段验收/真实模型质量结论，不阻碍离线设计与测试 |

三份原始需求继续给出硬边界：VP 需要有依据的解释/条件建议和竞争假设；IC 不能让方法许可或数据性质猜测反复挂起；CP 需要明确子问题的可信结果或真实具体缺口，不能用模型标签或尾注纠错。R7—R21/R4 的误拒、误放、版本/单位及任务权威轨迹须同时作回归背景；R4 中途停止，不是唯一目标。旧自然候选可证明旧门问题，但不能要求其原字节在新结构门下直接通过。

## 推荐的有限合并路径（每段有停止门）

### A. 可信核心合成（Phase 6 前半的宿主底座；不改正式发布）

RED：双轨表里的无据 99% 与 R11/R4 M03/M04/R16 M05 正确内容损失两侧并行；AC17 不把未证明的“缺少分母”当正确 oracle。结构化替代：仍用一个 `answer_bindings.v1`、当前 packet、既有 receipt/FactGroup/产物引用、analysis_state 的竞争假设关系；生成可检查的事实、**有宿主证据的** gap、方法/时间/单位边界和产物，不创建第二 journal/planner。旧门退役目标是“有一条有效绑定即整篇自由散文可信”与从句子反向猜族/数值/来源；回执数值与版本硬门保留。验收要分别统计正确事实/具体缺口/产物/假设关系的保留和独立错误事实的移除；达不到价值目标就不切默认。

### B. 纯宿主、离线 Phase 6 动作底座（可与 A 在同一集成阶段开发）

把现有 `publication_audit.v1` 的 claim/evidence 映射扩至**已经通过同快照 parser 的 typed claims**，不是接纳模型自报 ID；继续拒绝外来引用。仅做纯函数模拟 `keep → downgrade → mark_unassessed → remove` 和可定位的一次 targeted revision 计划，不能从 `reason_untrusted` 复制数值/业务事实；先以确定性问题与假审计回复回放，`publication_effect` 仍为 `none`。一个有问题的 claim 不删独立可信 claim，故障回退只发已验证核心。不得为处置增加新的模型调用或重试循环。

### C. Phase 5 真正 Shadow 调度与校准（独立启用门）

只有 A/B 的定位、身份与退化测试通过后，才设计明确开启的审计调度：独立版本化提示、不可信输入标记、精确 packet/answer digest、现有统一 Provider 账本和预算、超时不可用状态。开发测试用离线假回复；**任何真实 Provider 调用都要新精确冻结与用户显式授权**。先在历史正反候选上记录高风险漏检、正确 claim 误删、动作准确、超时/成本；Shadow 不改变用户可见结果。

### D. Phase 6 真实处置与验收（仍须另一次用户裁决）

只有 C 的校准能证明受限行动不会成为随机总门，才允许按 claim ID 的有限动作影响正式正文；默认可退化为 A 的可信核心，`overall=pass` 不能覆盖确定性失败。最多一次定向修订、一次确定性复核、必要时一次最终语义复核；不能无限循环或自由重写整篇。随后按根 `AGENTS.md` 做新 HEAD 的完整 Provider-disabled 内置浏览器 E3；真实 E4 另行冻结和授权。

## 何时可称“进入/完成” Phase 6

现在可**开始 A+B 的离线实现**，并标为 `phase6_preparatory_offline`；不能称 Phase 5 Shadow 完成，更不能称 Phase 6 处置生效。只有 A 的可信核心质量门、B 的闭合动作/失败回退、C 的显式审计与校准，以及 D 的受控发布和 E3 证据均成立，才称 Phase 6 本地验收。E4 仍是独立的真实 Provider 门，不因 E2/E3 自动满足。

这一路径有四个有名的门，不是无期限增加 claim 类型。若 A 发现关键解释/图表/关系无法从当前权威状态重建，需要在原始价值目标与更窄的可信核心之间请用户裁决，不能默默改低验收标准。

## A+B 首个离线切片（仍未过 A/B 完成门）

实施前 RED：现有 `render_verified_partial_answer` 只恢复 typed 块，缺少回执事实组和宿主可证实的遗漏；现有 Shadow validator 只绑定 M02 情景，且只看模型自报 claim ID/回执名，伪造的情景参数亦可被视为 bound。新测试最初因预览/模拟接口缺失而收集失败。结构替代：`render_trusted_core_preview` 在当前 packet 的副本上复用已有限定 renderer，另把同快照 `fact_groups` 中与 `facts` 一一相符的原始字段作为**未赋予 answered 身份**的上下文摘录；只从 `omitted_groups.reason=budget` 和 `scan.scan_incomplete` 输出宿主可核验的具体遗漏。`_typed_claim_evidence` 对所有现有 typed 家族复用各自确定性校验，再将当前事实/派生/回执引用映到 claim。`simulate_shadow_actions` 只产生离线的 claim 级预览、定向修订 ID，`publication_effect=none`；无效/外来 finding 降 advisory，理由从不复制进正文。旧门退役**目标**仍是“一条有效绑定让整篇散文获得事实权威”；本切片不改正式发布门，保留所有既有硬证据门。

首轮定向测试覆盖独立无据 99% 不进核心、两来源事实、预算/扫描缺口、错配指标身份、情景伪造及单 claim 移除而独立结果保留。旧 Shadow 夹具原先只有 claim ID/回执名，无真实可核验曲线范围/参数；加严后降为 advisory，已改成真实 R4 M02 等价结构，未放宽 validator。最终五组相关测试 **180 passed**；fresh `tmp/tprb17` 全量离线 **2905 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2906/failures=0/errors=0/skipped=1`，SHA256 `41C04E855B46FE6DAD2E3E0ABC4FEBF839E5389902E8693E16206E50AA503954`，runner `provider_calls=forbidden`。前一轮 `tmp/tprb16` **2904 passed、1 skipped**，但执行中发生代码收紧，不作为最终时点证据。该切片不改变 `AgentLoop` 正式正文、不调用 Provider、没有 Shadow 调度、没有额外账本。

未闭合：R4 M03 图表产物和六来源的**业务结论**不等于原始字段摘录；R4 M04 竞争假设关系尚未有同快照可核验的 packet 投影；R16 M05 方法上下文和 R11 正确否定边界仍须按历史正反样本校准。原始字段不能被提升成回答某一指标的授权，`analysis_state` 的模型自述关系也不能直接当作事实。这些需后续 A 小切片解决或向用户讨论取舍，不能据本轮把可信核心设默认。B 亦未做到真实审计处置；C Shadow 调度/校准和 D 正式发布改变继续独立授权。
