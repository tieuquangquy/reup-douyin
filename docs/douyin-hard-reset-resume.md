# Douyin Hard Reset Resume

## Current Step

Completed hard reset of the Douyin discovery primary path to persistent browser
profile backed fetch.

## Done

- Audited current browser-profile fetch, account preflight, live fetch client, adapter, and ingest pipeline.
- Created hard-reset docs before code changes.
- Disabled silent HTTP fallback by default for connected-account Intake.
- Required browser profile readiness in preflight unless legacy fallback is explicitly enabled.
- Improved browser-profile extraction with rendered-page settling/scrolling.
- Demoted manual import wording in `/accounts/douyin`.
- Added/updated focused tests for browser-profile-primary and legacy fallback behavior.
- Verified focused API tests, API compile, web typecheck, full smoke, and route smoke.

## In Progress

- None.

## Next Exact Task

Live operational verification requires an operator-authenticated Douyin browser
profile. From `/accounts/douyin`, open/reopen a browser profile, complete login,
then run `/intake` against a known real profile with videos.

## Key Files To Continue

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

## Known Limitation

The running API currently has an active Douyin account record without a reusable
browser profile attached. The hard reset intentionally blocks that account from
being used as the primary connected-account Intake path until a saved browser
profile is created/reopened for it.
