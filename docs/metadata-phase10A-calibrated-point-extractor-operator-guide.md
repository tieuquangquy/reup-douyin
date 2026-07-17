# Phase 10A Calibrated Point Extractor Operator Guide

## Why calibration is required

Global DOM/CDP/OCR extraction was reading the wrong numbers from the wider page. Calibration constrains reading to the four exact visible count labels that the operator confirms.

## Calibration workflow

1. Open a Douyin video modal.
2. Click `Start Right Rail Calibration`.
3. Click the visible labels in order:
   1. like
   2. comment
   3. favorite
   4. share
4. Confirm calibration is saved.
5. Run `Probe Current Modal Metrics`.

## Probe expectations

PASS requires:
- `aweme_id`
- `duration_seconds`
- calibrated `like/comment/favorite/share`

WARN examples:
- one point failed
- OCR fallback used with weak result
- viewport changed materially since calibration

FAIL examples:
- no calibration
- no `aweme_id`
- no `duration_seconds`

## Full harvest workflow

1. Calibrate once for the current modal layout.
2. Run Probe.
3. Start full harvest only after PASS.
4. Keep modal open and let navigation continue.
5. Recalibrate if layout/zoom/viewport changes.

## OCR fallback

The current Phase 10A implementation keeps OCR as a narrow adapter/parser fallback path only. The production PASS source is calibrated point DOM extraction. If a point read fails, the probe warns instead of promoting any global OCR/CDP scan to PASS.

## Live retest steps

1. Build/reload extension.
2. Open Douyin profile and click first video modal.
3. Run `Start Right Rail Calibration`.
4. Run `Probe Current Modal Metrics`.
5. Confirm PASS before starting full harvest.

## Verification

- `npm run typecheck` passed
- `npm test` passed
