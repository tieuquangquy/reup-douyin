# One-shot Summary to File Log

Date: 2026-04-29
Scope: temporary diagnostics convenience only (API-side file output)

## Goal
Persist existing `targeted_aweme_one_shot_summary` aggregation to a predictable JSON file after real capture flow, so operators can copy evidence without log hunting.

## Target IDs
- `7489123456789012346`
- `7489123456789012347`

## Planned output path
- `apps/api/tmp/targeted_aweme_one_shot_summary.json`

## Required behavior
1. Reuse existing one-shot summary payload generated in backend `_build_item` path.
2. Keep normal logs unchanged.
3. Also write/update one predictable JSON file.
4. Include only present target IDs for current run.
5. Keep valid, pretty JSON for easy copy.

## Implemented (API only)
- Added path helper and writer in [`_write_targeted_aweme_one_shot_summary_file()`](apps/api/src/services/capture_inbox_service.py:1620).
- Persisted run-local aggregate in session result summary under `targeted_aweme_one_shot_summaries`.
- On each target item in [`CaptureInboxService._build_item()`](apps/api/src/services/capture_inbox_service.py:702), backend now:
  - computes `one_shot_summary`
  - logs existing event `targeted_aweme_one_shot_summary`
  - updates aggregate map by `aweme_id`
  - writes `apps/api/tmp/targeted_aweme_one_shot_summary.json`

## Verification
- Syntax check passed via [`python -m compileall`](apps/api/src/services/capture_inbox_service.py).
