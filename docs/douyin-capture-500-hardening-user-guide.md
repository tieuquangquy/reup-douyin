# Douyin Capture 500 Hardening User Guide

## What changed

The Douyin extension capture flow has been hardened so incomplete active-tab data does not fail as an opaque backend 500. Captures are staged in Capture Inbox first, and item-level problems are reported as warnings or failed/skipped items.

## Expected operator behavior

1. Open a supported Douyin profile, feed, or video page.
2. Open the extension popup.
3. Confirm connection is healthy.
4. Click capture current page.
5. Review the capture summary:
   - submitted items,
   - staged items,
   - ready items,
   - duplicates,
   - skipped items,
   - failed items,
   - diagnostics id.
6. Open Capture Inbox for any item-level warnings or failed/skipped rows.
7. Promote only ready items from Capture Inbox to canonical Review Board candidates.

## Partial-success examples

### Missing thumbnail

The item can still stage. It may show preview missing and remain inspectable in Capture Inbox.

### Missing video id but valid source URL

The backend derives a video id from the URL when possible. If derivation fails, the item is staged as needing enrichment or failed with an item-level reason.

### One malformed item among valid items

Valid items are staged. The malformed item is recorded with a failure summary. The request should return a structured response instead of generic 500.

## When a capture can still fail

Some failures happen before a Capture Session can be created:

- page is a login page,
- page is a challenge page,
- payload contains secret-like fields,
- profile URL cannot be resolved,
- backend/database is unavailable.

For normal domain failures, the popup and manager show backend code, stage, message, and diagnostics id where available. True infrastructure failures may still appear as system failures and should be investigated through backend logs.

## Backend diagnostics shown in the UI

Successful and partially successful captures now include:

- `stage`, such as `capture_session_staged` or `item_normalization_partial_failure`,
- `warning_codes`, such as `partial_item_failures` or `no_ready_items`,
- `failure_summaries` with item index, stage, code, and safe message,
- `submitted_count`, `staged_count`, `deduped_count`, `skipped_count`, and `failed_count`,
- `diagnostics_id` for log lookup.

## Where to inspect results

- Extension popup: immediate capture summary and diagnostics.
- Web manager: latest capture status and history.
- Capture Inbox: staged item details, raw payload details, readiness reasons, and manual actions.

## Review Board note

Captured items do not directly enter Review Board. Only promoted canonical `VideoCandidate` records appear there.
