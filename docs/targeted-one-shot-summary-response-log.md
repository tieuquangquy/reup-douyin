# Targeted One-shot Summary Response Log

Date: 2026-04-29
Scope: diagnostics convenience only (surface targeted summary in capture response)

## Goal
Expose combined targeted one-shot summary in an operator-easy copy location immediately after one real capture request, without relying on backend file lookup.

## Target IDs
- `7489123456789012346`
- `7489123456789012347`

## Surfaced location (implemented)
Primary location: API response body for `POST /douyin-extension/capture-current-page` via field:
- `targeted_aweme_one_shot_summary.items`

Implementation points:
- Response assembly in [`DouyinExtensionCaptureService.capture_current_page()`](apps/api/src/services/douyin_extension_capture_service.py:182).
- Response dataclass field in [`DouyinExtensionCaptureSummary`](apps/api/src/services/douyin_extension_capture_service.py:76).
- Response schema field in [`DouyinExtensionCaptureResponse`](apps/api/src/schemas/douyin_extension.py:236).

## Planned output shape
```json
{
  "targeted_aweme_one_shot_summary": {
    "items": [
      {
        "aweme_id": "7489123456789012346",
        "checkpoint1": {},
        "checkpoint2": {},
        "checkpoint3": {},
        "first_missing_stage": "...",
        "likely_next_fix_boundary": "..."
      }
    ]
  }
}
```

Only include target IDs actually present in that capture.

## Verification result
- Contract build check passed:
  - [`python -m compileall apps/api/src/services/douyin_extension_capture_service.py apps/api/src/schemas/douyin_extension.py`](apps/api/src/services/douyin_extension_capture_service.py:1)
- Aggregation source reused from session result summary key `targeted_aweme_one_shot_summaries`.
- No extension or frontend behavior changes were required for this surfacing.
