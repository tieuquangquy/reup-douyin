# douyin-browser-post-login-fix-resume.md

## Current Step
Fix post-login stabilization, validation sequencing, resume flags, and retry validation for `/accounts/douyin`.

## Done
- Audited browser capture lifecycle.
- Audited canonical account validation and blocked assignment.
- Identified premature browser close and premature `blocked_response` mapping risk.
- Created post-login fix log/resume/architecture docs before code changes.
- Added post-login phase progress metadata.
- Added bounded browser-context auth stabilization.
- Added browser-context prevalidation before Playwright closes the browser.
- Added retry-validation API and UI action.
- Added response flags for browser resume, retry validation, keep-browser-open guidance, and validation attempt count.
- Updated `/accounts/douyin` wording so login detected and validation retry do not look like hard blocked immediately.
- Verified backend tests, Python compile sanity, route registration, frontend typecheck, frontend build, and live idle route checks.

## In Progress
- Nothing for this fix.

## Next Exact Task
Run a real Douyin QR login and record whether browser-context prevalidation plus retry validation reduces false `blocked_response` outcomes.

## Key Files To Continue
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
