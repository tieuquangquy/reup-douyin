# Douyin Profile Cleanup Log

## Status

Completed.

## Findings

- Persistent browser profiles are stored under `DOUYIN_PERSISTENT_BROWSER_PROFILES_ROOT_DIR`, currently `./data/browser-profiles/douyin` from the API process.
- Account profile identity is canonical on `DouyinAccountConnection.metadata_json`:
  - `browser_profile_id`
  - `browser_profile_path`
  - `browser_profile_mode = persistent_profile`
- The current local profile root contains 13 top-level profile directories.
- One account is linked to profile `00f25893-d246716e-0157-4f10-a42f-1988105cd9ec`.
- One active account currently has no profile metadata and must not be guessed into an unrelated old profile.
- Several directories use old connect-session style names like `<workspace-prefix>-<connect-session-id>`.
- Several directories use `account-<uuid>` names that are not currently linked by any account metadata.
- API dry-run found 16 account records including disabled/soft-deleted history.
- Final dry-run after cleanup found:
  - `profiles_scanned = 6`
  - `canonical_count = 6`
  - `duplicate_count = 0`
  - `orphan_count = 0`
  - `quarantine_count = 0`
  - `metadata_repairs_count = 0`

## Duplicate / Orphan Patterns

- A directory named by the account's explicit `browser_profile_id` or `browser_profile_path` is the canonical survivor.
- A directory named `account-<account_id>` can be adopted only for that exact account when the account has no profile metadata.
- Old connect-session profile names are treated as unlinked orphan candidates unless an account explicitly points at them.
- Unknown top-level directories are treated as orphan candidates.
- Runtime-active profiles are protected from quarantine.

## Reconciliation Policy

- Dry-run is available and is the default.
- Apply mode is explicit.
- The service never hard-deletes browser profiles.
- Noncanonical duplicate/orphan profiles are moved into a timestamped `_quarantine` folder under the same profile root.
- Active/in-use profiles are skipped.
- Account metadata can be repaired when a deterministic canonical profile exists.

## Files Touched

- `apps/api/src/services/douyin_profile_cleanup_service.py`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/tests/test_douyin_profile_cleanup_service.py`
- `docs/douyin-profile-cleanup-log.md`
- `docs/douyin-profile-cleanup-resume.md`
- `docs/douyin-profile-cleanup-architecture.md`
- `docs/douyin-profile-cleanup-user-guide.md`

## Verification Notes

- Unit tests passed:
  - `python -m unittest tests.test_douyin_profile_cleanup_service tests.test_douyin_browser_connect_service tests.test_douyin_account_service`
  - `python -m unittest tests.test_douyin_profile_cleanup_service tests.test_douyin_browser_connect_service tests.test_douyin_account_preflight tests.test_douyin_account_service tests.test_douyin_live_fetch tests.test_intake_discovery_service`
- Compile passed:
  - `python -m compileall src`
- Smoke passed:
  - `npm run smoke`
- Dry-run before apply:
  - 13 profiles scanned
  - 6 canonical profiles kept
  - 7 duplicate old connect-session profiles planned for quarantine
  - 0 active profiles skipped
  - 3 deterministic metadata repairs planned
- Apply result:
  - 7 duplicate profiles moved to `_quarantine/20260423T164322Z`
  - 3 account metadata repairs applied
  - 0 profiles hard-deleted
- Dry-run after apply:
  - 6 profiles scanned
  - 6 canonical profiles kept
  - 0 duplicate/orphan quarantine candidates remain
