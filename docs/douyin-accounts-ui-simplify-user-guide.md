# Douyin Accounts UI Simplify User Guide

## Purpose
This guide explains the simplified operator workflow for [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:345) after the persistent-profile-first cleanup.

The page now emphasizes one model only:
- one saved Douyin account
- one reusable local browser profile
- one clean handoff into intake

## Primary Workflow
Use the following primary sequence in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:365):

1. **Connect with browser** to create a new account/profile.
2. For existing rows, use **Open profile** or **Reopen profile** in [`account row actions`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:546).
3. Run **Validate** to confirm readiness for live fetch.
4. Use **Use in intake** to jump directly to intake with account preselection.
5. Use **Reset browser connect state** only when local runtime state is stuck.
6. Use **Delete** only when retiring that account from active use.

## Intake Handoff Behavior
The handoff from accounts to intake is implemented by [`useInIntake()`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:322), which appends `douyinAccountConnectionId` in the URL.

On intake load, [`IntakePage`](apps/web/src/components/intake/IntakePage.tsx:77) reads this query param and preselects the matching account if present. If not present or not found, intake falls back to existing default/usable account selection logic.

## Troubleshooting (Secondary)
Session-level controls are intentionally demoted into collapsed troubleshooting details in [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:403):
- resume active connect
- cancel active connect
- force restart connect
- retry validation
- queue health sweep
- active-session diagnostics

Use these controls only when recovering from a stuck or failed connect session.

## Localization
New labels introduced for the simplified flow were added in:
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json:759)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json:758)

## Verification
Type safety was verified via [`npm run typecheck`](package.json:10), which runs the web TypeScript check configured in [`apps/web/package.json`](apps/web/package.json:5).

## Scope Notes
This update is a UI simplification and intake handoff refinement only. It does not introduce a new account model, validation model, or browser-connect pipeline.