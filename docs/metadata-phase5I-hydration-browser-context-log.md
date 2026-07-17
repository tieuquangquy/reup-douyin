# Phase 5I Hydration Browser Context Log

## Status
- completed

## Root cause
- Metadata hydration selected `browser_profile`, but item-level detail fetch still assumed a live browser context already existed in the runtime registry.
- `fetch_detail_page(...)` returned `no_live_browser_context` when no context had been opened yet.
- `hydrate_capture_session_metadata(...)` did not open or reuse the saved persistent browser profile before looping items.
- That produced 49 repeated item failures instead of one session-level browser-context failure.

## Behavior change
- Hydration now ensures a live browser context before entering the item loop.
- It reuses an active context if present.
- If none is live, it opens/reuses the saved persistent browser profile through the existing account service path.
- It probes the browser-backed Douyin context once before item processing.
- If that probe fails, hydration stops once at session level with a clear error and operator command.

## Files touched
- `apps/api/src/services/capture_inbox_metadata_hydration_service.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/tests/test_capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
- `docs/metadata-phase5I-hydration-browser-context-log.md`
- `docs/metadata-phase5I-hydration-browser-context-resume.md`

## Tests run
- `python -m unittest tests.test_capture_inbox_metadata_hydration_service tests.test_hydrate_capture_session_metadata_script tests.test_douyin_account_service tests.test_douyin_account_readiness_script`
- `python -m compileall src scripts`

## Verification result
- Hydration no longer depends on a pre-existing live browser context.
- Missing context is handled once before the item loop.
- Session-level context failures now return operator-facing commands instead of repeating `no_live_browser_context` per item.
