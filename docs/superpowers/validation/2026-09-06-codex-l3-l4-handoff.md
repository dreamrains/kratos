# Codex 交接说明：L3 真实浏览器演练与 L4 真实 Provider 对照

日期：2026-09-06｜来源：分析价值保留专项（P0—P6 已完成，L0—L2 全绿）

> **L3 修复更新（2026-09-07）**：Codex 首轮浏览器演练 B01/B02/B05 passed；B03/B04/B06 的阻断已全部修复（[阶段记录 L3-R 节](2026-09-06-value-preservation-stage-records.md)）：**B06 预算守卫根因**（`registry.reset_groups` 连带清 `turn_state`，守卫在 loop 上从未生效——现预算状态整轮存活并有真实 budget_exceeded 回归）、**B03 产出物与导出**（packet ready 时注册 `publication_receipt` 产出物；导出追加来源/收据/omitted_refs/待验证附录）、**B04 版本失效生命周期**（同名数据集内容变更 → 旧证据按指纹排除 → 已判定假设转 `stale` 并以待验证区"失效"历史项展示）。**请按下文场景复验 B03/B04/B06**（B06 需真实 budget_exceeded 收据；保存失败/发布修订失败/pending confirmation 仍需同域收据），B01/B02/B05 已通过无需重跑。
>
> **P7 修复更新（2026-09-07）**：P7 执行报告中的两项阻断（P7-F01 多来源范围误放行、P7-F02 假设谓词/指标误判）与其余 7 项回归失败、2 项空会话跳过已全部修复：完整离线复跑 **2509 tests / 0 failed / 1 skipped**（tmp/vp-p7r-full-offline），边界测试 **19/0**（含 Codex 原 9 例 oracle 全绿）。修复明细见 [阶段记录 P7-R 节](2026-09-06-value-preservation-stage-records.md)。执行时重点核对 B02/B03（来源绑定发布边界）与 B04（假设谓词判定）。
>
> **P7 后续复核更新（2026-09-06，历史记录）**：上方“全绿”为交接时的历史子集状态。当时完整离线为 2478 passed / 7 failed / 3 skipped；新增独立安全反例为 5 passed / 4 failed。已复现多来源范围误放行和假设目标谓词/指标误判，按总计划 §8 停止依赖验收，B01—B06 全部 `blocked_not_started`，P8 也未启动。详见 [P7 执行报告](2026-09-06-vp-p7-execution-report.md)；下文第 3 节中标注“P7 补充阻断”的两条已由 P7-R 修复（来源绑定与谓词/指标门），其余为待执行要求。

本文件是 [总计划](../../superpowers/plans/2026-09-06-analysis-value-preservation-plan.md) P7 的 L3 部分与 P8 的执行交接。执行方：Codex。授权边界：L3 禁用 Provider；L4 需要用户单独授权（现有旧批次授权不能自动复用）。

## 0. 代码基线与变更清单

- 实施基线：`origin/main` = `36bca25a44a25c99ef8bb7bf56312bde05736ba2`，工作分支 `vp-analysis-value`，全部 P1—P6 改动为**未提交的工作区修改**（无 commit）。开始前先 `git status` 核对修改清单与 [阶段记录](2026-09-06-value-preservation-stage-records.md) 各阶段"命名修改文件"一致。
- 受控文件哈希基线：`docs/audit/2026-09-06-vp-p0-baseline-36bca25-files.json`（351 文件）＋各阶段记录中的文件清单。
- 离线回归入口：`scripts/testing/run_regression.py`（quick / full-offline / slow-offline；强制 Provider 禁用环境变量；run-dir 必须是 tmp/ 下不存在的新路径）。

## 1. L3：本地真实浏览器演练（B01—B06）

### 1.1 硬性前提

- Provider 必须禁用：用脚本化模型响应驱动（可用 stub 的 `LLMClient`/`stream_chat_structured` 注入固定回答序列，参考 `tests/test_publication_synthesis.py::test_streaming_publication_rewrites_once_and_never_projects_rejected_narrative` 的 `loop._stream_llm_round` 覆写手法），**不得 mock 掉**被测的校验（validate_final_narrative）、持久化（analysis_state/save）、投影（workbench_view）与 SSE 消费链。
- 输入夹具隔离在新测试目录（tmp 下新 run-dir），不写入用户生产会话。
- Web 启动：`python -m data_agent.web.entry`（端口 5001）或 `create_app().test_client()` 之上的真实浏览器（建议复用仓库既有浏览器驱动模式）。
- 浏览器 RED 必须来自当前源码运行实例；修复后同一场景重取 GREEN；禁止 sleep 掩盖竞争、禁止注入截图或直接改页面状态。

### 1.2 场景与逐项断言

