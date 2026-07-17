# Douyin Intake Preflight Log

## Step Name

Health-aware fetch path selection, auto reopen browser profile, and preflight before Intake discovery.

## Time Started

2026-04-23

## Findings

- Account health already exposes `can_use_for_live_fetch` via `DouyinAccountService.health_summary()`.
- Persistent browser profile availability is represented by `browser_profile_id` / `browser_profile_path` in `DouyinAccountConnection.metadata_json`.
- Runtime browser state is available from `DouyinBrowserContextRegistry.summary_for_account()`.
- Persistent profile reopen already exists in `DouyinBrowserContextRegistry.open_profile_for_account()`.
- `/intake` previously resolved an account and immediately built the adapter/started ingest, so obvious account/browser readiness failures were only discovered during live fetch.

## Current Readiness Signals

- Account status/health: active, blocked, expired, invalid, disabled.
- Fetch usability: `can_use_for_live_fetch`.
- Browser profile metadata: `browser_profile_id`, `browser_profile_path`.
- Browser runtime status: active, none, stale, invalid.
- HTTP fallback material: normalized Cookie header and User-Agent.

## Chosen Preflight Policy

Readiness categories:

- `fetch_ready_browser_profile`
- `fetch_ready_after_browser_reopen`
- `fetch_ready_http_fallback`
- `fetch_not_ready`

## Files Touched

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-intake-preflight-log.md`
- `docs/douyin-intake-preflight-resume.md`
- `docs/douyin-intake-preflight-architecture.md`
- `docs/douyin-intake-preflight-user-guide.md`

## Verification Notes

- `python -m unittest tests.test_intake_discovery_service tests.test_douyin_live_fetch`
- `python -m compileall src`
- `npm --workspace @reup-douyin/web run typecheck`

## Status

completed
