# Douyin Profile Cleanup Architecture

## Objective

Reconcile old local Douyin browser profile directories into the current strict model:

```text
one DouyinAccountConnection -> one canonical persistent browser profile
```

## Inventory Categories

- `canonical`: profile directory is explicitly linked by account metadata or deterministically adopted as `account-<account_id>`.
- `duplicate_noncanonical`: profile appears related to an account or old connect flow but is not the canonical survivor.
- `orphan_unlinked`: profile has no known account link.
- `active_in_use`: runtime registry reports the profile is active or in use.
- `quarantine_candidate`: noncanonical profile safe enough to archive, not delete.

## Canonical Selection Rules

For each account, choose one canonical profile using deterministic order:

1. Existing `browser_profile_id` and `browser_profile_path` in account metadata.
2. Existing metadata path leaf if the id is missing.
3. Existing `account-<account_id>` directory when the account has no metadata.
4. No canonical profile if none of the above exist.

The cleanup service does not randomly infer an account from an old connect-session profile.

## Cleanup Policy

- Default mode is dry-run.
- Apply mode moves noncanonical profiles into `_quarantine/<timestamp>/`.
- No hard delete is performed in V1.
- Active runtime profiles are skipped and reported.
- Account metadata repairs are allowed only when deterministic.

## API

- `GET /douyin-accounts/browser-profiles/cleanup`
  - dry-run scan only
  - returns inventory, planned actions, and account mapping summaries
- `POST /douyin-accounts/browser-profiles/cleanup`
  - request body: `{ "dry_run": false, "apply": true }`
  - applies deterministic metadata repairs and quarantine moves
  - if `dry_run` remains true, no changes are applied

## Runtime Guardrails

- The runtime registry exposes active profile identifiers for cleanup protection.
- Cleanup does not close browsers or reset runtime state.
- Reset runtime state remains a separate explicit recovery action.

## One-Account-One-Profile Reconciliation

After cleanup:

- linked accounts keep or adopt exactly one canonical profile identity;
- duplicate/orphan top-level directories are outside the active profile namespace;
- reopen, retry, validation, and intake resolve through account metadata;
- quarantined profiles remain recoverable by an operator.

## Applied Local Cleanup

The first cleanup run quarantined 7 old connect-session profile directories into:

```text
_quarantine/20260423T164322Z
```

It did not hard-delete any profile directory. The final post-cleanup dry-run reports 6 top-level canonical profiles and 0 duplicate/orphan candidates.

## Limitations

- V1 does not inspect browser profile contents for login quality.
- V1 does not delete quarantine automatically.
- V1 does not guess whether an unlinked old connect-session profile belongs to an account.
