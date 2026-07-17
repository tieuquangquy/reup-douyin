# Metadata Phase 5C Extension Detail Hydration Log

## Scope

- Requested scope: Phase 5C only.
- Goal: add extension-side detail hydration fallback so `raw_detail_aweme` can be collected when feed/profile evidence is missing.
- Non-goals:
  - no backend normalizer change
  - no Capture Inbox UI change
  - no backend hydration job
  - no fake performance/duration from DOM

## Phase 5A-R live input

Latest real live audit entering Phase 5C:

- total live items: `49`
- `raw_network_aweme`: `0 / 49`
- `raw_detail_aweme`: `0 / 49`
- `raw_dom_snapshot`: `49 / 49`
- `duration_seconds`: `0 / 49`
- `view_count`: `0 / 49`
- `like_count`: `0 / 49`
- `comment_count`: `0 / 49`
- `share_count`: `0 / 49`

Conclusion:

- upstream extension evidence acquisition is still the bottleneck
- exact-id detail fallback is needed

## Why detail hydration fallback is needed

- Grid discovery already gives:
  - `aweme_id`
  - `source_url`
  - `share_url`
- But live profile/feed capture can still miss both:
  - `raw_network_aweme`
  - `raw_detail_aweme`
- The extension therefore needs an active follow-up step:
  - fetch detail HTML/JSON for discovered `aweme_id`
  - recursively locate the exact aweme object
  - preserve bounded `raw_detail_aweme`

## Audit summary before implementation

- `extractor.ts` already supported a `detailHydrateItems` input path.
- `contentScript.ts` did not supply any live detail hydrate items.
- `popupTransport.ts` direct fallback intentionally stayed DOM-only, which remains unchanged.
- `networkCache.ts` already had canonical normalization suitable for reuse.

## Implemented fix

### 1. New detail hydration helper

Added:

- `apps/extension-douyin-capture/src/detailHydration.ts`

Main behavior:

- take discovered `aweme_id` + `source_url` / `share_url`
- fetch detail source with credentials included
- parse:
  - direct JSON responses
  - embedded JSON in HTML script tags
  - balanced JSON literals inside scripts
- normalize candidate roots through `normalizeDouyinNetworkPayload(..., "detail_hydrate")`
- keep only exact `aweme_id` matches

### 2. Capture flow integration

- `contentScript.ts` now:
  - discovers visible aweme ids
  - runs detail hydration fallback before final payload build
  - passes `detailHydrateItems` into `buildCapturePayload(...)`
  - records counters into payload diagnostics

### 3. Extractor integration

- `extractor.ts` now accepts `detailHydrateItems` in `buildCapturePayload(...)`
- detail items are context-filtered and passed into `extractVideos(...)`
- exact-id attachment remains unchanged

### 4. Evidence summary versioning

- `raw_evidence_summary.evidence_collection_version` now upgrades to `phase5c_detail_hydrate` when detail evidence is present

## Exact-id matching rule

- detail evidence attaches only when:
  - `String(candidate.aweme_id).trim() === String(targetAwemeId).trim()`
- No merge by:
  - title
  - thumbnail
  - index
  - order
  - URL similarity alone

## Timeout and concurrency strategy

- default timeout per item: `8000ms`
- default concurrency: `3`
- failure/timeout is item-local only
- whole capture does not fail if one detail hydrate fails

## Diagnostics added

Capture payload diagnostics now include:

- `detail_hydrate_attempted_count`
- `detail_hydrate_success_count`
- `detail_hydrate_failed_count`
- `detail_hydrate_timeout_count`
- `raw_detail_aweme_attached_count`

## Files changed

- `apps/extension-douyin-capture/src/detailHydration.ts`
- `apps/extension-douyin-capture/src/detailHydration.test.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/package.json`
- `docs/metadata-phase5C-extension-detail-hydration-log.md`
- `docs/metadata-phase5C-extension-detail-hydration-resume.md`
- `docs/metadata-phase5C-extension-detail-hydration-architecture.md`

## Tests run

- `npm run typecheck`
- `npm test`
- `npm run build`

## Verification result

- typecheck: passed
- extension tests: passed
- build: passed

## Exact live retest steps

1. `cd apps/extension-douyin-capture`
2. `npm run build`
3. Reload the unpacked extension
4. Refresh the real Douyin page fully
5. Run `Capture current page`
6. `cd ../api`
7. `python tests/metadata_phase5a_real_live_audit.py`

## Expected Phase 5A-R metrics to check

- `raw_detail_aweme` coverage > `0`
- `raw_evidence_summary.has_detail_aweme` > `0`
- `duration_seconds` coverage > `0` if detail `video.duration` exists
- `view_count` / `like_count` coverage > `0` if detail `statistics` exists
