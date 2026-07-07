# Workbench UX Simplification Review

## Outcome

The Workbench is now the only session trust surface. The former Trust Inspector
projection, historical route picker, active-bundle summary, duplicate risk
lists, and hidden compatibility bindings were removed rather than retained as
a parallel interface.

The API contract is intentionally bounded:

```text
status
session_id
updated_at
workbench.multifile_analysis
workbench.details
```

It does not publish artifact paths, task references, evidence signatures, or
legacy history collections.

## Primary Sections

The current-analysis tab contains exactly four user-value sections:

1. **Data Understanding** shows datasets, row counts, grain, fields, quality
   findings, and analysis constraints.
2. **Relationships** shows relationship status, analytical value, and risk. A
   relationship remains diagnostic and never authorizes an automatic join.
3. **Analysis Directions** shows supported or exploratory directions as
   read-only suggestions. Selecting a direction does not submit or populate a
   new request automatically.
4. **Answer Coverage** shows evidence and verified/failed claim counts,
   supported claims, and limitations.

## Secondary Details

The validation-details tab contains information that helps explain or debug a
current result without competing with the primary view:

- scope decisions with assignment, eligibility, reason, and task count;
- active confirmation question and blocking reason;
- verification status and claim/failure/downgrade counts;
- bounded relationship evidence and uncertainty notes.

Raw task IDs and verification signatures are replaced by counts. Relationship
evidence is sourced from the same Workbench relationship model used by the
primary section, avoiding a second diagnostic projection.

## Removed Duplicates

- top-level datasets, routes, risks, hypotheses, recommendations, scope counts,
  active bundle, file relationships, and history projections;
- the fifth, status-only Workbench panel above the four primary sections;
- historical route selection and its input-population behavior;
- legacy file-assignment and relationship-formatting JavaScript helpers;
- raw artifact path text in the outputs tab;
- unused Trust Inspector data, risk, and route CSS;
- duplicated artifact hydration embedded in view code. Hydration now lives in
  `artifact_refs.py` and is reused by analysis entry, hypotheses, and route
  capabilities.

## User Tasks Supported

- understand which data is available and at what grain;
- see whether relationships are useful, risky, or still uncertain without
  implying that files should be joined;
- review plausible analysis directions without accidental execution;
- determine which claims have evidence and what remains unsupported;
- inspect scope, confirmation, and verification details when a result needs
  explanation or debugging;
- open named outputs without exposing internal storage paths as visible text.

## Remaining Caveats

- The side Workbench remains desktop-oriented and is hidden below the existing
  `xl` breakpoint. At 390px the pre-existing application shell also overflows
  horizontally because the navigation rail remains fixed. A mobile inspection
  flow and shell need a separate interaction design rather than compressing
  this dense panel.
- The browser still reports the existing Tailwind CDN production warning.
  Production packaging should compile Tailwind locally before external release.
- Relationship cardinality and coverage metrics appear only when upstream
  relationship records provide them. This review does not infer or fabricate
  missing metrics in the UI.
