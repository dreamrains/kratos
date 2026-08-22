# Data Agent V2 Slice 5C5P：不完整时间边界周期闭合

- **日期**：2026-08-20
- **状态**：Implemented；deterministic verification PASS；等待 review
- **基线提交**：`dfa9f0c3aa735d045244adeb7636c4f979cbc5dd`
- **历史触发 digest**：`sha256:db3464a5249f9ae6ea7787998298bcbdf5aae4ea2fe56b1e5aef656840b7151c`
- **修复后 source digest**：`sha256:4d0895b17d6f5a62b0a8fd470ecb8d8b0efd3067495b538f86d0e15581906c93`
- **本切片 Provider calls**：0

## 1. 真实旅程发现

5C5O 按精确授权完成一次 planning：Provider calls 1、重试 0、HTTP 201，Planner 正确返回 `analysis_unit=unit_id`。零 Provider 调用的确定性续跑和刷新完成。

数据验证与独立复算确认：

- 双组比较可靠且计算一致：A/B 各 21 个单位，均值差 14，95% CI `[4.324, 23.676]`，p=0.00566，Hedges g=0.885；
- 周趋势数值也与代码一致，但输入周不可比：7 个 bucket 中首周 4 天、末周 3 天，其和为 432、475，而中间五周完整；
- 旧输出把 2025-12-29 当数据起点，实际最早记录是 2026-01-01；
- 因此“未检出可靠历史趋势”是方法学不可用，不是可发布 null result。

## 2. RED 回归

provider-neutral RED 覆盖：

- 日级数据聚合为周频且首尾周不完整时，trend 必须 limited；
- 同一共享 regular-series 输入进入 forecast 时也必须 limited。

修复前结果：`2 failed`。trend 返回 `null_result`，forecast 直到 backtest quality 才失败，均未在不完整周期比较前 fail closed。

后续回归还覆盖：完整 Monday-Sunday 日级窗口继续允许周趋势；原生周频、原生月频保持可用；日级数据聚合到不完整首尾自然月也 fail closed；multi-finding 发布真实数据范围和限制，不生成 HAC 趋势结论。

## 3. 共享修复

- `prepare_regular_series()` 识别目标频率与源记录 cadence；
- weekly/monthly 高到低频聚合检查日历边界，产生 `incomplete_boundary_periods`；
- trend 与 forecast 共同消费该状态并在模型拟合前停止；
- `TimeSeriesResult`、`ForecastResult`、Finding uncertainty/assumptions 及方法块保存受控周期数量；
- trend 的 `start_time/end_time` 改为真实有效记录范围，bucket 标签仍只用于序列坐标；
- Slice 4B/4C/4D 给出明确安全文案，不补零、不插值、不静默删除部分周期。

## 4. 验证

- RED：`2 failed`；
- time series：`10 passed`；
- time/forecast/Slice 4B/4C/4D focused：`30 passed`；
- V2/config：`323 passed`；
- compileall、`git diff --check`：PASS；
- unified deterministic journey：PASS，owner/incident/SSE 三层，Provider calls 0；
- 新 source digest：`sha256:4d0895b17d6f5a62b0a8fd470ecb8d8b0efd3067495b538f86d0e15581906c93`。

证据见 `docs/superpowers/evidence/2026-08-20-v2-5c5p-incomplete-boundary-periods-evidence.json`。

## 5. 边界

本切片不把 5C5O 反向改判为 PASS，不生成真实 Provider 或人工语义 receipt。当前源码变化后需要 review、提交、重新计算 clean digest 和重制 preflight；任何真实调用仍需新的精确次数授权。
