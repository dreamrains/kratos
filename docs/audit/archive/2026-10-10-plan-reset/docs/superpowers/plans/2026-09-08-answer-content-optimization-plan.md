# 回复内容完整性与表达优化：补充整改计划

日期：2026-09-14｜版本：v1.3｜状态：CP0—CP6 已合入 `main`；最新 AC40/E4 为 `main@b833501` 的 R16 完整批次，只有 M05 通过，M01/M02/M03/M04/M06 失败，AC40 保持 `executed_failed / not_accepted`；对应内容、发布、结构化收敛和上传绑定修复已提交为 `main@1dd19e8` 并通过 E1/E2/full-offline 与重点 Provider-disabled E3，新的 E4 尚未冻结或授权。

目标：在保持来源、口径、版本与推断边界的前提下，使已经完成的有价值分析进入最终回答，并按用户需求组织清楚、完整的表达。

## 1. 文档入口与适用范围

| 文档 | 用途 |
|---|---|
| [诊断报告](../../audit/2026-09-07-answer-content-and-presentation-audit.md) | 当前源码、保存会话与离线反例依据 |
| 本计划 | 范围、优先级、实施顺序、依赖与唯一阶段状态表 |
| [开发设计](../specs/2026-09-08-answer-content-design.md) | 发布生命周期、数据契约、事实恢复、覆盖与算术检查 |
| [回答内容与排版规范](../specs/2026-09-08-answer-presentation-contract.md) | 内容优先级、按需展开、图表引用和样例 |
| [验收矩阵](../validation/2026-09-08-answer-content-acceptance.md) | 正反例、质量指标、证据等级、阶段记录模板 |
| [实施交接](2026-09-08-answer-content-handoff.md) | 开发入口、重叠改动处理、可粘贴任务说明 |
| [规划基线](../../audit/2026-09-08-answer-content-planning-baseline.json) | HEAD、dirty、相关文件与全部现有受控文件字节哈希 |
| [实施记录](../../audit/2026-09-08-answer-content-implementation-record.md) | 独立分支、实际变更、两次离线运行、文件摘要与证据边界 |
| [实施差距自检](../../audit/2026-09-08-answer-content-implementation-gap-audit.md) | 计划文件面、AC01—AC40实际状态、代码风险与合并门槛 |

本包细化 [分析价值保留总计划](2026-09-06-analysis-value-preservation-plan.md) 的 P3/P4/P6，不替代 Route A、不从 P0 重做已有工作，不推翻历史测试结果。新的反例说明原验收覆盖不足，须新增回归；不能把旧 passed 当成新用例已通过。

与 [P08](../validation/2026-09-07-p08-full-matrix-validation-plan.md) 的关系：复用其真实验证与调用核算边界。CP6 的脚本模型浏览器通过不等于 P08 通过；下一真实批次仍须完整 M01—M06，新增内容质量样本另附冻结清单，不在执行中临时追加。

实现最初位于 `codex/answer-content-optimization`，基于 `85f62794e24cfa95a864293d159e0208c8615a4b`；提交 `61e7b47`、`bd42678` 以 patch-equivalent 提交 `1cd415e`、`5446e1a` 进入整合分支，最终随 `9e51b81` 合入 `main@f8ee717`。状态文档提交 `be5ee9a` 已普通推送到远程 `main`；未部署或启动真实 Provider。

## 2. 基线与已知结论

规划基线 HEAD 为 `8969abd6bfdf24914d365fdff61ebec42ae56c8d`；实施时原分支已前进到 `85f62794e24cfa95a864293d159e0208c8615a4b`，因此独立 worktree 从后者创建。原工作树的未提交并行修改保持原状，没有复制进本分支；合并时须按实际函数块保留届时主分支新增改动。

诊断已证实：旧发布包可被终局复用；每来源默认 10 项事实与 180 字符字符串裁剪；Python 技术元数据挤占业务结果；实际加权敏感性结果未进入回答；格式提示偏向紧凑；现有正文校验漏掉数量级错误。没有证实：所有变短均由硬删除造成、原始数据已丢失、特定 CSS 一定有缺陷、历史与当前运行模型完全一致。

历史 `159 passed` 仅作为 09-07 诊断背景。本分支最终重新执行了专项定向、完整离线和 Provider 禁用的真实 Flask/SSE 浏览器演练；结果独立记录为 `129 passed`、`2585 passed, 1 skipped` 以及 B03/B07 两个 E3 场景。它们证明当前 checkout 的本地实现，不证明凌晨历史服务进程、真实自然模型或生产环境。

