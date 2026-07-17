# Phase 5E Browser Profile Readiness Log

## Status
- completed

## Root cause
- Phase 5D hydration script failed with:
  - `browser_profile_required`
  - `No browser-profile-backed Douyin account is available for metadata hydration.`
- Live DB audit confirms the environment currently has no usable active browser-profile-backed Douyin account.

## Existing account/profile model audit
- Accounts live in `douyin_account_connections`.
- Browser-profile-backed identity is stored in `DouyinAccountConnection.metadata_json`:
  - `browser_profile_id`
  - `browser_profile_path`
- Browser runtime reuse/open lives in:
  - `DouyinAccountService.preflight_fetch_readiness(...)`
  - `DouyinAccountService._ensure_persistent_profile_context(...)`
  - `douyin_browser_context_registry.open_profile_for_account(...)`

## Live DB findings
- Total account rows present: `17`
- Non-deleted usable accounts: `0`
- All existing rows are currently soft-deleted / `DISABLED`
- Some deleted rows still have browser profile paths on disk, but they are not eligible for hydration because they are archived accounts, not active usable accounts

## Why hydration cannot run now
- Hydration resolves a browser-backed account from active account rows only.
- Since all account rows are deleted/disabled, default selection and browser-profile-backed preflight have no eligible account to use.

## Planned implementation
1. Add a readiness command to list active/deleted account/browser profile state.
2. Add a narrow browser-profile bootstrap path:
   - create a browser-profile-backed account row
   - attach a profile path to an account
   - set default account
3. Reuse existing browser connect/open-login flow for manual login.
4. Improve hydration script guidance so `browser_profile_required` points directly to the readiness command.

## Readiness command usage

### Inspect current readiness

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --include-deleted
```

### Create a fresh browser-profile-backed account and mark it default

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --create-browser-account --display-name "Douyin Hydration Browser" --set-default
```

### Open the saved browser profile for manual login

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id <new_account_id> --open-profile
```

### Attach an existing local browser profile path instead of creating a fresh one

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id <account_id> --attach-profile --profile-path "<profile_path>"
```

### Mark an account as default

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id <account_id> --set-default
```

## Manual login steps
1. Create a fresh browser-backed account row or attach an existing browser profile path.
2. Run `--open-profile` for that account.
3. Log into Douyin in the opened persistent browser profile.
4. Leave the browser open until the connect flow settles or rerun readiness after login.
5. Recheck:
   - `python scripts/douyin_account_readiness.py`
6. Rerun hydration:
   - `python scripts/hydrate_capture_session_metadata.py --session-id a57e64d1-a7a8-48e0-b49a-199128b25740`

## Files touched
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
- `docs/metadata-phase5E-browser-profile-readiness-log.md`
- `docs/metadata-phase5E-browser-profile-readiness-resume.md`

## Tests run
- `python -m unittest tests.test_douyin_account_readiness_script tests.test_hydrate_capture_session_metadata_script`
- `python -m compileall src scripts`

## Verification
- Readiness command runs against the live DB and confirms the current environment has `17` account rows but `0` non-deleted usable browser-profile-backed accounts.
- Hydration script now points directly to `python scripts/douyin_account_readiness.py` when it fails with `browser_profile_required`.
