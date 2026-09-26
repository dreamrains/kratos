# 可信发布重置：Phase 5—8 阶段任务与退出记录

本表是 [重置总计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)的当前状态索引；总计划与 VP、IC、CP 三份原始计划仍定义目标。本表只更新当前任务、证据和退出判断，历史运行记录不倒填。续接时先核对实际 HEAD/工作树，再逐项更新本表和相应审计记录。`本地机制就绪`、`E2`、`E3`、`E4`、`阶段退出`是不同身份。

## 2026-09-25 只读基线与已确认顺序

- 起点 `main@fc9ae7ac3e23d0096cec7f549c5f5b64372a9a12`，根工作树无列出改动；根 `AGENTS.md` 已核对。三份原始计划、总计划、交接 §30—32、Phase 5/C 校准 §8—9、完整 P08 E4 报告及自然 M03-P/N 报告已重新对照。
- Phase 0—3 有本地实现记录；Phase 4 的任务非全局阻断已收口，真实假设 ID 与原回执测量校验有 E2 纠偏，旧 E4 不可倒填为通过。前段本地通过不替代当前真实模型结果。
- 用户确认的顺序是：先收敛 Phase 6 默认关闭机制，完成 Phase 7 的逐族处置与 Phase 8 的分层验收准备，复核三份原始目标和复杂度，然后进入 Phase 9 系统矩阵。Phase 5/C 的自然质量与 Phase 6/D 的正式默认裁决保留独立退出门，不因后续阶段的本地实现自动通过。

## 子任务状态

