# Douyin Final Challenge State Fix Log

## Scope

Fix the final browser-backed Douyin challenge recovery state machine so a managed active runtime with a reusable saved profile is not stuck in stale `challenge_repeat_limit_reached` state after an operator solves the challenge.

## Audit findings

- `challenge_repeat_limit_reached` is assigned in `DouyinAccountService._set_challenge_detected_metadata()` when `douyin_challenge_count` reaches `DOUYIN_CHALLENGE_REPEAT_LIMIT`.
- `douyin_challenge_count`, `douyin_challenge_cooldown_until`, `douyin_challenge_recheck_resolved`, same-runtime/profile reuse, and intake readiness after recheck are stored in account `metadata_json`.
- `Mark challenge solved` currently calls `_run_challenge_recovery()` and then `validate_account(..., validation_source="mark_challenge_solved")`, so it does run browser-backed validation when the browser-backed validation path is enabled.
- The recheck path records same runtime/profile reuse by comparing registry summaries and saved profile identity before and after validation.
- Runtime-active state can coexist with unresolved challenge state because runtime diagnostics and challenge metadata are independent projections. A live managed context does not imply the challenge was cleared.
- Stale recheck metadata can remain visible because `_clear_challenge_metadata()` clears core challenge fields but intentionally preserves some postcheck fields, while failed rechecks keep state explicit.
- Current cooldown enforcement is mostly in Ready Check / preflight. Manual Validate can still run during cooldown, and the web UI does not disable Validate / Use in Intake during cooldown.
- `challenge_repeat_limit_reached` with an unexpired cooldown is not normalized to a clear `challenge_cooldown_active` failure for Validate and operator action gating.

## Implemented changes

- Added a canonical cooldown gate that classifies both `challenge_cooldown` and `challenge_repeat_limit_reached` with active `douyin_challenge_cooldown_until` as `challenge_cooldown_active`.
- Normal/manual Validate now rejects active cooldown before browser validation runs, preserving the stored challenge state while returning `challenge_cooldown_active` as the fresh validation result.
- `mark_challenge_solved` and `challenge_recheck` remain recovery validation sources, so the operator can run the real post-challenge browser-backed recheck after completing the manual step in the saved profile.
- Ready Check / Intake preflight now reports active cooldown with the explicit `challenge_cooldown_active` state, deadline, and recovery recommendation.
- Failed post-challenge rechecks now recompute challenge count/cooldown/repeat-limit state through the canonical challenge-detected metadata updater and preserve its deterministic next action.
- Successful post-challenge rechecks still clear challenge state, challenge count, and cooldown only after browser-backed validation succeeds on the saved profile boundary.
- The Douyin Accounts UI disables Validate and Use in Intake during active cooldown, keeps Mark challenge solved available, and renders the cooldown-specific labels/recommendation.

## Verification

- `npm run typecheck` passed for the web workspace.
- `python -m unittest tests.test_douyin_account_service tests.test_intake_discovery_service` passed from `apps/api` with 48 tests.
- `python -m pytest apps/api/tests/test_douyin_account_service.py apps/api/tests/test_intake_discovery_service.py` was attempted from the repository root but could not run because `pytest` is not installed in the local Python environment.

## Change log

- 2026-04-26: Audited challenge repeat-limit assignment, persisted metadata, recovery recheck path, preflight blocking, and UI action gating.
- 2026-04-26: Implemented active cooldown gating for Validate / Ready Check / Intake while preserving Mark challenge solved as the recovery path.
- 2026-04-26: Fixed failed post-challenge recheck metadata transitions so repeated challenge responses keep deterministic cooldown/backoff state instead of falling back to generic waiting state.
- 2026-04-26: Updated UI action gating, i18n labels, backend tests, intake tests, and final verification notes.
