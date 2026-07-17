# Targeted One-shot Summary Backend Log Log

Date: 2026-04-29
Scope: API-only diagnostics convenience logging

## Goal
Emit one full, copyable backend log block after each real capture request when at least one target aweme id is present.

## Target IDs
- `7489123456789012346`
- `7489123456789012347`

## Existing aggregation point
The combined response payload is already built in [`DouyinExtensionCaptureService.capture_current_page()`](apps/api/src/services/douyin_extension_capture_service.py:177) from `session.result_summary_json["targeted_aweme_one_shot_summaries"]`.

## Implemented marker
- `targeted_aweme_one_shot_summary_full`

## Implemented payload
The log event includes one full object in the backend terminal log message:

```json
{
  "targeted_aweme_one_shot_summary": {
    "items": []
  }
}
```

Only target IDs actually present in the run will be included.

## Implementation
- Added JSON formatting import in [`douyin_extension_capture_service.py`](apps/api/src/services/douyin_extension_capture_service.py:5).
- Emitted one copyable log block in [`DouyinExtensionCaptureService.capture_current_page()`](apps/api/src/services/douyin_extension_capture_service.py:177) after the combined summary payload is built.
- Existing capture response surfacing remains unchanged.

## Verification result
- Syntax check passed:
  - [`python -m compileall apps/api/src/services/douyin_extension_capture_service.py`](apps/api/src/services/douyin_extension_capture_service.py:1)
