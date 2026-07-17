# Douyin Capture Inbox User Guide

## What The Capture Inbox Is

The Capture Inbox is the staging area for videos captured by the Douyin browser extension. It lets the operator verify what the extension saw before any item appears in the Review Board.

## Normal Operator Flow

1. Open a supported Douyin page in the browser.
2. Use the Douyin extension popup and choose capture current page.
3. The backend stores the capture as a Capture Session.
4. Open `/ops/extensions/douyin/capture-inbox`.
5. Review the session counts and item readiness.
6. Inspect items with missing or unknown fields.
7. Promote ready items to the canonical review pipeline.
8. Open the Review Board to review promoted candidates.

## What Counts Mean

- Visible items: video-like entries the extension saw in the current tab.
- Captured items: raw rows saved by the backend.
- Normalized items: rows with usable normalized identity/URL/profile fields.
- Duplicates: rows that repeat another captured item or already exist canonically.
- Ready items: rows that can be promoted.
- Skipped items: rows intentionally excluded by the operator.
- Promoted items: rows sent to the canonical pipeline.
- Candidate count: rows that became or updated Review Board candidates.

## Manual Actions

The Capture Inbox exposes actions for operational recovery:

- Retry enrich: re-run lightweight normalization and readiness checks.
- Retry preview: re-check thumbnail/cover/media preview readiness.
- Promote now: promote a ready item or session into the existing canonical pipeline.
- Exclude/skip: mark a raw item as intentionally ignored.
- Open source: open the source URL in the browser.
- View raw details: inspect raw safe payload fields for troubleshooting.

## Unknown Data

Unknown fields are shown as unknown. The system must not invent titles, thumbnails, statistics, or profile data just to make a row look complete.

## Review Board Boundary

The Review Board is only for promoted candidates. Captured raw rows do not appear there until promotion creates or updates canonical `SourceVideo` and `VideoCandidate` records.

## Safety

The extension and backend reject secret-like payload keys. Do not paste cookies, tokens, credentials, browser profile paths, or private local paths into manual backend test forms or raw diagnostics.
