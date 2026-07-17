# Phase 18I-J3 Backend Flush Guided UX Log

## Scope

- App: `apps/extension-douyin-capture`
- Focus: popup-only backend flush guidance for Whole Profile Harvest
- Non-goals:
  - no backend ingest changes
  - no extraction/scanner/dry-run changes
  - no legacy runtime reuse

## What changed

The popup backend flush area now follows one guided four-step flow:

1. Prepare Session
2. Build Payload Preview
3. Flush One Item
4. Flush Batch

The UI now explains prerequisites, disabled reasons, compact guard status, and short success/failure summaries without dumping raw state into the main flow.

## Action gating rules

- Prepare Session:
  - enabled only when at least one extracted result exists and backend is reachable
- Build Payload Preview:
  - enabled only when a backend session exists and extracted data is available
- Flush One Item:
  - enabled only when session is ready, preview exists, and payload guard passes
- Flush Batch:
  - enabled only when session is ready, flushable extracted items exist, and one-item flush has already succeeded

This keeps batch writes behind a smaller proof step.

## Why Flush One Item comes before Flush Batch

One-item flush verifies that:

- the selected extracted row builds a valid backend payload
- the payload guard allows the commit
- the backend write succeeds for the current session

Only after that does the batch action become available.

## Payload guard display

Main UI shows compact guard information:

- guard status
- required fields summary
- disallowed fields summary
- evidence version
- commit policy
- selected aweme
- first three offending paths when guard fails

Full payload/guard details stay in Details.

## Capture Inbox CTA

After one-item success or completed batch flush, the popup shows a compact CTA message telling the operator to open Capture Inbox in the web app to review created items.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Next UX phase plan

- tighten wording around backend failure recovery
- add clearer distinction between one-item verification and batch continuation state
- optionally add direct Capture Inbox deep-link when route ownership is confirmed
