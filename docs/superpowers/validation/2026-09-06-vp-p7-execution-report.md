# P7 执行报告：离线回归失败，可信度边界阻断浏览器验收

日期：2026-09-06｜阶段：P7｜状态：**failed**｜本地候选：**未形成**。

已按用户“从 P7 开始”的指令执行。全量离线回归出现 7 项失败；进一步补充独立安全反例后，确认发布范围可被其他来源扩大、假设关系可产生错误支持/反驳。按总计划 §8 的停止规则，B01—B06 标记 `blocked_not_started`。本次没有启动真实 Provider、提交、推送或部署，也没有修复产品代码。

## 1. 基线、来源与证据等级

- HEAD：`36bca25a44a25c99ef8bb7bf56312bde05736ba2`；分支：`vp-analysis-value`。
- P1—P6 为既有未提交改动，执行时保留。P0—P6 阶段记录作为历史执行记录保留，不能替代 P7 复核。
- [执行收据](../../audit/2026-09-06-vp-p7-execution-receipt.json)保存 347 个已有 `src/tests/scripts` 文件的字节 SHA-256、Git 状态、每次运行的 JUnit 哈希、失败信息和独立反例的输入/实际输出。
- 该文件集合摘要：`6c217d57aa1ced84e77e4edaef810e591502f6153b53d1a5a2ec7f9621719282`。快照在首次全量回归结束后、添加 P7 测试之前记录；它不是运行前的 Provider 冻结身份。本轮最后核查，这 347 个文件没有改变。
- 新增 [P7 边界测试](../../../tests/test_value_preservation_p7_boundaries.py)，共 9 个参数化用例；保持真实预期，4 个失败没有改成 xfail 或跳过。
- 全量和复核使用仓库隔离入口 `scripts/testing/run_regression.py`：临时会话/工作空间、dummy loopback endpoint、真实 Provider 网络禁用、`tests/conftest.py` 阻止未 mock 的 completion。
- 全量覆盖仓库已有离线测试；新增安全反例为 **L1：结构化夹具＋真实宿主函数**。它们不是实际工具、HTTP、SSE、持久化或浏览器验收。当前没有 L3 截图、刷新或导出通过证据。

## 2. 实际执行结果

| 运行 | 时间（本地 +08:00） | 通过 | 失败 | 跳过 | JUnit |
|---|---|---:|---:|---:|---|
| 完整 `tests` 回归 | 21:03，约 158 秒 | 2478 | 7 | 3 | [full-01](../../../tmp/value-preservation-p7-full-01/junit.xml) |
| 独立安全反例 | 21:10，约 2 秒 | 5 | 4 | 0 | [boundaries-01](../../../tmp/value-preservation-p7-boundaries-01/junit.xml) |
| 原失败模块独立复核 | 约 13 秒 | 81 | 7 | 0 | [failure-triage-01](../../../tmp/value-preservation-p7-failure-triage-01/junit.xml) |

第一行发生在新增 9 个测试之前；第三行与第一行重叠，不能相加为独立通过数。原 7 项失败在两个模块单独运行时全部复现，不依赖完整套件的执行顺序。本次未修改已有实现或测试，因此没有 GREEN 或修复后全量结果。

完整回归的 7 条数值计算 warning 来自退化/恒定样本的 SciPy、statsmodels 运算，不是 7 项 assertion 失败的原因。独立反例另有 9 条 `record_property` 与默认 xunit2 格式兼容性 warning；属性实际存在于 JUnit，已提取到 JSON 收据，不能把这些 warning 当成通过或失败的原因。

## 3. 两项必须先处理的可信度问题

### P7-F01：A 的观察范围被 B 扩大

映射：P3 / N03、N06；关联浏览器场景 B02、多来源 B03。

设置两个当前来源：渠道 A 仅 D1—D7，渠道 B 为 D1—D30。通过真实 `publication_contract`、`build_publication_packet` 构造发布包，再调用 `validate_final_narrative`。

| 输入/上下文 | 应有结果 | 当前结果 |
|---|---|---|
| 只有 A：“渠道 A 不能预测 D30，建议继续收集至第30天。” | 允许边界与采集建议 | 允许 |
| 只有 A：“渠道 A 的 D30 留存预计为 5%。” | 拒绝外推 | 拒绝 |
| 同时有 A/B：“渠道 B 的 D30 留存为 8%。” | 允许 B 的观察事实 | 允许 |
| 同时有 A/B：“渠道 A 的 D30 留存预计为 5%。” | 拒绝 A 的外推 | **错误允许，返回 None** |

原因：[publication_synthesis.py](../../../src/data_agent/agent/publication_synthesis.py) 的 `_extrapolation_issues` 使用全部 curve scopes 的最大观察上界；`publication_contract` 没有为曲线范围保留可供逐主张判断的完整来源绑定。加入 B 后，上界从 7 变成 30，检查没有区分断言属于 A 还是 B。

