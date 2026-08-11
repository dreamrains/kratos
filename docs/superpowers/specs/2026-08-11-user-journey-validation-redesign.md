# Data Agent 真实用户流程验证重设计

日期：2026-08-11  
状态：Proposed  
适用范围：分析运行时、网页会话、证据发布与真实模型验收

## 1. 决策

1. **废止当前 Gate E 作为产品通过证据。** 当前固定字符串 + 人工时序观察只保留为 Web/SSE 传输回归，不再单独证明用户分析流程可用。
2. **重建 Gate E 为一次短、确定性、真实浏览器用户旅程。** 它必须覆盖 session、plan、task、computation、evidence、publication 和 refresh 的同一身份链。
3. **废止当前 Gate F“三次同一合成 CSV 后端直跑”的方案。** 保留真实 provider 的价值，但改成真实文件、不同风险场景、明确 oracle、至少一条完整网页路径。
4. **先快后慢、失败即停。** focused tests → deterministic incident replay → compact Gate E → provider preflight → risk-based Gate F。任何前层失败都不消耗后层 provider 会话。
5. **回执记录用户结果，而不是活动计数。** 工具调用数、答案长度和关键词只能作诊断，不能作为 PASS 的主要条件。
6. **工作台不属于本轮验收边界。** 工作台将另行重构；Gate E/F 不观察、不要求也不修复其 session、证据展示、完整叙述或刷新行为。底层 computation/evidence 契约仍由确定性状态检查验证，但不得借工作台 DOM 充当用户流程 PASS 证据。

## 2. 当前方案为什么会假绿

### 当前 Gate E

- `run_web_sse_fixture.py` 使用固定 `ScriptedProvider`、固定最终答案和 `DelayedAuditedLoop`；
- suspend/resume 使用独立 `_FixtureConfirmationRuntime`，不是产品 canonical confirmation 生命周期；
- 回执只接受“第一段”“第二段”“局限”等固定文本；
- 没有要求 plan/task 存在，没有要求任务从 0/N 到 N/N；
- 没有要求证据绑定 computation identity；
- 没有检查关键数值或用户问题是否得到回答。

因此它适合发现 SSE 缓冲、DOM 渲染、刷新文本丢失，却无法拦住任务 0/4、`analysis_step_not_found` 和 `legacy_unbound`。

### 当前 Gate F

- 三次运行来自同一个生成的 `live_provider_fixture.csv`，只改变少量噪声；
- 直接调用 `AgentLoop`，不走上传控件、网页聊天和刷新；
- confirmation 自动选择“批准/继续”，会掩盖不应出现的确认；
- PASS 主要依赖工具数量、发布长度、中文关键词、至少一个 verified material claim；
- 回执没有 `scenario_id`、文件 digest、prompt digest 和独立 oracle；
- 不检查任务 N/N、孤儿 computation/evidence、关键数值和空结构；
- 固定要求 3 次同类运行，成本高但覆盖面窄。

## 3. 新的验证金字塔

| 层 | 目的 | provider | 浏览器 | 典型时限 | 失败后动作 |
|---|---|---:|---:|---:|---|
| L0 focused | 当前修改的最小 RED/owner tests | 否 | 否 | 1–3 分钟 | 立即修复 |
| L1 incident replay | 真实事故状态机、证据、发布回放 | 否 | 否 | 2–5 分钟 | 不进入 Gate E |
| L2 Web transport | SSE、DOM、error/suspend/interruption 契约 | 否 | 必要时 | 1–3 分钟 | 只定位 Web 传输 |
| Gate E v2 | 一次完整确定性浏览器用户旅程 | 确定性边界 | 是 | ≤5 分钟 | 不调用真实 provider |
| F0 preflight | provider 鉴权/连接和最小响应 | 是，最多 1 次 | 否 | ≤60 秒 | BLOCKED，停止 F |
| Gate F v2 | 风险选择的真实文件用户旅程 | 是 | 至少一个场景必须是 | 每场景 ≤6 分钟 | 首个产品失败即停止剩余场景 |
| Release aggregate | 同一 digest 下的回执聚合和人工语义审查 | 否 | 否 | <1 分钟 | 不得升级状态 |

