# 需求对齐与必要澄清：诊断依据及评估裁决

日期：2026-09-07｜性质：**只读源码/会话核对与离线模拟，不是修复或产品验收**。

关联：[实施计划](../superpowers/plans/2026-09-07-intent-clarification-plan.md)｜[规划基线](2026-09-07-intent-clarification-planning-baseline.json)。规划 HEAD 为 `86f55af05b053d42b1e9fd5f10c95e1545109cc4`；跨分支必须重新核查，原会话未保存的运行细节不能由当前源码推定。

文档编写中另有工作修改 context/loop/registry/执行控制测试；本文源码机制以规划 HEAD 为定位依据，基线同时保留 dirty 快照，不能把并发改动归属为本专题的实现或验证。

## 1. 真实会话事实

| 会话 | 原始任务摘要 | 首次确认 spec |
|---|---|---|
| `9810fe7bacf6` | 游戏平台省钱卡功能对用户付费行为的影响：最终收益、复购率、购买偏好、付费频次、付费 ARPU、人均/日均/单次付费金额、金额区间分布；连续付费是否因省钱卡刺激而提升；说明计算方式并补充分析方向 | `spec_253dfdb81151` |
| `9959216b6a4a` | “这是一个游戏的新用户留存率数据，请根据数据为我拟合留存率的公式”，附件游戏B留存.xlsx | `spec_6a90daed83fe` |

两次首次确认文字相同：“当前问题适合按「Retention & Lifecycle」方法继续。请确认是否使用这个方法计划，或先补充目标口径、时间窗口和比较对象？”选项为“按此方法继续 / 先补充目标口径”。

两次 durable record 均为 `source=pending_confirmation`、`operation=method_confirmation`、`data_version=messages:2`，其来源 state 项为 `source=method_playbook`。两份保存的 conversation 中均没有 `ask_user_question` tool call。两次用户都选择 `confirm_method`，记录随后 resolved。

只读证据位置（本地可能被 Git 忽略，新分支不保证具备）：

- `sessions/9810fe7bacf6/{conversation.json,analysis_state.json,confirmations/snapshot.json,confirmations/events.jsonl}`。
- `sessions/9959216b6a4a/{conversation.json,analysis_state.json,confirmations/snapshot.json,confirmations/events.jsonl}`。
- 证据字节哈希和是否被 Git 跟踪见规划基线；本提交不搬运会话、上传文件、模型内部推理或个人数据。

“已确认的主方法”是省钱卡会话中回答确认后的 assistant 表述；首次问题本身没有“已确认”措辞。当前证据不支持跨会话确认串用。

附件在首次暂停前已加载并生成画像、契约和路线。准确描述是“主体分析前被通用模板阻塞”，不能说系统此时完全未见数据。

## 2. 现有代码依据

| 事实 | 符号/定位 |
|---|---|
| 非平凡输入先调用 LLM；无有效 primary 才回退规则 | [method_playbooks.select_playbooks](../../src/data_agent/agent/method_playbooks.py:410) |
| 空 LLM supporting 会触发规则补充，即使 primary 是 LLM 成功返回 | [supporting 分支](../../src/data_agent/agent/method_playbooks.py:450) |
| 回退高置信规则含“复购/留存”，先于盈利和功能/效果规则 | [回退规则](../../src/data_agent/agent/method_playbooks.py:560) |
| 留存模板顶层 requires_confirmation 固定为 true，理由为预测性留存/流失建模 | [模板](../../src/data_agent/agent/method_playbooks.py:237) |
| 四个模板要求确认：retention_lifecycle、evaluation_causal、effect_evaluation、forecast_decision_simulation | 同文件 PLAYBOOKS 定义 |
| 选中方法且有 spec、无同 ID 条目就写待确认项，问题为固定模板 | [apply_selection_to_state](../../src/data_agent/agent/method_playbooks.py:487) |
| spec ID 包含 goal 等内容的哈希；仅排除 id/created_at/workflow_id | [spec ID](../../src/data_agent/agent/method_playbooks.py:751) |
| pending 优先于新 question_need，由 loop 自动悬挂 | [自动暂停](../../src/data_agent/agent/loop.py:1010) |
| Web 流式入口 prepare 后可直接发 suspended，无需先经过主体模型工具调用 | [流式入口](../../src/data_agent/agent/loop.py:2501) |
| 检测器包含六类条件，咨询等意图跳过 | [question_need_detector](../../src/data_agent/agent/question_need_detector.py:73) |
| 四类能力封锁读取顶层 spec confirmation_policy | [能力门控](../../src/data_agent/agent/analysis_flow_controller.py:83) |
| 直接工具的提示说明及统一 UserConfirmationRequired | [interaction](../../src/data_agent/tools/interaction.py:299) |
| runtime 默认绑定 agent_turn；服务策略非阻塞可能不产生 record | [runtime](../../src/data_agent/agent/confirmation/runtime.py:112)、[service](../../src/data_agent/agent/confirmation/service.py:97) |
| loop 当前对不存在 record 的策略结果抛异常，降级接入须一起改 | [直接请求](../../src/data_agent/agent/loop.py:1771) |
| 决定复用目前检查 decision_key、data_version、spec_version | [policy](../../src/data_agent/agent/confirmation/policy.py:83) |

