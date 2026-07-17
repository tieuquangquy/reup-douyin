# Phase 21D-15 Waiting Profile Ready Stall Fix Log

## Summary

Phase 21D-15 fixes the Douyin extension Scan Profile path that could stall at `waiting_profile_ready` with `Profile scan ready: no` and `Scan rounds: 0` even when the active tab was already on a Douyin profile page with visible profile video links.

The workflow now treats profile readiness more tolerantly, records explicit waiting and scanner-start diagnostics, starts the canonical profile scanner from the verified profile state, and returns friendlier missing-grid failures when the scanner cannot find profile cards.

## Scope

Touched extension-only Scan Profile files:

- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`

Non-goals preserved:

- No backend contract changes.
- No classification endpoint changes.
- No Capture Inbox UI changes.
- No collector/save runner rewrite.
- No crawler or video-processing implementation.
- No V2/legacy runtime promotion.
- No fake scan results.

## Implementation Notes

### Tolerant profile readiness

The popup-side profile readiness probe now accepts a profile page as scan-ready when the URL matches the expected profile, no modal id is present, and either the detector is ready or strong profile signals are present.

Strong signals include:

- profile grid candidates
- validated aweme/video candidates
- visible profile links

This prevents a loaded profile grid from being blocked solely because one detector signal is slow or incomplete.

### Waiting profile ready diagnostics

The controller now persists a `waiting_profile_ready` checkpoint before warmup begins. Diagnostics include:

- `waiting_profile_ready_started_at`
- `waiting_profile_ready_expected_profile_url`
- `waiting_profile_ready_page_type`
- `waiting_profile_ready_tab_id`
- warmup completion and profile readiness details

Warmup timeout handling now fails explicitly as `profile_scan_timeout` only when timeout indicators are present, instead of treating every plain missing-grid scanner response as a warmup timeout.

### Explicit scanner runner start

Before calling the canonical profile scanner, the controller now writes a `scanning_profile` state with scan workflow state set to running and runner-start diagnostics persisted to both verify and profile scan diagnostics.

Runner-start diagnostics include:

- `scan_runner_started`
- `scan_runner_started_at`
- `scan_runner_action`
- `scan_runner_tab_id`
- `expected_profile_url`

These diagnostics are preserved into the final verified state so a completed scan can prove the runner started and the workflow did not stall before scanning.

### Friendly missing-grid wording

Missing profile grid failures now use the user-facing message:

```text
Could not find profile video grid.
```

The next action asks the operator to refresh the Douyin tab and try Scan Profile again.

### Repair note

During implementation, a broad local replacement accidentally changed some `prepared` references to `scanRunning` in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`. This caused the focused workflow test to fail before verification completed.

The invalid self-referential/out-of-scope references were repaired so `scanRunning` is only used after initialization and in the final verified state where preserving runner diagnostics is intended.

## Validation

Focused validation run so far:

```text
npx tsx src/wholeProfileHarvest.test.ts
```

Result: passed.

Full extension validation was also completed:

```text
npm test
npm run typecheck
npm run build
```

Result: passed.
