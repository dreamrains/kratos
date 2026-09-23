# 中文数据分析 Agent 可信发布架构重置：Phase 0 证据复核与实施交接

日期：2026-09-23
状态：Phase 0 completed；Phase 1 canonical history completed_local，等待提交；Phase 2 未开始
仓库：`D:\Project\Daily\data-agent`
本次核验 HEAD：`main@5176c41103ee1b1c77b4b44331d8225fb49890be`

## 1. 文档用途与授权边界

本文件是对
`docs/superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md`
的 Phase 0 证据复核，不是产品实现记录。后续上下文压缩后，应先读仓库根目录
`AGENTS.md`、可信重置计划、三份上位计划和本文件，再以实际仓库状态重新核验。

本轮已完成：

- 完整阅读 `AGENTS.md`；
- 完整阅读可信重置计划；
- 完整阅读三份上位计划：分析价值保留、意图澄清、回答内容优化；
- 复核所有 Git worktree、根工作树 HEAD/索引/dirty/untracked；
- 复核 R4 freeze、Provider 账本、会话、被拒候选、压缩 transcript、持久化状态；
- 复核当前发布门、压缩路径和相关现有测试；
- 只新增本审计文档，未修改产品代码或测试。

本轮没有授权，也没有执行：

- 真实 Provider 调用；
- 新浏览器矩阵；
- 产品代码或测试修改；
- 对既有未提交文件的覆盖、删除或暂存；
- push、部署、staging 或 production 操作。

## 2. 当前确切 Git 状态

### 2.1 根工作树

- 实际工作树：`D:/Project/Daily/data-agent`
- 分支：`main`
- HEAD：`5176c41103ee1b1c77b4b44331d8225fb49890be`
- 本地跟踪引用：`origin/main@be5ee9ac6305c15aec20f9981bf4f3ed25701fa5`
- 相对本地 `origin/main`：ahead 42、behind 0
- 本轮未执行 fetch；因此 `origin/main` 只代表本机现有远端跟踪引用，不声称远端服务器当前仍在该提交。
- 已跟踪工作树和索引均无改动。
- `git status` 报告 3 个未跟踪文件：
  - `docs/superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md`
  - `docs/superpowers/plans/2026-09-22-trust-architecture-restructure.md`
  - `tests/test_p08_trust_restructure.py`
- `git status` 同时报告无法读取 `.pytest_cache/`。因此不能把该目录内部状态纳入完整未跟踪文件断言；本轮未触碰该目录。

可信重置计划写作时只列出后两个既有未提交文件。现在计划自身也处于未跟踪状态，这是已确认的状态漂移。三个文件均保持原样。

### 2.2 其他 worktree

| worktree | HEAD / branch | 状态 |
|---|---|---|
| 根工作树 | `main@5176c41` | 3 个未跟踪文件；已跟踪文件和索引干净 |
| `.worktrees/ai9` | `codex/answer-intent-local-acceptance-20260909@9e51b81` | 干净 |
| `.worktrees/analysis-reliability` | `codex/analysis-reliability@9d419fe` | 干净 |
| `.worktrees/analysis-runtime-recovery` | `codex/analysis-runtime-recovery@d47f5d7` | 大量既有未跟踪 `artifacts/` 产物 |
| `.worktrees/answer-content-optimization` | `codex/answer-content-optimization@bd42678` | 干净 |
| `.worktrees/answer-intent-integration` | `codex/answer-intent-integration@0eb3111` | 2 个已跟踪文档修改和 1 个未跟踪审计文档 |
| `.worktrees/main` | detached `be5ee9a` | 干净；不是当前 `main` 分支所有者 |
| `.worktrees/test-suite-reset` | `codex/test-suite-reset@36bca25` | 相对其 upstream behind 63；干净 |
| `.worktrees/v2-rebuild` | `codex/v2-rebuild@1d57061` | 干净 |

后续不得因目录名 `.worktrees/main` 误把 detached `be5ee9a` 当作实际 main。当前 `main` 由根工作树持有。其他 worktree 的 dirty/untracked 内容均不属于本任务，不得清理或夹带。

## 3. 历史代码形态复核

可信重置计划的下列量化事实仍成立：

- `d41d242` 修改 23 个文件，新增 1248 行、删除 59 行；修改面横跨
  `context.py`、`loop.py`、`publication_synthesis.py`、LLM client、task manager、
  upload、SSE、Web 和多组测试。
