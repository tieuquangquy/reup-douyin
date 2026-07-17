# Douyin Final Recovery Path Log

## Status

Implemented and verified for the final browser-backed challenge recovery path.

## Short Implementation Plan

1. Finish the audited challenge recovery gap review across API, Intake, and web operator surfaces.
2. Keep one `DouyinAccountConnection` mapped to one saved persistent browser profile as the only primary recovery context.
3. Change the challenge action so operator confirmation triggers a real browser-backed post-challenge validation in the same profile.
4. Project structured post-check diagnostics to API and web responses.
5. Clear challenge state only after meaningful browser-backed success, including challenge count and cooldown reset.
6. Preserve safe cooldown/backoff when post-check still sees a challenge or cannot prove recovery.
7. Keep Ready Check, preflight, and Intake blocked until challenge recovery succeeds.
8. Update tests, run verification, then update this log with concrete results.

## Audit Findings Before Code Changes

- `DouyinAccountService.mark_challenge_solved()` recorded `challenge_recently_solved_pending_recheck` metadata and returned without running validation.
- `DouyinAccountService.recheck_challenge_after_solve()` performed the real browser-backed recheck, but it was a separate action after the operator mark.
- Browser validation success in `DouyinAccountService._validate_with_live_browser_context()` already cleared several challenge fields through `DouyinAccountService._clear_challenge_metadata()`, but stale `douyin_challenge_count` could remain.
- `DouyinAccountService._set_challenge_detected_metadata()` already incremented challenge count and applied cooldown or repeat-limit behavior on repeated challenge detection.
- `DouyinAccountService._challenge_preflight_block()` already blocked unresolved challenge states before Intake fetch, but cooldown-expiry metadata mutation needed a durable commit/cache-invalidating path.
- `DouyinAccountService._is_challenge_actionable()` did not include `challenge_repeat_limit_reached`, while the web UI treated it as actionable.
- `DouyinAccountsPage` showed separate `markChallengeSolved()` and `recheckChallenge()` actions.
- `IntakePage` already surfaced challenge state/category/count/cooldown and linked operators back to Douyin account controls.

## Implemented Post-Check Result Contract

The recovery action returns one of these safe result values:

- `challenge_postcheck_success`
- `challenge_postcheck_still_required`
- `challenge_postcheck_login_required`
- `challenge_postcheck_runtime_unavailable`
- `challenge_postcheck_blocked`
- `challenge_postcheck_inconclusive`
- `challenge_postcheck_failed_unknown`

## Files Touched

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

## Non-Goals Preserved

- No crawler implementation.
- No video processing implementation.
- No database schema migration for challenge metadata.
- No duplicate discovery pipeline.
- No automated captcha solving or challenge bypass.
- No re-enabling legacy manual import or detached HTTP fallback as default recovery.

## Implementation Notes

- `Mark challenge solved` now runs a browser-backed post-challenge validation immediately and returns a structured recovery result.
- The compatibility recheck endpoint now uses the same recovery engine.
- Successful post-check clears challenge state, count, cooldown, and stale challenge diagnostics while preserving safe recovery diagnostics.
- Failed post-check returns the account to an actionable manual challenge state and keeps Intake blocked.
- Same saved profile reuse is explicitly checked; a validation success without profile identity proof is downgraded to `challenge_postcheck_runtime_unavailable`.
- Cooldown expiry in preflight now clears the expired cooldown state durably and invalidates preflight cache.
- `challenge_repeat_limit_reached` is actionable so an operator can still recover manually without unsafe retry loops.
- Douyin Accounts UI now shows post-check result, same-profile reuse, runtime reopen, and Intake-ready diagnostics.

## Verification Results

- `set PYTHONPATH=apps/api&& python -m unittest apps.api.tests.test_douyin_account_service apps.api.tests.test_douyin_account_preflight apps.api.tests.test_intake_discovery_service apps.api.tests.test_douyin_live_fetch apps.api.tests.test_douyin_browser_connect_service`
  - Passed: 80 tests.
- `npm run typecheck --workspace apps/web`
  - Passed: TypeScript completed with exit code 0.
