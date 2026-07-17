# Douyin Single Profile Fix Architecture

## Rule

For the primary local-dev path:

```text
one DouyinAccountConnection -> one persistent browser_profile_id/path
```

Retry, reopen, validation, preflight, fetch, watchdog, and reset must operate on
that same identity.

## Canonical Profile Identity

The canonical identity lives on `DouyinAccountConnection.metadata_json`:

- `browser_profile_id`
- `browser_profile_path`
- `browser_profile_mode = persistent_profile`

If an account has no stored profile yet and the operator opens that account's
browser profile, the backend allocates:

```text
browser_profile_id = account-{account_id}
browser_profile_path = <profiles_root>/account-{account_id}
```

## Allocation Rules

Allowed profile allocation:

- New account connect before account creation: temporary connect-session profile,
  persisted onto the new account after login capture.
- Existing account with no profile metadata: one canonical `account-{id}`
  profile.

Disallowed:

- Restart of an existing account creating a connect-session profile.
- Reopen of an existing account attaching to a different active account session.
- Validation/intake creating a new identity when account metadata already exists.
- Reset runtime state allocating a new profile.

## Reuse Rules

- Reopen uses account metadata profile id/path.
- Retry validation uses `session.derived_account_id`, then account metadata.
- Intake preflight/fetch calls account service, which opens the same stored
  profile through the registry.
- Runtime reset closes/cancels runtime sessions only; persisted profile metadata
  remains untouched.

## Guardrails

- Existing-account capture compares runtime returned profile id/path with the
  account's canonical profile metadata.
- Mismatches fail with `profile_identity_mismatch`.
- Restart preserves `derived_account_id` from the old session if the new request
  did not explicitly provide an account id.
- Active sessions can only be reused for the same target account.
- Path-only legacy metadata is normalized to a safe profile id from the path
  directory name for diagnostics and reuse.
- Existing runtime records for the same account but a different profile are
  closed before reopening the canonical profile.

## Migration And Cleanup

No automatic deletion of old profile directories is performed. If duplicate
directories exist from previous broken runs, the account metadata profile is the
canonical survivor. Orphaned runtime directories can be cleaned manually after
confirming they are not referenced by any account metadata.

## Verification

Tests cover:

- stable account profile id generation,
- path-only profile metadata normalization,
- rejecting different profile identities,
- preserving derived account id on restart,
- rejecting unrelated active sessions for account-specific opens.
