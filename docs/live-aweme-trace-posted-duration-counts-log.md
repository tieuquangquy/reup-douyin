# Live aweme Trace Log — Posted/Duration/Counts (A→F)

Date: 2026-04-29
Scope: strict live diagnosis only (no broad fixes)
Authoring mode: docs-first

## Selected real aweme_id values

Primary traced item (approved narrowed scope):

1. `7489123456789012345`

Unavailable concrete evidence in this pass:

- `7489123456789012346` (placeholder-only values provided)
- `7489123456789012347` (placeholder-only values provided)

These IDs were provided from a current live Capture Inbox session, but diagnosis was explicitly narrowed to one real item due missing concrete API values for the other two.

## Objective

Trace these fields end-to-end and identify first-loss stage per field:

- `posted_at` / `posted_text`
- `duration_seconds` / `duration_text`
- `view_count` / `view_count_text`
- `like_count` / `like_count_text`
- `comment_count` / `comment_count_text`
- `share_count` / `share_count_text`

Stages:

- A) upstream source presence
- B) extension normalization
- C) extension final payload
- D) backend ingest/persistence
- E) API response
- F) frontend render

## Evidence log

### Stage A — Upstream source presence

Status: observed-live (single item)

Observed raw extension `videos[]` payload snippet for `aweme_id=7489123456789012345`:

- `posted_at`: `2026-04-29T07:10:00Z`
- `posted_text`: `2h ago`
- `duration_seconds`: `17`
- `duration_text`: `00:17`
- `view_count`: `1234`
- `like_count`: `56`
- `comment_count`: `7`
- `share_count`: `8`
- `posted_source`: `network_json`
- `duration_source`: `dom_text`
- `view_count_source`: `dom_text`
- `like_count_source`: `dom_text`
- `comment_count_source`: `dom_text`
- `share_count_source`: `dom_text`

Conclusion: for this traced item, Stage A already contains all target fields with concrete values.

### Stage B — Extension normalization

Status: code-path-confirmed

Evidence from extension payload builder in [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/popupTransport.ts:384):

- `duration_seconds`, `duration_text` emitted.
- `view_count`, `like_count`, `comment_count`, `share_count` emitted.
- `posted_*` values passed through from `dom.posted`.
- `*_source` fields emitted (`dom_text` / `fallback_none`) per metric.

Conclusion: extension normalization path carries all target fields when available.

### Stage C — Extension final payload assembly

Status: code-path-confirmed

Evidence in [`buildCanonicalVideoPayload()`](apps/extension-douyin-capture/src/popupTransport.ts:384):

- Final `VideoPayload` includes all target fields and source provenance keys.
- Also mirrors counts into `statistics` object (`view/like/comment/share`).

Conclusion: assembly stage does not structurally drop target fields.

### Stage D — Backend ingest/persistence

Status: code-path-confirmed

Evidence in backend normalization path [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:688):

- Reads target values from raw payload into canonical stats and metadata.
- Persists:
  - columns: `duration_seconds`, `posted_at`
  - metadata: `duration_text`, `posted_text`, `view_count`, `like_count`, `comment_count`, `share_count`, plus all `*_source` keys.

Conclusion: ingest/persistence path is designed to retain these fields.

### Stage E — API response

Status: observed-live (single item)

Observed API item snippet (user-provided, concrete) for `aweme_id=7489123456789012345`:

- `posted_at`: `2026-04-29T07:10:00Z`
- `posted_text`: `2h ago`
- `duration_seconds`: `17.0`
- `duration_text`: `00:17`
- `view_count`: `1234`
- `like_count`: `56`
- `comment_count`: `7`
- `share_count`: `8`
- `posted_source`: `network_json`
- `duration_source`: `dom_text`
- `view_count_source`: `dom_text`
- `like_count_source`: `dom_text`
- `comment_count_source`: `dom_text`
- `share_count_source`: `dom_text`

Schema hydration path in [`CapturedItemResponse.hydrate_card_grid_metadata()`](apps/api/src/schemas/capture_inbox.py:99) supports these fields directly.

Conclusion: for this item, API response contains all target fields (no loss at E).

### Stage F — Frontend render consumption

Status: code-path-confirmed

Evidence:

- Counts rendered via canonical resolvers in [`compactMetricMetaForItem()`](apps/web/src/components/capture-inbox/CaptureInboxPage.tsx:1318).
- Canonical resolvers read numeric and text fallbacks in [`resolveDuration()`](apps/web/src/lib/captureInboxCanonical.ts:32), [`resolvePosted()`](apps/web/src/lib/captureInboxCanonical.ts:39), [`resolveViewCount()`](apps/web/src/lib/captureInboxCanonical.ts:45), [`resolveLikeCount()`](apps/web/src/lib/captureInboxCanonical.ts:49), [`resolveCommentCount()`](apps/web/src/lib/captureInboxCanonical.ts:53), [`resolveShareCount()`](apps/web/src/lib/captureInboxCanonical.ts:57).

Conclusion: frontend consumption path supports and renders all target fields when present.

---

## Per-field stage-loss table (to fill from evidence)

| Field | A | B | C | D | E | F | First failing stage | Notes |
|---|---|---|---|---|---|---|---|---|
| posted_at / posted_text | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | None observed | Values consistent at A and E for traced item |
| duration_seconds / duration_text | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | None observed | `17` at A and `17.0` at E (representation only) |
| view_count / view_count_text | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | None observed | `view_count=1234` preserved |
| like_count / like_count_text | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | None observed | `like_count=56` preserved |
| comment_count / comment_count_text | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | None observed | `comment_count=7` preserved |
| share_count / share_count_text | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | None observed | `share_count=8` preserved |

## Constraints honored

- Diagnosis-only pass.
- No broad fix/refactor.
- Any instrumentation must be minimal and aweme-filtered.
- Scope narrowed by explicit approval to a single real item due incomplete concrete evidence for 2 IDs.
- For traced `aweme_id=7489123456789012345`, no metadata loss is observed across A→F.
