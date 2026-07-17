# Outcome Quality Model

Step 22 introduces `OUTCOME_SCORE_V1`, a deterministic score for operational output quality after publish preparation/publish.

It is not marketing attribution, engagement prediction, or ML. It is an explainable signal for improving source selection, preset use, routing, and scheduling.

## Components

Each component has raw inputs, subscore, weight, and weighted contribution.

- `publish_success_quality` - whether the draft reached a confirmed external published state.
- `processing_stability` - render/publish warnings and errors.
- `risk_noise_penalty` - open risk flags, especially high/blocking flags.
- `routing_fit_bonus` - whether assigned account matches the account actually used.
- `manual_intervention_penalty` - transcript/translation warning flags as a proxy for manual touch.
- `operator_feedback` - operator label after reviewing/publishing output.

## Labels

- `strong`: 80+
- `usable`: 65-79
- `needs_work`: 45-64
- `weak`: below 45

## Canonical Source

Scores are computed on read from existing tables:

- `PublishDraft`
- `PublishAttempt`
- `RenderOutput`
- `RiskFlag`
- `TranscriptSegment`
- `TranslationSegment`
- `OperatorFeedback`

No warehouse or summary table is introduced in phase 1.

Outcome summaries aggregate only drafts with real outcome signal:

- at least one publish attempt
- canonical publish state
- terminal publish draft state such as `PUBLISHED`, `FAILED`, or `NEEDS_ATTENTION`
- operator feedback

Individual READY drafts can still be inspected, but they do not distort source/preset/account trends until there is post-publish or feedback evidence.

## Limits

Outcome score does not prove audience performance. It only measures whether the internal pipeline produced stable, publishable outputs with low manual friction.
