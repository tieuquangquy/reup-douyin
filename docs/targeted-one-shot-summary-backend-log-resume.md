# Resume — Targeted One-shot Summary Backend Log

## Scope lock
API diagnostics convenience only.
No extension extraction changes.
No UI redesign.
No metadata fix.

## User outcome
After one real `Capture current page`, operator can search backend logs for one marker and copy one structured block.

## Exact marker
- `targeted_aweme_one_shot_summary_full`

## Copy steps
1. Start services with [`npm run dev`](package.json:12).
2. Run one real `Capture current page` with at least one target aweme id present.
3. In backend terminal logs, search for `targeted_aweme_one_shot_summary_full`.
4. Copy the pretty JSON block immediately below that marker.
5. Send the full `targeted_aweme_one_shot_summary` object for analysis.

## Verification checklist
- One log event per capture request when target summary has at least one item.
- Log includes full summary object.
- No log emitted when no target IDs are present.
- Existing response surfacing remains unchanged.

## Verification executed
- [`python -m compileall apps/api/src/services/douyin_extension_capture_service.py`](apps/api/src/services/douyin_extension_capture_service.py:1) completed successfully.
- No files outside `apps/api` and docs were changed for this task.
