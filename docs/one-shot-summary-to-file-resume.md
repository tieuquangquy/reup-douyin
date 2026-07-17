# Resume — One-shot Summary to File

## Scope lock
Temporary diagnostics helper only. No metadata fix. No UI changes.

## Files in scope
- `apps/api/src/services/capture_inbox_service.py`
- `docs/one-shot-summary-to-file-log.md`
- `docs/one-shot-summary-to-file-resume.md`

## Output file
- `apps/api/tmp/targeted_aweme_one_shot_summary.json`

## Operator outcome
After one real `Capture current page`, operator can open one file and copy summaries for target failing IDs.

## What was implemented
- Backend writes aggregate file at [`apps/api/tmp/targeted_aweme_one_shot_summary.json`](apps/api/tmp/targeted_aweme_one_shot_summary.json).
- Writer source is [`_write_targeted_aweme_one_shot_summary_file()`](apps/api/src/services/capture_inbox_service.py:1620).
- Trigger point is targeted branch inside [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:702).

## Quick verify steps
1. Run one real capture flow that includes either target aweme id.
2. Open [`apps/api/tmp/targeted_aweme_one_shot_summary.json`](apps/api/tmp/targeted_aweme_one_shot_summary.json).
3. Confirm JSON contains:
   - `generated_at`
   - `capture_session_id`
   - `capture_id`
   - `items` (array of one-shot summaries for target IDs seen in that run)

## Build/syntax verification done
- [`python -m compileall apps/api/src/services/capture_inbox_service.py`](apps/api/src/services/capture_inbox_service.py) completed with exit code 0.
