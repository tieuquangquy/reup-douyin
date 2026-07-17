# Douyin Browser Watchdog Implementation Log

## Findings

- Persistent browser runtime state lives in `apps/api/src/services/douyin_browser_context_registry.py`.
- Intake readiness is centralized in `DouyinAccountService.preflight_fetch_readiness()`.
- Existing preflight already checks account health, browser profile metadata, active runtime summary, one auto reopen attempt, and HTTP fallback material.
- Existing runtime checks already detect idle timeout, max lifetime, and lost Playwright context through `_ensure_usable()`, but this result is not exposed as a named watchdog result.
- Repeated `/intake` runs currently repeat the same readiness checks even when a recent successful preflight already proved the selected account/profile is ready.

## Current Runtime Friction Points

- Runtime summaries can report stale/invalid only after a preflight or fetch touches the registry.
- The UI cannot tell whether stale state was reconciled or whether the current readiness result was freshly checked.
- Short repeated intake runs can trigger repeated reopen/readiness logic even when the browser profile was checked seconds ago.

## Strategy

- Add a lightweight browser-profile watchdog in the runtime registry.
- Reuse the existing `_ensure_usable()` runtime truth instead of creating a second validation system.
- Add a conservative short-lived preflight cache in `DouyinAccountService`.
- Cache only passed preflight results, and invalidate on account validation/update/delete/disable.
- Expose safe diagnostics in API/UI:
  - cache used or fresh check,
  - watchdog result/status/reason,
  - runtime reconciled yes/no.

## Files Touched

- `apps/api/src/services/douyin_browser_context_registry.py`
  - Added `DouyinBrowserWatchdogResult`.
  - Added `watchdog_for_account()`.
- `apps/api/src/services/douyin_account_service.py`
  - Added short-lived in-memory preflight cache.
  - Added cache invalidation around account create/update/validate/disable/delete.
  - Integrated watchdog into `preflight_fetch_readiness()`.
- `apps/api/src/services/intake_discovery_service.py`
  - Propagated cache/watchdog/reconciliation diagnostics into summaries and logs.
- `apps/api/src/schemas/intake.py`
  - Added preflight cache/watchdog response fields.
- `apps/api/src/core/settings.py`
  - Added `douyin_intake_preflight_cache_ttl_seconds`.
- `apps/api/.env.example`
  - Documented `DOUYIN_INTAKE_PREFLIGHT_CACHE_TTL_SECONDS=30`.
- `apps/api/tests/test_douyin_account_preflight.py`
  - Added focused preflight cache tests.
- `apps/api/tests/test_intake_discovery_service.py`
  - Updated mocked preflight payloads.
- `apps/web/src/types/intake.ts`
  - Added cache/watchdog fields.
- `apps/web/src/components/intake/IntakePage.tsx`
  - Displays preflight cache, watchdog, runtime state, and reconciliation hints.
- `apps/web/src/lib/i18n/en.json`
  - Added new Intake labels.
- `apps/web/src/lib/i18n/vi.json`
  - Added matching Vietnamese labels.
- `docs/douyin-browser-watchdog-*.md`
  - Added implementation docs and user guide.

## Verification Notes

- `python -m unittest tests.test_douyin_account_preflight tests.test_intake_discovery_service tests.test_douyin_live_fetch`
- `python -m compileall src`
- `npm --workspace @reup-douyin/web run typecheck`

## Status

Completed.
