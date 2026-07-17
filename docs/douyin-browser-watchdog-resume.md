# Douyin Browser Watchdog Resume

## Current Step

Completed browser-profile watchdog, runtime self-healing diagnostics, and short-lived Intake preflight cache.

## Done

- Audited current registry/preflight insertion points.
- Created initial watchdog implementation docs.
- Add runtime watchdog result model and registry method.
- Add conservative preflight cache and diagnostics fields.
- Surface diagnostics through `/intake` API and UI.
- Added `DOUYIN_INTAKE_PREFLIGHT_CACHE_TTL_SECONDS`, default 30 seconds.
- Verified API tests, Python compile, and web typecheck.

## In Progress

- None for this step.

## Next Exact Task

Run a real local `/intake` fetch with a connected browser-profile account and verify the browser stays reused across repeated runs within the cache TTL.

## Key Files To Continue

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/api/tests/test_douyin_account_preflight.py`
