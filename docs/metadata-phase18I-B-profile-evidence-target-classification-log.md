# Phase 18I-B Profile Evidence + Target Classification Log

## Scope
Implemented Phase 18I-B scoped changes for whole-profile verify/classification flow and queue planning behavior, including extension + API read-only classification endpoint and tests.

## Completed Changes

### Extension
- Enriched verified target evidence model and normalization flow.
- Added classification-aware status handling: `new`, `incomplete`, `complete`, `failed`, `skipped`, `unknown`.
- Updated queue preview filtering so default planning excludes `complete` targets and respects mode behavior.
- Added local result override application in queue preview state refresh.
- Added runtime classification transport hook and verify-time merge/fallback behavior.
- Added explicit error code for classification failure.

### API
- Added target classification request/response schemas.
- Added read-only classification route:
  - `POST /douyin-extension/capture-inbox/classify-targets`
- Added service classification method returning per-target item status and aggregate counts.
- Preserved existing full-modal harvest behavior while restoring expected staged-harvest V2 run-id session resolution path used by tests.

### Tests
- Added/updated API route test for classification endpoint.
- Added/updated API service test for classification counts and status composition.
- Updated test fixture DB doubles to satisfy capture-session lookup behavior under current service logic.

## Validation Runs

### Extension
- `npm --workspace @reup-douyin/extension-douyin-capture run test -- wholeProfileHarvest.test.ts` ✅
- Extension suite/build path (invoked by workspace test script) ✅

### API
- `python -m unittest tests.test_douyin_extension_routes tests.test_douyin_extension_capture_service` (from `apps/api`) ✅
- `python -m compileall src` (from `apps/api`) ✅

## Notes
- `pytest` was unavailable in the environment, so API validation used `unittest`.
- One failing legacy expectation was resolved by restoring V2 run-id lookup usage in capture session resolution logic.
