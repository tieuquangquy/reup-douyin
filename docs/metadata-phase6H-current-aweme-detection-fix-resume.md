# Phase 6H Current Aweme Detection Fix Resume

## Summary

This fix hardens only the current-aweme detection boundary for Full Modal Harvest.

## Before

- start command could succeed
- popup progress could still show `Current aweme = not detected`
- first item was not bootstrapped into pending state
- no structured detector diagnostics were exposed

## After

- start/resume bootstrap current aweme detection immediately
- first current modal extraction is attempted immediately
- progress can include detector diagnostics:
  - `current_url`
  - `location_search`
  - `modal_id_from_url`
  - `path_video_id`
  - `video_element_count`
  - `active_video_duration`
  - `detector_error`

## Verification

Run extension tests and then live retest on a real Douyin modal URL with `modal_id=...`.