现有 `test_n06_other_source_with_valid_d30_not_blocked` 只证明 B 的合法 D30 不被误拒；`test_n06_a_scope_still_blocks_when_b_absent` 又移除了 B。两者没有覆盖“B 存在时 A 仍应拒绝”的关键反例。此问题由确定性检查复现，不能仅列为 L4 的模型语义限制。

证据边界：本次确认的是宿主发布检查误放行；没有运行浏览器，因此不声称该错误已通过真实 UI 流出或被用户看到。

### P7-F02：模型提出的关系标签仍可决定错误假设状态

映射：P5 / H04、H06、H07；关联 B04。

使用真实 `build_hypothesis_set` 生成目标：“revenue changed between the compared periods in sales.” 所有证据保持同一 sales 数据集、同一 plan_p7，排除跨计划混淆。独立 oracle 依据目标指标和“发生变化”这个谓词判断。

| 结构化证据及模型提出的关系 | 应有结果 | 当前结果 |
|---|---|---|
| revenue delta=10，supports | supported（正向对照） | supported |
| revenue delta=0，refutes | refuted（反向对照） | refuted |
| revenue delta=0，supports | 不能 supported | **supported** |
| revenue delta=10，refutes | 不能 refuted | **refuted** |
| orders delta=10，supports revenue 假设 | 不能 supported | **supported** |

原因：[hypotheses.py](../../../src/data_agent/agent/hypotheses.py) 的 `_validate_relation` 只检查模型选定的 metric 是否出现在该 evidence、observed 是否与 delta 符号一致，以及方法类型门。它没有检查 metric 是否为目标假设需要的指标，也没有检查 supports/refutes 与目标谓词是否一致；返回时直接采用提议的 relation。

当前 [trust_workflow_runtime.py](../../../src/data_agent/agent/trust_workflow_runtime.py) 会调用此函数更新、保存假设；`loop.py` 的合成路径会读取假设简报。因此这不是无调用者的辅助函数。不过，本次证据仍限于 L1 错误状态转换，没有运行完整存储/合成/浏览器链。

**假设 supported/refuted 与 Workbench verified 是不同状态。** 本次没有证明 verified 工作台被污染，不能用错误假设状态冒充“已验证结论泄漏”的证据。

## 4. 全量回归的 7 项失败如何处理

| 数量 | 失败位置 | 判断 | 后续处理要求 |
|---:|---|---|---|
| 3 | `test_multifile_regressions.py`：method_confirmation、orphan_relationship、no_file_consulting | 旧精确字典断言未跟随 P6 增量字段更新；实际仅多出空 pending_findings 与 verified_total=0 | 对齐已接受契约，仍断言确认信息不进入发现区、空态无已验证结论；不可删除原保护语义 |
| 1 | `test_phase_comprehensive.py::TestPhase1IntentClassification::test_fast_path_thanks` | “谢谢你的分析”被识别为 intent_negotiation；纯礼貌语规则只能剥离“谢谢”，残留“你的分析” | 修复完整礼貌短语，同时保留“谢谢，请继续分析……”的主任务路由反例，不恢复简单子串抢占 |
| 2 | `TestPhase3ConfidenceCalibration` 的 small_sample 与 record_auto_downgrades | 旧夹具未说明推断性主张，却要求 n<30 一律降级；与 C01 的新原则冲突 | 拆成明确描述性加总与明确推断两组；描述性计算不机械降级，推断性小样本仍检查必要边界。不能直接把全部断言改为不降级 |
| 1 | `TestCrossPhaseIntegration::test_confidence_calibration_with_real_data_analysis` | 5 行样本被写成无范围的“最受欢迎商品”；预期小样本降级，但新分类器将频率统计当成描述性 | 不直接裁定为陈旧测试。先明确“这 5 行内最多”与“总体最受欢迎”的不同主张，分别验证范围约束及校准，防止用描述性标签掩盖总体推断 |

上述原失败均保留，本次没有通过改旧测试来制造绿灯。7 项不应统一当作产品缺陷，也不应统一归为测试过时。

## 5. 跳过项逐条说明

1. `tests.real_data.test_golden_answer_quality::test_live_smoke_single_scenario`：需要 `GOLDEN_LIVE_SMOKE=1`。本次禁用真实 Provider，跳过符合 P7 的离线边界；不代表 P8 通过。
2. `tests.test_web_overhaul.TestSessionSorting::test_sessions_sorted_by_saved_at_desc`：隔离目录没有超过一个会话。后续应使用两个合成会话验证排序；本次排序未验证。
3. `tests.test_web_overhaul.TestRewindUI::test_rewind_info_endpoint_exists`：隔离目录没有会话。后续应准备合成会话验证端点；本次回退信息端点未验证。

后两项不是 B01—B06 的替代项，也不是跳过核心浏览器矩阵的理由。它们作为明确缺口保留，不能笼统写“既有跳过，无影响”。

## 6. 停止裁决与当前阶段

直接依据[总计划 §8](../plans/2026-09-06-analysis-value-preservation-plan.md)：放宽规则时的阶段停止条件是“**任一关键安全负例失败**”；并要求“**阶段失败先修当前阶段，不进入依赖它的后续阶段**”。P7-F01 和 P7-F02 均满足这一停止条件。停止的是依赖该可信度边界的浏览器验收；原失败的离线归类、证据整理仍继续完成。

