# Analysis Quality Regression Rubric

## Purpose

This rubric protects analytical delivery from two fatal defects:

1. a material claim has no supporting evidence;
2. a claim uses a relationship that is rejected, unconfirmed, or time-incompatible.

It is a scenario-validation helper, not a runtime synthesis policy. It must not
be used to replace EvidenceRecord validation, relationship validation, analyst
judgment, or domain-specific review.

## Decision Model

`score_analysis_quality()` returns:

- `claim_delivery_ready`: false when a fatal claim-level defect exists;
- `global_publish_gate`: false when any fatal blocker exists;
- `blockers`: stable reason strings for audit and regression comparison;
- `dimensions`: hard integrity diagnostics plus caller-supplied soft dimensions;
- `notes`: review context that does not silently change readiness.

There is deliberately no total score. Strong presentation, broad exploration,
or numerous passing dimensions cannot compensate for an unsupported material
claim or invalid relationship use.

Soft warnings remain visible without automatically blocking delivery. This
prevents arbitrary thresholds from narrowing analytical depth or encouraging
work that optimizes a score instead of answering the business question.

## Relationship Boundary

Relationship validation is diagnostic. A rejected or unconfirmed relationship
does not block independent analysis and is safe to report as a limitation. It
blocks delivery only when the relationship is used to support a material claim.

The real savings-card scenario demonstrates this distinction. The two files
have high user-key coverage, but both sides contain duplicate users, producing
a many-to-many relationship and row multiplication risk. That result is useful
relationship evidence, but it is not authority to execute a join.

## Scenario Coverage

- Game A banner, IAP, and rewarded-video files: independent evidence followed
  by synthesis, with no executed join.
- Savings-card orders and recent flow: candidate-key, cardinality, coverage,
  null-rate, row-multiplier, grain, and time-scope diagnostics.
- Unrelated files: false-join prevention unless an explicit business key and
  validated analytical need are supplied.
- Fault injection: duplicate keys, missing keys, time-scope mismatch, and
  many-to-many risk.

The scenario runner only validates manifest readiness and writes an auditable
JSON result under `artifacts/multifile-quality/<timestamp>/results.json`. It
does not modify source spreadsheets, execute joins, score claims, or publish an
analysis.

## Interpreting Results

- `global_publish_gate=false` means the affected delivery must be corrected,
  narrowed, or explicitly withheld.
- `global_publish_gate=true` means no modeled fatal blocker was found. It does
  not certify that the analysis is complete, professionally sufficient, or
  correct in dimensions the scenario did not inspect.
- A soft warning should trigger review in context. It must not be converted to
  a universal numeric threshold without scenario evidence and explicit design
  review.
