# Phase 21A — Product scope lock + concept rename log

## Goal

Lock the Douyin extension product definition as a **Douyin Profile Scanner / Collector** and standardize the user-facing terminology around scanning, collecting, saving, and reviewing.

## Product scope locked in this phase

The extension is not a generic debug harvest tool.

The extension product is:

- Douyin Profile Scanner
- Douyin Profile Collector
- popup-driven scan and collect controller
- backend review flow using the existing [`/extensions/douyin/capture-inbox`](docs/metadata-phase21A-product-scope-rename-log.md:1) product route decision documented in this phase

## Main workflow

1. User opens a Douyin profile URL.
2. Extension scans the profile and finds videos.
3. Extension classifies videos against the database.
4. Extension collects only:
   - new videos
   - incomplete videos
   - previously failed videos
5. Extension saves collected video metadata to the database.
6. User opens [`/extensions/douyin/capture-inbox`](docs/metadata-phase21A-product-scope-rename-log.md:1) to review collected videos.

## Popup role

The extension popup is only the controller.

Primary popup actions should communicate:

- Scan Profile
- Start Collecting
- Pause
- Resume
- Open Capture Inbox
- Reset

The popup should avoid presenting debug or legacy technical language as the main product surface.

## Capture Inbox role

The review UI remains the existing Capture Inbox surface.

The review board for collected videos is the existing route:

- [`/extensions/douyin/capture-inbox`](docs/metadata-phase21A-product-scope-rename-log.md:1)

No new review route should be created in this phase.

## Route decision

User-facing review CTAs must point to:

- [`/extensions/douyin/capture-inbox`](docs/metadata-phase21A-product-scope-rename-log.md:1)

User-facing review CTA label must be:

- Open Capture Inbox

Fallback copy is acceptable when the extension cannot navigate directly:

- Open [`/extensions/douyin/capture-inbox`](docs/metadata-phase21A-product-scope-rename-log.md:1) to review collected videos.

## Collected video fields

The product terminology and future backend alignment should center on these fields.

### Required identity fields

- `aweme_id`
- `profile_url`
- `video_url` or `source_url`

### Profile/card evidence

- `thumbnail_url`
- `caption` or `title`
- `posted_text` if visible
- `posted_at` if parseable
- `view_count` if available from reliable evidence

### Detail metrics

- `duration_seconds`
- `duration_text`
- `like_count`
- `comment_count`
- `favorite_count`
- `share_count`

### Operational fields

- `metadata_status`
- `review_status`
- `last_scanned_at`
- `error_code`
- `error_message`

If a field is not available from reliable evidence, it should remain null.

## Status model standardized in docs

### Conceptual states

- `new` = video is not in database yet
- `incomplete` = video exists but is missing required detail metadata
- `complete` = video exists and has enough required metadata
- `failed` = video failed in a previous collect run and should be retryable
- `skipped` = video was intentionally skipped
- `unknown` = classification cannot be determined safely

### User-facing wording

- `new` → New
- `incomplete` → Incomplete
- `complete` → Already collected
- `failed` → Need retry
- `skipped` → Skipped
- `unknown` → Unknown

## User-facing wording map

This phase standardizes wording without aggressively renaming internal runtime identifiers.

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

## What was intentionally changed

- Updated popup product title and main product copy toward scanning and collecting
- Updated Capture Inbox CTA wording toward Open Capture Inbox
- Updated save-flow wording in the popup results area toward scan session, save data, and save-to-inbox language
- Added a small terminology helper in the extension view-model layer for repeated product wording
- Added this product scope documentation for future phases

## What was intentionally not changed

- No scanner rewrite
- No backend classification endpoint implementation
- No database schema changes
- No API contract changes
- No runner behavior redesign
- No removal of working legacy handlers
- No new review route
- No Capture Inbox UX redesign beyond wording-safe adjustments
- No aggressive internal identifier renaming where it could risk breakage

## Next phase

Next phase should focus on backend data model alignment plus classification endpoint work, while preserving the Phase 21A route decision and product terminology.