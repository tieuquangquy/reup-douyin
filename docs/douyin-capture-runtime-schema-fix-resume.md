# Douyin Capture Runtime Schema Fix Resume

## Task

Fix the remaining true-system-failure path for `POST /douyin-extension/capture-current-page` by validating Capture Inbox runtime schema readiness, aligning backend runtime diagnostics, and surfacing stage-specific persistence errors.

## Constraints

- Preserve local-first, SaaS-ready boundaries.
- Keep the web app and extension browser-safe.
- Do not run long processing inline in HTTP handlers.
- Do not hide infrastructure failures behind generic HTTP 500 responses.
- Do not log secrets or private local paths.

## Files Expected To Change

- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/api/routes/douyin_extension.py` if route-level mapping is needed
- `apps/api/tests/test_douyin_extension_capture_service.py`
- UI or extension tests if error projection needs adjustment
- This document set under `docs/`

## Current Audit Summary

- Migration `0021_douyin_capture_inbox` creates the expected Capture Inbox tables.
- ORM models align with the migration at the table/column level.
- `CaptureInboxService.stage_extension_capture` can still raise raw database/runtime errors during Capture Session creation, item persistence recovery, or final reconciliation/commit.
- `DouyinExtensionCaptureService.capture_current_page` currently does not convert those runtime failures into `DouyinExtensionCaptureError`.
- The extension popup and web API helper already know how to display structured backend `detail` objects when the backend supplies them.

## Next Steps

1. Implement schema readiness validation and custom runtime error classification.
2. Convert persistence failures to explicit codes/stages.
3. Add tests.
4. Run API, web, and extension verification commands.
5. Update the log and user guide with final results.
