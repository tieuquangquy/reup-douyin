# Douyin Extension Popup Hardening User Guide

## What Changed

The Douyin extension popup actions are being hardened so they no longer appear dead when something goes wrong. Each action should end with a success message, a friendly error, or a timeout message.

## Check Extension Connection

Use this action to verify the popup can reach the local backend.

Possible outcomes:

- Connected successfully.
- Backend timed out.
- Backend unreachable.
- Version mismatch or setup action reported by the backend.

If the backend times out or is unreachable:

1. Confirm the API is running.
2. Confirm the API base URL in the popup, usually `http://127.0.0.1:8000`.
3. Try Check extension connection again.

## Detect Current Page

Use this action on an active Douyin tab.

Possible visible failures:

- No active tab.
- Unsupported tab.
- Douyin login page.
- Douyin challenge page.
- Direct execution failure.

## Capture Current Page

Use this action after opening a supported Douyin profile, feed, or video page.

Possible visible failures:

- No active tab.
- Unsupported tab.
- Douyin login page.
- Douyin challenge page.
- Capture not supported on the current page.
- Backend timeout or capture failure.

## Diagnostics

The popup may show lightweight diagnostics such as backend reachability, active tab availability, supported tab status, last action, and last error category. These are intended to help operators identify whether the problem is browser state, backend reachability, or capture execution.
