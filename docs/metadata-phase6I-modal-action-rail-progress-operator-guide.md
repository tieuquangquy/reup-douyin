# Phase 6I Modal Action Rail + Progress Operator Guide

## Probe workflow

1. Open a Douyin profile page.
2. Click the first video so the modal is open.
3. Open the extension popup.
4. Click `Probe Current Modal Metrics`.
5. Review:
   - `aweme_id`
   - `duration_seconds`
   - `like_count`
   - `comment_count`
   - `favorite_count`
   - `share_count`
   - confidence / rejected reasons
   - action blocks found
   - ordered right-rail block diagnostics with rect/hints/counts

Do not start a full harvest if probe cannot find:
- `aweme_id`
- `duration_seconds`
- any action rail blocks

If probe shows partial action-rail coverage, the first `Start Full Modal Harvest` attempt will warn. Click it again only if you intentionally want to continue with those warnings.

Probe status meanings:
- `PASS`: duration + like + comment + favorite + share were all detected from the modal rail
- `WARN`: the rail was found but one or more counts are still missing
- `FAIL`: `aweme_id`, duration, or the action rail itself could not be detected

## Full harvest workflow

1. After a successful probe, click `Start Full Modal Harvest`.
2. Leave the modal open and let the harvester advance naturally.
3. Use `Show Harvest Progress` to inspect:
   - current index
   - target
   - current `aweme_id`
   - caption snippet
   - elapsed seconds
   - average seconds per item
   - ETA
   - last extracted metrics
   - recent items
4. Use `Stop Full Modal Harvest` or `Resume Full Modal Harvest` as needed.
5. Use `Flush Harvested Metadata` to push pending items immediately.

## Safety behavior

- captcha/login wall still stops safely
- no fake `view_count`
- ambiguous action blocks stay null with diagnostic reasons
- duration text conflicts stay diagnostic-only and do not override `duration_seconds`

## Live retest steps

1. `cd apps/extension-douyin-capture`
2. `npm run build`
3. Reload the unpacked extension.
4. Open Douyin profile and click the first video modal.
5. Run `Probe Current Modal Metrics`.
6. Confirm probe sees action blocks and duration.
7. Start full modal harvest.
8. Inspect progress/ETA after a few items.
9. Flush harvested metadata.
10. `cd ../api`
11. `python tests/metadata_phase5a_real_live_audit.py`

## Verification

- `npm run typecheck` passed
- `npm test` passed
- backend focused tests remained green
