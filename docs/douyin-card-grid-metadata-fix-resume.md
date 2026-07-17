# Douyin Card Grid Metadata Fix Resume

## Current objective

Hard-fix visible Douyin profile-grid card capture so Capture Inbox consistently receives and renders truthful metadata for visible cards:

- canonical `thumbnail_url` from the real portrait poster/cover when available
- `duration_text` and `duration_seconds` when safely parsed
- `posted_text` and `posted_at` when safely parsed
- views, likes, and comments as raw text plus parsed numeric values when safe
- truthful `preview_status` / `preview_ready`
- truthful `media_status` / `media_ready`

## Files expected to change

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-card-grid-metadata-fix-log.md`
- `docs/douyin-card-grid-metadata-fix-resume.md`
- `docs/douyin-card-grid-metadata-fix-architecture.md`
- `docs/douyin-card-grid-metadata-fix-user-guide.md`

## Audit completed

Read and audited:

- `AGENTS.md`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`

## Key root causes to preserve for final report

1. Card root selection can be too narrow and can miss poster/overlay descendants.
2. Extension extraction does not emit duration/date text or top-level canonical counts.
3. Metric parsing relies on nearby labels and misses compact profile-grid overlays.
4. Backend request schema omits several canonical metadata fields requested by the product flow.
5. Backend stores stats in raw payload only, not in canonical metadata consumed predictably by UI.
6. Backend uses source URL as `preview_url` fallback, making preview readiness optimistic.
7. Backend uses source URL existence as media readiness, which is not the same as downloaded or playable local media.
8. Frontend chips do not use duration/post text fallbacks and depend on raw stats shape.

## Implementation completed

1. Updated extension types for canonical card-grid metadata.
2. Mirrored extraction helpers in both the content-script extractor and direct execute-script path.
3. Added robust scored card root selection and deterministic thumbnail candidate scoring.
4. Added safe duration, posted, and metric extraction from visible card text, link text, titles, and ARIA labels.
5. Extended backend schemas, normalization, persistence, and response hydration.
6. Adjusted readiness semantics so source links do not imply ready preview or ready media assets.
7. Updated frontend type and renderer helpers.
8. Added/updated extension, backend, and frontend tests.
9. Ran verification commands available in this local environment.
10. Updated the log, architecture note, resume, and user guide with implementation results.

## Verification commands run

- `npm --workspace @reup-douyin/extension-douyin-capture run test` — passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts` — passed.
- `npm --workspace @reup-douyin/web run typecheck` — passed.
- `python -m compileall apps/api/src/schemas/douyin_extension.py apps/api/src/schemas/capture_inbox.py apps/api/src/services/capture_inbox_service.py apps/api/src/services/douyin_extension_capture_service.py` — passed.
- `python -m pytest apps/api/tests/test_douyin_extension_capture_service.py -q` — blocked because the local Python environment reports `No module named pytest`.

## Current status

The hard-fix implementation is complete. The only verification gap is executing the backend pytest file in an environment with `pytest` installed; Python syntax compilation for the changed backend files passed.
