# Metadata Phase 3 Backend Normalizer Log

## Scope

Phase 3 only: backend canonical metadata normalizer for Capture Inbox using Phase 2 raw evidence.

In-scope:
- `apps/api` normalization logic and wiring.
- API/schema exposure updates needed for normalized metadata/status/source/reason fields.
- Focused backend tests and docs.

Out-of-scope:
- Extension evidence collection changes.
- Frontend redesign.
- Hydration job / queue / review flow.

## Audit Findings (Before Implementation)

### 1) Phase 2 raw evidence acceptance
- Accepted in [`class DouyinExtensionVideoPayload`](../apps/api/src/schemas/douyin_extension.py:137) with:
  - `raw_network_aweme`
  - `raw_detail_aweme`
  - `raw_dom_snapshot`
  - `raw_evidence_summary`

### 2) Phase 2 raw evidence persistence
- Persisted in [`CaptureInboxService._build_item()`](../apps/api/src/services/capture_inbox_service.py:703) into `metadata_json`:
  - `raw_network_aweme`
  - `raw_detail_aweme`
  - `raw_dom_snapshot`
  - `raw_evidence_summary`

### 3) Existing canonical metadata behavior and gaps
- Current canonical fields (`posted_at`, `duration_seconds`, counts, `engagement_rate`) are mostly sourced from top-level payload fields and loose `statistics` merge in [`CaptureInboxService._build_item()`](../apps/api/src/services/capture_inbox_service.py:719), not deterministically normalized from Phase 2 raw evidence.
- Existing status fields are computed at response hydration time in [`CapturedItemResponse._hydrate_metadata_status()`](../apps/api/src/schemas/capture_inbox.py:167), not explicitly produced by a backend normalizer contract.
- Missing reasons are generic strings (e.g., “No view_count or like_count captured.”) rather than deterministic rule-coded reasons tied to evidence normalization.

### 4) Existing API response behavior and gaps
- [`CapturedItemResponse`](../apps/api/src/schemas/capture_inbox.py:27) already exposes canonical fields and status fields.
- Status/source/missing reason values are inferred on response hydration from mixed `metadata_json` + `raw_payload_json`; currently no strict provenance-first normalizer output contract.
- Raw evidence summary is not yet explicitly exposed as first-class response field (can be read from `metadata_json`, but not normalized contract output).

## Planned Fixes

1. Add deterministic backend normalizer service to parse and normalize:
- Time: `posted_at`, `posted_text`
- Processing fit: `duration_seconds`, `duration_text`
- Performance: `view_count`, `like_count`, `comment_count`, `share_count`, `engagement_rate`

2. Enforce source-priority:
1) `raw_network_aweme`
2) `raw_detail_aweme`
3) constrained `raw_dom_snapshot` fallback
4) missing

3. Persist explicit status/source/reason fields from normalization result in `metadata_json`.

4. Keep raw evidence fields preserved for audit/debug.

5. Expose normalized contract fields through API response schema using existing field patterns.

## Files Planned

- `apps/api/src/services/capture_metadata_normalizer.py` (new)
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_capture_metadata_normalizer.py` (new)
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/api/tests/test_capture_inbox_metadata_status.py`
- `docs/metadata-phase3-backend-normalizer-architecture.md`
- `docs/metadata-phase3-backend-normalizer-resume.md`

## Verification Plan

- Unit tests for normalizer deterministic rules.
- Service integration tests for `_build_item` persistence and fallback behavior.
- API schema/status tests for exposure consistency and old-row safety.

## Implementation Outcome

Implemented in Phase 3 scope:
- Added deterministic normalizer service at [`capture_metadata_normalizer.py`](../apps/api/src/services/capture_metadata_normalizer.py).
- Wired normalizer into [`CaptureInboxService._build_item()`](../apps/api/src/services/capture_inbox_service.py:704) and persisted canonical/source/status/reason outputs into `metadata_json` while preserving raw evidence fields.
- Expanded source literal compatibility and evidence summary hydration in [`CapturedItemResponse`](../apps/api/src/schemas/capture_inbox.py:27).
- Added/updated backend tests:
  - [`test_capture_metadata_normalizer.py`](../apps/api/tests/test_capture_metadata_normalizer.py)
  - [`test_douyin_extension_capture_service.py`](../apps/api/tests/test_douyin_extension_capture_service.py)
  - [`test_capture_inbox_metadata_status.py`](../apps/api/tests/test_capture_inbox_metadata_status.py)

## Verification Results

Executed from [`apps/api`](../apps/api):

- `python -m unittest tests.test_capture_metadata_normalizer tests.test_douyin_extension_capture_service tests.test_capture_inbox_metadata_status -v`

Result:
- `Ran 47 tests in 0.143s`
- `OK`
