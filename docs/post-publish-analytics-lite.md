# Post-Publish Analytics Lite

Step 20 adds an operational analytics layer after publish. It is intentionally small: the goal is to know publish health and feed operator judgment back into source/preset decisions.

## Scope

Analytics-lite answers:

- how many publish attempts ran;
- how many succeeded, failed, or need reconciliation;
- which Page/account is unhealthy;
- which drafts are ready but not published;
- which publish drafts are blocked by risk;
- which source/profile/preset/niche groups look promising;
- what operator feedback says about published outputs.

This analytics-lite dashboard itself does not calculate deep engagement. Publication-level
views, likes, comments, shares and growth velocity are now captured by the separate
`Publication Metrics V1` authority. Conversion and revenue attribution remain out of scope.

It also does not make automatic ranking or publish decisions. Any source/preset/niche signal is directional operator feedback, not a scoring model.

## Source Of Truth

Existing tables remain source of truth:

- `PublishDraft`
- `PublishAttempt`
- `PlatformAccount`
- `SourceVideo`
- `SourceProfile`
- `VideoCandidate`
- `RiskFlag`

`OperatorFeedback` is the only new table. It records human feedback on a source video, render output, publish draft, or publish attempt.

## Computation Strategy

Phase 1 computes dashboard summaries on read. No warehouse, materialized view, or analytics snapshot table is introduced yet.

This keeps the system simple for local operation. If dashboard queries become slow with real data, the next step is a daily summary table, not a BI stack.

## Guardrails

- Do not add platform engagement scraping here.
- Do not add marketing attribution here.
- Do not auto-adjust Reup Score from feedback in phase 1.
- Keep new widgets tied to operator actions: reconcile, publish, investigate, or record feedback.