L2 中原 Gate E 的 suspend、interruption、synthetic error 和多 session 切换保留为自动回归，但不再每次用人工浏览器逐项采集 10 个固定字符串。

## 4. Gate E v2：确定性真实浏览器用户旅程

### 场景

默认只跑一个生命周期 canary：上传一个小型真实 schema fixture，发送明确的描述性问题，确定性 provider 通过正常工具协议创建 plan、运行计算、记录证据并发布已知答案。

不得再通过 wrapper 在完整答案生成后人工分块，也不得使用旁路 confirmation runtime。

### 必须观察的用户结果

1. 上传文件名在当前会话可见；
2. `/api/chat` 建立 session 后，聊天主区在首次任务轮询前绑定该 session；
3. 计划生成后任务总数 `N > 0`，服务端任务历史中同时最多一个 `in_progress`，浏览器只需稳定观察到自然进度提示，不依赖毫秒级 DOM 抽样；
4. 至少一个真实计算产物具有稳定 computation ref；
5. 证据引用有效 plan/step/computation，不是 `legacy_unbound`；
6. 任务单调推进并在终态达到 `N/N`；
7. 最终答案在 `turn_end` 前完整出现，包含 fixture 的两项已知 oracle 数值；
8. 没有内部 marker、`analysis_step_not_found`、generic failure 或空表/空章节；
9. 刷新后恢复同一 session、N/N 和完全相同的聊天答案摘要；
10. 侧栏切换后不存在跨 session 污染。

### 回执

新契约 `analysis_browser_user_journey.v2` 至少记录：

- source digest / commit；
- scenario ID、fixture digest、prompt digest；
- session ID；
- task total/completed/terminal status；
- bound computation/evidence count 与 orphan count；
- oracle assertions；
- answer progress visibility/usefulness/forbidden marker/content digest assertions；
- refresh session/task/evidence persistence 与 answer digest 一致性 assertions；
- elapsed milliseconds与首个失败阶段。

固定可见字符串不再是主 PASS 条件。

## 5. Gate F v2：真实文件、真实问题、风险选择

### 场景库

| scenario_id | 文件 | 主要风险 | 独立 oracle |
|---|---|---|---|
| `retention_descriptive_v1` | `游戏B留存.xlsx` | 否定意图、日期趋势、观察窗截尾 | 62 行；2020-07-01..2020-08-31；末端 6 天 30 日留存为 0 |
| `cross_promo_funnel_v1` | `游戏互推.xlsx` | 漏斗、加权口径、异常计数、证据发布 | 总曝光/点击/确认；内部/外部 CTR 与确认率；59/18/1/19 个质量异常 |
| `card_multifile_paired_v1` | 4 个省钱卡工作簿 | 多文件、去重、用户聚合、完整配对、沙盒回退 | 13,757→13,025；7,206→6,738；62 用户、61 完整配对；Wilcoxon p=0.030894 |

oracle 由独立确定性脚本从 fixture 计算并版本化，禁止从模型答案反向生成。

### 风险选择，而不是固定重复三次

- 小型 Web 文案或纯显示修改：Gate E v2；Gate F 可不跑。
- provider/intent/plan/loop/publication 修改：1 个代表场景，默认 `cross_promo_funnel_v1`。
- task/evidence/recovery/多文件修改：2 个场景，`cross_promo_funnel_v1` + `card_multifile_paired_v1`。
- 发布候选或跨层大改：3 个不同场景，各跑一次。

用户授权必须区分“最多 N 次”和“恰好 N 次”。默认解释为最多 N 次，并执行失败即停；只有用户明确要求“恰好”时才固定运行次数。

### 运行入口

- 发布候选的每个 Gate F 场景必须从正常 Web 上传和聊天入口启动；
- 若需要更快定位，可先运行不计入 PASS 的 F0 provider preflight；
- 后端直跑只能作为 provider semantic diagnostic，不能单独满足 Gate F。

