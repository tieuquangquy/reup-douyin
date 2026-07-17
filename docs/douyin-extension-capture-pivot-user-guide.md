# Douyin Extension Capture Pivot User Guide

## What Changed

Douyin collection now uses your real Chrome or Edge browser session as the primary path. Instead of asking the app to open and manage a Playwright browser profile, you browse Douyin normally, solve login or challenge prompts yourself, and use the browser extension to capture the current visible tab.

This is intended to be more reliable because it uses the browser session that already works for you.

## Primary Workflow

1. Install the Douyin capture extension.
2. Open Douyin in Chrome or Edge.
3. Login if needed.
4. Solve any challenge manually if Douyin shows one.
5. Open the target profile, profile feed, home feed, or video page.
6. Click Detect current page.
7. Confirm the extension recognizes the page type.
8. Click Capture current page.
9. Wait for the backend import summary.
10. Review imported candidates in the normal review workflow.

## Recommended Capture Pages

Best pages to capture:

- A Douyin profile page with visible videos.
- A profile feed after scrolling to load the videos you want.
- A video detail page when you want to capture a specific visible video.

Less useful pages:

- Login page.
- Challenge/captcha page.
- Empty feed page.
- Unsupported non-Douyin pages.

## Login and Challenges

If the extension reports a login page or challenge page:

1. Stay in your browser.
2. Complete the login or challenge manually.
3. Navigate back to the target profile/feed/video page if needed.
4. Click Detect current page again.
5. Capture only after the target content is visible.

The app does not need your cookies or password. Do not paste cookies or credentials into the extension or web app.

## Scrolling and Iterative Capture

Douyin often loads more videos as you scroll.

Recommended approach:

1. Open the profile/feed.
2. Scroll until the videos you want are visible.
3. Click Capture current page.
4. Scroll further.
5. Capture again.

Repeated captures are expected. The backend reuses canonical source/video records, updates known videos, records fresh metric snapshots, and runs the normal candidate filter.

## What Gets Sent

The extension sends safe page data such as:

- Current page URL.
- Current page title.
- Detected page type.
- Visible profile hints.
- Visible video links.
- Visible captions/titles.
- Visible metrics when available.
- Small diagnostics like extension version and extracted item count.

## What Is Not Sent

The extension must not send:

- Cookies.
- Passwords.
- Login tokens.
- Authorization headers.
- Browser profile paths.
- Full raw page HTML.
- Private local file paths.

## Backend Import Result

After capture, the backend should report a summary such as:

- Imported profile id.
- Crawl session id.
- Number of videos discovered.
- Number of videos created.
- Number of videos updated.
- Number of candidates matched.
- Any warnings, such as zero visible videos or unsupported page type.

## Legacy Managed Browser Path

Older Playwright-managed browser features may still appear in legacy/debug areas. They are no longer the primary Douyin collection path.

Use the extension flow first unless you are explicitly debugging the old managed runtime.

## Troubleshooting

### The extension says login page

Login manually in the browser, then run Detect again.

### The extension says challenge page

Solve the challenge manually. Do not capture until Douyin content is visible.

### The extension detects unsupported page

Open a Douyin profile, feed, or video page and run Detect again.

### Capture imports zero videos

Try scrolling to load visible video cards, then capture again.

### The backend is unreachable

Ensure the local API server is running and the extension backend URL points to the local API base URL used by this repository.

### Duplicate captures

Duplicate captures are safe. Existing source videos are updated, and new metric snapshots are recorded for the capture session.
