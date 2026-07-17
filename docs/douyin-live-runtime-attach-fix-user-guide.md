# Douyin Live Runtime Attach Fix User Guide

## What This Fix Is For

This fix addresses the case where the saved Douyin browser profile is already open, logged in, and manually verified, but validation or `Mark challenge solved` still fails because the original browser page tracked by the app was closed.

After the fix, the app should prefer the open saved browser runtime and recover by using another page or opening a fresh page inside the same saved browser context.

## Operator Workflow

1. Open the saved Douyin browser profile from the Douyin account screen.
2. Log in if needed.
3. Complete any visible captcha, slider, or security verification inside that browser.
4. Keep the browser profile open.
5. Click `Mark challenge solved` or `Validate`.
6. The app should attach to the existing live runtime/context first.
7. If the previous page was closed, the app should recover inside the same browser profile instead of reporting `first_page_closed_early:TargetClosedError`.

## Expected Results

When the profile is open and authenticated:

- `Validate` should complete browser-backed validation without requiring a new browser profile.
- `Mark challenge solved` should rerun browser-backed post-check in the same saved profile.
- If the challenge is gone, Intake should become unblocked for that account.
- Diagnostics should show same-profile reuse and either live runtime attach or same-context page recovery.
- `Runtime attach status` should show whether validation attached to the live runtime, required a reopen, or failed to attach.
- `Page recovery status` should show whether the existing page was usable, another page was reacquired, or a fresh page was created in the same context.

## If Validation Still Fails

Use the diagnostics shown on the Douyin account row:

- `challenge_still_required`: Douyin still shows a captcha/security check. Complete it in the saved browser profile and retry.
- `browser_validation_inconclusive`: the profile was reachable but did not produce enough page evidence. Retry once after the page finishes loading.
- `live_runtime_attached`: the app found and used the existing live runtime/context.
- `live_context_page_reacquired`: the remembered page was not usable, so another page in the same context was used.
- `live_context_new_page_created`: no existing page was usable, so a new page was created in the same context.
- `runtime_missing_reopen_required`: the app could not find a live runtime and will try to reopen the same saved profile.
- `reopen_success`: the same saved profile reopened successfully after the live runtime was unavailable.
- `reopen_failed`: the saved profile could not be reopened. Close duplicate Chromium/Douyin profile windows and retry opening the saved profile from the app.
- `runtime_attach_failed`: the runtime did not match the expected account/profile. Reopen the saved profile from the app to avoid attaching to the wrong context.

## Safety Notes

- This fix does not create a new Douyin browser profile for an existing saved account.
- This fix does not bypass Douyin verification.
- Cookies and secrets are not shown in diagnostics.
- The browser profile remains local-first and operator-controlled.

## Verification Checklist

A successful local verification should show:

- saved browser profile reused,
- no `first_page_closed_early:TargetClosedError`,
- validation continued in browser-profile path,
- challenge recheck resolved after successful post-check,
- Intake readiness restored only after browser-backed success.
