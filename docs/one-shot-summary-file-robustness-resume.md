# Resume — One-shot Summary File Robustness

## Scope lock
Diagnostics helper robustness only.
No metadata extraction fix.
No extension/frontend changes.

## Target output
- [`apps/api/tmp/targeted_aweme_one_shot_summary.json`](apps/api/tmp/targeted_aweme_one_shot_summary.json)

## Required behavior
After a real capture that includes at least one target aweme id, backend must:
1. Ensure parent `tmp` directory exists.
2. Write JSON to stable absolute path.
3. Log write attempt path/context.
4. Log explicit success or explicit error.

## Root-cause summary (pre-fix)
- Emission is conditional in [`_build_item()`](apps/api/src/services/capture_inbox_service.py:814).
- Path/parent creation code exists but lacked explicit write lifecycle observability.
- Operators could not immediately confirm write attempt/success/failure location.

## Logging markers added
- [`targeted_aweme_one_shot_write_attempt`](apps/api/src/services/capture_inbox_service.py:1635)
- [`targeted_aweme_one_shot_write_success`](apps/api/src/services/capture_inbox_service.py:1655)
- [`targeted_aweme_one_shot_write_error`](apps/api/src/services/capture_inbox_service.py:1665)

## Absolute path logic
- Writer path is computed by [`_targeted_aweme_one_shot_summary_path()`](apps/api/src/services/capture_inbox_service.py:1625).
- Effective absolute path:
  - `C:\Users\PC\Desktop\reup_douyin\apps\api\tmp\targeted_aweme_one_shot_summary.json`

## Operator steps to generate and find file
1. Run backend stack with [`npm run dev`](package.json:12).
2. Perform one real `Capture current page` that includes at least one target aweme id.
3. Open [`apps/api/tmp/targeted_aweme_one_shot_summary.json`](apps/api/tmp/targeted_aweme_one_shot_summary.json).
4. If file still not present, check backend logs for:
   - `targeted_aweme_one_shot_write_attempt`
   - `targeted_aweme_one_shot_write_success`
   - `targeted_aweme_one_shot_write_error`

## Verification checklist
- Confirm absolute output path is deterministic from [`Path(__file__)`](apps/api/src/services/capture_inbox_service.py:1625).
- Confirm parent directory creation is attempted with `mkdir(parents=True, exist_ok=True)` in [`_write_targeted_aweme_one_shot_summary_file()`](apps/api/src/services/capture_inbox_service.py:1644).
- Confirm write attempt log includes absolute path + aweme ids + parent dir existence flag.
- Confirm success log includes absolute path + item count.
- Confirm error log includes absolute path + exception message.
- Confirm JSON shape remains unchanged and includes only present target IDs.
