# Douyin Capture Bootstrap Fix User Guide

## What changed

The Douyin current-page capture workflow requires an app-managed browser runtime. A saved browser profile on disk is not enough by itself.

Use Open profile or Reopen profile from the app to attach the saved persistent browser profile to the app-managed runtime. After that, Detect current page and Capture current page operate only on the visible page inside that managed browser.

## Correct operator workflow

1. In Douyin Accounts, choose the account with the saved browser profile.
2. Click Open profile or Reopen profile.
3. Wait for the browser window opened by the app.
4. In that browser window, manually log in if needed.
5. Complete any Douyin captcha/security challenge manually.
6. Navigate manually to the target Douyin profile page or profile feed page.
7. Click Detect current page.
8. If the page is supported and capture-ready, click Capture current page.
9. Review imported candidates in the existing review workflow.

## Runtime states

### Saved profile exists, no app-managed runtime

This means the account has browser profile metadata, but the app does not currently control a live Playwright context for it.

Action: click Open profile or Reopen profile.

### Managed runtime active

The app has a live runtime attached to the saved profile.

Action: navigate to the target Douyin page and click Detect current page.

### Reopen failed

The app could not restore the saved profile into a managed runtime.

Common causes:

- The same browser profile is already open outside the app.
- The browser process closed during startup.
- Playwright/Chrome runtime is unavailable.

Action: close external browser windows for that profile, then click Reopen profile again. Do not create a new profile for the account.

### Page reacquired or page created in the same context

The app recovered from a closed first page without changing browser profile. This is acceptable and should still count as the same managed runtime/profile.

## Page detection results

### Capture-ready pages

- Douyin profile page.
- Douyin profile feed page.

### Not capture-ready pages

- Login page: log in manually, then navigate to the profile page.
- Challenge page: solve the visible challenge manually, then click Mark challenge solved or Detect current page again.
- Home/feed page: navigate to a specific profile page.
- Video detail page: navigate to the creator profile page before capture.
- Unsupported or unknown page: navigate to a profile page.
- Runtime missing: click Open profile or Reopen profile first.

## Mark challenge solved

Use Mark challenge solved only after completing the visible challenge in the app-opened browser profile.

Expected behavior:

- The app uses the same saved browser profile.
- If the managed runtime is missing, the app attempts to reopen that same saved profile.
- The app records whether the same profile/runtime was reused or reopened.
- The action should not succeed based only on detached HTTP session material.

## Capture current page button

Capture current page should stay disabled until:

- The managed runtime is active.
- Detect current page has run successfully.
- The detected page type supports capture.
- A profile URL can be normalized from the current page.

If Capture is disabled, follow the Detect current page operator message.

## Troubleshooting

### first_page_closed_early: TargetClosedError

The browser page closed during bootstrap. The app should now attempt recovery in the same context/profile when possible. If the whole browser context closes, Reopen profile will report runtime missing/reopen failed.

### profile_opened_outside_managed_runtime

The saved profile is already open outside the app. Close that external browser/process and click Reopen profile from the app.

### managed runtime missing

The saved profile exists but there is no app-managed runtime. Click Open profile or Reopen profile.

### challenge still required after Mark challenge solved

Douyin still shows a challenge, or post-check could not prove the challenge is cleared. Complete the visible challenge in the same app-opened browser profile and retry Mark challenge solved.

## Important constraints

- Do not manually create a new browser profile for an existing account.
- Do not switch accounts/profiles while a browser connect session is active.
- Do not rely on detached HTTP cookies for current-page capture readiness.
- Keep all login, captcha, and navigation steps operator-controlled in the managed browser window.
