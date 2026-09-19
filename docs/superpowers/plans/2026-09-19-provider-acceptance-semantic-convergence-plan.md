# Provider Acceptance Semantic Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace open-ended publication rescue patterns with positive evidence-bound claim gates, and fail closed when a competing-hypothesis repair still lacks its required structured audit trail.

**Architecture:** Keep the existing publication packet, one-time recovery, AgentLoop, Stage3C0B state, and pytest/browser runners. Refactor only the deterministic decision boundary: an out-of-range point is blocked when its clause publishes an affirmative value/direction/state payload; a provenance classification is blocked when it has neither packet evidence nor an uncertainty qualifier; an incomplete M04 candidate gets one guard repair and then either satisfies the existing structures or terminates with `analysis_audit_incomplete`.

**Tech Stack:** Python 3.11, pytest, existing `scripts/testing/run_regression.py`, Flask/SSE, existing Provider-disabled browser rehearsal, Git.

---

## File map

- Modify `src/data_agent/agent/publication_synthesis.py`: positive extrapolation payload detection and evidence-bound provenance claim validation.
- Modify `src/data_agent/agent/loop.py`: post-guard structured-gap recheck and deterministic failure closure for sync/stream paths.
- Modify `tests/test_publication_synthesis.py`: 30+ legal paraphrases, 15+ violations, provenance positive/negative contracts.
- Modify `tests/test_analysis_quality_guard_scope.py`: one guard, successful repair, and failed repair contracts.
- Modify `tests/test_execution_control.py`: prove sync/stream terminal parity for an incomplete post-guard audit.
- Update the three current plans, three acceptance matrices, stage record, and integration record after code validation.

### Task 1: Establish the M02 paraphrase gate in RED

**Files:**
- Modify: `tests/test_publication_synthesis.py:540-750`
- Test: `tests/test_publication_synthesis.py`

- [ ] **Step 1: Add the legal paraphrase corpus**

Add one `pytest.mark.parametrize` contract with at least 30 distinct legal clauses. It must include all historical forms and new grammatical families, including:

```python
LEGAL_D30_BOUNDARIES = [
    "目前暂不具备 D30 预测条件。",
    "D30 预测尚缺外推基础。",
    "D30 无从推算。",
    "现有证据无法支持 D30 的点估计。",
    "对 D30 暂不作方向判断。",
    "是否可以预测 D30？",
    "为什么当前阻断 D30 预测？",
    "建议继续观测至第 30 天再判断。",
    "如果 D30 达到预先阈值，则继续试点。",
    "D7 留存为 10%，当前不能预测 D30。",
    "D30 目前不可预测，只有 D1 至 D7 的观测。",
    "当前数据不足以支持对 D30 的预测，因此不报告 D30 数值。",
    "观测区间内的拟合不构成 D30 预测依据。",
    "能否预测 D30——当前证据分级。",
    "请把任何 D30 数字视为假设而非预测。",
    "D30 尚未观测。",
    "D30 缺少验证窗口。",
    "暂时没有 D30 的证据基础。",
    "D30 方向未知。",
    "现阶段无法形成 D30 结论。",
    "不应从 D7 直接外推 D30。",
    "当前不发布 D30 趋势判断。",
    "D30 外推条件尚未满足。",
    "已有数据不能用于估计 D30。",
    "D30 的变化方向仍不清楚。",
    "D30 不在当前观测窗口内。",
    "需要补充 D8 至 D30 数据后再验证。",
    "关于 D30 的结论仍待验证。",
    "D30 应保持为未知项。",
    "当前没有经过验证的 D30 结果。",
    "本轮没有计算 D30。",
    "D30 标记为未计算。",
]

@pytest.mark.parametrize("text", LEGAL_D30_BOUNDARIES)
def test_n01_legal_d30_paraphrases_publish(text):
    assert validate_final_narrative(text, _retention_packet()) is None
```

- [ ] **Step 2: Add the violation corpus**

Add at least 15 affirmative violations covering numeric, percentage, direction, state, point estimate, mixed negation, and unbound-source claims:

```python
ILLEGAL_D30_CLAIMS = [
    "预计 D30 将达到 5%。",
    "D30 留存大约是 5%。",
    "预测 D30 会继续下降。",
    "D30 将保持稳定。",
    "D30 预计处于低位。",
    "不能预测 D30，但 D30 大约是 5%。",
    "D30 留存为 0.05。",
    "D30 约 0.05。",
    "D30 会继续上升。",
    "D30 将出现反弹。",
    "D30 预计改善。",
    "D30 会回落。",
    "D30 将保持高位。",
    "D30 留存将翻倍。",
    "D30 将提高 8 个百分点。",
    "D30 留存将在 4% 至 6% 之间。",
    "D30 不低于 5%。",
    "渠道 A 的 D30 留存为 5%。",
]

@pytest.mark.parametrize("text", ILLEGAL_D30_CLAIMS)
def test_n03_affirmative_d30_claims_are_rejected(text):
    assert validate_final_narrative(text, _retention_packet()) is not None
```

