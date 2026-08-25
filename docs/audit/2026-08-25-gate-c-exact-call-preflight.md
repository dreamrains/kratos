# Gate C 精确调用预检收据（未执行 Provider）

日期：2026-08-25

## 目的与边界

本收据只冻结一次有价值的真实 Provider 评估批次；它不执行 Provider 请求，也不把离线、mock 或 Flask `test_client()` 结果表述为真实 Provider 或浏览器验证。

- 准备前基线提交：`efd23a551c73842fe7041949ab381f731e7a5595`（`feat: complete slice 7 history migration regression`）。
- 当前受控源码摘要：`sha256:b060f8fb04d47ce73a59f0ac9c4287c30e5c0205281700f3f03ff3cb178c6046`。
- 未调用真实 Provider：`0`；未上传数据；未触碰、暂存或提交 `artifacts/`、`tmp/`。
- 本批次刻意不驱动可变轮数的 `AgentLoop`。它只评估冻结事实包上的模型遵循、范围、方法边界与发布语义；完整工具编排继续由既有 provider-neutral 和本地 Web 收据覆盖。

## 执行契约

- 模型必须为：`openai/deepseek-v4-flash`，并与运行配置逐字匹配。
- 请求参数固定为：`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`。
- 每场景只发 1 个非流式、无工具请求；`LLMClient.chat_once()` 显式传递 `num_retries=0`。
- 不使用 AgentLoop、工具、模型切换、fallback 或第二次调用。任何传输异常、工具调用、非 JSON、遗漏冻结事实、越界确认缺失或评估不合格，均记为已消耗的该场景一次，并立即停止整批。
- 网络层是否已到达远端在连接中断时不可判定；本契约计数的是本客户端发起的 Provider 请求尝试，绝不以重试来消除该不确定性。

## 冻结候选（总计最多 4 次）

| 场景 | 真实数据 ID 与 SHA-256 | Prompt SHA-256 | 调用预算 |
|---|---|---|---:|
| `R02_paired_before_after` | `savings_card_before_after` `e110c7e9e4abe5e21cede1e99a77e8f8a6827ef562a773eea16482808f6dce37` | `6025e9b1eb90cfa1e014983ad37f1cdecd974f684c444c6a2ad35aa0c68ccdbb` | 1 |
| `R03_dirty_cross_promotion` | `game_cross_promotion` `063f5415f490f90967b48d2e29972b3d2e1b908335aeb4a6420a90fb2eb19f83` | `ca123f61e7160078e90b3f4fd3e0b200de3753f5e1d43f873f3847fb83540b85` | 1 |
| `R04_game_a_synthesis` | `game_a_rewarded_video` `cd70017a106f6f2a64ff81bab7c75f4b8936745931679fd4782c414db1088ff7`; `game_a_in_app_purchase` `fe1644834de2c3495870ea9780d9a866bf780126368c3128924725647399624e`; `game_a_banner` `21919b8480488a3a24a19b27e75f8bf5ee9c9d36b3003e2f6d823cc154b39a8a` | `0d4fe70e9d10c48474f6cc2d83b7414f93c8298332a747882ebb75e092fb6d0c` | 1 |
| `R07_end_to_end_publication` | `savings_card_orders` `9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3` | `e866f5ee447873139271f1d37ed29da96c9d84c0f467842aadee088afc8b110a` | 1 |

事实包只包含已经由当前离线 oracle 验证的数值、数据质量边界和方法限制。Provider 的输出必须是 JSON，并使用全部事实 ID、承认禁止的因果/缺失补造推断、给出非空判断、限制和下一步。因此，这四次调用回答的是此前最易发生语义退步的四类问题，而不是用真实调用探索未知的协议缺口。

## 预检验证

- `tests/test_route_a_provider_preflight.py` 覆盖数据、模型、请求参数、prompt hash 与精确预算的离线冻结；配置或预算漂移在任何请求前失败。
- mock `completion` 传输失败验证 `chat_once()` 恰好一次，且 `num_retries=0`。
- fake Provider 覆盖成功时每场景恰好一次、`tools=None`；首个非 JSON 响应后 `calls_made=1`，第二场景不再调用。
- 当前运行：`16 passed`（Gate C 预检、模型配置、真实数据 manifest、release source）；`compileall` 与 `git diff --check` 通过。

## 下一步与授权格式

只有用户明确确认上表的模型、当前 source digest、四个数据/prompt hash、每场景 1 次和总计最多 4 次后，才能运行：

```text
我授权 Gate C 批次：仅在 source digest sha256:b060f8fb04d47ce73a59f0ac9c4287c30e5c0205281700f3f03ff3cb178c6046 上，使用 openai/deepseek-v4-flash，执行本收据列出的 R02、R03、R04、R07；每场景恰好 1 次，总计最多 4 次，使用冻结的数据 hash、prompt hash 和请求参数。任一失败立即停止整批；不重试、不换模型、不回退、不补跑。
```

如源码、模型、数据、提示或请求参数变化，预检和授权均失效，必须重建冻结单；不能沿用本收据。
