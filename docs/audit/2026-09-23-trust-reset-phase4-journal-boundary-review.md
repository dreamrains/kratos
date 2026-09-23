# 可信发布重置 Phase 4：事后台账边界审查

日期：2026-09-23。审查基线：`main@d0a261429c82ddadadc5a9377e719526fe1f4fbc`。本文件是 Phase 4 的源码/历史/离线证据复核；未增加 journal、planner、模型调用或 Provider 验证。

## 1. 跨历史 RED 与原始需求

| 历史证据 | 已观察的失败/成功 | Phase 4 不能误读为 |
| --- | --- | --- |
| R11 M04 | 正文可区分 v1/v2，但 `evidence_records=0`、`hypothesis_sets=0`；缺少竞争假设审计闭环 | 只要正文通顺就可取消证据关系 |
| R14 M04 | 有效 `record_analysis_plan` 后投影任务全为 pending，scope 要求唯一 in-progress 而阻断后续工具；随后已有原子启动/推进修复 | 再做一套任务规划器 |
| R16 M04 | 计划/假设/竞争证据未结构化收敛；本地修复恢复显式竞争假设审计要求 | task completed 可代替证据 |
| R21 M02 `8885cd032ffe` | 四个工具触发 `workspace_scope_authoritative_downgrade`，D1—D7/D7=10% 可在正文保留，但工具链 0/4；`4a6493f`/`89623e6` 已保护活动结构化 plan 权威 | 允许静默覆盖 plan 或绕开 scope 安全边界 |
| R21 M04 `ef2694420c2e` | v1/v2 都已加载，两轮因未终态 task 被 `analysis_audit_incomplete` 卡死；后续 `8d25851` 已让任务状态不再单独阻断发布，并在成功发布时由宿主以 `closed_by_publication`/原因关闭 | 还需要新账本，或可把未完成任务伪装成 completed |
| R4 M04 | 已有结构化成功轨迹，说明 plan、证据和版本闭环并非概念上不可行 | 一次成功即等于所有自然模型路径通过 |

三份原始需求合起来要求：保留有证据的独立业务价值（P0—P8）、主目标及明确子问题不被任务模板窄化（IC）、每个明确子问题被回答或给出具体缺口且未支持主张不抹掉独立可信部分（CP 的 CR03/CR07）。P5 对显式竞争假设任务另外要求假设身份、证据关系、反证/未决与版本失效；不能用 journal 消去这些内容义务。

## 2. 当前已有的宿主事实源

- `AgentLoop._record_tool_receipt()` 已持久化工具调用/回执、数据身份、结果 hash、事实组与 `turn_receipt_ids`；`build_publication_packet()` 只选本轮有效回执，生成 sources、requirements、coverage 与缺口。`answer_bindings.v1` 已把相应 requirement 的回答状态写回 packet。这里已有事后执行/证据投影，不应再复制一份可漂移的台账。
- `TaskManager` 已有活动 plan 权威、互斥、scope 保护，以及 `close_open_tasks_for_publication()` 的明确未完成关闭原因。`tests/test_scope_downgrade_recovery.py` 与 `tests/test_publication_task_closure.py` 覆盖 R21 两种死亡轨迹的局部修复。
- `AgentLoop._competing_hypothesis_quality_gaps()` 已不再把未完成 task 列为发布缺口，但对于**显式竞争假设任务**仍要求 analysis plan、hypothesis set 和含竞争关系的 evidence record。`tests/test_analysis_quality_guard_scope.py` 保留正反例。这个结构化审计门与原始 P5 目标存在对应关系，不应被误称为“仅 task JSON 门”。

## 3. 第一阶段实施前的三联门

- **RED 轨迹**：R21 M02 scope 权威降级与 R21 M04 未完成任务卡死均已对应本地修复；在当前 HEAD 上，不能把历史 RED 直接当作仍然失败。若要实施新改动，先构造当前真实剩余缺口的 RED，例如“一个 requirement/claim 有可核验回执、另一个缺证据时，前者被 plan/task 状态全局拒绝”。若回放无法重现，不应为了履行路线图而制造新 journal。
- **结构化替代物**：优先使用现有 receipt、packet 的 sources/requirements/answer coverage、analysis-state evidence 与 TaskManager 权威/closure 状态。journal 仅可作为同一快照上的只读事后投影；不拥有执行决策或第二份持久权威。claim 的 completed/gap/degraded 只能由其绑定证据与版本决定。
- **将退役的旧门**：已退役的是“投影任务必须全部 completed 才能发布”；接下来只有发现当前仍存在“模型 plan/task JSON 作为所有独立 claim 的发布许可证”时才精确退役该门。显式竞争假设任务的结构化关系要求不能在没有目标裁决的情况下连带删除。

## 4. 需要用户裁决的冲突

总计划写“模型不再承担计划 JSON 正确性”，但当前显式竞争假设审计门要求 `analysis_plan`，而原始 P5 与 R11/R16 修复要求结构化竞争证据闭环。用户已确认采用窄解释：plan 不是**所有独立 claim**的发布许可证，但显式竞争假设任务仍需结构化 plan 和假设/证据关系；未完成 task 状态不阻断独立可信 claim。因此不删除既有 plan/假设门，也不把 task 状态重新升为通用发布许可证。

## 5. 验证与禁止事项

当前 HEAD 的定向离线回归运行了 `test_scope_downgrade_recovery.py`、`test_publication_task_closure.py`、`test_analysis_quality_guard_scope.py`、`test_task_plan_versioning.py`、`test_stage3c0b_execution_scope.py`、`test_publication_synthesis.py`、`test_answer_publication_contract.py`，结果 214 passed。它们证明 R21 两种死亡轨迹的现有本地修复及发布覆盖/结构门；并不证明真实自然模型、浏览器完整链路或跨轮次继续执行的所有语义。

Phase 4 当前不新建数据结构或产品代码：上述事后簿记已由现有 receipt、packet 和 task ledger 承担；不存在已复现且未修复的“任务状态全局阻断独立 claim” RED。若后续发现当前 HEAD 的精确反例，应先记录 receipt/claim/version/状态，再局部修复旧门。特别监控成功发布后 `closed_by_publication` 对用户明确的跨轮次继续任务是否产生不当 scope 释放；目前不把可能性写成已证实缺陷。

没有新浏览器框架、模型审核调用、任务创建器或另一套持久账本；任何真实 Provider 仍需新精确冻结及显式授权。本审查不构成 E3/E4 验收。
