# Gate C R07 旅程试点预检收据（未执行 Provider）

日期：2026-08-25

## 冻结绑定

- manifest：`tests/acceptance/route_a_gate_c_journey_r07_candidate.json`（schema `route_a_journey_candidate.v1`）。
- 当前受控源码摘要：`sha256:06fecbd6985740cccb36022ca700e8278067800653fecc1334962caedbc49e04`。
- 模型：`openai/deepseek-v4-flash`（`.env` 主配置端点与凭据）。
- 请求：`temperature=0.0`、`timeout_seconds=120`、每轮非流式单请求（`chat_once` 语义：无重试、无回退、无客户端自动升级）、每轮冻结阶梯 `[2000, 8000, 32000]`（仅零正文 `finish_reason=length` 升档）、轮次硬上限 `round_cap=6`。
- 预算：**至多 18 次**（6 轮 × 3 档）；每轮首个非截断响应即完成该轮；实际调用数入收据。
- 问题（冻结）："上传的省钱卡订单数据覆盖 2026-04-07 至 2026-05-06。请比较前 15 天与后 15 天的收入变化，给出可发布结论及其边界。"
- 数据：`savings_card_orders` `sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`。
- 契约：必需工具 `load_data`；最终回答须含锚点 `1818`、`684`、`71`、`30`；无错误事件；轮数不超上限。
- 会话：`gate_c_journey_exec_r07`（专用前缀，执行前重建）。
- 收据：仅写入 `docs/audit/2026-08-25-gate-c-journey-r07-execution-report.json`；逐轮持久化（含 in-flight 标记）；只含结构摘要、档位、finish reason 与长度桶，绝无 Provider 正文。

## 边界

- 这是**首次真实 Provider 旅程级调用**：单次调用批次证明判断纪律，本试点证明真实工具循环（真实工具面 64 schema、真实工具执行、真实 SSE 链路语义）。
- 第 2 轮起 prompt 依赖模型此前的工具选择，无法预先 hash 冻结；可数性由轮次上限 × 档数保证。
- 离线回放实测 3 轮结构（见 [旅程回放构架收据](2026-08-25-gate-c-journey-replay-harness.md)）；真实模型轮数可能不同，上限 6。
- 通过不等于 Gate C 完成。

## 所需单独授权

```text
我授权 Gate C R07 旅程试点：仅在 source digest sha256:06fecbd6985740cccb36022ca700e8278067800653fecc1334962caedbc49e04 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop 执行 R07_end_to_end_publication_journey 恰好 1 次：轮次至多 6、每轮按冻结阶梯 [2000, 8000, 32000] 单次非流式请求、仅零正文 finish_reason=length 才升档，总计至多 18 次 Provider 调用，使用本收据冻结的问题、数据 hash、temperature=0、timeout=120 秒与契约（load_data 必需、最终回答含 1818/684/71/30 锚点），并仅写入 docs/audit/2026-08-25-gate-c-journey-r07-execution-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```
