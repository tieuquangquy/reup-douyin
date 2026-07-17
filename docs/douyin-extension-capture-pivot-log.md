# Douyin Extension Capture Pivot Log

## Purpose

This log tracks the pivot from Playwright-managed Douyin collection as the primary path to a browser-extension current-tab capture model that uses the operator's real Chrome or Edge session.

## Non-negotiable Direction

- Primary Douyin collection is extension-based current-tab capture.
- The operator logs in, solves challenges, and navigates manually in the real browser.
- The extension detects and captures the current visible Douyin page.
- The backend imports extension payloads into the existing canonical ingest and review pipeline.
- Playwright-managed browser/runtime flows remain only for legacy/debug use.
- No raw cookies, auth tokens, credentials, or private browser profile paths are captured, logged, or shown in UI.

## Required Primary Operator Flow

1. Install the Douyin capture browser extension.
2. Open Douyin in the operator's real Chrome or Edge session.
3. Login and solve any Douyin challenge manually.
4. Open the desired profile, feed, or video page manually.
5. Click Detect current page in the extension popup.
6. Click Capture current page.
7. Send the safe capture payload to the local backend.
8. Import the payload through the canonical downstream pipeline.

## Audit Notes

### Repository Rules Read

`AGENTS.md` was read before implementation. Relevant rules for this pivot:

- Read relevant files before editing.
- Plan first for non-trivial changes.
- Keep changes scoped to the requested step.
- Prefer correctness, maintainability, and observability.
- Do not add dependencies unless necessary.
- Keep app boundaries clean.
- Do not leak secrets.
- Add focused tests when adding API contracts, schemas, or boundary behavior.

### Reusable Backend Pipeline

The existing canonical ingest path is reused as the only downstream persistence architecture for extension captures.

Audited files:

- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/src/models/ingestion.py`
- `apps/api/src/services/candidate_service.py`
- `apps/api/src/services/douyin_current_page_capture_service.py`
- `apps/api/src/services/intake_discovery_service.py`

Key finding:

- `SourceIngestService.ingest_profile(...)` already accepts `adapter_payload_json`.
- When the adapter is `DouyinProfileAdapter`, it calls `DouyinProfileAdapter.normalize_fetch_payload(profile_url, adapter_payload_json)`.
- `DouyinProfileAdapter.normalize_fetch_payload(...)` accepts a raw payload shaped as:
  - `profile` or `user`
  - `videos` or `aweme_list`
  - optional `metadata`
- This means extension captures can be mapped into the existing adapter input shape without creating a second downstream discovery architecture.

### Canonical Entities Preserved

Extension import reuses:

- `SourceProfile`
- `SourceVideo`
- `CrawlSession`
- `VideoMetricSnapshot`
- `VideoCandidate`

Existing dedupe behavior remains useful:

- `SourceProfile` is unique by platform plus external profile id.
- `SourceVideo` is unique by platform plus external video id.
- Metric snapshots are unique per video and crawl session.
- Repeated extension captures can create new crawl sessions, update existing videos, and add fresh metric snapshots.

### Candidate Pipeline

Extension capture calls `CandidateEvaluationService.apply(...)` after canonical ingest so imported videos become review candidates through `VideoCandidate`, not through a new review pipeline.

## Implemented Files

Docs:

- `docs/douyin-extension-capture-pivot-log.md`
- `docs/douyin-extension-capture-pivot-resume.md`
- `docs/douyin-extension-capture-pivot-architecture.md`
- `docs/douyin-extension-capture-pivot-user-guide.md`

Backend:

- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/main.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`

Extension:

- `apps/extension-douyin-capture/package.json`
- `apps/extension-douyin-capture/tsconfig.json`
- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/scripts/copy-static.mjs`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/chrome.d.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`

Web and workspace:

- `apps/web/src/components/douyin-accounts/DouyinAccountsPage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `package.json`
- `package-lock.json`

## Implementation Status

Completed:

- Mandatory docs were created before code.
- Backend Pydantic contracts were added for extension page detection and capture.
- Backend service validates payload safety, classifies pages, maps extension captures into the canonical Douyin adapter payload, calls canonical ingest, and runs candidate evaluation.
- FastAPI routes were registered at:
  - `POST /douyin-extension/detect-page`
  - `POST /douyin-extension/capture-current-page`
- MV3 extension workspace was added for Chrome/Edge current-tab detection, visible DOM extraction, popup controls, and backend submission.
- Web Douyin account/intake copy now presents extension capture as the primary path and labels managed runtime controls as legacy/debug.
- Focused backend and extension tests were added.
- Workspace lockfile was updated with `npm install`.

## Verification

Commands run:

- `npm install` — passed; updated workspace lockfile. NPM reported 2 audit findings already present after install output: 1 moderate and 1 critical.
- `npm run extension:test` — passed.
- `npm run extension:build` — passed.
- `npm run typecheck` — passed for the web workspace.
- `py -m unittest apps.api.tests.test_douyin_extension_capture_service` from repo root — failed because Python could not import `src` from the root working directory.
- `py -m unittest tests.test_douyin_extension_capture_service` from `apps/api` — passed, 5 tests.

## Known Follow-up

- Full repository smoke tests were not run in this focused pivot pass.
- The NPM audit output should be reviewed separately; no automatic `npm audit fix --force` was run because it may introduce broad dependency changes.
- Extension extraction is intentionally conservative and visible-DOM based. Real Douyin pages may require iterative selector hardening after operator testing.

## Explicit Non-goals

- No Douyin crawler implementation.
- No automated challenge solving.
- No automated publishing.
- No raw cookie/session export through extension capture.
- No new database schema.
- No replacement of the existing canonical source/candidate models.
- No broad rewrite of account health, worker orchestration, or unrelated UI modules.
