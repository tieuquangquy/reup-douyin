# Douyin Extension Setup Log

## Purpose

This log tracks implementation of the dedicated Douyin extension setup flow for the browser-extension current-tab capture model.

The setup flow exists to help the local operator install the extension manually, confirm extension/backend connectivity, verify version compatibility, and understand the next action before using the canonical current-tab capture endpoints.

## Required Direction

- Extension-based current-tab capture remains the primary Douyin collection model.
- Existing capture endpoints remain canonical:
  - `POST /douyin-extension/detect-page`
  - `POST /douyin-extension/capture-current-page`
- New setup endpoints should support install guidance and connection/version status only.
- Browser extension installation remains manual in Chrome/Edge.
- No setup UI should claim one-click browser installation.
- No raw cookies, tokens, credentials, browser profile paths, auth headers, local storage, session storage, or raw HTML may be sent or displayed.

## Initial Implementation Plan

1. Re-read repository rules and audit existing extension/backend/web implementation.
2. Create mandatory setup docs first.
3. Add backend handshake, status, compatibility, and download access.
4. Add extension-side handshake/version reporting.
5. Add a dedicated web setup page and API client/types.
6. Add tests and run verification.
7. Update docs with final implementation and verification status.

## Audit Notes

### Repository Rules

`AGENTS.md` was read before implementation. Relevant constraints:

- Read relevant files before editing.
- Plan first for non-trivial changes.
- Keep changes scoped.
- Add tests for API contracts and boundary behavior.
- Keep web/API/extension boundaries clean.
- Avoid secrets and private local paths.
- Keep Windows as the primary Phase 1 runtime.

### Existing Extension

Audited files:

- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/chrome.d.ts`
- `apps/extension-douyin-capture/scripts/copy-static.mjs`

Findings:

- The manifest version is `0.1.0`.
- The popup stores `apiBaseUrl` and calls detect/capture endpoints.
- The extension does not currently perform a backend setup handshake.
- The extension does not currently display backend compatibility status.
- Static build output is `apps/extension-douyin-capture/dist` after build.

### Existing Backend

Audited files:

- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/services/douyin_extension_capture_service.py`
- `apps/api/src/main.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`

Findings:

- Existing backend supports detect and capture only.
- Existing schemas are focused on page detection and capture payloads.
- Existing extension capture service maps payloads into canonical ingest and candidate evaluation.
- No setup status store exists yet.
- No extension ZIP download route exists yet.

### Existing Web App

Audited files:

- `apps/web/src/app/accounts/douyin/page.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/test/route-nav.test.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

Findings:

- Route modules are thin wrappers around client components.
- Navigation and breadcrumbs are centralized in `navigationConfig.ts`.
- Route coverage is tested in `route-nav.test.ts`.
- There is no dedicated extension setup route yet.

## Planned Files

Docs:

- `docs/douyin-extension-setup-log.md`
- `docs/douyin-extension-setup-resume.md`
- `docs/douyin-extension-setup-architecture.md`
- `docs/douyin-extension-setup-user-guide.md`

Backend:

- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/services/douyin_extension_setup_service.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/tests/test_douyin_extension_setup_service.py`

Extension:

- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/chrome.d.ts`
- Possibly `apps/extension-douyin-capture/public/popup.html`
- Possibly `apps/extension-douyin-capture/public/popup.css`

Web:

- `apps/web/src/app/setup/douyin-extension/page.tsx`
- `apps/web/src/components/douyin-extension-setup/DouyinExtensionSetupPage.tsx`
- `apps/web/src/types/douyin-extension-setup.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/test/route-nav.test.ts`
- Possibly a focused setup state test.

## Status Model To Implement

- `not_installed_or_not_connected`
- `installed_not_connected`
- `connected`
- `version_mismatch`
- `backend_unreachable_from_extension`
- `stale_connection`

## Implementation Log

### 2026-04-26

- Started setup task with implementation plan.
- Re-read repository rules in `AGENTS.md`.
- Audited existing extension capture implementation.
- Created mandatory architecture doc.
- Created this setup log.
- Created mandatory resume and user guide docs.
- Added backend setup schemas, status model, handshake request, and status response.
- Added `apps/api/src/services/douyin_extension_setup_service.py` with process-local setup status, version compatibility, stale status, and ZIP packaging.
- Added backend routes:
  - `POST /douyin-extension/handshake`
  - `GET /douyin-extension/status`
  - `GET /douyin-extension/download`
- Added focused backend setup tests.
- Added extension popup connection-check UI and safe handshake reporting.
- Added extension manifest-version and extension-id declarations.
- Added web setup route `/setup/douyin-extension`.
- Added dedicated setup page with download, manual install steps, Chrome/Edge shortcuts, status details, version compatibility, last seen, and recommended next action.
- Added web API types/helpers and route/navigation/i18n coverage.

## Verification Log

Commands run successfully:

- `py -m unittest tests.test_douyin_extension_setup_service` from `apps/api`.
  - Result: 6 tests passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` from repository root.
  - Result: passed.
- `npm --workspace @reup-douyin/web run typecheck` from repository root.
  - Result: passed.
- `npx tsx src/test/route-nav.test.ts` from `apps/web`.
  - Result: passed, 12 hrefs verified across 29 declared routes.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` from repository root.
  - Result: passed.
- `py -m unittest tests.test_douyin_extension_setup_service tests.test_douyin_extension_capture_service` from `apps/api`.
  - Result: 11 tests passed.
- `npm --workspace @reup-douyin/web run test` from repository root.
  - Result: passed.

## Open Questions / Decisions

- Use in-memory status for Phase 1 setup connectivity because it is local convenience state and no database schema is requested in this step.
- Use Python standard library ZIP creation for download access to avoid new dependencies.
- Use `/setup/douyin-extension` as the dedicated operator setup route because setup is an operator onboarding flow, not an ops-console-only tool.
