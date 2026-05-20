# Evidence-Linked Charts Design

## Goal

Make analytical charts accurate, evidence-bound, and visible at the point where they support a conclusion. Interactive charts must come from verified `create_chart` artifacts, while Mermaid remains reserved for structural or conceptual diagrams.

## Scope

This design addresses chart generation, chart metadata, chat rendering, and formal report rendering. It does not rebuild the analysis engine or migrate old session artifacts in place.

## Current Problems

Historical sessions show four recurring problems:

- Chart text and chart visuals can diverge, especially after a `create_chart` failure.
- Some chart metadata claims grouping or evidence purpose that the rendered chart does not actually support.
- Chat turns render chart artifacts before the assistant's final markdown, so charts are detached from the conclusion they explain.
- Formal reports append all chart HTML after the markdown body, so evidence charts are not placed next to the matching insight or evidence record.

## Design

`create_chart` remains the only supported path for data-backed interactive charts. The tool will validate chart intent more strictly, record metadata that can be trusted by downstream renderers, and return enough structured information for the web UI to show the chart as a turn artifact.

Assistant markdown may reference generated charts with a simple chart reference syntax:

```text
[[chart:<chart_id_or_artifact_path>]]
```

The frontend will replace those references with inline interactive chart blocks. A chart that is generated in the same turn but not referenced by the markdown will appear after the markdown under a supplemental charts section. This preserves visibility without forcing every artifact to the top of the answer.

Formal reports will use `evidence_ids` and `InsightRecord.chart_ids` to place validated charts under the corresponding insight or evidence section. Unmatched valid exploratory charts can still appear in a supplemental section.

## Validation Rules

The chart contract should reject or warn on cases that made past sessions misleading:

- `color_col` must either affect the rendered chart or be rejected for that chart type.
- `purpose=evidence` and `purpose=insight` require at least one `evidence_id`.
- A title that claims distribution, rate, CTR, comparison, or trend must match the supplied columns closely enough to be credible.
- Data-backed chart failures must not recommend Mermaid fallback. The assistant should fix chart inputs or show a verified numeric table.

## Frontend Behavior

The chat UI should render in this order:

1. Assistant markdown content.
2. Inline chart blocks where `[[chart:...]]` references appear.
3. Supplemental chart blocks for valid turn artifacts that were not referenced.

Each chart block should show the chart title, artifact type, validation warnings when available, and the interactive iframe. The side artifact list remains available as a session-level index.

## Report Behavior

Formal reports should place chart HTML near matching insights instead of appending every chart at the end. The existing validated chart loader can be extended to group entries by chart id and evidence id. Charts without a matching insight or evidence stay in an appendix-like supplemental section.

## Testing

Tests should cover:

- Chart validation rejects unsupported or misleading metadata.
- Grouped charts actually produce grouped Plotly traces.
- Chat reconstruction and rendering support inline chart references and supplemental charts.
- Formal report HTML places evidence charts near their matching insight or evidence section.
