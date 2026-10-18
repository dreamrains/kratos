# 系统审查后新会话交接

日期：2026-10-09。用途：新会话继续实施的入口，不是第二份计划。**已完成关键断点审查和规范更新，系统根因仍待核验；尚未修改源码。用户质疑后已纠正“直接开始S1”的交接。**

## 1. 唯一权威与身份

- 工作树：`C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`。
- 分支：`codex/trust-rebuild-20260927`；HEAD：`f7210e170d4dd1945abec15d57e364e04942eae4`。
- 唯一当前计划：`C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent\docs\superpowers\plans\2026-09-22-analysis-agent-trust-reset-plan.md`，**当前执行段§0.8**。旧§0.7是历史本地出口，不能继续按其旧下一步直接准备自然批次。
- D供体：`D:\Project\Daily\data-agent`，`main@b181646ff66ea9ea3b0e6a38ffcd3d16b6687312`，只读；其中同名计划不是当前文件。
- 原始需求：VP/IC/CP及其验收矩阵；当前产品PRD1.7、发布PRD1.4、设计文末“唯一实现责任与状态合同”、验收§19。
- 审查：[需求驱动系统审查](2026-10-09-requirements-system-review.md)。机器材料：`tmp/system-review-20261009-r1`；收据 `review-receipt.json`。

## 2. 用户决定与实施边界

用户因反复自然测试失败要求先系统审查，再讨论制定计划，**在新会话中继续源码实施**。审查中已逐项确认：

1. Q1：有限数据探索可先于正式计划；同目标、来源和业务范围只追加必要交付，保留变更记录与旧义务。正式计算仍在派发前绑定，不事后把探索结果补成完成。
2. Q2：计算DAG成功依赖只消费事实、产物和结构化关系；解释、限制、条件行动归最终覆盖与既有一次审核，不加中间审核。
3. Q3：全部现有工具能力保留，先贯通六条核心用户链，再按族核对全部声明能力；未评估家族不签整体重构完成。

直接用户答复记录在 `approved-decisions.json`。以上已获授权，不重复询问。边界之外的能力删除、范围/方法权威改变或新架构歧义仍须讨论。不得复活旧散文门/双路径/兼容wrapper；不新增Planner、调度器、事实库、Provider账本、测试框架或付费judge。

## 3. 当前确定问题与复现

| 发现 | 当前依据 | 下一处理 |
| --- | --- | --- |
| F1 schema与validator不一致 | 最新自然6份计划全部过公开schema、全部被宿主拒绝；原 `zero-call-plan-replay.json` | 同一结构定义、字段化错误和既有限恢复；动态身份约束保持 |
| F2 计划可选/发布必需，且追加被拒 | prompts:290、execution_scope的无计划许可；R-replan | 区分探索和正式派发；记录追加，不缩小原义务 |
| F3 工具业务语义到目录断开 | 真distribution均值15.5只形成table；真forecast三期因periods映射缺失报无序列 | 生产者与封闭适配的共同语义合同，按族验收 |
| F4 开放交付卡计算DAG | 第一事实已闭合，但interpretation无投影使后续blocked；R-open-dag | 计算依赖与最终覆盖各自职责明确、共享事实 |
| F5 坏scope被静默删掉 | 合成响应进入实际classifier，整个scope消失，无结构issue | 保留目标和未决原因，禁止降成无约束计算 |
| F6 验收理想输入掩盖跨接口问题 | helper补计划/执行绑定；ScriptedClient按marker预先生成正确计划 | 新跨边界门走真实正常入口；独立业务oracle，不靠测试补失踪字段 |
| F7/F8 语义审核风险与文档漂移 | 一次审核误拒/漏放仍可能；旧首页和阶段状态矛盾 | 保留一次审核，分报质量；当前状态只读唯一计划§0.8 |

`diagnose_contracts.py` 是一次性审查诊断，不是新测试框架，也不是app/browser验收。它使用现有隔离engine设置、实际record_analysis_plan、真实工具/派发绑定/回执/投影，无Provider。`diagnostics.json`记录四项反例；`intent-scope-diagnostic.json`是合成解析输入，不能冒称自然观察。

## 4. 已核与不可借用的证据

