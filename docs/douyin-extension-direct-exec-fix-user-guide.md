# Douyin Extension Direct ExecuteScript Fix User Guide

## What Changed

Detect current page and Capture current page now run directly inside the active Douyin tab through browser script execution. They no longer require a preloaded content-script message listener in the normal primary flow.

The extension still uses the same backend handshake, detect, and capture endpoints. The change is limited to how the popup obtains the current-page DOM snapshot before sending safe data to the backend.

## Normal Operator Flow

1. Open a supported Douyin page in Chrome or Edge.
2. Open the Douyin Capture extension popup.
3. Confirm backend connection is healthy.
4. Click Detect current page or Capture current page.
5. The popup executes the detector/extractor directly in the active tab and sends the safe result to the backend.

## Supported Tabs

Use HTTPS Douyin pages under supported domains:

- `https://www.douyin.com/`
- `https://www.douyin.com/user/...`
- `https://www.douyin.com/video/...`
- supported `*.douyin.com` pages
- supported `*.iesdouyin.com` pages

## Friendly Error Messages

### No active tab is available. Open a supported Douyin tab and try again.

The browser did not provide an active tab with a usable URL.

### Open a supported Douyin page and refresh it, then try again.

The active tab is not an HTTPS Douyin tab supported by the extension.

### This Douyin page is not supported for capture. Open a profile, feed, or video page and try again.

The tab is on Douyin, but the page type is not usable for capture.

### This Douyin page is asking for login. Log in in the browser, refresh the page, and try again.

The active page appears to be a login page.

### Douyin is showing a challenge. Solve it in the browser, refresh the page, and try again.

The active page appears to be a CAPTCHA/security challenge.

### Could not execute the Douyin detector in this tab. Refresh the page and try again.

Chrome/Edge blocked direct execution or the page was not ready.

## Content Script Status

The bundled content script may still exist for compatibility or future auxiliary extension behavior, but the popup Detect current page and Capture current page buttons no longer depend on a content-script message listener.

## Verification Status

The extension direct execution refactor has passed typecheck, focused tests, and build verification.

## Privacy

The extension still does not export cookies, passwords, auth tokens, browser storage, raw HTML, or private local paths.
