# Phase 18J Canonical Capture Session Create Fix Resume

## Status

Implemented Phase 18J capture-session alignment and diagnostics.

## Files Touched

- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/api/tests/test_douyin_extension_routes.py`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/errors.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `docs/metadata-phase18J-canonical-capture-session-create-fix-log.md`
- `docs/metadata-phase18J-canonical-capture-session-create-fix-resume.md`

## Live Retest

1. Restart the API so the updated schema is active.
2. Rebuild and reload the extension.
3. Open a verified Whole Profile Harvest state with verified targets.
4. Click Run Harvest.
5. Confirm progress moves through `harvest_creating_capture_session` to `harvest_opening_target`.
6. Confirm `Capture session` shows `ready:<short id>`.
7. If it fails, click Copy Debug JSON and inspect `debug.last_request_summary` and `debug.last_response_summary` for endpoint, request body, status, response body, parsed session id, and error code.
