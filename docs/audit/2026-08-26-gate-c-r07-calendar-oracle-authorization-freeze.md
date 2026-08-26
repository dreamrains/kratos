# Gate C R07 日历 oracle 重验授权冻结（未执行 Provider）

日期：2026-08-26

## 冻结前提

- 分支：`rebuild`
- 受控源码摘要：`sha256:86ad00aa3920ecccdaf2a1b0b03706c07a5689b46e3f3d94c054e5637b866a3e`
- 候选清单：`tests/acceptance/route_a_gate_c_journey_r07_candidate.json`，文件 hash `sha256:8a8d6f19422444f960c0556442e126d01b51ff877ce1442c4611e0741bbee853`。
- 真实工具 replay：`tests/acceptance/route_a_gate_c_journey_r07_replay.json`，文件 hash `sha256:ebcbef8687a26a791b9348300ae3fd42eb55a777866e800f8e058fd9199519ec`。
- 数据：`savings_card_orders`，`sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`，上传为 `省钱卡订单.xlsx`。
- 问题 hash：`sha256:7822388b42f78708f4a90bb86751f502456db0ae647be5f3b1eadf4c18268d0c`。
- 模型：`openai/deepseek-v4-flash`；temperature=0、timeout=120 秒、每轮 token 阶梯 `[2000,8000,32000]`，仅 `finish_reason=length` 升档；round_cap=10，最多 30 次 Provider 调用。
- 执行契约：`load_data` 与 `compare_periods` 都必须调用；最终正文含 `1818`、`684`、`71`、`30`；预检会先重跑真实工具 oracle，失败则零调用。
- 唯一允许写入的 Provider 报告：`docs/audit/2026-08-26-gate-c-r07-calendar-oracle-report.json`。

多轮 Agent prompt 会因真实工具结果和模型响应演进，不能在调用前诚实地声称单一静态 prompt hash；每轮的 `prompt_sha256` 与工具 schema hash 由执行报告逐轮记录。问题、候选、真实工具 replay、数据与受控源码均已冻结。

```text
我授权 Gate C R07 日历 oracle 重验：仅在 source digest sha256:86ad00aa3920ecccdaf2a1b0b03706c07a5689b46e3f3d94c054e5637b866a3e 上，使用 openai/deepseek-v4-flash，按 docs/audit/2026-08-26-gate-c-r07-calendar-oracle-authorization-freeze.md 与 tests/acceptance/route_a_gate_c_journey_r07_candidate.json 冻结的候选 hash、真实工具 replay hash、上传、问题 hash、数据 hash、temperature=0、timeout=120 秒、每轮阶梯 [2000,8000,32000] 和 round_cap=10，执行 R07_end_to_end_publication_journey 恰好 1 次；总计至多 30 次 Provider 调用，仅 finish_reason=length 才升档。预检（包括真实工具 oracle replay）不通过则零调用；失败即停止该旅程；不重试、不换模型、不回退、不补跑；仅写入 docs/audit/2026-08-26-gate-c-r07-calendar-oracle-report.json。
```

本冻结不授权 R09、其他模型、历史报告改写、推送、合并、部署或删除资产。
