# Metadata Status Phase 1 Resume

## Current Goal

Introduce a Phase 1 metadata status and evidence model for Capture Inbox so Time, Performance, and Processing fit can be diagnosed from API responses and shown compactly in the web UI.

## Required Files

- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_douyin_extension_capture_service.py` or a focused Capture Inbox schema test file
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/metadata-status-phase1-log.md`
- `docs/metadata-status-phase1-resume.md`

## Scope Constraints

Do not change:

- extension extraction logic
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
- metadata sourcing
- overall Capture Inbox layout
- hydration jobs/workers

## Status Rules To Preserve

- Time captured: `posted_at` exists or reliable `posted_text` exists.
- Performance captured: `view_count` or `like_count` exists.
- Processing fit captured: `duration_seconds` exists.
- Complete: all groups captured.
- Partial: at least one group captured and at least one group missing/pending.
- Missing: no groups captured after metadata evidence/attempt exists.
- Pending hydration: new/no-attempt item with no captured groups.
- Failed: hard item error or metadata hydration error marker.

## API Fields To Expose

- `metadata_status`
- `time_status`
- `performance_status`
- `processing_fit_status`
- `metadata_missing_reason`
- `time_missing_reason`
- `performance_missing_reason`
- `processing_fit_missing_reason`
- `metadata_source_summary`
- `last_metadata_hydrated_at`

## UI Rendering Target

- Card: compact label for metadata status:
  - Metadata complete
  - Metadata partial
  - Needs metadata
  - Metadata failed
- Inspector Metadata section:
  - Time status + reason
  - Performance status + reason
  - Processing fit status + reason
  - Source summary

## Test Targets

- Complete item.
- Partial item.
- Missing item.
- Pending item.
- Failed item.
- API serializes statuses.
- Frontend renders statuses honestly.
