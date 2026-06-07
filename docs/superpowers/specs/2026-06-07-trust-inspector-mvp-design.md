# Trust Inspector MVP Design

## Purpose

This phase makes the trustworthy analysis state visible in the Web UI.

The goal is not to add a prettier route recommendation list. The goal is to lower the business user's analysis decision cost by making four hidden states explicit:

1. What the loaded data appears to support.
2. Which analysis directions are recommended by the data contract.
3. Which risks, unsupported analyses, or cleaning issues bound the result.
4. Whether recent evidence-backed claims passed verification or were downgraded.

The existing chat flow remains the primary interaction model. Trust Inspector supports the chat flow by helping the user decide what to ask next.

## User Problem

Today, users can ask follow-up questions in natural language after data is loaded. That is flexible, but it leaves a gap for non-technical users:

- They may not know which analyses are possible from the current data.
- They may not know which recommended direction is safer or more reliable.
- They may not notice that a direction is unsupported by the available grain or fields.
- They may not understand why a final answer became cautious after verification.

Trust Inspector addresses this by turning the current session's trust state into a compact side panel.

## Scope

In scope:

- Add a read-only Web API for a session trust summary.
- Add a right-side Trust Inspector panel to the existing Web chat layout.
- Show compact summaries for data overview, recommended routes, risk boundaries, and latest verification status.
- Let users click a recommended route to fill the chat input with a suggested prompt.
- Refresh the inspector when the current session changes and after chat turns complete.
- Add focused backend and frontend contract tests where practical.

Out of scope:

- No mandatory wizard.
- No new analysis algorithms.
- No new LLM calls.
- No changes to `AgentLoop` planning or synthesis behavior.
- No automatic execution when a route is clicked.
- No full verification report reader.
- No route selection requirement before users can continue chatting.
- No broad redesign of the Web UI.

## Product Shape

Trust Inspector is a right-side panel in the Web chat experience.

Default behavior:

- No data loaded: show a lightweight empty state, such as "Load data to view trustworthy analysis status."
- Data loaded: show the trust summary.
- Narrow screens: keep the panel collapsed by default and expose a toolbar button to open it.
- Desktop: show the panel by default when data exists; allow users to collapse it.

The panel complements the existing conversation rather than replacing it.

## UX Sections

### 1. Data Overview

Shows one compact row per loaded dataset, derived from `dataset_contracts` and `preview_digests`.

Fields:

- dataset name
- row and column count when available
- quality status: `ready`, `warning`, `blocked`, or `unknown`
- a few key fields or inferred roles when available

The section should avoid long schema dumps. It should help the user answer: "Is there usable data here?"

### 2. Recommended Routes

Shows the top 2-4 `route_proposals`.

Each route item should include:

- user-facing label
- direction id, such as `trend`, `period_compare`, or `dimension_decomposition`
- short reason or evidence basis when available
- limitations when present

Click behavior:

- Clicking a route does not send a message.
- It fills the existing chat input with a suggested prompt.
- The user can edit the prompt before sending.

Example generated prompt:

```text
请基于当前数据做周期对比分析，优先使用系统推荐的 period_compare 路线，并说明关键指标变化、证据依据和限制。
```

This preserves user confirmation while reducing prompt-writing effort.

### 3. Risk Boundaries

Shows compact risk items derived from:

- blocked quality issues in `dataset_contracts`
- unsupported analyses in `dataset_contracts`
- cleaning decisions in `cleaning_logs` when they indicate confirmation or blocking risk

Risk item fields:

- severity: `info`, `warning`, or `blocked`
- source: `data_quality`, `unsupported_analysis`, or `cleaning`
- short message
- affected dataset or field when available

The purpose is not to explain every data quality detail. The purpose is to prevent unsupported or risky analysis from looking equally safe.

### 4. Verification Status

Shows the latest verification report summary from `verification_reports`.

Fields:

- overall status: `pass`, `pass_with_downgrades`, `fail`, or `unknown`
- claim count
- failed count
- downgraded count
- evidence signature or timestamp when useful for debugging

If no verification has run yet, show a neutral state: "No evidence verification yet."

The first MVP does not show every claim check. It only explains why the final answer may need caution.

## Backend API

Add a read-only endpoint:

```text
GET /api/sessions/<session_id>/trust
```

The endpoint:

- loads the current `AnalysisSessionState` for the session
- returns a frontend-friendly trust view model
- does not call LLMs
- does not run analysis tools
- does not mutate state
- returns a safe empty state when analysis state is missing

Suggested response shape:

