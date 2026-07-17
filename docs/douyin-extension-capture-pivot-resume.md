# Douyin Extension Capture Pivot Resume

## Current Goal

Pivot Douyin collection so the primary path is a browser extension that captures the operator's current Douyin tab from their real Chrome or Edge session and sends a safe payload to the local backend.

## Required Primary Flow

1. Install the browser extension.
2. Open Douyin in real Chrome or Edge.
3. Login and solve challenges manually.
4. Navigate to the desired profile, feed, or video page manually.
5. Detect the current page in the extension popup.
6. Capture the current page in the extension popup.
7. Send the safe payload to the backend.
8. Import into the canonical source ingest and candidate review pipeline.

## Completed

- Read `AGENTS.md` and confirmed repository rules and boundaries.
- Audited the current backend ingest path.
- Confirmed `SourceIngestService.ingest_profile(...)` can import adapter payloads through `DouyinProfileAdapter.normalize_fetch_payload(...)`.
- Confirmed canonical entities are reused:
  - `SourceProfile`
  - `SourceVideo`
  - `CrawlSession`
  - `VideoMetricSnapshot`
  - `VideoCandidate`
- Confirmed extension payload maps to the existing adapter raw shape:
  - `profile` or `user`
  - `videos` or `aweme_list`
  - `metadata`
- Created mandatory docs before code.
- Added backend schemas, service, routes, and main router registration.
- Added `apps/extension-douyin-capture` as an npm workspace with MV3 extension source, popup, content extraction, static copy script, and tests.
- Updated web UI copy so extension capture is primary and Playwright-managed runtime controls are legacy/debug.
- Added focused backend tests for extension detect/capture, canonical ingest mapping, challenge rejection, and secret-field rejection.
- Ran verification commands.

## Implemented Route Shape

- `POST /douyin-extension/detect-page`
- `POST /douyin-extension/capture-current-page`

These routes are local/dev friendly and do not expose storage, queue, database, or worker internals.

## Page Type Taxonomy

The implementation supports:

- `login_page`
- `challenge_page`
- `home_feed_page`
- `profile_page`
- `profile_feed_page`
- `video_detail_page`
- `unsupported_page`
- `unknown_page`

## Critical Design Decision

A second downstream discovery model was not introduced. The extension only changes how raw Douyin page data enters the system. Persistence, metric snapshots, filtering, scoring, and review candidates remain in the canonical backend pipeline.

## Safety Requirements Preserved

- Do not capture cookies, local storage tokens, request headers, account credentials, browser profile paths, or raw HTML dumps.
- Do not log secrets.
- Keep diagnostics small and operator-safe.
- Treat login, challenge solving, and navigation as manual operator tasks.

## Verification Status

Passed:

- `npm install`
- `npm run extension:test`
- `npm run extension:build`
- `npm run typecheck`
- `py -m unittest tests.test_douyin_extension_capture_service` from `apps/api`

Expected failed invocation:

- `py -m unittest apps.api.tests.test_douyin_extension_capture_service` from repo root failed with `ModuleNotFoundError: No module named 'src'` because API tests expect `apps/api` as the working directory.

Not run:

- Full repository smoke test.
- Full API test suite.

## Legacy Runtime Status

Existing Playwright-managed browser actions remain available only as legacy/debug paths. They are not presented as the primary Douyin collection path in the main operator workflow.

## Follow-up Notes

- `npm install` updated `package-lock.json` and reported 2 audit findings. No forced audit fix was applied.
- Real Douyin UI changes may require selector hardening in `apps/extension-douyin-capture/src/extractor.ts` after operator testing.