行号只是规划 HEAD 的导航，目标分支优先按函数名复核。步骤中已有 `confirmation_policy` 只证明存在元数据，不证明已经具备完整逐步骤暂停/恢复；legacy spec 的工作流投影还受到契约版本限制。

## 3. 两组离线模拟与推断边界

诊断阶段用真实 `select_playbooks`、`apply_selection_to_state` 和两个原始首条请求，只替换 `select_playbook_llm`；状态在内存，不执行 controller.save、真实 transport 或会话恢复。

| 模拟条件 | 9810 输出 | 9959 输出 |
|---|---|---|
| LLM 返回 None，实际关键词回退 | retention_lifecycle；supporting=metric_overview/revenue_profitability/user_behavior_analysis；spec_253dfdb81151 | retention_lifecycle；supporting=metric_overview；spec_6a90daed83fe |
| LLM 成功返回 retention_lifecycle、supporting=[]，实际规则补充辅助方法 | 同上，LLM 选择器调用一次 | 同上，LLM 选择器调用一次 |

两条路径均能复现相同 spec ID、问题和理由。因此结果与规则相符，只证明规则足以解释现象，不能证明历史上 LLM 未调用、失败或超时。八秒辅助超时和选择器返回 None/吞异常使诊断信息不足，应新增原因记录；本轮没有以真实调用测量超时概率。

这些是诊断模拟，不是新实现的测试报告；CI 应在目标分支转为隔离合成夹具重新运行，不能复用本文文字作为通过证据。

## 4. GLM 分析的采纳与修正

| 判断/建议 | 评估裁决 |
|---|---|
| 模板确认过粗、文案没有数据上下文 | 采纳，有直接代码和会话证据 |
| 省钱卡整体目标被局部复购指标缩窄 | 采纳为计划适配问题；并不等于复购方法与任务完全无关 |
| 两个会话必然由关键词决定，连 LLM 都未询问 | 不采纳；忽略外层 LLM 优先，且成功空 supporting 是反例 |
| 超时导致回退 | 仅列可能原因，未证实历史失败类型 |
| 换措辞会产生新 spec，存在重复确认隐患 | 采纳机制风险；是否实际弹出还取决于意图分类/重建/暂停路径 |
| 只在高风险建模步骤前确认 | 不直接采纳；方法计算本身不该审批，真正业务未知才需澄清 |
| 长文本改用 LLM 优先 | 当前已经如此；应改善目标理解、回退和日志，不重复增加调用 |
| 同会话同 playbook 永久免确认 | 不采纳；相关指标/分母/时间/数据改变时旧答案不能覆盖 |
| skippable 与阻塞互相矛盾 | 不成立；允许主动 skip 与等待回答可同时存在，skip 恢复效果需验证 |
| 游戏语料抽样导致几乎总是留存 | 合理假设，但两例不能证明统计频率 |
| 完全符合代码所以不是 bug | 属于可复现策略/需求实现缺陷；命名不影响应修复的行为 |

依据 [8 月架构原则](../superpowers/specs/2026-08-23-route-a-top-architecture-design.md) 与 [能力清单 CAP-AGENT-03](2026-08-25-capability-preservation-ledger.md)，方法许可应收窄为用户独占的业务语义选择。9 月其他专项对真实歧义、数据范围和可信结论的保护继续适用，不据此放宽发布等级。

## 5. 待实施验证与非结论

尚未完成新策略、运行时降级、决定复用、迁移、计划覆盖或日志改造；尚未运行本专题产品回归/浏览器/真实 Provider。没有诊断结论证明原始分析的全部数值正确，也没有全量生产统计证明发生率。

实施时独立验证：所有入口是否一致、语义问题是否仍能正确暂停、无效通用问题是否返回正常工具结果、旧记录迁移是否幂等、取消审批后因果/外推/跨数据范围是否仍受约束。