```json
{
  "status": "ready",
  "session_id": "abc123",
  "updated_at": "2026-06-07 10:30:00",
  "datasets": [
    {
      "dataset": "orders",
      "rows": 1200,
      "columns": 18,
      "quality_status": "ready",
      "key_fields": ["date", "revenue", "channel"]
    }
  ],
  "routes": [
    {
      "id": "route_orders_period_compare",
      "direction": "period_compare",
      "label": "周期对比",
      "reason": "Data has a usable date column and numeric metrics.",
      "limitations": ["Descriptive comparison only"],
      "prompt": "请基于当前数据做周期对比分析，优先使用系统推荐的 period_compare 路线，并说明关键指标变化、证据依据和限制。"
    }
  ],
  "risks": [
    {
      "severity": "warning",
      "source": "unsupported_analysis",
      "dataset": "orders",
      "message": "The loaded data cannot support user-level retention analysis."
    }
  ],
  "verification": {
    "status": "pass_with_downgrades",
    "claim_count": 3,
    "failed_count": 0,
    "downgraded_count": 1
  }
}
```

When no data is loaded:

```json
{
  "status": "empty",
  "session_id": "abc123",
  "datasets": [],
  "routes": [],
  "risks": [],
  "verification": null
}
```

## Backend Shape

Create a small view-model builder rather than putting formatting logic directly in a Flask route.

Suggested module:

```text
src/data_agent/agent/trust_view.py
```

Responsibilities:

- `build_trust_view(state) -> dict`
- normalize malformed refs defensively
- derive compact datasets, routes, risks, and verification summary
- generate route prompt text

Suggested Web route location:

```text
src/data_agent/web/blueprints/sessions.py
```

or a small new blueprint if the route file becomes crowded. For the MVP, adding one route to `sessions.py` is acceptable if the formatter lives in `trust_view.py`.

## Frontend Shape

Extend the existing Alpine app rather than introducing a new framework.

State:

- `trustInspectorCollapsed`
- `trustView`
- `trustLoading`
- `trustError`

Methods:

- `loadTrustView()`
- `selectTrustRoute(route)`
- `trustStatusLabel(status)`
- `trustStatusClass(status)`

Refresh triggers:

- after `switchSession(...)`
- after `loadSession(...)`
- after chat `turn_end`
- after upload/load-data flows when the current session is known

Route click behavior:

```javascript
selectTrustRoute(route) {
  if (!route || !route.prompt) return;
  this.inputText = route.prompt;
}
```

The MVP should not auto-submit.

## Layout

Desktop:

- keep the existing sidebar on the left
- keep chat in the center
- add Trust Inspector as a right-side panel
- panel width should be compact, approximately 300-360px
- user can collapse it

Mobile or narrow screens:

- inspector defaults collapsed
- open from a top bar button
- display as a drawer or stacked panel

The panel must not place cards inside cards. Use section blocks and compact repeated route/risk items.

## Empty And Error States

Empty state:

- "加载数据后显示可信分析状态"
- no scary warning language

Missing analysis state:

- same as empty state

Malformed refs:

- backend skips malformed entries
- response still returns a valid view model

API failure:

- front end shows a small retry/error note
- chat remains usable

## Testing Strategy

Backend tests:

- `build_trust_view` returns empty state when no state or no refs exist.
- Dataset summaries are derived from dataset contracts and preview digests.
- Route proposals produce route cards and prompt text.
- Unsupported analyses and blocked quality become risk items.
- Latest verification summary is included.
- Malformed refs do not crash the builder.

Web API tests:

- `GET /api/sessions/<session_id>/trust` returns empty for missing session state.
- Returns populated trust view for a session with analysis state.
- Does not mutate `analysis_state.json`.

Frontend tests where existing test patterns support it:

- Trust Inspector renders empty state.
- Trust Inspector renders route items from API data.
- Clicking a route fills `inputText` and does not send a chat request.

If browser-level frontend tests are too brittle, keep the first frontend coverage at API contract and HTML/JS structure level.

## Success Criteria

This phase is complete when:

- A Web user can see a right-side trust summary after data is loaded.
- Recommended routes are visible without reading a long assistant message.
- Risk boundaries and verification status are visible in compact form.
- Clicking a route fills the chat input but does not auto-send.
- Existing chat workflows continue to work without using the Inspector.
- Focused backend and Web tests pass.

## Risks And Mitigations

### Risk: The panel becomes another noisy dashboard

Mitigation:

- show only compact summaries
- limit routes to 2-4
- keep detailed verification report out of MVP

### Risk: UI duplicates natural-language assistant output

Mitigation:

- show state, not prose
- make route prompts editable and optional

### Risk: Frontend starts parsing raw analysis state

Mitigation:

- backend returns a dedicated trust view model
- frontend consumes simple fields only

### Risk: Users assume route click executes analysis

Mitigation:

- click only fills input
- button label and behavior should imply "use this prompt" rather than "run"

## Later Follow-Up

After MVP validation:

- route-specific prompt templates can become configurable
- verification detail drawer can show claim-level checks
- risky cleaning decisions can request explicit confirmation
- route selection can become a lightweight guided wizard
- SSE can push trust updates in real time
