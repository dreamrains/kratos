# Gate C 主模型 R01–R07 带原子报告预检收据（未执行 Provider）

日期：2026-08-25

## 绑定与执行报告

- 基线提交：`2e3eda2fa800f3fa1252e074c7d6b517a1cded57`。
- 当前受控源码摘要：`sha256:63166cea90bf2e516a83587c6fb123230958bae618e1178727a873ec2d3dd2a7`。
- 模型：`openai/deepseek-v4-flash`；`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`。
- Provider 调用数：本预检 `0`。真实执行必须传入 `--report-path docs/audit/2026-08-25-gate-c-main-model-r01-r07-batch-report.json`；路径或 `.json` 后缀不符合要求则在任何调用前失败。
- 报告使用临时文件后原子替换，只保存 source digest、预算、稳定错误码和响应摘要；含 `response`、`text`、`reasoning` 或 `raw` 的报告被拒绝。

## 冻结七场景

| 场景 | Prompt SHA-256 | 预算 |
|---|---|---:|
| `R01_retention_curve` | `85af8c9c7320ad6f906683facdc43570b6449ed1eb3f482ca6638c798af6fb2b` | 1 |
| `R02_paired_before_after` | `ce3a489e2e2fe0c52d670b996558e5cf26fd610ff1edb74043d2497f5e68dec7` | 1 |
| `R03_dirty_cross_promotion` | `980727a4567acc13a8d0227a477f1e2771f3e88a7bae9542f994622e95be4b9c` | 1 |
| `R04_game_a_synthesis` | `469349d64f70d04c6107b0073689781a0fbf7b3e99060d0522e529a416cd840e` | 1 |
| `R05_relationship_scope` | `2f3103f89767535d9509c9b931eb4cad652f3412c4e6f2a63de3ed903c41694d` | 1 |
| `R06_long_term_value_cohort` | `1c22ed1548b54abf6218de897810f3218b2609fb1424ac14243d4bf2e4a75f1e` | 1 |
| `R07_end_to_end_publication` | `018865ff3f65135a32251757a68f813c7424e3f911f96a58e04d0fa1a013f7e8` | 1 |

数据 ID 与完整 SHA-256、以及 R01/R05/R06 真实文件 oracle 见 [上一版七场景预检](2026-08-25-gate-c-main-model-r01-r07-preflight.md)；本版仅增加受控报告机制，事实包和 prompt hash 未变。

验证：`23 passed`（含真实文件 candidate oracle 与报告安全测试）、`compileall`、`git diff --check`、配置/数据/source 预检均通过。

```text
我授权 Gate C 主模型批次：仅在 source digest sha256:63166cea90bf2e516a83587c6fb123230958bae618e1178727a873ec2d3dd2a7 上，使用 openai/deepseek-v4-flash，执行本收据列出的 R01、R02、R03、R04、R05、R06、R07；每个场景恰好 1 次，总计恰好 7 次，使用冻结的数据 hash、prompt hash、temperature=0、max_tokens=1000、timeout=120 秒，并只写入 docs/audit/2026-08-25-gate-c-main-model-r01-r07-batch-report.json。预检不通过则零调用；批内失败记录后继续其余场景；不重试、不换模型、不回退、不补跑。
```
