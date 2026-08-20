# Data Agent V2 Slice 5C5L：当前源码浏览器证据与语义范围加固

## 目标与边界

本切片在不调用真实 Provider 的前提下，重新建立当前源码的确定性与实际浏览器证据，并用 5C5J 的真实输出做逐维语义复核。禁止隐式重试、自动 repair、Planner 合同放宽、根入口切换和产品完成声明。

## 客观发现

1. 5C5B 增加的模型身份绑定使 provider-neutral fixture 暴露出 `DeterministicJourneyPlanner` 缺少 `model_id` 的共享合同缺口，规划在 fake Planner 调用前 409；
2. `build_provider_neutral_fixture()` 修改全局 Planner、budget、router factory 与配置，fixture 测试没有恢复，组合测试结果依赖文件顺序；
3. 5C5J 的真实输出正确给出日期范围、HAC/Welch 推断、效应量、图表和因果边界，但没有显式报告有效样本、缺失情况和适用总体，`data_scope` 不能判 PASS。

## RED 与修复

- `test_fixture_planning_model_identity_reaches_needs_input` 先证明缺少模型身份时规划返回 409；fixture Planner 现在声明与预算一致的 `provider-neutral-fixture`；
- 将 fixture 与 planning focused tests 组合运行，先复现 6 个顺序相关 409；autouse fixture 现在恢复所有被替换的全局 factory 与配置；
- `test_multi_finding_answer_reports_data_scope_sample_and_missingness` 先证明方法块缺少时间范围、有效周期、缺失周期、有效分析单位、完整/剔除记录和适用总体；共享 multi-finding publisher 现在从确定性结果投影这些字段，并明确不外推。

修复没有改变 Provider schema、authorization、重试策略或分析方法，只闭合测试身份/隔离和答案数据范围合同。

## 当前源码证据

source digest：`sha256:402f4ac145c052bc291ea6b89be06fcf43de67afd807f4cfa1c281ec82328499`。

- unified deterministic oracle：PASS，Provider 调用 0；
- actual-browser planning journey：PASS，fake Planner 调用 3、一次性 authorization 3 次、无隐藏重试、Provider 调用 0；
- 6400 字规划回答完整持久化；规划失败刷新稳定；显式重试后完成分析；
- actual-browser interaction journey：上传、实时进度、运行中草稿、queued steer、stop、失败恢复、session isolation、图表与刷新恢复均通过；
- 最终 multi-finding 输出包含 4 个消息块、2 个邻接图表以及完整数据范围说明；刷新前后答案 digest 一致；
- 当前源码已签发 unified 场景的 owner、incident、SSE、browser、refresh 五层 PASS receipt；未签发 real-provider 或 human-semantic receipt。

## 语义评审边界

5C5J 的真实 Provider 证据绑定旧 digest `sha256:3212b49e...`，当前只能作为历史能力事实。它暴露的数据范围缺口已在当前源码修复，但不能据此反向生成当前源码的真实 Provider PASS。

本切片的逐维记录由实现代理完成，只是 human review preparation，不冒充人工评审。当前仍缺：

1. 当前 source digest 上的 `real_provider_analysis_journey`；
2. 独立人工对当前真实旅程的十一维语义评审；
3. 真实 Provider 重复运行的稳定性证据（次数必须另行精确授权）。

因此 release readiness 仍为 `not_ready`，`/` 根入口未获授权。

## 验证结果

- focused planning/browser/authorization/Slice 4D：`49 passed`；
- V2/config 全量确定性测试：`315 passed`；
- unified deterministic evidence validator：PASS；
- planning 与 interaction browser validator：PASS；
- browser receipt composer：PASS；
- `compileall`：PASS；
- `git diff --check`：PASS；
- release readiness：`not_ready`；当前 unified 场景只缺 `real_provider_analysis_journey` 与 `human_semantic_review`，完整矩阵的其他场景仍有独立缺口。

唯一测试告警是当前目录 `.pytest_cache` 无写权限；不影响测试结果，也没有清理或修改该用户目录。

中间 digest `sha256:60dd53c...` 的 5C5K provider-neutral evidence 在数据范围修复后已成为历史证据。5C5J 的 `sha256:3212b49e...` 真实 Provider 证据同样不是当前源码 PASS；两者均不得混入当前 receipt 集合。
