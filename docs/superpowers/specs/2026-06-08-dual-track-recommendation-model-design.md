# Dual-Track Recommendation Model Design

## Purpose

The existing analysis suggestion feature should not be removed. It is valuable because it helps users think beyond the first obvious analysis path.

However, after adding active scope, route proposals, risks, hypotheses, and a side panel, a single mixed "recommended directions" list is no longer precise enough.

The new rule is:

> Analysis recommendations use a dual-track model: executable recommendations are strict and structured; exploratory suggestions are broader but must state conditions and data needs.

This is a companion design to `2026-06-08-active-scope-session-side-panel-design.md`. Active scope decides what the current work is. The dual-track model decides how recommendations should be classified and presented inside that scope.

## Product Problem

If all suggestions are constrained to only what current data fully supports, the agent becomes too conservative and loses brainstorming value.

If all suggestions are open-ended LLM ideas, the agent can overstate what the current data can support and conflict with the side panel.

The product needs both:

- trustworthy execution guidance
- useful exploratory thinking

## Recommendation Tracks

### Track 1: Executable Recommendations

Executable recommendations answer:

> What can the user safely ask the agent to analyze now?

Properties:

- strict
- active-scope filtered
- based on structured trust state
- eligible for side-panel route cards
- eligible for click-to-fill prompts
- must include limitations when present

Sources:

- `route_proposals`
- `dataset_contracts.supported_analyses`
- `dataset_contracts.unsupported_analyses`
- `cleaning_logs`
- route artifact limitations
- active dataset and active route

Allowed categories:

- `ready`: current data supports this route.
- `needs_confirmation`: route is plausible but depends on cleaning or field assumptions.
- `blocked`: route should not run until quality or confirmation issues are resolved.

Track 1 is intentionally conservative. It is the source for "click this to continue" actions.

Example:

```text
Current data can directly support:
1. cohort analysis
2. funnel analysis

Limitations:
- cohort requires stable user IDs and event history
- funnel requires valid event steps or aggregate funnel columns
```

### Track 2: Exploratory Suggestions

Exploratory suggestions answer:

> What else might be worth considering if the user wants to deepen the analysis?

Properties:

- broader and more generative
- chat-only by default
- not shown as executable route cards
- must include data requirements or limitations
- must never be phrased as immediately supported analysis unless Track 1 also supports it

Sources:

- user goal
- domain hints
- active dataset contract
- missing fields and unsupported analyses
- existing evidence and hypothesis gaps
- method playbooks

Allowed categories:

- `needs_more_data`: useful direction, but requires additional fields, rows, time window, or event grain.
- `method_discussion`: useful concept or framework that can be discussed without data.
- `future_deep_dive`: useful later analysis after current task completes.

Track 2 preserves the value of the original recommendation feature. It should help users think, not imply that the current dataset can already prove the idea.

Example:

```text
Further exploratory directions:
1. User-level long-term retention
   - Needs: user-level event history across a longer observation window.
   - Current status: not directly supported by the loaded aggregate data.
2. Lifetime value by segment
   - Needs: follow-up purchases or revenue history.
   - Current status: can be discussed conceptually, but not verified yet.
```

## UI And Chat Responsibilities

### Side Panel

The side panel primarily shows Track 1 in the "current analysis" tab.

It should show:

- ready routes
- routes needing confirmation
- blocked or unsupported routes when they explain why a user request cannot run

It should not show broad exploratory ideas as clickable executable cards.

If exploratory ideas appear in the side panel at all, they belong in a small "further ideas" area without run buttons, or in the "data and history" tab.

The side panel labels must be Chinese-first in the UI:

- "可直接分析" for `ready`
- "需先确认" for `needs_confirmation`
- "暂不支持" for `blocked`
- "后续探索" for exploratory suggestions

Each section should have a short help affordance explaining what the section means and why it is useful.

### Chat

Chat can show both tracks.

Required structure when both exist:

```text
Current data can directly support:
- ...

Further ideas if you want to go deeper:
- ...
```

Chat must avoid writing exploratory suggestions as if they are ready-to-run recommendations.

The original chat recommendation behavior changes only in classification, not in ambition:

- it may still offer broader analysis ideas
- it must label whether each idea can run now
- it should explain missing data for ideas that cannot run now
- it should reuse the same route capability source as the side panel

Bad:

```text
Recommended directions: cohort, funnel, user-level retention.
```

Better:

```text
Current data supports cohort and funnel analysis. User-level retention is a useful next direction, but it needs more detailed event history.
```

## Active Scope Rules

All executable recommendations default to the active dataset.

If multiple datasets exist:

- Track 1 shows only active dataset routes unless the user asks for cross-dataset analysis.
- Track 2 may mention other datasets, but must label them as cross-dataset or future exploration.
- Chat should not mix route lists from several datasets into one flat recommendation list.

When a new file is uploaded:

- Track 1 resets to the new active dataset.
- Track 2 can mention possible links to earlier datasets, but not as automatic execution recommendations.

When the user is in consulting mode:

- Track 1 is empty or hidden.
- Track 2 can provide method discussion and data requirements.

