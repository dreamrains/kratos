---
title: M2 — Rigor + Richness Recovery (Single-Mode, Refine-on-Top)
status: approved
date: 2026-08-12
builds_on: docs/superpowers/specs/2026-08-11-assurance-overlay-recovery-design.md (M1, landed on main)
---

# 1. Goal

M1 made the project usable (publication non-destructive, scope/confirmation/advancement unblocked). But the **analysis output is still poor** — short (~2318 chars, under a hard 2400 cap), chart-less, plainly formatted — because the **generation-time discipline layer chokes it**. M2 restores rigorous, complete, data-grounded analysis output by **refining the behaviors layered on the existing infrastructure** (not ripping it out).

**Acceptance bar (user-defined, NOT "replicate 7/11"):** 严谨(最高) + 数据为本 + 方法合规完整.
- **严谨**: no over-claiming; the audit honestly annotates over-claims / out-of-scope / unverified claims (transparent publication relays + annotates, never deletes).
- **数据为本**: all conclusions/evidence within the user's actual data; anything beyond the data is downgraded to advisory AND explicitly labeled.
- **方法合规完整**: the analysis executes its defined method (playbooks / method_plan / analysis_requirements) fully — including the charts/sections/diagnostics the method requires — and the synthesis reports it faithfully. Richness is the *consequence* of method completeness, not a cosmetic target.

# 2. Foundations kept (NOT removed — refine on top)

Confirmed with user 2026-08-12: the post-July infrastructure is valuable; M2 keeps it and refines behaviors.
- **Evidence contracts** (`evidence_contracts.py`): measurement identity, projection, bounded catalog — the rigor backbone. M2-B makes binding/projection actually work.
- **`[[evidence:aeNN#amNN]]` markers**: the claim↔evidence binding the audit verifies on. Kept (marker ceremony softened — see D3).
- **SynthesisPolicy + `derive_synthesis_policy` + `build_synthesis_instruction`**: deterministic synthesis policy structure. Kept (instruction content refined — D1).
- **Audit-revision loop** (synthesis-only repair): sound concept. Kept (repair instruction de-rigidified — D3).
- **Phase budget** (token management): sound structure. Kept (threshold tuned — D2).
- **Transparent publication** (M1): kept.

# 3. Decisions

- **D1 — Synthesis instruction refined** (`synthesis_policy.py:228-277` `build_synthesis_instruction`):
  - REPLACE the `<synthesis_evidence_discipline>` "if a material claim is not supported by an EvidenceRecord, return a partial answer..." directive with a lightweight **data-grounded rule**: "所有结论必须基于已加载数据；超出数据范围的只能是标注清楚的提示性内容，不得伪装为数据支撑的结论。"
  - KEEP "synthesis does not re-run analysis tools" — charts belong in the analysis phase, not synthesis.
  - Keep the bounded catalog injection (evidence-contract structure).
- **D2 — Marker ceremony softened** (option A, approved): keep `[[evidence:]]` markers; drop the rigid "copy metric_label verbatim / do not translate or round / begin the answer by copying required_verified_core_copy verbatim / at least one standalone verified-core sentence using exactly one measurement" ceremony. The model writes naturally and drops a marker where it uses a catalog measurement.
- **D3 — 2400-char cap DELETED** (`loop.py:2714`): length ≠ rigor. Removed from the truncation-repair instruction (and audited for any other char cap).
- **D4 — Audit-repair instruction de-rigidified** (`loop.py:2702-2750` `_inject_final_answer_audit_repair`): remove the verbatim-copy / standalone-verified-core-sentence rules from BOTH branches; keep "complete answer with findings/recommendations/limitations" and "downgrade unsupported claims, keep markers for re-audit." Keep "synthesis-only revision does not call tools."
- **D5 — Phase-budget threshold tuned** (`execution_control.py` `synthesis_reserve_tokens` + `loop.py _enter_synthesis_reserve_if_needed`): raise/relax the threshold so the analysis phase completes its chart-producing exploration before synthesis is forced. Exact value pinned in the plan after reading the budget math.
- **D6 — Sequencing**: M2-A (richness: D1, D2, D3, D4, D5) first; M2-B (rigor: best-effort binding + promote run_python + meaningful per-claim audit annotations) second, after M2-A is live-validated.
- **D7 — Scope**: M2 stays focused. tiered/strict publication code cleanup + Gate E/F are separate (deferred).

# 4. Architecture (generation freed, rigor at annotation layer)

```
Analysis phase: executes the defined method fully (incl. charts the playbooks require)
   — phase budget (D5) no longer cuts this off prematurely
Synthesis: faithful, data-grounded report of what the method produced
   — instruction (D1) no longer forces partial answers; markers softened (D2); no char cap (D3)
Audit-revision (if needed): synthesis-only repair, de-rigidified (D4)
Publication: transparent relay + honest annotation (M1, kept)
```
Rigor is enforced by the **audit + transparent annotation + the data-grounded generation rule (D1)** — NOT by choking generation (the old 2400 cap / partial-answer / rigid-ceremony approach, which M2 removes).

# 5. M2-A tasks (richness; the implementation plan)

1. Delete the 2400-char cap (D3) + audit for other char caps.
2. Refine `build_synthesis_instruction`: replace the partial-answer directive with the data-grounded rule (D1); soften the marker ceremony (D2).
3. De-rigidify the audit-repair instruction in both branches (D4).
4. Tune the phase-budget threshold so exploration/charts complete before synthesis (D5).

Each task TDD with its own commit. Live-validate against a real-LLM session: full method-compliant answer with charts + sections, no char-cap truncation, honest data-grounded handling.

# 6. M2-B (separate plan, after M2-A lands)

Best-effort `bind_tool_call_to_plan_step` (attribute supporting tools to the active step; dedup capabilities) → advisory projection (promote `run_python`) → the audit now verifies real claims → meaningful per-claim annotations (the footer becomes specific or absent). Resolves the parked M1 findings (readable() strict; two-tools-two-steps).

# 7. Out of scope

- Removing dormant tiered/strict publication code (cleanup, separate).
- Gate E/F (browser/provider) receipt mechanics.
- Changing the defined method/playbooks themselves (if M2 reveals a method defect, raise for user discussion — do not silently change).