| ID | 必须交付与当前所有者 | 已有证据 | 未满足的退出条件 / 下一动作 |
| --- | --- | --- | --- |
| 5.1 | `publication_audit.v1` 版本化协议、同包/正文身份、有效 claim/evidence 归属、无效 finding 降 advisory；`publication_audit.py` | E2 已有；确定性失败不受 `overall` 覆盖 | 维持，不另建审核协议 |
| 5.2 | 从已接受正文、原位 trace、规范历史和回执形成受限 `audit_view`；`publication_audit.py` + `publication_synthesis.py` | E2 已有；旧包和无 typed 答案返回 unavailable | 自由散文仍 `not_audited`，不得把可定位 typed 数量当整篇质量 |
| 5.3 | 显式开启的真实 Shadow 调度、统一 Provider 账本/总预算、超时和故障降级；现有 `run_shadow_audit_once` 与 AgentLoop | 受控脚本可单次调用；普通 AgentLoop 未调度 | 先验收零调用/有调用/错误/超时机械门，默认不影响发布；真实批次另精确冻结授权 |
| 5.4 | 以自然可行动 claim 为分母，校准误删、漏检、动作、不可评估率和成本 | 受控 r4 四例可评；自然 M03-P/N 各六条 typed，但尚无同一分母的 Shadow 校准 | 不能以人工构造四例或旧归档 0 typed 宣称自然质量；Phase 5 未退出 |
| 6.A1 | R11/M02 观测、R16 聚合、M03 六源比较的同版本 typed 生产→回执绑定→宿主原位渲染；`answer_bindings.v1` 与 AgentLoop 显式入口 | E2；M03 自然 P/N 各六块的局部 E4 | R11 原句与尺度、R16 方法/分母、M03 图表/解释、M04 关系价值尚未跨历史等价闭合；普通路径未启用 |
| 6.A2 | 每个明确子问题的回答或宿主可证实具体缺口，保留方法、产物、条件建议 | 现有部分要求绑定、缺口和 artifact 机制 | 旧 E4 六场景 `answer_requirements=0`；无身份不能标 `answered`，模型自报缺口不算宿主证明 |
| 6.A3 | typed 旁的独立高风险事实与正确解释分别处置 | 有效 binding 旁无据 99% 的离线 RED；自然 M03 正反样本也有未绑定汇总、解释和建议 | 不可整篇借一个 binding 获事实权威；也不能用纯核心删除全部正确解释。此项阻碍 A 退出和 Phase 7 大范围退役 |
| 6.B | 仅同快照 typed claim 的 keep/downgrade/unassessed/remove、最多一次定向修订与故障回退；`simulate_shadow_actions`、现有一次 publication recovery | 纯函数 E2、一次修订限额 E2；`publication_effect=none` | 未有正式审计处置链；引用合法不等于 finding 语义真实，不能直接执行模型建议 |
| 6.C | Phase 5 的真实 Shadow 与校准进入受限处置前的独立门 | 见 5.3/5.4 | 自然质量未验收 |
| 6.D | 受控正式处置、确定性复核、默认策略与回退 | 未授权默认切换 | 需要用户就保留解释/局部降级的具体方案裁决；真实自然矩阵和当前 HEAD E3 不得从旧批次借用 |
| 7.1 | 每族列旧门、误拒/误放、结构所有者及历史正反；`publication_synthesis.py` | `_period_label_issues` 已软化，死 `render_verified_appendix` 已删除 | `_extrapolation_issues`、`_currency_unit_issues` 等仍处理旁侧散文；逐族列证据后才可降级/删除 |
| 7.2 | 对每族删除旧词面硬判并以同版本 claim/回执/宿主渲染或受限语义审计替代 | 局部 typed 族有 E2/E3，R4/R11 误拒仍有历史证据 | 正确解释/方法上下文保留和无据强断言剔除须同时回放；Phase 7 未退出 |
| 7.3 | 修正上一提交的过渡边界说明 | `fc9ae7a` 把旧情景与来源修订的宿主说明放在正文末尾 | 总计划 §2.3/§4.4 禁止靠末尾说明抵消错误正文；不得将其作为结构化替代或 Phase 7 退出证据 |
| 8.1 | blocking、structured completeness、semantic audit、advisory 分层；去掉词面数字伪 oracle | E2 已有，旧完整 P08 可分维回放 | 不能把 `unassessed` 当通过；每条 blocking 需原始需求与可机器判定证据 |
| 8.2 | 同版本回执、binding、原位 trace 的正向事实核验及需求价值矩阵 | 当前审计视图能定位局部 claim；M01—M06 历史/脚本矩阵已汇总 | 邻接解释仍未审计；原位可信数不得升级成整篇价值通过 |
| 8.3 | 当前实现的完整 Provider-disabled E3 与最终真实 E4 分层验收 | `959ea6a` E3：16 会话、Provider 0；旧 E4：82 调用、执行完成但验收失败 | 本地路径已完成；真实 E4 属 Phase 9，须新冻结和明确授权；Phase 8 整体真实验收未通过 |

## Phase 7 门族与删减判据

| 现有门族 | 结构化所有者与证据 | 本轮处置 |
| --- | --- | --- |
| 曲线解释、区间外点值与未来窗口 | `descriptive_fit` / `scenario_extrapolation` 可从当前回执原位渲染；R11/R4 M02 正确边界与错误 9.9% 是正反例 | 原位 claim 已有替代；未绑定的独立句仍需旧门。不能因为一个 binding 放行整篇，也不能把尾注当预测语气纠错。 |
| 单位、显式算术、缺失归零 | 同版本回执/单位确认和宿主复算约束 typed 数值；R7—R21 的单位、CV、缺失成本回归是负例 | 保留确定性数值/版本硬门；散文单位仍未有可定位局部替代。 |
| 时间口径与统计显著性 | `comparison` 原位数值与范围有回执；散文“同比/显著”不因表格自动获权威 | `_period_label_issues` 已软化；其余旧门保留，语义质量待受限审计。 |
| 数据来源/性质推断 | 有源字段时可从 packet 证明；无字段时仅一次修订，旧 R14/M06 是负例 | `fc9ae7a` 的正文末尾说明只暴露未证实状态，若前文仍断言来源则违反总计划完成定义 #6；不得记为退役或修复。 |
| 需求覆盖与邻接自由散文 | 已核验的 `answer_bindings.v1`、原位 trace 只能证明自身；M03 自然 P/N 每例六个 claim，旁侧解释/建议未经审计 | 保持 `unassessed`；不得用 claim 数、关键词或模型自述缺口签发整篇通过。 |

