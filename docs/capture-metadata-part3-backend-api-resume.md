# Capture Metadata Part 3 Backend/API Resume

Date: 2026-04-29
Status: Completed

## Scope lock

- Part 3 only: backend ingest + persistence + Capture Inbox API exposure.
- No extension normalization changes in this task.
- No frontend Tile Gallery/UI changes in this task.

## Audit summary

### Ingest

- [`DouyinExtensionVideoPayload`](apps/api/src/schemas/douyin_extension.py:123) accepts many canonical fields but misses Part 2 provenance + processing-fit semantic keys.
- `posted_source` literal in backend schema is narrower than extension output and should include `detail_hydrate` for contract alignment.

### Persistence

- [`CaptureInboxService._build_item(...)`](apps/api/src/services/capture_inbox_service.py:688) already persists canonical Time/Performance values.
- Current metadata pruning at [`capture_inbox_service.py:776`](apps/api/src/services/capture_inbox_service.py:776) drops `None`; this must be adjusted for explicit-null semantic keys.

### API exposure

- [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24) and [`hydrate_card_grid_metadata(...)`](apps/api/src/schemas/capture_inbox.py:89) currently expose time/perf basics but not Part 2 provenance fields nor processing-fit semantic fields first-class.

### Data model / migration

- [`CapturedItem`](apps/api/src/models/capture_inbox.py:56) already supports JSON-backed extensibility.
- Part 3 can ship without DB migration by using `metadata_json` + schema hydration.

## Implementation results

1. Ingest schema updated in [`DouyinExtensionVideoPayload`](apps/api/src/schemas/douyin_extension.py:123):
   - Added provenance keys: `duration_source`, `view_count_source`, `like_count_source`, `comment_count_source`, `share_count_source`, `engagement_rate_source`.
   - Added processing-fit semantic keys: `has_speech`, `text_density`, `has_heavy_watermark`, `processing_complexity`, `copyright_risk`.
   - Expanded `posted_source` compatibility to include `detail_hydrate`.

2. Persistence updated in [`_build_item(...)`](apps/api/src/services/capture_inbox_service.py:688):
   - Writes provenance keys and processing-fit semantic keys into `metadata_json`.
   - Keeps explicit null for processing-fit keys via explicit allowlist at [`capture_inbox_service.py:782`](apps/api/src/services/capture_inbox_service.py:782).

3. API exposure updated in [`CapturedItemResponse`](apps/api/src/schemas/capture_inbox.py:24) and [`hydrate_card_grid_metadata(...)`](apps/api/src/schemas/capture_inbox.py:89):
   - Exposes provenance fields first-class.
   - Exposes processing-fit semantic fields first-class.

4. Tests updated in [`test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py:59) and [`test_douyin_extension_capture_service.py`](apps/api/tests/test_douyin_extension_capture_service.py:403):
   - payload acceptance assertions for new ingest fields.
   - end-to-end `_build_item` + `CapturedItemResponse` exposure checks.
   - explicit-null retention assertions for processing-fit semantic fields.

## Verification evidence

- Backend test command executed from [`apps/api`](apps/api):
  - [`python -m unittest tests.test_douyin_extension_capture_service -v`](apps/api/tests/test_douyin_extension_capture_service.py)
- Result: 29 tests passed.

## Migration

- No DB migration required for Part 3 because persistence uses existing `metadata_json` plus already-existing top-level canonical columns (`duration_seconds`, `posted_at`).
