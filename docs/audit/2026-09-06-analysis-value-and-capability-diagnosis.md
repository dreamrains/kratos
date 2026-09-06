# 分析价值保留与能力完整性诊断

日期：2026-09-06。对象：`D:/Project/Daily/data-agent` 当前工作区（包括已有未提交修改）。HEAD：`9e6d1c4`。

## 结论

当前实现确实存在过度保守、摘要遗漏和合规内容被误拒绝的问题；同时，竞争假设判定又存在证据要求不足的问题。因此，不建议整体降低可信度门槛或单纯增加输出长度。

| 用户问题 | 当前判断 | 证据边界 |
|---|---|---|
| 分析是否过于保守 | 部分路径已确认：中文建议识别、粒度限制和置信度规则会误伤正常分析 | 能证明具体规则行为，不能估计全部真实回答的发生比例 |
| 有价值内容是否被裁剪、删除或放弃 | 已确认发布误拒绝、证据摘要遗漏和工作台限量展示；三者应分别处理 | 没有证明所有被摘要省略的事实都从最终正文消失，也没有证明原始结果文件被删除 |
| 意图识别、多角色区分是否正常 | 常规意图分类仍可用，但复合输入、否定表达有明确误判。用户身份适配未见完整结构化实现 | 多角色按用户确认的“业务人员、分析师、管理者”解释；熟练度适配不等于身份适配 |
| 竞争性假设等分析能力是否正常 | 模板生成、存储和部分基础分析仍在；假设判定与发布闭环不足，不能认定完整正常 | 假设的 supported 标记不等于 Workbench 的 verified；本次没有证明错误假设被工作台发布为已验证结论 |

本次完成代码诊断与可执行离线探针，没有修改产品源码或现有测试，没有调用真实 Provider，没有启动真实浏览器验收，没有 commit/push。旧记忆仅用于定位模块和了解授权边界；下列结论均重新检查了当前源码。

## 验证与复现材料

- 定向回归第一组：308 passed，覆盖意图识别、语义分类的 mock 路径、数据细化、竞争假设、回答策略、发布、熟练度、分析入口和验证层。
- 第二组：84 tests，0 failures / 0 errors / 0 skipped，覆盖工作台投影、分析质量、执行控制和系统数据分析审计。结果取自已落盘 JUnit；原命令会话在恢复时已不可读取。
- 33 个合成输入探针观察，包含正例与反例。这是诊断观察数量，不是 33 个验收通过项；它们主动展示现存缺陷。
- 两次初始回归命令包含不存在的测试文件名，均在运行前退出；更正路径后取得上述结果，不把初始命令计为通过。
- 没有全量离线回归或当前源码真实 Provider / 浏览器验收，因此本报告不构成发布就绪证明。

材料：

- [探针脚本](D:/Project/Daily/data-agent/tmp/diagnosis-20260906/probe.py)
- [探针结果及被检查源码的 SHA-256](D:/Project/Daily/data-agent/tmp/diagnosis-20260906/probe-results.json)
- [第一组 JUnit](D:/Project/Daily/data-agent/tmp/diagnosis-20260906-regression-02/junit.xml)
- [第二组 JUnit](D:/Project/Daily/data-agent/tmp/diagnosis-20260906-projection-regression-02/junit.xml)

可复现命令：

```powershell
.venv\Scripts\python.exe tmp/diagnosis-20260906/probe.py
```

探针只使用合成状态与本地函数，禁止真实 Provider 配置；意图探针提供拒绝调用的客户端，本次调用尝试为 0。压缩探针的输出目录隔离在自身目录下。回归使用已有 `scripts/acceptance/offline_test_runner.py`，其运行目录必须是仓库 `tmp` 下未存在的新路径。

## 具体发现

### D01：中文决策诉求被压成浅层描述（高优先级）

在相同 `directed_analysis` 和相同证据状态下：

- “比较两个渠道表现，并给出行动建议”得到 `analytical / light`，且 `suppressed_moves` 包含 `decision_recommendation`。
- 英文的 “Compare channel performance and recommend actions”得到 `advisory / standard`，不抑制建议。
- 中文“预测下个月销量”与英文 forecast 也分流到不同策略。
- “详细诊断渠道收入下降原因”仍被固定为 light。

来源：[策略分支](D:/Project/Daily/data-agent/src/data_agent/agent/synthesis_policy.py:88)、[英文建议关键词](D:/Project/Daily/data-agent/src/data_agent/agent/synthesis_policy.py:272)。