- 当前 `src/data_agent/agent/publication_synthesis.py` 为 2136 行。
- 该文件当前有 43 处 `re.compile`。
- `tmp/p08-p16-fixloop-full-offline-1/junit.xml` 仍在，记录
  `2812 tests / 0 errors / 0 failures / 1 skipped`，运行时长 235.313 秒。

边界不变：这份 full-offline 收据只证明当时 checkout 的离线回归，不证明 R4 自然模型路径、当前新设计、staging、production 或部署。

## 4. R4 冻结身份与账本

目录：`tmp/p08-glm-operator-20260922-r4`

### 4.1 冻结身份

- source commit：`5176c41103ee1b1c77b4b44331d8225fb49890be`
- model：`openai/deepseek-flash`
- endpoint：`https://api.deepseek.com`
- call cap：90
- matrix：M01—M06
- freeze SHA-256：
  `FC3F4B7312FDDDB1F6657CBC96B86F72E80FBB668D584E357FD24D772FB5BFE4`
- Provider ledger SHA-256：
  `3FC978A7A39FB4FBD87771DBC26730832855841E589A14C8004FB23BC87F9728`

### 4.2 账本与停止边界

- `provider-calls.jsonl`：82 started / 82 dispatched。
- 调用号：1—82，started 和 dispatched 均各 82 个唯一编号。
- 账本没有 failed/denied 事件；最后事件是 call 82 dispatched。
- 剩余冻结额度为 8，但批次由用户停止，不能继续使用，也不能转授给后续批次。
- R4 目录共 313 个文件，约 2.70 MB；最晚文件更新时间为 2026-09-22 13:29:43（Asia/Shanghai）。

R4 不是完整 M01—M06 验收，也不能报告成完整 M05。M06 没有会话目录。

## 5. R4 会话与真实轨迹复核

### 5.1 会话映射

| 场景/尝试 | session | 终态 | 复核结论 |
|---|---|---|---|
| M01 | `5df75d57da84` | completed | 发生了不必要的数据性质确认；用户选择 B 后完成 |
| M02 误启动 | `3c363c4ae13f` | cancelled | 用户提示被重复拼接成 312 字符后取消；计划此前未记录这次额外尝试 |
| M02 正式轨迹 | `c3f4c190384c` | failed | 两版正确候选均被 `unbound_time_point_claim` 拒绝 |
| M03 | `50e734df7af7` | completed | 正文/导出保留六来源；压缩摘要失实 |
| M04 | `f2db8a75de3d` | completed | 结构化计划、4 条 evidence、2 组 hypotheses 和两轮发布产物存在 |
| M05 前三轮 | `10218e074850` | completed | 仅执行初稿、业务负责人、分析师三轮；12/120、范围、未知单位保持 |
| M06 | 无 | not started | 未执行 |

`3c363c4ae13f` 是重要的批次完整性补充：它说明 R4 不只是“在 M05 中途停止”，还存在一次被取消的 M02 误启动。由于正式 M02 后续在新会话重做，R4 更不应作为严格遵守“一场景一新会话且不局部重跑”的完整验收批次。它仍可作为真实失败轨迹来源。

### 5.2 M01：确认误挂起成立

session：`5df75d57da84`

确认问题为：

> 数据中 channel 全部为 "all"、amount 全部为 10（零方差）。这属于哪种情况？

选项包括：

- A. 占位/演示数据
- B. 真实值，就是常量
- C. 取数有误

确认记录的 `decision_kind` 为 `field_semantics`，`confirmation_type` 为
`data_quality_confirmation`，状态最终为 resolved，用户选择 B。

结论：计划对“数据性质问题不应挂起”的事实判断成立。不得通过新增
`真实值|真实业务值` 等词表修补；正确替代物是结构化 confirmation kind / business gap 判定。

### 5.3 M02：正确内容被散文门删除成立

session：`c3f4c190384c`

持久化回执支持：

- D1—D7：55%、42%、31%、24%、18%、13%、10%；
- exponential：`a=0.73892193`、`b=-0.28583215`、`R²=0.99946726`；
- logarithmic：`a=0.56522015`、`b=-0.23771293`、`R²=0.99519237`；
- power：`a=0.67600697`、`b=-0.86571711`、`R²=0.85626503`；
- D30 情景复算：exponential 0.00014、logarithmic -0.24329、power 0.03558；
- 未做留出验证、回测或外部验证，工具 claim ceiling 为 descriptive。

