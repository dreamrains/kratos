# Gate C R07 旅程试点失败诊断与修复（含重跑冻结）

日期：2026-08-25

## 执行事实（授权消耗 4/18）

在 `sha256:06fecbd6985740cccb36022ca700e8278067800653fecc1334962caedbc49e04` 上以真实 AgentLoop 执行 R07 旅程恰好 1 次（收据：[execution report](2026-08-25-gate-c-journey-r07-execution-report.json)）：

- 4 轮、恰好 4 次 Provider 调用、全部 2000 档；轮次与预算上限未触发。
- 模型执行的工具全部为 profiling/浏览类：`list_data`、`list_files`、`load_data`、`describe_dataset`、`preview_data`；**未执行任何实质分析工具**。
- 轮 3 工具面 64→70（组扩张生效）。
- 轮 4 `finish_reason=length` 且正文 1_to_256（部分正文截断）；契约判定 `final_answer_numeric_anchors_present=false` → **试点失败**。

## 三条原因链（全部离线证实）

1. **模型路由行为**：`compare_periods` 不在 core 面（39 项），但 profiling 工具触发扩张后进入可见面（扩张面 52+ 含它；执行中轮 3-4 面为 70）。工具可达，模型可见而未选择——这是 R09「工具存在但实际不可达/不被选用」靶风险在 R07 上的显形，非产品可达性缺陷。
2. **执行器升档条件设计错误**（已修）：部分正文 + `finish_reason=length` 未升档。该条件照搬了产品流式客户端的「零正文」约束（流式已发布正文无法撤回）；但可数执行器每轮是单次非流式请求、轮内零发布，任何 `finish_reason=length`（空正文/部分正文/截断的工具调用）都可安全作废重发。修复：`CountableJourneyClient` 对 `finish_reason=length` 一律升档。
3. **分析质量守卫逃逸**（已修，产品缺陷）：`_should_continue_for_analysis_quality` 要求 `tools_used ⊆ _PROFILING_TOOLS` 才拦截；`list_files` 不在该白名单，导致「用过工具但全是非实质工具」的最终回答被放行。修复：拦截面改为「用过工具 ∧ 与 `_SUBSTANTIVE_TOOLS` 无交集」，不再依赖白名单子集（`src/data_agent/agent/loop.py`）。该守卫在重跑中本身就是引导模型补做实质计算的机制。

## 验证

- 新增 RED→GREEN 测试：部分正文截断升档、截断工具调用轮升档、守卫对 profiling+浏览工具组合触发/对实质工具静默/对无工具静默/单次注入。
- `21 passed`（旅程 + 守卫套件）；`TestConversationFlow` 集成 4/5 通过（唯一失败为 HEAD 上即存在的 `test_streaming_without_guard_yields_text_deltas_immediately`）。
- 本次诊断与修复 Provider 调用 `0` 次。

## 重跑冻结（授权语义有变，需新授权）

- 新受控源码摘要：`sha256:fd5e3ff558c16083e683e8b308f0e698b02d0f25371aab6600a4d2d90d9b5f6a`。
- manifest 不变：`tests/acceptance/route_a_gate_c_journey_r07_candidate.json`（问题、数据 hash、契约、round_cap 6、阶梯 [2000, 8000, 32000]、至多 18 次均不变）。
- 语义变化：每轮 `finish_reason=length`（不限零正文）即升档；执行器升档条件修复 + 守卫修复将在重跑中生效。
- 授权模板：

```text
我授权 Gate C R07 旅程试点重跑：仅在 source digest sha256:fd5e3ff558c16083e683e8b308f0e698b02d0f25371aab6600a4d2d90d9b5f6a 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop 执行 R07_end_to_end_publication_journey 恰好 1 次：轮次至多 6、每轮按冻结阶梯 [2000, 8000, 32000] 单次非流式请求、该轮 finish_reason=length（无论正文形态）即升档，总计至多 18 次 Provider 调用，使用 2026-08-25-gate-c-journey-r07-preflight.md 冻结的问题、数据 hash、temperature=0、timeout=120 秒与契约（load_data 必需、最终回答含 1818/684/71/30 锚点），并仅写入 docs/audit/2026-08-25-gate-c-journey-r07-retry-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```
