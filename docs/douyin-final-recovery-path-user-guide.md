# Douyin Final Recovery Path User Guide

## When You Need This

Use this recovery path when a connected Douyin account shows a browser challenge state such as `browser_validation_challenge_required`, `browser_validation_captcha_required`, `challenge_cooldown`, or `challenge_repeat_limit_reached`.

This means the saved browser profile is the recovery context. Do not create a new profile and do not use detached cookie import as the default workaround.

## Operator Steps

1. Open the Douyin Accounts page.
2. Find the affected account.
3. Open or resume the saved browser profile for that account.
4. In that same browser window, complete the Douyin challenge manually.
5. Return to the app and click `Mark challenge solved`.
6. Wait for the app to run the browser-backed post-check.
7. If the post-check succeeds, run Ready Check or Intake again.
8. If the post-check still reports a challenge or cooldown, wait for the cooldown or solve the visible challenge again before retrying.

## What `Mark challenge solved` Means

`Mark challenge solved` is a real recovery action. It does not simply toggle a flag. After you click it, the system validates the account in the saved browser profile. Intake is allowed only after that validation succeeds.

## Result Meanings

- `challenge_postcheck_success`: recovery succeeded and Intake can use the same profile again.
- `challenge_postcheck_still_required`: Douyin still shows a challenge; solve it in the same profile and retry when allowed.
- `challenge_postcheck_login_required`: the saved profile is no longer logged in; reconnect or log in again.
- `challenge_postcheck_runtime_unavailable`: the browser runtime/profile could not be opened or attached.
- `challenge_postcheck_blocked`: Douyin is still blocking the browser-backed validation.
- `challenge_postcheck_inconclusive`: validation did not prove that the account is ready.
- `challenge_postcheck_failed_unknown`: unexpected failure; retry only after reviewing the account state.

## Intake Behavior

When a challenge is unresolved, `/intake` Ready Check shows a challenge-blocked state and links back to the Douyin account. Intake should not start live fetch while challenge state is unresolved or cooldown is active. After successful post-check, Ready Check should report the browser-backed account as ready and Intake should resume through the same saved profile.

## Safety Notes

- Complete challenges only in the saved profile for the affected account.
- Do not create a replacement browser profile unless explicitly reconnecting that same account.
- Do not paste or expose cookies, tokens, credentials, or private local paths.
- Repeated failures are intentionally cooled down to avoid unsafe retry loops.
