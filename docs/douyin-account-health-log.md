# Douyin Account Health Log

## Step
Implement Douyin account health, auto revalidate, and session warning flow.

## Findings
- Canonical source account model is `DouyinAccountConnection`.
- Current validation path is `DouyinAccountService.validate_account`.
- Existing fields already store latest validation time/status/error.
- `/intake` currently checks only `account.status === ACTIVE` in the UI and API runtime resolver.
- Browser-assisted connect creates canonical account connections and validates through the same service.
- The job system already has durable jobs, step templates, and a local polling worker.
- There is no scheduled sweeper yet, so V1 auto revalidate should be run-now job orchestration, not a new scheduler platform.

## Current Architecture Inventory
- Account model: `apps/api/src/models/source_accounts.py`
- Validation service: `apps/api/src/services/douyin_account_service.py`
- Account API: `apps/api/src/api/routes/douyin_accounts.py`
- Browser connect: `apps/api/src/services/douyin_browser_connect_service.py`
- Intake account-backed fetch: `apps/api/src/services/intake_discovery_service.py`
- Job model/service/runner: `apps/api/src/models/jobs.py`, `apps/api/src/services/job_service.py`, `apps/api/src/services/job_runner.py`
- Worker runtime: `apps/worker/src/runtime.py`
- Account UI: `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- Intake UI: `apps/web/src/components/intake/IntakePage.tsx`

## Decisions Made
- Reuse `DouyinAccountConnection`; do not add a duplicate account model.
- Reuse `DouyinAccountService.validate_account`; health is a deterministic projection over canonical status and validation timestamps.
- Add latest-summary fields only; no validation history table in V1.
- Add job types for validating one account and sweeping due accounts.
- V1 auto revalidate is a queued job/manual run-now action; full scheduling is deferred.
- Expiry is heuristic because Douyin does not expose reliable expiry through current code.

## Fields Added
- `health_status`
- `warning_level`
- `last_successful_validation_at`
- `validation_source`
- `next_validation_due_at`
- `expires_at`
- `last_error_code`
- `warning_summary_json`

## Files Touched
- `apps/api/src/enums/__init__.py`
- `apps/api/src/models/source_accounts.py`
- `apps/api/alembic/versions/0018_douyin_account_health.py`
- `apps/api/alembic/versions/0019_douyin_account_health_job_types.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/services/job_templates.py`
- `apps/api/src/services/job_runner.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-account-health-log.md`
- `docs/douyin-account-health-resume.md`
- `docs/douyin-account-health-architecture.md`
- `docs/douyin-account-health-user-guide.md`

## Verification Notes
- Migration passed:
  - `alembic upgrade head`
- API focused tests passed:
  - `python -m unittest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_intake_discovery_service.py apps/api/tests/test_douyin_adapter.py`
- API compile passed:
  - `python -m compileall -q apps/api/src`
- Web checks passed:
  - `npm run typecheck`
  - `npm run test`
- Route registry confirmed new routes are registered before `/{account_id}`:
  - `POST /douyin-accounts/revalidate-due`
  - `POST /douyin-accounts/revalidate-due/job`
  - `POST /douyin-accounts/{account_id}/revalidate-job`
- Runtime smoke:
  - `GET /accounts/douyin` returned 200.
  - `GET /intake` returned 200.
  - `GET /douyin-accounts` returned safe account list JSON.
  - `POST /douyin-accounts/revalidate-due` returned zero checked/updated accounts on empty DB.
  - `POST /douyin-accounts/revalidate-due/job` queued a health sweep job.
  - Local worker `run_once()` completed the queued health sweep job.

## Status
Completed.