两份 `publication_rejected/` 候选都清楚区分观测、拟合情景和预测，也报告族、参数、R²、验证缺口和敏感性。第二份还明确逐族绑定 D30 数值。最终仍因同句提到“对数族因负值不适用于外推”而触发
`unbound_time_point_claim`。

结论：计划对 M02 事实判断成立。第一结构化替代物必须是 claim/quantity/receipt 绑定和宿主渲染，不是放宽一个正则或补一个范围标记词。

### 5.4 M03：症状成立，但计划所写根因不成立

session：`50e734df7af7`

已证实：

- 压缩前 transcript 有 27 条消息；
- 压缩后 `conversation.json` 有 28 条消息；
- 压缩后第 1 条是失实摘要，第 2 条是合成 ACK，之后保留 26 条 recent 消息；
- 因此可反推本次 `early` 只有 1 条，即原始用户请求；
- 失实摘要确实写了“尚无助手分析输出”；
- 最终六来源回答仍在 recent 中，conversation Markdown 与 publication receipt 双产物均存在。

`compact_history()` 在写 transcript 后才计算 split；该 transcript 与传入的同一份
`messages` 产生。因此 R4 直接证明：压缩入口当时拿到了完整 27 条内存历史。失实摘要的直接原因是
`_find_safe_boundary()` 在长工具链上把分割点退到 1，摘要模型只看到了第一条用户消息；确定性 execution ledger 也只从 `early` 提取，所以为空。

未证实：R4 不能证明“loop 内存历史少于持久历史”是本次事故根因。

计划仍可保留“持久历史是 canonical、内存只是带 revision 的缓存”作为目标架构，因为当前代码确实有
`loop.messages`、`conversation.json`、`conversation.jsonl` 和 transcript 多个载体，且没有 history revision/hash。只是 Phase 1 RED 必须基于已观察的错误分割与摘要矛盾，不能伪称已复现内存/持久层分裂。

### 5.5 M04：结构化路径成功成立

session：`f2db8a75de3d`

当前持久化状态包含：

- 1 个活动 analysis plan；
- 4 条 evidence records（v1 两条、v2 两条）；
- 2 组 hypothesis sets（v1/v2 各一组）；
- 22 个 tool receipts；
- 2 个 publication packets。

v1 记录 10→20→20，v2 记录 10→10→10；v2 evidence 明确反驳 v1 的上升趋势和台阶跃迁。计划关于“结构化状态和宿主维护可工作”的判断成立，但不应把一次成功扩大为所有 claim 类型已收敛。

### 5.6 M05/M06 边界成立

M05 session `10218e074850` 只执行了 6 个冻结表达轮次中的前三轮：

1. 证据受限事实摘要；
2. 业务负责人表达；
3. 分析师表达。

三轮都保留 12 条、amount 合计 120、2026-09-01 至 2026-09-12、单位未知及证据限制。它不是完整 M05。

M06 未执行。不得推断 missing dataset、业务口径确认、not_computed/evidence_insufficient、SSE 终态等 R4 结果。

## 6. 当前发布门清单与行为

`validate_final_narrative_issues()` 当前串行执行以下检查：

| 检查族 | 当前依据 | 当前行为 | 已知问题/后续所有者 |
|---|---|---|---|
| empty/tool markup | 空文本、未执行工具标记 | hard block | 保留为封闭类 |
| curve interpretation | 中文/英文语义正则 | hard block | 开放语义；未来由 typed claim + semantic audit 接管 |
| extrapolation | 时间点、族名、百分比、表格和回执参数混合解析 | hard block | M02 误拒；Phase 2 claim/renderer 垂直切片替代 |
| significance | 显著性措辞和检验回执正则 | hard block | 不能简单删除；需 claim validation status / audit 替代后退役 |
| currency unit | 金额 token 和 unit scope | hard block | 应由结构化 quantity/unit + 宿主紧邻渲染替代 |
| future window | 日期/未来方向措辞 | hard block | 开放语义；结构化 horizon/claim type 后退役 |
| period label | “同比”等词面与 compare_periods | nominal revision-only | 代码只为 provenance 设置 second-pass flag；仅同比触发时并未完整兑现 revision-only 设计，需修正文档或实现 |
| arithmetic | 可解析算术 | hard block | 保留封闭类，但必须明确覆盖范围和 unknown |
| data provenance semantics | 来源/样例/真实等词表 | revision-only after one rewrite | M01 证明词表分类不可作为确认依据；宿主 provenance status 替代 |
| missing→zero | “后者为零”等词面 | hard block | 真实风险，但必须迁移到 typed gap/quantity state 后才能退役 |
| answer bindings numeric | answer-bindings ↔ derived evidence | hard block | 保留并演进为 claim/quantity 封闭校验 |
| answer coverage | label 在正文附近的词法搜索 | hard block | 迁移为 requirement → answered claim / typed gap 映射 |

