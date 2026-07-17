# Phase 17W V2 Capture Session Fix Resume

## Current State

Phase 17W implementation is complete for the isolated Whole Profile Staged Harvest V2 Capture Inbox session flow.

## Touched Areas

- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/tests/test_douyin_extension_routes.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`

## Important Behavior To Preserve

- V2 must not call legacy `capture-current-page` or Smart Capture runtime paths.
- V2 session creation must happen before target navigation.
- V2 session preflight must create only a `CaptureSession`; it must not create visible `CapturedItem` rows.
- Full-modal finalized payloads must include explicit V2 session and target metadata.
- Backend full-modal session resolution must prefer explicit `capture_session_id`, then V2 `run_id`, then legacy latest-session fallback.
- `capture_session_not_found` must remain a distinct V2 error reason.

## Verification State

Passed:

- Extension typecheck.
- Targeted modal whole-profile extension test.
- Python compilation for touched API source and tests.

Blocked:

- Targeted backend pytest command could not run because global Python lacks `pytest`.

Command that was blocked:

```powershell
python -m pytest apps/api/tests/test_douyin_extension_routes.py apps/api/tests/test_douyin_extension_capture_service.py
```

Observed error:

```text
No module named pytest
```

## Suggested Next Verification When Python Test Environment Is Available

Run:

```powershell
python -m pytest apps/api/tests/test_douyin_extension_routes.py apps/api/tests/test_douyin_extension_capture_service.py
```

Then live retest the V2 operator flow from the extension popup and confirm the first finalized backend write no longer fails with `capture_session_not_found`.
