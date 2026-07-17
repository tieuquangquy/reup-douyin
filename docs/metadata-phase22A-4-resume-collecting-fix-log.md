# Phase 22A-4 Resume Collecting Fix Log

## Scope

Phase 22A-4 fixes active Resume behavior after a paused whole-profile collection checkpoint in the Douyin capture extension only.

## Intent

When the operator clicks Resume after Pause, the popup and controller now make the click visible immediately and continue the collection runner from the persisted checkpoint instead of appearing idle or stale.

## Files Changed

- `apps/extension-douyin-capture/src/popup.ts`
  - Routes active primary-card Resume and footer Resume through a dedicated resume handler.
  - Marks active Resume paths with `22A-4 ACTIVE SCANNER RESUME BUTTON`.
  - Writes immediate Resume diagnostics before async controller work.
  - Clears canonical pause flags and the legacy runtime pause bridge before the runner resumes.

- `apps/extension-douyin-capture/public/popup.html`
  - Marks the active footer pause/resume control with `22A-4 ACTIVE SCANNER RESUME BUTTON`.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
  - Adds `getNextPendingCollectTarget` for checkpoint-aware resume target selection.
  - Bypasses the dry-run recommendation guard for explicit Resume.
  - Clears pause and stop request flags when Resume starts.
  - Reuses the existing queue, capture session, batch, speed, and collection runner where valid.
  - Starts from the first pending or processing queue item.
  - Completes explicitly with `No pending videos remain.` when a paused state has no resumable targets.

- `apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`
  - Adds advanced diagnostics for Resume timestamps, result, checkpoint target, counts, session, runner target, pause fields, workflow state, and collection counters.

- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
  - Adds coverage for checkpoint helper selection, Resume from paused checkpoint, Resume with dry-run still idle, pause flag clearing, and no-pending Resume completion.

- `apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
  - Adds source-level assertions for active Resume markers, event routing, immediate diagnostics, and advanced diagnostics exposure.

## Resume Diagnostics

Immediate Resume click diagnostics now include:

```txt
last_scanner_action = "resume"
last_scanner_result = "clicked"
resume_requested_at = now
last_scanner_error = null
```

Runner diagnostics include:

```txt
resume_started_at
resume_acknowledged_at
resume_result
resume_error
resume_from_index
resume_from_aweme
resume_pending_count
resume_skipped_completed_count
resume_session_id
resume_runner_target
```

## Checkpoint Semantics

Resume uses `getNextPendingCollectTarget` to find the first queue item with status `pending` or `processing`. It skips extracted and skipped items so completed videos are not reprocessed. If no pending or processing targets remain, Resume transitions the collection workflow to success and records `No pending videos remain.`.

## Non-Goals

This phase did not redesign the UI, change backend API contracts, change Capture Inbox UI, implement crawling, add video processing, add scoring/filtering, introduce a database schema, add queue infrastructure, or add auto-publishing integrations.

## Validation

Completed during implementation:

```txt
npx --workspace @reup-douyin/extension-douyin-capture tsx src/wholeProfileHarvest.test.ts
```

Result: passed.

Full test, typecheck, and build commands are run separately for the final Phase 22A-4 checklist.
