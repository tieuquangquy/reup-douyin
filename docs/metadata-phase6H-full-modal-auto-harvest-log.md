# Phase 6H Full Modal Auto-Harvest Log

## Why this strategy

- Grid/profile capture already finds the right `aweme_id` set.
- Backend browser hydration and network replay are operationally vulnerable to Douyin block/captcha surfaces.
- The opened video modal is the one place where current-video detail metadata is reliably visible in the operator's real browser session.
- The operator wants full-session coverage without manually opening 49 videos one by one.

## Chosen workflow

1. Operator opens a Douyin profile page.
2. Operator opens the first video modal manually.
3. Extension starts a controlled modal harvester.
4. Extension extracts current-video DOM-detail metrics.
5. Extension moves to the next modal item and waits for `aweme_id` change.
6. Extension batches harvested evidence to the backend every few items and once at the end.
7. Backend updates existing Capture Inbox items by exact `aweme_id` and reuses `CaptureMetadataNormalizer`.

## Expected full-coverage fields

- `duration_seconds`
- `duration_text`
- `like_count`
- `comment_count`
- `favorite_count` / `collect_count`
- `share_count`
- `posted_text`

## Not guaranteed

- `view_count`
- `raw_detail_aweme`

Those remain absent unless explicitly present in trustworthy modal/page state.

## Safety behavior

- stop button
- in-memory progress state
- exact `aweme_id` dedupe
- periodic flush
- captcha/login wall detection
- no fake `view_count`
- no backend browser crawling

## Scope

- extension popup/content script only
- backend batch evidence update only
- narrow normalizer alignment for `raw_dom_detail_metrics`

## Status

- implementation complete

## Files changed

- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `apps/extension-douyin-capture/src/modalHarvest.test.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/package.json`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/services/capture_metadata_normalizer.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_capture_metadata_normalizer.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`

## Tests run

- `cd apps/extension-douyin-capture && npm run typecheck`
- `cd apps/extension-douyin-capture && npm test`
- `cd apps/api && python -m unittest tests.test_capture_metadata_normalizer tests.test_douyin_extension_capture_service`
- `cd apps/api && python -m compileall src`

## Verification result

- extension modal helper tests passed
- extension build passed
- backend focused tests passed
- backend compile check passed
- no backend browser crawling path was introduced
- no fake `view_count` path was introduced
