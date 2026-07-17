# Douyin Final Challenge Cooldown Fix Resume

## Current objective

Fix the final Douyin browser-backed challenge cooldown state machine, action gating, and post-challenge result projection so a healthy managed runtime is not shown as generically blocked, cooldown is enforced correctly, and successful recovery restores Intake readiness.

## Required docs

- `docs/douyin-final-challenge-cooldown-fix-log.md`
- `docs/douyin-final-challenge-cooldown-fix-resume.md`
- `docs/douyin-final-challenge-cooldown-fix-architecture.md`
- `docs/douyin-final-challenge-cooldown-fix-user-guide.md`

## Key files

- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

## Audit summary

- `challenge_repeat_limit_reached` and `challenge_cooldown` are persisted by `_set_challenge_detected_metadata`.
- `challenge_cooldown_active` is derived by `_active_challenge_cooldown` from persisted state plus `douyin_challenge_cooldown_until`.
- Normal validation already had an active cooldown gate, but the previous projection collapsed it into generic blocked status and generic labels.
- Browser health alignment previously returned persisted challenge state, so UI gating could miss active cooldown when persisted state was `challenge_repeat_limit_reached`.
- `_challenge_postcheck_result_for` previously lacked precise categories for active cooldown and profile mismatch.
- `_run_challenge_recovery` previously mapped post-success profile mismatch to runtime unavailable, causing contradictory operator messaging.

## Implemented changes

1. Added effective challenge state projection in the API without changing persisted challenge states.
2. Updated health summary to emit challenge-specific labels/details before generic blocked projection.
3. Updated browser health alignment to expose `challenge_cooldown_active` when the cooldown deadline is in the future.
4. Added postcheck result categories and next-action mapping for active cooldown and saved-profile mismatch.
5. Cleared stale challenge/postcheck metadata before writing fresh success diagnostics.
6. Updated UI labels and button gating so normal Validate and Use in Intake are disabled during active cooldown.
7. Added focused backend tests for cooldown projection, postcheck profile mismatch, and explicit cooldown postcheck categorization.

## Verification

- `python -m unittest tests.test_douyin_account_service tests.test_intake_discovery_service` from `apps/api`: passed, 51 tests.
- `npm run typecheck` from `apps/web`: passed.