只有对某族同时证明**正确解释/方法/产物保留**和**独立无据断言被局部处置**，才能删除该族散文硬门及其专属测试。若做不到，应记录未退役及原因，不以行数减少换取误放。`fc9ae7a` 的尾注问题是当前已知设计风险，进入 Phase 9 前必须显式列为未闭合项或用正反证据完成局部替代。

## 复杂度和本次收敛证据

对总计划编写时 `5176c411` 至起点 `fc9ae7a` 的 `git diff --shortstat`：`src` 16 文件 +4785/−342 行，`tests` 32 文件 +5309/−183 行，`scripts` 7 文件 +656/−191 行；`publication_synthesis.py` 单文件 +2720/−79 行。该量说明重置期间既有原位 claim 能力，也有尚未退役的并行旧门，不能称已经完成减法。已按证据退役的例子包括未接线离线选择器（`a84dbc1`，相关源码/测试净删）和死附录（`fc9ae7a`）；这不抵消总体增长。后续优先证明旧入口无调用、旧门已有等价结构替代、正反价值不回退，再删源码和镜像测试；不为缩行数砍掉当前唯一安全边界。

本轮 Phase 8 报告把同版本 `publication_audit_view` 的宿主原位 claim 数标作 `verified_host_spans`，整篇数字与自由散文仍 `unassessed`，总判定不变。定向审计测试 21 passed；只读回放自然 M03-P/N 归档各为 6 个可定位 claim、0 个不可定位，整篇仍未评估。这项变更不新增 oracle、词表、模型审核或 Provider 调用。

当前改动在 fresh `tmp/trust-reset-stage-gate-20260925-r1` 完成 full-offline：**3015 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `BD154DC2B2A041F3963063F2DF4F8FEDCFE6207830A50DF74AA314B5BBB437C3`，runner 显式 `provider_calls=forbidden`。这是 E2，不是 Phase 5/C 自然 Shadow、当前提交 E3、真实 E4 或正式发布切换。

随后在该代码提交 `main@959ea6a11f2689b097d5c118e043cacd1dde6c7a` 完成 fresh `tmp/trust-reset-stage-e3-20260925-r2` Provider-disabled 内置浏览器完整矩阵：16 会话，14 completed、预期保存故障 1 unknown、预期预算耗尽 1 failed；实际 Provider initiated **0**。明细、会话、运行端口/PID、导出哈希及局限见 [当前 HEAD 浏览器审计记录](2026-09-24-trust-reset-current-head-browser-rehearsal.md)。`r1` 因官方 IAB 无现存 tab、桥接策略报错未启动浏览器矩阵；用户明确允许新建一个 IAB tab 后，才在 fresh `r2` 完整重跑，未把 `r1` 混入结果。当前审计器只读回放旧完整真实 P08 仍为六例、`verdict=failed`，分维为执行/导出 failed、证据/价值 unassessed、声明 passed，宿主原位 claim 0。新 E3 不升级这些真实 E4 结论。

## 原始目标防遗漏索引

| 上位目标 | 进入 Phase 9 前必须核对的内容 |
| --- | --- |
| VP G1—G6 / P1—P6 | 描述性发现、待验证解释和有条件可逆建议不被静默清除；版本变化使旧证据失效；竞争假设有真实 ID/反证/未决；不同身份视角不改变事实；分析、确认、导出、刷新和 SSE 不回退。 |
| IC 原则 / IC1—IC5 | 仅真实业务歧义暂停；同范围确认复用、范围变化重问、skip 不授权；方法许可/数据性质不挂起；用户主目标不被子指标缩窄。 |
| CP CR01—CR07 / AC01—AC40 | 终局包与正文/导出同版本；事实组与省略可恢复；明确子问题有答或具体缺口；数字/单位/方法绑定；深度与图文保真；错误局部受限且独立可信内容保留。 |
| 重置计划完成定义 1—15 | 结构化权威、宿主渲染、canonical history、受限审计与降级、历史正反保留、当前 HEAD E2/E3、经新授权的完整 E4，分别记证据等级。 |

