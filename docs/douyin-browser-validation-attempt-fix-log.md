# douyin-browser-validation-attempt-fix-log.md

## Status

- Audit completed.
- Docs created before major code changes.
- Implementation completed.
- Verification passed.

## Audit Findings

The current contradictory UI state can happen because browser validation metadata is persisted as unscoped `last_*` fields in account metadata.

Observed sources:

1. `_validate_with_live_browser_context()` writes reopen attempt fields only when auto-reopen is needed.
2. Later validation attempts with an already active browser runtime do not clear those old reopen fields.
3. `_validate_with_live_browser_context()` currently ORs `last_browser_validation_continued_after_reopen` with the previous persisted value, which can keep old continuation state alive across attempts.
4. `_browser_health_alignment_summary()` reads `last_browser_validation_auto_reopen_attempted`, `last_browser_validation_reopen_status`, `last_browser_validation_runtime_reattached`, and `last_browser_validation_continued_after_reopen` directly from metadata without checking an attempt id.
5. The web UI renders runtime reattached and validation continued fields even when the current attempt did not perform reopen.
6. Browser probe status `blocked` with reason `browser_context_blocked_response` is mapped to generic `browser_validation_inconclusive`, so operators see a vague result instead of a captcha/challenge/manual verification category.

## Implemented Fix

- `DouyinAccountService._validate_with_live_browser_context()` now starts each browser-backed Validate run by clearing attempt-specific browser validation diagnostics and assigning `last_browser_validation_attempt_id`.
- Current-attempt reopen fields are initialized to false and only populated as reopen details when the current attempt actually tries reopen.
- The stale boolean merge was removed; `last_browser_validation_continued_after_reopen` is now the current attempt value only.
- Browser context `blocked` results are classified into explicit categories:
  - `browser_validation_captcha_required`
  - `browser_validation_challenge_required`
  - `browser_validation_manual_verification_required`
- `browser_context_blocked_response` now maps to `browser_validation_challenge_required` with recommended next action `complete_challenge_in_browser_profile`.
- Browser health alignment projection now exposes current-attempt challenge fields and suppresses reopen status/reattach/continued values when current attempt did not perform auto-reopen.
- `/accounts/douyin` UI now shows challenge category and recommended next action, and only shows runtime reattach/continued diagnostics under current-attempt auto-reopen.

## Verification

Passed:

```cmd
python -m py_compile apps/api/src/services/douyin_account_service.py apps/api/src/schemas/douyin_accounts.py apps/api/tests/test_douyin_account_service.py && set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service apps.api.tests.test_douyin_browser_connect_service && npm --prefix apps/web run typecheck
```

Result:

- `py_compile` passed.
- `unittest` ran 47 tests and passed.
- `npm --prefix apps/web run typecheck` passed.
