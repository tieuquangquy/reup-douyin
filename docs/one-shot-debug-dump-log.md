# One-shot Debug Dump Log

Date: 2026-04-29
Scope: temporary diagnostics convenience for two failing aweme IDs only.

Target aweme IDs:
- `7489123456789012346`
- `7489123456789012347`

## Goal
After one real `Capture current page` action, emit one unified structured summary per target ID with:
- `checkpoint1` (pre-canonical)
- `checkpoint2` (canonical output)
- `checkpoint3` (backend `_build_item`)
- `first_missing_stage`
- `likely_next_fix_boundary`

Only fields:
- `posted_at`
- `posted_text`
- `duration_seconds`
- `duration_text`
- `view_count`
- `like_count`
- `comment_count`
- `share_count`

## Planned implementation
1. Keep existing checkpoint extraction in extension and backend.
2. Add temporary checkpoint payload embedding in extension for target IDs:
   - `_target_debug_checkpoint1`
   - `_target_debug_checkpoint2`
3. In backend `_build_item`, read those checkpoint payloads (stored as JSON strings in `raw`), compute checkpoint3, compute first-missing stage deterministically, and emit one compact summary log object.
4. Keep diagnostics scoped to target IDs only.

## Output contract (per aweme)
```json
{
  "aweme_id": "...",
  "checkpoint1": { "posted_at": null, "posted_text": null, "duration_seconds": null, "duration_text": null, "view_count": null, "like_count": null, "comment_count": null, "share_count": null },
  "checkpoint2": { "posted_at": null, "posted_text": null, "duration_seconds": null, "duration_text": null, "view_count": null, "like_count": null, "comment_count": null, "share_count": null },
  "checkpoint3": { "posted_at": null, "posted_text": null, "duration_seconds": null, "duration_text": null, "view_count": null, "like_count": null, "comment_count": null, "share_count": null },
  "first_missing_stage": "checkpoint1|checkpoint2|checkpoint3|none",
  "likely_next_fix_boundary": "..."
}
```
