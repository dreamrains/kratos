# Gate C R07 日历边界与真实工具 oracle 修复（零 Provider）

日期：2026-08-26
受控源码摘要：`sha256:86ad00aa3920ecccdaf2a1b0b03706c07a5689b46e3f3d94c054e5637b866a3e`

## 根因

R07 的冻结数据和历史数值并不冲突。`compare_periods` 与 `contribute_decomposition` 将用户给出的结束日期标准化到当天 00:00:00 后使用 `<=` 比较，因而丢弃了结束日其余时间的事件。R07 两个 15 天期间各有一条售价 45 的结束日事件被排除，旧工具结果遂为 1773/639，而正确完整自然日口径为 1818/684。

历史 R07 replay 还存在独立门禁缺口：它只验证工具调用名称与脚本化模型正文数字。其 `load_data` 使用了当前运行时不可解析的相对路径，实际没有加载工作簿，但没有使 replay 失败。因此历史 replay 的 passed 不能作为真实数据工具证据。

## 修复的共享契约

1. 新增 `inclusive_date_period_mask`：将日期范围实现为 `[start_day, end_day + 1 day)`，保留时间戳精度并完整包含声明的结束自然日。
2. `compare_periods` 与 `contribute_decomposition` 共同使用该函数；没有为 R07 单独打补丁。
3. R07 replay 通过产品 inbox 放置冻结工作簿，并以上传文件名执行 `load_data`；问题文本也与 Web 上传后的形状一致。
4. replay 读取实际 `tool_result.web.data`，对 `compare_periods` 的结构化标量进行 oracle 校验。R07 candidate 的预检必须验证该 replay 文件 hash 且重跑成功，才会允许任何 Provider 调用。
5. R07 实际旅程必需工具由 `load_data` 收紧为 `load_data` 与 `compare_periods`；模型正文锚点不再能代替比较工具调用。

## 真实数据重算

- 数据：`savings_card_orders`，`sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`。
- 前期：2026-04-07 至 2026-04-21，47 行、15 天、售价 1818。
- 后期：2026-04-22 至 2026-05-06，24 行、15 天、售价 684。
- 合计：71 行、30 个自然日。两个期末被修复纳入的事件各为售价 45。
- 离线 replay：passed，所有 6 个结构化 oracle 断言通过，`provider_calls=0`。

## 验证边界

- `tests/test_comparability.py`：13 PASS，0 FAIL。
- `tests/test_route_a_journey_replay.py`、`tests/test_route_a_journey_countable.py`、`tests/test_analysis_quality.py`：41 passed，8 skipped。
- R07 candidate preflight：`ready=true`、`provider_calls=0`、最大调用预算 30。
- `compileall src`：通过。
- 本地真实浏览器：运行 Flask、SSE、AgentLoop、真实工具和持久化，固定本地客户端只提供三轮控制响应；最终页面的 receipt-backed appendix 显示 `metrics.售价.period_a=1818`、`metrics.售价.period_b=684`。这不是 Provider 验证。

一次更宽的旧 pipeline 组合测试打印了 LiteLLM 重试日志，因此未将其计入本收据，也不再把该集合用于零 Provider 声明；本收据中的 R07 replay、预检与浏览器本地客户端路径均明确为零 Provider。

## 冻结材料

- R07 candidate：`sha256:8a8d6f19422444f960c0556442e126d01b51ff877ce1442c4611e0741bbee853`。
- R07 replay：`sha256:ebcbef8687a26a791b9348300ae3fd42eb55a777866e800f8e058fd9199519ec`。
- R07 question：`sha256:7822388b42f78708f4a90bb86751f502456db0ae647be5f3b1eadf4c18268d0c`。

本轮没有调用 Provider、没有推送、合并、部署、切根、删除历史实现，亦未处理 `artifacts/` 或 `tmp/`。