When the user has already selected a route:

- chat should not repeat the full initial recommendation list on every turn
- side panel should keep the active route visible
- follow-up suggestions should focus on verification, hypotheses, caveats, or deeper next steps

## Prompt Templates

Executable route prompt:

```text
Please analyze the current active dataset using the "{route_label}" route. Explain key findings, evidence, limitations, and avoid claims beyond what the current data supports.
```

Route needing confirmation prompt:

```text
Before running "{route_label}", please clarify the assumptions for these fields: {fields}. Explain how the assumption affects the result.
```

Unsupported or needs-more-data prompt:

```text
I want to explore "{analysis_label}". Please tell me what data is missing, why the current data cannot verify it, and what dataset would be needed.
```

Exploratory chat wording:

```text
This is a useful follow-up idea, but it is not directly verified by the current data. To analyze it, we would need {data_requirements}.
```

Chinese UI wording should carry the same distinction:

```text
当前数据可以直接支持：
- ...

如果你想继续深入，还可以考虑：
- ...（需要补充 ...，当前数据暂不能验证）
```

Click-to-fill prompts must not auto-submit. The user remains in control of whether the route should run.

## Conflict Rules

### Source Priority

Use this priority order when sources disagree:

1. Explicit user choice for active dataset or route.
2. Structured unsupported analysis and cleaning blockers.
3. Structured supported routes from dataset contract and route proposals.
4. Verified evidence, hypotheses, and limitation records.
5. LLM or domain-playbook ideation.

LLM or playbook ideas can add Track 2 suggestions, but they cannot upgrade an unsupported route into Track 1.

### LLM Suggests A Route But Structured Model Says Unsupported

Structured model wins.

The chat response must downgrade the idea to Track 2:

- "needs more data"
- "can discuss method"
- "not directly supported"

It must not appear as a ready executable route.

### Structured Model Supports Route But Cleaning Risk Exists

The route remains Track 1, but category becomes `needs_confirmation`.

The route card and chat must mention the relevant field assumption.

### Chat Has Three Ideas But Side Panel Has Two Routes

This is acceptable only if the third item is explicitly Track 2.

The chat should say:

```text
Two directions can run now. One additional direction is a future exploration idea that needs more data.
```

This resolves the observed mismatch pattern from session-style feedback: chat may discuss three useful directions, while the side panel shows two executable routes. The mismatch is a bug only when the chat presents all three as equally runnable.

## Data Shape

Suggested route capability model:

```json
{
  "active_dataset": "orders",
  "active_route": "cohort",
  "active_mode": "data_loaded",
  "executable": [
    {
      "id": "exec_orders_cohort",
      "route": "cohort",
      "label": "Cohort analysis",
      "category": "ready",
      "limitations": ["Requires stable user IDs and event history"],
      "prompt": "Please analyze..."
    }
  ],
  "exploratory": [
    {
      "id": "explore_orders_user_level_retention",
      "analysis": "user_level_retention",
      "category": "needs_more_data",
      "reason": "Current data lacks user-level event history.",
      "data_requirements": ["user_id", "event_time", "activity events"],
      "value_if_available": "Estimate long-term retention decay and segment differences.",
      "prompt": "I want to explore..."
    }
  ]
}
```

The model should be small enough to fit context budgets. Long explanations belong in chat rendering or help text, not in every stored recommendation object.

## Testing Strategy

Add tests for:

- chat recommendation builder separates executable and exploratory items
- unsupported analysis appears as exploratory, not executable
- side-panel route cards only use executable items
- active dataset filters executable routes
- consulting mode hides executable route cards but can show method guidance
- route prompt templates are shared by chat and side panel
- new file upload changes Track 1 to the new active dataset without deleting old session recommendations
- selected route suppresses repeated full recommendation lists in later chat turns
- a session with two executable routes and one exploratory idea renders as "2 can run now, 1 needs more data"

## Success Criteria

This model succeeds when:

- original analysis suggestions remain useful and expansive
- side-panel route cards stay trustworthy and executable
- chat and side panel no longer appear to disagree
- users can tell the difference between "run this now" and "consider this later"
- unsupported analyses are not hidden, but are clearly labeled as requiring more data
- the recommendation feature is less noisy after a route has already been chosen
- recommendations stay compact enough for context-budget pressure

## Non-Goals

This model does not:

- eliminate open-ended brainstorming
- force every exploratory idea into a route card
- require new statistical tools
- auto-run suggested analysis
- replace active scope filtering
- create a multi-step wizard before every analysis
- require side-panel UI to display every exploratory idea

## Implementation Order

Recommended order:

1. Define a route capability builder that returns executable and exploratory tracks.
2. Refactor side-panel route cards to consume only executable items.
3. Refactor chat analysis suggestions to explain both tracks from the same builder.
4. Share prompt templates between side panel and chat suggestions.
5. Add tests for unsupported-route downgrade and active-dataset filtering.
6. Add a regression fixture based on a session where chat mentions three ideas while the side panel has two executable routes.
7. Update Chinese UI labels and section help text after the data contract is stable.
