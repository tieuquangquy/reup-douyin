# Pipeline Outcome Feedback

Pipeline outcome feedback connects final publish results back to earlier selection choices.

## Current Signals

The phase 1 dashboard can combine:

- `PublishDraft` status and canonical publication state
- `PublishAttempt` failure/reconciliation state
- `VideoCandidate.score`
- `VideoCandidate.preset_name`
- `SourceProfile.display_name`
- optional niche labels from metadata/filter config
- `OperatorFeedback`
- publish risk blocks from `RiskFlag`

## Grouping

The dashboard groups outcomes by:

- source profile
- niche
- preset

Each group shows:

- published count
- good feedback count
- weak feedback count
- reconciliation count
- average Reup Score when available

## Limits

The grouping is directional, not statistically rigorous. It helps the operator see patterns, but it should not replace manual review or real platform performance data.

Future analytics can add engagement metrics after connector publishing is stable.
