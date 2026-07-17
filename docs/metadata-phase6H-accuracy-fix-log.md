# Phase 6H Accuracy Fix Log

## Why this fix is needed

- Phase 6H full modal harvest is now able to detect the current `aweme_id`, extract one modal item, and flush it to the backend.
- The remaining blocker is extraction accuracy, not transport or persistence.
- Live evidence showed two concrete quality failures:
  - `duration_seconds` came from the active video element, but `duration_text` came from a different timeline source and did not match.
  - `share_count` matched the same visible number as `like_count`, which means action-region mapping is too loose.

## Confirmed pre-fix issues

1. `duration_text` was accepted without validating that it belonged to the same active video/player as `video.duration`.
2. `findActionMetric(...)` scanned generic nodes and used `findMetricTextNearNode(...)`, so repeated numeric nodes could be reused for multiple action metrics.
3. `comment_count` could remain null because the current selector strategy did not identify a distinct comment action block confidently.
4. `raw_evidence_summary` reflected whichever keys were emitted, but the emitted keys were only as accurate as the loose DOM matching.

## Scope

- `apps/extension-douyin-capture` only
- focused tests/docs for Full Modal Harvest metric accuracy
- no backend architecture changes
- no normalizer redesign

## Non-goals

- no captcha bypass
- no backend browser crawling
- no attempt to infer `view_count`
- no broader modal harvest architecture rewrite

## Planned fix

1. Keep `duration_seconds` anchored to the active `HTMLVideoElement.duration`.
2. Accept `duration_text` only when its parsed total duration matches the active video duration within a small tolerance.
3. Replace generic nearby-number action lookup with structural action-block mapping for:
   - like
   - comment
   - favorite
   - share
4. Emit diagnostics directly in `raw_dom_detail_metrics` so bad mappings are visible in harvest/debug output.
5. Show a compact last-harvested-item summary in popup progress for live operator verification.

## Files expected

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `docs/metadata-phase6H-accuracy-fix-log.md`
- `docs/metadata-phase6H-accuracy-fix-resume.md`

## Implemented fix

1. `duration_seconds` now stays anchored to the active `HTMLVideoElement.duration`.
2. `duration_text` is only accepted when parsed timeline total matches active video duration within 3 seconds.
3. Side actions now resolve through distinct action-block candidates instead of generic nearby-number reuse.
4. Reused/shared action blocks are rejected for the second metric instead of silently duplicating a count.
5. `raw_dom_detail_metrics` now carries compact diagnostics for duration selection, block texts, confidence, and rejected reasons.
6. Harvest progress now shows the last harvested item summary so the operator can inspect live accuracy before running all 49 videos.

## Files changed

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/api/src/schemas/douyin_extension.py`
- `docs/metadata-phase6H-accuracy-fix-log.md`
- `docs/metadata-phase6H-accuracy-fix-resume.md`

## Tests run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer`
- `cd apps/api && python -m compileall src`

## Verification result

- extension typecheck passed
- extension test suite passed
- backend focused ingest/normalizer tests passed
- backend compile check passed

## Status

- implementation complete
