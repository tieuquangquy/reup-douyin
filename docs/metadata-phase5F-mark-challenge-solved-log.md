# Phase 5F Mark Challenge Solved Log

## Status
- completed

## Why this is needed
- The operator can already confirm manually that the saved browser profile no longer shows Douyin captcha/challenge.
- But backend state can remain stuck in:
  - `challenge_cooldown_active`
  - `challenge_waiting_for_manual_verification`
  - `challenge_recently_solved_pending_recheck`
- That stale state keeps blocking hydration/intake before a fresh browser-backed revalidate can run.

## Planned change
- Add a narrow operator command:

```powershell
python scripts/douyin_account_readiness.py --account-id <id> --mark-challenge-solved
```

- It will:
  - clear challenge/cooldown metadata
  - reset the account into a revalidate-required state
  - not mark the account `READY` blindly
  - instruct the operator to run `--revalidate`

## Files touched
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/scripts/douyin_account_readiness.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_douyin_account_readiness_script.py`
- `docs/metadata-phase5F-mark-challenge-solved-log.md`
- `docs/metadata-phase5F-mark-challenge-solved-resume.md`

## Tests run
- `python -m unittest tests.test_douyin_account_service tests.test_douyin_account_readiness_script`
- `python -m compileall src scripts`

## Verification result
- Manual challenge-clear command is available:

```powershell
python scripts/douyin_account_readiness.py --account-id <id> --mark-challenge-solved
```

- It clears stale challenge/cooldown metadata and moves the account into `manual_revalidation_required`.
- It does not mark the account `READY`.
- It returns the required next command:

```powershell
python scripts/douyin_account_readiness.py --account-id <id> --revalidate --timeout-seconds 120
```
