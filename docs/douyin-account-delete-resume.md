# Douyin Account Delete Resume

## Current Step

Safe Delete Connected Account action for `/accounts/douyin`.

## Done

- Audited existing Douyin account management flow.
- Confirmed existing delete endpoint currently hard-deletes account rows.
- Chosen safe soft-delete semantics to preserve references and hide deleted accounts from active UI/intake usage.
- Implemented typed delete response.
- Implemented backend soft-delete guardrails.
- Added frontend Delete button with confirmation.
- Added focused backend service tests.

## In Progress

None.

## Next Exact Task

Use `/accounts/douyin` and delete a non-critical test account through the confirmation flow if manual UI validation is desired.

## Key Files To Continue

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-account-delete-user-guide.md`
