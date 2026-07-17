# Phase 17AC Capture Inbox session items resume

## Completed
- Backend/service/schema response contract updated for finalized V2 writes to include item linkage and metadata status.
- Backend reconcile/commit behavior adjusted to keep session counters accurate on matched harvest paths.
- Extension V2 state trace now records item linkage and emits missing-item-id warning summary token.
- Web Capture Inbox now shows loaded/hidden diagnostics and explicit empty-state messaging for session-empty vs filter-empty.
- API/web/extension tests updated for new assertions.

## Remaining
- Run full verification commands and capture pass/fail output:
  - API unit tests + compileall
  - Web tests
  - Extension tests/typecheck/build
- Prepare final 9-section report with exact retest steps.

## Verification commands planned
- `cd apps/api && python -m unittest tests.test_douyin_extension_capture_service tests.test_capture_metadata_normalizer tests.test_capture_inbox_metadata_status`
- `cd apps/api && python -m compileall src scripts`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`
