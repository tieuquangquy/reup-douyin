# Douyin Current-Page Capture Resume

## Current objective

Refactor Douyin intake so the primary workflow is operator-assisted browser capture from the current visible page in the managed persistent browser profile.

The workflow is:

1. Operator opens/reopens the managed browser profile for a `DouyinAccountConnection`.
2. Operator logs in and solves any challenge manually in that same browser.
3. Operator navigates manually to the target Douyin page.
4. The app detects the current page type without navigating away.
5. The app captures/imports visible/current-page profile or video data.
6. Existing canonical ingest, candidate filtering, review board, and downstream systems continue unchanged.

## Required docs

Created before implementation:

- `docs/douyin-capture-current-page-log.md`
- `docs/douyin-capture-current-page-resume.md`
- `docs/douyin-capture-current-page-architecture.md`
- `docs/douyin-capture-current-page-user-guide.md`

## Audited files

Backend:

- `AGENTS.md`
- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/adapters/types.py`
- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/models/ingestion.py`
- `apps/api/src/services/candidate_service.py`

Frontend:

- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

## Key implementation constraints

- Keep `DouyinAccountConnection`.
- Keep one account mapped to one managed persistent browser profile.
- Do not create another downstream discovery pipeline.
- Reuse `SourceIngestService.ingest_profile(adapter_payload_json=...)`.
- Preserve canonical persistence:
  - `SourceProfile`
  - `SourceVideo`
  - `CrawlSession`
  - `VideoMetricSnapshot`
  - `VideoCandidate`
- Keep secrets out of logs, UI, and captured metadata.
- Do not auto-navigate before capture. Detection and capture must inspect the current visible page only.
- Treat login/challenge pages as explicit operator states, not failed background fetches.

## Implementation checklist

- [x] Audit existing Douyin browser/intake/ingest flow.
- [x] Create mandatory docs first.
- [x] Define page taxonomy and planned architecture.
- [ ] Add backend current-page detection models.
- [ ] Add backend current-page capture/import service.
- [ ] Add backend account routes for detect/capture.
- [ ] Add tests for classification and import behavior.
- [ ] Add frontend types/API helpers.
- [ ] Add minimal operator UI actions.
- [ ] Run backend tests.
- [ ] Run frontend typecheck.
- [ ] Update docs with verification results.

## Expected new files or touched files

Likely backend additions:

- `apps/api/src/services/douyin_current_page_capture_service.py`
- `apps/api/tests/test_douyin_current_page_capture_service.py`

Likely backend edits:

- `apps/api/src/services/douyin_browser_context_registry.py`
- `apps/api/src/schemas/douyin_accounts.py`
- `apps/api/src/api/routes/douyin_accounts.py`
- `apps/api/src/services/intake_discovery_service.py` if ready-check output is simplified to current-page status.
- `apps/api/src/schemas/intake.py` if ready-check/capture response needs current-page fields.

Likely frontend edits:

- `apps/web/src/types/douyin-accounts.ts`
- `apps/web/src/types/intake.ts` if intake response includes current-page capture fields.
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

## Current design notes

- Detection response should include:
  - account id,
  - runtime status,
  - page type,
  - current page URL,
  - title,
  - supported flag,
  - capture readiness,
  - visible video link count,
  - recommended operator action.
- Capture response should include:
  - page classification,
  - submitted/resolved profile URL,
  - crawl session id,
  - source profile id,
  - videos discovered/created/updated,
  - candidates total/matched/rejected,
  - next route to review board.
- Unsupported/login/challenge pages should not import.
- `video_detail_page` may import a minimal one-video payload if a profile identity can be resolved; otherwise it should be detected but capture-blocked until profile context is available.

## Resume point

Implementation should start by adding the backend current-page service and schemas, then tests, then routes, then frontend typing/UI.
