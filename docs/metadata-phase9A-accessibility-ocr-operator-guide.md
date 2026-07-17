# Phase 9A Operator Guide: Accessibility/OCR Right-Rail

## What Changed
The extension now prioritizes visual right-rail extraction from Accessibility Tree, with OCR fallback when needed.

## Expected Behavior
- Successful visual capture yields source values like:
  - `accessibility_tree_right_rail`
  - `screenshot_ocr_right_rail`
- Probe PASS/ready-for-harvest depends on usable visual-source metrics.
- Non-visual fallbacks may still appear in diagnostics but should not be treated as PASS-qualifying.

## Validation Commands
- Run targeted harvest test: `npx tsx apps/extension-douyin-capture/src/modalHarvest.test.ts`
- Run CDP/background test: `npx tsx apps/extension-douyin-capture/src/background.test.ts`
- Run full extension suite: `npm run test --workspace @reup-douyin/extension-douyin-capture`

## Troubleshooting Signals
- If probe fails with `visual_source_unusable`, verify visual callback flow via [`getVisualRightRail()`](apps/extension-douyin-capture/src/contentScript.ts:401).
- If CDP attach tests fail on expected commands, verify `Accessibility.enable` ordering in [`startCdpHarvest()`](apps/extension-douyin-capture/src/background.ts:127).