当前已有修改允许 `pass_with_downgrades` 下保留条件性、可逆建议，这个方向合理；但它保留原策略，所以不能解除中文请求在前面分支里已有的建议抑制。提示词中“显式请求时可给条件建议”又与 `suppressed_moves` 冲突，最终模型如何取舍仍需端到端验证。

建议：将分析深度、建议需求、证据强度分开表达；中文和英文等价请求应形成等价契约。保持同一证据门槛，依据用户请求与任务复杂度决定展开深度。

### D02：外推检查误拒绝边界说明和补数据计划（高优先级）

观测区间为 D1—D7 时，下列两段均被拒绝：

> D7 留存为 10%。当前不能预测 D30，需补充数据。

> D7 留存为 10%。建议继续收集至第30天再验证。

当前正则只检查正文是否出现超出范围的 D/第 N 天，没有区分预测断言、否定语句和未来数据采集计划。无依据的“D30 留存预计为 5%”被拦截是正确正例，不应为修复误伤而放开。

来源：[时间点校验](D:/Project/Daily/data-agent/src/data_agent/agent/publication_synthesis.py:283)、[一次重写](D:/Project/Daily/data-agent/src/data_agent/agent/loop.py:1345)、[流式终止路径](D:/Project/Daily/data-agent/src/data_agent/agent/loop.py:2623)。

实际机制是整份候选回答被拒绝，允许一次重写，再失败则返回错误；并非仅删除违规句。因此一个边界句可能阻断其余有效结果。

建议：先区分主张类型和语境，再定位具体不合规主张；保留已支持的观察和边界说明。修复后的回归必须同时证明错误预测仍被挡住，不能只增加否定词白名单。

补充：`publication_contract` 仅把 `ab_test` 的 `test.p_value` 视为已执行推断，`causal_analysis` 等计算的推断结果没有统一进入此字段。对整份正文做“本轮没有检验”判断存在工具覆盖不完整风险，应改为与具体主张绑定。

### D03：多层摘要会遗漏早期来源、关键分组和有效证据（高优先级）

发布包只保留最近 4 个来源、每个来源最多 10 个事实；递归深度最多 5，每个数组只遍历前 3 项。选择不考虑问题覆盖率或业务重要性。

探针确认：

- 六个成功来源只剩 `tr_3`—`tr_6`。
- 分组值为 `[1, 2, 3, 999]` 时，第四组 999 根本不进入候选事实。
- 证据先取全局最近四条，再按本轮收据过滤。即使 `tr_1` 被正确选为当前来源，与其绑定的 `ev_1` 也可被提前切片丢掉，最终 evidence 为空。

来源：[事实抽取](D:/Project/Daily/data-agent/src/data_agent/agent/publication_synthesis.py:72)、[发布包选择](D:/Project/Daily/data-agent/src/data_agent/agent/publication_synthesis.py:155)。`publication_scope` 仍携带 eligible 来源的范围契约，不应描述为所有旧来源信息全部丢失。

此外，`micro_compact` 对 120—15000 字符的旧工具消息直接压缩，不由此函数先保存完整原文。714 字符合成消息被压为 203 字符，尾部事实丢失，未产生压缩备份。

来源：[微压缩](D:/Project/Daily/data-agent/src/data_agent/agent/compact.py:138)。其他收据、对话存档可能仍有原内容，所以这里证明的是模型活动上下文损失，不是全系统永久数据丢失。

建议：先按本轮、任务、数据集、版本过滤，再按问题覆盖和主张重要性分配摘要预算；携带省略数量及可检索引用，关键比较项保留配对字段。压缩前可靠保存原文。不能仅把固定上限从 4 提高到更大数。

### D04：工作台主动限制展示，和正文发布是两回事（中优先级，涉及产品选择）

工作台只返回有当前验证指纹且在通过列表中的 high / medium 结论，再截取前 6 条；low / speculative、假设、待验证线索没有单独投影。

探针中 8 条 medium 通过记录及 1 条 low 记录，只展示前 6 条 medium。该行为也由现有 Slice 6 测试明确固定，不能径自恢复成旧的复杂面板。

来源：[工作台](D:/Project/Daily/data-agent/src/data_agent/agent/workbench_view.py:8)、[既有最简视图测试](D:/Project/Daily/data-agent/tests/test_slice6_workbench_minimal.py:23)。

建议：已验证区域保留证据规则；先为六条以上通过结论提供展开，再由用户确认是否需要独立的“待验证发现”入口。低置信内容必须明确标记其性质，不能混进已验证列表。

### D05：意图快路径把复合句和否定表达认成明确意图（高优先级）

