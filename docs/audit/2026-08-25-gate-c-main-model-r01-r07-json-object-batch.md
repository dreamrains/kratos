# Gate C 主模型 R01–R07 JSON-object 批次收据

日期：2026-08-25

- 源码摘要：`sha256:80b149a2c035cd8430c45be3cca06e5d1ea1fad3dfae48a3d4983350be33b531`。
- 用户授权 `openai/deepseek-v4-flash`、R01–R07 各 1 次、总计 7 次，带 `response_format={"type":"json_object"}`、冻结数据/prompt hash 与逐场景报告路径。
- 受控报告：[json-object batch report](2026-08-25-gate-c-main-model-r01-r07-json-object-batch-report.json) 确认 `calls_made=7`、`completed_with_failures`，且不含原始 Provider 文本。

| 场景 | 结果 |
|---|---|
| R01、R02、R03、R04、R06、R07 | 通过：完整事实 ID、数值落地、限制、禁止推断确认 |
| R05 | 失败：`provider_response_validation / response_not_json` |

结论：`json_object` 使 R02 恢复通过，但不能稳定保证纯 JSON。本批次不通过，不重跑。下一步是在共享解析层严格提取唯一 JSON 对象信封并记录 `direct/fenced/embedded` 摘要，仍保持全部字段、数值和边界校验；修复后需要新的 source-bound 授权。
