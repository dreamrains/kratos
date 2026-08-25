# Gate C R07 旅程重跑结果与三跑冻结（未执行新的 Provider）

日期：2026-08-25

## 重跑事实（授权消耗 7/18）

在 `sha256:fd5e3ff558c16083e683e8b308f0e698b02d0f25371aab6600a4d2d90d9b5f6a` 上重跑恰好 1 次（收据：[retry report](2026-08-25-gate-c-journey-r07-retry-report.json)）：

- 7 次 Provider 调用、6 轮完成；轮 5 空正文 `finish_reason=length` 触发**首次真实升档**（2000→8000 后以 tool_calls 完成）。
- 轮 5 模型给出全 profiling 最终回答 → **修复后的分析质量守卫正确拦截**并注入守卫消息。
- 轮 6 模型经 `tool_search` 定位并调用 `compare_periods`——**实质分析工具首次被真实路由**（首跑从未发生）。
- 第 7 轮被 loop 请求时超出 round_cap=6 → 执行器按契约拒绝（`JourneyStructureError`；流式异常后 loop 的同步回退再次触发拒绝，`rounds_used` 记 8，其中零请求消耗）→ turn 终止，最终回答未产出，锚点缺失 → **失败**。

## 判定

两处修复均被真实验证有效（升档 + 守卫路由引导）。失败原因是**轮次预算过紧**：4 轮探索 + 1 次守卫拦截 + 1 轮实质分析 = 6 轮耗尽于总结之前。这是试点对预算形态的测量产出，不是产品质量缺陷。

## 三跑冻结（round_cap 6→8，需新授权）

- manifest 变更：`round_cap` 6→8；总预算 18→24（8 轮 × 3 档）；问题、数据 hash、契约、阶梯、温度、超时均不变。
- 新受控源码摘要：`sha256:e59e3ec2f7657c4793d61559045ace677926aa57d14dc9a5b15994dc5c925b66`。
- 授权模板：

```text
我授权 Gate C R07 旅程试点三跑：仅在 source digest sha256:e59e3ec2f7657c4793d61559045ace677926aa57d14dc9a5b15994dc5c925b66 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop 执行 R07_end_to_end_publication_journey 恰好 1 次：轮次至多 8、每轮按冻结阶梯 [2000, 8000, 32000] 单次非流式请求、该轮 finish_reason=length（无论正文形态）即升档，总计至多 24 次 Provider 调用，使用 2026-08-25-gate-c-journey-r07-preflight.md 冻结的问题、数据 hash、temperature=0、timeout=120 秒与契约（load_data 必需、最终回答含 1818/684/71/30 锚点），并仅写入 docs/audit/2026-08-25-gate-c-journey-r07-third-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```
