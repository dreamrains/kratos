# Data Agent V2 5C6 新会话交接

- **日期**：2026-08-22
- **目的**：压缩无关历史，在新会话中从事实基线直接实施发布收敛
- **工作目录**：`D:\Project\Daily\data-agent`
- **分支**：`codex/data-agent-v2`
- **HEAD**：`f184dfd3cc3e7ef2b9a66fe687dd05a9abb7a179`
- **提交说明**：`test(v2): record browser and semantic review evidence`
- **source digest**：`sha256:2dbb829eefb47652556222dfc055faa64a97b8fb0950e50d7d6518e675181fba`
- **source dirty**：`false`

## 1. 新会话首先读取

按顺序读取，不从聊天记录猜测合同：

1. `docs/superpowers/plans/2026-08-22-data-agent-v2-5c6-new-session-handoff.md`
2. `docs/superpowers/plans/2026-08-22-data-agent-v2-slice-5c6-acceptance-reset-and-release-acceleration.md`
3. `docs/superpowers/specs/2026-08-13-data-agent-v2-architecture-design.md` 的第 21 节
4. `docs/superpowers/plans/2026-08-13-data-agent-v2-slice-5c1-structured-planner-contract.md`
5. `docs/superpowers/plans/2026-08-22-data-agent-v2-slice-5c5aa-current-provider-stability-preflight.md`
6. `docs/superpowers/evidence/2026-08-22-v2-5c5aa-real-provider-stability-result.json`
7. `docs/superpowers/evidence/2026-08-22-v2-5c5y-current-unified-release-status.json`
8. `docs/superpowers/evidence/2026-08-22-v2-5c5z-human-semantic-review.json`

重点源码：

- `src/data_agent/v2/planner.py`
- `src/data_agent/v2/recommendation.py`
- `src/data_agent/v2/release.py`
- `src/data_agent/v2/provider_authorization.py`
- `src/data_agent/v2/real_provider_journey.py`
- `src/data_agent/web/blueprints/v2.py`
- `src/data_agent/web/blueprints/pages.py`
- `tests/release/v2_release_matrix.json`
- `tests/test_v2_planner.py`
- `tests/test_v2_recommendation_policy.py`
- `tests/test_v2_release_readiness.py`
- `tests/test_mvp_real_data_fixtures.py`
- `tests/real_data/`

## 2. 开始前必须现场核对

```powershell
git branch --show-current
git rev-parse HEAD
git log -1 --pretty=%s
git status --short
.\.venv\Scripts\python.exe -c "from data_agent.v2.release import compute_release_source_digest; s=compute_release_source_digest('.'); print(s.source_digest); print(s.dirty); print(len(s.files))"
```

预期基线是本文件顶部记录的 branch、HEAD 和 digest。如果不一致，先报告差异；不要覆盖或清理已有文件。

不得删除或覆盖：

- `artifacts/`
- `docs/audit/`
- `tmp/`

## 3. 当前未提交成果

当前已有、必须保留并先审查的修改：

```text
M  docs/superpowers/evidence/2026-08-22-v2-5c5y-current-unified-release-receipts.json
M  docs/superpowers/evidence/2026-08-22-v2-5c5y-current-unified-release-status.json
M  docs/superpowers/evidence/2026-08-22-v2-5c5z-human-semantic-review.json
M  docs/superpowers/plans/2026-08-22-data-agent-v2-slice-5c5z-human-semantic-review.md
?? docs/superpowers/evidence/2026-08-22-v2-5c5aa-real-provider-stability-preflight.json
?? docs/superpowers/evidence/2026-08-22-v2-5c5aa-real-provider-stability-result.json
?? docs/superpowers/plans/2026-08-22-data-agent-v2-slice-5c5aa-current-provider-stability-preflight.md
?? docs/superpowers/plans/2026-08-22-data-agent-v2-slice-5c6-acceptance-reset-and-release-acceleration.md
?? docs/superpowers/plans/2026-08-22-data-agent-v2-5c6-new-session-handoff.md
```

`artifacts/`、`docs/audit/`、`tmp/` 也是未跟踪目录，但属于用户资产，不进入清理或提交范围。

新会话应先审查 5C5AA evidence/status diff。只有用户明确要求后才提交；不要把 5C6 源码实现与 5C5AA 历史证据检查点混成一个提交。

## 4. 已核实的当前状态

### Unified 当前进展

当前 `unified_analysis_entry`：

- PASS：owner contract；
- PASS：incident replay；
- PASS：SSE transport；
- PASS：browser interaction；
- PASS：refresh persistence；
- PASS：real Provider analysis journey；
- human semantic review：10 个业务维度 PASS，旧合同中的 stability FAIL；
- current status：`not_ready`；
- root switch：未授权。

### 5C5AA 的准确结果

