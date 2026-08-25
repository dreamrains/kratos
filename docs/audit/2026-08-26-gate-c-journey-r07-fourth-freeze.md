# Gate C R07 旅程四跑冻结：收尾推进机制（未执行 Provider）

日期：2026-08-26

## 收尾推进机制（产品能力，TDD 落地）

三跑结论是「模型 8 轮全工具调用、从未尝试总结」。本机制为质量守卫的逆向补全：`AgentConfig.wrap_up_round`（`WRAP_UP_ROUND`，默认 8，None 禁用，1–100 校验）；当**已完成轮 ≥ 阈值且 turn 仍在工具循环**时，向 messages 注入一次 `<analysis_wrap_up_guard>`（「基于已有证据收尾：已验证结论+数值+边界+下一步；除非收尾必需不再开新探索」）。每 turn 至多一次；turn 与 resume 两条流式路径均接线；`_reset_turn_tracking` 重置。

测试 9 项（阈值前不注入、命中注入一次、可禁用、跨 turn 重置、流式集成——第三轮前消息可见且 turn 正常收尾发布）。

## 四跑冻结

- manifest 变更：`round_cap` 8→10；总预算 24→30（10 轮 × 3 档）。问题、数据 hash、契约、阶梯、温度、超时、升档语义均不变。
- 受控源码摘要：`sha256:3a63426707e4152284d5cc69c235c083b1588dfff6e9c97628d1efcc375b1af3`。
- 预期行为路径：模型探索至轮 8 → wrap-up 注入 → 轮 9-10 内产出含锚点的最终回答；若模型仍不收尾或锚点缺失，按失败记录，不再有第五跑盲试（转按系统完整性结案）。
- 离线门禁：全量 `2283 passed`（3 失败中 2 个为 HEAD 先在已知对，1 个为本收据前已修正的断言跟进）；`compileall`、`git diff --check` 通过；Provider 调用 `0`。

## 所需单独授权

```text
我授权 Gate C R07 旅程试点四跑：仅在 source digest sha256:3a63426707e4152284d5cc69c235c083b1588dfff6e9c97628d1efcc375b1af3 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop（含默认启用的 WRAP_UP_ROUND=8 收尾推进机制）执行 R07_end_to_end_publication_journey 恰好 1 次：轮次至多 10、每轮按冻结阶梯 [2000, 8000, 32000] 单次非流式请求、该轮 finish_reason=length（无论正文形态）即升档，总计至多 30 次 Provider 调用，使用 2026-08-25-gate-c-journey-r07-preflight.md 冻结的问题、数据 hash、temperature=0、timeout=120 秒与契约（load_data 必需、最终回答含 1818/684/71/30 锚点），并仅写入 docs/audit/2026-08-26-gate-c-journey-r07-fourth-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```
