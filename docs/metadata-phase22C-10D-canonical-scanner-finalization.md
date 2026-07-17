# Phase 22C-10D - Canonical Scanner Finalization

## Deadlock Point

The active Scan Profile path reached `canonical_scanner_completed` in `apps/extension-douyin-capture/src/background.ts` inside `runCanonicalScanProfile22C10D`.

The deadlock shape came from a split write:

1. `persistCanonicalScanDiagnostics22C10D(..., "canonical_scanner_completed", ...)` wrote the transitional phase.
2. The code then parsed `response`, checked `verifiedCount`, and later called `finalizeCanonicalScanSuccess22C10D(...)`.
3. If the response was missing/malformed, or execution stopped between the transitional write and terminal write, storage stayed in:
   - `lastScannerResult = running`
   - `active_task = scan_profile`
   - `action_lock = scan_profile`
   - `scan_finalization_result = none`

## Fix

The canonical route is now versioned `22C-10D` and has a terminal-state contract:

- success
- incomplete
- failed

The orchestrator now:

- validates the content-script scanner response before queue adaptation;
- fails malformed/missing scanner responses as `canonical_scanner_completed_without_result`;
- records response parse diagnostics and response keys;
- records whether the queue adapter was invoked or why it was skipped;
- tracks whether a terminal state was persisted;
- uses a final `finally` guard to persist a failed terminal result if no terminal write happened;
- clears `active_task` and `action_lock` on every terminal path.

## Expected Count Incomplete

Expected-count shortfall now terminally finalizes as incomplete instead of staying running:

- `lastScannerResult = incomplete`
- `lastScannerError = profile_scan_incomplete_expected_count_not_reached`
- `scan_finalization_result = incomplete`
- `canonical_terminal_state = incomplete`
- `canonical_finalizer_ran = yes`
- `canonical_lock_release_ran = yes`

## Stale Recovery

Popup recovery now specifically detects stale canonical scans when:

- runtime starts with `22C-10`
- `lastScannerResult = running`
- phase is `canonical_scanner_completed`
- scan lock is still `scan_profile`
- no `scan_finalized_at`
- run age exceeds 90 seconds

It recovers as:

- `lastScannerError = canonical_scan_stale_running_recovered`
- `scan_finalization_result = recovered_failed`
- lock cleared
- next action returns to Scan Profile.

## Tests

Coverage added/updated for:

- valid canonical scanner result invokes queue adapter and clears lock;
- expected-count incomplete terminally finalizes and clears lock;
- missing scanner result after scanner completion fails as `canonical_scanner_completed_without_result`;
- finalizer diagnostics are stamped;
- stale canonical completed lock recovery is present;
- 22C-10D canonical message/version markers.

## Manual Retest

1. Rebuild extension and reload from `apps/extension-douyin-capture/dist`.
2. Refresh the Douyin profile tab.
3. Click Scan Profile.
4. Verify it reaches one terminal state:
   - success, incomplete, or failed.
5. Confirm these are never left after the run:
   - `lastScannerResult = running`
   - `action_lock = scan_profile`
   - `active_task = scan_profile`
   - `scan_finalization_result = none`
   - popup stuck on `Scanning...`.
