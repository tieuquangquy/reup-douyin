# Douyin Extension Setup Architecture

## Summary

The Douyin extension setup flow provides a first-class operator page for installing, checking, and troubleshooting the browser-extension current-tab capture model. The extension capture model remains the primary Douyin collection path. The setup flow does not replace capture endpoints and does not introduce a second ingest pipeline.

Implemented operator route: `/setup/douyin-extension`.

The setup flow helps the operator:

- Download or locate the unpacked extension build.
- Open Chrome or Edge extension management pages.
- Follow honest manual install steps.
- Check whether the extension has reached the local backend.
- See extension version, backend expected version, browser family, last ping time, and recommended next action.

## Goals

- Provide a dedicated web setup page for Douyin extension installation and status.
- Add a lightweight backend handshake/status contract for extension connectivity.
- Add end-to-end version compatibility reporting.
- Expose a user-friendly download or build access route without claiming automatic install.
- Preserve the current extension capture endpoints as the canonical capture path.
- Avoid raw cookies, auth tokens, credentials, browser profile paths, or private local paths.

## Non-goals

- No automated Chrome/Edge extension installation.
- No Chrome Web Store or Edge Add-ons publishing flow.
- No crawler implementation.
- No automated login or challenge solving.
- No Playwright-managed runtime setup in the primary setup page.
- No database schema or durable multi-operator status store in this step.
- No changes to canonical ingest, scoring, or publishing workflows.

## Implementation Status

Completed implementation files:

- Backend schemas: `apps/api/src/schemas/douyin_extension.py`.
- Backend setup service: `apps/api/src/services/douyin_extension_setup_service.py`.
- Backend setup routes: `apps/api/src/api/routes/douyin_extension.py`.
- Backend setup tests: `apps/api/tests/test_douyin_extension_setup_service.py`.
- Extension popup UI and handshake: `apps/extension-douyin-capture/src/popup.ts`, `apps/extension-douyin-capture/src/types.ts`, `apps/extension-douyin-capture/src/chrome.d.ts`, `apps/extension-douyin-capture/public/popup.html`, and `apps/extension-douyin-capture/public/popup.css`.
- Web setup route: `apps/web/src/app/setup/douyin-extension/page.tsx`.
- Web setup page: `apps/web/src/components/douyin-extension-setup/DouyinExtensionSetupPage.tsx`.
- Web setup types: `apps/web/src/types/douyin-extension-setup.ts`.
- Web API helpers: `apps/web/src/lib/api.ts`.
- Web navigation, breadcrumbs, i18n, and route tests: `apps/web/src/lib/navigationConfig.ts`, `apps/web/src/lib/i18n/en.json`, `apps/web/src/lib/i18n/vi.json`, and `apps/web/src/test/route-nav.test.ts`.

## Existing Audit Findings

- The extension manifest declares version `0.1.0` and uses Manifest V3.
- The extension popup now calls `POST /douyin-extension/handshake`, `POST /douyin-extension/detect-page`, and `POST /douyin-extension/capture-current-page`.
- The backend route module exposes setup, detect, and capture endpoints.
- The backend schemas define setup status, handshake, page detection, and capture contracts.
- The web navigation exposes `/setup/douyin-extension` under the intake/operator setup flow.
- The extension static build copies files from `public` to `dist`; ZIP packaging uses Python standard library `zipfile` and does not add a dependency.

## Ownership Boundaries

### Extension

The extension owns browser-side version reporting and safe install/session identity. It may send:

- `install_id`: a client-generated opaque identifier stored in extension storage.
- `extension_id`: `chrome.runtime.id` when available and safe.
- `extension_version`: manifest version from `chrome.runtime.getManifest().version`.
- `browser_family`: `chrome`, `edge`, `chromium`, or `unknown` inferred from the user agent.
- `api_base_url`: local backend URL configured by the operator.
- `client_time`: current extension-side timestamp.

It must not send:

- Cookies.
- Authorization headers.
- Passwords.
- Browser profile paths.
- Local storage or session storage contents.
- Raw HTML.
- Credentials or tokens.

