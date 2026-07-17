# Capture Current Page 422 Diagnosis/Fix Log

## Scope
- Fix only current backend `422` for extension [`capture_current_page`](apps/api/src/api/routes/douyin_extension.py:131) after content-script ESM issue was already resolved.
- In-scope: [`apps/extension-douyin-capture`](apps/extension-douyin-capture), [`apps/api`](apps/api), and focused docs/tests.

## Exact 422 root cause

### Failing layer
- Request validation layer at FastAPI/Pydantic boundary for [`DouyinExtensionCaptureRequest`](apps/api/src/schemas/douyin_extension.py:197) (before service business logic).

### Exact failing fields/path
Live schema check reproduced validation errors for payload shape now emitted by extension direct-capture path:
- `videos.0.duration_source = "dom_text"` rejected by [`DouyinDurationSource`](apps/api/src/schemas/douyin_extension.py:51), which currently only allows `"network_json" | "detail_hydrate" | "dom_fallback" | "fallback_none"`.
- `videos.0.view_count_source = "dom_text"` rejected by [`DouyinMetricSource`](apps/api/src/schemas/douyin_extension.py:50), same mismatch.
- `videos.0.engagement_rate_source = "derived_from_canonical_counts"` rejected by [`DouyinEngagementRateSource`](apps/api/src/schemas/douyin_extension.py:52), which currently expects `"derived_from_counts"` (different literal).

### Why this happened
- Extension payload contract in [`types.ts`](apps/extension-douyin-capture/src/types.ts:47) and direct execution builder in [`popupTransport.ts`](apps/extension-douyin-capture/src/popupTransport.ts:411) use provenance literals:
  - `dom_text` for duration/metric sources
  - `derived_from_canonical_counts` for engagement-rate source
- Backend schema enum literals drifted to older/different naming (`dom_fallback`, `derived_from_counts`).

## Before-fix request/load path
- Extension sends payload via [`postJson(..."/douyin-extension/capture-current-page", response.payload)`](apps/extension-douyin-capture/src/popup.ts:100).
- Route receives body at [`capture_douyin_extension_current_page()`](apps/api/src/api/routes/douyin_extension.py:132).
- Body parsing fails in Pydantic model [`DouyinExtensionCaptureRequest`](apps/api/src/schemas/douyin_extension.py:197), producing HTTP 422 before service staging in [`capture_current_page()`](apps/api/src/services/douyin_extension_capture_service.py:176).

## Planned narrow fix
1. Align backend schema enum literals with extension payload contract for source/provenance fields.
2. Keep current extension payload semantics unchanged (they reflect canonical naming already used in current code/tests).
3. Add focused backend tests proving these literals are accepted and explicit-null processing-fit fields remain valid.
4. Re-run targeted tests for capture current page flow.

## Files changed
- Updated [`DouyinMetricSource`](apps/api/src/schemas/douyin_extension.py:50) to also accept `"dom_text"`.
- Updated [`DouyinDurationSource`](apps/api/src/schemas/douyin_extension.py:51) to also accept `"dom_text"`.
- Updated [`DouyinEngagementRateSource`](apps/api/src/schemas/douyin_extension.py:52) to also accept `"derived_from_canonical_counts"`.
- Added focused schema-acceptance test [`test_video_payload_accepts_extension_dom_text_and_canonical_engagement_literals()`](apps/api/tests/test_douyin_extension_capture_service.py:138).

## Tests run
- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_video_payload_accepts_extension_dom_text_and_canonical_engagement_literals -q` (cwd: [`apps/api`](apps/api)) -> pass.
- `python -m unittest tests.test_douyin_extension_capture_service.DouyinExtensionCaptureServiceTests.test_video_payload_preserves_card_grid_metadata_for_staging -q` (cwd: [`apps/api`](apps/api)) -> pass.

## Verification result
- Backend request schema now accepts the extension-emitted literals that previously produced HTTP 422 at request-validation time.
- Existing payload provenance behavior remains valid in focused service-schema tests.
