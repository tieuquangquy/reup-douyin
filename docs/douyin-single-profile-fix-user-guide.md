# Douyin Single Profile Fix User Guide

## What This Fix Guarantees

- Opening an existing Douyin account reuses that account's saved browser profile.
- Reopening, retry validation, validation, and Intake fetch target the same
  profile identity.
- Reset runtime state clears stuck runtime sessions but does not create another
  profile or delete the saved profile.

## Normal Workflow

1. Open `/accounts/douyin`.
2. For a new account, create a browser profile and login once.
3. For an existing account, use **Open/Reopen profile**.
4. Validate the account.
5. Use the account in Intake.

## If You See A New Browser Profile

That should only happen when creating a new Douyin account. For an existing
account, it indicates either:

- the account has no saved profile metadata yet, so the backend creates the one
  canonical `account-{id}` profile for it, or
- a stale older connect session is being cancelled/reset.

## Troubleshooting

- Use **Reset runtime state** if a browser runtime is stuck.
- Do not use manual import as the primary path.
- If an operation fails with `profile_identity_mismatch`, the backend protected
  the account from being rebound to a different profile. Reopen the account's
  saved profile or reset stuck runtime state.
- If another account already has an active browser connect session, cancel or
  reset that session before opening this account's profile.
