# Phase 21A — Product scope lock + rename resume

## Phase objective

Phase 21A locks the product definition for the Douyin extension as a **Douyin Profile Scanner / Collector** and standardizes user-facing wording around the existing Capture Inbox review flow.

## Final route decision

The review UI remains the existing route:

- [`/extensions/douyin/capture-inbox`](docs/metadata-phase21A-product-scope-rename-resume.md:1)

This route is the review board for collected videos.

No new review route should be introduced.

Explicit non-goals for this phase:

- no [`/extensions/douyin/review`](docs/metadata-phase21A-product-scope-rename-resume.md:1)
- no [`/extensions/douyin/review-board`](docs/metadata-phase21A-product-scope-rename-resume.md:1)
- no new backend review route alias

## Popup role summary

The popup is the operator controller, not the review destination.

The popup should guide the operator through:

- Scan Profile
- Start Collecting
- Pause
- Resume
- Open Capture Inbox
- Reset

The popup should avoid presenting legacy technical terms as primary product wording.

## Capture Inbox role summary

Capture Inbox is the review workspace where collected videos are displayed and reviewed after collection.

Recommended CTA wording:

- Open Capture Inbox
- Open Review Inbox

But the target route decision stays:

- [`/extensions/douyin/capture-inbox`](docs/metadata-phase21A-product-scope-rename-resume.md:1)

## Collected field scope

The product is oriented around these fields:

- `aweme_id`
- `profile_url`
- `video_url` or `source_url`
- `thumbnail_url`
- `caption` or `title`
- `posted_text`
- `posted_at`
- `view_count`
- `duration_seconds`
- `duration_text`
- `like_count`
- `comment_count`
- `favorite_count`
- `share_count`
- `metadata_status`
- `review_status`
- `last_scanned_at`
- `error_code`
- `error_message`

Missing values must remain null when reliable evidence is unavailable.

## Status model summary

### Conceptual classification

- `new`
- `incomplete`
- `complete`
- `failed`
- `skipped`
- `unknown`

### User-facing wording

- New
- Incomplete
- Already collected
- Need retry
- Skipped
- Unknown

## Wording map locked in this phase

- Harvest → Collect
- Run Harvest → Start Collecting
- Flush → Save
- Flush Batch → Save to Capture Inbox
- Payload → Save data
- Payload Guard → Data check
- Capture Session → Scan session
- Backend → Capture Inbox
- Review Board → Capture Inbox
- Complete → Already collected
- Failed → Need retry
- Captcha → Security check

## Safe implementation boundary used in Phase 21A

This phase only changes user-facing wording, docs, CTA labels, and safe UI text where breakage risk is low.

Internal code may still keep technical identifiers such as:

- `harvest`
- `capture_session`
- `payload`
- `flush`
- `full_modal_harvest`

These are intentionally preserved where renaming would risk functional regressions.

## Intentionally not changed

- scanner internals
- backend data model
- API contracts
- DB schema
- classification endpoint
- runtime orchestration behavior
- review UI information architecture
- legacy/debug implementation internals except for safe surface wording

## Next phase

Next phase should implement backend data model alignment and classification endpoint work while keeping the existing Capture Inbox route and Phase 21A terminology stable.