| 阶段/用例 | 当前状态 | 原因 |
|---|---|---|
| P2 | failed（P7 复核重开） | 完整回归复现纯礼貌语路由错误 |
| P3 | failed（P7 复核重开） | N06 多来源负例不通过；历史子集通过记录保留 |
| P5 | failed（P7 复核重开） | H06/H07 目标谓词及指标负例不通过 |
| P7 离线部分 | failed | 原 7 项回归失败＋新增 4 项关键反例失败 |
| B01 | blocked_not_started | 安全停止；未启动浏览器，无截图/刷新收据 |
| B02 | blocked_not_started | P3 发布边界必须先修复 |
| B03 | blocked_not_started | 多来源发布依赖 P3 可信边界 |
| B04 | blocked_not_started | P5 假设判定必须先修复 |
| B05 | blocked_not_started | 固定可信事实的身份适配尚无 L3 证据 |
| B06 | blocked_not_started | 错误恢复及确认场景未做本地浏览器演练 |
| P8 | blocked_not_started | P7 未通过，且没有本专项新的真实 Provider 授权 |

这里没有把 B02/B04 写为浏览器 failed：实际失败来自 L1，浏览器没有开始。P6 的 U05—U08 仍未完成真实浏览器验证。

## 7. 恢复 P7 所需工作与通过标准

### R1：恢复来源范围约束（P3）

- 为发布范围保留真实 receipt、dataset/version/plan 与指标/时间范围身份，使单个主张只能引用匹配来源。主张归属不明确时保留已确认的观察/边界、将该主张标为缺少绑定，进入已有一次受预算约束的修订。
- 不能把 `max` 简单换成所有来源的 `min`：那会重新误伤 B 已观察到的 D30。也不能依赖提示词承诺模型不混淆。
- 通过标准：本报告 4 个发布正反例全绿；A/B 交换顺序、同名不同版本、未指明来源、混合边界与预测的用例补齐；合法采集建议仍可发布；原 N01—N12 全通过。随后用 B02/B03 检查错误候选没有 SSE 先泄漏再删除。

### R2：恢复假设目标判定（P5）

- 在既有假设契约中明确待检指标与可计算谓词；模型只提出候选关系，宿主依据当前有效证据、范围、目标指标、所需方法及谓词决定是否成立。
- 针对 period_compare 的 changed 假设，本轮冻结 oracle 为：目标 metric 的有限、可比较非零 delta 支持变化，零 delta 才能反驳变化；其他 metric 不能替代。趋势、基线波动与因果假设需各自证据条件，不能复用一个方向门。
- 缺少判定信息的旧假设/关系保持未决，不通过临时字符串匹配或模型自报 method 升级。新规则不强制自动把错误 supports 改成 refutes；至少拒绝错误提议并保留原因。
- 通过标准：本报告 5 个假设正反例全绿；加入当前验证、版本、NaN/无穷值、缺失指标、因果证据不足等回归；原 H01—H12 与持久化/失效路径通过，supported 与 verified 分别断言。

### R3：关闭常规回归缺口并重做完整验收

- 按 §4 处理 7 项原失败，补充 §5 两个依赖空会话的测试夹具；保留 Provider live smoke 的离线跳过。
- 在新的 tmp run-dir 重跑新增反例、相关模块以及包含新反例的完整 tests。不得复用本次 JUnit 当作修改后的结果。
- 冻结新源码及脚本化模型身份后才恢复 B01—B06；真实工具、状态保存、发布检查、投影、SSE 消费均不能被 mock。每场景保留输入、实际工具记录、正文、状态、截图、刷新/导出和逐条断言。
- 只有全部必测项通过且无可信度边界错误，才能把 P7 改为 passed。P8、Git 提交/推送、部署仍按各自授权边界执行。

## 8. 重现命令与本轮改动

以下命令中的 run-dir 必须不存在；重跑时换用新的目录名。完整套件当前将包含新增 9 个边界测试，预期仍为 RED，不能以本报告的历史总数作为断言。

```powershell
.venv\Scripts\python.exe scripts/testing/run_regression.py quick tests/test_value_preservation_p7_boundaries.py --run-dir tmp/vp-p7-boundaries-next
.venv\Scripts\python.exe scripts/testing/run_regression.py quick tests/test_multifile_regressions.py tests/test_phase_comprehensive.py --run-dir tmp/vp-p7-triage-next
.venv\Scripts\python.exe scripts/testing/run_regression.py full-offline --run-dir tmp/vp-p7-full-next
```

本轮命名改动：新增本报告、JSON 执行收据、P7 边界测试；更新总计划当前状态、交接文档阻断提示；在阶段记录追加 P7 执行结果。临时目录保存三次运行的原始 JUnit、隔离会话及基线快照。既有 src、已有 tests、scripts 内容未修改；既有用户工作区改动与审计/临时资料全部保留。