`_REVISION_ONLY_CODES` 当前只有
`unsupported_data_origin_inference` 和 `unsupported_yoy_label`。但
`_turn_origin_revision_issued` 只在错误文本包含
`unsupported_data_origin_inference` 时置位；因此“同比”单独命中时并不自然获得计划宣称的第二次放行路径。这是新的实现/文档不一致，不能在后续验收中默认为已解决。

## 7. 既有未提交设计与测试的处置

以下文件保持原样、未暂存：

- `docs/superpowers/plans/2026-09-22-trust-architecture-restructure.md`
- `tests/test_p08_trust_restructure.py`

它们可作为历史分析素材，但不能直接实施，原因包括：

1. 明确提出给数据性质词表补 `真实值|真实业务值`，违反本轮“确认类型化、不得补词”的约束；
2. 测试要求“差异不显著”“缺失成本为零”“未来将持续上升”等正文错误不再触发旧门，却只用末尾宿主附录兜底；这会允许正文与附录自相矛盾；
3. 一次性退役六个散文门，尚未逐项建立 claim/renderer/typed gap/audit 的结构化替代物；
4. `_scenario_family_values` 局部放宽仍是对散文布局的修补，不是 M02 claim/renderer 垂直切片。

后续实施不得修改这两个文件来“变绿”，也不得把它们加入测试收集或提交。若用户未来决定废弃，应另行明确授权；本任务目前只隔离其设计影响。

## 8. 可信重置计划需要修订之处

### 8.1 必须修订

1. 未提交文件从 2 个改为 3 个，并把可信重置计划自身列入保护范围。
2. M03 根因从“已证实内存历史与持久历史分裂”改为：
   - 已证实的直接原因：安全分割点退到 1，摘要输入只有用户请求；
   - 架构风险：内存/JSON/JSONL/transcript 缺少统一 revision/hash，但尚未由 R4 证明是事故根因。
3. R4 会话清单补记取消的 M02 误启动 `3c363c4ae13f` 和重复提示，明确 R4 不是严格完整批次。
4. R4 账本补记 82/82、call 1—82、cap 90 和停止边界。
5. 当前门清单补记 `unsupported_yoy_label` 的 revision-only 声明与 loop flag 不一致。
6. Phase 1 验收不得只检查“摘要含 execution ledger”；本次 early 没有工具调用，所以 ledger 为空且无法防止失实摘要。必须验证 split、canonical snapshot、revision 和最终执行结果的一致性。

### 8.2 保持不变

- 顺序保持：canonical history → M02 claim/renderer → 确认类型化 → 宿主 journal → LLM audit Shadow。
- 不补自然语言关键词。
- 不用末尾免责声明抵消正文错误。
- 不新增 planner、浏览器框架、重复账本或隐藏 Provider 调用。
- LLM audit 只能受 claim/evidence 约束，不能成为随机总审批门。
- 每个旧门必须在结构化替代物生效并有回放证据后逐族退役。
- 真实 Provider 必须新冻结并取得新的显式授权。

## 9. Phase 1：canonical history 最小实现边界

Phase 1 只修会话历史与压缩一致性，不触碰 M02 发布语义、确认分类、planner/task、LLM audit 或浏览器框架。

### 9.1 进入实施前必须先展示的三件事

| 项目 | Phase 1 内容 |
|---|---|
| RED 真实轨迹 | R4 M03：27 条 transcript → split early=1 → 摘要声称无助手输出；最终回答和工具轨迹其实存在 |
| 结构化替代物 | `CanonicalHistorySnapshot`（逻辑名称，可映射到现有 history 模块）：messages、revision、content hash、message count；compact 的 input revision/hash 和 write-back CAS |
| 将退役的旧行为 | `/api/compact` 直接把可变 `agent_loop.messages` 交给 compactor 并无条件覆写；仅靠 message count 的 merge protection；仅从 early 构造 execution ledger |

### 9.2 最小代码所有权

允许修改面仅限：

