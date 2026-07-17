# Phase 22B-1 Modal-First One-Item Save Log

## Scope

Implemented Phase 22B-1 only: modal-first one-item collect/save with calibration-context lock for the Douyin extension collector.

## Active Collector Path

- Popup Start Collecting uses `runStartCollectingWorkflow()` in `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`.
- The workflow forces the Phase 22B one-item smoke path with `collect_mode: "one_item_smoke_test"` and `batch_limit: 1`.
- `runRealModalExtractionHarvest()` delegates one-item mode to `runOneItemCollectSmokeTest()`.
- The one-item runner now opens a profile modal URL for profile-modal calibration and validates extraction context before metrics extraction.

## Changes

- Added calibration layout context fields: `layout`, `source_url`, `profile_url`, and `aweme_id`.
- Added modal-first detail URL builder that prefers a matching profile modal source URL, otherwise builds `profile_url_without_query?modal_id=AWEME_ID`.
- Blocked silent direct `/video/AWEME_ID` fallback when calibration layout is `profile_modal`.
- Added extraction-context validation for expected layout, current URL, page type, modal id, modal presence, and visible metric rail/buttons.
- Added popup runtime extraction-context reporting from the active tab.
- Added diagnostics for calibration layout, detail open strategy, payload preview, payload guard, backend save, and verify readback.
- Added tests for modal URL behavior, context validation, modal-first one-item save, and context-mismatch save blocking.

## Non-Goals

- No Capture Inbox frontend changes.
- No backend schema changes.
- No fake extracted metrics.
- No crawler, scoring, filtering, or publishing implementation.
- No direct-video calibrated extraction beyond preserving the existing explicit `direct_video` branch.
