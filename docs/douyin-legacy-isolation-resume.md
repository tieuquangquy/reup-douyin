# Douyin Legacy Isolation Resume

## Current status

The legacy-isolation task is implemented and verified. The default Douyin runtime and main operator UI now use the browser-profile-backed flow as the only primary happy path. Legacy manual import and detached HTTP fallback remain in code, but they are isolated behind explicit legacy/debug flags.

## Goal

Make the browser-profile-backed Douyin flow the only default primary happy path while preserving legacy manual-import and detached HTTP-fallback code for explicit legacy/debug mode.

Default operator flow:

1. Create or open a persistent browser profile for a Douyin account.
2. Log in and solve challenges inside that same profile.
3. Validate using that same browser profile.
4. Run Intake using that same browser profile.
5. Extract profile/video data through browser-backed fetch.
6. Feed the existing canonical downstream ingest/discovery pipeline.

## Completed

- Read `AGENTS.md` and confirmed repository working rules.
- Audited key backend runtime paths:
  - `apps/api/src/core/settings.py`
  - `apps/api/src/services/douyin_account_service.py`
  - `apps/api/src/services/intake_discovery_service.py`
  - `apps/api/src/adapters/douyin_live_fetch.py`
  - `apps/api/src/adapters/douyin.py`
  - `apps/api/src/schemas/douyin_accounts.py`
  - `apps/api/src/schemas/intake.py`
- Audited key frontend/UI paths:
  - `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
  - `apps/web/src/components/intake/IntakePage.tsx`
  - `apps/web/src/types/douyin-accounts.ts`
  - `apps/web/src/types/intake.ts`
- Created mandatory docs before runtime/UI edits:
  - `docs/douyin-legacy-isolation-log.md`
  - `docs/douyin-legacy-isolation-architecture.md`
  - `docs/douyin-legacy-isolation-user-guide.md`
- Added default-off backend settings and env documentation:
  - `DOUYIN_ENABLE_LEGACY_MANUAL_IMPORT=false`
  - `DOUYIN_ENABLE_LEGACY_HTTP_FALLBACK=false`
  - `DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES=false`
- Added default-off frontend env documentation:
  - `NEXT_PUBLIC_DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES=false`
- Gated legacy manual-import smoke validation, response projection, browser-connect fallback availability, and main UI visibility.
- Gated detached HTTP validation fallback, fetch fallback, preflight fallback, Ready Check safe-to-run behavior, health alignment, and fallback UI diagnostics.
- Added/updated backend tests for default browser-only behavior and explicit legacy enablement.

## Important audit findings

### Manual import

Manual import remains reachable through:

- Account create/update smoke validation in `DouyinAccountService`.
- `manual_import_preflight` response projection.
- The main Douyin Accounts page manual import panel.
- Manual import preflight details in account rows.
- Browser connect recovery wording and `manual_fallback_available` response fields.

### Detached HTTP fallback

Detached HTTP fallback remains reachable through:

- `validate_account()` fallback after browser validation returns inconclusive.
- `build_fetch_client()` configuration.
- `preflight_fetch_readiness()` fallback readiness.
- `IntakeDiscoveryService.ready_check()` and `FALLBACK_READY` handling.
- Browser health alignment fields such as `detached_http_state`, `effective_validation_path`, and `expected_intake_path`.
- Intake and Douyin Accounts UI labels/diagnostics.

## Verification status

Passed on 2026-04-26:

```powershell
set PYTHONPATH=apps/api&& python -m unittest tests.test_douyin_account_preflight tests.test_intake_discovery_service tests.test_douyin_account_service tests.test_douyin_live_fetch tests.test_douyin_browser_connect_service
```

Result: `Ran 80 tests in 1.095s` / `OK`.

```powershell
npm run typecheck --workspace apps/web
```

Result: web TypeScript typecheck completed with exit code 0.
