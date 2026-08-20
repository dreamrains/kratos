# Data Agent V2 Slice 5C5Q：时间边界修复后的真实 Provider 预检

- **日期**：2026-08-20
- **状态**：离线预检 PASS，等待新 digest 的精确次数授权
- **基线提交**：`fec3e701a5081cd18a884af534c53529a5038775`
- **source digest**：`sha256:4d0895b17d6f5a62b0a8fd470ecb8d8b0efd3067495b538f86d0e15581906c93`
- **本切片 Provider calls**：0

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
