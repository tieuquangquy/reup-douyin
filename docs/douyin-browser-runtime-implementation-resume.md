# Douyin Browser Runtime Implementation Resume

## Current Step

Completed browser runtime implementation and verification for the canonical Douyin browser-assisted connect path.

## Done

- Read `AGENTS.md`.
- Audited `/accounts/douyin` frontend call path.
- Audited API endpoint path:
  - `POST /douyin-accounts/browser-connect/start`
  - `GET /douyin-accounts/browser-connect/{id}`
  - `POST /douyin-accounts/browser-connect/{id}/cancel`
- Identified canonical service:
  - `apps/api/src/services/douyin_browser_connect_service.py`
- Identified canonical runtime:
  - Python Playwright in API process.
- Confirmed no second browser-connect pipeline should be added.
- Confirmed manual session import fallback remains in `DouyinAccountsPage`.
- Confirmed local direct Playwright launch works in the current shell.
- Added Windows Proactor event loop policy guard before Playwright starts.
- Added deterministic runtime error mapping:
  - `dependency_missing`
  - `browser_binary_missing`
  - `launch_failed`
  - `runtime_probe_failed`
  - `runtime_not_supported`
  - `browser_closed`
- Preserved manual import fallback.
- Updated doctor/smoke Playwright checks to use the same Windows runtime policy.
- Verified endpoint start/poll/cancel reaches `WAITING_FOR_LOGIN` rather than immediate runtime failure.
- Updated local setup and troubleshooting docs.

## In Progress

None.

## Next Exact Task

Run a real operator login through `/accounts/douyin` and confirm validation quality against a real Douyin account. No code task is pending from this implementation pass.

## Key Files To Continue

- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/api.ts`
- `scripts/dev-doctor.ps1`
- `scripts/smoke-check.ps1`
- `docs/douyin-browser-runtime-implementation-log.md`
- `docs/douyin-browser-runtime-implementation-architecture.md`

## Guardrails

- Do not log raw cookies.
- Do not return raw cookies in API responses.
- Do not create a duplicate account/session table.
- Do not fake login success.
- Do not remove manual import fallback.

## Verification Completed

- `npm run doctor`
- `npm run smoke`
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run test`
- `python -m unittest apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_intake_discovery_service.py`
- `GET http://localhost:3000/accounts/douyin`
- `POST /douyin-accounts/browser-connect/start` followed by poll and cancel
