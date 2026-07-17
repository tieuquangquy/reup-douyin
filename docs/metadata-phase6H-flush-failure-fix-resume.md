# Phase 6H Flush Failure Fix Resume

## Summary

This fix hardens only the Full Modal Harvest flush boundary.

## Before

- extraction worked
- pending state worked
- flush could fail with `Failed to fetch`
- popup still showed a green flush success message

## After

- flush uses the extension runtime backend transport instead of direct content-script fetch
- progress stores:
  - `flush_url`
  - `flush_status_code`
  - `flush_error_message`
  - `pending_count_before_flush`
  - `pending_count_after_flush`
  - `backend_response_summary`
- popup shows success only when flush actually succeeds

## Verification

- extension tests cover failed fetch and successful flush state transitions
- backend route registration and modal ingest tests still pass
