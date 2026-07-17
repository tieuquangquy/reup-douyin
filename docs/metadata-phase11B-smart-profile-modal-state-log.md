# Phase 11B Smart Profile/Modal State Log

## Scope

Fixed only `apps/extension-douyin-capture` Smart Capture & Harvest popup workflow behavior plus workflow tests/docs.

## Root Cause

The popup had two stale-state paths:

1. The operational summary could report `Viewport warning: none` from the current viewport while the separate red status banner still held an old viewport recalibration error text.
2. The smart workflow treated the last stored modal probe as generally reusable. It did not bind probe PASS state to the current page `modal_id`, so a profile URL with no `modal_id` could still display an old PASS and skip the intended profile-first/manual-modal checkpoint.

## Fix Summary

- Added Douyin popup page classification for profile, modal, direct video, other, and unknown URLs.
- Added probe freshness validation requiring the current page to expose a modal/video id, the probe `aweme_id` to match it, the probe to PASS, harvest readiness to be true, and the source to be calibrated point based.
- Reconciled stale `viewport_changed_significantly` state to clear `last_error` when the current viewport matches the calibration.
- Changed profile/no-modal Smart Capture behavior to run capture first, save the capture binding, clear stale probes, set `modal_required`, and render the modal instruction as a neutral status instead of an error banner.
- Changed Resume behavior to require a modal URL, run a current modal probe, validate freshness, then resume harvest only after the PASS matches the current modal id.

## Profile-vs-Modal Workflow

### Profile URL

On `/user/...` without `modal_id`:

1. Smart Capture runs Capture current page.
2. The latest capture session/capture id/item count are stored.
3. Calibration and viewport are checked.
4. If calibrated and viewport is acceptable, state becomes `modal_required`.
5. The operator sees: `Open the first video modal, then click Resume Smart Capture & Harvest.`
6. Any old modal probe is cleared and not reused.

### Modal URL

On `/user/...?modal_id=...` or `/video/{aweme_id}`:

1. Resume runs a fresh calibrated point probe for the visible modal/video.
2. The probe must PASS for the same current modal/video id.
3. Harvest resumes using the stored capture session binding.

## Probe Freshness Rule

A stored/current probe is harvest-ready only when all are true:

- current page has a `modal_id` or direct video id
- `probe.aweme_id` equals the current id
- `probe.probe_status` is `PASS`
- `probe.ready_for_full_harvest` is true
- `probe.source_used` is one of `calibrated_point_dom`, `calibrated_point_ocr`, or `mixed_calibrated_point`

On profile URLs with no modal id, probe display is `not applicable` and harvest cannot start from the old probe.

## Resume Behavior

Resume no longer starts/resumes harvest directly from saved state. It first detects the current modal id, probes the current modal, validates the PASS/current-id/source match, then sends the resume harvest message with the stored capture session options.

## Tests Added/Updated

Updated `apps/extension-douyin-capture/src/popupWorkflow.test.ts` to cover:

- stale viewport error clearing when current viewport is acceptable
- profile URL classification and `modal_required` transition
- stale previous modal PASS not being reused on profile URLs
- `modal_required` operator instruction
- modal/direct-video URL id extraction
- fresh probe validation by current `modal_id`
- source freshness requirement for calibrated point sources
- source-level assertions that Smart Capture captures first, clears stale probe, and Resume probes before harvest
- continued actual viewport-change blocking
- `no_saved_harvest_state` not becoming a viewport warning

## Verification

Verification completed:

```text
npx tsx apps/extension-douyin-capture/src/popupWorkflow.test.ts
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```
