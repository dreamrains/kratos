# Conversation Synthesis And Report Artifact Design

## Decision

Intent recognition will stay in evaluation and discussion only. Do not change the current runtime intent classifier, prompt routing, tool-group activation, or TurnIntent flow until real usage feedback shows clear value and acceptable risk.

For the current product stage, remove brief and formal report as product features. The agent should satisfy report-like user needs through high-quality conversational analysis and current-session synthesis. Keep the underlying evidence system because EvidenceRecord, InsightRecord, charts, tasks, and analysis state are part of analysis quality, not report-specific baggage.

Future report work should be redesigned as a new cross-session synthesis or analysis dossier capability rather than continuing the current formal report artifact.

## Rationale

The current agent has not yet been used by many external users, so there is little historical compatibility pressure. Keeping brief and formal report now may create unnecessary product concepts, confuse users, and constrain a better future design.

The user expectation is simpler than the current feature split:

- When a user asks an analytical question, the agent should answer with conclusions, evidence, caveats, and next steps in the conversation.
- When a user asks to summarize the current work, the agent should synthesize the current session context and analysis state in the conversation.
- When a user later needs a multi-session, shareable deliverable, that should be a separate analysis dossier feature with its own design.

The existing formal report duplicates the current-session conversational synthesis use case. Without cross-session capability, it does not add enough distinct value to justify a separate product path.

## What Stays

The following capabilities remain important and should not be removed:

- EvidenceRecord and InsightRecord capture
- AnalysisSpec and analysis state
- chart artifacts and chart validation
- task tracking for analysis workflow
- conversation export
- conversational synthesis of current session context and findings

These are analysis-quality foundations. They support reliable answers and will also support any future cross-session dossier feature.

Conversation export should stay limited to reliable formats for now: HTML and Markdown. PDF export is removed from the current product surface because usage is low and the current PDF output is unreliable. Reintroduce PDF only as part of a future redesigned export/dossier workflow.

## What Goes

Remove or stop exposing these report artifact features:

- `generate_analysis_brief`
- `generate_formal_report`
- deprecated `generate_report`
- PDF conversation export
- web buttons for brief/formal reports
- web buttons for PDF conversation export
- CLI `/report brief` and `/report formal`
- CLI `/export pdf`
- capability metadata that advertises brief/formal report artifacts
- project skill dependencies that require formal report generation
- prompt guidance that treats comprehensive analysis as ending with formal report generation

If deletion creates too much test churn in one step, the implementation may first hide product entry points and deprecate the tools internally. The target state is still removal from the product surface and from the agent's normal tool vocabulary.

## Current-Session Synthesis

The replacement for current-session formal report is not a new artifact. It is a conversational behavior:

When the user asks for "summarize the current analysis", "give me a complete conclusion", "synthesize what we have found", or similar, the agent should synthesize:

1. the user's stated goal and constraints
2. loaded datasets and relevant data scope
3. completed analysis steps
4. EvidenceRecord and InsightRecord findings
5. validated charts when useful
6. limitations, uncertainty, and missing evidence
7. recommended next analysis or action

The output should be readable by both business and analytical users: business-facing conclusion first, then evidence and method detail. It should not require a separate report command.

## Future Cross-Session Feature

Do not evolve the current formal report into the future report system. Design a new feature later when requirements are clearer.

Possible future names:

- analysis dossier
- cross-session synthesis
- deliverable builder
- analysis portfolio

Likely future scope:

- select multiple sessions or projects
- merge EvidenceRecords, charts, and key conversation conclusions
- deduplicate findings
- identify conflicts between sessions
- generate an auditable deliverable from selected evidence
- preserve links back to source sessions and artifacts

This is intentionally out of scope for the current implementation.

## Intent Recognition Status

Intent recognition remains a research and evaluation topic only.

Do not implement the previously proposed semantic planner or capability router now. Keep the current classifier and tool activation behavior unchanged except where report tools are removed from the visible product surface.

Before any future intent redesign:

1. collect real user turns and failure cases
2. build an evaluation set
3. run any new planner in shadow mode
4. compare old and new behavior on classification, tool routing, latency, and final answer quality
5. only then decide whether runtime replacement is justified

## Implementation Phases

### Phase 1: Product Surface Cleanup

1. Remove brief/formal report buttons from the web workbench.
2. Remove PDF conversation export from the web workbench and API capability matrix.
3. Change single-reply Markdown export so it downloads an `.md` file instead of copying text to the clipboard.
4. Remove or rewrite CLI `/report` behavior so it no longer advertises brief/formal report generation.
5. Keep HTML and Markdown conversation export as the basic export mechanism.
6. Update capability metadata so brief/formal reports are not advertised as active product capabilities.

### Phase 2: Tool And Prompt Cleanup

1. Remove report tools from normal tool vocabulary or mark them internal/deprecated during transition.
2. Remove prompt guidance that asks comprehensive analysis to end with `generate_formal_report`.
3. Update project skills so full analysis ends with conversational synthesis and evidence-backed conclusions, not a formal report artifact.
4. Update tests that assert brief/formal report availability.

### Phase 3: Current-Session Synthesis Quality

1. Ensure `get_analysis_summary` exposes enough state for conversation-mode follow-up and synthesis.
2. Strengthen prompt guidance for current-session synthesis.
3. Add tests for "summarize current analysis" requests.
4. Verify synthesis includes conclusions, evidence, methods, caveats, and next steps without requiring report tools.

## Acceptance Criteria

- Users can ask for a complete analysis or current-session summary and receive a comprehensive conversational synthesis.
- The default UI no longer presents brief/formal report generation.
- The CLI no longer encourages brief/formal report generation as a separate analysis path.
- Conversation export remains available.
- Conversation export supports HTML and Markdown, not PDF.
- Single-reply Markdown export creates an `.md` document instead of duplicating copy-to-clipboard behavior.
- EvidenceRecord, InsightRecord, chart artifacts, task state, and analysis state remain intact.
- Intent recognition behavior is not changed as part of this report cleanup.
- Future cross-session report/dossier work is left unblocked by the old formal report concept.
