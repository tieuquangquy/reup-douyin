# Phase 6H Hardening Resume Safety Log

## Why hardening is needed

- Full Modal Auto-Harvester can stop mid-run because of captcha, navigation stalls, popup close, page reload, or backend flush issues.
- The operator must not lose already harvested modal metadata at item `10/49`, `20/49`, or `48/49`.
- Resume has to continue from exact `aweme_id` state, not restart blind.

## Hardening scope

- persist modal harvest state in extension local storage
- keep the harvest loop in the content script
- make flush incremental and idempotent
- stop safely on captcha/login/security wall
- preserve pending items on flush failure
- add explicit resume action

## Expected behavior

- progress saved after each harvested item
- flush every `N` items and again on stop
- resume skips already harvested `aweme_id`
- backend repeated flush of same `aweme_id` stays idempotent
- interrupted run remains operator-recoverable

## Status

- implementation complete

## Storage and resume mechanism

- content script remains the main harvest loop owner
- durable state is stored in `chrome.storage.local`
- storage key: `douyinFullModalHarvestState`
- state persists:
  - `harvested_aweme_ids`
  - `pending_items`
  - `flushed_aweme_ids`
  - `failed_items`
  - `stopped_reason`
  - progress counters

## Files changed

- `apps/extension-douyin-capture/src/chrome.d.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `docs/metadata-phase6H-hardening-resume-safety-log.md`
- `docs/metadata-phase6H-hardening-resume-safety-resume.md`
- `docs/metadata-phase6H-hardening-operator-guide.md`

## Tests run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`
- `cd apps/api && python -m unittest tests.test_capture_metadata_normalizer tests.test_douyin_extension_capture_service`
- `cd apps/api && python -m compileall src`

## Verification result

- progress is persisted through the controller save path
- flush failure preserves pending items
- resume skips already harvested `aweme_id`
- navigation timeout retries once and then stops safely
- repeated backend flush of the same `aweme_id` stays idempotent
