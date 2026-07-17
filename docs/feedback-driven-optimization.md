# Feedback-Driven Optimization

Step 22 closes a small loop from real operation back into pipeline decisions.

## Signal Sources

The optimization layer uses:

- source profile and source video metadata
- candidate preset and Reup Score
- transcript/translation warning flags
- render and publish warnings
- risk flags
- publish attempt and canonical publication state
- operator feedback
- account health and assignment data

## What It Produces

- outcome summaries by source profile, niche, preset, account, and score bucket
- preset effectiveness hints
- routing hints with confidence and reasons
- scheduling slot hints
- manual touch hotspots
- semi-automation guardrail decisions

## What It Does Not Do

- no automatic weight rewriting
- no ML model training
- no full autopublish
- no cross-platform connector logic
- no deep marketing analytics

The output is operator-assist data. Automation remains guarded and explainable.

Trend summaries intentionally exclude drafts with no publish attempt, terminal state, or operator feedback. This keeps optimization based on observed outcomes rather than ready-but-untested backlog.
