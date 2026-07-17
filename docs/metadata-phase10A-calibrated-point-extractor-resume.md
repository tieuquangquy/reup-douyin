# Phase 10A Calibrated Point Extractor Resume

## Objective

Replace failed global modal metric extraction with a user-calibrated point-based extractor for the Douyin modal right rail.

## Operator workflow

1. Open Douyin profile modal.
2. Click `Start Right Rail Calibration`.
3. Click the visible count labels in order: like, comment, favorite, share.
4. Run `Probe Current Modal Metrics`.
5. Start full harvest only after Probe reports PASS.

## PASS policy

Probe/harvest PASS requires:
- calibration present
- `aweme_id` present
- `duration_seconds` present
- `like_count`, `comment_count`, `favorite_count`, `share_count` all read from calibrated point DOM/OCR sources

## Safety

- captcha/login wall still stops harvest
- pending/flushed state remains resumable
- viewport-ratio fallback is allowed but should warn on large geometry shifts

## Verification

- implemented
- extension typecheck passed
- extension tests passed