### 进入 Phase 9 前的逐组核对

| 需求组 | 当前可核代码/证据所有者 | 未完成或不得升格的部分 |
| --- | --- | --- |
| VP G1—G3、IC 1—4/6 | 既有确认策略、计划/路由、canonical history；R11/R16 与 IC-B 矩阵有本地和旧 E4 正反 | R11 原句“10%”缺单位确认；R16 的中文订单数与英文列语义映射、跨轮完整方法价值不能从旧文本倒填。IC5 最新完整 E4 仍 `executed_failed`。 |
| VP G4—G6、P5 竞争假设 | 现有受众表达、analysis_state、真实假设 ID/原回执测量复核、工具/SSE/导出/恢复 | M04 关系的测量可核不等于假设解释被回答；当前 HEAD 脚本 E3 已跑，E4 尚待，不能以旧脚本/历史通过替代。 |
| CP CR01—CR02/CR06 | final packet、同版本回执、fact group/omission、artifact、canonical history 与浏览器持久化 | R4 M03 图表及六源解释的等价价值需和原位比较分开；导出/刷新只在对应代码 HEAD 的批次成立。 |
| CP CR03—CR04 | `answer_bindings.v1`、确认记录、宿主复算 renderer 和原位 trace | 覆盖身份仅在宿主证实后可 `answered`；旧六场景要求记录为 0，不得填“已覆盖”。未知单位/方法仍 `unassessed`。 |
| CP CR05/CR07、重置完成定义 #6/#10/#11 | 旧散文门、局部 typed 渲染、一次修订、只读受限审计输入 | 自然 M03 正确解释与无据建议同在；有效 binding 旁独立 99% 仍可误放；尾注可能与错误来源正文冲突。无局部可信处置和自然语义校准，不得宣称 Phase 7 退役或整篇质量通过。 |
| 重置完成定义 #7—#9/#12—#15 | `publication_audit.v1` validator/one-shot Shadow、Phase 8 分维审计器、现有 E3/E4 runner/账本 | 普通路径 Shadow 未调度，自然质量分母未校准；D 默认策略未裁决；当前 HEAD 完整 E3 已跑，未来冻结后 E4、正式发布/部署分别是独立证据。用户工作树须保留。 |

### Phase 9 前总计划逐项核对结论

完成定义 #1—#5 的现有代码所有者已列出；#2 的非词面暂停、#3 的局部观测/情景重算、#4 的 canonical history 与 #5 的无第二套 planner 都有本地证据，但 R11 原句尺度、R16 业务映射、M03 正文价值和 M04 关系解释使跨历史完整等价仍未通过。#6 的末尾说明风险未闭合。#7—#9 的受限审计协议与单次模拟有 E2，真实 Shadow 调度、自然质量及正式降级未通过。#10—#11 的历史正反要求未通过完整自然验证，且不得以删除正确解释或单个 99% 样例替代。#12 的当前代码 E2/E3 本地矩阵已有隔离收据，其中 E3 不持久逐轮 terminal 序列，不能独立证明唯一 terminal。#13 是未来真实批次的精确冻结/授权要求，旧授权不得复用。#14 的旧完整 E4 失败，须在 Phase 9 新批次验收。#15 本轮工作树 clean，未覆盖用户文件。这是**无遗漏的依赖核对**，不是 15 项都已完成。

