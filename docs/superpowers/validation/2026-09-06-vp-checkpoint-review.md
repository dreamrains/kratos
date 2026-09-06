# 后续实施前的 Git 检查点审查

日期：2026-09-06｜结论：**建议先建立本地研发检查点，再继续修复**。

用户本次要求检查是否需要提交。本次只核查并整理提交方案，没有暂存、提交、推送、合并、创建标签或修改产品代码。

## 1. 为什么现在提交

当前分支 `vp-analysis-value`，HEAD 为 `36bca25a44a25c99ef8bb7bf56312bde05736ba2`。P1—P6 实现和 P7 诊断仍全部在工作区，尚无专项提交；暂存区为空。检查时专项范围为 48 个文件：16 个产品文件、21 个测试文件、11 个规划/阶段/审计文件。

下一步 P3/P5/P2 修复会再次修改已有文件。先保存这一状态，可以把“已有实现”“独立反例发现问题”“后续修复改变了什么”对应到明确 Git 父子版本。保留 RED 测试有助于证明修复有效，不能为提交而删除失败、加 xfail 或提前改写阶段为 passed。

这次检查点应明确记录 P7 failed，不能命名为功能完成、验收通过或发布候选。它也不触发进入 P8 的条件。只建议建立一个反映当前真实状态的检查点，不倒拆成未经逐阶段重验的 P1—P6 历史提交。

## 2. 核查结果

| 项目 | 结果 | 对提交的影响 |
|---|---|---|
| 当前分支与 HEAD | vp-analysis-value / 36bca25 | 在现有专项分支记录，不改变 main |
| 已跟踪改动 | 34 个文件，2862 行增加、202 行删除 | 包括 16 个产品文件与 18 个测试文件 |
| 专项新增 | 3 个测试、11 个文档/JSON | 与实现一起保留规划、阶段状态和独立失败证据 |
| 暂存区 | 空 | 未混入已暂存的其他改动 |
| P7 收据对应关系 | 347 个已有受控文件哈希均仍匹配；新增 P7 测试哈希匹配 | 可作为修复前状态记录；不是重新运行测试的证明 |
| 差异格式检查 | git diff --check 无错误 | 仅检查已有跟踪改动，不代表功能通过 |
| 换行配置 | core.autocrlf=true；没有项目 .gitattributes | 不顺带修改换行策略；收据字节哈希与 Git blob 身份需分别记录 |
| 本地提交 hooks | hooksPath 未配置，hooks 目录只有 sample 文件 | 未发现本地提交钩子；未访问远端，不能据此推断远端分支保护或 CI 规则 |
| 历史审计材料 | 27 个 A06R3/R4/R5 未跟踪文件 | 排除并原样保留 |
| stash | 两份仍在，包括 A06 切换基线前的改动 | 不应用、不删除、不并入检查点 |

证据来源为本次本地 Git 和文件核查。未访问远端、未重新运行产品测试。已有 P7 结果见 [执行报告](2026-09-06-vp-p7-execution-report.md)：全量 2478/7/3；新增安全反例 5/4/0；原失败模块复核 81/7/0。最后一组与全量重叠，不累计为额外覆盖。

## 3. 推荐提交方案

建议提交标题：

```text
chore: checkpoint value-preservation work with P7 blocked
```

建议提交正文：

```text
保存分析价值保留专项的现有实现、规划和 P7 失败基线。

完整离线回归：2478 passed / 7 failed / 3 skipped。
新增独立安全反例：5 passed / 4 failed。
确认多来源发布范围误放行及假设目标指标/谓词误判。
P2/P3/P5 需修复后重验，P7 failed，B01-B06 blocked_not_started。

本提交仅为研发检查点；不是发布候选。
未启动真实 Provider；不包含历史 A06 材料、运行会话或 tmp/artifacts。
```

本次新建本审查文档后，建议提交范围为 **49 个命名文件**。下方清单是审查范围，不是已经暂存的结果。提交执行时须再次核对 HEAD、工作区及暂存区差异；如果出现额外改动，应重新裁定归属，不能直接扩大范围。

