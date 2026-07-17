# Phase 6H Hardening Operator Guide

## What changed

- modal harvest progress is now stored in extension local storage
- harvest can be resumed after captcha, popup close, navigation timeout, or flush failure
- already harvested `aweme_id` values are skipped on resume
- repeated flush of the same `aweme_id` is idempotent on the backend

## Captcha handling

1. harvester stops immediately
2. already harvested pending items are flushed if possible
3. stop reason becomes `captcha_or_login_wall_detected`
4. operator completes captcha/login manually
5. operator reopens the modal if needed
6. operator clicks `Resume Full Modal Harvest`

## Resume behavior

- progress is restored from `chrome.storage.local`
- storage key: `douyinFullModalHarvestState`
- harvested and flushed `aweme_id` state is preserved
- pending items remain pending if the previous flush failed
- duplicate `aweme_id` is skipped

## Flush behavior

- flush every `5` items by default
- flush on stop
- flush on captcha stop if pending items exist
- flush failure keeps pending data in extension local storage

## If the run stops at item 10/49 or 30/49

1. open the extension popup
2. click `Show Harvest Progress`
3. check `stopped_reason` and `pending_count`
4. if captcha/login was the cause, resolve it manually first
5. click `Resume Full Modal Harvest`
6. if needed, click `Flush Harvested Metadata`

## Live resilience test steps

1. build and reload the extension
2. open a Douyin profile page
3. open the first video modal
4. click `Start Full Modal Harvest`
5. let it run for a few videos
6. test one interruption:
   - close the popup
   - or stop manually
   - or reload the page after checking that progress was already saved
7. reopen the modal if needed
8. click `Show Harvest Progress`
9. click `Resume Full Modal Harvest`
10. click `Flush Harvested Metadata`
11. run:

```powershell
cd apps/api
python tests/metadata_phase5a_real_live_audit.py
```

## Status fields to watch

- `harvested_count`
- `flushed_count`
- `pending_count`
- `duplicate_count`
- `failed_count`
- `current_aweme_id`
- `stopped_reason`
- `last_error`
- `can_resume`
