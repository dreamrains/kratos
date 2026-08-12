# M2-A (Richness) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Restore rigorous, complete, data-grounded analysis output by refining the generation-time behaviors layered on the existing synthesis/audit infrastructure (NOT removing infrastructure). Target: a full method-compliant answer (charts, sections, depth, no char-cap truncation), data-grounded, honestly annotated.

**Architecture:** M1 made publication non-destructive; M2-A frees GENERATION. The synthesis instruction stops forcing partial answers / rigid marker ceremony; the audit-repair instruction stops capping length / forcing verbatim regeneration. Rigor moves to: a lightweight data-grounded generation rule + transparent annotation (M1). Foundations (evidence contracts, markers, SynthesisPolicy, audit-revision loop) are KEPT.

**Tech Stack:** Python 3.12, pytest. Source `src/data_agent/`.

**Spec:** `docs/superpowers/specs/2026-08-12-m2-rigor-richness-design.md`

## Global Constraints

- Chinese-language product; no English fallback in published answers.
- 严谨(最高) + 数据为本 + 方法合规完整 is the bar — NOT "looks like 7/11".
- Do NOT remove infrastructure (evidence contracts, marker system, SynthesisPolicy, audit-revision loop). Only refine behaviors/instruction text.
- Do NOT change the defined method/playbooks. If a method defect surfaces, raise it for user discussion.
- Offline suite must stay green (`uv run pytest tests/ -q`, known order-dependent golden flake acceptable in isolation). Release gates A–D PASS.
- Branch from `main`; one commit per task.

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/data_agent/agent/synthesis_policy.py` | `build_synthesis_instruction` — replace partial-answer directive with data-grounded rule; soften marker ceremony | Task 1 |
| `src/data_agent/agent/loop.py` | `_inject_final_answer_audit_repair` — remove 2400-char cap + rigid marker-copying rules | Task 2 |

---

### Task 1: Refine the synthesis instruction (data-grounded rule + softened marker ceremony)

The synthesis instruction currently (a) forces a "partial answer with missing-evidence limitations" whenever a claim lacks a catalog EvidenceRecord, and (b) imposes rigid marker ceremony (copy metric_label verbatim, begin answer by copying `required_verified_core_copy`, ≥1 standalone verified-core sentence). Both choke the draft. Replace (a) with a lightweight data-grounded rule; soften (b) to "drop a marker where you use a measurement" while keeping the marker system.

**Files:**
- Modify: `src/data_agent/agent/synthesis_policy.py:255-276` (the `<internal_evidence_markers>` and `<synthesis_evidence_discipline>` blocks in `build_synthesis_instruction`)
- Test: `tests/test_synthesis_policy.py` (or the existing synthesis-policy test file — locate it; add assertions on the instruction text)

**Interfaces:** consumes `policy.evidence_catalog`/`evidence_aliases` (unchanged); produces a refined instruction string.

- [ ] **Step 1: Write the failing test**

```python
def test_synthesis_instruction_is_data_grounded_and_marker_light():
    from data_agent.agent.synthesis_policy import SynthesisPolicy, build_synthesis_instruction
    policy = SynthesisPolicy(
        answer_mode="analytical", insight_depth="light", business_translation="cautious",
        risk_boundary="descriptive", required_moves=["core_answer"], suppressed_moves=[],
        wording_style="balanced", reason="test",
    )
    instr = build_synthesis_instruction(policy)
    # D1: data-grounded rule present; "partial answer" directive gone
    assert "超出数据范围" in instr or "数据为本" in instr or "基于已加载数据" in instr
    assert "return a partial answer with" not in instr
    assert "partial answer with missing-evidence limitations" not in instr
    # D2: marker ceremony softened — keep the marker system, drop the rigid verbatim rules
    assert "[[evidence:aeNN#amNN]]" in instr          # markers kept
    assert "required_verified_core_copy" not in instr  # rigid open-copy rule gone
    assert "at least one standalone verified-core sentence" not in instr
    # Sound rules kept
    assert "do not call any analysis" in instr or "不要调用" in instr or "do not call" in instr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_synthesis_policy.py::test_synthesis_instruction_is_data_grounded_and_marker_light -q`
Expected: FAIL (current instruction has the partial-answer directive + rigid ceremony).

- [ ] **Step 3: Refine the instruction**

In `build_synthesis_instruction`, replace the `<internal_evidence_markers>` block with a softened version (keep: every material claim using a catalog measurement should carry its `[[evidence:aeNN#amNN]]` marker; do not invent aliases; markers are internal and stripped before publication. Drop: verbatim metric_label copy, no-translate/no-round, `required_verified_core_copy` open-copy, standalone-verified-core-sentence quota).

Replace the `<synthesis_evidence_discipline>` block with a data-grounded rule that KEEPS "do not call analysis/plan/evidence tools during synthesis" and "do not read raw datasets during synthesis", and REPLACES the partial-answer directive with: "所有结论必须基于已加载数据；任何超出数据范围的判断只能作为标注清楚的提示性内容，不得伪装为数据支撑的结论。" Keep "the bounded_evidence_catalog is the evidence source for catalog-bound claims."

- [ ] **Step 4: Run test to verify it passes; run synthesis-policy + publication regression**

Run: `uv run pytest tests/test_synthesis_policy.py tests/test_tiered_analysis_publication.py tests/test_assurance_overlay_m1.py -q`
Expected: PASS (update any existing test that asserted the old directive text — assert the new data-grounded rule instead; do not weaken).

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/synthesis_policy.py tests/test_synthesis_policy.py
git commit -m "feat(synthesis): data-grounded rule + softened marker ceremony

Replace the 'partial answer if no catalog evidence' directive with a
lightweight data-grounded rule (conclusions within the loaded data;
out-of-scope content labeled as advisory). Soften the evidence-marker
ceremony: keep [[evidence:]] markers but drop the verbatim-copy /
required_verified_core_copy / standalone-verified-core-sentence rigidity
that choked the draft. Foundations (markers, catalog, SynthesisPolicy) kept."
```

---

### Task 2: De-rigidify the audit-repair instruction + remove the 2400-char cap

`_inject_final_answer_audit_repair` (`loop.py:2702-2750`) injects a repair instruction that caps the answer at 2400 Chinese chars (`:2714`) and forces rigid marker regeneration (verbatim copy, standalone verified-core sentence). The cap directly explains the ~2318-char M1 output; the rigidity crowds out content. Remove both; keep the sound parts (complete answer with findings/recommendations/limitations; downgrade unsupported claims; keep markers for re-audit; synthesis revision does not call tools).

**Files:**
- Modify: `src/data_agent/agent/loop.py:2702-2750` (`_inject_final_answer_audit_repair`, both the truncation branch `:2710-2724` and the synthesis branch `:2726-2739`)
- Test: `tests/test_final_answer_publish_gate.py` (the audit-repair instruction tests) + a grep guard

**Interfaces:** produces `self._turn_final_audit_instruction`; consumed unchanged.

- [ ] **Step 1: Write the failing test**

```python
def test_audit_repair_instruction_has_no_char_cap_and_no_rigid_ceremony(monkeypatch):
    loop = _analysis_loop()
    loop._inject_final_answer_audit_repair(mode="synthesis", reason_codes=["provider_output_truncated"])
    instr = loop._turn_final_audit_instruction
    # D3: 2400-char cap removed
    assert "2400" not in instr
    assert "within 2400" not in instr
    # D4: rigid marker ceremony removed
    assert "required_verified_core_copy" not in instr
    assert "standalone verified-core sentence" not in instr
    # Sound parts kept
    assert "findings" in instr and "limitations" in instr          # complete answer
    assert "downgrade" in instr or "unsupported" in instr.lower()  # downgrade unsupported
    # synthesis branch keeps no-tools
    loop._inject_final_answer_audit_repair(mode="synthesis", reason_codes=["missing_evidence_identity"])
    assert "Do not call tools" in loop._turn_final_audit_instruction or "do not call" in loop._turn_final_audit_instruction.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_final_answer_publish_gate.py -k "audit_repair_instruction" -q`
Expected: FAIL (current instruction has "2400" + the rigid ceremony).

- [ ] **Step 3: Rewrite both branches**

Truncation branch (`provider_output_truncated`): remove "Keep the visible answer within 2400 Chinese characters..." and the verbatim-copy / `required_verified_core_copy` / standalone-verified-core-sentence rules. Keep: "Rewrite as one complete self-contained answer; do not continue from the cutoff and do not call tools. It must contain explicit findings, actionable recommendations, and limitations. Where you cite a catalog measurement, carry its [[evidence:aeNN#amNN]] marker; downgrade unsupported claims; keep internal evidence markers for re-audit. This is the only truncation repair attempt."

Synthesis branch (else): remove the verbatim-copy / `required_verified_core_copy` / standalone-verified-core-sentence rules. Keep: "Revise the synthesis only. Do not call tools. Where you cite a catalog measurement, carry its [[evidence:aeNN#amNN]] marker and keep the exact identity tokens. Downgrade or remove unsupported claims, add required limitations/exploratory labels, and keep the internal evidence markers for re-audit. Return a complete answer with findings, recommendations, and limitations. This is the only synthesis revision attempt."

Then grep to confirm no other char cap: `grep -rn "2400\|within [0-9]* Chinese char\|within [0-9]* char" src/data_agent/` — if any other cap exists in a synthesis/publication path, remove it too (note in report).

- [ ] **Step 4: Run test + publish-gate regression**

Run: `uv run pytest tests/test_final_answer_publish_gate.py tests/test_final_answer_claim_audit.py -q`
Expected: PASS (update tests that asserted the old rigid text — assert the kept sound parts; do not weaken).

- [ ] **Step 5: Commit**

```bash
git add src/data_agent/agent/loop.py tests/test_final_answer_publish_gate.py
git commit -m "fix(synthesis): remove 2400-char cap and rigid marker regeneration

The audit-repair instruction capped the answer at 2400 Chinese chars and
forced verbatim marker-copying regeneration, which truncated and choked
the draft (the M1 answer sat at 2318 chars). Remove the cap and the rigid
ceremony; keep complete-answer + downgrade-unsupported + keep-markers +
synthesis-no-tools."
```

---

### Task 3: M2-A verification (offline + live)

**Files:** none (verification only)

- [ ] **Step 1: Full offline suite + release gates**

Run: `uv run pytest tests/ -q` (expect green, known golden flake in isolation) and `uv run python scripts/run_analysis_release_gates.py --profile deterministic` (expect overall_status PASS).

- [ ] **Step 2: Live validation (fresh real-LLM session, 最强砖块记录.xlsx, same prompt)**

Confirm against the bar (严谨 + 数据为本 + 方法合规完整), NOT 7/11 looks:
- The answer executes the method fully (multivariable model + diagnostics + effect size + limitations + decomposition + metric overview) and REPORTS it (charts present, section structure).
- NOT capped near 2400 chars (expect substantially longer, method-complete).
- Charts render inline (validation of M1 Task 5 + actual generation this run).
- Conclusions are within the data; any out-of-scope statement is labeled advisory.
- No `无法发布` placeholders; footer absent or (post-M2-B) meaningful.

- [ ] **Step 3: Conditional D5 (phase-budget tuning) — ONLY if charts/depth still lacking**

If Task 2's live run STILL lacks charts or is cut short, investigate whether `execution_control.py:92-93` (`synthesis_reserve_tokens = total * 0.08`) forces early synthesis entry, and tune. Otherwise DEFER D5 (record in ledger). Do not tune speculatively.

- [ ] **Step 4: Record outcome.** If green + rich, M2-A is done → write the M2-B plan.

---

## Deferred / out of scope

- D5 phase-budget tuning — conditional (Task 3 Step 3).
- M2-B (binding + projection + meaningful per-claim annotations) — separate plan after M2-A.
- tiered/strict publication code cleanup, Gate E/F — separate.

## Self-Review

- Spec coverage: D1+D2 → Task 1; D3+D4 → Task 2; D5 → conditional Task 3 Step 3; D6 sequencing (M2-A first) reflected; D7 scope (focused) reflected.
- No placeholders: both code tasks have the exact code/text to write (the implementer reads the exact current strings and replaces per the spec).
- Type consistency: `_inject_final_answer_audit_repair` signature unchanged; `build_synthesis_instruction` signature unchanged.
