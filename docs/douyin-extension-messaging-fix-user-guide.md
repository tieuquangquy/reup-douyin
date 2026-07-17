# Douyin Extension Messaging Fix User Guide

## What Changed

Detect current page and Capture current page now validate the active tab and try one automatic content-script recovery before showing an error.

## Normal Operator Flow

1. Open a supported Douyin page in Chrome or Edge.
2. If the extension was just installed or reloaded, refresh the Douyin page once.
3. Open the Douyin Capture extension popup.
4. Confirm backend connection is healthy.
5. Click Detect current page or Capture current page.
6. If the tab has not loaded the content script yet, the popup will try one automatic recovery injection and retry the action.

## Supported Pages

Use a Douyin page under supported domains such as:

- `https://www.douyin.com/`
- `https://www.douyin.com/user/...`
- `https://www.douyin.com/video/...`
- supported `*.douyin.com` pages
- supported `*.iesdouyin.com` pages

## Recovery Strategy

The popup uses one shared transport helper for both Detect current page and Capture current page:

1. Find the active tab.
2. Validate that it has a URL and is a supported Douyin HTTPS URL.
3. Send the content-script message.
4. If Chrome reports that the receiving end does not exist, inject `contentScript.js` once.
5. Retry the original message once.
6. If the retry still fails, show a friendly refresh-required message instead of the raw Chrome error.

## Friendly Error Messages

### No active tab is available

Open a supported Douyin tab and try again.

### Open a supported Douyin page and refresh it, then try again.

The active tab is not a supported Douyin tab.

### This tab has not loaded the Douyin capture script yet. Refresh the Douyin page and try again.

The extension could not reach the content script even after one recovery attempt.

### Could not load the Douyin capture script into this tab. Refresh the Douyin page and try again.

The one-time recovery injection failed.

### Capture is not supported on this Douyin page. Open a profile, feed, or video page and try again.

The extension reached the page, but the current page type is not capturable.

## Browser Limitation

Chrome and Edge can only message a content script that is loaded in the active tab. If the extension was installed or reloaded after the tab was already open, the page may need a refresh. The popup now attempts one automatic injection recovery, but some browser pages still require a manual refresh.
