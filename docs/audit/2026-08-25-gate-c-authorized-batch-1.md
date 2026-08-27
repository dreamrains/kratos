# Gate C 获授权批次 1 收据（完整诊断）

日期：2026-08-25

## 冻结绑定与实际调用

- 源码提交：`f3c061bd22608422c041819268d63b7af71ec60f`（`feat: complete gate c diagnostic batches`）。
- 受控源码摘要：`sha256:52bdffd2f21098c39506abed14dfc45948410589ac13a015fcd91ac604817f00`。
- 用户授权模型 `openai/deepseek-v4-flash`，R02/R03/R04/R07 每个场景恰好 1 次、总计恰好 4 次，及冻结数据/prompt hash、`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`。
- 执行前预检、执行器路径、模型、数据 hash 与 source digest 全部匹配。

| 场景 | 实际请求 | 结果 | 稳定失败码 |
|---|---:|---|---|
| `R02_paired_before_after` | 1 | 失败 | `provider_response_validation / missing_method_limitations` |
| `R03_dirty_cross_promotion` | 1 | 失败 | `provider_response_validation / prohibited_inference_unacknowledged` |
| `R04_game_a_synthesis` | 1 | 失败 | `provider_response_validation / missing_method_limitations` |
| `R07_end_to_end_publication` | 1 | 失败 | `provider_response_validation / missing_method_limitations` |

- 批次结果：`completed_with_failures`，`calls_made=4`。
- 无重试、换模型、fallback、AgentLoop 或工具调用；未持久化原始响应、推理内容或密钥。

## 已确认事实、未确认原因与修复方向

已确认：四个响应均越过 JSON 解析与场景 ID/冻结事实校验，随后在所列必填字段上失败。未确认：Provider 实际使用了何种替代字段或为何漏填；原始文本依照安全边界未被保存，不能据此臆测。

下一步是离线强化请求中的精确 JSON 结构、全部事实 ID、非空 `method_limitations` 与字面量 `true` 提示，并以 mock 回归测试验证请求契约。该修复会改变 source digest 和 prompt hash，因此不能沿用本批次授权；修复后必须重新预检并取得新的精确授权。
