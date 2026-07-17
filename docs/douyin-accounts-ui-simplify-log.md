# Douyin Accounts UI Simplify Log

## Findings
- [`/accounts/douyin`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:61) still mixes the old browser-connect session mental model with the newer persistent-profile model.
- The current top panel makes transient connect-session controls prominent, including [`retry connect`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:433), [`resume connect`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:436), [`force restart`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:442), and [`retry validation`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:445).
- The current row action set also contains non-primary lifecycle controls such as [`revalidate`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:580), [`set default`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:581), and [`disable`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:582), which dilute the final operator model.
- The persistent-profile pivot is already documented in [`docs/douyin-persistent-profile-hard-pivot-architecture.md`](docs/douyin-persistent-profile-hard-pivot-architecture.md:3): one account is backed by one reusable local browser profile.
- Account health and intake selection are already canonicalized in [`docs/douyin-account-health-architecture.md`](docs/douyin-account-health-architecture.md:3) and [`docs/douyin-intake-account-selection-architecture.md`](docs/douyin-intake-account-selection-architecture.md:1), so the UI simplification should not create a second selection or validation model.

## Primary vs Secondary Action Decisions
- Keep as primary row actions:
  - Open/Reopen profile
  - Validate
  - Use in intake
  - Reset runtime state
  - Delete account
- Keep as top-level primary creation path:
  - Connect with browser for new account creation only
- Demote to secondary troubleshooting:
  - Resume active connect session
  - Cancel active connect session
  - Force restart connect
  - Retry validation on active connect session
  - Manual cookie import fallback
  - Low-level active connect/session diagnostics
- Remove from main row action cluster:
  - Queue revalidate job
  - Set default
  - Disable

## Wording Decisions
- Main page should talk about reusable local browser profiles, readiness validation, and intake handoff.
- Avoid session-centric primary wording such as connect session, retry connect, force restart, and validation retry ready outside troubleshooting details.
- `Reset runtime state` remains operator-facing but framed explicitly as recovery for stuck local browser/profile runtime state, not account deletion.

## Implementation Results
- [`DouyinAccountsPage`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:58) now keeps the persistent-profile path as the visible primary flow.
- Primary browser section now emphasizes `Connect with browser` and `Reset browser connect state`, while resume/restart/cancel/retry/session diagnostics are demoted into collapsed troubleshooting details.
- Row actions now match the final model: open/reopen profile, validate, use in intake, reset runtime state, and delete.
- Legacy row actions (`revalidate`, `set default`, `disable`) were removed from the main table action cluster.
- [`Use in intake`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:550) now navigates to intake with `douyinAccountConnectionId`.
- [`IntakePage`](apps/web/src/components/intake/IntakePage.tsx:77) now reads `douyinAccountConnectionId` from query params and preselects that account when present.
- i18n keys were updated in both [`en.json`](apps/web/src/lib/i18n/en.json:759) and [`vi.json`](apps/web/src/lib/i18n/vi.json:758) for new persistent-profile actions and troubleshooting labels.

## Files Touched
- [`apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`](apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx:58)
- [`apps/web/src/components/intake/IntakePage.tsx`](apps/web/src/components/intake/IntakePage.tsx:77)
- [`apps/web/src/lib/i18n/en.json`](apps/web/src/lib/i18n/en.json:759)
- [`apps/web/src/lib/i18n/vi.json`](apps/web/src/lib/i18n/vi.json:758)
- [`docs/douyin-accounts-ui-simplify-log.md`](docs/douyin-accounts-ui-simplify-log.md:1)
- [`docs/douyin-accounts-ui-simplify-resume.md`](docs/douyin-accounts-ui-simplify-resume.md:1)
- [`docs/douyin-accounts-ui-simplify-architecture.md`](docs/douyin-accounts-ui-simplify-architecture.md:1)
- [`docs/douyin-accounts-ui-simplify-user-guide.md`](docs/douyin-accounts-ui-simplify-user-guide.md:1)

## Verification Notes
- Ran [`npm run typecheck`](package.json:10) at repository root.
- TypeScript check passed for [`@reup-douyin/web`](apps/web/package.json:5) with no type errors.

## Status
- Completed: `/accounts/douyin` UI simplification and intake handoff are implemented and typechecked.
