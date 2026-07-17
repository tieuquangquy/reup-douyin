# Phase 22D-1 — Backend normalized Douyin metadata fields log

## Scope

Implemented backend response-only normalized Douyin metadata fields for Capture Inbox filters. This phase intentionally avoided extension crawler changes, frontend layout/filter redesigns, database migrations, and storage backfills.

## Current field audit

Capture Inbox item persistence already stores canonical fields on the item row plus raw and metadata JSON blobs. Relevant response mapping is centralized through `CapturedItemResponse.model_validate(item)`, including the Capture Inbox session detail, item list, query, and extension session item endpoints.

The safe Phase 22D-1 path is lazy response normalization because old items can be hydrated from existing canonical fields and JSON metadata without mutating stored raw captured values.

## Files changed

- `apps/api/src/services/douyin_metadata_normalization.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_douyin_metadata_normalization.py`
- `apps/api/tests/test_capture_inbox_metadata_status.py`

## Normalized field model

Added helper dataclasses for normalized duration, posted metadata, estimated views, engagement metrics, and data quality flags. Added response fields on `CapturedItemResponse` for Phase 22D-1 normalized fields while preserving existing legacy fields.

## Duration normalization

Duration normalization supports existing seconds, `mm:ss`, `hh:mm:ss`, zero duration, and invalid raw text preservation. It emits:

- `duration_text_raw`
- `duration_text`
- `duration_seconds`
- `duration_parse_confidence`

## Posted normalization

Posted normalization composes the existing lazy Douyin posted-date parser with Phase 22D response fields. It preserves raw posted text, uses display-ready `dd/mm/yyyy` output when available, preserves canonical `posted_at`, and carries known `posted_source` values.

## Estimated views normalization

Estimated views normalization supports compact ranges such as `9K–43K`, hyphen ranges such as `24K-118K`, compact single values such as `432K`, Chinese units such as `1.2万`, numeric legacy fallbacks, and missing/unparseable values.

It emits display/raw text plus min/max/mid integers and parse confidence.

## Engagement calculation

Engagement score is the sum of likes, comments, shares, and favorites when present. `engagement_rate` remains ratio-based for compatibility with existing backend semantics. The rate basis is `estimated_views_mid` when available, otherwise legacy `view_count`, otherwise `none`.

## Data quality flags

Response mapping now exposes booleans for thumbnail, posted, duration, views, likes, comments, shares, and all-core-metadata readiness. It also exposes `missing_metadata_fields` as a stable list of missing core fields.

## Lazy normalization behavior

No database mutation or backfill was added. `CapturedItemResponse` hydrates normalized fields from canonical row fields, `metadata_json`, and `raw_payload_json` at response time. Legacy raw/display fields remain available and are not overwritten in storage.

## Tests

Added focused helper tests and response-mapping regression tests for normalized duration, posted metadata, estimated views, metrics, engagement, data quality flags, serialization, and legacy lazy normalization.

## Validation run

Executed:

```cmd
python -m unittest tests.test_douyin_metadata_normalization tests.test_capture_inbox_metadata_status
```

Result: passed, 23 tests.

## Remaining risks

- Advanced filter request/service filtering has not been expanded to use these normalized fields; this phase only exposes backend normalized response fields for later filter work.
- Estimated views from exact legacy `view_count` are treated as a response fallback for old items.
- Parse confidence is conservative and does not infer missing metadata.
