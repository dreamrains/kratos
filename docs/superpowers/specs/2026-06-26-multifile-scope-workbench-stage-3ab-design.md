# Multi-File Scope And Workbench Stage 3A/3B Design

Date: 2026-06-26

## Decision

Stage 3 will repair multi-file analysis by separating file participation from file relationship inference.

The next implementation should deliver Stage 3A and Stage 3B as one designed change set with two implementation slices:

1. Stage 3A changes the backend scope contract so files can participate in analysis without first proving pairwise relationships.
2. Stage 3B changes the right workbench panel so it explains user-facing analysis scope and actionable decisions instead of surfacing technical relationship diagnostics as pending work.

Chart validation and operation-level join or union confirmation remain separate later stages.

## Problem

The current multi-file path treats relationship uncertainty as scope uncertainty:

1. `classify_file_relationship` often creates `requires_confirmation=True` relationship records for files that may still be valid inputs for the same analysis.
2. `build_analysis_scope_plan` treats pending relationships as `pending_files`.
3. `trust_view` exposes those pending files through `workbench.current_context`.
4. The right panel renders this as waiting confirmation or relationship status, but the chat may have no answerable confirmation card.

This creates a confusing user experience: the system says there is something to confirm, but the user cannot see what question must be answered or why the analysis should stop.

The deeper issue is conceptual, not cosmetic. File participation and cross-file relationship are different decisions:

- Participation answers: should this file be available for this analysis?
- Relationship answers: can these files be joined, unioned, compared at the same grain, or mapped through a shared entity?

A file can participate without any relationship to another file. For example, four uploaded files can all be available to an exploratory analysis even if only two are later joined.

## Goals

- Include files explicitly supplied for the current analysis unless the user excludes them or the file cannot be loaded.
- Stop using pairwise relationship uncertainty as a blocking scope decision.
- Keep legacy relationship records readable as diagnostics, not as the primary source of truth for scope.
- Make the right panel describe analysis participation in user terms: what is used, what is available, what is not used, and what action is actually needed.
- Preserve the unified confirmation runtime: if a decision blocks progress, it must have one visible, answerable, resumable confirmation card.
- Keep the change safe by avoiding a new implicit join, union, or entity reconciliation policy.

## Non-Goals

- Do not implement chart validation in this stage.
- Do not remove historical `dataset_bundles` or `file_relationships`.
- Do not migrate old session files in place.
- Do not introduce automatic joins or unions merely because files are included in scope.
- Do not redesign export or artifact delivery.

## Stage 3A: Analysis Scope Contract

### New Scope Model

`build_analysis_scope_plan` should produce a participation-first plan.

Each file summary should have a participation state:

- `included`: available to planning and tools for the current analysis.
- `available`: loaded and inspectable, but not currently needed for the active goal.
- `unused`: intentionally not used for the current goal.
- `needs_scope_decision`: only for genuine ambiguity about whether the file belongs to the requested analysis.
- `unavailable`: file profile is missing, failed to load, or cannot be inspected.

The scope plan should expose these groups:

- `included_files`
- `available_files`
- `unused_files`
- `decision_files`
- `unavailable_files`

For backward compatibility, existing `pending_files` may remain during the transition, but it should be derived only from `decision_files`, not from relationship uncertainty.

### Default Rules

The backend should apply these rules in order:

1. Files explicitly named by the user for the current request are `included`.
2. Files loaded in the same user turn are `included` unless the user explicitly excludes them.
3. Files in the active bundle are `included`, unless there is stronger explicit exclusion.
4. Historical files already present in the session are `available` by default, not silently included.
5. Files clearly unrelated to the active goal are `unused`, not blocking.
6. Files with unreadable or missing profiles are `unavailable`.
7. Only ambiguous user intent about participation creates `needs_scope_decision`.

Pairwise key overlap, theme overlap, `possibly_linked`, and `requires_confirmation` relationship flags must not by themselves create `needs_scope_decision`.

### Relationship Diagnostics

Relationship evidence should be retained as optional diagnostic metadata:

- possible shared keys,
- weak or generic ID overlap,
- time range compatibility,
- relationship status from legacy records,
- uncertainties about join or comparison safety.

This metadata can inform future operation-level validation, but it must not decide whether a file participates in the analysis.

### Scope Status

`scope_status` should represent participation readiness:

- `ready`: files needed for the current analysis are available.
- `ready_with_notes`: analysis can proceed, but there are non-blocking scope notes.
- `needs_decision`: user must decide whether one or more files belong to the analysis.
- `blocked`: required files are unavailable or unreadable.

`needs_confirmation` should not be used for scope unless it maps to an active confirmation runtime suspension. If retained for backward compatibility, it should be translated from `needs_decision` only when the API consumer requires the old value.

### Confirmation Trigger Standard

This stage should only ask the user a question when participation itself is unclear.

Examples that should not ask:

- Files were uploaded together and the user asked to analyze them.
- Files have unclear join keys but no join is being executed yet.
- A relationship record says `possibly_linked`.
- An old relationship record has `requires_confirmation=True` but no active suspension.

Examples that may ask:

- The user asks to analyze "the sales file", but multiple loaded files match and none is clearly current.
- The user says "ignore the older data" and the system cannot identify which files are older.
- A required file is present historically but was not selected for the current task.

Cross-file operation questions belong to Stage 3C, not Stage 3A. Examples:

- Which user identifier should be used for a merge?
- Should two tables be unioned despite different grain?
- Should account ID and member ID be treated as the same entity?

## Stage 3B: Workbench Side Panel

### User-Facing Structure

The right panel should be organized around decisions and impact:

1. Current analysis target
2. Files used in this analysis
3. Other available files
4. Files not used and why
5. Action needed, only when an active confirmation exists
6. Technical details, collapsed by default

The primary panel should avoid relationship-first labels such as "relationship pending" or "waiting confirmation" unless there is a visible confirmation card.

### Suggested Labels

The implementation can localize these labels in Chinese UI text:

- "Used in this analysis"
- "Available, not currently used"
- "Not used"
- "Needs your decision"
- "Technical relationship notes"
- "No action needed"

The sidebar should answer three user questions:

1. Which files is the system using?
2. Why are other files not being used?
3. Is there anything I need to answer before analysis continues?

### Technical Details

Legacy relationship records should move into a collapsed diagnostic area. The diagnostic area may show:

- relationship status,
- candidate keys,
- weak evidence,
- unresolved uncertainties,
- whether this is historical metadata rather than an active blocker.

Diagnostic entries must use non-blocking wording unless backed by the confirmation runtime.

For example:

- Good: "Possible shared user identifiers found. This will be checked if a merge is needed."
- Bad: "2 files / relationship pending / waiting confirmation."

### Workbench Contract

`trust_view` should expose a workbench contract that separates display groups from diagnostics:

```json
{
  "current_context": {
    "goal": "...",
    "scope_status": "ready_with_notes",
    "included_files": [],
    "available_files": [],
    "unused_files": [],
    "decision_files": [],
    "unavailable_files": [],
    "notes": []
  },
  "confirmations": {
    "status": "clear",
    "question": "",
    "blocking_reason": ""
  },
  "relationship_diagnostics": []
}
```

During the transition, `pending_files` can remain for old clients, but new UI code should prefer `decision_files`.

## Compatibility

Existing sessions must remain inspectable:

- Continue reading `dataset_bundles`.
- Continue reading `file_relationships`.
- Continue exposing legacy fields where current tests or clients require them.
- Do not let legacy relationship confirmation flags create an active confirmation unless a runtime suspension exists.

New writes should follow the participation-first model.

## Testing Plan

Stage 3A tests:

- Same-turn explicit files are included without relationship confirmation.
- A `possibly_linked` relationship does not create `decision_files`.
- Active bundle files remain included.
- Historical files are available but not silently included.
- Clearly unrelated files are unused and non-blocking.
- Unreadable profiles are unavailable and can block only when required.
- `pending_files` compatibility mirrors `decision_files`, not relationship diagnostics.

Stage 3B tests:

- Workbench current context exposes `included_files`, `available_files`, `unused_files`, `decision_files`, and `unavailable_files`.
- Relationship diagnostics are present but non-actionable by default.
- The sidebar does not display "waiting confirmation" for orphan legacy relationship flags.
- The "action needed" area appears only when the confirmation runtime reports an active pending confirmation.
- Existing confirmation runtime and workbench parity tests still pass.

Regression tests:

- Legacy pending confirmations without suspension remain ignored by active confirmation UI.
- No final report is emitted while a real blocking confirmation is unresolved.
- No scope repair introduces automatic join, union, or entity mapping behavior.

## Implementation Slices

### Slice 1: Stage 3A Backend Scope

- Update scope classification in `multi_file_scope.py`.
- Add compatibility fields so existing consumers keep working.
- Update multi-file scope regression tests to the new participation-first semantics.
- Keep relationship records as metadata only.

### Slice 2: Stage 3B Workbench Contract And Sidebar

- Update `trust_view.py` workbench output.
- Update right panel template and JS helper wording.
- Add or update tests for sidebar/workbench display behavior.
- Keep export and artifact UI unchanged.

## Risks And Mitigations

Risk: Including files by default may be mistaken for joining files automatically.

Mitigation: Scope inclusion must only mean "available for analysis". Operation-level merge, union, and mapping decisions remain separate and must not be added in this stage.

Risk: Legacy relationship records may still leak as blockers.

Mitigation: Treat them as diagnostics unless there is an active confirmation runtime suspension.

Risk: UI text may hide useful technical evidence.

Mitigation: Keep technical details available in a collapsed diagnostic section, but make the primary panel user-facing.

Risk: Backward compatibility fields may preserve confusing names.

Mitigation: New UI should read the new fields first. Compatibility fields should be derived, documented, and covered by tests.

## Acceptance Criteria

- Four files supplied for one analysis can all participate without pairwise relationship confirmations.
- Relationship uncertainty does not create `scope_status=needs_confirmation`.
- The sidebar names used and available files in user-facing language.
- The sidebar shows no "waiting confirmation" unless an active confirmation card exists in chat.
- Legacy relationship diagnostics remain inspectable but do not block analysis.
- Existing confirmation runtime tests continue to pass.
- Stage 3 does not implement or imply automatic joins, unions, or entity reconciliation.

## Open Implementation Notes

- The final implementation should prefer additive contract changes before removing old fields.
- If the current state lacks same-turn provenance, the first implementation slice should use available active-bundle and explicit state signals, then add stronger provenance only if needed.
- Test fixtures should encode the product rule directly: participation is not relationship.
