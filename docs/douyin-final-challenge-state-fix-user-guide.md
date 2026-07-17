# Douyin Final Challenge State Fix User Guide

## What changed

If a Douyin browser challenge repeats too many times, the account enters a challenge cooldown. A managed browser may still be active and attached, but Intake remains blocked until the challenge is actually cleared by a browser-backed post-challenge recheck.

## Operator workflow

1. Open or reuse the saved browser profile from the app.
2. Complete the Douyin challenge in that managed browser window.
3. Click Mark challenge solved.
4. Wait for the post-challenge recheck result.

## During cooldown

- Validate is disabled in the UI and blocked by the API as normal validation.
- Use in Intake is disabled in the UI and blocked by Ready Check / preflight.
- Mark challenge solved remains the recovery action after the operator manually completes the challenge.
- The UI shows the `challenge_cooldown_active` state, cooldown deadline, and recommended action.

## Successful recovery

When the post-challenge recheck succeeds on the saved browser profile:

- challenge state is cleared,
- challenge count is reset,
- cooldown is cleared,
- account health returns to usable,
- Intake can use the same saved browser profile again.

## Failed recovery

If the post-challenge recheck still sees a challenge:

- challenge state remains visible,
- cooldown/backoff is updated,
- Intake stays blocked,
- the recommended next action tells the operator to complete the browser challenge and mark it solved again.

## Important distinction

An active managed runtime means the app owns the browser context. It does not mean the Douyin challenge is solved. Runtime state and challenge state are shown separately.
