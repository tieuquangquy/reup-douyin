# Phase 11A Production Stabilized Calibrated Harvest Log

## Final production workflow

1. Capture current page
2. Calibrate four right-rail points
3. Probe current modal via calibrated points
4. Smart Capture & Harvest
5. Backend ingests calibrated-point payload
6. Tile Gallery renders truthful real or estimated views

## Old extractors disabled as normal PASS sources

Normal PASS no longer comes from:

- global DOM selector extraction
- icon/action rail heuristics
- text cluster extraction
- combined modal text fallback
- CDP runtime/network/DOMSnapshot
- broad OCR/accessibility scans

Normal PASS requires calibrated-point sources only.

## Calibrated point source contract

Allowed calibrated pass sources:

- `calibrated_point_dom`
- `calibrated_point_ocr`
- `mixed_calibrated_point`

Probe PASS still requires:

- `aweme_id`
- `duration_seconds`
- `like_count`
- `comment_count`
- `favorite_count`
- `share_count`

## Backend schema compatibility fix

The API full-modal harvest schema now accepts:

- `raw_dom_detail_metrics.extraction_source`
  - `dom_detail_modal`
  - `video_element_modal`
  - `calibrated_point_dom`
  - `calibrated_point_ocr`
  - `mixed_calibrated_point`

- `raw_evidence_summary.evidence_collection_version`
  - `phase2`
  - `phase5c_detail_hydrate`
  - `phase6h_full_modal_auto_harvest`
  - `phase10a_calibrated_point_extractor`
  - `phase10c_smart_capture_harvest`
  - `phase11a_production_stabilized_calibrated_harvest`

The ingest service now preserves incoming calibrated evidence version instead of forcing Phase 6H.

## Stale viewport bug root cause

The popup reused persisted smart state without reconciling it against live calibration, current viewport, and probe state. That let `viewport_changed_significantly` survive after the viewport was already valid again.

## Views 0 bug root cause

Tile Gallery treated `view_count = 0` as real data even when provenance was missing or fallback-only. That suppressed estimated views and showed misleading `Views 0`.

## Estimated views formula

When real views are unknown and `like_count > 0`:

- low = `like_count * 20`
- base = `like_count * 33`
- high = `like_count * 100`

Cards render the compact low-high range.

## Tests run

- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_status`
- `cd apps/api && python -m compileall src scripts`
- `npx tsx apps/web/src/test/capture-inbox.test.ts`
- `npm --workspace @reup-douyin/web run typecheck`

## Live retest steps

1. Build and reload the extension
2. Open a Douyin profile page
3. Click `Capture current page only`
4. Open first modal video
5. Run calibration if missing
6. Click `Probe Current Modal Metrics`
7. Confirm probe `PASS`
8. Click `Smart Capture & Harvest`
9. Confirm no stale viewport warning when calibrated viewport matches current viewport
10. Flush pending harvest
11. Open Capture Inbox Tile Gallery and confirm unknown views render as `Est. Views` or `—`, not `Views 0`

## Verification result

- Extension tests passed
- Extension typecheck passed
- Extension build passed
- API tests passed
- API compile check passed
- Web tests passed
- Web typecheck passed
