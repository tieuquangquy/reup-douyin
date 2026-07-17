# Phase 5E Operator Confirm Ready Log

## Status
- completed

## Why this is needed
- Automated browser-backed revalidate can end as `browser_validation_inconclusive`.
- The operator may still have manually verified that the saved browser profile is logged into Douyin and usable.
- Hydration needs a narrow operator-confirmed path that allows a browser-backed attempt without claiming automated validation passed.

## Planned change
- Add:

```powershell
python scripts/douyin_account_readiness.py --account-id <id> --operator-confirm-ready
```

- It will:
  - clear stale challenge/inconclusive state
  - store `operator_confirmed_ready_at`
  - keep the account distinct from automated `READY`
  - allow hydration to proceed for a short TTL window using the saved browser profile
  - keep captcha/block stop behavior unchanged

## Files touched
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/scripts/hydrate_capture_session_metadata.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `apps/api/tests/test_capture_inbox_metadata_hydration_service.py`
- `apps/api/tests/test_hydrate_capture_session_metadata_script.py`
- `docs/metadata-phase5E-operator-confirm-ready-log.md`
- `docs/metadata-phase5E-operator-confirm-ready-resume.md`

## Tests run
- `python -m unittest tests.test_douyin_account_service tests.test_douyin_account_readiness_script tests.test_capture_inbox_metadata_hydration_service tests.test_hydrate_capture_session_metadata_script`
- `python -m compileall src scripts`

## Verification result
- Added `--operator-confirm-ready` command.
- Operator confirmation stores `operator_confirmed_ready_at` and clears stale challenge/inconclusive markers.
- Preflight now returns a browser-profile pass for `fetch_ready_operator_confirmed` within a 6-hour TTL.
- Hydration continues to stop safely on captcha/block; this path only relaxes the readiness gate, not captcha handling.