- [ ] **Step 3: Run the new tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_publication_synthesis.py -k "legal_d30_paraphrases or affirmative_d30_claims" -q
```

Expected: at least the three new legal forms reproduced during diagnosis fail with `unbound_time_point_claim`; violation cases remain rejected. The command must fail because current code incorrectly rejects legal forms, not because of collection/import errors.

### Task 2: Implement positive-payload extrapolation gating

**Files:**
- Modify: `src/data_agent/agent/publication_synthesis.py:1076-1235`
- Test: `tests/test_publication_synthesis.py`
- Test: `tests/test_value_preservation_p7_boundaries.py`
- Test: `tests/test_p08_boundary_finalization.py`

- [ ] **Step 1: Add a focused affirmative payload helper**

Replace the `predicts` trigger plus rescue-family branching with a helper whose only responsibility is determining whether the clause publishes an affirmative payload for the matched point:

```python
_AFFIRMATIVE_POINT_DIRECTION = re.compile(
    r"(?:将|会|预计|预估|预测|推算)?(?:继续|仍将|可能)?\s*"
    r"(?:上升|下降|增长|减少|提高|降低|改善|恶化|反弹|回落|趋稳|保持(?:稳定|不变|低位|高位))",
    re.I,
)

def _asserts_time_point_payload(clause: str, match: re.Match[str]) -> bool:
    suffix = clause[match.start():]
    without_point = clause[:match.start()] + clause[match.end():]
    return bool(
        _ASSERTS_VALUE.search(suffix)
        or re.search(r"[-+]?\d+(?:\.\d+)?\s*%", without_point)
        or _AFFIRMATIVE_POINT_DIRECTION.search(suffix)
    )
```

Direction matching is applied only to the suffix beginning at the matched time point. A failure outside these defined numeric/rate/direction/state payloads returns to design review rather than adding a generic “prediction word means claim” trigger.

- [ ] **Step 2: Simplify `_extrapolation_issues` around the helper**

For each matched time point:

```python
if _COLLECTION_ACTION.search(prefix[-30:]) and not _asserts_time_point_payload(clause, match):
    continue
if not _asserts_time_point_payload(clause, match):
    continue
```

Then reuse the existing bound/unbound observation-range checks unchanged. Remove constants that become unused solely because they rescued noun-like prediction mentions.

- [ ] **Step 3: Run focused GREEN verification**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_publication_synthesis.py -k "d30 or extrapolation or prediction or paraphrases" -q
.venv\Scripts\python.exe -m pytest tests/test_value_preservation_p7_boundaries.py tests/test_p08_boundary_finalization.py -q
```

Expected: all selected tests pass; observed-source D30 values and conditional actions remain allowed, while numeric/directional/unbound violations remain rejected.

- [ ] **Step 4: Commit the M02 unit**

```powershell
git add -- src/data_agent/agent/publication_synthesis.py tests/test_publication_synthesis.py
git commit -m "Refactor extrapolation gate around affirmative claims"
```

Do not stage unrelated files.

### Task 3: Bind provenance classifications to evidence or uncertainty

**Files:**
- Modify: `tests/test_publication_synthesis.py:270-330`
- Modify: `src/data_agent/agent/publication_synthesis.py:1435-1560,1813-1835`

- [ ] **Step 1: Add provenance RED contracts**

Add parameterized unsupported assertions and bounded statements:

```python
UNSUPPORTED_PROVENANCE_ASSERTIONS = [
    "该数据是测试数据。",
    "该样本由机器生成。",
    "这是合成数据。",
    "这个文件是人工构造的。",
    "这些记录并非真实账本。",
]

BOUNDED_PROVENANCE_STATEMENTS = [
    "需确认该数据是否为测试数据。",
    "尚不清楚该样本是否由机器生成。",
    "当前证据无法判断这些记录是否来自真实账本。",
    "分析文件: M01-sales.csv",
]
```

Assert that unsupported affirmative classifications yield `unsupported_data_origin_inference`, while bounded statements and ordinary source identities do not.

