# Douyin Accounts UI Simplify Resume

## Current Step
Completed implementation and verification for the simplified persistent-profile-first UI on [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:58).

## Done
- Reviewed repository constraints in [`AGENTS.md`](AGENTS.md:1).
- Audited current `/accounts/douyin` UI actions in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:58).
- Reviewed account/browser API surface in [`api.ts`](apps/web/src/lib/api.ts:200).
- Reviewed shared frontend account/connect types in [`douyin-accounts.ts`](apps/web/src/types/douyin-accounts.ts:5).
- Reviewed intake account selection behavior in [`IntakePage`](apps/web/src/components/intake/IntakePage.tsx:44).
- Reviewed related architecture docs for persistent profile, reset, account health, intake selection, and active connect recovery.
- Defined the final primary action set and troubleshooting demotion strategy in [`docs/douyin-accounts-ui-simplify-architecture.md`](docs/douyin-accounts-ui-simplify-architecture.md:15).
- Refactored [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:365) primary browser section to emphasize profile creation/recovery path.
- Demoted connect-session controls and diagnostics into collapsed troubleshooting details in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:403).
- Simplified table row actions to open/reopen, validate, intake handoff, reset runtime, and delete in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:546).
- Added intake handoff query bridge (`douyinAccountConnectionId`) in [`useInIntake()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:322).
- Added intake query-param preselect support in [`IntakePage`](apps/web/src/components/intake/IntakePage.tsx:77).
- Updated i18n strings in [`en.json`](apps/web/src/lib/i18n/en.json:759) and [`vi.json`](apps/web/src/lib/i18n/vi.json:758).
- Verified with [`npm run typecheck`](package.json:10).

## In Progress
- None.

## Next Exact Task
1. Optional UX/runtime smoke test through [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:345) and [`/intake`](apps/web/src/components/intake/IntakePage.tsx:401) in a running dev environment.
2. Continue any future refinements as separate scoped tasks.

## Key Files To Continue
- [`apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:58)
- [`apps/web/src/components/intake/IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx:44)
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json:759)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json:758)
- [`docs/douyin-accounts-ui-simplify-log.md`](docs/douyin-accounts-ui-simplify-log.md:1)
