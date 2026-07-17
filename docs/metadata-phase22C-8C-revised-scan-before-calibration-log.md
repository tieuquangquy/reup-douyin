# Phase 22C-8C-Revised Scan Before Calibration Log

## Scope
- Kept Scan Profile ahead of calibration in the canonical primary action selector.
- Confirmed calibration only gates Start Collecting / extraction paths.
- Hardened zero-round scan failure classification so `profile_scan_incomplete` is never emitted when no scan round starts.

## Changes
- Updated runtime markers to `22C-8C-revised` in controller, popup, selector diagnostics, and view-model fallbacks.
- Added canonical primary action decision trace fields: selector version, profile scan readiness, calibration readiness, extraction readiness, backend session readiness, selected action, and reason.
- Added no-round normalization diagnostics: original scan error before normalization, normalized scan error, no-round guard applied, and scan no-round reason.
- Added expected-count metadata to profile scan diagnostics so counts are tied to the current profile URL and update time.

## Emitter Audit
- `profile_scan_incomplete` runtime emission is centralized in `classifyProfileScanFailure` in `wholeProfileHarvest/controller.ts`.
- `wholeProfileHarvest/errors.ts` only defines the code/message.
- Tests reference the code for regression coverage.

## Flow
1. Scan Profile.
2. Build queue / pending videos.
3. Calibrate 4 Points only if calibration is missing.
4. Start Collecting.
5. Extract modal/video metadata.
6. Flush to backend Capture Inbox.
