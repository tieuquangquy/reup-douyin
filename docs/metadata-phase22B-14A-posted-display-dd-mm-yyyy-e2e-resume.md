# Phase 22B-14A Posted display dd/mm/yyyy E2E Resume

## Completed
- Audited the end-to-end posted metadata flow across extension, backend ingest, backend response hydration, and web Tile Gallery display.
- Confirmed new finalized ingest was already correct in [`_apply_modal_harvest_to_item()`](../apps/api/src/services/douyin_extension_capture_service.py:1154).
- Added backend lazy normalization for legacy saved items in [`apps/api/src/schemas/capture_inbox.py`](../apps/api/src/schemas/capture_inbox.py).
- Aligned the web contract in [`apps/web/src/types/capture-inbox.ts`](../apps/web/src/types/capture-inbox.ts).
- Updated focused web resolver fixtures in [`apps/web/src/test/capture-inbox-canonical.test.ts`](../apps/web/src/test/capture-inbox-canonical.test.ts).
- Added focused backend regression coverage in [`apps/api/tests/test_capture_inbox_metadata_status.py`](../apps/api/tests/test_capture_inbox_metadata_status.py).

## Key Findings
- The conversion was not lost in the extension parser.
- The conversion was not lost in finalized backend ingest for new modal harvest items.
- The remaining bug was legacy response hydration: old rows containing only raw `posted_text` like `4天前` or `昨天` had no lazy backfill to `posted_at` / `posted_display`.
- Because [`resolvePosted()`](../apps/web/src/lib/captureInboxCanonical.ts:45) already uses `posted_at` before `posted_text`, fixing backend response hydration was sufficient to correct Tile Gallery output without redesigning the frontend component.

## Validation Status
- Passed: [`python -m unittest tests.test_capture_inbox_metadata_status`](../apps/api/tests/test_capture_inbox_metadata_status.py)
- Passed: [`npx tsx src/test/capture-inbox-canonical.test.ts`](../apps/web/src/test/capture-inbox-canonical.test.ts)
- Unrelated workspace script issue remains in the broader web test entrypoint and was observed during [`npm test`](../apps/web/package.json).

## Files Touched In Phase 22B-14A
- [`apps/api/src/schemas/capture_inbox.py`](../apps/api/src/schemas/capture_inbox.py)
- [`apps/api/tests/test_capture_inbox_metadata_status.py`](../apps/api/tests/test_capture_inbox_metadata_status.py)
- [`apps/web/src/types/capture-inbox.ts`](../apps/web/src/types/capture-inbox.ts)
- [`apps/web/src/test/capture-inbox-canonical.test.ts`](../apps/web/src/test/capture-inbox-canonical.test.ts)
- [`docs/metadata-phase22B-14A-posted-display-dd-mm-yyyy-e2e-log.md`](../docs/metadata-phase22B-14A-posted-display-dd-mm-yyyy-e2e-log.md)
- [`docs/metadata-phase22B-14A-posted-display-dd-mm-yyyy-e2e-resume.md`](../docs/metadata-phase22B-14A-posted-display-dd-mm-yyyy-e2e-resume.md)
