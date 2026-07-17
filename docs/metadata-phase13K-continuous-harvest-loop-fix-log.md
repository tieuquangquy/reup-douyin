# Phase 13K Continuous Harvest Loop Fix Log

## Scope

Phase 13K is limited to `apps/extension-douyin-capture` harvest-state restoration and popup progress normalization.

In-scope:

- Canonical running/paused mapping for active harvest phases in popup progress normalization.
- Restore-path state projection so stored running status is not coerced into paused.
- Test coverage for active-phase running inference and stale-heartbeat pause fallback.
- Phase documentation and verification logs.

Out-of-scope:

- New crawler/processing behavior.
- Backend/API contract changes.
- Queue/storage architecture changes.

## Root Cause

Smart Harvest loop execution was already continuous in controller flow, but UI/restored-state normalization could misclassify active harvest progress as paused:

1. Restored progress conversion could map non-complete states into non-running status by default, causing `running: false` and paused display semantics after reload/resume.
2. Popup canonical status logic treated active phases (`extracting_metrics`, `loading_next_video`, `waiting_modal_change`, `flushing`) as paused when status fields were mixed or partially stale.

This produced operator-visible “auto-pause” behavior even while the queue should continue.

## Implementation

### 1) Restore-path status projection

Updated `storedStateToProgress` to preserve canonical `harvest_status` and derive `running` from that canonical status instead of coercing running to paused.

- File: `apps/extension-douyin-capture/src/contentScript.ts`
- Effect: restored progress now keeps running semantics when stored state indicates running; completion states remain canonicalized.

### 2) Popup canonical running/paused logic

Updated popup normalization and canonical status derivation:

- Running canonicalization now converts stale paused/stopped/terminal phase badges into `harvesting` so running status cannot render with paused badge.
- Paused canonicalization now records `harvest_loop_inactive` when an active/raw-running state has stale heartbeat and no explicit stop reason.
- Active harvest phases now infer `running` (with heartbeat freshness check) instead of being auto-mapped to paused.

- File: `apps/extension-douyin-capture/src/popupProgress.ts`

## Behavioral Outcome (Phase 13K)

- Smart Harvest no longer appears as paused after each successful item during normal continuation.
- Popup remains running for active queue transitions until a true blocker or completion state occurs.
- Stale heartbeat still transitions to paused inactive-loop state.
- Resume keeps multi-item continuity instead of one-item-then-paused behavior caused by display/status mismatch.

## Tests Added/Updated

Updated extension tests in:

- `apps/extension-douyin-capture/src/popupProgress.test.ts`

Added assertions for:

- Running canonical status clears stale paused phase.
- Active harvest phase inference resolves to running.
- Stale heartbeat still resolves to paused with inactive-loop reason.

## Verification Commands (Executed)

Executed from repository root:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

All three commands succeeded.

## Files Changed in Phase 13K

- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popupProgress.ts`
- `apps/extension-douyin-capture/src/popupProgress.test.ts`
- `docs/metadata-phase13K-continuous-harvest-loop-fix-log.md`
- `docs/metadata-phase13K-continuous-harvest-loop-fix-resume.md`
