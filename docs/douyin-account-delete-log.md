# Douyin Account Delete Log

## Step: Safe Delete Connected Account

Time started: 2026-04-23

## Findings

- `/accounts/douyin` already has a Connected accounts table with Validate, Revalidate, Set default, and Disable actions.
- The API already exposes `DELETE /douyin-accounts/{account_id}`, but the service currently hard-deletes the `DouyinAccountConnection`.
- `DouyinAccountConnection` can be referenced by `DouyinBrowserConnectSession.derived_account_id` and by intake/live-fetch flows through selected account ids.
- Intake uses `GET /douyin-accounts` and `can_use_for_live_fetch` to populate/select usable accounts.
- Browser-connect reset explicitly does not delete saved account connections, so account deletion needs a separate canonical account-management action.

## Chosen Delete Semantics

Delete is implemented as a safe soft-delete:

- Mark the account `DISABLED`.
- Clear `is_default`.
- Add delete metadata under `metadata_json`.
- Hide soft-deleted accounts from normal `GET /douyin-accounts` responses.
- Preserve the row so historical browser-connect/intake references do not become dangling.
- Rename the archived display name with a deleted suffix so the operator can reconnect a new account with the same display name later.

## Guardrails

- Delete is blocked if a running browser-connect session is currently tied to the account.
- Deleting a default account clears the default flag and returns a warning.
- Deleting a usable account returns a warning because it may affect intake live fetch.
- Deleting the only usable account returns an additional warning.
- Raw cookies/session secrets are never returned.

## Files Touched

- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-account-delete-log.md`
- `docs/douyin-account-delete-resume.md`
- `docs/douyin-account-delete-architecture.md`
- `docs/douyin-account-delete-user-guide.md`

## Verification Notes

- `PYTHONPATH=apps/api python -m unittest apps/api/tests/test_douyin_account_service.py` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `PYTHONPATH=apps/api python -m unittest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_douyin_browser_connect_service.py apps/api/tests/test_intake_discovery_service.py` passed.
- `npm --workspace @reup-douyin/web run build` passed.
- `DATABASE_URL=sqlite:///:memory: PYTHONPATH=apps/api python -c "from src.main import app; ..."` passed and confirmed `/douyin-accounts/{account_id}` is registered.
- Live local smoke:
  - `GET http://127.0.0.1:8000/docs` returned 200.
  - `GET http://localhost:3000/accounts/douyin` returned 200.
  - `GET http://127.0.0.1:8000/douyin-accounts` returned a safe account list.

## Status

Completed.
