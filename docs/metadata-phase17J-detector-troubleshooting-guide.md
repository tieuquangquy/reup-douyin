# Phase 17J Detector Troubleshooting Guide

## Purpose

This guide covers popup diagnostics for Douyin detector/content-script failures after Phase 17J.

## Normal Ready State

The popup should show:

- Supported Douyin tab: `yes`
- Content script: `ready`
- Detector: `ready`
- Last reconnect: `not_needed` or `success`
- Last chrome error: `none`

In this state, detector-dependent actions may proceed, including Test Current Video, Modal Whole Profile Test, Smart Capture & Harvest, calibration, and harvest diagnostics.

## Reconnect Flow

Click `Reconnect Douyin Tab` when the popup reports missing/failed content script or detector unavailable. The button performs:

1. Ping active Douyin tab with `REUP_DOUYIN_PING`.
2. Inject `contentScript.js` if ping fails or reconnect is forced.
3. Wait briefly for the content script to initialize.
4. Ping again.
5. Run page-context detector.
6. Refresh popup operational state and clear stale detector errors if ready.

## Diagnostics Meaning

- Supported Douyin tab = `no`
  - The active tab URL is not a supported HTTPS Douyin host.
  - The extension will not inject content script.
- Content script = `missing`
  - Ping did not receive a ready pong.
  - Reconnect attempts injection only on supported Douyin tabs.
- Content script = `failed`
  - Injection or second ping failed.
  - Inspect Ping error / Injection error / Last chrome error.
- Detector = `failed`
  - The content script may be ready, but `REUP_DOUYIN_DETECT_PAGE_CONTEXT` failed or returned no page context.
- Last reconnect = `success`
  - Injection/reconnect succeeded and stale detector errors should clear.
- Last reconnect = `failed`
  - Popup could not restore the content-script bridge automatically.
- Manifest matched = `no`
  - The active tab was not eligible for content-script injection.

## Operator Recovery Steps

1. Open an HTTPS Douyin page on `https://www.douyin.com/*` or `https://douyin.com/*`.
2. Click `Reconnect Douyin Tab` in the popup.
3. If diagnostics become ready, rerun the original action.
4. If the popup says `Content script unavailable. Reload extension, then hard refresh Douyin tab.`:
   - reload the unpacked extension in `chrome://extensions`,
   - hard refresh the Douyin tab,
   - click `Reconnect Douyin Tab` again.

## Notes

The extension intentionally does not inject into non-Douyin pages, popup pages, or unsupported browser URLs. This avoids silently mutating stale/non-target tabs and keeps diagnostics precise.
