# P08 真实 Provider 冻结批次 R1：完整执行与失败分析

记录时点：2026-09-24，M06 在 18:21 CST 获用户精确代选授权后收口。本文件是完整执行但**验收失败**的 E4 记录，**不是** Phase 5 Shadow、Phase 6 D 正式处置或 Phase 7 完成证明。三份原始需求、R7–R21、完整 R16、被中途停止的 R4、本地旧会话及当前 E3 一起构成后续对照；不得以本次单一失败修改词表或扩大总审批门。

## 冻结身份与现场

- 源提交 `b70fbc35e212ed4d5389205d1a3ee9d801e2065f`；启动前工作树无列出的改动。此前定向 26 passed，最终 fresh full-offline `tmp/trust-reset-fo-20260924-contract-r3` 为 2964 passed、1 skipped、16 warnings、0 failures，JUnit SHA256 `ACF02767CD5613CC8AAD6B021CB94DB6D362CCB6BB2DBFB687948311876C4E7F`。
- 零调用 preflight 通过；`tmp/trust-reset-p08-real-20260924-r1/freeze.json` SHA256 `09781503FF21ADC0CCC05E95408A63E89C9994B350B0720CAB6D71150116021F`。模型 `openai/deepseek-flash`、端点 `https://api.deepseek.com`、上限 120、六场景和十份夹具按现有 P08 contract 冻结。用户对此精确修订后批次已授权真实调用；授权不扩展到额外场景、改变冻结身份、局部重跑、push 或部署。
- 既有真实矩阵入口 `scripts/testing/run_p08_real_matrix.py --authorized`，端口 `5228`，隔离 run-dir `tmp/trust-reset-p08-real-20260924-r1`，OS PID `12168`，Codex exec session `67748`；按同一 exec session 中断后 PID 已停止、`/p08-freeze` 不可达，未留下运行中的真实 Provider 服务。全批只用 Codex `iab` 原 tab ID 2，没有改浏览器栈。
- 只用可见上传 label、`filechooser` 和绝对夹具路径。M03 六份一次上传；M04 按用户裁决 v1 首轮前和 v2 首轮终态后、同会话第二轮前分别上传。M04 第二阶段首次 label 点击未弹出 chooser，检查原控件后以同一方法重试成功，未换上传路径。

## 按冻结顺序的已观察结果

| 场景 | 会话 | 当前状态与可复核轨迹 |
| --- | --- | --- |
| M01 | `126c9f6a9d17` | `completed`；正文有 12 条、总额 120、单位未确认及条件建议；刷新保留。仍须按旧历史与具体证据核对解释边界。 |
| M02 | `ffb95bc5a766` | `failed`，两份拒绝候选在 `publication_rejected/`；`[unbound_claim_placeholder]` 指向 `[[claim:C1]]`。候选自报 `unit_status=not_confirmed`，却将原始 `0.55…0.10` 写成 `55%…10%`；不能将宿主阻断当作单位风险已解决。MD 导出只有会话产物，没有成功 publication；刷新保留失败。 |
| M03 | `06a81b4d660c` | `completed`；六来源 10→11 至 60→66、总额 210→231、逐来源记录数与图表在正文/刷新后可见，已执行压缩和 MD 导出。正文另出现与两日范围矛盾的“七天跨度”，并断言六来源“相互独立”；不能因为表格正确就给这些解释授予证据权威。 |
| M04 | `d4776ba7b746` | v1 `failed`：缺 current structured plan 与假设关系；v2 同会话已识别 10/10/10、录入 plan，但仍 `failed`：无 evidence record 的结构化假设关系。刷新保留两轮失败。运行时 quality guard 要求引用已展示的 `<competing_hypotheses>` ID；对话中的 system 消息只含该 guard，未见实际 `<competing_hypotheses>…</competing_hypotheses>` 列表。这是待与 R4 成功链路交叉核对的生产者/消费者疑点，尚非修复裁决。 |
| M05 | `e7a6e6b17ee8` | 六轮均 `completed`，业务负责人/分析师/管理者/大白话/技术表达都保持 12/120、日期范围及单位未知；末稿 MD 已导出，刷新可恢复。部分轮次出现“补一项即可升级可决策级”“退款一条都还没剔”等需逐句核对的过度陈述；不得以 auditor 的数字 token 命中替代语义验收。 |
| M06 | `4656c27b3f5a` | 第一轮 `completed`，准确指出 `missing_orders` 不存在，但在“单一下一步”后又追加了“改为分析 M01-sales”的第二条路径。第二轮产生 `metric_definition` 卡片；预授权解释不足时浏览器动作被拒绝两次，未旁路。用户随后明确授权仅在本会话选 B；原卡片 B 已选，经原按钮提交，**仅恢复一次**并 `completed`。确认快照 `integrity_status=ok`、记录 `resolved`、response 为 B；最终区分 12/120、未计算成本/净收益与证据不足，MD 导出、刷新保留。正文把未定义单位/业务含义的 `amount` 称为“毛收入”，须记为解释风险。 |

最终既有 `provider-calls.jsonl` 为 **82 `started` / 82 `dispatched` / 0 `failed`**，低于冻结上限 120；SHA256 `F99D73E1A998357F06699A26819A93E04FE831F86E74EF54215077D3927EBDE9`。同目录 `scenario_audit.json` SHA256 `2B9DFDB97E4918B87AD38AB1B1BC11360F294561DD018B9EAAFC58309661253B`；既有审计器最终 `verdict=failed`，阻断为 M02 `run_state_completed`/缺 publication 导出和 M04 `run_state_completed`。M02 原始尺度/单位项按修订契约明确为 `unassessed` 非阻断，需要人工核对。其余 M01/M03/M05/M06 的机械项通过，**不等于**下表的人审价值维度通过。各场景工具消息配对分别为 3/3、14/14、18/18、17/17、3/3、4/4。浏览器 console warn/error 为空；未独立取得逐条 SSE terminal 持久轨迹，不能宣称每轮终态事件唯一。

