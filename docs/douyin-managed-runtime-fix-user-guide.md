# Douyin Managed Runtime Fix User Guide

## What changed

Douyin browser-backed accounts use only browser windows opened and managed by the app. If you can see a Douyin browser window but the app says the live runtime is missing, that window was likely opened outside the app or belongs to a stale process. The app will not treat it as usable unless it owns the Playwright runtime.

## Correct operator flow

1. Go to Douyin Accounts.
2. Use `Open profile` for the target account.
3. Log in or complete Douyin verification in that app-opened window.
4. Run `Validate`.
5. If a challenge is detected, solve it in the app-opened browser window, then use `Mark challenge solved` or post-challenge recheck.
6. Run Intake only after Ready Check says the browser profile is ready.

## Recovery messages

### Managed runtime missing

Meaning: the app does not currently own a browser runtime for this saved profile.

Action: use `Open profile` from the app. Do not rely on a manually opened browser window.

### Profile opened outside managed runtime

Meaning: the saved profile appears to be open in another browser process, so the app cannot safely own it.

Action: close all external browser windows for that profile, then use `Open profile` in the app.

### Profile locked by existing process

Meaning: Chromium reported that the user data directory/profile is already in use.

Action: close the external browser/process using that profile. If needed, use Task Manager to close leftover Chrome/Chromium processes, then use `Open profile`.

### First page closed but context alive

Meaning: the app-managed browser context is still alive, but the first remembered page closed.

Action: retry the action. The app should reacquire or create a page in the same managed context.

### Managed runtime stale

Meaning: the app had a runtime record, but it no longer responds reliably.

Action: close/reopen the profile through the app, then validate again.

## Important notes

- A visible browser window is not enough; it must be the window opened through the app.
- Do not manually open the saved profile directory with Chrome while using the app.
- Do not run Intake from a browser profile that Ready Check reports as unmanaged, locked, missing, or stale.
- The app should never create a new account profile to work around a lock; it should reuse the canonical saved profile after the conflict is resolved.
