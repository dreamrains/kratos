# 需求对齐与必要澄清：跨分支实施交接

日期：2026-09-07｜状态：**仅文档交付；代码实施未开始**。

先读 [总计划](2026-09-07-intent-clarification-plan.md)，再读 [设计](../specs/2026-09-07-intent-clarification-design.md)、[验收](../validation/2026-09-07-intent-clarification-acceptance.md)、[诊断](../../audit/2026-09-07-intent-clarification-diagnosis.md)、[基线](../../audit/2026-09-07-intent-clarification-planning-baseline.json)。

## 1. 当前事实与用户意图

用户已认同综合评估，要求准备优化文档并提交，将在另一分支实施以隔离当前优化。本次不改产品代码、不切换当前工作区、不创建实施分支、不推送或合并。

文档编写前分支为 `vp-analysis-value`，HEAD 为 `86f55af05b053d42b1e9fd5f10c95e1545109cc4`，暂存区为空、无已跟踪改动；27 个既有未跟踪矩阵文档在基线中逐项列出，不属于本专题。该 HEAD 只标识诊断环境，**不是实施必须继承的父提交**。

编写期间观察到其他工作新增四个已跟踪文件改动：`src/data_agent/agent/context.py`、`src/data_agent/agent/loop.py`、`src/data_agent/tools/registry.py`、`tests/test_execution_control.py`。涉及预算状态/工具分组及执行控制，既与本专题有重叠，也不属于本次实现；全部留在原工作区。基线区分提交内容与当时 dirty 字节，后续可能继续变化，不能从本次文档提交推断它们已合入。

本次文件清单：

1. `docs/superpowers/plans/2026-09-07-intent-clarification-plan.md`
2. `docs/superpowers/specs/2026-09-07-intent-clarification-design.md`
3. `docs/superpowers/validation/2026-09-07-intent-clarification-acceptance.md`
4. `docs/audit/2026-09-07-intent-clarification-diagnosis.md`
5. `docs/superpowers/plans/2026-09-07-intent-clarification-handoff.md`
6. `docs/audit/2026-09-07-intent-clarification-planning-baseline.json`

六份文件应是同一个仅文档提交。准确提交哈希在交付回复及 Git 历史中获取；本文件不嵌入自身提交哈希，避免自引用。可按下面的路径定位，再检查它确实只含上述六个新增文件：

```powershell
git log -1 --format="%H %s" -- docs/superpowers/plans/2026-09-07-intent-clarification-plan.md
git show --format=fuller --stat <文档提交哈希>
git diff-tree --no-commit-id --name-status -r <文档提交哈希>
```

尖括号是待替换值，不能原样执行。不要仅凭提交标题选择，也不要误取源分支后来加入的实现提交。

## 2. 隔离迁移方式

1. 用户选择实施基线/目标分支。若新任务没有给出且无法从目标项目上下文确认，先只读检查并询问基线，不默认采用 `vp-analysis-value`。
2. 推荐为该基线创建独立 worktree；建议新分支名 `codex/intent-clarification`，仅为建议，尊重用户实际选择。
3. 在目标 worktree 中只 `git cherry-pick <文档提交哈希>`。正常文档提交迁移不需要继承其父分支的产品代码历史。
4. 核对目标提交内容只有六份文档；不要 merge/rebase 整个源分支，不复制源工作区 dirty 文件，不拷贝 `.env`、sessions、workspace 或 matrix 授权材料。
5. 进入 IC0，按目标分支源码重新映射接口/测试/源哈希。跨分支源哈希不同本身不等于错误，但必须解释功能和安全前置差异。

以上是未来实施任务的操作说明，本次没有执行。迁移发生冲突时保留双方内容，形成具体差异再解决；不要覆盖其他专项已有工作。代码提交/推送/合并在未来任务按该任务授权执行，本轮的“提交文档”授权不自动扩展。

## 3. 与当前其他优化的重叠面

