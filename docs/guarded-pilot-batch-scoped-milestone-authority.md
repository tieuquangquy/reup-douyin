# Guarded Pilot Batch-Scoped Milestone Authority

This note documents the durable batch-scoped artifact keys, the additive highest-passed-milestone
authority model, the treatment of an unrecoverable earlier batch, and the feature-flag decision for
the guarded hybrid Start-Collecting Pilot pipeline in the Douyin capture extension
([`apps/extension-douyin-capture/src/popup.ts`](../apps/extension-douyin-capture/src/popup.ts)).

## Problem

Pilot 10 and Pilot 50 production and post-verify artifacts were both written to a single shared
"latest" alias (`hybridStartCollectingPilotLatestProduction` /
`hybridStartCollectingPilotLatestPostVerify`). A later batch (Pilot 50) overwrote the earlier batch
(Pilot 10) artifact, so:

- batch-scoped reads could not recover the Pilot 10 milestone once Pilot 50 ran, and
- `next_action` in the Compact Guarded Pipeline Status regressed to `run_guarded_start_collecting_pilot_10`
  even though a higher milestone (Pilot 50 post-verify) had already passed, contradicting the
  Per-Batch Milestone Authority Diagnostic.

## Batch-Scoped Storage Keys

Each pilot batch size now persists under its own durable key, in addition to the shared "latest"
alias that is kept only for backward compatibility and "latest run" diagnostics:

- Production source: `hybridStartCollectingPilotLatestProductionBatch{batchSize}`
  (e.g. `...Batch10`, `...Batch50`) written by
  [`persistGuardedHybridStartCollectingPilotSourceFromSummary()`](../apps/extension-douyin-capture/src/popup.ts).
- Post-verify summary: `hybridStartCollectingPilotLatestPostVerifyBatch{batchSize}` written by
  [`persistGuardedHybridStartCollectingPilotPostVerifySummary()`](../apps/extension-douyin-capture/src/popup.ts).

Queue Completion 10 (`hybridStartCollectingQueueCompletionPilotLatest`) and Queue Completion 50
(`hybridStartCollectingQueueCompletionPilot50Latest`) were already written to distinct keys, so they
are inherently batch-scoped and a later batch cannot overwrite an earlier one.

Milestone-authority reads prefer the batch-scoped key first, then fall back to the shared latest
alias only when it still matches the requested batch size, then to the Queue Completion 10 derived
milestone. Because each batch owns its own key, a later batch can never overwrite or invalidate an
earlier batch's milestone artifact.

## Additive Highest-Passed-Milestone Authority

`next_action` is derived from the highest passed milestone, never from raw artifact presence, so it
cannot regress behind a milestone that already passed. Priority (highest first):

1. `guarded_start_collecting_pilot_50_post_verify`
2. `queue_completion_pilot_10_post_verify`
3. `guarded_start_collecting_pilot_10_post_verify`

The Compact Guarded Pipeline Status `nextSearchStart` resumes at the follow-up step for the highest
passed milestone (Pilot 50 passed → resume at `queue_completion_pilot_50`). The Compact Guarded
Pipeline Status now emits a `milestone_authority` block with `highest_passed_milestone`, the
per-batch authority booleans, and `next_action_regression_to_pilot_10_prevented`. The Per-Batch
Milestone Authority Diagnostic emits `compact_status_highest_passed_milestone` and
`diagnostic_and_compact_status_consistent` so the two exports can be checked for agreement.

## Treatment of an Unrecoverable Earlier Batch (Decision: Option a)

When the earlier batch-10 milestone artifact is unrecoverable (shared alias was overwritten by a
later batch before batch-scoped keys existed, and no batch-scoped batch-10 key was ever written) but
Pilot 50 and Pilot 50 post-verify have passed, the **higher Pilot 50 milestone supersedes the earlier
batch** as sufficient authority for the next eligible action. This is option (a).

This is never a silent regression:

- The batch-10 compact steps are explicitly marked with
  `superseded_by_higher_milestone: "guarded_start_collecting_pilot_50_post_verify"` and a
  `batch_10_recovery_recommendation` describing the optional one-time operator re-run.
- The `milestone_authority` block sets
  `earlier_batch_unrecoverable_superseded_by_pilot_50: true` and an `earlier_batch_treatment`
  explanation.
- No pilot is auto-rerun and no backfill is performed. If explicit batch-10 authority is required,
  the operator may optionally re-run Pilot 10 once; this is a recommendation, never automatic.

Going forward, because batch-scoped keys are now written on every pilot run, this unrecoverable
state only applies to artifacts produced before this change; new runs always have a recoverable
per-batch key.

## Feature-Flag Decision

The pilot and queue-completion feature flags
(`hybridEstimatedViewsStartCollectingPilotEnabled`,
`hybridStartCollectingPilotQueueCompletionEnabled`,
`hybridStartCollectingPilot50QueueCompletionEnabled`) are **operator-default-false by design**, not
code-disabled. Their readers
([`hybridStartCollectingPilotQueueCompletionEnabled()`](../apps/extension-douyin-capture/src/popup.ts)
and siblings) return the live checkbox state when the popup control is present, otherwise the stored
`chrome.storage.local` value, defaulting to `false` when unset.

A build showing all flags `false` therefore reflects an operator who has not enabled them (or fresh
storage), not a regression that disabled them in code. To progress, the operator enables the
relevant flag in the popup before running the gated action. This default-off posture is intentional:
each guarded write to the production backend stays opt-in.

## Safety Invariants (unchanged)

- `estimated_views` is never copied into `view_count`.
- Full queue completion remains disabled (`full_queue_completion_enabled: false`).
- Queue completion uses exact aweme-id-only matching.
- The Per-Batch Milestone Authority Diagnostic and storage inventory are read-only: no storage
  mutation, no stage rerun, no backend writes, and no backfill.