原工作树的并行文档没有复制进整合提交。`main@f8ee717` 的文件树与整合提交 `9e51b81` 一致，确认策略、工具消息配对、发布快照、候选隔离、回复级 binding、失败回滚和终态唯一性均保留。合并后的本地浏览器矩阵已在 `main@be5ee9a` 完成；full-offline 仍保留用户已接受的单一隔离夹具例外，不改写为全绿。

## 3. 需求与非目标

| ID | 必须实现的可观察行为 | 非目标/约束 |
|---|---|---|
| CR01 | 最终包反映最后有效结果、证据、验证与版本 | 不是只多调用一次构建函数；正文、收据、导出必须绑定同一包 |
| CR02 | 业务事实组完整，遗漏可定位恢复 | 不把所有原始数据塞进 prompt，不以简单加大常量交差 |
| CR03 | 用户明确子问题均有回答或具体缺口 | 不把关键词出现、任务 completed、模型自报当覆盖证明 |
| CR04 | 绑定数字、单位、派生计算一致 | 不承诺确定性理解任意自然语言；未知必须如实记录 |
| CR05 | 深度跟随任务和明确要求，保留有效解释 | 不以增加字数、emoji 或统一长报告作为质量目标 |
| CR06 | 图文对应、刷新/导出一致、审计可追溯 | 不删除技术收据，不放宽图表来源和推断边界 |
| CR07 | 未支持主张受限，独立可信部分保留 | 不用一条错误清空全部答案，不绕过现有阻断与确认 |

内容分级：明确请求与解释必需事实优先；已有且影响口径/判断的比较、敏感性与替代解释其次；可选延伸最后。无依据行业评级、因果解释、外推数值不是需要恢复的内容。

## 4. 实施工作包

阶段编号采用 CP，避免和现有 P0—P8、IC0—IC5 混淆。每阶段先写能识别本次反例的 RED，再最小修改、定向回归和记录。已有测试不得为绿灯削弱。

| 阶段 | 工作与产物 | 主要修改面 | 依赖与退出条件 |
|---|---|---|---|
| CP0 基线与接口映射 | 目标 checkout、dirty 归属、契约映射、正反例 fixture、缺口记录 | 文档/测试；不改算法 | 确认新旧接口可衔接，明确已有/需适配/缺前置；与 P08 重叠修改归属清楚 |
| CP1 发布快照闭环 | 分离预览与最终包；终局重新验证与构建；内容指纹、发布绑定、幂等持久化 | loop、publication_synthesis、analysis_state、report | CP0；AC01—AC07 通过，两条执行路径都覆盖；P08-02/04 不回退 |
| CP2 业务事实与可恢复摘要 | 工具适配器、事实组、受控详情恢复、分层预算和省略清单 | publication_synthesis、工具结果/收据、compact | CP1；AC08—AC15；没有“读得到但提示不知如何恢复”的悬空引用 |
| CP3 需求到正文覆盖 | 复用计划、保留用户原句、正文定位与答案/缺口映射 | context、计划/证据契约、publication_synthesis、loop | CP2；AC16—AC21；不把审计表覆盖当正文覆盖 |
| CP4 数字一致性 | 类型化量值、受限运算、正文绑定、位置化问题与一次修订 | evidence_input/契约、publication_synthesis、loop | CP2、CP3；AC22—AC29；误报负例与数量级错误均被区分 |
| CP5 表达与图文 | 统一深度策略、按内容组织 Markdown、图表引用、审计分离 | prompts、synthesis_policy、app.js、report | CP3、CP4；AC30—AC35；简短模式与详细模式同样完整可信 |
| CP6 联调与交付 | 全离线、脚本模型真实浏览器、对照评审、迁移与回退验证 | tests、隔离 fixtures、验收记录 | CP1—CP5；AC36—AC40；真实 Provider 待独立授权和新批次 |

CP3/CP4 仅在 CP2 契约稳定后可独立开发；这不是创建子代理或并发修改共享文件的指令。CP1 可形成独立修复补丁，但不能据此宣布内容优化全部完成。

## 5. 完成标准与取舍

核心门槛：指定验收样本的必答项“答案或具体缺口”覆盖率 100%；必须保留事实组保留率 100%；被选择与被省略组的归属清单完整；已绑定数字的一致性检查零已知错误；未知项不能标为 checked；没有新增无依据因果/外推结论。