| ID | 操作过程 | 重点核对（含新增能力的验证点） |
|---|---|---|
| B01 | 加载 F-SALES（12 条订单×10）→ 中文"分析并给出行动建议" → 最终回复 → 刷新 | 120 的描述性事实保留；**中文建议请求不再被压成无建议**（P2/S01：answer_mode=advisory）；建议有条件与停止条件；正文与工作台一致；刷新后内容一致 |
| B02 | 加载 F-RET7（D1—D7 聚合）→ 发布"D7 为 10%，不能预测 D30"→ 再试"D30 预计 5%" | **合规边界句可发布（N01）**；"建议收集至第30天"可发布（N02）；错误 D30 断言被拦截且不先流到浏览器再删除（一次受预算修订；P3 的违规位置进恢复提示） |
| B03 | 多来源/六子问题（F-SIX 式）→ 中途触发 micro_compact（>8 个工具结果）→ 综合回复 → 展开/导出 | **全部六个来源进入发布包**（P4/E01）；第四组及之后的分组数值成对保留（E03）；压缩原文落盘且尾部事实可从 `tool_outputs/{id}__{hash}.txt` 恢复（E06）；省略项有 omitted_refs；导出完整 |
| B04 | 创建竞争假设 → 提交结构化 supports 关系（delta>0, observed=increased）→ 补反证（delta=0, refutes）→ 清空证据 → 刷新 | supported→contested→stale 状态流转（P5/H11）；**待验证发现区**（默认折叠）显示未决项及状态文字/依据/尚缺/下一步（P6/U02/U03）；已验证区不混入假设 |
| B05 | 固定分析结果 → "我是业务人员…"→ "我是数据分析师…"→ "给管理层汇报" 连续追问 | 呈现重点变化（受众块生效）；数值、范围、限制与证据等级三轮一致（A04）；"用大白话"当轮生效且下一轮专业提问恢复术语表达（A06，auto 不再固化） |
| B06 | 工具失败 / 保存失败 / 发布修订失败 / 预算耗尽 / pending confirmation 分别触发 | 状态真实；确认边界生效；无无限恢复；错误候选不发布；流式与同步语义一致（N12）；预算耗尽时覆盖缺口明确列出（E10 coverage） |

每场景保存：源码摘要（git status＋关键文件哈希）、进程与运行配置、输入、脚本化响应身份、工具执行记录、证据/假设/发布状态、最终正文、浏览器截图、刷新/导出结果、逐项 assertion。结果状态只能用 not_started/running/passed/failed/blocked_not_started/skipped_with_reason。

### 1.3 L3 通过后

- 把 B01—B06 的收据路径与逐项结论写回阶段记录文件（新起一节"L3 执行记录（Codex）"），不要改写 P0—P6 的既有记录。

## 2. L4：真实 Provider 质量对照（P8，需单独授权）

- **进入条件**：P7 全量离线＋B01—B06 全部通过；冻结源码（建议先把 P1—P6 改动提交，取得冻结 commit——提交本身需要用户授权）、输入、模型、endpoint、oracle、预算、报表路径、停止规则；获得用户对本专项的新 Provider 授权（旧批次授权不可复用）。
- 推荐场景与验收矩阵 §12 一致：中文建议、复合意图、聚合留存、竞争解释、跨轮补证、三类受众，与 B01—B06 对应。
- 硬指标（0 错误放行类）：关键安全负例、问题处理覆盖率、关键事实保留率、误拒绝率、关键未依据主张、假设错误升级、身份事实一致性、生命周期一致性、调用核算完整性——定义与阈值见验收矩阵 §12.1。
- 业务可用性评分（1—5，要素先冻结）：解释价值、行动价值、假设区分、身份适配、可读性——见 §12.2。
- 对照运行旧基线同样计入授权预算；评分阈值不得事后调整。

## 3. 已知边界（来自 P0—P6 记录，供 L3/L4 重点观察）

1. 发布包覆盖词项与显著性对象绑定是词法匹配；同义改写/跨语言绑定依赖最终合成质量——L4 重点观察。**P7 曾发现曲线外推取全部来源最大上界导致 A 借 B 范围误放行——已由 P7-R 修复为按主张绑定来源（唯一提及→按该来源；未提及/多义→须全部来源观测到，否则标缺绑定进修订）**；B02/B03 执行时按此核对。
2. 结构化假设关系（competing_hypotheses）依赖模型按 schema 提交——L4 需验证真实模型是否愿意/正确提交 `hypothesis_id/relation/metric/observed`；不提交时假设保持未决（安全但信息少）。**P7 曾发现格式合法但目标指标/谓词不匹配仍错误 supported/refuted——已由 P7-R 修复为宿主 decision_rule 判定（目标指标门＋谓词一致性门＋非有限值拒绝，被拒提议保留原因）**；B04 执行时按此核对。
3. 待验证发现区数据来自假设集；无假设集的会话该区为空（"暂无待验证发现"）。
4. 受众检测为关键词规则；未命中时用通用表达。
5. micro_compact 的 KEEP_RECENT=8 与内容寻址文件（`{id}__{sha10}.txt`）——恢复工具需按新命名读取。
