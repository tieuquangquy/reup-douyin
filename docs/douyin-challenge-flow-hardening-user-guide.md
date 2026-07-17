# Douyin Challenge Flow Hardening User Guide

## When This Appears

A Douyin account can show `browser_validation_challenge_required` when Douyin presents a security challenge or captcha inside the saved reusable browser profile. This usually means the browser/runtime wiring is working, but Douyin needs a human to complete verification.

## Operator Flow

1. Open `/accounts/douyin`.
2. Find the affected Douyin account.
3. Open the reusable browser profile for that account.
4. Complete the visible Douyin challenge manually in the browser window.
5. Click “Mark challenge solved”.
6. Run the post-solve challenge recheck.
7. Use the account in Intake only after browser-backed validation succeeds.

## Intake Behavior

If a challenge is unresolved, Intake ready check returns `CHALLENGE_BLOCKED`, shows the challenge state/category/count/cooldown diagnostics, and links back to the Douyin account challenge controls. Intake should not run live fetch until a post-solve browser validation succeeds.

## Important Notes

- Do not import a detached cookie to bypass this state.
- Do not create a second profile for the same account.
- An active browser runtime is not enough; the latest browser-backed validation must pass after the challenge is solved.
- If the challenge repeats too many times, wait for cooldown or review the account manually before retrying.

## Diagnostics To Expect

The account and Intake screens should expose safe diagnostics such as:

- challenge detected: yes/no
- challenge category
- recommended next action
- challenge count
- last challenge time
- cooldown until
- latest post-solve recheck result
- whether the same browser profile/runtime was reused

No secrets, cookies, tokens, credentials, or private local paths should be displayed.
