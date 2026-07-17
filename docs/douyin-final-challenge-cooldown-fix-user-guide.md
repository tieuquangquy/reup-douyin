# Douyin Final Challenge Cooldown Fix User Guide

## What this fixes

When Douyin shows repeated captcha/security/manual verification challenges, the account can enter a cooldown. The app must show this as a challenge recovery state, not as a generic broken browser runtime.

## Expected operator flow

1. Open the saved Douyin browser profile from Accounts.
2. Complete the Douyin challenge in that saved browser profile.
3. If the account shows active cooldown, wait until the cooldown expires or complete the challenge manually if Douyin allows it.
4. Click `Mark challenge solved` after manual completion.
5. Let the browser-backed post-challenge validation run.
6. If validation succeeds, Intake readiness is restored.
7. If validation fails, follow the specific next action shown in Accounts.

## Button behavior

- `Validate` is disabled while challenge cooldown is active because normal validation should not hammer Douyin during backoff.
- `Use in Intake` is disabled while challenge cooldown or unresolved challenge state is active because live fetch is not safe to run.
- `Mark challenge solved` remains available for actionable challenge states and is the intended recovery action.
- `Open profile` remains available so the operator can solve the challenge in the saved profile.

## Reading result messages

- `Challenge cooldown active`: the saved runtime can still be healthy, but Intake and normal Validate are paused by cooldown/backoff.
- `Success; challenge cleared and Intake is ready`: the saved profile validated successfully and Intake can resume.
- `Challenge is still required in the browser profile`: solve the Douyin challenge in the profile, then mark solved again.
- `Challenge cooldown is still active`: wait or finish the manual challenge in the saved profile before retrying.
- `Saved browser profile mismatch`: the validation did not prove the same saved profile; reopen the profile from the app and retry.
- `Browser runtime/profile is unavailable`: the app could not open or attach the runtime/profile; fix browser runtime setup or close conflicting external browsers.
- `Login is required`: log into Douyin again in the saved profile.

## Verification status

This fix was verified with focused API unit tests and web typechecking on 2026-04-26.

## Safety notes

- Do not paste passwords or secrets into logs or issue reports.
- The UI only shows safe metadata and diagnostics.
- Use the app-managed Open profile action instead of opening the profile directory manually in another browser.
