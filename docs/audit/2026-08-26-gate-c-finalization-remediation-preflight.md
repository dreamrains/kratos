# Gate C 受控最终化修复与重验预检（未执行 Provider）

日期：2026-08-26

## 触发事实

当前最终两次真实旅程收据均如实为失败：

- R07 六跑：10 次 Provider 调用后达到 `round_cap=10`；无最终回答锚点。
- R09 三跑：14 次 Provider 调用后达到 `round_cap=12`；无最终回答锚点。

二者均完成了所需实质工具链，但原实现仅在第 8 轮后注入软性收尾文字，仍持续向模型提供工具 schema。模型继续工具调用，随后计数执行器拒绝下一轮；流式 fallback 将该结构拒绝表面化为“LLM 返回为空”。这不是可接受的完成/发布验证成功，也不能靠禁用推理解决。

## 本次零调用修复

受控源码摘要：`sha256:61edff7c3c979d0b17fca0a955ee55e6e378b3f818f0bc4630a89976c9b85290`。

1. 收尾阈值后，只有本轮已执行实质分析（例如 `compare_periods`、`curve_fitting`、`contribute_decomposition`、统计/预测/回归等）才进入 `analysis_finalization_mode`。
2. 最终化轮仍由模型完整推理并生成答案；仅不再传入工具定义，因而不能继续无限探索。
3. 只有读取、浏览、清洗、字段派生或变换不构成“证据充分”；这类回合保留既有软性守卫，不强迫无依据结论。
4. `round_cap_exceeded` 保持为明确结构失败；拒绝的下一轮不计入 `rounds_used`，也不再伪装成空 LLM 响应。

这不是 `reasoning_effort`、temperature 或模型切换；请求不新增任何 Provider 参数。

## 零调用门禁

- `tests/test_analysis_quality_guard_scope.py`：最终化只在实质分析后关闭工具面，且后续请求的 `tools=None`。
- `tests/test_route_a_journey_countable.py`：上限拒绝不增计数，并输出 `round_cap_exceeded`。
- R07/R09 当前清单预检均 `ready=true`：温度 0、超时 120 秒、阶梯 `[2000, 8000, 32000]`，最坏调用数分别为 30 与 36。

## 当前结论与后续授权边界

历史 Gate C 收据仍是对应旧源码的真实记录，不能被改写；本修复使它们不再是当前源码的通过证据。Gate C 的“判断纪律、工具可达和有界执行”历史结论保留，但“当前源码的旅程完成/发布真实性”须重新验证。

下一步应先取得一条或两条新的精确授权，在本 digest 上执行 R07 与 R09 各一次，沿用各自冻结的问题、数据 hash、模型 `openai/deepseek-v4-flash`、temperature=0、timeout=120 秒、阶梯和既有最坏调用预算。两条旅程均通过后，才冻结当前 digest 的主模型/异构批次重验范围；不得把本地 fake 或预检冒充真实 Provider 结果。