| 重叠面 | 本专题改变 | 必须保留/核查 |
|---|---|---|
| intent / request_language / intent_refinement | 主目标与子指标的路由协作 | 已有否定、复合意图、聚合与用户级留存区分，不退回粗子串 |
| analysis_entry / scope / data contracts | 必要澄清和已解决决定消费 | 文件身份、相关数据过滤、版本、缺字段/质量限制 |
| loop / context / tools/interaction | 非阻塞确认处理、工具结果、SSE 和恢复 | 执行预算、辅助调用记账、正确工具响应、一次终态和上下文边界 |
| analysis_state / workflow / task | 新决定元数据与旧通用审批退役 | 单运行时、契约版本、步骤和计划身份、历史审计 |
| publication / trust / hypotheses | 原则上仅回归验证，必要的接口适配单列 | 逐主张证据、无依据外推/因果禁止、来源绑定，不能为了减少确认放宽 |
| prompts / data_io / 项目内 full_report 提示 | 清理“方法/可恢复错误需要许可”的冲突指导 | 数据真歧义的具体提问和任务覆盖 |
| regression / browser rehearsal | 本专题合成用例和隔离连接 | 现有 Provider 禁用/隔离机制；不把其他专项 oracle 当本专题结果 |

当前源分支的历史计划/执行报告可能记录旧失败，后续提交又有修复与验证；不要只看单份旧报告就宣布当前通过/失败。本专题不复述或继承其他专项的测试数量，只重新验证自己依赖的能力。

IC0 产物要列出“目标分支已有 / 需兼容适配 / 缺前置需讨论”三类。不能为满足文档中的某个字段而引入目标分支没有的第二套 planner 或旧 memory 中的契约名称。

## 4. 实施与授权边界

- 已决定的行为：无需通用方法审批；真实语义缺口具体问；用户同意不能替代证据；保持 LLM 优先、不增加调用；按决定有效范围复用；计划覆盖整体需求。
- 不采用：仅改文案、逐模型审批、只按 playbook 永久放行、删掉所有确认、把关键词回退误认历史事实、凭同意输出因果/预测。
- 开始前：确认目标 checkout 与用户实施指令；阅读 IC0，逐项记录兼容决策。常规实现细节不需要重复批准，改变产品原则或缺少关键前置再讨论。
- 原始会话只读；实现/测试不得自动恢复或修改 `9810fe7bacf6`、`9959216b6a4a`。
- E1—E3 必须禁用真实 Provider；历史矩阵额度和授权不得复用。可选 E4 需新的精确预检与授权，不隐式重试、换模型或补跑。
- 禁止 `git add -A`、暂存无关文件、清理 artifacts/tmp/其他审计材料、自动推送或部署。

## 5. 可直接粘贴到新任务的说明

> 请在我指定的独立实施分支/工作区，按 `docs/superpowers/plans/2026-09-07-intent-clarification-plan.md` 推进“需求对齐与必要澄清”优化。先完成 IC0：确认目标分支、HEAD、dirty、相关模块和测试；本专题文档来自 `vp-analysis-value` 的一个仅文档提交，不代表需要继承该分支其他优化。若尚未迁移文档，先核对提交仅含交接清单中的六份文档，再按我选择的基线迁移；没有明确基线时先与我确认。
>
> 背景是会话 9810fe7bacf6 的省钱卡综合分析和 9959216b6a4a 的留存曲线拟合，首次都出现了不具体的 Retention & Lifecycle 方法审批。已经证实是模板自动确认；历史 LLM 是否失败未证实。目标是安全分析计算自主执行，只询问无法从当前请求、数据和有效历史决定确定的业务选择，并修复整体目标被局部复购词缩窄的计划问题。
>
> 阅读配套设计、验收矩阵、诊断和基线后按 IC0—IC5 实施。统一模板/检测器/模型直接工具/能力门控及恢复结果，不能只关一处。按决定的指标、分母、窗口、人群和相关数据范围复用答案，不能同方法永久放行；相关变化重新评估。保留真实歧义、数据/权限/版本、证据和发布约束；用户批准不能变成因果或外推依据。复用现有单运行时，不新建审批数据库或额外 LLM 审核调用。
>
> 保留当前分支其他改动，原始会话只读，测试使用隔离合成数据并禁止真实 Provider。真实调用、推送、合并、部署及代码提交按本新任务另行给出的授权处理；不要复用文档提交授权或历史矩阵额度。若目标分支缺少关键前置能力或存在实质需求分歧，先说明具体差异并讨论；普通实现选择按已确定原则推进。逐阶段记录测试和局限，不把旧诊断或脚本模型浏览器结果当真实 Provider 验收。

## 6. 当前未完成项

IC0—IC5 均未执行。实施分支/基线由用户在新任务中选择；本次未创建。六份文档提交后，仍没有本专题产品代码、回归报告、本地浏览器验收或真实 Provider 结果。
