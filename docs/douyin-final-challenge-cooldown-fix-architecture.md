# Douyin Final Challenge Cooldown Fix Architecture

## Problem

A Douyin account can have a healthy app-managed browser runtime and still be in a manual challenge cooldown. The system must not conflate these facts:

- Runtime health answers whether the app can attach to the saved browser profile.
- Challenge readiness answers whether Douyin currently requires manual verification or cooldown.
- Intake readiness must require both a usable runtime path and no unresolved challenge/cooldown state.

The previous behavior projected active challenge cooldown through generic `BLOCKED` health/status and exposed persisted `challenge_repeat_limit_reached` to the UI, so Validate and Use in Intake could look available while Intake was not ready.

## Authoritative state model

### Persisted challenge state

Persisted metadata keeps durable recovery history:

- `challenge_waiting_for_manual_verification`
- `challenge_recently_solved_pending_recheck`
- `challenge_cooldown`
- `challenge_repeat_limit_reached`

These are stored in `douyin_challenge_state` and should not be replaced by a transient effective value.

### Effective challenge state

Effective state is computed at projection time:

- If persisted state is `challenge_cooldown` or `challenge_repeat_limit_reached` and `douyin_challenge_cooldown_until` is in the future, effective state is `challenge_cooldown_active`.
- If cooldown is expired or missing, effective state remains the persisted challenge state.
- If post-challenge validation succeeds, challenge metadata is cleared and readiness can be restored.

### Account connection status

Connection status should not be the sole operator truth for challenge recovery. A managed runtime can be active while the account is temporarily not fetch-ready due to challenge cooldown. Health labels and browser health alignment project challenge-specific text before generic blocked text.

## Action model

- Normal `Validate` is blocked while effective state is `challenge_cooldown_active`.
- `Use in Intake` is blocked while effective state is `challenge_cooldown_active` or another unresolved challenge state.
- `Mark challenge solved` remains the main recovery action for manual completion.
- Post-challenge recheck can bypass cooldown gating because it is the explicit recovery path.

## Post-challenge result taxonomy

Postcheck result categories should describe the fresh attempt truthfully:

- `challenge_postcheck_success`: validation succeeded, same saved profile was confirmed, state cleared.
- `challenge_postcheck_still_required`: Douyin still requires captcha/challenge/manual verification.
- `challenge_postcheck_cooldown_active`: a fresh recovery attempt is still constrained by challenge cooldown/backoff.
- `challenge_postcheck_profile_mismatch`: validation did not prove reuse of the saved profile.
- `challenge_postcheck_runtime_unavailable`: runtime or saved profile really could not be opened/attached.
- `challenge_postcheck_login_required`: saved profile requires login.
- `challenge_postcheck_blocked`: browser validation is blocked outside the explicit challenge categories.
- `challenge_postcheck_inconclusive`: browser validation did not produce a safe conclusion.
- `challenge_postcheck_failed_unknown`: fallback category for unclassified failures.

## Metadata cleanup

Successful post-challenge validation clears unresolved challenge metadata before writing fresh success diagnostics. This prevents prior runtime-unavailable, profile-mismatch, cooldown, or challenge-required state from leaking into a ready account after a fresh saved-profile success.

## Verification

- API focused tests cover active cooldown projection, cooldown gating, successful state clearing, failed challenge cooldown recomputation, explicit cooldown postcheck categorization, and profile mismatch postcheck projection.
- Web typecheck confirms the challenge-specific labels and action gating compile with existing account contracts.

## Non-goals

- No crawler implementation.
- No video processing changes.
- No database migration unless required by existing enum constraints.
- No rewrite of browser runtime ownership.
- No SaaS/multi-user workflow implementation.
