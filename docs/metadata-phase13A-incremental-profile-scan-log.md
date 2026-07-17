# Phase 13A Incremental Profile Scan Log

## Scope

Phase 13A implements incremental Douyin profile scan behavior for Smart Capture & Harvest. The extension captures the visible profile list, the API classifies each captured `aweme_id` against canonical storage, and Smart Capture & Harvest processes only the selected target queue.

## Dedupe Key

The canonical lookup key is:

```text
source_platform = "douyin"
source_video_external_id = aweme_id
```

This matches the `SourceVideo` unique constraint and avoids duplicate canonical videos on repeated profile captures.

## Classification

The API returns a scan summary with:

- `new`: no canonical `SourceVideo` exists for the dedupe key.
- `incomplete`: a canonical row exists, but required Douyin capture metadata is missing.
- `complete`: a canonical row exists and required metadata is present.
- `skipped`: duplicate or malformed IDs in the same capture response.

Required completeness fields are `source_video_external_id`, `duration_seconds`, `like_count`, `comment_count`, `favorite_count`, `share_count`, and either `posted_at` or `posted_text`. `view_count` is not required and estimated views do not affect completeness.

## Harvest Modes

- `new_only`: targets only `new_aweme_ids`.
- `new_and_incomplete`: default; targets `new_aweme_ids + incomplete_aweme_ids`.
- `refresh_all`: explicit operator mode; targets all captured unique `aweme_id`s.

## Implementation Notes

The API persists `incremental_scan_summary` on the capture session result summary and returns the summary directly to the extension. The extension stores the latest capture session, capture count, scan summary, harvest mode, and target queue in Smart Capture state.

Smart Capture no-ops when the selected target queue is empty and reports `No new or incomplete videos found.` instead of opening the modal harvester.