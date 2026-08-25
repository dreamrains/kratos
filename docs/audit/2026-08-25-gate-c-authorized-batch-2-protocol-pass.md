# Gate C 获授权批次 2 收据（协议通过，质量缺口保留）

日期：2026-08-25

## 冻结绑定与实际调用

- 源码提交：`de4266476590cf4b02c258cb4cc200e19d450bcd`（`fix: strengthen gate c response contract`）。
- 受控源码摘要：`sha256:7aa0e6c1d13b64b30ddd864a12e1534053a96eb083062a5e913dda47c44008d4`。
- 用户授权模型 `openai/deepseek-v4-flash`，R02/R03/R04/R07 每个场景恰好 1 次、总计恰好 4 次，及冻结数据/prompt hash、`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`。
- 执行前预检、执行器路径、模型、数据 hash 与 source digest 全部匹配。

| 场景 | 实际请求 | 当时协议结果 |
|---|---:|---|
| `R02_paired_before_after` | 1 | 通过 |
| `R03_dirty_cross_promotion` | 1 | 通过 |
| `R04_game_a_synthesis` | 1 | 通过 |
| `R07_end_to_end_publication` | 1 | 通过 |

- 批次结果：`passed`，`calls_made=4`；无重试、换模型、fallback、AgentLoop 或工具调用。
- 不持久化原始 Provider 响应、推理内容或密钥。

## 质量边界与后续离线修复

确认事实：四个响应均满足当时的 JSON、场景 ID、全事实 ID、禁止推断确认、非空限制与下一步契约。随后人工审阅执行回显发现 `decision` 复述了结构模板的占位语，未实际落地冻结数值；因此本收据不能作为有价值的语义质量通过或 Gate C 完成证据。

已实施但尚未真实调用验证的修复：拒绝模板回显，要求 `decision` 包含冻结事实包中的原样数字，并将成功输出缩减为 fact ID、限制计数、布尔确认和长度等稳定元数据。该修复改变 source digest/prompt hash，任何下一批真实调用都须重新预检并重新精确授权。