## 4. 证据保存与后续进度管理

- 拟提交的 P7 JSON 收据包含源码字节哈希、失败断言、独立反例输入/实际输出及 JUnit 哈希；新增测试提供可重跑入口。
- 三次原始 JUnit、隔离会话及运行输出仍位于被 Git 忽略的 tmp 目录，只在当前工作区可用。检查点不会自动包含它们，应保留原目录；在另一台机器上查看历史日志，需要另行提供这些原始文件。不能把只有摘要/哈希的 Git 检查点描述为完整运行档案。
- Git 的换行规范化可能影响重新检出后的字节哈希。保留旧收据作为历史事实，不为匹配新提交改写旧哈希。提交后的实际 commit id/Git blob 身份应在下一次修复记录中引用；修复后的新运行重新生成当前源码快照。
- 后续按独立问题提交：P3 来源绑定、P5 假设判定、P2 礼貌语及其余回归契约处理；每次关联问题编号、命名文件和相关 RED/GREEN 收据。
- 完整离线与 B01—B06 全部完成后，再单独记录 P7 本地候选结果。提交本身不改变阶段完成状态，不包含推送、合并、部署或真实 Provider 授权。

当前适合保存研发状态；能否进入后续阶段仍由验收结果决定。本检查未执行 Git 写操作。

## 5. 拟提交的完整文件清单

```text
docs/audit/2026-09-06-analysis-value-and-capability-diagnosis.md
docs/audit/2026-09-06-analysis-value-planning-baseline.json
docs/audit/2026-09-06-vp-p0-baseline-36bca25-files.json
docs/audit/2026-09-06-vp-p0-baseline-36bca25.json
docs/audit/2026-09-06-vp-p7-execution-receipt.json
docs/superpowers/plans/2026-09-06-analysis-value-preservation-plan.md
docs/superpowers/specs/2026-09-06-analysis-value-preservation-design.md
docs/superpowers/validation/2026-09-06-analysis-value-preservation-acceptance.md
docs/superpowers/validation/2026-09-06-codex-l3-l4-handoff.md
docs/superpowers/validation/2026-09-06-value-preservation-stage-records.md
docs/superpowers/validation/2026-09-06-vp-checkpoint-review.md
docs/superpowers/validation/2026-09-06-vp-p7-execution-report.md
src/data_agent/agent/analysis_entry.py
src/data_agent/agent/compact.py
src/data_agent/agent/context.py
src/data_agent/agent/hypotheses.py
src/data_agent/agent/intent.py
src/data_agent/agent/intent_refinement.py
src/data_agent/agent/loop.py
src/data_agent/agent/prompts.py
src/data_agent/agent/publication_synthesis.py
src/data_agent/agent/request_language.py
src/data_agent/agent/synthesis_policy.py
src/data_agent/agent/trust_workflow_runtime.py
src/data_agent/agent/workbench_view.py
src/data_agent/tools/analysis_flow.py
src/data_agent/web/static/js/app.js
src/data_agent/web/templates/index.html
tests/test_analysis_entry.py
tests/test_analysis_flow_tools.py
tests/test_analysis_quality.py
tests/test_audience_adaptation.py
tests/test_compact_preservation.py
tests/test_execution_control.py
tests/test_hypotheses.py
tests/test_intent_classification.py
tests/test_intent_refinement.py
tests/test_multifile_workbench_view.py
tests/test_pipeline_comprehensive.py
tests/test_publication_synthesis.py
tests/test_slice6_workbench_minimal.py
tests/test_synthesis_policy.py
tests/test_trust_inspector_api.py
tests/test_trust_inspector_ui.py
tests/test_trust_view.py
tests/test_trust_workflow_runtime.py
tests/test_value_preservation_p7_boundaries.py
tests/test_verification_layer.py
tests/test_web_workbench_action_board.py
```
