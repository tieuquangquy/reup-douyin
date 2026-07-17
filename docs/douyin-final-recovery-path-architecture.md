# Douyin Final Recovery Path Architecture

## Objective

Provide one decisive browser-backed challenge recovery path for connected Douyin accounts. A human operator solves the Douyin challenge in the account's saved browser profile, clicks `Mark challenge solved`, and the system immediately performs browser-backed validation in that same profile before clearing state or allowing Intake.

## Canonical Model

- Account identity is `DouyinAccountConnection`.
- Profile identity is the saved browser profile metadata for that account, especially profile id/path metadata already attached to the account.
- Recovery context is the live browser runtime when present, or a reopened runtime bound to the exact saved profile when the live runtime is gone.
- Successful recovery evidence is a meaningful browser-backed validation success from the same saved profile.
- Operator confirmation alone is not success evidence.

## State Machine

### Challenge Detection

Browser validation may produce explicit challenge validation categories:

- `browser_validation_challenge_required`
- `browser_validation_captcha_required`
- `browser_validation_manual_verification_required`

Those map to unresolved account challenge states:

- `challenge_waiting_for_manual_verification`
- `challenge_cooldown`
- `challenge_repeat_limit_reached`

Repeated challenge detection increments count and can add cooldown. These states block Ready Check, preflight, and Intake.

### Manual Solve Action

The final `Mark challenge solved` action performs these steps atomically from the operator perspective:

1. Confirm the account has a saved reusable browser profile.
2. Confirm the current challenge state is actionable.
3. Record `mark_challenge_solved_attempted` and solve attempt timestamps.
4. Start a post-challenge browser-backed validation attempt.
5. Reuse the live runtime when it is still bound to the same account/profile.
6. Reopen the exact saved profile when runtime is missing.
7. Map the validation result to a structured post-check result.
8. Update challenge state, health projection, and preflight cache according to the result.

### Post-Check Results

- `challenge_postcheck_success`: validation passed with browser evidence; clear challenge state, count, and cooldown; restore account readiness.
- `challenge_postcheck_still_required`: Douyin still shows challenge/captcha/manual verification; preserve challenge state and apply count/cooldown rules.
- `challenge_postcheck_login_required`: browser profile is no longer logged in; account remains not ready and operator must reconnect/login.
- `challenge_postcheck_runtime_unavailable`: same saved profile cannot currently be launched or attached.
- `challenge_postcheck_blocked`: validation reached a browser-backed hard block that is not a normal challenge success.
- `challenge_postcheck_inconclusive`: browser validation did not prove success or a clear operator action.
- `challenge_postcheck_failed_unknown`: unexpected failure path; account remains blocked until a safe retry or manual review.

## Clearing Rules

Challenge state may be cleared only when browser-backed validation returns meaningful success for the account's same saved profile. Clearing must remove unresolved state, challenge detection flags, challenge count, cooldown, and recommended challenge action. Diagnostic attempt id/timestamps may remain if they do not make the account look blocked.

## Backoff Rules

When post-check still sees a challenge, the system must not spin. It should reuse existing challenge count/cooldown behavior and make repeated challenge loops explicit through `challenge_cooldown` or `challenge_repeat_limit_reached`.

## Intake Gate

Ready Check, fetch preflight, and Intake discovery must treat unresolved challenge states as stronger evidence than active runtime/watchdog status. Intake can resume only after post-check success updates the account to ready browser-backed status and invalidates stale preflight cache.

## API Surface

The existing account challenge routes should remain stable where possible, but `Mark challenge solved` must become the real recovery action. The old separate recheck route can be preserved as compatibility if it calls the same recovery implementation and returns the same structured diagnostics.

## UI Surface

The Douyin Accounts screen should present one primary challenge recovery action: solve the visible challenge in the same browser profile, then click `Mark challenge solved`. The result message should report the structured post-check result and whether Intake is ready afterward. The Intake screen should continue linking blocked operators back to the account recovery controls.

## Observability And Safety

- Do not log or display cookies, tokens, credentials, or private local paths.
- Include stable identifiers in backend logs if logging is added.
- Expose only safe boolean/status diagnostics for same-profile reuse and runtime reopen.
- Never silently create a new browser profile during recovery.

## Non-Goals

- No Douyin security bypass.
- No automated captcha solving.
- No schema migration in this step.
- No new canonical ingestion/discovery pipeline.
- No default use of legacy detached HTTP fallback.
