# Gate C 主模型 R01–R07 审计批次收据

日期：2026-08-25

- 源码摘要：`sha256:63166cea90bf2e516a83587c6fb123230958bae618e1178727a873ec2d3dd2a7`。
- 配置：`openai/deepseek-v4-flash`、`temperature=0.0`、`max_tokens=1000`、`timeout_seconds=120`。
- 受用户精确授权的 R01–R07 各一次实际完成：`calls_made=7`；无重试、换模型、fallback、AgentLoop 或工具调用。
- 受控报告：[batch-report.json](2026-08-25-gate-c-main-model-r01-r07-batch-report.json)；仅包含 digest、hash、稳定失败码及摘要，无原始模型文本。

| 场景 | 结果 |
|---|---|
| R01 | 通过：全事实 ID、数值落地、1 条限制 |
| R02 | 失败：`provider_response_validation / response_not_json` |
| R03 | 通过：全事实 ID、数值落地、2 条限制 |
| R04 | 通过：全事实 ID、数值落地、1 条限制 |
| R05 | 通过：全事实 ID、数值落地、1 条限制 |
| R06 | 通过：全事实 ID、数值落地、1 条限制 |
| R07 | 通过：全事实 ID、数值落地、2 条限制 |

结论：本批次为 `completed_with_failures`，不能称为主模型 R01–R07 通过。R02 的非 JSON 是共享输出格式可靠性缺口；后续修复采用请求级 `response_format={"type":"json_object"}`，而不放宽或绕过 R02 校验。该修复改变 source digest，下一批必须重新预检并获得新的精确授权。