- [ ] **Step 2: Run provenance tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_publication_synthesis.py -k "provenance or unsupported_data_origin" -q
```

Expected: “测试数据/机器生成/合成数据” affirmative cases fail because current code returns no issue; bounded statements remain green.

- [ ] **Step 3: Implement clause-level provenance structure**

Introduce separate subject, predicate, and uncertainty patterns rather than full-sentence rescue patterns:

```python
_PROVENANCE_SUBJECT = re.compile(r"数据|样本|文件|记录|账本|来源", re.I)
_PROVENANCE_PREDICATE = re.compile(
    r"测试|样例|示例|合成|模拟|机器生成|人工(?:生成|构造)|规则生成|"
    r"占位|演示|脱敏|真实账本|非真实账本|不是真账本",
    re.I,
)
_PROVENANCE_UNCERTAINTY = re.compile(
    r"是否|未知|尚不清楚|无法判断|不能判断|未验证|待确认|需(?:要)?确认|"
    r"可能|疑似|假设|如果|若",
    re.I,
)
```

Change `_unsupported_data_semantics_issues(text, packet)` to reject a clause only when subject + predicate are present, the clause lacks uncertainty, and `_packet_supports_provenance(packet, predicate)` cannot find a matching controlled fact. The helper inspects only facts whose path contains `provenance`, `origin`, `source_type`, `data_kind`, or `generation_method`, then compares the normalized predicate token with that fact value. It must not search arbitrary narrative summaries, treat the model’s answer as evidence, or add persistent fields.

- [ ] **Step 4: Run provenance and full publication tests GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_publication_synthesis.py -q
```

Expected: complete file passes; existing CV, YoY, missing-value, currency, source-binding, arithmetic, and coverage contracts remain green.

- [ ] **Step 5: Commit the provenance unit**

```powershell
git add -- src/data_agent/agent/publication_synthesis.py tests/test_publication_synthesis.py
git commit -m "Require evidence for provenance classifications"
```

### Task 4: Fail closed after one incomplete M04 repair

**Files:**
- Modify: `tests/test_analysis_quality_guard_scope.py:35-85`
- Modify: `src/data_agent/agent/loop.py:2098-2175,3188-3210,3612-3635`
- Modify: `tests/test_execution_control.py:430-840`

- [ ] **Step 1: Add post-guard RED tests**

Add tests proving these states:

```python
def test_explicit_hypothesis_task_rechecks_gaps_after_guard():
    loop = _loop_with(["record_analysis_plan", "record_evidence_record"])
    loop.context.analysis_state.analysis_plan = None
    loop.context.analysis_state.hypothesis_sets = []
    loop.context.analysis_state.evidence_records = []
    loop._inject_analysis_quality_guard()

    assert loop._should_continue_for_analysis_quality(
        "请提出并检验至少两种竞争性假设", "still prose only",
    ) is False
    assert "analysis_audit_incomplete" in loop._analysis_quality_failure_after_guard()

def test_complete_repair_clears_post_guard_failure():
    # Populate a current plan, a hypothesis set, and one evidence relation.
    # After the same one guard, failure helper returns None.
```

Also assert the guard system message count remains exactly one.

- [ ] **Step 2: Run guard tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_analysis_quality_guard_scope.py -k "post_guard or rechecks_gaps or complete_repair" -q
```

Expected: current code either clears gaps solely because the guard flag is set or lacks `_analysis_quality_failure_after_guard`; tests fail for that reason.

- [ ] **Step 3: Implement one-repair recheck**

- Remove the early `_turn_final_guard_injected` return from `_competing_hypothesis_quality_gaps`.
- Make `_should_continue_for_analysis_quality` refresh `_turn_analysis_quality_gaps` on every candidate, inject only when gaps exist and no guard has yet been used, and clear stale gaps when structures are complete.
- Add:

```python
def _analysis_quality_failure_after_guard(self) -> str | None:
    gaps = list(getattr(self, "_turn_analysis_quality_gaps", []) or [])
    if not getattr(self, "_turn_final_guard_injected", False) or not gaps:
        return None
    return "[analysis_audit_incomplete] 竞争假设审计结构仍不完整：" + "; ".join(gaps)
```

- In sync and stream terminal paths, call the helper immediately after the one-time continuation check. Return/yield the existing error form and stop without persisting or publishing the rejected candidate.

- [ ] **Step 4: Run guard and execution-control GREEN tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_analysis_quality_guard_scope.py tests/test_execution_control.py -q
```

Expected: all tests pass; one guard only, complete repair publishes, incomplete repair returns one explicit failure, confirmation/tool pairing contracts remain unchanged.

- [ ] **Step 5: Commit the M04 unit**

```powershell
git add -- src/data_agent/agent/loop.py tests/test_analysis_quality_guard_scope.py tests/test_execution_control.py
git commit -m "Fail closed on incomplete hypothesis audits"
```

