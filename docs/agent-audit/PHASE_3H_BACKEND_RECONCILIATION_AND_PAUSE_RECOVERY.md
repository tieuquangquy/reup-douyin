# Phase 3H Backend Reconciliation and Pause Recovery

## Scope

Phase 3H fixes three targeted `Collecting videos` regressions without changing scanner discovery, auto-scroll behavior, backend validation, `/douyin-extension/full-modal-harvest` payload shape, item semantics, calibration storage, or queue reset scope.

## Backend reconciliation after Scan Profile

After Scan Profile / Refresh Profile builds the canonical profile queue, the extension now performs a non-blocking Capture Inbox reconciliation for the current profile.

Data sources:

- `runtime.listCaptureSessions()` / backend capture session list.
- `runtime.listCaptureSessionItems(captureSessionId)` / Capture Inbox items for matching sessions.

Profile restriction:

- Candidate backend sessions must match the current profile via the existing profile-safe session matcher.
- Matching uses normalized profile URL / `sec_uid` behavior already owned by the Phase 3E session verification path.
- Query parameters such as `modal_id` are ignored by the profile URL normalization path.

Item matching:

- Preferred key: `aweme_id`.
- Backend fallback item keys: `source_video_external_id`, `video_external_id`, `external_id`.
- Matched queue items are marked `already_collected` / complete locally and receive backend item identifiers where available.

Failure behavior:

- Backend lookup failure does not fail the scan.
- Reconciliation status is written to diagnostics so the operator can distinguish `success`, `failed`, or `unavailable`.

## Count behavior

Before Phase 3H, Reset -> Refresh Profile could show backend-existing same-profile videos as all-new because reset cleared local queue state and the scan count contract did not reconcile against Capture Inbox.

After Phase 3H:

- Backend-existing same-profile queue items count as already collected.
- Unmatched scanned items remain pending/actionable.
- Existing retry/incomplete semantics are preserved for actionable items.

## Collect backend write diagnostics

The one-item Start/Continue Collecting path still uses Phase 3E profile-safe capture session verification and still writes through `/douyin-extension/full-modal-harvest`.

Additional redacted diagnostics now indicate whether the backend write was attempted and whether it succeeded, failed, or saved without verification:

- `collect_backend_write_attempted`
- `collect_backend_write_status`
- `collect_backend_write_success_count`
- `collect_backend_write_failed_count`

These fields intentionally do not include secrets, cookies, raw credentials, raw DOM, or full private local paths.

## Pause / Resume recovery

Before Phase 3H, stale state could display `Paused` and `Resume collecting` while also blocking resume with `No paused run to resume`.

After Phase 3H:

- Resume is shown only when `resume_available === true` and the collection state is actually resumable.
- Stale non-resumable paused state is recovered to an idle safe state while preserving queue, calibration, and session state.
- Pause clicks are guarded when no active `collect_videos` run exists.
- Footer pause/resume routing only resumes real resumable paused runs and only pauses active collection runs.

Recovery diagnostics include:

- `stale_pause_state_recovered: "yes"`
- `stale_pause_recovery_reason: "paused_without_resume_available"`

## Tests

Focused coverage was added/updated for:

- Backend reconciliation diagnostics and hooks in the whole-profile controller source tests.
- Collect backend write diagnostics in the whole-profile controller source tests.
- Stale non-resumable paused state selecting Start/Continue Collecting instead of disabled Resume.
- Readiness selector marker expectations aligned with the current `22C-11B` primary action selector.

## Manual validation checklist

After loading the built extension:

1. Reset only the current run, preserving calibration.
2. Refresh / Scan Profile on a profile that already has Capture Inbox items.
3. Confirm backend-existing same-profile items count as already collected instead of all new.
4. Click Start/Continue Collecting.
5. Confirm new/uncollected items save through `/douyin-extension/full-modal-harvest`.
6. Confirm debug diagnostics include backend reconciliation fields and collect backend write fields.
7. Click Pause only during an active collection and confirm Resume appears only when a paused run is actually resumable.
8. If stale paused state is present, confirm the popup recovers to Start/Continue Collecting instead of disabled Resume.
