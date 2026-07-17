# Douyin Legacy Isolation User Guide

## What changed

The main Douyin workflow is now defined as browser-profile-first and browser-profile-only by default. Manual session import and detached HTTP fallback remain legacy/debug capabilities, but they are not the normal operator path.

## Normal operator workflow

Use this flow for normal Douyin Intake work:

1. Open the Douyin Accounts page.
2. Start browser connect for the account.
3. Log in inside the opened persistent browser profile.
4. Solve any Douyin challenge in that same browser profile.
5. Validate the account.
6. If validation reports a challenge, solve it in the browser profile and recheck.
7. Open Intake.
8. Run Ready Check.
9. If Ready Check is successful, run Intake.

## Expected healthy state

A healthy default account has:

- A saved persistent browser profile.
- A browser context that can be reopened or is already active.
- Validation evidence from the browser profile.
- Intake readiness through the browser profile.

## If Ready Check is not ready

Follow the browser-profile action shown by the UI:

- Reopen the browser profile if it is closed or stale.
- Validate the account if browser validation is stale.
- Solve a challenge in the browser profile when prompted.
- Recheck after solving a challenge.
- Reconnect the browser profile if the saved profile cannot be reused.

The default workflow should not ask you to switch to detached HTTP fallback.

## Legacy manual import

Manual import is retained for legacy/debug use only. It is not the recommended default way to connect a Douyin account.

Manual import may be re-enabled by configuration only when explicitly needed for debugging old session material or migration investigation.

Default setting:

```env
DOUYIN_ENABLE_LEGACY_MANUAL_IMPORT=false
```

## Legacy detached HTTP fallback

Detached HTTP fallback is retained for legacy/debug use only. It is weaker than browser-profile evidence because it uses detached session material instead of the persistent browser profile that Douyin actually sees.

Default setting:

```env
DOUYIN_ENABLE_LEGACY_HTTP_FALLBACK=false
```

When disabled, browser validation/fetch failures should remain browser-specific failures. The system should not silently run detached HTTP fallback.

## Legacy debug UI surfaces

Legacy debug surfaces are hidden by default so the main operator UI stays focused on the reliable browser-profile workflow.

Default setting:

```env
DOUYIN_ENABLE_LEGACY_DEBUG_SURFACES=false
```

When enabled intentionally, debug surfaces may show manual import controls and detached HTTP fallback diagnostics. These should be treated as legacy diagnostics, not the normal production workflow.

## Troubleshooting

### The account says browser profile is required

Open browser connect for the account and complete login in the persistent browser profile.

### The account says challenge is blocked

Open or reuse the browser profile, solve the challenge manually, then run the challenge recheck action.

### Intake is blocked after reopening

Run validation again. If validation still cannot use the profile, reconnect the browser profile rather than using detached HTTP fallback.

### I need legacy fallback for debugging

Set the explicit legacy/debug flags in the API/web environment only for a debug session. Do not put secrets, cookies, or private paths in committed files.

## Safety notes

- Never paste real cookies, credentials, tokens, or private account secrets into docs, issue comments, or logs.
- Treat manual import and detached HTTP fallback as legacy/debug paths.
- The browser profile is the source of truth for normal Douyin account readiness.