- 模型：`openai/deepseek-v4-flash`；
- source digest：`sha256:2dbb829eefb47652556222dfc055faa64a97b8fb0950e50d7d6518e675181fba`；
- Provider calls：1；
- automatic retries：0；
- authorization：第一份 consumed；第二份未签发；
- planning：HTTP 201，合同合法的 ready `multi_finding_synthesis`；
- 唯一 normalized plan identity 差异：`parameters.action_risk medium -> low`；
- 其他方法和数据绑定完全相同；
- 独立统计复算通过；
- 旧 exact-identity protocol 判定 FAIL 并停止；
- 当前没有任何新的 Provider 调用授权。

不得补跑 5C5AA，不得复用 authorization，不得把历史 FAIL 手工改为 PASS。

## 5. 已确认的流程根因

1. exact normalized plan identity 把行为等价的 advisory 方差当成整个规划失败；
2. `action_risk` 在当前 Planner 上下文中缺乏足够业务依据，且 low/medium 在本次 recommendation policy 中走相同路径；
3. stability 是技术属性，却被强制放进 human semantic review；
4. 没有版本化、受测试的材料性 semantic comparator；
5. 开发诊断与正式 source-bound release receipt 过早混用，导致每次源码变化都重做发布仪式；
6. 现有 9 × 7 matrix 是有限的，但历史 canary 入口和共享运行时层重复展开，没有面向 root cutover 的 burn-down；
7. `test_v2*.py + config` 不覆盖真实数据 suite；
8. `tests/test_mvp_real_data_fixtures.py` 仍引用两个不存在的旧文件名。

最近一次真实数据离线核查：

```text
2 failed, 28 passed, 1 skipped
```

失败文件名：

- `省钱卡订单_20260507.xlsx`
- `省钱卡用户最近流水_20260511.xlsx`

当前 `reference/test_doc` 包含九个实际 Excel 文件，不得修改、覆盖或上传，除非后续 preflight 明确限定 metadata 并获得用户授权。

## 6. 新会话的第一实施目标

不要申请 Provider。首先实施 5C6 Phase 1：

1. 从历史 baseline/5C5AA/needs-input 事实编写 provider-neutral stability RED；
2. 定义 planning execution identity、recommendation safety identity 和 outcome stability；
3. 证明 `medium -> low` 在行为完全等价时不应触发 planning semantic failure；
4. 同时证明 high/irreversible、必需绑定、analysis unit、路线、数据范围和 outcome 材料性漂移继续 fail closed；
5. 审查所有 `action_risk`、`reversible`、`recommendation_intent` 调用点后，再决定共享合同修改；
6. 不为当前单一输出增加特例或补丁层。

完成 RED 后先向用户报告：

- 旧测试为什么错误；
- 新材料性边界是什么；
- 哪些安全变化仍会阻断；
- 预计会修改哪些共享合同；
- 是否与 5C6 计划存在差异。

如果代码事实与计划冲突，先报告，不实施。

## 7. 发布优先级

用户当前最高优先级是尽快用 V2 替换旧代码并发布。执行顺序必须是：

1. 验收合同重置；
2. evidence/status 自动化；
3. 当前真实数据离线 canary；
4. 全部代码一次冻结；
5. 一份成组、精确次数的 Provider preflight 和授权；
6. `/v2-workbench` root-cutover burn-down；
7. 生成 `ready_for_root_cutover_decision`；
8. 用户单独授权后切换 `/`；
9. 保留 rollback route；
10. 稳定观察和独立授权后才删除旧代码。

不要继续使用“一个小修复对应一次真实调用”的节奏。

## 8. 授权与 Git 边界

- 当前 Provider authorization：无；
- 未经包含模型、digest、目的、Provider host、允许 metadata 和精确次数的用户授权，不得调用 Provider；
- 不自动 retry、repair、fallback 或补跑；
- 本交接不授权 commit、merge、push、部署、切换 `/` 或删除旧代码；
- source 变化后旧 current-source release PASS receipt 不得继续用于新候选；
- 历史 evidence 仍可作为 RED fixture 和事故事实，不冒充新 digest PASS。

## 9. 新会话停止条件

遇到以下情况必须停止并报告：

- branch、HEAD、digest 或未提交文件与交接不一致；
- 需要修改用户真实数据；
- 需要 Provider 调用或数据出境；
- 计划要求会削弱 authorization/source-binding/fail-closed 安全边界；
- 发现当前 V2 无法支持选定真实数据场景；
- 需要切换根入口、删除旧系统、commit、merge、push 或部署。

困难、测试较慢或旧 receipt stale 本身不是继续申请 Provider 的理由。

## 10. 建议的新会话首轮输出

新会话完成只读核查后，应先简洁报告：

1. branch、HEAD、工作区和 source digest；
2. 与本交接不一致的文件；
3. 当前 5C5AA evidence 是否完整且自洽；
4. 5C6 Phase 1 RED 的具体测试列表；
5. 本轮 Provider calls 将保持为 0；
6. 在用户确认没有事实差异后开始实施。