Phase 9 入口：按用户确认的顺序，本地分层契约、当前代码 E2/E3 和原始目标核对已准备；Phase 5/C 自然 Shadow、Phase 6 A/C/D、Phase 7 逐族退役及 Phase 8 真实整体验收明确保持 open，进入系统矩阵后仍须逐项解决，不能把“到 Phase 9”写成前置阶段退出。下一次真实 Provider 先精确冻结，再取得该冻结专属授权；不以连续 E4 为离线状态机问题打补丁。

2026-09-26 Phase 9 R1 已完成 fresh 本地回归和零调用冻结；真实矩阵 M01 后因 M02 发送时自动审批拒绝而停止。M01 11 次 Provider 发起、M02—M06 无发起，不能称完整 E4；精确身份、会话、账本、拒绝原因及新的授权门见 [R1 授权停止记录](2026-09-26-trust-reset-phase9-r1-authorization-stop.md)。

### 2026-09-26：Phase 9 操作路径纠偏（Phase 5—8 状态不倒填）

用户已手工确认上传控件可用；先前自动化点击落点不准，不能据此认定产品上传故障。原浏览器协议 r2 未发送任何提示、Provider initiated 0，且不适用于改变控制路径后的批次。按用户授权，仅改变测试控制方式：保留现有隔离服务、应用 `/api/upload`、`/api/chat`、SSE、持久会话和原 Provider 账本，增加冻结摘要约束的 HTTP 驱动；六场景顺序、输入、提示与 oracle 不变。Provider-disabled 单例在 `tmp/phase9-http-probe-20260926-r1` 验证了 F-SALES.csv 上传票据 SHA256、同票据聊天、唯一 `turn_end` 与持久 `completed`（session `eec87d2e3bcc`），`forbidden_provider_transport=0`、实际 Provider 0；它不是 M01—M06 完整本地矩阵。根 `AGENTS.md` 已补充 HTTP 控制路径与证据降级规则。

下一真实批次必须用新的提交、`p08.real_matrix.v3` 操作协议和 HTTP driver digest 重新精确冻结并取得该身份的授权；r2 的 browser-protocol 授权不可移用。HTTP 批次可检验自然模型、工具、票据绑定、SSE、会话与导出；上传按钮、视觉原位渲染和浏览器刷新仍为 `unassessed`，不得称完整浏览器 E4 通过。

Phase 5 的普通路径 Shadow 调度与自然 claim 分母校准仍 open；Phase 6 A 的 R11/R16/M03/M04 跨历史价值、邻接散文局部安全、C 自然审计和 D 正式默认裁决仍 open；Phase 7 的散文门逐族退役和错误来源正文被尾注抵消的风险仍 open；Phase 8 的本地分层契约已有 E2/E3，真实完整验收仍 open。新自然矩阵结果须逐项对照这些门与 R4、R7—R21 的正反轨迹，不以六例单一 verdict 代替阶段审查，也不由测试失败立即扩大词表或新增投影。

HTTP 控制路径的 E2 全量回归在首次长目录运行中有一例报告写文件失败；同例在短目录单独通过。随后在 fresh `tmp/p9h2` 重跑全量为 **3017 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `D84F72BE48130E53D06834B4E9881D870DCCC9131957B09980476589920BE8ED`，Provider 仍为 0。复核服务端 `/api/chat/resume` 实际发送 `turn_start` 后修正 HTTP 驱动的对应校验，定向上传与 launcher 测试 **24 passed**。这些只证明本地代码和控制协议，不能替代下一冻结批次的真实自然模型结果。

新授权的 [Phase 9 R3 真实模型矩阵](2026-09-26-trust-reset-phase9-r3-real-matrix.md) 已按 M01—M06 完整执行，90 次物理调用核算闭合，总判定 **`executed_complete / not_accepted`**。M02/M04 为产品执行阻断，M06 的选项 B 存在但测试控制文字失配；M01/M03/M05 有自然价值却均无宿主原位 claim。Phase 5/C、Phase 6 A/C/D、Phase 7 和 Phase 8 完整 E4 退出条件均未因此满足。下一动作是依据 R3 与 R11/R16/R4/R7—R21 的正反证据审查和简化阻断门、修复控制协议，再做 fresh 本地验证；新真实批次须重新冻结及授权。

