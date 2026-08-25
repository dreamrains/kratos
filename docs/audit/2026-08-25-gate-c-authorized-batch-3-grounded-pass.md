# Gate C 获授权批次 3 收据（冻结四场景通过）

日期：2026-08-25

## 冻结绑定与实际调用

- 源码提交：`772abc7e02c9a3d2048f5104394b9a13a79b301c`（`fix: require grounded gate c decisions`）。
- 受控源码摘要：`sha256:91f0aaf412bc3be8f0e65cbf6e0fcba60b6a14ccc2ed4dcd624400a81e0e11e1`。
- 用户授权模型 `openai/deepseek-v4-flash`，R02/R03/R04/R07 每个场景恰好 1 次、总计恰好 4 次，及冻结数据/prompt hash、`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`。
- 执行前预检、执行器路径、模型、数据 hash 与 source digest 全部匹配。

| 场景 | 实际请求 | 结果摘要 |
|---|---:|---|
| `R02_paired_before_after` | 1 | 全事实 ID、禁止推断确认、1 条限制；decision 103 字符，next action 46 字符 |
| `R03_dirty_cross_promotion` | 1 | 全事实 ID、禁止推断确认、2 条限制；decision 72 字符，next action 55 字符 |
| `R04_game_a_synthesis` | 1 | 全事实 ID、禁止推断确认、2 条限制；decision 40 字符，next action 39 字符 |
| `R07_end_to_end_publication` | 1 | 全事实 ID、禁止推断确认、2 条限制；decision 71 字符，next action 36 字符 |

- 批次结果：`passed`，`calls_made=4`。
- 每个通过项均满足：场景 ID、全部冻结事实 ID、非空限制、`prohibited_inference_acknowledged=true`、非占位 decision/next action，且 decision 引用了冻结事实中的原样数值。
- 无重试、换模型、fallback、AgentLoop 或工具调用；不持久化原始 Provider 响应、推理内容或密钥。

## 证据边界

本收据仅证明四个冻结事实包上的单请求 Provider 遵循、数值落地、方法限制与禁止推断契约。它不证明完整 AgentLoop、真实上传浏览器旅程、R01、R05/R06、异构模型或完整 Gate C/Gate D 通过；这些需要独立的冻结范围、预检和精确授权。