- `src/data_agent/session/history.py`
- `src/data_agent/agent/compact.py`
- `src/data_agent/web/blueprints/commands.py`
- `src/data_agent/web/blueprints/sessions.py` 中只修改 rewind 的 canonical read/CAS 显式截断路径；
- 如确有必要，`src/data_agent/web/agent_manager.py` 中只做 cache revision 同步；不得扩展生命周期设计。
- 对应现有测试文件或一个聚焦的 Phase 1 测试文件；不得新增测试框架。

明确不在 Phase 1：

- `publication_synthesis.py` 的散文门；
- claim schema 和 M02 renderer；
- confirmation policy；
- task manager/planner；
- LLM semantic audit；
- SSE/UI 新功能；
- Provider 调用。

### 9.3 最小行为契约

1. 持久化 conversation 是 canonical source；JSON + JSONL 必须通过一个读取入口形成确定性快照。
2. 快照至少带 `revision`、`sha256` 和 `message_count`；revision 的生成/持久化方式必须复用现有 session 元数据或最小扩展，不另建账本。
3. Web compact 开始时读取 canonical snapshot，不以 manager cache 是否“看起来更长”决定事实。
4. compact transcript、summary input 和 write-back 都引用同一 input revision/hash。
5. `_find_safe_boundary` 不得把“已完成工具轮的最终回答”留在 recent、同时把摘要输入退化为只有用户请求；需要以完整 turn/reply group 为边界。
6. execution ledger 从 canonical snapshot 的完整被替换区构建；如果摘要保留 recent 的最终回答，摘要不得宣称不存在助手输出或执行结果。
7. 写回前再次读取 revision；不一致则放弃 compaction，不修改 canonical conversation，不覆盖新消息。
8. compaction 失败保留原 conversation、reply identity、publication binding、导出与 transcript。
9. 刷新、公开投影和导出继续从同一持久化事实源读取；合成 ACK 仍不进入公开回复。
10. 不改变 rewind 的显式截断语义；rewind 应使用明确的 authorized truncation 路径而非绕过新不变量。

### 9.4 Phase 1 RED 与回归测试清单

优先新增/扩展现有 pytest，不引入新 runner：

#### A. R4 真实轨迹回放

- 用 R4 M03 的最小化消息形状复现 27 条长工具链；断言旧边界会得到 `early=1`。
- 修复后断言 summary input 包含已完成工具轮及最终执行结果，或整轮被保留在 recent，二者不能分裂成失实状态。
- 断言摘要不得包含“尚无助手分析输出/未包含执行结果”等与 canonical snapshot 矛盾的结论。
- 断言六来源数值、工具调用和最终回答在 compact 后仍可恢复。

#### B. canonical snapshot / CAS

- JSON + JSONL 合并顺序稳定，重复读取 revision/hash 一致。
- 新消息追加后 revision/hash 必须变化。
- compact 读取后、写回前插入并发新消息；CAS 失败，原历史和新消息均保留。
- cache revision 落后于 disk 时，从 disk 重载；不得以长度比例 heuristic 覆盖。
- 相同长度但内容不同必须由 hash 检出，不能仅比 message count。

#### C. 工具轮和边界

- assistant tool_calls 与全部 tool results 不被分拆。
- 连续多工具块、失败工具、修复工具和最终 assistant reply 构成完整 turn。
- keep_recent 目标不能迫使边界退到只剩用户请求；可保留更多 recent，而不是生成失实摘要。
- transcript 记录 input revision/hash/message_count 和实际 split index。

#### D. 持久化与公开投影

- conversation 保存、刷新和 export conversation 使用同一 canonical revision。
- publication receipt 与 conversation Markdown 双产物仍存在。
- compaction ACK 不窃取 reply id，不进入公开消息或导出。
- publication packet id、snapshot digest、answer SHA 和 detail refs round-trip 保持。
- 旧会话无 revision 字段时可读；首次安全写入时升级，不批量改写历史会话。

#### E. 失败与恢复

- summary LLM 失败、空响应或失实两次时，确定性兜底不破坏 history。
- transcript 写失败时不做有损 compaction。
- canonical write 失败时不替换内存 cache。
- revision 冲突返回可恢复结果，不产生重复 terminal event。
- rewind 仍能显式截断并产生新的 revision。

### 9.5 Phase 1 建议定向测试集合

实现后至少运行：

