# Phase 13D Profile Modal State Detector Fix Log

## Scope

Phase 13D is limited to `apps/extension-douyin-capture` and extension-facing documentation. It fixes the Douyin extension popup workflow so profile capture is treated as a profile-stage action, modal/video metric extraction remains the only calibration-dependent stage, and detector/content-script failures are surfaced before calibration guidance.

## Root Cause

The popup workflow previously inferred readiness from a mixed snapshot of capture session, calibration, probe, and page state. On a Douyin profile URL without `modal_id`, a missing calibration could win state reconciliation before the operator had captured the profile grid. This made a profile page incorrectly display `calibration_required`, even though right-rail calibration is only needed after the operator opens a modal/video where like/comment/favorite/share counts are read.

A second issue was that content-script and detector availability were not represented as first-class popup state. When the extension could not reach or refresh the Douyin content script, the popup could fall through to calibration messaging instead of telling the operator to reconnect the active tab.

## Changes

- Added content-script page-context detection through `detectDouyinPageContext()` with profile, modal, video, and unknown page types.
- Added content-script ping support through `REUP_DOUYIN_PING`.
- Added content-script page-context message support through `REUP_DOUYIN_DETECT_PAGE_CONTEXT`.
- Added shared `DouyinPageContext` types and page-context response fields.
- Added popup detector reconnect logic using active-tab URL validation, ping, optional `contentScript.js` injection, re-ping, and page-context detection.
- Added the `Reconnect Douyin tab` popup button.
- Added popup diagnostics for page type, content script status, detector status, capture session, calibration, current state, and next required action.
- Added workflow states for backend unavailable, unsupported tab, content script unavailable, detector unavailable, profile capture required, and harvest ready.
- Updated state priority so backend/tab/content-script/detector failures are evaluated before calibration.
- Updated profile-page reconciliation so profile pages without a capture session become `profile_capture_required` instead of `calibration_required`.
- Updated profile-page reconciliation so profile pages with a capture session become `modal_required` and clear stale probe applicability.
- Preserved calibration for modal/video pages only; missing calibration on modal/video still produces `calibration_required`.
- Preserved existing calibration data when detector/content-script reconnect fails.

## Verification Added

Extension tests now cover:

- Profile URL without `modal_id` is classified as profile.
- Modal URL with `modal_id` is classified as modal.
- Direct video URL is classified as video.
- Detector/content-script unavailable state does not become `calibration_required`.
- Profile page without capture session becomes `profile_capture_required`.
- Profile page with capture session becomes `modal_required`.
- Modal page missing calibration becomes `calibration_required`.
- Modal page with calibration but no current probe remains probe-gated.
- Stale probe PASS is not reused on profile pages.
- Popup source implements ping-inject-ping detector reconnect.
- Popup HTML renders the `Reconnect Douyin tab` button.
- Popup summary includes page type, content script status, and detector status.

## Verification Run

From the repository root, this command passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
```

The test script also ran the extension build and distribution module-resolution check.

## Operator Result

On a Douyin profile page, the popup now asks the operator to capture the current profile page first. After profile capture creates a capture session and target queue, the popup asks the operator to open the first modal/video before requiring calibration or probe actions. If the detector or content script is unavailable, the popup asks the operator to click `Reconnect Douyin tab` instead of showing calibration guidance.

## Non-Goals Preserved

No backend, web app, metric extraction, CDP/debug workflow, calibrated point concept, auto-publish integration, crawler implementation, or broader harvest algorithm rewrite was introduced in Phase 13D.
