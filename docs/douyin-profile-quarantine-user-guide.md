# Douyin Profile Quarantine User Guide

## What Quarantine Means

A quarantined Douyin browser profile is a saved managed browser profile that has produced too many repeated challenge or blocked-validation signals. The app keeps the profile available for reference, but stops treating it as a good candidate for normal Intake and capture.

Quarantine does not delete the profile or account connection.

## Why This Happens

Douyin can classify a browser profile or account as high risk. In that state, the browser may still look usable for casual manual viewing, but automation-assisted validation or capture may repeatedly hit:

- security verification pages;
- captcha pages;
- blocked browser-context responses;
- cooldown cycles;
- repeated post-challenge recheck failures.

When this repeats, continuing to retry the same profile can waste time and keep blocking the normal workflow.

## What You Should Do

When a profile is quarantined:

1. Stop using it as the preferred Intake/capture account.
2. Keep it only for reference or manual troubleshooting.
3. Create or connect a fresh cleaner Douyin browser-backed account/profile.
4. Validate the new profile through the app-managed browser flow.
5. Use the clean profile for Ready Check and Intake.

## What Still Works

For a quarantined profile, the app should still allow reference actions:

- open/reopen the saved managed browser profile;
- inspect the visible browser page manually;
- detect the current page for troubleshooting when the managed runtime is active.

## What Is Restricted

The app should not prefer quarantined profiles for normal operations:

- Ready Check should not report the quarantined profile as ready.
- Intake should not auto-select the quarantined profile.
- Account recommendation should prefer clean usable accounts.
- Capture current page should be blocked by default.
- Use in Intake should be disabled or clearly blocked.

## Clean Profile Recommendation

The recommended recovery path is not infinite retry on the same challenged profile. The preferred path is:

1. Go to Douyin accounts.
2. Start or connect a managed browser profile for a cleaner account.
3. Log in manually in the app-opened browser.
4. Let the app capture/validate the managed browser profile.
5. Make the clean account default or choose it explicitly in Intake.

## Safety Notes

- Do not paste or expose cookies, tokens, or credentials in notes/logs.
- Do not manually edit private browser-profile paths unless debugging locally.
- Do not delete a quarantined profile unless you are intentionally cleaning local storage and no longer need reference access.
- If a quarantined profile becomes healthy later, validate it through the app-managed browser path before considering it for normal work again.