- 新增的 canonical-history / R4-M03 replay 测试；
- `tests/test_compact_preservation.py`；
- `tests/test_p08_compaction_ack_projection.py`；
- `tests/test_answer_publication_contract.py` 中 compaction/reply binding 用例；
- `tests/test_export_conversation.py`；
- `tests/test_export_projection_roundtrip.py`；
- `tests/test_comprehensive_analysis_flow.py` 中 history merge protection；
- `tests/test_pipeline_comprehensive.py` 中 compact history；
- `tests/test_web_overhaul.py` 中 compact/rewind；
- `tests/test_web_sse_lifecycle.py` 中 reply export/terminal 唯一性相关用例。

Phase 1 退出前再跑相关子集和隔离 full-offline。Provider-disabled 浏览器矩阵属于后续本地整合门，不在 Phase 1 最小代码 RED 阶段提前启动；真实 Provider 禁止。

## 10. 后续阶段固定顺序与防漂移门

| 阶段 | 实施前 RED | 结构化替代物 | 之后才可退役的旧门 |
|---|---|---|---|
| Phase 1 canonical history | R4 M03 | canonical snapshot + revision/hash/CAS | 内存直写、长度 heuristic、early-only ledger |
| Phase 2 M02 claim/renderer | R4 `c3f4c190384c` 两份正确候选 + 编造 D30 负例 | curve claim、quantity refs、receipt refs、validation status、host table/disclosure | 族名/数值跨子句配对和范围标记词门 |
| Phase 3 confirmation typing | R4 M01 `5df75d57da84` + 合法成本/分母/窗口正例 | confirmation kind + typed business gap + scope key | 数据性质/真实值/模板词表判定 |
| Phase 4 host journal | R21 task/scope 真实失败 + M04 成功轨迹 | receipt-derived execution journal / claim status | 模型 plan/task JSON 作为发布许可证 |
| Phase 5 audit Shadow | 历史正确候选与高风险越界校准集 | `publication_audit.v1` finding + claim/evidence refs | 只记录，不退役正式门，不影响用户结果 |
| Phase 6 bounded action | Shadow 指标达到预设门槛后 | typed action + 一次 targeted revision | 对应 claim 的旧开放语义门 |
| Phase 7 gate retirement | 每一检查族独立回放 | 新 owner 已上线且闭合 | 逐族删除，禁止一次清空 |
| Phase 8/9 acceptance | 分层 oracle 回放与完整本地矩阵 | blocking/structured/semantic/advisory 四维结果 | 单一 6/6 总判定和措辞 hard oracle |

任何阶段若准备新增关键词、靠末尾附录抵消正文、让 audit LLM 自由改写终稿、引入第二 planner/账本/浏览器框架，必须停止并回到设计审查。

## 11. Phase 0 最终结论

可信重置的大方向和实施顺序仍成立，但不是“原计划事实全部成立”：

- Git 基线、代码形态、M01、M02、M04、M05/M06 边界成立；
- 未提交文件数、R4 额外取消会话、账本完成度需要补记；
- M03 症状成立，但计划所写直接根因与 R4 证据不符，必须改为 split/turn-boundary 事实；
- 现有未提交重构文档/测试包含明确被本轮否决的关键词补丁和“附录兜底正文错误”路径，不能实施；
- Phase 1 应保持极小：只建立 canonical history snapshot、revision/hash、完整 turn 边界和 CAS，不触碰发布语义或其他阶段。

用户已在后续消息中确认可以吸收补充并继续推进。该确认只授权本地计划修订和后续本地实施；
不构成 Provider、push 或部署授权。

## 12. 2026-09-23 用户补充复核与计划校准

### 12.1 `answer_bindings.v1` 是 Phase 2 的既有种子

用户指出 claim 通道不应从零新建。复核确认：

- `publication_synthesis.py` 已提示模型输出 `answer_bindings.v1`；
- 当前 parser 已校验 terminal binding block、packet digest、`exact_text` 唯一性以及
  `requirement_refs/fact_refs/derived_refs` 是否属于当前 packet；
- `test_answer_content_coverage.py` 与 `test_answer_numeric_consistency.py` 已覆盖 schema、旧快照、
  exact-text 和数值一致性；
- R4 M03 transcript 的终稿确实自发输出了 `schema_version=answer_bindings.v1`、blocks、exact_text、
  fact_refs 和 derived_refs。

因此 Phase 2 应从该协议向后兼容扩展 `claim_type/status/unit_status` 等 typed 字段，不新建平行 claim
通道。这样会显著缩小 Phase 2：重点变成 schema extension、M02 typed claim、宿主重算/renderer 和旧门退役，
而不是重新设计模型—宿主传输协议。

