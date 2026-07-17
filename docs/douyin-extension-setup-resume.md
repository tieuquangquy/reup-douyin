# Douyin Extension Setup Resume

## Current Goal

Implement a complete Douyin Extension Setup page and backend setup flow for the browser-extension current-tab capture model.

The setup flow must include:

- Extension download/build access.
- Honest manual install guidance.
- Chrome and Edge extension-page shortcuts.
- Extension/backend connection status.
- Last seen / last ping time.
- Browser family if detectable.
- Extension version.
- Backend compatibility/version match status.
- Recommended next action.
- Check extension connection button.

## Canonical Direction

Extension-based current-tab capture is the primary Douyin collection model. The setup flow supports that model only. It must not re-promote Playwright-managed browser runtime flows.

Existing capture endpoints remain canonical:

- `POST /douyin-extension/detect-page`
- `POST /douyin-extension/capture-current-page`

The setup flow adds metadata-only connectivity and version checks.

## Completed Implementation

- Started with a short implementation plan.
- Re-read `AGENTS.md`.
- Audited current extension implementation.
- Audited current backend extension schemas/routes/services.
- Audited current web route/navigation/API patterns.
- Created the mandatory setup docs:
  - `docs/douyin-extension-setup-architecture.md`
  - `docs/douyin-extension-setup-log.md`
  - `docs/douyin-extension-setup-resume.md`
  - `docs/douyin-extension-setup-user-guide.md`
- Added backend setup schemas, service, routes, and focused tests.
- Added extension handshake/version reporting and popup setup status UI.
- Added the dedicated web setup route at `/setup/douyin-extension`.
- Added web API helpers, setup page component, nav/breadcrumb entries, i18n labels, and route coverage.
- Ran backend, extension, and web verification successfully.

## Mandatory Docs

Required docs for this task were created and updated:

- `docs/douyin-extension-setup-log.md`
- `docs/douyin-extension-setup-resume.md`
- `docs/douyin-extension-setup-architecture.md`
- `docs/douyin-extension-setup-user-guide.md`

## Key Audit Findings

### Extension

- Manifest path: `apps/extension-douyin-capture/public/manifest.json`.
- Current extension version: `0.1.0`.
- Popup path: `apps/extension-douyin-capture/src/popup.ts`.
- The popup now calls `POST /douyin-extension/handshake` on init and through the manual connection check button.
- The popup reports safe metadata only: install id, extension id when available, extension version, browser family, configured backend URL, and client timestamp.
- Chrome type declarations now include `chrome.runtime.getManifest` and `chrome.runtime.id`.

### Backend

- Existing schema file: `apps/api/src/schemas/douyin_extension.py`.
- Existing route file: `apps/api/src/api/routes/douyin_extension.py`.
- Existing capture service remains unchanged as the canonical capture implementation: `apps/api/src/services/douyin_extension_capture_service.py`.
- New setup service: `apps/api/src/services/douyin_extension_setup_service.py`.
- New setup endpoints:
  - `POST /douyin-extension/handshake`
  - `GET /douyin-extension/status`
  - `GET /douyin-extension/download`

### Web

- Setup route wrapper: `apps/web/src/app/setup/douyin-extension/page.tsx`.
- Setup page component: `apps/web/src/components/douyin-extension-setup/DouyinExtensionSetupPage.tsx`.
- Setup response types: `apps/web/src/types/douyin-extension-setup.ts`.
- Navigation and breadcrumbs live in `apps/web/src/lib/navigationConfig.ts`.
- API client functions live in `apps/web/src/lib/api.ts`.
- Route declarations are tested in `apps/web/src/test/route-nav.test.ts`.

## Implemented Files

### Backend

Added setup schemas to `apps/api/src/schemas/douyin_extension.py`:

- `DouyinExtensionSetupStatus` literal.
- `DouyinExtensionBrowserFamily` literal.
- `DouyinExtensionHandshakeRequest`.
- `DouyinExtensionStatusResponse`.

Added `apps/api/src/services/douyin_extension_setup_service.py`:

- Maintain process-local last handshake snapshot.
- Compute status.
- Compute version compatibility.
- Compute recommended next action.
- Create extension ZIP response from `apps/extension-douyin-capture/dist` if present.
- Return clear missing-build errors without private absolute paths.

Extended `apps/api/src/api/routes/douyin_extension.py`:

- `POST /douyin-extension/handshake`.
- `GET /douyin-extension/status`.
- `GET /douyin-extension/download`.

### Extension

Updated popup flow in `apps/extension-douyin-capture/src/popup.ts`, `apps/extension-douyin-capture/src/types.ts`, `apps/extension-douyin-capture/src/chrome.d.ts`, `apps/extension-douyin-capture/public/popup.html`, and `apps/extension-douyin-capture/public/popup.css` to:

- Generate/persist `install_id`.
- Read version using `chrome.runtime.getManifest().version`.
- Read extension id using `chrome.runtime.id` when available.
- Infer browser family from user agent.
- Send `POST /douyin-extension/handshake` during popup init and via a manual status/check action.
- Display backend compatibility summary in popup.

### Web

Added:

- `apps/web/src/app/setup/douyin-extension/page.tsx`.
- `apps/web/src/components/douyin-extension-setup/DouyinExtensionSetupPage.tsx`.
- `apps/web/src/types/douyin-extension-setup.ts`.

Updated:

- `apps/web/src/lib/api.ts` with status fetcher.
- `apps/web/src/lib/navigationConfig.ts` with route/nav/breadcrumbs.
- `apps/web/src/lib/i18n/en.json` and `apps/web/src/lib/i18n/vi.json`.
- `apps/web/src/test/route-nav.test.ts` for route coverage.

## Status Model

The status model should include exactly these states:

- `not_installed_or_not_connected`
- `installed_not_connected`
- `connected`
- `version_mismatch`
- `backend_unreachable_from_extension`
- `stale_connection`

## Recommended Next Action Mapping

Suggested backend/web action values:

- `download_extension`
- `build_extension`
- `install_extension_manually`
- `open_extension_and_check_connection`
- `refresh_setup_page`
- `update_extension`
- `open_douyin_and_capture`
- `check_backend_url`

## Verification Completed

Completed commands:

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

## Privacy Guardrails

Do not send, log, or display:

- Cookies.
- Auth tokens.
- Passwords.
- Authorization headers.
- Raw browser storage.
- Raw HTML.
- Browser profile paths.
- Private local absolute paths.

## Resume Point

The setup implementation and verification are complete. If work resumes later, start from the implemented setup route `/setup/douyin-extension`, backend setup service `apps/api/src/services/douyin_extension_setup_service.py`, and extension popup handshake flow in `apps/extension-douyin-capture/src/popup.ts`.