### Task 5: Isolated regression and Provider-disabled browser acceptance

**Files:**
- No production edits unless a reproduced regression requires returning to its owning RED/GREEN task.

- [ ] **Step 1: Run targeted publication/quality regression in a fresh run-dir**

Run with the existing isolated runner and a new directory:

```powershell
.venv\Scripts\python.exe scripts/testing/run_regression.py quick --run-dir tmp/p08-semantic-convergence-targeted-1 tests/test_publication_synthesis.py tests/test_value_preservation_p7_boundaries.py tests/test_p08_boundary_finalization.py tests/test_analysis_quality_guard_scope.py tests/test_execution_control.py
```

Expected: 0 failures and Provider network prohibited.

- [ ] **Step 2: Run the broader contract group in a second fresh run-dir**

Include analysis flow, hypotheses, confirmation, content binding, SSE lifecycle, compaction, and artifact publication files used by R16/R17. Record the exact file list and output in the implementation record.

Expected: 0 failures and Provider network prohibited.

- [ ] **Step 3: Run full-offline once in a fresh run-dir**

```powershell
.venv\Scripts\python.exe scripts/testing/run_regression.py full-offline --run-dir tmp/p08-semantic-convergence-full-offline-1
```

Expected: 0 failures; any ordinary test failure is recorded and the suite completes. Stop only for the existing isolation/evidence/service integrity gates.

- [ ] **Step 4: Run Provider-disabled browser rehearsal**

Start the existing rehearsal entry with a new run-dir and use the Codex built-in browser. Exercise B02/B02-NEG with at least three new legal paraphrases and one illegal value/direction candidate; exercise B04 through one complete structured repair and one deliberately incomplete scripted repair; recheck upload binding, refresh, export, console, terminal uniqueness, and persisted state.

Expected: legal boundaries publish, illegal claims are revised or rejected, complete B04 persists plan/hypotheses/evidence relations, incomplete B04 ends once with `analysis_audit_incomplete`, console has no error/warning, and actual Provider initiated calls equal 0.

### Task 6: Documentation, final verification, and local commit

**Files:**
- Modify: `docs/superpowers/plans/2026-09-06-analysis-value-preservation-plan.md`
- Modify: `docs/superpowers/plans/2026-09-07-intent-clarification-plan.md`
- Modify: `docs/superpowers/plans/2026-09-08-answer-content-optimization-plan.md`
- Modify: `docs/superpowers/validation/2026-09-06-analysis-value-preservation-acceptance.md`
- Modify: `docs/superpowers/validation/2026-09-07-intent-clarification-acceptance.md`
- Modify: `docs/superpowers/validation/2026-09-08-answer-content-acceptance.md`
- Modify: `docs/superpowers/validation/2026-09-06-value-preservation-stage-records.md`
- Modify: `docs/audit/2026-09-09-answer-intent-integration-record.md`

- [ ] **Step 1: Record evidence boundaries**

Record RED/GREEN commands, exact targeted/full-offline results, browser sessions/run-dir, Provider initiated calls=0, commits, and the fact that P08/IC5/AC40 remain `executed_failed / not_accepted` until a new E4 succeeds.

- [ ] **Step 2: Run final static verification**

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors; only named documentation changes remain before the documentation commit.

- [ ] **Step 3: Commit named documentation files**

```powershell
git add -- docs/superpowers/plans/2026-09-06-analysis-value-preservation-plan.md docs/superpowers/plans/2026-09-07-intent-clarification-plan.md docs/superpowers/plans/2026-09-08-answer-content-optimization-plan.md docs/superpowers/validation/2026-09-06-analysis-value-preservation-acceptance.md docs/superpowers/validation/2026-09-07-intent-clarification-acceptance.md docs/superpowers/validation/2026-09-08-answer-content-acceptance.md docs/superpowers/validation/2026-09-06-value-preservation-stage-records.md docs/audit/2026-09-09-answer-intent-integration-record.md
git commit -m "Record semantic convergence acceptance evidence"
```

- [ ] **Step 4: Prepare a new zero-call freeze only after all commits**

Use `scripts/testing/run_p08_real_matrix.py --preflight` with a new run-dir tied to the final exact commit. Freeze model, endpoint, fixture hashes, complete prompts/oracles, matrix, call cap 120, built-in browser protocol, and ledger path. Verify the ledger is absent and isolation directories are empty.

- [ ] **Step 5: Stop at the Provider authorization gate**

Report the exact final commit, freeze SHA-256, model, endpoint, matrix, budget, and ledger path. Do not call the Provider, push, deploy, or reuse the superseded `fde218b7...af4ac` freeze.
