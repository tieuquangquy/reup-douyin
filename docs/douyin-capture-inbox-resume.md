# Douyin Capture Inbox Resume

## Current Goal

Implement Capture Sessions / Capture Inbox / Enrichment / Promotion-to-Review for Douyin browser-extension captures.

## Current Architecture Direction

Raw extension capture must stage data first. Canonical downstream entities stay unchanged and are reached only through promotion:

1. Capture Session receives raw payload.
2. Captured Items persist raw rows.
3. Enrichment normalizes identity, URLs, statistics, duplicate status, and preview readiness.
4. Capture Inbox exposes manual inspection/actions.
5. Promotion sends ready items into canonical source ingest and candidate evaluation.
6. Review Board only sees promoted `VideoCandidate` rows.

## Files Expected To Change

### API

- `apps/api/src/enums/__init__.py`
- `apps/api/src/models/capture_inbox.py`
- `apps/api/src/models/__init__.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/api/routes/capture_inbox.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/main.py`
- `apps/api/alembic/versions/0021_douyin_capture_inbox.py`
- API tests near `apps/api/tests/test_douyin_extension_capture_service.py` and new Capture Inbox tests.

### Web

- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/types/douyin-extension-manager.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/app/ops/extensions/douyin/capture-inbox/page.tsx`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- focused web source-level tests.

### Docs

- `docs/douyin-capture-inbox-architecture.md`
- `docs/douyin-capture-inbox-log.md`
- `docs/douyin-capture-inbox-resume.md`
- `docs/douyin-capture-inbox-user-guide.md`

## Verification Results

- `python -m pytest tests/test_douyin_extension_capture_service.py`: not available in the active Python environment because `pytest` is not installed.
- `python -m unittest tests.test_douyin_extension_capture_service`: passed, 6 tests.
- `npm run typecheck --workspace apps/web`: passed.
- `npx tsx apps/web/src/test/capture-inbox.test.ts && npx tsx apps/web/src/test/route-nav.test.ts && npx tsx apps/web/src/test/douyin-extension-manager-ux.test.ts`: passed.

## Implementation Notes

- Keep the extension endpoint URL stable.
- Keep the Review Board candidate API unchanged.
- Use JSONB for raw/enrichment summaries.
- Use local/default workspace when no workspace id is supplied.
- Treat unknown fields honestly in the UI instead of inventing values.