| 输入 | 实际类型 | 问题 |
|---|---|---|
| 你好，请分析收入趋势 | simple_response | 问候覆盖了明确分析任务 |
| 不要报告，只导出这张表 | comprehensive_report | 忽略否定语义 |
| 请分析收入下降原因并给出分析建议 | analysis_consultation | “分析建议”优先于实际执行诉求 |
| 分析销售趋势 | directed_analysis | 常规正例正常 |
| 计算总收入 | data_operation | 常规正例正常 |
| 什么是回归分析 | knowledge_qa | 常规正例正常 |

这些错误结果标记为 clear，直接跳过 LLM 语义层。数据细化主要处理分析意图与数据可用性，并不会普遍纠正前三类误判。意图会影响预算、提示词和工具组；其他关键词可能继续激活一些工具，所以不能断言每次都会完全停止执行。

来源：[快路径返回](D:/Project/Daily/data-agent/src/data_agent/agent/intent.py:182)、[规则顺序](D:/Project/Daily/data-agent/src/data_agent/agent/intent.py:239)、[消费意图](D:/Project/Daily/data-agent/src/data_agent/agent/loop.py:952)。

建议：快路径只接收纯问候、纯操作等确定输入；复合任务和否定表达先做冲突判断，再交语义层或明确规则处理。使用完整用户目标作为主任务，不让客套话覆盖它。

### D06：数据限制的适用范围过宽（高优先级）

- “只拟合已提供的聚合留存曲线，不计算个人留存”仍因出现“留存”且数据不支持 user_level_retention 被改成 request_data。
- “只分析 sales 收入趋势”在另一个无关数据集 blocked 时也被改成 ask_question。

来源：[意图细化](D:/Project/Daily/data-agent/src/data_agent/agent/intent_refinement.py:26)、[分析入口留存判断](D:/Project/Daily/data-agent/src/data_agent/agent/analysis_entry.py:67)。入口已有 active_dataset 过滤，但细化层仍遍历全部 contracts，两个阶段的边界不一致。正常持久化状态可能使用 compact refs，而探针使用完整 contracts；是否在特定真实会话触发需要按实际存储形式补集成用例。

建议：所有入口共用当前任务的数据作用域，按请求所需粒度判断能力；聚合留存描述和用户级留存计算应分别判定。不能通过删除粒度约束解决。

### D07：用户身份适配没有形成独立能力（中优先级，需确认设计）

当前只有 beginner / intermediate / advanced 熟练度，按统计术语和口语关键词推断。业务人员、分析师、管理者三个探针都得到 intermediate；没有找到独立 audience 身份契约及相应验证路径。基础模型可能依自然语言自行适配，但这不构成受保证的功能。

`_build_system_prompt` 首次把 auto 替换为检测结果并写回上下文；后续不再进入 auto 分支，存在会话内适配固定在初始判断的问题。初学者提示词还要求“因为 X，所以 Z”的因果表达，与其他位置的证据边界容易冲突。

来源：[检测](D:/Project/Daily/data-agent/src/data_agent/agent/prompts.py:323)、[初学者提示](D:/Project/Daily/data-agent/src/data_agent/agent/prompts.py:359)、[缓存检测值](D:/Project/Daily/data-agent/src/data_agent/agent/loop.py:764)。

建议：将 audience 与 proficiency 分开，显式用户要求优先且允许会话中改变；无需多个 Agent 或额外 Provider 调用。

| 身份 | 优先展开 | 共用底线 |
|---|---|---|
| 业务人员 | 变化、可能原因、可执行动作和跟踪指标 | 相同事实、范围、限制和证据等级 |
| 分析师 | 口径、方法、参数、误差、竞争假设与复现依据 | 相同事实、范围、限制和证据等级 |
| 管理者 | 业务影响、优先级、选项、资源权衡与停止条件 | 相同事实、范围、限制和证据等级 |

本次未做历史能力追溯，不能断言它“曾经完整实现后被删除”。

### D08：竞争假设的支持判定不可靠（最高修复优先级）

模板、字段要求和持久化仍在，但支持关系由英文 token 重合或整句包含决定：

- “It is false that + 原假设”被标 supported。
- 错误 dataset / 旧 plan 的同一句文字也被标 supported。
- 中文等价证据无法匹配英文模板，保持 inconclusive。
- 一旦存在 supporting_evidence_ids，之后传入空证据集仍保留 supported。
- conflicting_evidence_ids 被初始化为空，更新函数没有实质反证处理，也没有支持撤销机制。