覆盖率分母来自独立 fixture/评审标注，不从模型输出或已选事实反推。支持“全部来源/分组”且内容过大时，正文须有清楚总览、完整可访问表和省略范围，不能只丢一个内部 receipt id；用户明确要求正文逐项时按节展开，容量无法满足则具体说明未展开项，不能声称已完整回答。

明确简短请求优先控制篇幅，但保留所有必答结果与解释关键边界。一般分析不必主动附冗长方法章节；多指标、详细验证要求不能被“2–4 小节”压缩。格式规范不能更改事实与置信度。

正常路径不新增模型审核调用；修订沿用现有一次额度与统一预算，不通过新阶段另获一次重试。规则不能可靠判定的自然语言语义，按 unknown/人工验收处理，不能用伪精确通过率掩盖。

## 6. 风险和工程约束

- **共享 loop 冲突**：保留 P08 pending_fallback_resolution、正确工具消息、终态唯一性；基于实际函数重叠合并，不复制整文件。
- **只更新包、不更新答案**：新包可能与先前生成候选不一致；必须执行 CP3/CP4 对绑定与覆盖的检查，必要时走现有一次修订。
- **扩大信息导致超预算**：完整详情保留在会话内，prompt 只发必要事实与稳定引用；预算不足输出部分完成和具体缺口。
- **新检查过度保守**：明确区分 invalid 和 unassessed；不支持的全自动判断不加泛化阻断，不能清除原来可发布的观察。
- **读取历史/外部文件**：已有受控读取器校验会话目录、版本与哈希；失败则缺口，不重算用户原始数据或静默扩大权限。
- **回退与兼容**：优先局部补丁回退；保留新审计记录可读与旧会话原文。禁止整库 reset、删除会话、篡改旧结果。

## 7. 唯一阶段状态表

