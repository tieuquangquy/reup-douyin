# Douyin Manual Import Preflight Resume

Current step: manual-import preflight diagnostics

Done:
- Audited current manual import hardening docs.
- Audited `DouyinAccountService`, account schemas, routes, and `/accounts/douyin` UI.
- Confirmed current operator-facing visibility is too coarse for imported-account troubleshooting.
- Added canonical manual-import preflight categories and safe response payload.
- Persisted bounded preflight summary in account metadata for manual imports.
- Surfaced preflight details in `/accounts/douyin`.
- Updated intake account-resolution mapping for new manual-import diagnostics.
- Added focused tests and passed verification.

In progress:
- None.

Next exact task:
- Optional next pass: surface the same manual-import preflight summary in `/intake` account picker hints so operators can see unusable imported accounts before submitting discovery.

Key files to continue:
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/api/tests/test_douyin_account_service.py`
