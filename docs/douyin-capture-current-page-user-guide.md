# Douyin Current-Page Capture User Guide

## What changed

Douyin intake is moving to an operator-assisted browser workflow. Instead of asking the system to validate/fetch Douyin in the background first, you use the managed browser profile directly:

1. Open the managed Douyin browser profile.
2. Log in manually if needed.
3. Solve any challenge manually if needed.
4. Navigate to the target Douyin page yourself.
5. Click detect current page.
6. Click capture current page/profile.
7. Review imported candidates on the review board.

This keeps challenge-sensitive actions visible and under operator control.

## Supported page types

The app classifies the current page as one of these states:

- `login_page` — log in before capture.
- `challenge_page` — solve the challenge in the browser before capture.
- `home_feed_page` — visible feed page; capture may be limited and profile pages are preferred.
- `profile_page` — supported capture target.
- `profile_feed_page` — supported capture target.
- `video_detail_page` — supported only when profile/author identity can be resolved.
- `unsupported_page` — navigate to a Douyin profile/feed/video page.
- `unknown_page` — navigate to a clearer supported page and detect again.

## Recommended workflow

### 1. Open the managed browser profile

From Douyin Accounts:

1. Choose the account you want to use.
2. Click Open/Reopen browser profile.
3. Wait for the managed browser to open.

Do not use a separate normal browser window for the workflow. The app captures only from the managed browser profile linked to the selected account.

### 2. Log in or solve challenges manually

If Douyin shows login or verification:

1. Complete the login/challenge in the managed browser.
2. Stay in the same browser window.
3. Navigate manually to the target creator/profile/feed/video page.

The app should not try to drive these challenge-sensitive steps automatically.

### 3. Navigate to the target page

Preferred target pages:

- creator profile page;
- profile video/feed tab;
- video detail page when author/profile context is visible.

If you want more visible videos, scroll or load more manually in the managed browser before capture.

### 4. Detect current page

Click Detect current page.

Expected outcomes:

- Supported profile/feed page: capture is enabled.
- Login page: log in, then detect again.
- Challenge page: solve challenge, then detect again.
- Unsupported/unknown page: navigate to a supported page, then detect again.

### 5. Capture current page/profile

Click Capture current page/profile.

The app imports currently visible/parseable data into the existing intake pipeline:

- source profile is created or updated;
- source videos are created or updated;
- metric snapshots are recorded;
- candidates are evaluated with the selected filter settings;
- review board remains the next step.

### 6. Load more and capture again

To import more videos:

1. In the managed browser, manually scroll or click load more.
2. Click Detect current page again if the page changed.
3. Click Capture current page/profile again.

Repeated captures are safe. Existing profiles/videos are deduped and updated.

## Troubleshooting

### Browser runtime missing

Action: open or reopen the managed browser profile for the account.

### Login page detected

Action: log in manually in the managed browser, then navigate back to the target page and detect again.

### Challenge page detected

Action: solve the challenge manually in the managed browser. Do not reset the browser profile unless instructed by troubleshooting docs.

### Unsupported page detected

Action: open a Douyin creator profile, profile feed tab, or video detail page in the managed browser.

### Unknown page detected

Action: wait for the page to finish rendering or navigate to a clearer supported page. Then click detect again.

### Capture imports zero videos

Possible reasons:

- the current profile has no visible videos;
- the page has not finished loading;
- videos are hidden behind a tab or lazy-loaded area;
- the operator needs to scroll/load more manually;
- the parser cannot see enough structured data yet.

Action: load more manually and capture again. If zero videos persist on a visibly populated page, record the page type and diagnostics id from the UI.

## Safety notes

- Never paste real cookies or credentials into bug reports.
- Do not share screenshots containing private account details unless explicitly approved.
- Do not run capture from a personal unmanaged browser window; use the app-managed profile.
- Avoid opening unrelated sensitive websites in the managed browser profile.

## What stays unchanged

After capture, the rest of the workflow remains the same:

- imported source videos appear in intake/review data;
- candidates appear on the review board;
- downstream download, analysis, editing, rendering, and publishing flows are not changed by this refactor.
