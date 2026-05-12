# Expert Analysis Flow And Playbook Design

## Goal

Upgrade the data analysis agent from evidence-backed summaries to evidence-backed expert analysis. The user-facing experience should feel like a professional analyst: it should translate business goals into an analysis plan, explore data, validate findings statistically, explain business meaning, and recommend next steps.

## Current Problem

Recent evidence-chain improvements improved report reliability but shifted the agent toward thin evidence summaries. In session `858bc2e86789`, the user provided a rich analysis goal, but the final output mostly listed metric values and short explanations. The system underused exploratory analysis, statistical inference, charts, method explanations, and recommended follow-up analysis.

The root issue is architectural: EvidenceRecord became too central in the user-facing output. Evidence should support analysis, not replace analysis.

## Target Flow

Default analytical turns should follow this flow:

1. Question framing
   - Identify whether the user asks for description, comparison, effect evaluation, diagnosis, attribution, prediction, decision support, or opportunity discovery.

2. Analysis plan
   - Produce or maintain an Analysis Plan with goals, metrics, dimensions, data mapping, methods, Visualization strategy, statistical checks, limitations, and expansion paths.

3. Exploratory analysis
   - Profile data, inspect trends, distributions, segments, anomalies, candidate factors, and exploratory charts.

4. Validation analysis
   - Validate key findings with statistical tests, correlation, effect size, confidence intervals, model fit, or explicit limitations when validation is not possible.

5. Evidence synthesis
   - Save validated or carefully bounded findings as EvidenceRecord.
   - Bind or promote key charts to evidence/insight charts.

6. Expert output
   - Default final answer includes core conclusions, metric table, statistical explanation, necessary charts or tables, business interpretation, limitations, recommendations, and next analysis directions.

## Report Tool Positioning

- `generate_analysis_brief` remains useful for quick summaries, intermediate exports, and gap summaries.
- It should not be the default final output for complete analysis or rich user goals.
- `generate_formal_report` should consume ExpertInsight, EvidenceRecord, and validated visualization artifacts for durable reports.
- The normal chat answer should still provide an expert analysis response, not only a report artifact path or evidence list.

## Playbook Taxonomy

Playbooks should be composable. Selection should produce a playbook stack instead of a single route.

### Foundation Playbooks

- Data Understanding: schema, quality, grain, feasible analyses.
- Metric Overview: KPI table, distributions, top contributors.
- Trend Analysis: trend, seasonality, period comparison, change points.
- Distribution Analysis: skew, long tail, outliers, ranges.
- Segment Comparison: group comparison, user or product strata.
- Correlation And Driver: Pearson/Spearman, candidate drivers, model fit.
- Contribution Decomposition: dimension contribution and excluded hypotheses.
- Funnel Analysis: step conversion and drop-off.
- Cohort And Retention: repeat behavior, retention, lifecycle.
- Forecast And Scenario: forecast, what-if, sensitivity.

### Business Problem Playbooks

- Effect Evaluation: feature, campaign, policy, or intervention impact.
- Business Diagnosis: why a metric changed or degraded.
- Revenue And Profitability: revenue, cost, ROI, net value.
- User Behavior Analysis: frequency, amount, preference, paths, segments.
- Product Feature Analysis: feature adoption, usage, value, downstream behavior.
- Growth Opportunity: expansion dimensions, optimization ideas, next experiments.
- Risk And Anomaly Review: data or business anomalies and operational risks.
- Decision Support: continue/stop/adjust decisions with evidence and assumptions.

### Domain Playbooks

Domain playbooks should be added gradually:

- Ecommerce Promotion: coupons, discount, subsidy, promotion ROI.
- Membership Or Subscription: cards, packages, subscription value, renewal.
- Ads Monetization: ad revenue, placements, ARPU, fill/rate tradeoffs.
- Game Economy: in-app purchases, items, paying user behavior.
- SaaS Retention: renewal, churn, expansion, cohort health.

## Playbook Quality Contracts

Each playbook must define:

- Required data
- Minimum viable analysis
- Visualization strategy
- Required statistical evidence
- Required limitations
- Output sections
- Forbidden overclaims

Examples:

### Effect Evaluation

- Define treatment/exposure, outcome metric, observation window.
- Check whether a control group exists.
- With control group: prefer A/B, DID, matching, or causal methods.
- Without control group: only allow observational before-after conclusions.
- Require sample size, effect size, significance or confidence interval when feasible.
- Define a visualization strategy for trend context and before/after comparison when charts improve explanation.
- Must state causal limitations.

### Revenue And Profitability

- Split revenue, cost, net value, and missing cost items.
- Require cost/revenue definitions and time scope.
- Define a revenue/cost visualization or table strategy.
- Include sensitivity analysis when assumptions are incomplete.

### User Behavior Analysis

- Analyze frequency, amount, distribution, repeat behavior, and segments.
- Require observation window and user grain.
- Define distribution or segment comparison visualization when it improves explanation.
- Avoid claiming behavior change without comparison design.

### Growth Opportunity

- Identify high-leverage dimensions or segments.
- Recommend follow-up analyses and data needed.
- Distinguish evidence-backed opportunities from hypotheses.

## Session 858bc2e86789 Expected Playbook Stack

For a savings-card impact analysis, selection should include:

- Product Feature Analysis
- Effect Evaluation
- Revenue And Profitability
- User Behavior Analysis
- Trend Analysis
- Segment Comparison
- Correlation And Driver
- Growth Opportunity

Expected outputs:

- Direct net revenue: card sales, coupon cost, net value.
- Purchase preference: monthly vs weekly card share and revenue contribution.
- Repeat purchase: repeat rate and observation-window caveat.
- Before/after behavior: frequency, ARPU, order value, distribution.
- Trend context: whether changes started before launch.
- Statistical validation: p-value, effect size, correlation, model fit, or explicit reason unavailable.
- Causal boundary: lack of non-card control group.
- Charts: KPI comparison, revenue/cost composition, trend, distribution/segment, correlation heatmap where useful.
- Next analyses: control-group DID/PSM, longer window, coupon usage sensitivity, segment-level lift, monthly-card optimization.

## Implementation Phases

### Phase 1: Quality Stopgap

- Reduce default use of `generate_analysis_brief`.
- Require statistical details in core EvidenceRecord.
- Let validated exploratory charts appear as supplemental charts.
- Add a golden scenario for session-like savings-card analysis.

### Phase 2: Playbook Expansion

- Add business problem playbooks: Effect Evaluation, Revenue And Profitability, User Behavior Analysis, Product Feature Analysis, Growth Opportunity.
- Support playbook stacks.
- Merge Visualization strategy, statistical requirements, and output sections into AnalysisSpec.

### Phase 3: Completeness Gate

- Add an Analysis Completeness Check before final output.
- For complete analysis, require sufficient evidence, presentation sufficiency, method explanations, statistical checks, limitations, and next directions.
- If incomplete, continue analysis or explain explicit gaps.

## Open Design Decisions

- Whether the agent should always show the Analysis Plan before executing, or only for complex analysis.
- Whether completeness gates should block final output or downgrade confidence and list gaps.
- How visualization strategy should decide between chart, table, and text per problem type.
- Whether playbook stacks should be deterministic rules first or LLM-assisted after rule filtering.



