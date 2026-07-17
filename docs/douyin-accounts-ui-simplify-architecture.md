# Douyin Accounts UI Simplify Architecture

## Final Mental Model
Each saved Douyin account is backed by one reusable local browser profile.

The page should make this obvious:
- create a new account by opening a browser profile
- reopen the saved profile for an existing account
- validate readiness for live fetch
- send the chosen account into intake
- recover from stuck local runtime state when needed

The page should no longer feel like a browser-connect session console.

## Canonical Primary Actions
For an existing account, the canonical row-level operator actions are:
1. `Open profile` / `Reopen profile`
2. `Validate`
3. `Use in intake`
4. `Reset runtime state`
5. `Delete account`

For creation, the main top-level action remains:
- `Connect with browser`

That creation action is for creating a new account-backed persistent profile, not for teaching the operator a second ongoing mental model.

## Secondary Troubleshooting Actions
The following remain available only as secondary troubleshooting or dev recovery tools:
- resume active connect session
- cancel active connect session
- force restart connect
- retry validation for a connect session
- manual session import fallback
- connect-session diagnostics and phase details

These actions remain inside the existing canonical browser-connect backend flow. They are merely demoted in UI prominence.

## Wording Cleanup Decisions
Primary wording should use:
- reusable local browser profile
- open the saved browser profile
- validate account readiness for live fetch
- use this account in intake
- reset stuck browser runtime state

Primary wording should avoid:
- connect session
- retry connect
- force restart connect
- validation retry ready
- active session exists

Those terms are allowed only inside troubleshooting details when technically necessary.

## Layout Model
Recommended operator reading order:
1. page title and profile-centric subtitle
2. create a new account with browser
3. saved connected accounts table
4. clean primary row actions
5. collapsed troubleshooting/fallback section

## Row Action Model
Each row should visually prioritize the final operator path:
- Open/Reopen profile
- Validate
- Use in intake
- Reset runtime state
- Delete

Rare or non-canonical controls should not sit in the main row action cluster.

## Intake Integration
`Use in intake` should navigate to [`/intake`](apps/web/src/components/intake/IntakePage.tsx:44) with a minimal safe account-selection bridge.

The bridge should:
- reuse existing account ids
- not create a parallel source of truth
- allow intake to continue showing canonical health warnings
- preserve backend resolution logic from [`IntakeDiscoveryService`](docs/douyin-intake-account-selection-architecture.md:43)

## No-Duplication Strategy
This step must not add:
- a second account model
- a second validation model
- a second intake-selection authority
- a second browser-connect pipeline
- a new architecture for manual import

The simplification is purely an operator-surface cleanup over the existing persistent-profile architecture.
