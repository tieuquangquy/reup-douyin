# Phase 9A Accessibility/OCR Right-Rail Migration Log

## Scope
- Extension-only Phase 9A migration to visual-first modal metrics extraction.
- PASS gating now requires visual extraction sources for probe/full harvest.
- Legacy DOM/CDP fallback sources are retained for diagnostics but must not independently produce PASS.

## Implemented
- Added Accessibility Tree right-rail metric extraction path in [`captureVisualRightRailPayload()`](apps/extension-douyin-capture/src/background.ts:280) and [`extractVisualRightRailMetrics()`](apps/extension-douyin-capture/src/modalHarvest.ts:1979).
- Added OCR fallback parsing and selection flow in [`parseOcrCompactCountLines()`](apps/extension-douyin-capture/src/modalHarvest.ts:2036).
- Wired content script visual callback in [`getVisualRightRail()`](apps/extension-douyin-capture/src/contentScript.ts:401).
- Updated probe/full harvest gating in [`probeCurrentModalMetrics()`](apps/extension-douyin-capture/src/modalHarvest.ts:873) and [`extractCurrentModalMetricsForAweme()`](apps/extension-douyin-capture/src/modalHarvest.ts:988).

## Test Alignment Completed
- Updated Phase 9A expectations in [`modalHarvest.test.ts`](apps/extension-douyin-capture/src/modalHarvest.test.ts).
- Updated CDP lifecycle assertion for Accessibility enable in [`background.test.ts`](apps/extension-douyin-capture/src/background.test.ts:135).

## Verification
- `npx tsx apps/extension-douyin-capture/src/modalHarvest.test.ts` PASS.
- `npx tsx apps/extension-douyin-capture/src/background.test.ts` PASS.
- `npm run test --workspace @reup-douyin/extension-douyin-capture` PASS.

## Notes
- Observed fallback extraction modes like `right_rail_numeric_band` / `right_rail_element_from_point_fallback` can still populate fields while probe remains blocked with `visual_source_unusable` where visual evidence is absent.
- Combined text fallback may appear in evidence summaries but does not override visual-source PASS gating.
