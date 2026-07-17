# Douyin Manual Import Hardening Resume

Current step: completed.

## Done

- Audited manual import UI payload shape.
- Audited persisted `DouyinAccountConnection` fields.
- Audited canonical runtime fetch config shape.

## In Progress

- None.

## Next Exact Task

If work continues, the next useful step is adding a small guided helper in `/accounts/douyin` for extracting `User-Agent` from a browser export so operators can repair legacy manual imports without trial and error.

## Key Files To Continue

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/api.ts`
