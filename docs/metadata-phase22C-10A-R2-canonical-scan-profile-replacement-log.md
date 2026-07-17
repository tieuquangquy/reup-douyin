# Phase 22C-10A-R2 Canonical Scan Profile Replacement Log

## Summary

Active Scan Profile now uses a single canonical background-owned route:

Popup Scan Profile -> background `runCanonicalScanProfile22C10A` -> resolve Douyin tab -> ping content script -> self-test `DOUYIN_SCAN_PROFILE_CANONICAL_22C10A_PING` -> send `DOUYIN_SCAN_PROFILE_CANONICAL_22C10A` -> content script calls `collectProfileCardsUntilStable(...)` through the existing `runModalTestProfileScan` wrapper -> background adapts verified targets into the profile queue.

## Deletion Audit

| Area | Current purpose | References | Action | Reason |
| --- | --- | --- | --- | --- |
| `background.ts` `runScanProfileWorkflow(...)` active start route | Old controller orchestration | Scan Profile start message | Bypassed from active route | It still supports older tests/helpers, but no longer handles popup Scan Profile. |
| `background.ts` post-probe handoff helpers | 22C-9Z recovery path | Not used by canonical route | Kept unreachable | Broad deletion risk due existing tests and helper exports. |
| `background.ts` direct legacy 22C-9Z-10 helper | Broken direct scan bypass | Only old runtime helper/tests | Kept unreachable | Removed from active route; safe later deletion candidate. |
| `contentScript.ts` direct legacy 22C-9Z direct handler | Old direct scanner message | Content script only | Removed from supported active handlers | Canonical messages replace it. |
| `contentScript.ts` `collectProfileCardsUntilStable(...)` wrapper | Existing verified scanner | Canonical handler | Kept | Required scanner engine, unchanged. |
| `state.ts` 22C-9C validator | Legacy state repair | Normalization | Kept | Shared state migration path; not active in canonical success path. |

## Canonical Handler

The content script now exposes:

- `DOUYIN_SCAN_PROFILE_CANONICAL_22C10A_PING`
- `DOUYIN_SCAN_PROFILE_CANONICAL_22C10A`

The ping proves the handler and scanner function are available before scan dispatch.

## Queue Adapter

Verified targets are adapted with `canonical_verified_target_queue_adapter_22C10A`.
Queue entries use:

- `status = pending`
- `capture_status = new`
- `discovery_source = canonical_profile_scanner_22C10A`

Success diagnostics include `profileScanReady = yes`, `profile_queue_total_count`, `profile_batch_limit = 10`, and `profile_batch_pending_count`.

## Tests Run

- `npx tsx apps/extension-douyin-capture/src/background.test.ts`
- `npx tsx apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`

