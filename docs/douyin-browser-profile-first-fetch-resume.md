# Douyin Browser Profile First Fetch Resume

## Current Step

Completed: connected-account local-dev discovery now prefers browser-profile-backed fetch when the account has a reusable persistent browser profile path.

## Done

- Audited the canonical connected-account fetch insertion point.
- Confirmed persistent profile metadata lives on `DouyinAccountConnection`.
- Confirmed browser-profile fetch is an execution strategy inside the existing adapter path, not a second pipeline.
- Added/preserved browser artifact extraction:
  - browser network JSON responses,
  - rendered DOM `/video/` links,
  - rendered page metadata for challenge/login classification.
- Propagated execution-path diagnostics:
  - `fetch_execution_path`,
  - `fallback_from_execution_path`,
  - `browser_profile_available`,
  - `browser_profile_unavailable_reason`,
  - `browser_fallback_attempted`,
  - `http_shell_detected`.
- Updated `/intake` to show the fetch path.
- Added focused fetch-client tests.

## In Progress

- None.

## Next Exact Task

Run live operator verification:

1. Open `/accounts/douyin`.
2. Reopen/validate the connected account's persistent browser profile.
3. Run `/intake` against the previously failing real profile.
4. Confirm the status panel shows `Fetch path: Browser profile`.
5. If it still fails, capture the exact `fetch_stage_code` and diagnostics id.

## Key Files To Continue

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/web/src/components/intake/IntakePage.tsx`

## Guardrails

- Do not add a second Douyin discovery pipeline.
- Do not persist browser-only data outside the canonical ingest models.
- Do not log or expose raw cookies/session material.
- Keep HTTP available as fallback only.