### API

The API owns validation, compatibility checks, and status summary. It should expose:

- `POST /douyin-extension/handshake`
- `GET /douyin-extension/status`
- `GET /douyin-extension/download`

The API may keep a local in-memory last-seen snapshot for Phase 1. This is acceptable because the setup status is local operator convenience state, not durable ingest state. A future SaaS implementation can replace it with a database-backed status table keyed by workspace/operator/install identity.

### Web

The web app owns operator setup guidance. It should provide a dedicated operator route such as `/setup/douyin-extension` and may link to it from Douyin account/intake surfaces.

The setup page should show:

- Download section.
- Manual install steps.
- Chrome and Edge extension page shortcuts.
- Connection status.
- Last seen / last ping time.
- Browser family if detectable.
- Extension version.
- Backend expected extension version.
- Compatibility status.
- Recommended next action.
- Check extension connection button.

## Status Model

The backend setup status model uses these states:

- `not_installed_or_not_connected`: no handshake has been received by this backend process.
- `installed_not_connected`: reserved for future browser-side setup signals when the extension exists but has not successfully reached the backend.
- `connected`: a recent handshake exists and the version is compatible.
- `version_mismatch`: a recent handshake exists but the extension version does not match the backend expected/supported version.
- `backend_unreachable_from_extension`: used by extension UI when a handshake request cannot reach the backend.
- `stale_connection`: a previous handshake exists, but it is older than the freshness threshold.

## Compatibility Model

The backend exposes:

- `backend_expected_extension_version`: the expected extension version for this codebase.
- `backend_supported_extension_versions`: a list of compatible extension versions.
- `compatible`: true when the extension version is supported.
- `version_status`: `compatible`, `version_mismatch`, or `unknown`.

For this implementation, expected and supported version should match the current extension manifest version unless the code intentionally supports multiple versions.

## Download Strategy

The setup page should offer a backend download endpoint for a ZIP when a built `dist` directory exists. If the built extension directory is missing, the backend should return a clear error that tells the operator to run the extension build command first.

No new dependency is required for ZIP creation because Python standard library `zipfile` can package the extension build directory on demand.

The UI and docs must clearly say that Chrome and Edge still require manual loading of the unpacked extension or ZIP contents through the browser extension page.

## Browser Shortcuts

The web page may expose links/buttons for:

- `chrome://extensions`
- `edge://extensions`

Browsers may block direct navigation to internal pages from normal web content. The UI must provide the text URLs for copy/paste as a fallback.

## Security and Privacy

The handshake is deliberately minimal and must remain metadata-only. It is safe to display in the web setup page because it does not include credentials or private browser state.

The backend should reject or ignore unexpected secret-like keys if the handshake contract later grows. The current implementation should keep the schema explicit and avoid arbitrary raw diagnostic payloads for setup.

## Observability

The backend should include stable fields in responses:

- status.
- last_seen_at.
- install_id.
- extension_version.
- browser_family.
- compatibility status.
- recommended_next_action.

Errors should be actionable, such as build missing or version mismatch. They must not reveal private local absolute paths.

## Verification

Completed verification:

- `py -m unittest tests.test_douyin_extension_setup_service` from `apps/api`: 6 tests passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run build` from repository root: passed.
- `npm --workspace @reup-douyin/web run typecheck` from repository root: passed.
- `npx tsx src/test/route-nav.test.ts` from `apps/web`: passed, 12 hrefs verified across 29 declared routes.
- `npm --workspace @reup-douyin/extension-douyin-capture run test` from repository root: passed.
- `py -m unittest tests.test_douyin_extension_setup_service tests.test_douyin_extension_capture_service` from `apps/api`: 11 tests passed.
- `npm --workspace @reup-douyin/web run test` from repository root: passed.

## Future SaaS-Ready Notes

When multi-user or distributed workers are introduced, extension status can move from process memory to durable storage keyed by workspace id, operator id, and install id. The public contract can remain stable if the current response shape avoids implementation details.
