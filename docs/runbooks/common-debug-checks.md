# Common Debug Checks

Use this before diving into a specific pipeline runbook.

## Symptoms

- UI shows empty data unexpectedly.
- Job appears stuck.
- API returns 422 or 500.
- Media preview is unavailable.

## Checks

1. Confirm API env:
   - `DATABASE_URL`
   - `LOCAL_STORAGE_ROOT`
   - `LOG_LEVEL`
2. Confirm migrations:
   - `cd apps/api`
   - `alembic current`
   - `alembic upgrade head`
3. Confirm browser-connect runtime readiness (for `/accounts/douyin` browser-assisted connect):
   - `npm run doctor`
   - Verify checks: `playwright browser binary`, `playwright launch`
   - If needed: `npm run playwright:install`
4. Confirm seed/demo data:
   - `.\scripts\seed-demo.ps1`
5. Inspect job:
   - `GET /jobs/{job_id}`
   - check `status`, `current_step_key`, `error_code`, `error_message`
5. Inspect media assets:
   - `GET /source-videos/{source_video_id}/assets`
   - check `status`, `asset_type`, `storage_key`, `is_current`
6. Inspect risk:
   - `GET /targets/{type}/{id}/risk-summary`

## Immediate Fixes

- Rerun a job only when input assets and payload are still valid.
- Use `retry` only for transient failures.
- Use `cancel` when the input is wrong.
- Use `needs_fix` or `reject` in operator flows when output quality is wrong, not when infrastructure failed.

## Escalate

Escalate to code/debug work when:

- migrations are current but models disagree with API schemas
- storage asset exists in DB but file is missing
- job step repeatedly fails at the same deterministic point
- UI contract shape no longer matches API response
