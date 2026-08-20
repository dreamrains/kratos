# Data Agent V2 Slice 5C4C：统一浏览器与刷新收据

- **日期**：2026-08-20
- **状态**：Implemented；待提交
- **基线提交**：`b464415`（`test(v2): validate workbench interaction journey`）
- **分支**：`codex/data-agent-v2`

## 1. 目标

把 5C4A 的 planning 观察与 5C4B 的 interaction 观察组合成发布矩阵可读取的两张独立收据：

- `browser_interaction_journey`
- `refresh_persistence_journey`

组合只收窄和计算已有观察，不允许把任一子旅程缺失、过期或失败的状态改写为 PASS。

## 2. 审计发现与修正

### 2.1 原子旅程使用了错误的数据夹具

发布矩阵把 `unified_analysis_entry` 绑定到：

```text
tests/fixtures/v2_slice4d_combined.csv
```

5C4A/5C4B 的实际浏览器观察此前使用 `v2_slice1_sales.csv`。只按场景名组合会得到夹具错误的伪证据。

本切片把 provider-neutral fixture 和两个原始收据都绑定到矩阵指定的 combined 数据；validator 对 `fixture_path` fail closed。

### 2.2 规划旅程没有验证图表

统一场景的图表策略为 conditional。原确定性 Planner 只执行描述分析，不能证明多 Finding 的正文图表邻接。

第三次显式规划现在路由到 `multi_finding_synthesis`，使用日期、销售、渠道和分析单位。实际浏览器观察到 4 个答案块和 2 张正文内嵌图表；planning receipt 必须声明 `chart_observation=rendered` 且 `chart_count>0`。

### 2.3 完成后无法从页面复核长回答

分析完成后规划输入区会被收起，旧收据只能自行声明回答未截断。验收 fixture 现在从 append-only PlanningInputStore 读取持久化事实，只返回每条回答的字符数和 SHA-256，不返回正文。

实际旅程保存了 12480 个字符；写入前与刷新后的持久化摘要均为：

```text
sha256:e1f75e1c5952019d204e0a3adc08315f5c4019396d28e293bf05d12a281c02f3
```

## 3. 组合不变量

组合器只有在以下条件全部满足时才生成收据：

- planning 与 interaction 均为 `actual_browser`；
- 两者绑定同一当前 source digest；
- 两者绑定矩阵指定的 combined fixture；
- planning 精确满足 0/1/2/3 次显式规划与授权序列；
- interaction 覆盖运行中草稿、排队转向、停止、错误恢复、会话隔离和刷新恢复；
- planning 实际观察到正文内嵌图表；
- 两个子旅程交互并集覆盖矩阵的全部 required interactions；
- Provider 调用为 0，console error 为空。

证据引用是两个原始 JSON 的规范化 SHA-256。组合结果不会声明 release readiness，也不会授权根入口切换。

## 4. 当前源码实际浏览器结果

绑定摘要：

```text
sha256:97f5ea43aaaf39aee1aa14d78e1455aa6e5b7420826053845abc341c713dd837
```

规划旅程：

- `loaded/estimated`：0 次 Planner、0 个授权；
- `needs_input/answer_estimated`：1 次 Planner、1 个授权；
- `failed/failure_stable/retry_estimated`：2 次 Planner、2 个授权，无自动重试；
- `completed/refreshed`：3 次 Planner、3 个授权；
- 12480 字符回答摘要一致；
- 4 个答案块、2 张内嵌图表，刷新后内容和 URL 身份一致。

交互旅程使用三个隔离 session：

- stop：`v2_665fac007bbc`，中断后 0 blocks，刷新仍为 interrupted；
- steer：`v2_dd14d896aa32`，同 session 从 source turn 进入新 target turn，两者均 finalized；
- error recovery：`v2_9787d26a31a0`，失败后同 session 新 turn 成功并可刷新恢复。

真实 Provider 调用为 0，浏览器 console error 为空。

## 5. 收据与准备度边界

持久化证据：

- `docs/superpowers/evidence/2026-08-20-v2-5c4c-planning-browser.json`
- `docs/superpowers/evidence/2026-08-20-v2-5c4c-interaction-browser.json`
- `docs/superpowers/evidence/2026-08-20-v2-5c4c-unified-release-receipts.json`

两张组合收据均为当前摘要 PASS，且无 stale、conflict 或 incomplete。但完整矩阵仍有 61 个 requirement missing；当前状态仍是：

```text
not_ready
provider_calls = 0
root_switch_authorized = false
```

因此不能切换 `/`，也不能把本切片称为产品完成。

## 6. 下一步

先为统一入口补齐当前源码绑定的 `owner_contract`、`incident_replay` 和 `sse_transport_contract` 收据，避免在确定性层仍缺证据时提前消耗真实 Provider。

之后才进入 `real_provider_analysis_journey`。每个真实调用仍必须由用户另行给出精确次数授权；完成后还需要独立 `human_semantic_review`，根入口切换继续作为单独人工决策。
