# Douyin Final Challenge State Fix Resume

## Current objective

Fix the final Douyin browser-backed challenge recovery state machine so active managed runtime/profile diagnostics no longer mask unresolved challenge cooldown/recheck state.

## Non-negotiables

- Challenge state remains authoritative until cleared by real browser-backed success.
- Active cooldown blocks normal Validate and Intake.
- Mark challenge solved performs the real post-challenge browser-backed recheck.
- Successful postcheck clears challenge metadata, counters, and cooldown.
- Failed postcheck keeps challenge state explicit and recomputes cooldown/backoff deterministically.
- Runtime state, page state, challenge state, recheck result, and final validation category are reported separately.

## Completed implementation

1. Added cooldown helper logic to classify active cooldown and build consistent validation/preflight blocking.
2. Gated `validate_account()` for normal/manual validation when active cooldown is present.
3. Preserved `mark_challenge_solved` / `challenge_recheck` as allowed recovery validation sources.
4. Updated `_run_challenge_recovery()` so failed challenge postchecks call the canonical challenge-detected metadata updater rather than overwriting repeat-limit state with generic waiting state.
5. Kept `_clear_challenge_metadata()` as the success-only cleanup path for counters/cooldown/core challenge state while preserving postcheck evidence.
6. Updated Ready Check / Intake summaries for `challenge_cooldown_active`.
7. Updated web action gating for Validate and Use in Intake during cooldown, while keeping Mark challenge solved available.
8. Added/updated focused backend tests for cooldown gating, successful clearing, failed recheck persistence, intake readiness summaries, and stale diagnostic expectations.

## Verification scenarios

- Repeat-limit with active cooldown rejects normal Validate as `challenge_cooldown_active`: covered by `test_validate_blocks_normal_action_during_active_challenge_cooldown`.
- Ready Check / preflight reports not ready with challenge cooldown details: covered by intake ready-check tests for `challenge_cooldown_active`.
- Use in Intake is disabled/blocked while cooldown is active: enforced by backend preflight and frontend action gating.
- Mark challenge solved runs browser-backed validation despite cooldown: recovery validation sources bypass the cooldown gate.
- Successful postcheck clears challenge state and restores active/healthy/readiness: covered by `test_recheck_challenge_success_clears_unresolved_challenge_metadata`.
- Failed postcheck leaves challenge state explicit and updates count/cooldown deterministically: covered by `test_mark_challenge_solved_runs_post_solve_recheck_and_keeps_intake_blocked_when_challenge_remains`.
- Managed runtime active does not render runtime-unavailable recovery text unless runtime actually fails: preserved by separate runtime/challenge projections and stale diagnostic reset coverage.

## Verification commands

- `npm run typecheck` passed.
- `python -m unittest tests.test_douyin_account_service tests.test_intake_discovery_service` passed from `apps/api` with 48 tests.
- `python -m pytest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_intake_discovery_service.py` could not run because `pytest` is not installed.
