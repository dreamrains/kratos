# Gate C 主模型 R01–R07 精确调用预检收据（未执行 Provider）

日期：2026-08-25

## 当前冻结绑定

- 基线提交：`258d7f22b8bb7cda7c8da9a85fa0abf481a92279`。
- 当前受控源码摘要：`sha256:459122b2d71539414079992967b20916101618d1f0536d9c8bc4e4c43713db79`。
- 模型：`openai/deepseek-v4-flash`；`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`。
- 本预检真实 Provider 调用：`0`；未上传数据；未触碰、暂存或提交 `artifacts/`、`tmp/`。
- 每个已到达场景恰好一次、无工具、无 AgentLoop、无 fallback、`num_retries=0`；预检失败为零调用，批内失败记录后继续其余独立场景。

## 七场景主模型批次（总计恰好 7 次）

| 场景 | 数据 ID | Prompt SHA-256 | 预算 |
|---|---|---|---:|
| `R01_retention_curve` | `game_b_retention` `63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0` | `85af8c9c7320ad6f906683facdc43570b6449ed1eb3f482ca6638c798af6fb2b` | 1 |
| `R02_paired_before_after` | `savings_card_before_after` `e110c7e9e4abe5e21cede1e99a77e8f8a6827ef562a773eea16482808f6dce37` | `ce3a489e2e2fe0c52d670b996558e5cf26fd610ff1edb74043d2497f5e68dec7` | 1 |
| `R03_dirty_cross_promotion` | `game_cross_promotion` `063f5415f490f90967b48d2e29972b3d2e1b908335aeb4a6420a90fb2eb19f83` | `980727a4567acc13a8d0227a477f1e2771f3e88a7bae9542f994622e95be4b9c` | 1 |
| `R04_game_a_synthesis` | `game_a_rewarded_video` `cd70017a106f6f2a64ff81bab7c75f4b8936745931679fd4782c414db1088ff7`; `game_a_in_app_purchase` `fe1644834de2c3495870ea9780d9a866bf780126368c3128924725647399624e`; `game_a_banner` `21919b8480488a3a24a19b27e75f8bf5ee9c9d36b3003e2f6d823cc154b39a8a` | `469349d64f70d04c6107b0073689781a0fbf7b3e99060d0522e529a416cd840e` | 1 |
| `R05_relationship_scope` | `savings_card_orders` `9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`; `savings_card_user_payments` `cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03` | `2f3103f89767535d9509c9b931eb4cad652f3412c4e6f2a63de3ed903c41694d` | 1 |
| `R06_long_term_value_cohort` | `savings_card_user_payments` `cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03` | `1c22ed1548b54abf6218de897810f3218b2609fb1424ac14243d4bf2e4a75f1e` | 1 |
| `R07_end_to_end_publication` | `savings_card_orders` `9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3` | `018865ff3f65135a32251757a68f813c7424e3f911f96a58e04d0fa1a013f7e8` | 1 |

## 新增真实数据 oracle

- R01：62 个日级观测（2020-07-01 至 2020-08-31）；幂律最优，`a=0.18800129`、`b=-0.71667274`、`R²=0.98240474`，6 个零值点排除；只允许描述性、不外推结论。
- R05：71 行订单与 13,757 行付费数据按 `user_id` 为 `many_to_many`，关系 `rejected`；左/右覆盖率 `0.98591549`/`1.0`，倍率 `1.11325144`，禁止物化 join。
- R06：13,757 行、62 用户，支付窗口 2026-02-01 至 2026-05-10；cohort 大小 45/8/8/1，2026-02 的 month_1 为 97.78%；晚 cohort 存在右截断，零值不可直接解释为流失。

`tests/test_route_a_provider_candidate_oracles.py` 直接从当前真实文件与确定性工具重算这些事实；连同原 Gate C、模型配置、数据 manifest 与 source-digest 检查共 `22 passed`，以及 `compileall`、`git diff --check` 通过。

## 不在本批次的范围

该批次是单请求冻结事实评估，不是完整 AgentLoop 或浏览器旅程。异构模型的实际可用 model ID/配置未被猜测，必须先有明确配置和独立预检。R08/R09 继续由现有 provider-neutral/Web 收据覆盖，是否需要真实调用另行决定。

## 授权格式

```text
我授权 Gate C 主模型批次：仅在 source digest sha256:459122b2d71539414079992967b20916101618d1f0536d9c8bc4e4c43713db79 上，使用 openai/deepseek-v4-flash，执行本收据列出的 R01、R02、R03、R04、R05、R06、R07；每个场景恰好 1 次，总计恰好 7 次，使用冻结的数据 hash、prompt hash、temperature=0、max_tokens=1000、timeout=120 秒。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
