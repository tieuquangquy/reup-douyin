# Douyin Card Grid Metadata Fix Log

## Scope

This log tracks the hard-fix for visible Douyin profile-grid card capture metadata flowing from the browser extension into Capture Inbox.

Touched areas planned:

- `apps/extension-douyin-capture`: visible card DOM extraction and direct execute-script parity.
- `apps/api`: extension request schema, Capture Inbox normalization, metadata persistence, readiness semantics, and safe logs.
- `apps/web`: Capture Inbox canonical thumbnail, metadata chips, and readiness display.
- `docs`: implementation notes, architecture, resume, and operator guide.

Non-goals:

- No crawler implementation.
- No media download or video processing pipeline.
- No fake thumbnails, fake counts, or synthetic posted dates.
- No Capture Inbox redesign.
- No distributed enrichment or SaaS queue work.

## Audit findings before implementation

### Extension visible card extraction

Current extraction starts from visible video links, derives the closest card with `nearestCard`, extracts card text, then emits thumbnails and marker-based metrics. The thumbnail collector already checks `img.currentSrc`, `img.src`, raw `src`, `data-src`, `srcset`, `source[srcset]`, `video[poster]`, dataset keys, image-like attributes, inline background image, and computed background image.

Gaps found:

- `nearestCard` can stop at a shallow `div`, which may exclude the actual image/poster or overlay metadata in Douyin profile-grid cards.
- The content-script path and direct execute-script path duplicate extraction logic, so both must be kept aligned.
- The extension emits thumbnail aliases, but not `duration_text`, `posted_text`, top-level `view_count`, `like_count`, or `comment_count`.
- Metrics are only parsed when label markers such as likes/comments/views are near a number. Overlay-only or compact Douyin grid text can be missed.
- No extraction diagnostics identify whether duration, posted text, and each metric were observed per card.

### Backend schema and normalization

Current backend request schema accepts thumbnail aliases, `duration_seconds`, `duration`, `posted_at`, `create_time`, `statistics`, and `stats`.

Gaps found:

- It does not explicitly accept `duration_text`, `posted_text`, top-level `view_count`, `like_count`, `comment_count`, `preview_status`, or `media_status`.
- Capture Inbox normalization merges stats into raw payload only; it does not preserve canonical stats in `metadata_json` for API/UI consumers.
- `preview_url` is set to `thumbnail_url or source_url`, causing source video URLs to masquerade as preview assets.
- `preview_ready` can be true from `preview_url` or even `source_url` during retry checks, which is not truthful for a missing visual preview.
- `media_ready` is currently true when `source_url` exists, which means link captured rather than media asset ready.

### Frontend rendering

Current Capture Inbox rendering resolves thumbnails from canonical `thumbnail_url`, raw aliases, image-like preview URLs, metadata aliases, and nested image-like URLs. Metadata chips read numeric duration/date fields and stats from raw payload.

Gaps found:

- Duration and posted chips do not fall back to canonical text fields such as `duration_text` and `posted_text`.
- Stats chips depend on raw nested stats unless backend canonicalizes them.
- Media readiness displays `Ready` for `media_ready`, even though backend currently sets that from a source URL.
- Preview label treats `preview_url` as captured/pending even when it may be a source URL.

## Implementation checklist

- [x] Create docs first.
- [x] Improve card root selection and thumbnail candidate scoring.
- [x] Add duration, posted text/date, and stats extraction without fabricating values.
- [x] Add safe diagnostics/logging counts for metadata extraction success/failure.
- [x] Extend backend schema and normalization to preserve canonical metadata.
- [x] Make preview/media readiness truthful.
- [x] Update frontend chips to prefer canonical fields and honest statuses.
- [x] Add/update extension, backend, and frontend tests.
- [x] Run verification commands where local dependencies are available.

## Change log

### 2026-04-27

- Read repository rules and audited the end-to-end capture path before editing implementation code.
- Identified data loss and optimistic readiness stages.
- Created initial docs before implementation, per task requirement.
- Updated the extension payload contract and both DOM extraction paths to emit canonical card-grid thumbnail, duration, posted, metric, readiness, and diagnostic fields.
- Replaced shallow card-root selection with scored ancestor selection so poster and overlay metadata are less likely to be excluded.
- Added deterministic thumbnail candidate scoring across image, source, video poster, dataset, attribute, inline background, and computed background sources.
- Added visible-text duration, posted text, and metric extraction while preserving raw text when parsing is ambiguous.
- Extended backend extension schemas, Capture Inbox normalization, metadata persistence, API response hydration, and safe metadata logs.
- Corrected readiness semantics so source URLs no longer make preview or media assets ready by themselves.
- Updated Capture Inbox frontend types and metadata chip helpers to prefer canonical fields, use raw text fallbacks, and distinguish source-link capture from ready media.
- Updated extension, backend, and frontend tests for the canonical metadata path.
- Verification completed:
  - `npm --workspace @reup-douyin/extension-douyin-capture run test` passed.
  - `npx tsx apps/web/src/test/capture-inbox.test.ts` passed.
  - `npm --workspace @reup-douyin/web run typecheck` passed.
  - `python -m compileall apps/api/src/schemas/douyin_extension.py apps/api/src/schemas/capture_inbox.py apps/api/src/services/capture_inbox_service.py apps/api/src/services/douyin_extension_capture_service.py` passed.
  - `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py -q` could not run because this local Python environment does not have `pytest` installed.
