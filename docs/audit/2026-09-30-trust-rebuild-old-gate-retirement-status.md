# M01—M06 旧整段散文门退役状态

日期：2026-09-30。实施树 `C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`，`codex/trust-rebuild-20260927@4bb7f85` 加当前在途改动；供体 `D:\Project\Daily\data-agent@b181646` 只读。本记录从属[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。

## 当前实际调用边界

`AgentLoop._render_terminal_publication` 在当前 packet 中依次构造 M02、聚合、比较和描述宿主 claim。只要形成任一 `host_parts`，宿主即在原 `answer_bindings.v1` 中组合块、原位渲染、更新需求覆盖并执行有界开放审核，然后直接返回；此路径不调用 `_render_finalized_publication`，因而不再让 `validate_final_narrative` / `validate_final_narrative_issues` 的整段关键词、数字和句式检查决定这些宿主事实能否交付。

这已覆盖当前 M01—M06 的实际事实族：M01 比较、描述和条件行动输入；M02 观测与描述性拟合；M03 六源比较；M04 当前比较及版本化证据关系；M05 边界聚合；M06 聚合、确认口径和逐项缺口。宿主 block 的回执、完整版本、字段、算术、确认和 render trace 是事实权威；试验审核只处理可定位开放片段或已核输入上的行动候选，失败或不可用不删除宿主事实。

## 仍保留的旧门

`_render_finalized_publication` 仍服务于**没有形成任何宿主 claim**、但模型提交了旧式 typed binding 或自由候选的遗留终局。其 `validate_final_narrative` 调用尚未全局删除，因为这类回执族还没有统一宿主 builder；直接删除会使默认审核关闭时的无宿主散文失去现有 fail-closed 保护。它不再是 M01—M06 当前宿主路径的决定权威，但仍是 R5 全局出口的剩余债务。退役条件是先把对应遗留回执族接入现有 `answer_bindings.v1` 的宿主渲染或给出明确的封闭保留依据，不能改成新词表或第二 planner。

## 证据

- `tests/test_r3_comparison_host_claims.py::test_terminal_host_comparison_does_not_depend_on_prose_gate` 直接把旧散文门替换为会拒绝候选的 stub，比较宿主事实仍发布；同文件覆盖描述+比较组合、当前行动输入、六源与图表。
- `tests/test_r3_aggregate_host_claims.py` 覆盖聚合+比较、日期跨度、缺口、真实确认公式与宿主渲染；`tests/test_basic_summary_binding.py` 覆盖当前 frame、错和/旧版本/篡改绑定拒绝及组合时只接当前描述回执；`tests/test_publication_synthesis.py` 覆盖 M02 原值、单位确认、D30 未知与同版本拟合。
- 新目录完整 E2 `tmp/trust-rebuild-e2-20260930-r4` 为 2976 passed / 1 skipped / 16 warnings；Provider 禁用联合 r2 `tmp/trust-rebuild-pd-matrix-20260930-r2` 的 M01—M06 全部产生上述宿主块并满足独立非视觉 oracle。

因此，本轮可声明的是“M01—M06 当前事实族已从旧整段散文门退出”；不能声明旧门代码已全局删除或 R5 全局出口完成。
