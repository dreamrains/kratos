# Data Agent V2 Slice 5C5Q：时间边界修复后的真实 Provider 预检

- **日期**：2026-08-20
- **状态**：精确单次调用与确定性续跑完成；真实 Provider API journey PASS，人工语义评审待完成
- **基线提交**：`fec3e701a5081cd18a884af534c53529a5038775`
- **source digest**：`sha256:4d0895b17d6f5a62b0a8fd470ecb8d8b0efd3067495b538f86d0e15581906c93`
- **执行时 Git HEAD**：`b470ed78e6ab08f01d2c40e3a6a71a0749dc4b29`
- **本切片 Provider calls**：1

## 1. 前置闭环

5C5O 证明 Planner 的 analysis-unit 合同已经生效，但暴露出周频求和对不完整首尾周期的错误比较。5C5P 已在 trend/forecast 共享 regular-series 合同中 fail closed，保留原生周期数据和完整日历窗口，并用真实记录范围替代 period bucket 范围。

当前源码已通过 323 个 V2/config 测试、compileall、diff check 和 owner/incident/SSE 三层确定性 journey。5C5O authorization 已 consumed，不可复用；其 attempt 只是旧 digest 上的历史语义失败事实。

## 2. 当前预检身份

- 场景：`unified_analysis_entry`；
- 目的：`analysis_planning`；
- 模型：`openai/deepseek-v4-flash`；
- Provider host：`api.deepseek.com`；
- dataset fingerprint：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`；
- request fingerprint：`sha256:f2908f90327a0e43ce6fc9c74eb574a7e3d5311abe564be2ec3b0000d806385d`；
- Planner schema fingerprint：`sha256:6d0eaf57ac63110ee5cc6ca5a6290bc7fe206c69cb6a7b4d943cf60a9ac363e8`。

## 3. 离线结果

- preflight validator：PASS，reason codes 为空；
- Planner parity：PASS，7 个自动分析类型、9 个状态分支；
- estimated input：3,510 tokens；
- model context：1,000,000 tokens；
- reserved output：8,000 tokens；
- available input：992,000 tokens；
- fits：true；
- authorization issued：false；
- Provider calls observed：0。

## 4. 精确调用边界

需要恰好 1 次 `analysis_planning` Provider 调用。授权必须绑定本文件中的 source digest、`openai/deepseek-v4-flash`、`unified_analysis_entry`、`analysis_planning`、`api.deepseek.com` 和精确次数 1。

失败即停止，不自动重试。若返回 `needs_input`，保存回答与重新估算不调用 Provider；任何 follow-up planning 仍需新的精确授权。

本 preflight 不签发 authorization，不调用 Provider，不构成真实 Provider 或人工语义 PASS，不宣称 release readiness、产品完成或根入口切换。

## 5. 已授权单次调用

- upload、estimate：HTTP 200；authorization、planning：HTTP 201；
- Provider calls observed：1；automatic retries：0；
- authorization：`provider_auth_fa49f16d382945ab81304baaaf214d40`，状态 `consumed`；
- plan：`plan_be601d811361b4587b54b6a5`，状态从 `ready` 进入确定性执行后的 `consumed`；
- route：`multi_finding_synthesis`；
- 参数：`time_field=date`、`metric=sales`、`frequency=daily`、`aggregation=sum`、`group=channel`、`analysis_unit=unit_id`、`recommendation_intent=investigate`、`action_risk=medium`、`reversible=true`。

本次授权已经完全耗尽，不可复用。未调用 repair、retry、fallback 或 follow-up Provider。

## 6. 确定性续跑与独立核查

确定性执行和刷新均为 HTTP 200，终态为 `turn_completed` / `finalized`，生成 5 个答案块、2 张图和 2 个 Finding，续跑 Provider calls 为 0。

时间趋势使用 42 个完整日周期，真实范围为 2026-01-01 至 2026-02-11，不完整边界周期为 0。带星期控制的 HAC 趋势、Welch 双组差异、置信区间、p 值和 Hedges g 均与独立复算一致。发布内容明确保留观察性、非因果和非干预效果边界，并把建议限制为低风险、可逆的进一步调查。

因此为 `unified_analysis_entry` 签发本 source digest 上的 `real_provider_analysis_journey` PASS receipt。证据：

- `docs/superpowers/evidence/2026-08-20-v2-5c5q-real-provider-attempt.json`；
- `docs/superpowers/evidence/2026-08-20-v2-5c5q-deterministic-continuation.json`；
- `docs/superpowers/evidence/2026-08-20-v2-5c5q-real-provider-release-receipt.json`。

## 7. 尚未通过的边界

本次没有签发 `human_semantic_review` PASS：当前评审者仍是 implementation agent，同 digest 的真实 Provider 规划没有实际浏览器记录，且稳定性只有一次样本。完整产品矩阵其他场景也没有因此自动获得真实 Provider 或人工语义 PASS。

未宣称 Gate F、release readiness 或产品完成；未授权根入口切换、旧系统删除、push 或 merge。
