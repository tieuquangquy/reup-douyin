# douyin-browser-validation-attempt-fix-user-guide.md

## What Changed

Browser-backed Douyin validation diagnostics are now treated as a current-attempt snapshot. Each browser-backed Validate run gets a fresh attempt id and overwrites attempt-scoped reopen/challenge/result fields.

Before this fix, a later Validate attempt could show an active browser runtime and a current browser probe result while still displaying old reopen failure fields from an earlier attempt. That made the account look like it both failed reopen and reached browser validation at the same time.

## Expected Operator Meaning

- Active runtime: the saved browser profile is currently open and attached.
- Validation success: the browser probe produced usable authenticated evidence.
- Challenge/captcha/manual verification: the browser is open, but Douyin is asking for an operator action before validation can pass.
- Reopen failed: shown only when the current Validate attempt actually tried and failed to reopen the saved profile.

## Challenge Categories

The UI may show:

- `captcha_required`: solve captcha in the open profile, then retry Validate.
- `challenge_required`: complete Douyin security verification in the open profile, then retry Validate.
- `manual_verification_required`: inspect the open profile and complete any verification prompt, then retry Validate.

The previous generic `browser_validation_inconclusive` result is still reserved for uncertain browser probes. A browser-context blocked/challenge response now surfaces as a stronger explicit operator-action category instead of remaining generic.

## Recommended Operator Actions

- If runtime is active and captcha/challenge is shown: solve it in the open profile, then retry Validate.
- If runtime is missing: use Reopen profile or Validate to auto-reopen.
- If profile reopen fails: check browser/runtime setup or whether another process locked the profile.
- If login is required: log in again in the browser profile.

## Reopen Diagnostics

Reopen diagnostics now describe only the current Validate attempt:

- `Auto-reopen attempted` appears only when this attempt tried to reopen the saved profile.
- `Runtime reattached` appears only under that current-attempt auto-reopen block.
- `Validation continued after reopen` appears only under that current-attempt auto-reopen block.
- If the browser runtime is already active and validation reaches a captcha/challenge, stale reopen failure fields from older attempts are not shown as current state.

## Security Notes

Diagnostics must not display raw cookies, credentials, auth tokens, or private session payloads.