### 每场景的阶段性 fail-fast

1. **上传后 15 秒内**：文件名和 session 建立；否则 FAIL；
2. **计划阶段 60 秒内**：不应出现的 confirmation 立即 FAIL；任务仍为 0 个立即 FAIL；
3. **执行阶段**：`analysis_step_not_found`、孤儿 computation/evidence、任务非单调立即 FAIL；
4. **终态**：必须 N/N、有用答案、关键 oracle 可核验；generic failure 或大面积剥离立即 FAIL；
5. **刷新**：同一 session/version 的任务、证据和聊天答案必须恢复；不检查工作台或无场景依据的图表。

首个产品失败后停止剩余场景并保留诊断目录，除非用户明确要求继续用完授权次数。provider 网络/凭证问题记录为 BLOCKED，不与产品 FAIL 混为同一根因。

### 回执

新契约 `analysis_live_user_journey.v2` 每个 run 必须记录：

- scenario/fixture/prompt/oracle identity；
- entrypoint=`web`；
- provider model 与 session ID；
- expected/observed confirmation；
- plan/task/computation/evidence identity checks；
- exact/tolerance-based oracle checks；
- terminal usefulness和禁止内容；
- refresh/session isolation；
- human semantic review：问题理解、方法强度、结论强度、局限是否改变 claim；
- elapsed time、provider 调用次数和首个失败阶段。

工具次数、答案长度和关键词只保留为诊断字段。

## 6. 执行效率规则

1. 任何源码修改后先跑 owner tests，不重复跑全套 A–D。
2. 共享状态机、evidence、publication 或 Web 合流后，只跑一次 incident replay。
3. 全套 deterministic 和 source digest 只在候选冻结时跑一次。
4. Gate E v2 通过前不申请/消耗 provider 授权。
5. F0 只验证连接，不生成产品 PASS；通过后才开始计费场景。
6. 每个 live 场景实时写阶段结果，失败时不等待完整超时才出诊断。
7. 运行目录保存 manifest、日志、session 状态和回执；报告引用它们，不重复人工抄录长 DOM。
8. 目标：普通修复循环不超过 5 分钟；冻结候选的 deterministic + Gate E 不超过 15 分钟；每个 live 场景不超过 6 分钟。

## 7. 脚本修改顺序

1. 新增 scenario manifest 与独立 oracle runner；先为三个真实 fixture 生成可复算断言。
2. 为 `browser_gate_contract.py` 写 v2 false-green RED tests：0/N、orphan evidence、缺失 oracle、generic failure、refresh session/task/evidence mismatch、answer digest mismatch 均 FAIL；旧 workbench 字段作为越界字段拒绝。
3. 修改 `run_web_sse_fixture.py`：移除 `DelayedAuditedLoop` 的权威证明和旁路 confirmation；确定性 provider 走规范 plan/task/evidence 链。
4. 新建紧凑 Gate E 浏览器执行清单/采集器；只保留一个 lifecycle canary。
5. 为 `live_provider_gate_contract.py` 写 v2 RED tests：必须有不同 scenario identity、Web entrypoint、oracle、N/N、refresh 和人工语义审查。
6. 修改 `replay_analysis_reliability.py`：旧合成 CSV 模式降级为 diagnostic；新增基于 scenario manifest 的真实文件运行器。
7. 修改 `run_analysis_release_gates.py`：接受 v2 receipt；旧 v1 receipt 只能显示 historical，不可满足新产品 PASS。
8. 更新系统恢复计划：把验证重构前移到再次执行真实模型之前；Task 5 当前真实失败必须先修复并通过新 Gate E。

## 8. 当前候选的处理

- Task 5 commit `064ec117fd4b065bab63ef63b957262da96f7f8e` 的真实数据扩展验收为 FAIL；
- 不进入 Task 6，先按真实失败重开 Task 5 停止门；
- 旧 Gate E/F PASS 回执不适用于当前 source digest，也不适用于 v2 方案；
- 在 v2 deterministic user journey 通过前，不再申请真实模型会话。
