# M01 描述事实与比较事实的组合边界

日期：2026-09-29。实施树 `codex/trust-rebuild-20260927@4bb7f85` 加保留的未提交变更，供体 `main@b181646` 只读。本记录是[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)包 B/C 的局部结果，不是新计划。

## 当前实现与 E1

终局已有比较或聚合宿主块时，允许**同一个当前 packet** 中独立验过的唯一 `described_table` 块继续进入原 `answer_bindings.v1`，各块仍按自己的回执、来源版本和原位 trace 渲染。已有 `run_python` 摘要的优先路径不变；没有当前唯一描述回执时不补旧事实。组合与既有比较/摘要定向测试 **20 passed**；新目录完整 E2 `tmp/trust-rebuild-e2-20260929-r3` 为 **2965 passed / 1 skipped / 16 warnings**，Provider transport 禁止。新增来源优先级断言在完整 E2 启动后写入，已由随后的定向 20 passed 覆盖。这证明当前 packet 包含两类已核来源时的渲染机制，不证明任何跨轮来源会自动进入新 packet。

## Provider 禁用正常 app 的独立结果

所有批次事前选择 `control_route=local_http_api`，使用既有 Provider 禁用演练入口；HTTP 上传票据核对，picker、视觉和浏览器刷新 `unassessed`。三批均健康 `ok=true/provider_enabled=false`，结束后服务停止，`forbidden_provider_transport=0`，实际 Provider initiated calls **0**。

| 运行身份 | 收据与观察 | 边界 |
| --- | --- | --- |
| `tmp/m01-composed-20260929-r1`，端口 18772，PID 25048，exec session 1560 | 会话 `eb4eb080b818`，两票据 SHA 核对；首轮描述与次轮比较各有单一 SSE completed、同一会话的持久 packet/答案 SHA、导出。首轮有 12/120 描述块，次轮仅有比较块，`described_tables=[]`。控制器 SHA `c13879358f750c66f01202bbf57925c39e5a006e4fb3aee355d09305ccb3cbf6`，launcher SHA `cf726fced6d5d8aceff6d5da2fe77e1cacfab284e770b44a3eff073fda39ec17`；控制结果/运行迹线 SHA 分别 `5cdc6406d9efbc179dea99fe6cafb7b8fac6dc71139fd3cfba9ace420e3f3b3f` / `8554624ef1c82ab7baa3b080268c021029a01d139e28793331f3cf09afb8638d`。 | 新轮 `turn_receipt_ids` 只含本轮比较，旧描述虽持久化但未被当前要求的结构化来源引用。不能把上一轮答案文字或仅凭请求词面升级为本轮事实。 |
| `tmp/m01-composed-20260929-r2`，端口 18773，PID 18408，exec session 11190 | 同轮串行六次工具调用，六个回执、两条 evidence；在候选脚本读取 preview packet 时终态 `failed`，无已发布答案。控制器 SHA `9f875e3580ab517b8ed7f1c5371c901f9a1c36920054dfe3a7cda15679a750b7`，launcher SHA `a75cfff827f890dd093c7b1d3068f3d3a4c41c63fc873bcae48ec356dcc37ecf`。 | 控制脚本的串行轮次未形成预期 preview；不可称产品事实组合失败。 |
| `tmp/m01-composed-20260929-r3`，端口 18774，PID 16440，exec session 64251 | 同轮改为每轮两项工具调用，六个成功回执、两条 evidence；会话 `16f1b1a9cb9e` 在脚本索取 preview packet 时同样 `failed`，无已发布答案。控制器 SHA 同 r2，launcher SHA `8a1655365433da590e1df6fca18e02ffdf255e3de2eb69e0d2c95a12d2edb8cd`；控制结果/运行迹线 SHA 分别 `c25e9c6359192b99aa81fe425a0af1bbfbd479f35f2e3fa23f318a6b8847d0da` / `59a6585b2873cf059de4b47b9bd923216170ef023d67c8184453e9a337705f71`。 | 同一脚本阻断连续两轮，已停止同型补丁，并移除临时 `B01-DESCRIBE-ACTION` 演练分支；原 launcher 在途改动保持。 |

`r2`、`r3` 的失败只证明当前单轮脚本假定的 preview 时机不成立，不是已核事实出错。下一设计决策是为“同轮多来源、完整行动提案”确定一个正式可复用的 packet/候选交接点，或以当前 packet 已有来源作独立组合验收；跨轮复用则先要结构化当前要求、来源身份与版本核对。没有该边界前，不把 M01 的 12/120 与比较/条件行动同版交付标为通过，也不追加模型散文词表。

## 2026-09-30：同轮交接根因与新目录复验

回读 `r3` 持久态后，确认该演练的 `answer_requirements=[]`：脚本辅助意图分类器没有为 `B01-DESCRIBE-ACTION` 返回 `requested_outputs`。`_maybe_inject_wrap_up` 因而没有当前 `conditional_action` 需求，尚未到普通轮次阈值时不会注入 preview。两次失败是控制器缺少既有意图契约输入，而非终局 packet 构造失败。现为这一**演练情景**提供精确原文 span 与现有 `result/conditional_action` 类型，不让产品从散文词表反推事实。跨轮旧描述来源仍无当前结构化来源引用，未改变这条边界。

