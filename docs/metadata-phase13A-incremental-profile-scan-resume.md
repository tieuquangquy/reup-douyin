# Phase 13A Incremental Profile Scan Resume Notes

## Current Behavior

Smart Capture & Harvest now resumes from the persisted `target_aweme_ids` queue instead of the full profile capture count. This keeps repeated profile scans focused on new or incomplete Douyin videos unless the operator explicitly chooses `refresh_all`.

## Stored State

The extension Smart Capture state stores:

- latest capture session id
- latest capture id
- captured item count
- `harvest_mode`
- `scan_summary`
- `target_aweme_ids`
- `target_count`
- per-target status map from modal harvest progress

## Resume Semantics

Resume uses `target_aweme_ids` and the modal harvest target status map. Completed, skipped, and failed target states are retained by the modal harvest controller so the workflow can continue through the same target queue after interruption.

## No-op Resume State

If a capture returns an empty target queue for the selected mode, Smart Capture stores `completed_noop`. This is a terminal successful state for that scan and does not start modal harvest.

## SaaS-ready Boundary

The API owns classification against canonical storage. The extension owns operator mode selection, target queue persistence, and modal harvest control. The browser does not infer database completeness and the API does not perform long-running modal harvest work inline.