## 双向价值复核：判定器通过不等于事实获权威

| 维度 | 保留的正确价值 | 未闭合/误放或误拒 |
| --- | --- | --- |
| M01 | 12/120、未知金额单位、范围与条件性建议有可见结果 | 行动建议的样例/占位解释须与真实业务来源区分；当前无 typed span，不能把 `completed` 当整篇事实认证。 |
| M02 | 候选正确指出无 D30 直接观测、无留出验证并保留三族敏感性，宿主没有把无效占位符发布出去 | 原始 CSV 是 `0.55…0.10` 且无百分比单位；候选正文却是 `55%…10%`，同时自报 `unit_status=not_confirmed`。末尾只有普通 `json` 代码围栏而非 parser 要求的 `answer-bindings` 围栏；claim ID `C1/C2` 也不满足现行 `claim_…` 协议。两次候选都因无可绑定占位符被拒，正确 D30 边界亦未交付。不能靠改审计器的 `55`/`10` 子串让它通过。 |
| M03 | 六源两日金额、绝对/相对变化、行数、图表、导出和刷新均保留；历史 R4 的六源价值没有在本次正文丢失 | 同一正式正文在正确两日表格之外写“七天跨度”，又把六源说成“相互独立”；目前未见来源独立性证据。脚本 `answer_numeric_oracles` 通过仍漏掉这一事实/解释边界。 |
| M04 | v1 `10→20→20`、v2 `10→10→10` 由真实工具识别，v2 没被提升成 v1 的事实；宿主拒绝无审计结构的发布 | R4 旧会话有 plan 和 4 条带关系形状的 evidence，但其别名 `h_trend/h_level_shift` 与实际持久假设 ID 不同，假设集仍 `inconclusive`、0 支持/反证。此次首次无 plan/关系，二轮有 plan 仍无关系；guard 说 ID 已在 `<competing_hypotheses>` 中展示，而本次传给模型的 system 消息没有实际假设列表。现行完成门只查非空关系提议，不保证关系经宿主验证。不得把 R4 旧“有关系字段”写成真实关系闭合，也不得为避免阻断撤掉显式假设任务的审计要求。 |
| M05 | 六轮 12/120、窗口、未知单位与方法来源总体稳定，完整 R16 的多轮价值方向得到正面再验证 | 某些轮次说“补任一项即可升可决策级”、或“退款一条都还没剔”，超出已证明的数据适用性/退款存在性；先作逐句人工复核，不能单凭高置信 evidence 标签或脚本通过放行。 |
| M06 | 成本范围确认是真业务缺口；B 选择不补成本数据，最终将已计算 120、未计算两项成本/净收益和其他证据缺口分开；确认记录闭合 | 缺失数据集首轮的“单一下一步”又给第二路径；最终 `amount` 未有可信业务口径却称 120 为“毛收入”。这两处在 auditor 中未形成阻断。 |

四个 `completed` 会话的最终 publication packet 均有 `answer_render_trace.v1`，但 `entries=[]`：自然模型成功交付的这些正文**没有**现行 typed claim 原位渲染。M02 尝试 typed 却格式和 ID 均不合法；因此不能把这批 E4 当 Phase 5 Shadow 可审 claim 分母、A 可信核心价值已保留或 D 可默认切换。宿主确定性拒绝无效 M02/M04 是正面保护，但 M03/M05/M06 的自由散文误放与 R11/R16 正确价值损失构成同一双向边界。R4 中断、R16 完整已通过 M05、R7—R21 的错单位/版本/算术和独立无据 99% 仍须同时校准；本批不能独占 oracle。

## 后续最小阶段的 RED、结构化替代与旧门

1. **先做跨历史只读/离线双轨校准，不立即改正式发布**：RED 是 R11/R4 的合法边界误拒、本批 M02 无效 typed 尝试、M03 两日表旁“七天”、M06 单一动作旁第二路径、R16/本批 M05 方法价值与独立 99% 误放。对每份候选记录 `事实/解释/缺口/产物/关系` 的宿主所有者、可重建结果、损失与误放；未有可验证指标身份、单位或用户子问题关系时保持 `unassessed`，不能给模型标签自动 `answered`。结构化替代仍是既有 packet/回执/answer_bindings.v1/默认关闭核心预览；拟退役的是“一条合法 binding 给整篇自由散文授权”，**不是**版本、算术、单位或证据硬门。
2. **单独核对协议生产者/消费者**：M02 的提示说 fenced answer-bindings JSON，但 parser 仅接受固定 `answer-bindings` fence、`claim_…` ID；M04 guard 声称已展示假设 ID，而现行 `hypotheses_prompt_brief` 只列 claim/status，未列 `hypothesis.id`。先以 R4/current 正反重放验证格式/ID/回执/版本/关系如何丢失，再设计最小宿主可核验生产链。不能只在 M02 放宽自由散文、只在 M04 加一个提示词或把关系形状当验证通过。
3. **阶段门不升级**：Phase 5 仍无真实 Shadow 调度与成本/误删校准；Phase 6 A 的价值保留/误放剔除仍不闭合，B 仅离线动作，C/D 仍各有独立门；Phase 7 不开始。另一真实 Provider 批次须在代码/契约修订、E2/E3 和新的精确冻结后再获单独授权。本批授权已用完，不适用于局部重跑、额外审核调用或部署。
