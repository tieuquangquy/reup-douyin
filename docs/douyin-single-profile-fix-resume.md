# Douyin Single Profile Fix Resume

## Current Step

Completed strict one-account-one-persistent-browser-profile identity reuse.

## Done

- Audited profile allocation in browser context registry.
- Audited browser connect start/restart/retry flow.
- Audited validation, preflight, and browser-backed fetch profile reuse.
- Created required docs before code edits.
- Added backend guards so account-backed flows cannot overwrite profile metadata
  with a new connect-session profile.
- Preserved account id through restart even if the caller omits it.
- Added tests for restart/account profile invariants.
- Verified focused API tests and API compile.

## In Progress

- None.

## Next Exact Task

Use `/accounts/douyin` to open/reopen the target account profile, then run
`/intake` with that account selected. The same profile id should appear as the
account's browser context id when no live runtime context is active.

## Key Files To Continue

- `apps/api/src/services/douyin_browser_connect_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/tests/test_douyin_browser_connect_service.py`

## Known Constraints

- A brand-new account cannot have an account id until login capture creates the
  account. Before that point, a connect-session profile may be used as a draft
  profile and then persisted onto the newly created account.
- Once an account exists, all reopen/retry/validate/intake paths must use the
  account's persisted profile identity.
- This change does not delete old orphaned browser profile directories.
