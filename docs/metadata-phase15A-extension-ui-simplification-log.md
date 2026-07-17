# Phase 15A Extension UI Simplification Log

- Scope limited to `apps/extension-douyin-capture` popup UX only.
- Updated popup action surface to production-first workflow.
- Moved technical controls under an `Advanced Diagnostics` collapsible section.
- Renamed key operator labels:
  - Start Right Rail Calibration -> Calibrate 4 Points
  - Probe Current Modal Metrics -> Test Current Video
  - Resume Harvest -> Resume
  - Stop Harvest -> Stop
- Simplified status summary fields to Page/Backend/Detector/Session/Calibration/Harvest.
- Added visibility behavior in popup runtime for running/paused states.
- Updated workflow tests to assert new section/labels.
