# Douyin Final Challenge Cooldown Fix Log

## Scope

This log tracks the final cooldown/state projection fix for Douyin browser-backed challenge recovery.

## Audit findings

- Active browser runtime ownership is not the remaining issue. The failing state is projection and action gating around challenge recovery.
- Persisted challenge states are `challenge_waiting_for_manual_verification`, `challenge_recently_solved_pending_recheck`, `challenge_cooldown`, and `challenge_repeat_limit_reached`.
- `challenge_cooldown_active` is an effective runtime projection derived from a future `douyin_challenge_cooldown_until`, not a persisted base state.
- Normal validation currently blocks during active cooldown, but sets account connection status to `BLOCKED`, which causes generic health/status labels.
- Browser health alignment returns the persisted challenge state instead of the effective active cooldown state, so the UI can miss active cooldown gating when the persisted state is `challenge_repeat_limit_reached`.
- Post-challenge profile proof failure is collapsed into `challenge_postcheck_runtime_unavailable`, which can contradict diagnostics showing a live runtime and same saved profile reuse.
- Successful post-challenge recovery clears core challenge fields, but stale postcheck/runtime-unavailable summary fields can still leak if not explicitly cleaned.

## Implementation plan

1. Add authoritative effective-state helpers in the API service without changing the persisted challenge state model.
2. Project active cooldown as `challenge_cooldown_active` in health alignment and Intake/preflight-facing summaries.
3. Keep Intake blocked and normal Validate gated while cooldown is active.
4. Keep `Mark challenge solved` and explicit post-challenge recheck as the recovery path.
5. Replace contradictory postcheck result projection with precise categories for active cooldown and profile mismatch.
6. Clear stale challenge/postcheck metadata on successful post-challenge validation.
7. Update UI gating and labels to use effective cooldown state and precise result labels.
8. Add focused tests for backend state projection and frontend-visible behavior.

## Progress

- 2026-04-26: Audit completed and mandatory docs created before code changes.
- 2026-04-26: API projection now derives `challenge_cooldown_active` at response/health/preflight projection time while preserving persisted `challenge_cooldown` and `challenge_repeat_limit_reached` metadata.
- 2026-04-26: Health summaries now emit challenge-specific labels before generic blocked projection, including active cooldown and repeat-limit states.
- 2026-04-26: Browser health alignment now exposes active cooldown as the effective challenge state, keeps repeat-limit as persisted history, and explains that a managed runtime can be healthy while Intake remains blocked by cooldown.
- 2026-04-26: Post-challenge result projection now distinguishes active cooldown and saved-profile mismatch from runtime/profile unavailability.
- 2026-04-26: Web Accounts actions now disable normal Validate and Use in Intake during active cooldown, while preserving Mark challenge solved as the recovery action.
- 2026-04-26: English and Vietnamese UI labels now show challenge-specific status/result text instead of generic blocked/runtime-mismatch text.
## Verification

- `python -m unittest tests.test_douyin_account_service tests.test_intake_discovery_service` from `apps/api`: passed, 51 tests.
- `npm run typecheck` from `apps/web`: passed.
