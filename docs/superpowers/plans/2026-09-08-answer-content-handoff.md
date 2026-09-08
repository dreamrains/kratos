# 回复内容优化：实施交接

日期：2026-09-08｜状态：独立分支核心实现完成，等待后续合并；浏览器与真实 Provider 未验收。

实施结果以 [实施记录](../../audit/2026-09-08-answer-content-implementation-record.md) 为准。下文保留最初实施要求作为设计追溯；其中“未开始”“未来实施”等时态已由本次分支工作取代。

先读 [总计划](2026-09-08-answer-content-optimization-plan.md)，再读 [设计](../specs/2026-09-08-answer-content-design.md)、[表达规范](../specs/2026-09-08-answer-presentation-contract.md)、[验收](../validation/2026-09-08-answer-content-acceptance.md)、[诊断](../../audit/2026-09-07-answer-content-and-presentation-audit.md)、[基线](../../audit/2026-09-08-answer-content-planning-baseline.json)。

## 1. 当前交付与范围

用户先要求准备文档，随后要求另建分支实施。分支 `codex/answer-content-optimization` 已从 `85f62794e24cfa95a864293d159e0208c8615a4b` 创建并完成核心代码、测试与文档；没有合并回原分支、Provider调用或部署。

文档交付包括：

1. `docs/superpowers/plans/2026-09-08-answer-content-optimization-plan.md`
2. `docs/superpowers/specs/2026-09-08-answer-content-design.md`
3. `docs/superpowers/specs/2026-09-08-answer-presentation-contract.md`
4. `docs/superpowers/validation/2026-09-08-answer-content-acceptance.md`
5. 本交接文件。
6. `docs/audit/2026-09-08-answer-content-planning-baseline.json`
7. `docs/audit/2026-09-07-answer-content-and-presentation-audit.md`
8. `docs/audit/2026-09-08-answer-content-implementation-record.md`

另在 `docs/superpowers/plans/2026-09-06-analysis-value-preservation-plan.md` 增加本包导航与关系说明。

实施分支修改 `loop.py` 的发布生命周期，但没有带入原工作树尚未提交的并行改动。完整离线回归覆盖了分支基线已有的 P08 行为；未来合并仍须对届时主分支的新改动重新验证。

## 2. 核心判断与实现重点

- 当前终局可能复用第8轮的早期发布包；凌晨详细省钱卡最终7条证据，但包里0条。正文可能仍用了后期历史，不能把包内少项直接等同于答案全部丢失。
- run_python 的事实提取主要抓到技术字段，stdout只保留180字符；需要业务事实组与受控恢复，而不是把10改成100。
- 最终回答少了已计算的加权敏感性；同时出现22400×5.1%被写成1.14万人的错误。内容保留和数值可靠性都要修。
- 新增覆盖与数字绑定不能依靠模型自报verified；不能承诺理解所有自由文本。unknown要明确，不以新守卫把独立可信分析全部拒掉。
- 按任务组织章节、适量图标与图文对应；不恢复无依据行业评级、因果结论或任意Mermaid数据图。

## 3. 开发开始步骤

收到明确实施任务后：

1. 只读核对目标路径、分支、HEAD、dirty、AGENTS以及相关文件当前字节；将基线差异列为已有能力/需适配/缺前置。
2. 保护P08已有修改；不要先执行reset/clean，也不要把未提交改动归到本包。用户指定独立工作区时依该上下文使用；不默认搬走共享工作区。
3. 阅读计划CP0—CP6并建立阶段记录。先复现AC01、AC08、AC16、AC22等关键负例，再推进CP1。文档静态校验不替代CP0。
4. 复用实际现有接口。若逻辑字段已有等价表达，记录映射并复用；不可依据旧memory创建第二套analysis_requirement/final_answer_audit存储。
5. 定向测试通过后推进后续阶段；完整离线、脚本模型浏览器与自然模型验证分别记录，不因既有159项测试绿灯省略本包反例。

常规实现细节按本设计自主解决，不需要逐阶段提问；仅实际需求冲突、缺少重要前置或授权范围不明确时说明具体问题。

## 4. 与已有整改的重叠

| 面 | 必须保留的行为 | 合并检查 |
|---|---|---|
| loop终局 | P08-02允许有证据描述/合规边界正常结束 | 新覆盖检查不能重新把合法D30拒绝卡成未完成 |
| loop/compact历史 | P08-04工具调用响应配对、原始历史审计 | 新摘要/绑定不能删有效tool消息或暴露内部块 |
| 确认/analysis_entry | 只问改变结果的具体业务语义缺口 | 不为排版、摘要或一般模型选择新增审批 |
| publication/hypotheses | 当前版本、逐主张范围与未决竞争解释 | 不因扩大事实选择绕过验证；同名字段不得跨数据借用 |
| artifacts/SSE/report | 持久化、一次终态、刷新和导出 | preview不得刷出多个正式来源说明；断流恢复不重生成答案 |
| prompts/synthesis_policy | 已有中文建议/否定与受众适配 | 使用统一策略，不一处允许另一处suppressed |

不要改动当前dirty的P08矩阵方案/执行器来掩盖失败。新的内容质量样本先准备为独立附件，下一批冻结前才纳入；已消耗批次不补记成通过。

## 5. 迁移、提交与运行边界

本分支采用逐文件暂存并在提交前检查 diff；Git 忽略的真实数据夹具与 `tmp/r2` 不进入提交。后续合并必须核对实际提交 hash 和目标分支最新 `loop.py`，按函数块保留并行确认/P08改动，不用整文件覆盖解决冲突。

用户原始sessions/workspace只读。测试生成物进入独立tmp/test-runs或专项隔离目录。真实Provider需新的零调用预检、输入/hash/模型/预算/启动进程身份与明确授权，不继承P08或A06任何历史额度。Git外部操作与部署按未来任务的明确授权处理。

回退以阶段命名文件补丁为单位，先停止新writer再调整读取/投影，保留历史新格式可读；不删用户会话或审计记录。不能通过回退丢掉已经修好的来源/确认/消息协议边界。

## 6. 可直接粘贴的实施任务

> 请在本任务明确的目标工作区，按 `docs/superpowers/plans/2026-09-08-answer-content-optimization-plan.md` 实施“回复内容完整性与表达优化”。先核对HEAD、dirty和相关源码，完成CP0接口映射与独立正反例，再按CP1—CP6推进。当前文档基线8969abd仅是规划快照，包含已有P08并行改动，不是必须回退到的版本。
>
> 目标是修复发布证据包过期、业务事实被截断或技术元数据挤占、需求覆盖与派生数字检查不足，并按任务需要改善Markdown/图表表达。参考配套设计、表达规范、40项验收和09-07诊断。普通均值与加权均值对照应能被保留；22400×5.1%不能再写成1.14万人。保留独立可信内容，不通过无限加长回答、加大常量、取消可信度约束或额外LLM审核调用交差。
>
> 保持单运行时，复用计划、证据、收据和artifact；新增字段贯通schema、宿主校验、持久化和读取。同步、流式、刷新和导出必须绑定同一最终快照；沿用既有一次修订预算，不各模块单独重试。P08确认与工具消息协议修复不得回退。原始会话只读，测试隔离且禁止真实Provider；只在额外明确授权后准备并执行新的真实批次。常规实现决策按文档推进，实质需求冲突先具体说明。完成后报告阶段证据、未评估能力和回退范围，不把离线/脚本浏览器当自然模型或生产验收。

此引文保留为后续继续扩展未完成 AC 或冲突合并时的任务背景；当前核心实现已经执行。
