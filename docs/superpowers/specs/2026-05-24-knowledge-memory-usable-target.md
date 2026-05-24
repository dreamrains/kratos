# Knowledge Memory Usable Target

## Purpose

This note defines when the knowledge and memory system is "usable enough" for the data-analysis agent.

It exists to prevent uncontrolled expansion. Future plans should revisit this note before adding new knowledge or memory features.

## Product Target

The knowledge and memory system is not intended to become a full knowledge-management platform.

Its job is to help the data-analysis agent:

1. Ask fewer repeated questions.
2. Avoid repeating corrected mistakes.
3. Reuse confirmed metric definitions, preferences, and workflows.
4. Preserve traceability to source evidence.
5. Protect the quality and context budget of the core data-analysis flow.

## Usable Definition

The system is usable when it can:

1. Detect high-signal learnable moments such as "remember", "default", "next time", "correction", and "metric definition".
2. Create a small number of memory candidates from those moments.
3. Avoid creating noisy candidates from ordinary conversation.
4. Keep candidate memories out of prompt retrieval until confirmed.
5. Show users why a candidate was created and which evidence supports it.
6. Let users confirm, reject, edit, delete, or promote candidates.
7. Retrieve confirmed memory and formal knowledge only when relevant.
8. Enforce strict retrieval context budgets.
9. Keep evidence out of normal prompts unless explicitly requested or needed.
10. Let formal knowledge remain user-managed and traceable.

## MVP Acceptance Line

Phase 2 should be considered successful if all of these are true:

- A session containing explicit "remember/default/correction/metric definition" language creates one or more candidate memories.
- A normal analysis or chat session does not create many low-value candidates.
- Re-saving the same session does not duplicate candidates.
- Every candidate has a reason and source evidence IDs.
- Candidate memories never appear in `memory_hints`.
- Confirmed memories can be retrieved for similar tasks.
- Retrieval includes metadata showing context usage and trimming.
- Web management lets users review, edit, confirm, reject, delete, and promote candidates.
- Evidence and memory failures never break session saving or the analysis flow.

## Stop-Expansion Rule

Once the following loop is stable, new major knowledge/memory features should pause unless real usage exposes a specific problem:

```text
User correction or preference
-> Candidate memory
-> User review
-> Confirmed memory or formal knowledge
-> Budgeted retrieval in a later relevant analysis
-> Traceable source evidence
```

At that point, development should return to the core data-analysis workflow and use real feedback to decide further investment.

## Non-Goals Until Real Usage Proves Need

Do not add these by default:

- Full Persona system.
- Knowledge graph UI.
- Vector database as the primary retrieval layer.
- Automatic formal knowledge creation.
- Automatic Skill generation.
- Complex conflict arbitration workflow.
- Large governance dashboard.
- Per-turn LLM memory summarization.
- Full conversation replay inside the memory UI.

These may be valuable later, but they are not required for the system to be useful.

## Guiding Principle

Memory should improve analysis quality by reducing repeated context work.

If a memory feature increases prompt noise, slows the analysis loop, or makes the system harder to audit, it should be deferred or removed.
