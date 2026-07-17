# Phase 6I Modal Action Rail + Progress Log

## Why this phase is needed

- Phase 6H now proves the end-to-end modal harvest path works for at least one item.
- The remaining gaps are extractor robustness and operator confidence before running a full 51-video sweep.
- Real Douyin modal UI exposes a clear right action rail, but the current extractor still misses `comment_count` on live pages.
- The popup also lacks a proper probe/self-check and production-grade progress/ETA fields.

## Confirmed pre-fix issues

1. Action rail extraction is still too dependent on semantic hints alone and can miss comment/share on real profile layouts.
2. There is no dedicated probe action for current modal metrics before starting full harvest.
3. Start Full Modal Harvest does not block when current modal evidence is obviously incomplete.
4. Progress lacks `current_index`, elapsed time, average seconds per item, ETA, and recent item summaries.

## Scope

- `apps/extension-douyin-capture`
- tiny API alignment only if payload/response types need narrow support
- focused tests/docs only

## Non-goals

- no backend browser crawling
- no captcha bypass
- no automated captcha solving
- no fake `view_count`
- no backend normalizer redesign

## Planned implementation

1. Add a modal action rail extractor with:
   - semantic identity first
   - vertical order fallback second
   - distinct node assignment
2. Add `Probe Current Modal Metrics` action.
3. Make full-harvest start run the probe first and block on missing `aweme_id`, missing duration, or zero action blocks.
4. Add richer progress state with ETA and recent items.
5. Keep existing duration conflict handling and flush/resume behavior.

## Expected files

- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/popupActions.test.ts`
- `docs/metadata-phase6I-modal-action-rail-progress-log.md`
- `docs/metadata-phase6I-modal-action-rail-progress-resume.md`
- `docs/metadata-phase6I-modal-action-rail-progress-operator-guide.md`

## Implemented fix

1. Action rail extraction now works in two passes:
   - semantic identity first from aria/title/class/text hints
   - vertical-order fallback second, but only for obfuscated action blocks
2. Action rail candidates are now restricted to the right-side modal rail geometry:
   - center point must be in the right 20% of the viewport
   - top/bottom extremes are excluded to avoid caption/search/player-control bleed
3. Vertical-order fallback no longer steals counts from semantically identified comment/share blocks.
4. Added `Probe Current Modal Metrics` before full harvest.
4. Start Full Modal Harvest now:
   - blocks on missing `aweme_id`
   - blocks on missing duration
   - blocks on zero action blocks
   - warns on partial action-rail coverage and requires an explicit second click to override
5. Probe now reports ordered block diagnostics:
   - index
   - rect
   - visible text
   - aria/title/class hints
   - assigned metric
   - count text
   - count value
6. Progress now includes:
   - current index
   - caption snippet
   - elapsed seconds
   - average seconds per item
   - ETA
   - last extracted metrics
   - recent items

## Tests run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`
- `cd apps/api && python -m unittest tests.test_capture_metadata_normalizer tests.test_douyin_extension_capture_service`
- `cd apps/api && python -m compileall src`

## Verification result

- extension typecheck passed
- extension test suite passed
- backend focused tests remain passing
- backend compile check passed
