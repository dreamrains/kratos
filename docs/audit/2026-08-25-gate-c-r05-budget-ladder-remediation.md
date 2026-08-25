# Gate C R05 预算截断架构修复与阶梯 canary 预检（未执行 Provider）

日期：2026-08-25

## R05 根因（来自 2000-token 批次收据）

在 `sha256:5f79c9a14fdc72eb93ad289787922b7ea81013e01ebf3642cd6d0bcd9e87e3cd` 上，R01–R07 恰好 7 次执行：6 项通过；R05 失败，安全收据为 `response_truncated`、`response_length_bucket=empty_or_non_string`、`response_finish_reason=length`、`response_reasoning_length_bucket=over_4096`。结论：该网关将隐藏 reasoning 计入 `max_tokens`，R05 在产出任何可见正文前耗尽 2000 预算。

同批次 R02 的 reasoning 已达 `1025_to_4096`。因此这不是 R05 单点问题，而是结构性问题：对推理模型，`max_tokens` 封顶的是「推理+输出」之和，而批次想约束的只是输出。继续调大标量只会移动失败场景，且要求用户预知各 Provider 语义漂移（OpenAI gpt-* 仅输出 / o 系列合并计算 / DeepSeek 各代语义不一），该参数不可长期维护。

## 架构决策（用户于 2026-08-25 确认方向）

预算所有权从用户维护的标量移交系统，分四层落地；`reasoning_effort` 降级方案被否决（损害强推理模型用户体验，且为 Provider 专属参数）。

1. **路由归一化**（`src/data_agent/llm/routing.py`）：裸模型名映射到已验证的原生 provider 路径（仅 `deepseek-*` → `deepseek/`，经 litellm 1.83.13 离线验证；显式 `provider/` 前缀永不改写；未知裸名保持默认路由）。修复：裸 `deepseek-*` 名此前在 litellm 直接抛 `BadRequestError`。context-window 元数据跨等价形式回退查找。
2. **默认省略 `max_tokens`**（`config.py`、`client.py`）：`MAX_TOKENS` 默认 `None`，请求不再携带该字段，输出上限由 Provider/模型默认托管并随模型升级自动跟随；显式设置时仍作为覆盖护栏（100–128000 校验保留）。
3. **有界预算升级重试**（`client.py`、`loop.py`）：仅当 `finish_reason=length` 且零可见正文（R05 形态）时升级重试；显式预算按 ×4 升档，省略预算按该次实际 `completion_tokens × 4` 起档；最多 2 次升级（单逻辑调用至多 3 次请求）、封顶 128000；部分正文截断不升级、原样上浮。流式路径补齐真实 `finish_reason` 传播（此前恒为 `stop`），零正文截断时透明重开流。AgentLoop 终态守卫：升级耗尽后给出明确提示（提高 MAX_TOKENS/换模型），不再静默空答案。
4. **Gate C 冻结阶梯**（`scripts/acceptance/route_a_provider_preflight.py`）：manifest 请求支持 `max_tokens_ladder`（1–3 档、严格升序、每档 100–128000、与标量互斥；场景 `call_budget` 必须等于档数，总预算=最坏情形调用数）。执行器仅对 `response_truncated` 逐档上行、首个成功档即停；语义失败与传输错误不升档；收据记录 `max_tokens_attempts`、成功档 `max_tokens_used`，`calls_made` 按实际请求数计。

## R05 阶梯 canary 冻结

- manifest：`tests/acceptance/route_a_gate_c_r05_budget_ladder_canary.json`。
- 当前受控源码摘要：`sha256:fc339c7915ba34d65dd375fa8b7437a2bf1c45ab0fca86302a4a5c4cfd384b1f`。
- 模型：`openai/deepseek-v4-flash`；请求：`temperature=0.0`、`timeout_seconds=120`、`response_format={"type":"json_object"}`、`max_tokens_ladder=[2000, 8000, 32000]`。
- 唯一场景：`R05_relationship_scope`，`call_budget=3`，总计恰好 3 次（最坏情形）。
- 冻结数据：`savings_card_orders` `sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`；`savings_card_user_payments` `sha256:cb0dab0ad6e0f8b7edf3ba2476bc525371f667a934242d29cf8d891a60e8ab03`。
- 冻结 prompt：`sha256:2f3103f89767535d9509c9b931eb4cad652f3412c4e6f2a63de3ed903c41694d` —— 与 2000 批次失败的 R05 调用**逐字节一致**；本 canary 相对该失败调用的唯一差异是冻结阶梯（单变量实验）。
- 2000 档预期复现已知失败形态；8000 档与产品历史默认一致；32000 档为推断上限。任何一档成功即停止整阶梯。

## 离线门禁

- 全量 `python -m pytest tests/`：`2250 passed, 11 skipped, 3 failed`。3 个失败甄别：`test_streaming_without_guard_yields_text_deltas_immediately` 与 `test_registered_tool_surface_matches_reviewed_manifest_exactly` 在干净 HEAD 上同样失败（stash 对照验证，先于本次改动）；`test_golden_savings_card_effect_evaluation` 单独运行通过（已知顺序依赖抖动）。
- 新增测试 28 项（routing 7、budget defaults 5、budget escalation 9、preflight ladder 7 含 canary 冻结），全绿。
- `compileall`、`git diff --check` 通过；本次 Provider 调用 `0`。
- 另记录：`uv run pytest tests/` 直接调用会在 `tests/real_data/test_golden_answer_quality.py` 收集期因 `scripts` 不在 `sys.path` 报错（HEAD 上同样存在）；全量运行需 `python -m pytest`。

## 所需单独授权

```text
我授权 Gate C R05 预算阶梯 canary：仅在 source digest sha256:fc339c7915ba34d65dd375fa8b7437a2bf1c45ab0fca86302a4a5c4cfd384b1f 上，使用 openai/deepseek-v4-flash，执行 R05_relationship_scope：按冻结阶梯 [2000, 8000, 32000] 逐档单次请求、仅前档 response_truncated 才升档、任何一档成功即停，总计至多 3 次，使用本收据冻结的数据 hash、prompt hash、temperature=0、timeout=120 秒、response_format={"type":"json_object"}，并仅写入 docs/audit/2026-08-25-gate-c-r05-budget-ladder-canary-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```

canary 通过后，R01–R07 主批次需以同一阶梯语义重新冻结并另行授权（7 场景 × 3 档上限 = 至多 21 次）。本次修复不构成 Gate C 或 Gate D 通过声明。