需要保留一个精确证据边界：R4 transcript 中的原始块使用通用 `json` fence 和 `snapshot_digest` 字段，
而当前 parser 契约使用 `answer-bindings` fence 和 `packet_digest`。现有落盘材料足以证明“模型会生成该结构，
代码已有校验通道”，但不能仅凭 transcript 断言该原始块已按当前 parser 规范化接纳。Phase 2 首个 RED 应把
R4 原始终稿、host parser 和最终 packet 中的 normalized binding 三者固定为同一回放契约。

### 12.2 Phase 4 journal 只做事后簿记

接受用户提出的硬边界。Phase 4 复用 `turn_receipt_ids`、analysis-state receipts 以及 `4a6493f`/
`89623e6` 的 plan-authority/互斥基础，但 journal 只记录：

- 已执行的工具调用；
- 已产生且可绑定的收据；
- 数据版本与 scope；
- 对应 claim 已闭合、未闭合、降级或 gap 的状态。

journal 不生成目标、方法、步骤、未来任务、下一工具或执行顺序；也不能因为自己推导出未闭合项就授权新执行。
一旦承担这些职责，就已经成为第二 planner，必须停止该设计。

### 12.3 历史测试背景已扩展为累积证据

后续不能只用 2812 项最近 full-offline 和 R4 不完整批次解释系统。已把仓库内可追溯测试史纳入背景：

| 时段 | 代表性收据 | 对本次重置的意义 |
|---|---|---|
| 2026-08-25 Slice 0—7 | 2181 passed/11 skipped；多组 50—446 项切片回归；本地 Flask/浏览器、Workbench、导出；同时保留 Slice 3 全量挂起和旧 Web collection 失败 | 说明功能面和历史恢复面很宽，Phase 1 不能只过新测试 |
| 2026-08-27/28 | 6 failed/2216 passed 后修复为 2342 passed/9 skipped；Provider-disabled 浏览器链路 | 说明 Windows checkout、runner 和浏览器生命周期都曾产生非语义失败 |
| 2026-09-06 | 2393 passed/3 skipped 的隔离 full-offline | 建立 fail-closed Provider-disabled 回归入口 |
| 2026-09-08—20 | 2585、2569、2644、2713 等 full-offline；129、268、285+、301 等定向；B/IC/CONTENT 本地浏览器矩阵 | 说明内容、确认、导出和 reply binding 都是 canonical-history 回归消费者 |
| P08 R10—R21 | 多轮真实 Provider 完整失败或不完整批次 | 形成散文误拒、结构化状态、任务权威、单位、上传和终态的真实失败库 |
| 2026-09-19—22 | 2708、2717、2812 等 full-offline；R4 82 次已调度调用 | 最近绿灯仍未阻止 R4 暴露 M01/M02/M03，证明测试数量不能替代结构正确性 |

历史绿灯只用于确定回归面，不平移为当前 HEAD 证据；历史失败也不得被后续局部绿灯覆盖。每阶段仍需
当前源码的 RED、定向 GREEN、隔离 full-offline 和相应浏览器/Provider 层级证据。

## 13. Phase 1 启动记录

实施前固定的三项边界：

| 项目 | 已冻结内容 |
|---|---|
| RED | R4 M03 transcript 27 条消息，旧 `_find_safe_boundary(..., 10)` 实测为 1，early 只有用户请求 |
| 结构化替代 | `CanonicalHistorySnapshot(messages, revision, sha256, message_count)`；压缩 input identity；写回 CAS |
| 退役旧行为 | 内存直接覆写、message-count 比例 merge、单个用户轮内切分、无 revision/hash 写回 |

当前已新增聚焦 pytest `tests/test_canonical_history_compaction.py`，并完成一次实现前直接断言 RED：

```text
message_count=27
old_split=1
has_canonical_snapshot=False
has_cas_conflict=False
```

仓库当时的 `.venv` 是 Python 3.14 且未安装 pytest；现有隔离 Python 3.12 与桌面运行时也没有 pytest。
这属于测试宿主缺失，不能记作产品测试失败或通过。先完成 compileall 和同解释器纯函数/临时目录检查，
随后离线恢复 pip，并按 `uv.lock` 中的精确版本安装 pytest，才取得下述正式 pytest/full-offline 收据。

### 13.1 当前实现与临时验证结果

已完成的最小实现面：