- 当前408项源/测试/运行资产与 `tmp/arc-final-r1/all-assets-r3.json` 一致；旧本地 `3530 passed /2 skipped /17 warnings`，HTTP `47组90回合检查0失败`只证明其原断言。没有因本次文档修改重跑源码测试。
- 四批封存原文件791/823/734/120，共2468，逐份摘要一致，见 `history-integrity.json`；未改原始材料。
- 77注册工具及30项现有capability metadata只读索引在 `tool-capabilities.json`；不是77项当前自然通过，非事实工具不应强制产生claim。
- 882df1c：133调用，六场景未达标；3e079b7：132调用，六场景failed；69035ed：111调用，M06余额不足停止，部分未评估。
- **f7210e1/r3：18 started，17返回结算＋1Timeout，0在途；只运行M01部分。** turn1/2咨询完成，turn3交付登记失败，turn4超时；M02—M06 `blocked_not_started`。会话 `a3cbeeb41dda`，4个唯一终态/3个接受对象；原服务PID21784/8780已关闭。
- 最新batch `tmp/p5-real-20261009-r3`；冻结SHA `dc2fc3825587bc210417887df8baa3cce2ae44f452c5b9a36a921add06ff957e`；账本SHA `10685049fcef133d87f728978673b5edae35eaee7bb21c6a92add59ecf114467`；封存manifest SHA `cb79663395ffd5ec67d546f0ead19952cee6042f1c6770383782f95122260b49`。
- ddb9daa/71e23d0原自然重放依用户决定保持unassessed，旧失败保留。HTTP picker/visual/refresh/console、新自然质量和生产/部署均无本次证明。
- 本次Provider0；所有旧批授权均已关闭。未用额度不继承，用户Q1—Q3是设计授权，不是新Provider批次授权。

## 5. 文件与保护

审查前已有：唯一计划M；r3审计未跟踪。已备份 `plan.before.md`、`r3-audit.before.md`、`git-status.before.txt`。本次只更新/新增下列文档；完整命名差异与摘要见 `review-receipt.json`：

- 原唯一计划（§0.8正式S0—S4，旧阶段保留）。
- 两份原产品PRD。
- 原单路径设计和验收契约。
- 新系统审查文档和本交接。

r3审计原字节保留。本次未暂存或提交，未改任何源码/测试或正式配置。保留所有dirty/untracked和tmp原材料；禁止reset、bulk-stage、批量清理。C树不在默认可写root时经获准的elevated命令通道操作；不要退回D树修改。

## 6. 新会话可直接粘贴

```text
继续可信发布重建，按已确认系统审查后的因果核验；当前先不改源码。

唯一工作树 C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent，分支 codex/trust-rebuild-20260927，预期HEAD f7210e170d4dd1945abec15d57e364e04942eae4；D:\Project\Daily\data-agent 的 main/b181646 是只读供体。
先读C树AGENTS.md、唯一计划 docs/superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md 的§0.8、docs/audit/2026-10-09-requirements-system-review.md 和 docs/audit/2026-10-09-system-review-handoff.md；再读产品PRD1.7、发布PRD1.4、设计文末当前合同及验收§19。核对worktree/HEAD/dirty/环境，保护全部dirty/untracked。

Q1有限探索和有记录的只追加交付、Q2计算DAG与最终开放解释完成分离、Q3全部工具能力按族保留和贯通，已由我逐项确认，不要重复询问。按§0.8先完成S0尚欠的历史故障归因、共同机制反证和最小跨边界验证，参见系统审查§5.1。不要把Q1—Q3批准当作根因已闭合；完成核验后再进入S1最小业务链、S2全部能力和S3本地联合验收。新产品取舍不明时先讨论。

先使用 tmp/system-review-20261009-r1 的R反例和原自然材料建立真正跨接口回归；核对公开schema/实际validator、正常派发绑定、工具业务产物、依赖与最终覆盖。不得测试执行后补绑定来代替正常入口，不按LLM散文补词表，不保留兼容双路径，不新增Planner/调度器/事实库/账本/语义重审链。原VP/IC/CP、咨询、多输入、证据/假设、确认/版本、连续会话/压缩/分支/导出能力保留。

最新f7210e1/r3只有M01部分证据：18调用后Timeout停止，M02—M06未启动，原批不续跑。旧本地3530通过/47组90回合不证明新审查断点闭合。所有旧Provider授权关闭；S4仅在S1—S3稳定后准备新精确冻结，再按AGENTS获批执行。正式默认、外部Git、部署分别授权。不要修改历史结果或把unassessed记成通过。
```
