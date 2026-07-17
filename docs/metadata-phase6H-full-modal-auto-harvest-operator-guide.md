# Phase 6H Full Modal Auto-Harvest Operator Guide

## Operator workflow

1. Build and reload the extension.
2. Open a Douyin profile page in the real browser.
3. Click the first video manually so the video modal is open.
4. Open the extension popup.
5. Start Full Modal Harvest.
6. Wait for the run to finish or stop.
7. Flush any remaining harvested metadata.
8. Run the live audit script.

Popup actions added:

- `Start Full Modal Harvest`
- `Stop Full Modal Harvest`
- `Flush Harvested Metadata`
- `Show Harvest Progress`

## What the harvester collects

- duration from active video element or modal timeline
- like count
- comment count
- favorite / collect count
- share count
- posted text

Backend ingest path:

- `POST /douyin-extension/full-modal-harvest`
- matches existing Capture Inbox items by exact `aweme_id`
- persists `raw_dom_detail_metrics`
- merges `raw_evidence_summary`
- reuses `CaptureMetadataNormalizer`

## Why view count is not guaranteed

- modal UI does not consistently expose trustworthy view count
- this phase will not invent it from arbitrary page numbers
- view count is only accepted when explicitly present in trustworthy state

## Safety / stop behavior

- stops on captcha/login/security wall
- stops when no next video is available
- stops at configured max items
- operator can stop manually
- flush happens periodically and again at the end

## Live test steps

```powershell
cd apps/extension-douyin-capture
npm run build
```

- reload unpacked extension
- open Douyin profile
- click first video
- run Full Modal Harvest with `max_items=49`
- flush harvested metadata

Then:

```powershell
cd apps/api
python tests/metadata_phase5a_real_live_audit.py
```

## Expected live result

- `duration_seconds` coverage increases
- `like_count` coverage increases
- `comment_count` coverage increases
- `share_count` coverage increases
- `processing_fit_status = captured` increases
- `performance_status = captured` increases

## Verification run

- `npm run typecheck`
- `npm test`
- `python -m unittest tests.test_capture_metadata_normalizer tests.test_douyin_extension_capture_service`
- `python -m compileall src`
