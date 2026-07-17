# Douyin Capture 500 Hardening Resume

## Current objective

Harden the Douyin extension `capture_current_page` backend path so active-tab captures never fail as a generic HTTP 500 for malformed or partially incomplete page data.

## Required behavior

- Create a `CaptureSession` before item processing.
- Stage as many items as possible.
- Record per-item malformed/partial failures on `CapturedItem` rows or session diagnostics.
- Return structured counts and stage diagnostics.
- Reserve HTTP 500 for true system failures only.
- Keep canonical downstream entities unchanged and reachable only through Capture Inbox promotion.

## Files expected to change

- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/web/src/types/douyin-extension-manager.ts`
- `apps/web/src/components/douyin-extension-manager/DouyinExtensionManagerPage.tsx`
- `apps/web/src/lib/api.ts` if structured error formatting needs extension
- `apps/web/src/test/douyin-extension-manager-ux.test.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupActions.ts` if popup error projection needs richer categories
- `apps/extension-douyin-capture/src/popupActions.test.ts` or `popupTransport.test.ts`

## Audit state

Read:

- `AGENTS.md`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/douyin-extension-manager.ts`
- `apps/web/src/components/douyin-extension-manager/DouyinExtensionManagerPage.tsx`
- `apps/web/src/test/douyin-extension-manager-ux.test.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupActions.ts`
- `apps/extension-douyin-capture/src/popupActions.test.ts`
- `apps/extension-douyin-capture/src/popupTransport.test.ts`

## Resolved risks

- `CaptureInboxService.stage_extension_capture` now commits the `CaptureSession` before item processing, so ordinary item defects do not roll back the session.
- Per-item normalization and persist paths now produce failed item diagnostics where possible.
- Backend capture response now includes explicit stage, warnings, failure summaries, and count fields for partial success.
- Web manager and popup projection now show backend stage, warning, diagnostics, submitted/staged/failed counts, and structured backend error detail.
- True system failures from the staging service are not converted into partial successes.

## Verification completed

- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`: passed.
- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`: passed.
- `npm --workspace @reup-douyin/web test`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture test`: passed.
