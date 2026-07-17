# One-shot Summary File Robustness Log

Date: 2026-04-29
Scope: API-only diagnostics file emission robustness

## Goal
Make temporary one-shot summary file emission reliable and observable so operators can always locate output after a real target capture.

## Root-cause check (pre-fix)
Inspected [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:703) and writer helpers near [`_targeted_aweme_one_shot_summary_path()`](apps/api/src/services/capture_inbox_service.py:1625).

Findings:
1. Writer **is called** only when a target aweme id is present via [`if source_video_external_id in TARGET_DEBUG_AWEME_IDS`](apps/api/src/services/capture_inbox_service.py:814).
2. Parent directory creation existed via [`output_path.parent.mkdir(parents=True, exist_ok=True)`](apps/api/src/services/capture_inbox_service.py:1631).
3. Path resolution already uses `Path(__file__)` and should resolve to `apps/api/tmp/...`.
4. Missing robustness/observability: there were **no explicit attempt/success/error logs** around file emission, so operators could not know if write was attempted, where exact absolute path was, or why it failed.

Exact root cause classification: **(4) write failure/behavior was not observable enough**, plus operational ambiguity because emission is conditional on target aweme IDs.

## Implemented fix
- Kept conditional behavior unchanged (target IDs only) in [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:814).
- Strengthened path resolution in [`_targeted_aweme_one_shot_summary_path()`](apps/api/src/services/capture_inbox_service.py:1625) using resolved absolute path.
- Added explicit write lifecycle logging in [`_write_targeted_aweme_one_shot_summary_file()`](apps/api/src/services/capture_inbox_service.py:1629):
  - `targeted_aweme_one_shot_write_attempt`
  - `targeted_aweme_one_shot_write_success`
  - `targeted_aweme_one_shot_write_error`
- Attempt log now includes:
  - `absolute_path`
  - `aweme_ids`
  - `parent_dir_existed_before`
- Success log includes:
  - `absolute_path`
  - `item_count`
- Error log includes:
  - `absolute_path`
  - `error_message`

## Verified path
Resolved stable absolute output path:
- `C:\Users\PC\Desktop\reup_douyin\apps\api\tmp\targeted_aweme_one_shot_summary.json`

## Verification commands
- [`python -m compileall apps/api/src/services/capture_inbox_service.py`](apps/api/src/services/capture_inbox_service.py)
- Path resolution check:
  - `python -c "from pathlib import Path; p=(Path('apps/api/src/services/capture_inbox_service.py').resolve().parents[2] / 'tmp' / 'targeted_aweme_one_shot_summary.json').resolve(); print(p)"`

## Files in scope
- [`apps/api/src/services/capture_inbox_service.py`](apps/api/src/services/capture_inbox_service.py)
- [`docs/one-shot-summary-file-robustness-log.md`](docs/one-shot-summary-file-robustness-log.md)
- [`docs/one-shot-summary-file-robustness-resume.md`](docs/one-shot-summary-file-robustness-resume.md)
