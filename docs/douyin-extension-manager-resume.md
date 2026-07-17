# Douyin Extension Manager Resume

## Current Goal

Build a dedicated backend/web-app Extension Manager for the Douyin browser extension.

## Canonical Direction

Extension-based current-page capture is the primary Douyin collection path. The manager must reuse the current extension handshake, detect, capture, and download contracts rather than introducing a second downstream discovery architecture.

## Mandatory Docs

- `docs/douyin-extension-manager-log.md`
- `docs/douyin-extension-manager-resume.md`
- `docs/douyin-extension-manager-architecture.md`
- `docs/douyin-extension-manager-user-guide.md`

## Completed

- Re-read `AGENTS.md`.
- Audited extension package/build output.
- Audited backend setup/detect/capture endpoints.
- Audited existing setup UI.
- Audited version exposure and capture result shape.
- Chose manager route: `/ops/extensions/douyin`.
- Created mandatory manager docs before code changes.
- Added backend manager history schemas, service support, route support, and tests.
- Added `GET /douyin-extension/history`.
- Recorded handshake, detect, and capture success/failure events in manager history.
- Added the web manager route, page, API helpers, TypeScript contracts, navigation, breadcrumbs, i18n labels, and route-nav coverage.
- Verified focused backend tests, web typecheck, route-nav tests, and the web test suite.

## Relevant Existing Files

### Backend

- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_setup_service.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/tests/test_douyin_extension_setup_service.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`

### Extension

- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`

### Web

- `apps/web/src/components/douyin-extension-setup/DouyinExtensionSetupPage.tsx`
- `apps/web/src/types/douyin-extension-setup.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/test/route-nav.test.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

## Implemented Backend Work

- Added manager/history schemas to `apps/api/src/schemas/douyin_extension.py`.
- Extended `DouyinExtensionSetupService` with lightweight process-local manager history.
- Added `GET /douyin-extension/history`.
- Recorded detect and capture attempts in manager history from existing route handlers.
- Kept history safe and compact.
- Preserved existing canonical detect/capture processing in `DouyinExtensionCaptureService`.

## Implemented Web Work

- Added `apps/web/src/app/ops/extensions/douyin/page.tsx`.
- Added `apps/web/src/components/douyin-extension-manager/DouyinExtensionManagerPage.tsx`.
- Added `apps/web/src/types/douyin-extension-manager.ts` for manager/history/detect/capture payloads.
- Added API helpers for history, detect, and capture.
- Added nav/breadcrumb/i18n/route test coverage.

## Verification Completed

- `npm --workspace @reup-douyin/web run typecheck`
- `npx tsx src/test/route-nav.test.ts`
- `py -m unittest tests.test_douyin_extension_setup_service tests.test_douyin_extension_capture_service`
- `npm --workspace @reup-douyin/web run test`

## Privacy Guardrails

Do not send, log, or display:

- cookies
- auth tokens
- passwords
- authorization headers
- raw browser storage
- raw HTML
- browser profile paths
- private local absolute paths

## Resume Point

Implementation and verification are complete. If this work is resumed later, start from follow-up product refinements rather than core manager plumbing.
