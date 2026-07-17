# Douyin Manual Import Preflight Log

## Step: add manual-import preflight diagnostics

Started: 2026-04-23

Status: completed

## Findings

- Manual import hardening already normalizes saved session material into the canonical runtime shape:
  - `Cookie` header string
  - `User-Agent`
  - optional `proxy_url`
- `/intake` no longer collapses manual-import failures into a generic `500`.
- Current account-level visibility is still coarse:
  - `health_status`
  - `warning_summary_json.reason`
  - `last_error_code`
  - `last_error_message`
- Operators can see that an imported account is blocked or invalid, but not a compact preflight answer for:
  - malformed import payload
  - missing or thin cookies
  - missing user-agent
  - login-required redirects
  - blocked responses
  - transport/parsing failures
  - usable-for-fetch success

## Decisions

- Keep one canonical `DouyinAccountConnection` model and one canonical fetch-client construction path.
- Add a dedicated safe manual-import preflight summary to the account response instead of overloading generic health labels.
- Persist only bounded, non-secret preflight diagnostics in existing JSON metadata/summary fields.
- Reuse the existing validation/fetch path; do not add a manual-import-only fetch pipeline.

## Files Touched

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/types/douyin-accounts.ts`
- `docs/douyin-manual-import-preflight-log.md`
- `docs/douyin-manual-import-preflight-resume.md`
- `docs/douyin-manual-import-preflight-architecture.md`
- `docs/douyin-manual-import-preflight-user-guide.md`

## Verification Notes

- Focused API tests passed:
  - `python -m unittest tests.test_douyin_account_service tests.test_intake_discovery_service`
- Web typecheck passed:
  - `npm --workspace @reup-douyin/web run typecheck`
- Added preflight coverage for:
  - malformed JSON cookie export
  - cookie export too thin for authenticated fetch
  - safe preflight summary in account response
  - `/intake` account resolution mapping for the new manual-import failure class