### 2026-09-26：R3 后 M02/M04 本地收敛（阶段状态不升格）

依据 [R3 批后 RED 与正反边界](2026-09-26-trust-reset-phase9-r3-real-matrix.md#批后-m02m04-收敛后续-head本批结论不回写)，M02 的正常任务完成现在由现有 `TaskManager.update` 顺序启动同计划下一就绪任务；原证据完成路径中重复的推进段已删除。无活动计划的旧任务、其他 session 不推进；原始数据作用域拒绝门不变。M04 仅把宿主已有的 `metric_missing_in_evidence` 和同计划证据的实际测量指标写入一次修订提示，关系继续 `inconclusive`，未核验的 `refuted` 仍被拒。没有新增 planner、claim 类型、词表、账本或 Provider 调用。

fresh `tmp/trust-reset-r3-followup-20260926-r1` 的 full-offline 为 **3021 passed、1 skipped、16 warnings、0 failures**；JUnit SHA256 `49AD414B41EA8ED76BE3E2FB1C781F6A96DDF0CA42AD98A7EEF75E37720BB474`，runner 显式 `provider_calls=forbidden`。完整回归后发现并补上“活动计划 ID 必须非空”的一行边界；该 RED 先失败，修复后受影响的作用域、任务、假设测试 **261 passed**。因此全量回归对应这一行补充前的版本，最终工作树的补充行由定向回归覆盖。R3 的真实账本与六例判定均不回写。

Phase 5/C 自然 Shadow 调度与分母仍 open；Phase 6 A 的普通自然 typed 生产、M02 的单位与占位绑定、M03/M05 的旁侧散文、M04 的解释身份仍 open，C/D 也未退出；Phase 7 的局部替代与旧门退役、Phase 8 的完整真实/视觉验收继续 open。下一真实批次只能在新提交、冻结和精确授权后启动；本地修复不自动构成阶段退出。

这张表是**实施与验收缺口清单**，不改变原计划退出要求。历史 R7—R21 的边界分类和具体源会话见 [跨历史门记录](2026-09-24-trust-reset-cross-history-gate.md)、[双轨校准](2026-09-24-trust-reset-dual-track-calibration.md)；R4 中断、R16 完整通过项和本地真实会话须共同参与正反验收。

### 2026-09-26：R4 完整真实矩阵后的总计划核对

用户授权的 `main@d13653f` 冻结批次已按 M01—M06 全序执行，权威账本 **88 started / 88 dispatched / 0 failed**；六例宿主原位 claim 均为 **0**。M01/M03/M05/M06 completed 并保留部分有用分析，M02/M04 failed；M06 实际完成成本业务确认和恢复，但当前审计器误把结构化 `metric_definition` 记为 unauthorized。HTTP 控制不验收上传按钮、视觉渲染或刷新。精确身份、每例正反内容和逐门判断见 [R4 总计划复核](2026-09-26-trust-reset-phase9-r4-plan-review.md)。

当前状态不倒填：5.3/5.4 普通路径 Shadow 与自然 claim 分母、6.A 的普通自然 typed/价值/邻接散文、6.C/D、7.2 逐族退役和 8.2/8.3 真实完整质量仍 open。下一步先修正可证明的 M06 审计假阴性，再以 R11、R16、旧 R4、R7—R21 与本批双向评审决定 Phase 6 产品切口；不把 M02/M04 的语法失配单独当作阶段主线，不因六例终态将正确解释清空。批后局部 parser/测试草稿已经撤回，本记录先于新的产品代码变更。

**收敛核对**：普通 R4 的 `typed_trial=False`，已有宿主候选未注入；模型自行尝试的 M02/M04 binding 也未通过。六例零 claim 不能证明 opt-in 生产者失效，亦不能和自然 M03-P/N 的 opt-in 六块正例相互否定。M06 审计假阴性已在本地用真实记录形状及不相关业务问题负例修正：21 个审计测试通过，只读回放原批仅改变该单项判定，原 R4 审计文件未修改，批次总失败不变。阶段依赖、跨历史正反价值与删减停止线见[收敛图](2026-09-26-trust-reset-convergence-map.md)。这项本地修复只更新 8.1 的判定准确性，不提升 Phase 5/6/7 或真实 E4 退出身份。

### 2026-09-26：Phase 6 A3 默认关闭的答案分区试验

用户选定“已核验事实 / 待核验解释”分区作为受控试验，正式默认不变。当前只在 `typed_trial=True` 且本轮实际注入宿主候选时，继续用原 `answer_bindings.v1` 解析、原散文门校验与原宿主 renderer：已验证 binding 的占位符移至“已核验的回执结果”，模型原文的原位置仅留编号引用，其余解释原序保留在“待核验的分析与解释”引用块内。引用块防止模型自带 `## 结论` 等标题在 Markdown 中跳出待核区，宿主的每个表格以独立小标题呈现。无 binding 时，整段模型解释只在待核区；引用旧快照或外来事实仍拒发。现有来源/情景边界说明在此试验中置于待核区开头，不靠末尾说明为前文断言背书。原位 trace 仍按最终可见答案生成 span 与 digest。

RED 是同一六来源回执样本中正确解释与 claim 混排，旧布局无待核分区；正例要求保留六个宿主结果和解释原文，反例要求无 binding 不得出现已核验区、伪造引用不得借分区发布、普通默认布局不变。定向 `tests/test_confirmed_multisource_comparison_claim.py` 与 `tests/test_typed_preview_comparison_claim.py` 为 **10 passed**。这个试验不把待核解释判为真，也不逐句识别错误建议；旧散文门继续运行，所以 Phase 6 A3、Phase 7 逐族退役和正式 D 均未退出。自然 E4、图表/导出/刷新和 R11/R16/M04 跨历史价值尚须独立验收；R4 归档不倒填。此轮新增分区逻辑而没有安全依据删除旧门，复杂度债仍在，不能宣称已完成减法。

对既有自然 M03-P/N 归档做了**零调用只读回放**：先校验归档答案 SHA 和每个原位 trace span，再以当前 packet 的原占位符重建草稿，经新分区及原 renderer 重放。P/N 均为六个宿主 span，全在已核验区；最终排版 P 的已核验区 1285 字、待核区 1244 字，N 分别为 1285/1727 字。正确方法解释仍在待核区，N 的额外建议也仍在待核区，未被证明正确或安全。这只证明分区机械性与历史正文保留，不是新自然 Provider、当前服务浏览器或 Phase 7 局部语义审计通过。

最终本地版本在 fresh `tmp/trust-reset-converge-20260926-r4` 完成 full-offline：**3026 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `FB2E842F36A364815E7C95DA21AAF24C189E4C16360E5C6D3DAA1E7581A40DF7`，runner 显式 `provider_calls=forbidden`。先前 `r3` 因检查自然 Markdown 容器时主动中断，不能记为完整结果。此验收等级仅为 E2，不替代当前 HEAD 的 Provider-disabled E3 或新冻结自然 E4。

## 更新规则与停止条件

每次代码变更先在对应 ID 下写 RED、结构化替代、拟退役旧门、正反回放及不可证明项；验证后更新精确 commit/运行目录，不覆盖旧失败。出现新词表硬门、模型 finding 无同 claim/evidence 绑定、以末尾说明纠正错误正文、为绿灯削弱回执/版本/单位、或新增 planner/账本/浏览器框架时，停止该实现并回到总计划。进入 Phase 9 前逐项核对本表与三份原始计划和总计划完成定义，明确“机制就绪”与“阶段退出”的差别。
