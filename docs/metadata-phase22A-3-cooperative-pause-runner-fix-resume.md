# Phase 22A-3 Cooperative Pause Runner Fix Resume

## Phase

Phase 22A-3 — Fix cooperative Pause in Collecting runner.

## Status

Implementation and focused tests are complete. Required documentation was added in this file and the companion fix log.

## Behavior After This Phase

When the operator clicks Pause during Start Collecting:

1. The popup immediately writes a canonical pause request.
2. The collection workflow enters `pausing`.
3. The active button displays `Pausing...` and is disabled while the runner reaches a safe checkpoint.
4. The runner checks pause state at safe boundaries instead of killing the tab or interrupting a write.
5. The runner persists a paused state with acknowledgement diagnostics.
6. Resume clears stale pause request flags and continues from the next pending queue target.

## Resume Semantics

Paused collection state keeps `resume_from_index` aligned with the next pending or checkpoint target. Resume starts from that persisted queue position and clears these request flags before running:

- `stop_requested`
- `pause_requested`
- `pause_requested_at`
- `pause_reason`

The acknowledgement fields and pause diagnostics remain available on the paused state for operator/debug visibility until the resumed run transitions forward.

## UI Contract

The scanner UI now follows these states:

- `running` shows `Pause`.
- `pausing` shows disabled `Pausing...`.
- `paused` shows `Resume`.
- `idle` with a ready queue shows `Start Collecting`.

The active visible button is marked in both popup HTML and popup TypeScript with:

```txt
22A-3 ACTIVE SCANNER PAUSE BUTTON
```

## Storage Diagnostics Contract

Immediate pause click diagnostics include:

```txt
last_scanner_action = "pause"
last_scanner_result = "clicked"
pause_requested = true
pause_requested_at = now
pause_source = "main_pause_button"
```

Runner acknowledgement diagnostics include the safe checkpoint, acknowledged timestamp, target index where available, aweme id where available, and runner location.

## Validation Commands

Completed:

```txt
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
```

```txt
npm --workspace @reup-douyin/extension-douyin-capture run test
```

Pending at the time this resume note was written:

```txt
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Non-Goals

This phase did not add crawler behavior, video processing, scoring/filtering, database schema changes, queue infrastructure, or auto-publishing integrations. It only fixes cooperative pause behavior in the current extension whole-profile collection runner.
