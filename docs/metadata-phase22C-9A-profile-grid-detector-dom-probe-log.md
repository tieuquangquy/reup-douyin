# Phase 22C-9A Profile Grid Detector DOM Probe Log

## Scope

Implemented only Phase 22C-9A scan-profile hardening. Backend APIs, Capture Inbox UI, Review Board, Reup Score, modal extraction, batch collection, and calibration requirements were not changed.

## Why Scan Profile Reached No Round Started

The active Scan Profile path was:

`popup.ts` primary action `scan_profile` -> `runScanProfileWorkflow()` -> `completeProfileVerify()` -> `scanWholeProfileTargets()` -> popup runtime `scanProfile()` -> content script message `REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE` -> `runModalTestProfileScan()` -> `collectProfileCardsUntilStable()`.

The scanner could return zero scan rounds without a structured page-level reason. The controller then normalized the failure to `profile_scan_no_round_started` or `profile_grid_not_ready_timeout`, but diagnostics lacked selector hits, link counts, aweme extraction counts, and scroll-container evidence. The operator could see that no round started, but not why round 1 never became valid.

## DOM Probe Fields

Added `profile_dom_probe` with trace version `22C-9A`.

Key fields include URL/path/search, document ready state, body text length, page type, profile container/grid selectors, `/video/` anchor count and samples, `modal_id`/`aweme_id` link count and samples, extracted aweme id count and samples, selector hit counts, scroll container details, empty profile detection, login/captcha/checkpoint/page-block detection, and probe errors.

## Grid Detection Selectors

Grid readiness is no longer tied to one brittle selector. The probe checks:

- `a[href*="/video/"]`
- `a[href*="modal_id="]`
- `a[href*="aweme_id="]`
- `[data-aweme-id]`
- `[data-item-id]`
- `[data-e2e*="user-post"]`
- `[data-e2e*="post-item"]`
- `[data-e2e*="user-work"]`
- `[data-e2e*="work-item"]`
- post/work/card/video class fallbacks

One valid video/modal/aweme candidate is enough to start scanning.

## Aweme Extraction Fallbacks

Aweme IDs are extracted from:

- `/video/<aweme_id>`
- `modal_id=<aweme_id>`
- `aweme_id=<aweme_id>`
- data attributes and bounded element attributes
- existing bounded card-context extraction

IDs are normalized as strings, validated as 16-22 digits, deduped, and timestamp-like candidates are rejected.

## Error Classification

Added explicit preflight classification:

- `profile_grid_not_ready_timeout` when no grid/video candidates appear before timeout.
- `profile_aweme_extraction_failed` when candidate links exist but no aweme can be extracted.
- `douyin_login_required` for login walls.
- `douyin_checkpoint_required` for captcha/checkpoint/security blocks.
- `no_videos_found` for explicit empty profile state.

`profile_scan_incomplete` remains valid only after real scan rounds start.

## Diagnostics

Progress and advanced diagnostics now expose profile DOM probe status, grid readiness, grid selector, video anchor count, aweme id count, grid candidate count, scroll container state, preflight status, and no-round reason.

## Tests Run

- `npx tsx apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`
- `npx tsx apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`

Full extension test/build pending at this log checkpoint.

## Manual Retest Steps

1. Open a Douyin profile with visible video cards.
2. Open the extension.
3. Confirm diagnostics show scanner runtime `22C-9A`.
4. Click Scan Profile before calibration.
5. If scan succeeds, confirm scan rounds start and pending queue builds.
6. If scan fails, expand diagnostics and inspect `profile_dom_probe`, selector hits, video anchor count, aweme id count, scroll container, and no-round reason.
