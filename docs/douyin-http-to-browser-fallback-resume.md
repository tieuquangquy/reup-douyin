# Douyin HTTP To Browser Fallback Resume

## Current Step

Completed: automatic HTTP classified-failure fallback to browser-profile-backed fetch is implemented inside `DouyinLiveFetchClient`.

## Done

- Audited current fetch orchestration.
- Confirmed fallback logic exists but is unreachable for key HTTP classified failures because `_finalize_payload()` raises before the fallback block.
- Defined fallback trigger categories.
- Confirmed canonical downstream pipeline is unchanged.
- Patched `DouyinLiveFetchClient.__call__()` so HTTP `_finalize_payload()` exceptions can trigger browser fallback.
- Added regression coverage for:
  - HTTP `parse_zero_videos` -> browser fallback success,
  - HTTP `parse_zero_videos` -> browser fallback blocked failure with dual diagnostics.
- Verified API tests, compile, and web typecheck.

## In Progress

- None.

## Next Exact Task

Run live verification with a real connected account and profile:

1. Trigger `/intake` against the profile that previously returned HTTP shell/zero videos.
2. Confirm the diagnostics show `fetch_execution_path = http_then_browser_fallback` when HTTP is tried first, or `browser_profile` when browser-first is configured.
3. If both attempts fail, capture final `fetch_stage_code` and diagnostics id.

## Key Files To Continue

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/tests/test_douyin_live_fetch.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/web/src/components/intake/IntakePage.tsx`

## Guardrails

- No HTTP/browser retry loop.
- Fallback only once.
- No duplicate normalization or persistence path.
- No raw cookie/session logging.
