# Douyin Extension Rollback Guide

Release: `0.1.0`

## When to rollback

Rollback if any of the following release blockers appear during operator trial:

- Extension cannot be loaded unpacked.
- Popup cannot open or crashes consistently.
- Backend connection cannot be configured or reached with a known-good backend.
- Scanner starts running without explicit operator action.
- Safety checkpoint handling fails and scanning continues through captcha/login/security prompts.
- Package hygiene report fails.
- Capture Inbox save flow creates invalid or unsafe metadata.

## Rollback steps for Chrome or Edge

1. Open `chrome://extensions` or `edge://extensions`.
2. Locate `Reup Douyin Current Tab Capture`.
3. Disable the extension.
4. Select Remove if the installed release is unsafe to keep loaded.
5. Load the previous known-good unpacked extension package using Load unpacked.
6. Restart the browser tab containing Douyin.
7. Restart the local backend only if backend state or routes were also changed.
8. Open the previous known-good extension popup and confirm backend connectivity.

## Restore current trial package after rollback test

1. Re-run the package command if needed:

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run package
```

2. Load `apps/extension-douyin-capture/release/reup-douyin-extension-0.1.0` as unpacked.
3. Confirm the hygiene report passes before retrying operator trial.

## Data safety notes

- Removing the extension can remove extension-local state depending on browser behavior.
- Capture Inbox records already saved to the backend are not removed by extension rollback.
- Do not delete local backend storage unless a separate backend rollback procedure requires it.

## Rollback verification

After rollback, verify:

- Extension popup opens.
- Backend URL is correct.
- No scan starts automatically.
- Existing Capture Inbox data remains available.
- The operator can stop using the failed release package.
