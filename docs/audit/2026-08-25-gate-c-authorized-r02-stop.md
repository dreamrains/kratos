# Gate C 获授权 R02 批次停止收据

日期：2026-08-25

## 冻结绑定

- 源码提交：`5a90e9ce248c26799405aca5e2cd7f654144c154`（`feat: prepare exact gate c provider preflight`）。
- 受控源码摘要：`sha256:b060f8fb04d47ce73a59f0ac9c4287c30e5c0205281700f3f03ff3cb178c6046`。
- 用户明确授权模型 `openai/deepseek-v4-flash`、R02/R03/R04/R07、每个已到达场景 1 次、总计最多 4 次、`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`，并规定失败即停止、无重试/换模型/回退/补跑。
- 执行前重新验证执行器位于当前工作区、当前模型与摘要匹配，且所有冻结数据和 prompt hash 通过预检。

## 实际执行

| 场景 | 冻结预算 | 实际 Provider 请求 | 结果 |
|---|---:|---:|---|
| `R02_paired_before_after` | 1 | 1 | 返回内容不是要求的 JSON；schema 验证失败，批次立即停止 |
| `R03_dirty_cross_promotion` | 1 | 0 | 未调用 |
| `R04_game_a_synthesis` | 1 | 0 | 未调用 |
| `R07_end_to_end_publication` | 1 | 0 | 未调用 |

- 结果：`status=stopped_on_failure`，`calls_made=1`。
- 未再次调用 R02；未调用 R03/R04/R07；未使用工具、AgentLoop、fallback 或其他模型。
- 不持久化原始 Provider 响应、推理内容或密钥。可审计的稳定失败原因为 `Provider response is not a JSON object`。

## 结论与边界

这不是通过结论，也不能据此声称真实 Provider、完整 AgentLoop 或真实浏览器旅程通过。失败按授权条款正确止损，未把剩余三次用来试探其他未知问题。

本次收据的失败即整批停止规则已被用户在事后明确替换为“批内继续、批后统一修复”；此变更不追溯本次已停止批次。后续先在离线/模拟环境补强 JSON 协议并重新预检；任何新的真实调用仍需要新的、精确且与新 source digest 绑定的用户授权。
