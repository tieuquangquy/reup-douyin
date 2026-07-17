# Phase 17AD Operator Guide — Diagnose no-item after V2 harvest

## Goal
Quickly determine why a created V2 capture session shows no items in Capture Inbox.

## Step 1 — Check extension run outcome
- In popup V2 trace, verify each target flush result.
- If target fails with `capture_inbox_item_not_created`, inspect backend fields:
  - `code`
  - `stage`
  - `reason`

## Step 2 — Query backend session items endpoint
Use:
- `GET /douyin-extension/capture-sessions/{capture_session_id}/items`

Expected:
- `items_count`
- `items[]`
- `counts { captured, ready, dup, fail }`

If `items_count=0` and extension showed `capture_inbox_item_not_created`, issue is ingest path (B).

## Step 3 — Query backend debug endpoint
Use:
- `GET /douyin-extension/capture-sessions/{capture_session_id}/debug`

Review:
- `last_ingest_events[]`
- latest event `status`, `item_created_or_updated`, `capture_inbox_item_id`, `error_code`

## Step 4 — Confirm UI diagnostics
In Capture Inbox session view:
- `Loaded items`
- `Hidden by filters`
- Empty-state includes session existence and endpoint source.

Interpretation:
- Loaded > 0, Hidden > 0: filter-driven visibility (D).
- Loaded = 0 with backend items_count = 0: no ingested items (B/A depending trace).
- Backend items_count > 0 but UI loaded 0: UI fetch/wiring issue (C/D).

## Escalation checklist
- Capture session id
- failing aweme_id
- latest `last_ingest_events` entry
- extension trace event around `flush_failed`
- API response payload from session items endpoint