| 阶段 | 状态 | 证据 |
|---|---|---|
| 文档准备 | completed | 诊断、计划、设计、表达规范、验收矩阵、交接、实施记录与差距关闭审计已同步 |
| CP0 | completed_local | 独立 worktree/分支、固定小中大 fixture、AC01—AC40 映射及 Provider 零调用边界已记录 |
| CP1 | completed_local | preview/final 分离、内容寻址快照、正文绑定、幂等修订、写入失败回滚、流式候选隔离与回复前持久化已实现 |
| CP2 | completed_local | 完整 FactGroup、同会话 detail_ref/hash、扫描与省略披露、公平分源预算、compact 引用保留已实现 |
| CP3 | completed_local | 持久化需求生命周期、撤回/替换、内部 answer-bindings 解析/宿主校验及状态区分已实现 |
| CP4 | completed_local | 类型化量值、受限 Decimal 派生运算、单位/来源/版本/情景绑定及合并修订问题已实现 |
| CP5 | completed_local | 深度策略、Markdown 表格、全角 chart wrapper、会话内图表匹配、桌面端图表/公式/导出体验已实现 |
| CP6 | completed_local | `129 passed` 定向、`2585 passed, 1 skipped` full-offline、两条真实 Flask/SSE 脚本浏览器场景通过 |
| 本地 `main` 整合 | merged | `main@f8ee717`；整合定向 129＋301 passed；full-offline 的环境例外由用户接受用于合并，但不记为全绿 |
| 合并后浏览器 | passed_local | `main@be5ee9a`、`tmp/main-ic4-browser-20260909-be5ee9a`；CONTENT-B03/B07 与共用 B01—B06、IC-B01—IC-B06 完成，Provider initiated calls=0 |
| 真实 Provider 验收 | executed_failed / not_accepted | AC40 随 P08 M01—M06 完整批次执行；账本 77 started / 77 dispatched / 0 failed。M03 发布收敛/Workbench 不闭合，M05 发生未知单位→“块钱”漂移，M06 残留原始 `[[chart:]]` 标记，内容硬门槛未通过。 |
| AC40 失败项本地修复 | completed_local / E3 passed | `main@13c129a`：可恢复 fallback 不再作为终态错误；展示回合仅在数据身份未变时复用已接受发布快照；未知金额单位和混合日期窗口受确定性边界约束；SSE 非有限数转为严格 JSON `null`；空 `[[chart:]]` 转为可见缺失提示。内容/Web 定向 208 passed；`main@176f5f2`、`tmp/repair-browser-20260910-r3` 的联合浏览器复验通过，六来源 Markdown/发布报告、表格/公式/Plotly/刷新和控制台均已核对，Provider initiated calls=0；真实 Provider 未复验。 |
| AC40 / E4 修复后复验 | executed_failed / not_accepted | `main@3873ff9`、冻结 SHA-256 `7156c9e...8827f44`；账本 80 started / 80 dispatched。M05 六种表达均保留 12/120、范围、未知金额单位和受限证据等级；M06 正确区分已计算、未计算、证据不足。M02 合规 D7/D30 边界被发布门拒绝；M03 六来源正文/刷新/Markdown 完整但压缩保存 500；M04 正文重判正确但 Workbench 仍把 v1 旧事实列为 verified。 |
| AC40 / E4 R10 复验 | executed_failed / not_accepted | `main@dc44382`、冻结 SHA-256 `0879740...9e451`；账本 78 started / 78 dispatched。M01/M04/M05 通过；M02 的非预测假设边界被误拒，M03 的六来源事实虽在正文/刷新/导出/压缩后完整保留但相邻日期被错误称为“同比”，M06 的成本范围未形成真实确认暂停。 |
| AC40 最新失败项本地修复 | completed_local / E3 passed | `main@16d2257`：发布门允许无数值的非预测假设边界但继续拒绝未观测率；显式相邻日期的“同比”会触发一次修订；误标方法确认的真实成本/窗口/分母口径由宿主恢复，真正方法许可仍非阻塞。隔离回归 152 passed 与 126 passed；full-offline 2626 passed、1 skipped。`tmp/repair-browser-20260913-r10` 的六来源刷新、压缩和 9380 字节 Markdown 保留全部六组金额/变化/记录数，成本口径与方法许可路径通过，Provider initiated calls=0；新的真实 Provider 批次未执行。 |
| AC40 / E4 R11 复验 | executed_failed / not_accepted | `main@fe83160`、冻结 SHA-256 `c41c606...d7e0`；账本 89 started / 89 dispatched。M01/M03/M05/M06 通过：六来源内容与 210→231、12/120、未知单位、刷新/导出及已计算/未计算边界均保留。M02 的无数值 D30 边界仍被误拒；M04 正文正确但结构化 evidence/hypothesis 状态为空，不能满足可审计内容闭环。 |
| AC40 R11 失败项本地修复 | completed_local / E3 passed | `main@bed3b15`：发布门识别明确不报告 Dxx 数值的边界；计划、measurement 与竞争假设使用既有契约向模型公开并兼容既有自由格式记录。隔离回归 131 passed 与 80 passed，full-offline 2630 passed、1 skipped；`tmp/repair-browser-20260913-r11` 的 B02/B04 重点复核通过，版本变更后旧证据进入 exclusions，Provider initiated calls=0。新的真实 Provider 批次未执行。 |
| AC40 / E4 R14 复验 | executed_failed / not_accepted | `main@ae8a5f4`、冻结 SHA-256 `b4826cb...a0cce`；账本 74 started / 74 dispatched。M01/M03 通过；M02 表头边界误拒，M04 计划任务启动死锁，M05 六轮未保留总额且出现 CV 算术矛盾与样例/账本推断，M06 虽保持已计算/未计算/证据不足和确认事件，却仍含无依据数据来源/总体波动解释。 |
| AC40 R14 失败项本地修复 | completed_local / E3 passed | `main@6d6f7e0`：沿用一次修订，允许预测阻断标题，拒绝非零均值下“CV 分母为 0”和恒定样本无依据来源/总体语义；Stage3C0B 任务原子启动/推进并在全部终态后释放 scope。隔离回归 324 passed 与 80 passed，full-offline 2637 passed、1 skipped；`tmp/repair-browser-20260914-r15` 的 B02/B04 completed，Provider initiated calls=0。新的 E4 尚未冻结或授权。 |
| AC40 / E4 R16 复验 | executed_failed / not_accepted | `main@b833501`、冻结 SHA-256 `a018f0d...92306`；账本 72 started / 72 dispatched。只有 M05 通过；M01 无依据来源，M02 合规边界误拒，M03 “同比例”误判及样例推断，M04 结构化竞争证据未收敛，M06 缺失成本归零；同批发现上传引用重复。 |
| AC40 R16 失败项本地修复 | completed_local / E3 passed | `main@1dd19e8`：沿用一次修订和既有状态，修复否定预测边界、同比标签、无依据来源、缺失归零、结构化收敛及文件引用精确去重。隔离回归 165 passed 与 173 passed，full-offline 2644 passed、1 skipped；`tmp/p08-post-r16-browser-2` 的上传绑定、B02/B02-NEG 和 B04 通过，Provider initiated calls=0。新的 E4 尚未冻结或授权。 |

