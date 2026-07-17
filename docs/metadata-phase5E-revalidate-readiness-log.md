# Phase 5E-R Revalidate Readiness Log

## Status
- completed

## Root cause
- The account exists and has a saved browser profile path, but it remains:
  - `status = INVALID`
  - `health_status = UNKNOWN`
- `preflight_fetch_readiness(...)` blocks early on account health before fetch-path readiness can pass.
- The missing operator path is a browser-backed revalidation command that updates account status/health after manual login or captcha completion.

## Audit findings
- `DouyinAccountService.validate_account(...)` already contains the browser-backed validation path.
- It can:
  - reuse an existing live browser runtime
  - reopen the saved persistent profile if needed
  - validate Douyin access through `validate_account_context(...)`
  - update account status/health to `ACTIVE` / `HEALTHY` on success
- `douyin_account_readiness.py` currently supports:
  - list readiness
  - create browser-backed account
  - attach profile
  - set default
  - open profile
- It does **not** yet expose a `--revalidate` action.

## Planned implementation
1. Add `--revalidate` to `python scripts/douyin_account_readiness.py`.
2. Use the existing saved browser profile and browser-backed validation path.
3. Return explicit success/failure JSON with next commands.
4. Improve hydration script guidance for `account_not_fetch_ready`.

## Files touched
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
- `docs/metadata-phase5E-revalidate-readiness-log.md`
- `docs/metadata-phase5E-revalidate-readiness-resume.md`
- `docs/metadata-phase5E-revalidate-operator-guide.md`

## Exact commands

### Check current readiness

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172
```

### Open the saved browser profile

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --open-profile --timeout-seconds 300
```

### Revalidate after manual login/captcha completion

```powershell
cd apps/api
python scripts/douyin_account_readiness.py --account-id 552e16ae-2d5c-40a6-a26c-bc917b28a172 --revalidate --timeout-seconds 120
```

### Rerun hydration

```powershell
cd apps/api
python scripts/hydrate_capture_session_metadata.py --session-id a57e64d1-a7a8-48e0-b49a-199128b25740
```

## Success/failure behavior
- Success:
  - `status = ACTIVE`
  - `health_status = HEALTHY`
  - `readiness_status = READY`
- Failure examples:
  - `manual_login_required`
  - `captcha_required`
  - `profile_open_failed`
  - `douyin_blocked`
- Readiness listing now surfaces `manual_revalidation_required` instead of the generic `account_not_fetch_ready` when the account has a saved browser profile but has never been successfully browser-revalidated.

## Tests run
- `python -m unittest tests.test_douyin_account_readiness_script tests.test_hydrate_capture_session_metadata_script`
- `python -m compileall src scripts`

## Verification
- Passed focused tests.
- Live readiness check for account `552e16ae-2d5c-40a6-a26c-bc917b28a172` now reports:
  - `blocking_reason = manual_revalidation_required`
  - instead of the less actionable generic `account_not_fetch_ready`.