在途 `publication_audit.py` 另有真实组合阻断：一个 packet 同时有 `observed_basic_summary` 与已核 `conditional_action_inputs` 时，审核视图先选摘要候选，行动候选没有进入可发布分支。修正后优先定位封闭行动输入；描述事实仍作为独立宿主 claim 留在同一个审核视图。没有行动输入时，原摘要诊断路径仍在。定向审核/比较/摘要 **21 passed**。完整离线 `tmp/trust-rebuild-e2-20260930-r1` **2967 passed / 1 skipped / 16 warnings**、exit 0，Provider 禁止。新目录只证明此次修正后的 E2，不追认旧运行身份。

所有下列运行事前固定 `control_route=local_http_api`，使用仓库既有 Provider 禁用入口，上传 `F-SALES.csv` 与 `F-ACTION.csv` 并核对 filename/SHA；服务健康 `ok=true/provider_enabled=false`，运行后停止，实际 Provider initiated **0**，`forbidden_provider_transport=0`。每条只有一个 SSE 终态，和持久 run state 相符，答案 SHA 与 packet 一致，Markdown 导出已读取。picker、视觉与浏览器刷新仍为 `unassessed`。

| 身份与服务 | 结果 | 冻结控制证据 SHA-256 |
| --- | --- | --- |
| `tmp/m01-composed-20260930-r4`，端口 18775，PID 16152，exec session 73182，会话 `1f7d3c391932`，审核关闭 | `completed`；同一最终 packet 有 `observed_comparison`、`conditional_action_inputs`、`observed_basic_summary`，12 行/120/含首尾 12 日与两期比较同版发布；行动候选按默认门扣留。 | launcher `41484fa5edb61606cc34d92570f536b6a596d1e6713093d966609fe823584498`；driver `9f875e3580ab517b8ed7f1c5371c901f9a1c36920054dfe3a7cda15679a750b7`；control `fa7e70f9be8a9fed04d8784ed6b776244e513382f19f8fc9c98595e6d9a7c6f3`；runtime `0f9e9d874ddb89f64665ab68085139fd39ecf01070d798b34834f7390ca`。 |
| `tmp/m01-composed-audit-20260930-r1`，端口 18776，PID 8872，exec session 80846，会话 `76871a15be03`，修正前试验审核 | `completed`，宿主数值保留，但摘要候选优先级遮住已核行动输入；候选仍扣留。保留为 RED。 | 对照 packet 的 `candidate_resolution=withheld_pending_semantic_binding`、无 `semantic_review`；同一 launcher/driver 输入，单独运行身份。 |
| `tmp/m01-composed-audit-20260930-r2`，端口 18777，PID 25512，exec session 96428，会话 `69a417fc93e9`，修正后试验审核 | `completed`；审核 1 次、无 finding，候选 `semantic_review_passed_trial`，完整下一七日双条件与否则暂停复核进入最终答案；三个当前行动需求 `answered/checked`，12/120 和比较事实仍在。 | launcher `41484fa5edb61606cc34d92570f536b6a596d1e6713093d966609fe823584498`；driver 同 r4；audit source `add7fe9bd94395f0714409690494ef23954f0382290dd561407df34895869245`；control `bbfae860595f2e616fb49c8b9c55ae37228bc3ce6130a27db008f8daff52afb8b8`；runtime `be9f2ff907af77ec94dd7b2a5c4466d5a365841c63cc755ece8a43fce495c1f9`。 |
| `tmp/m01-composed-audit-risk-20260930-r1`，端口 18778，PID 25368，exec session 70353，会话 `a1bfdad85468`，同包负例 | `completed`；候选把本期误作下一窗口停止触发，审核 high finding 扣留；错误“必须立即暂停”未发布，三个行动需求保持 `evidence_insufficient/checked`，12/120/含首尾 12 日与比较事实保留。 | launcher `0319f5077c617121d7bc78cc042463b93b5582f987ac0b87457fd39c45d4f688`；driver `c8615c988b0b948d8a0d6f361eb984a0c4ce8d6199adf4dbb8797ae2851ad6b8`；control `5fc624132f15db256e6d88974dfa0eb735762367df097451bb87b18329c45090`；runtime `a3202956e1bc60756694a7de8401f37fe9e57c7bd166bdfb74a09cb0a0010b5e`。 |

局限：正负候选与审核由 Provider 禁用脚本生成，仍非自然模型语义能力证据。两个 `result` 型精确 span 虽在宿主答案中有对应事实，其 packet `answer_coverage/coverage_check` 仍为 `unassessed/unassessed`，因为比较与描述宿主块尚无可核的逐需求 `requirement_refs`；不能靠答案字符串命中将其改成 `answered`。下一切片须让现有 `answer_bindings.v1` 对这些结果需求提供源/字段/版本可验证的引用，并保持跨来源不串值。全 M01—M06 Provider 禁用矩阵、自然 Provider 与视觉 oracle 仍未完成。
