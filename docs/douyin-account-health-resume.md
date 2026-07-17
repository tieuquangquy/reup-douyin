# Douyin Account Health Resume

## Current Step
Implement account health, auto revalidate, and session warning flow for Douyin source accounts.

## Done
- Audited canonical account, validation, browser connect, intake, and job flow.
- Chosen no-duplication approach: health summary projects from `DouyinAccountConnection` and existing validation service.
- Created health task docs before code edits.
- Added health and warning enums plus latest-summary fields.
- Added migrations `0018_douyin_account_health` and `0019_douyin_account_health_job_types`.
- Updated `DouyinAccountService` to normalize validation status and project health summaries.
- Added run-now and job-backed revalidation endpoints.
- Added job templates and worker runner branches for account revalidation.
- Updated `/accounts/douyin` with health badges, warning strip, next validation, and queue actions.
- Updated `/intake` to use `can_use_for_live_fetch` and show account health warnings.
- Completed API/web/migration/worker verification.

## In Progress
- None.

## Next Exact Task
Run a real account through browser-assisted connect, let the account become stale or force its `next_validation_due_at`, then validate the operator-facing warning copy with a real live fetch.

## Key Files To Continue
- `apps/api/src/enums/__init__.py`
- `apps/api/src/models/source_accounts.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/services/job_templates.py`
- `apps/api/src/services/job_runner.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