`completed_local` 表示代码、离线回归和本地脚本浏览器门槛已达到，不代表自然模型内容评分、部署或生产验证。详细证据见验收与整合记录；最新 AC40 的 `executed_failed` 不能由本地修复或局部场景通过升级。后续复验仍须使用新的冻结清单、零调用预检和明确 Provider 授权。

## 8. 2026-09-14 R16 E4 与 R17 本地状态

- R16：`main@b833501` 按冻结 SHA-256 `a018f0dfb96eeb07c697713b8d36e5a151d15de0ebb403447036a51d6b892306` 完整执行 M01—M06，账本 72 started / 72 dispatched。只有 M05 通过；M01 无依据来源，M02 合规非预测边界被误拒，M03 “同比例”误判及样例推断，M04 结构化竞争证据未收敛，M06 缺失成本归零。同批确认上传文件引用在会话中重复展示。因此 AC40 保持 `executed_failed / not_accepted`。
- R17：`main@1dd19e8` 沿用既有一次修订、分析状态和上传 binding，修复上述确定性边界与结构化收敛，并仅补齐缺少的精确文件引用。隔离回归 165 passed 与 173 passed，full-offline 2644 passed、1 skipped；Provider-disabled 内置浏览器 `tmp/p08-post-r16-browser-2` 验证上传引用发送/刷新均为一次，B02/B02-NEG 与 B04 完成，控制台无 error/warning，真实 Provider initiated calls=0。新的 AC40/E4 尚未冻结或授权。

## 9. 2026-09-20 联合本地验收收口

`main@9a3031e` 关闭不可变结果详情在复用调用 ID 时的收据身份歧义；`tmp/p08-fo-r4` full-offline 为 2713 passed、1 skipped。完整 Provider-disabled 内置浏览器目录 `tmp/p08-br-r3` 中，B03 和 CONTENT-B03 的对话导出均为 9620 字节、发布报告均为 9390 字节，全部包含 `src_1`—`src_6`、金额、日期和记录数；CONTENT-B07 刷新前后均保留表格、KaTeX、Plotly/备用链接和 120/12，740 像素视口无整页横向溢出。控制台 0 error/warning，实际 Provider initiated calls=0。

CP0—CP6 与最新本地 E3 保持 `completed_local / passed_local`；AC40 的历史真实 Provider 批次仍为 `executed_failed / not_accepted`。本次没有真实 Provider、push、部署、staging 或生产验证，下一次 E4 仍须新冻结和新授权。

## 10. 2026-09-21 目标校准附录

用户裁决把内容目标校准为：权威表述（单位/披露/来源状态）**由宿主渲染**，不解析模型散文；硬门只许封闭类检查，开放语义"召回→一次修订→advisory"；验收分层，6/6 全 oracle 硬过不再是可用门槛。

据此完成的目标校准实现（均 TDD，RED 素材优先取真实失败轨迹回放，main 上 9 提交 `dac451d`→`9dbba60`）：

- CR02/CR04（绑定数字一致）：`同比`标签跨年判定改绑 compare_periods 回执；审计端 `_find_compare_periods_receipts` 以 tool_outputs 结构化范围为权威，散文年份挖掘与 `同比(?!例)` 冗余表达式退役。
- CR06（导出一致）：导出 conversation Markdown 双产物恢复——压缩 ACK（"好的，继续。"）不再窃取回复组身份（r1/r3 双批次 M03 真实 unbound_reply 通路；真实受损会话复验恢复）；展示复用按封闭类身份门（ready+answer_sha256+指纹一致）而非 R15 措辞正则，正则外措辞的终答不再跳过全量叙事校验（R15 M05"120 块"泄漏通路收口）。
- 内容保真：压缩摘要携带确定性执行台账（Codex M03 会话 52a61396f8e6"未包含执行结果"失实摘要回放；两次失实兜底骨架替换）；被拒修订候选全文落盘 `sessions/<sid>/publication_rejected/`，且不进证据库（r2 M02 泄漏：user_correction 误分类可检索）。
- §5（不伪精确）：`single_next_step_advisory` 价值维软检查（r1 M06"下一步（单一动作）"）；审计 oracle 全部引用 VP/IC/CP 原则号，目标漂移可检。

新目录隔离 full-offline 回执：`main@9dbba60`，`tmp/p08-p16-fixloop-full-offline-1`，2812 tests / 0 errors / 0 failures / 1 skipped（235.3s，junit.xml 在档）。