- `history.py`：增加 canonical JSON+JSONL snapshot、内容 SHA-256、单调 revision、进程内历史锁、原子单文件写入和 revision/hash CAS；
- `history.py`：merge protection 改为精确 hash/prefix 判定；较短分歧 cache 不能覆盖较长磁盘历史；同长度合法完整替换保留兼容，但 compaction/rewind 必须用 hash+revision CAS；legacy 会话首次安全写入时补 identity；
- `compact.py`：只允许在新 user turn 前分割；单个长工具轮找不到完整早期轮时保留全部历史，不调用 summary LLM；
- `compact.py`：transcript sidecar 记录 input revision/hash、message count 和真实 split index；
- Web `/api/compact`：从 canonical snapshot 而非 manager cache 读取；写回前 CAS；冲突返回 409，保留并发新消息且不污染 compact state；
- `agent_manager.py`：从磁盘恢复后同步 `_last_jsonl_idx`，避免把已恢复历史再次当作新增 JSONL 尾部；
- `sessions.py`：rewind 改为读取 canonical snapshot，并以原 revision/hash 做显式截断 CAS；成功后才刷新 cache；
- 新增聚焦测试覆盖 R4 M03、JSON+JSONL、同长度 hash 差异、append revision、CAS、legacy 升级、Web canonical read 和 Web 冲突；较短分歧 cache 由既有 merge-protection 测试覆盖。

静态与直接离线检查：

```text
compileall: PASS
R4 M03 messages: 27
new split_index: 0
summary LLM calls: 0
append revision: 2
safe-save revision: 3
stale CAS write: rejected
temporary Web compact: 200
temporary Web concurrent compact: 409
temporary focused harness: 11 passed
```

第一次临时检查因 transcript 目录没有随 history 根一起重定向，在仓库 `sessions/m03` 生成了两份本轮测试文件。
已核对精确路径后删除这两个文件及其空目录；它们不可恢复但可由同一测试重建，未触碰其他 session。
随后测试同时重定向 history、transcripts 和 tool outputs，全部产物只存在于系统临时目录并在退出时清理。

### 13.2 正式 pytest 与 full-offline 收据

当前 `.venv` 缺失 pip/pytest。使用 Python 自带 `ensurepip` 离线恢复 pip 后，严格按 `uv.lock` 安装
`pytest==9.0.3`；安装过程不涉及任何模型或 Provider。随后完成：

| 层级 | 结果 |
|---|---|
| 新增 canonical-history 聚焦测试（修正前版本） | 11 passed in 2.91s；最终文件为 10 项，删除了与既有合法替换契约冲突的断言 |
| compaction/ACK/publication/export/history/rewind/SSE 定向组合 | 73 passed |
| 受影响完整文件：comprehensive/pipeline/Web/SSE | 312 passed，6 条既有数值边界 warnings |
| 第一次 full-offline | 2823 passed、5 failed、1 skipped、16 warnings；完整跑完，无中途修复 |
| 失败归因后聚焦重跑 | 12 passed |
| 第二次 fresh full-offline | 2821 passed、1 skipped、16 warnings、0 failures，256.55s |

第一次 full-offline 的 5 个失败分成：

1. 1 个真实回归：新 merge protection 把同长度完整替换误判为 stale cache，导致 memory candidate 重索引未更新；
2. 4 个来自用户保留、但本计划已否决且明确不得进入收集的未跟踪 `tests/test_p08_trust_restructure.py`。

真实回归已修为：hash 检测所有差异；较短分歧 cache 不覆盖较长磁盘；同长度/更长的合法完整保存保持兼容；
compaction 和 rewind 等并发敏感路径必须提供 revision/hash CAS。原失败、Phase 1 聚焦和既有 merge protection
共同重跑为 12 passed。

第二次 full-offline 使用新目录 `tmp/trust-reset-phase1-full-offline-2`，通过 pytest 原生
`--ignore=tests/test_p08_trust_restructure.py` 明确模拟“该用户未跟踪草案不进入收集”的既定边界；其余套件不变。
JUnit 为 2822 tests、0 failures、0 errors、1 skipped。runner 输出 `provider_calls=forbidden`。
这是一份带公开排除条件的本地 E1/E2 收据，不是默认脏工作树无条件全绿，也不是浏览器或 Provider 证据。

Phase 1 现可标为 `completed_local`：结构化替代、真实 R4 RED、聚焦 GREEN、既有回归和隔离 full-offline 均闭合。
Provider-disabled 浏览器留在后续整合门；Phase 2 尚未开始。
