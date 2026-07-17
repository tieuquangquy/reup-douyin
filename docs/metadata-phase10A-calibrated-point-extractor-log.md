# Phase 10A Calibrated Point Extractor Log

## Why old global extractors were abandoned

Live Probe results proved the global extractor family was fundamentally too broad. DOM selector scans, right-band numeric scans, CDP DOM snapshots, visual right-rail OCR, and combined modal text kept pulling numbers from caption text, hidden text, chapter labels, player controls, or the background profile grid behind the modal.

The modal itself is trustworthy, but the page-level extraction surface is not. Phase 10A therefore moves PASS/WARN/FAIL to a user-calibrated point extractor that reads only the four operator-confirmed count locations.

## Scope

This phase changes only the extension-side modal probe/harvest flow and its tests/docs.

Non-goals:
- no backend browser crawling
- no captcha bypass
- no broad backend contract redesign
- no revival of global DOM/CDP/OCR extractors as PASS sources

## Chosen approach

1. Operator runs `Start Right Rail Calibration`.
2. The content script shows an overlay and asks the operator to click the visible count labels in this order:
   1. like
   2. comment
   3. favorite
   4. share
3. The extension stores absolute coordinates plus viewport ratios in `chrome.storage.local`.
4. Probe/harvest reads only those points.
5. Primary extraction uses `document.elementsFromPoint(x, y)` and compact-text parsing.
6. If DOM lookup fails for a point, OCR fallback is attempted on a small cropped screenshot around that point.
7. PASS is allowed only when counts come from calibrated point DOM/OCR sources.

## Extraction rules

- `aweme_id` still comes from modal URL detection.
- `duration_seconds` still comes from the active modal video.
- `like/comment/favorite/share` come only from calibrated point reads.
- Old global extractors remain debug-only and cannot make Probe PASS.

## Recalibration rules

Warn or fail when:
- calibration is missing
- viewport changed materially relative to calibration
- zoom/layout changed enough that point reads fail

## Tests run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`

## Verification

- Typecheck passed
- Extension test suite passed
- Full modal probe/harvest now uses calibrated points as the only PASS source
- Old global DOM/CDP/right-rail scanners remain available only as legacy diagnostics, not as PASS gates
