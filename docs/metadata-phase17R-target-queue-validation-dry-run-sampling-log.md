# Phase 17R Target Queue Validation And Dry-run Sampling Log

## Scope

Phase 17R is limited to `apps/extension-douyin-capture` and related docs/tests. It cleans the Modal Whole Profile Test target queue before any production harvest integration.

## Issue Found

The previous scanner could accept long numeric values when they appeared near broad aweme/modal/video/item strings in scoped attributes or card HTML. A value such as `202605050200442800701` can look like a generated date/timestamp value, not a Douyin video aweme id, but length-only validation was not enough to reject it.

## Implementation

- Added typed candidate classifications with accepted/rejected status, source, reason, URL evidence, and card-context flag.
- Added `validateDouyinAwemeCandidate()` to reject invalid length, likely timestamp values, unscoped body regex candidates, excluded footer/legal contexts, and values without video/card/link context.
- Updated profile card extraction to accept only validated targets from video links, modal links, data attributes inside video-like cards, and scoped card-context regex.
- Added diagnostics for raw candidate count, accepted count, rejected count, rejected examples, and source counts.
- Ensured harvest-plan targets are filtered back to accepted scanner targets before becoming `target_count`.
- Added dry-run sampling modes: first N, last N, stable random N, and specific aweme IDs.
- Kept dry-run state isolated to `douyinModalWholeProfileTestRun` and did not call production full-modal-harvest.

## Non-goals

- No backend broad changes.
- No Tile Gallery writes.
- No Capture Inbox writes.
- No modal metrics extraction changes.
- No calibration workflow changes.
- No CDP/debug workflow reintroduction.
- No production Smart Capture merge.
