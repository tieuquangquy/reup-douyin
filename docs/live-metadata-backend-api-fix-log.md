# Live Metadata Backend/API Fix Log (Part D only)

## Task

Part D only: persist and expose live-fixed metadata fields through backend staging and Capture Inbox API.

In scope fields only:

- `posted_at`
- `posted_text`
- `duration_seconds`
- `duration_text`
- `view_count`
- `like_count`
- `comment_count`
- `share_count`

Out of scope:

- extension normalization changes
- frontend rendering/UI changes
- unrelated metadata expansion

## Inputs from Part B / Part C

Confirmed extension fixes:

- [`docs/live-posted-duration-extension-fix-log.md`](./live-posted-duration-extension-fix-log.md)
- [`docs/live-performance-extension-fix-log.md`](./live-performance-extension-fix-log.md)

Part D baseline expectations:

1. Persist these fields during staging without inventing missing values.
2. Expose these fields via Capture Inbox API with backward-safe null handling.
3. Keep compatibility for old rows where some fields are absent.

## Persistence/API strategy

Use repository-consistent pattern:

- persist canonical values to existing top-level item columns where established
- preserve values in `metadata_json` where established
- API schema + hydration should expose target fields from canonical columns and fallback metadata/raw payload as needed
- preserve honest null for unavailable values

## Planned touchpoints (before implementation)

Likely backend/API files:

- [`apps/api/src/services/capture_inbox_service.py`](../apps/api/src/services/capture_inbox_service.py)
- [`apps/api/src/schemas/capture_inbox.py`](../apps/api/src/schemas/capture_inbox.py)
- focused API/service tests under [`apps/api/tests`](../apps/api/tests)

No extension or frontend file changes in Part D.

## Verification plan

Focused validation:

1. staging persists time fields (`posted_at`, `posted_text`)
2. staging persists duration fields (`duration_seconds`, `duration_text`)
3. staging persists performance fields (`view_count`, `like_count`, `comment_count`, `share_count`)
4. Capture Inbox API exposes target fields
5. legacy rows with missing fields serialize safely
6. null/missing values remain honest

## Implementation results

### Files changed

- [`apps/api/src/schemas/capture_inbox.py`](../apps/api/src/schemas/capture_inbox.py)
  - Expanded accepted source literals for API exposure/hydration to align with live extension outputs:
    - `duration_source`: now accepts `dom_text`
    - `view_count_source`: now accepts `dom_text`
    - `like_count_source`: now accepts `dom_text`
    - `comment_count_source`: now accepts `dom_text`
    - `share_count_source`: now accepts `dom_text`
    - `engagement_rate_source`: now accepts `derived_from_canonical_counts` and `dom_text`
  - Preserved backward-safe behavior for existing literals and missing values.

- [`apps/api/tests/test_douyin_extension_capture_service.py`](../apps/api/tests/test_douyin_extension_capture_service.py)
  - Updated provenance-focused assertion fixture to include live extension literals (`dom_text`, `derived_from_canonical_counts`).
  - Updated assertions so response hydration verifies these literals are exposed instead of being dropped to `None`.

### Persistence verification

- Confirmed staging persistence in [`CaptureInboxService._build_item()`](../apps/api/src/services/capture_inbox_service.py) already writes target fields in-scope:
  - top-level columns: `duration_seconds`, `posted_at`
  - `metadata_json`: `duration_text`, `duration_seconds`, `posted_text`, `posted_at`, `view_count`, `like_count`, `comment_count`, `share_count`
- No additional persistence code changes were required for Part D field set.

### API exposure verification

- [`CapturedItemResponse.hydrate_card_grid_metadata()`](../apps/api/src/schemas/capture_inbox.py) now accepts/returns live extension source literals for duration/performance provenance fields.
- Backward compatibility preserved: old rows with missing source/value fields continue to serialize with null-safe fallbacks.

### Tests run

- Command attempted (not available in environment):
  - `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py`
  - Result: `No module named pytest`

- Verification command used:
  - `python -m unittest tests/test_douyin_extension_capture_service.py` (run from `apps/api`)
  - Result: `Ran 30 tests ... OK`

### Scope compliance

- No extension normalization changes in Part D.
- No frontend/UI changes in Part D.
- Changes constrained to backend API schema + backend tests.