来源：[状态更新](D:/Project/Daily/data-agent/src/data_agent/agent/hypotheses.py:65)、[文本匹配](D:/Project/Daily/data-agent/src/data_agent/agent/hypotheses.py:298)。runtime 将全部 state.evidence_records 送入更新，复用依据是 dataset + route，未形成按当前 plan/version 严格绑定的假设身份。

建议：文本相似只能提示“可能相关证据”，不能证明支持。引入明确的 hypothesis_id、证据引用、关系类型与数据/版本/计划绑定；只有满足对应证据要求才转换状态，支持反证与失效。优先防止错误 supported，同时保留未验证但有价值的解释作为候选。

### D09：竞争假设还缺少完整执行与最终输出闭环（中高优先级）

自动假设更新挂在 `_maybe_inject_synthesis_policy` 中：已有 evidence 才运行，一轮只执行一次。发布前刷新的是验证报告，没有对假设做对应的最终刷新。提示上下文主要输出假设集合 id / dataset / route / count，发布包没有携带完整假设对比；工作台也没有假设视图。

EvidenceRecord 的 `competing_hypotheses` 是可选透传，当前只检查外层为 list；没有逐项验证结构和排除依据。主提示词要求“至少一个被排除的替代解释”，但没有足够证据时并不能保证排除，容易诱导模型编造排除过程。

来源：[一次注入](D:/Project/Daily/data-agent/src/data_agent/agent/loop.py:1578)、[发布刷新](D:/Project/Daily/data-agent/src/data_agent/agent/loop.py:1630)、[假设上下文](D:/Project/Daily/data-agent/src/data_agent/agent/analysis_state.py:767)、[透传](D:/Project/Daily/data-agent/src/data_agent/tools/analysis_flow.py:518)、[提示词](D:/Project/Daily/data-agent/src/data_agent/agent/prompts.py:182)。

建议：按新证据和版本变化刷新假设，在归因/驱动/异常问题的合成输入中携带“候选解释、支持、反证、当前状态、区分性检验”。允许“尚无法排除”，不机械要求所有问题必须排除至少一个解释。

### D10：置信度规则混淆计算可信度、推断力度和业务外推（中高优先级）

探针确认：`statistical_inference=False`、12 条已记录订单的描述性结果仍触发“小于30不能高置信”；“365天”被按“有天字且无月字”判为短观察期。主提示词还无条件要求单一来源无交叉验证不得高置信。

来源：[校准](D:/Project/Daily/data-agent/src/data_agent/tools/analysis_flow.py:75)、[时间限制](D:/Project/Daily/data-agent/src/data_agent/tools/analysis_flow.py:60)、[提示词](D:/Project/Daily/data-agent/src/data_agent/agent/prompts.py:193)。

判断：记录内的精确加总与总体趋势、预测、因果属于不同主张。不能把缺少总体推断条件等同于已完成计算本身不可信，也不能因计算准确就宣称结论可以外推。

建议：按主张类型和方法前提校准；时间长度从结构化窗口计算。保留来源、口径、缺失、范围说明，删除与具体主张无关的自动警告。

## 建议执行顺序与验收条件

1. **先修局部正确性。** 修复 D02 的合规语句误拒绝、D05 的意图冲突、D03 的先切片后过滤；为 D08 建立反证、错数据集和失效证据的失败用例并修复支持判定。验收时既检查有效内容被保留，也检查无依据推断仍不能通过。
2. **统一主张和证据的作用域。** 将 D01 / D06 / D10 的建议、粒度、置信度规则与当前任务及主张绑定。相同证据下中英文请求应一致；额外加载无关坏数据不能改变目标任务的判断。
3. **完成价值保留闭环。** D03 按问题覆盖选证据，D09 给出可追踪的假设状态；每个主要问题要有结论，或明确说明缺什么证据及为何暂未回答。不要把完整性验收做成固定字数要求。
4. **实现身份适配与渐进展示。** 按 D07 的身份表调整重点，共用证据；D04 保留最简已验证区域，选择性增加展开和待验证发现。需要用户确认产品呈现方式。
5. **最后验证实际回答质量。** 先用 Provider 禁用的集成回放和本地真实浏览器检查，再冻结新源码、准备真实 Provider 对照批次。比较主问题覆盖、有效结论保留、无依据主张、假设区分、角色适配和调用消耗。现有旧批次授权不能自动复用。

建议用户确认的原则：允许发布明确标注的描述性发现、待验证解释和有证据支持的条件性可逆建议；将“已验证结论”保留为严格等级。身份只改变关注重点和表达，不改变事实与证据门槛。

本报告中的优化为建议，尚未实施。下一步应先确认上述产品原则，再在当前工作区按最小改动逐项落地。
