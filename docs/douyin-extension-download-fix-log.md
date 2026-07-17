# Douyin Extension Download Fix Log

## Goal

Fix the Douyin Extension Manager download/install flow so the operator either receives a real downloadable extension ZIP or sees an honest manual Load unpacked workflow with no broken download link.

## Initial Audit

- `apps/web/src/lib/api.ts` exposes `getDouyinExtensionDownloadUrl()` as the stable web URL helper for `/douyin-extension/download`.
- `apps/api/src/api/routes/douyin_extension.py` already exposes `GET /douyin-extension/download`.
- `apps/api/src/services/douyin_extension_setup_service.py` already packages `apps/extension-douyin-capture/dist` into a ZIP on demand with Python standard library ZIP support.
- `apps/extension-douyin-capture/package.json` builds only the unpacked `dist` folder; it does not create a committed or persistent ZIP artifact.
- `apps/web/src/components/douyin-extension-manager/DouyinExtensionManagerPage.tsx` always renders a clickable Download extension link, even before status is loaded or when `download_available` is false.
- `apps/web/src/components/douyin-extension-setup/DouyinExtensionSetupPage.tsx` always renders a clickable Download ZIP link, even before status is loaded or when `download_available` is false.
- `DouyinExtensionSetupService.status()` currently treats any existing `dist` directory as downloadable, even if it is empty. `build_download_zip()` correctly rejects empty output, so status and route availability can disagree.

## Plan

1. Keep the existing on-demand ZIP packaging strategy because it already serves a real file when `dist` contains build files.
2. Tighten backend download availability so status only reports download available when the extension `dist` directory contains files.
3. Keep `GET /douyin-extension/download` as the stable route and return a ZIP only when build output exists.
4. Update setup and manager UIs so the Download action is only clickable when status explicitly reports `download_available`.
5. Show clear manual `npm run extension:build` and `apps/extension-douyin-capture/dist` Load unpacked steps when the ZIP is not available.
6. Add focused tests for backend availability and web text behavior.

## Non-Goals

- No Chrome Web Store publishing.
- No automatic browser extension installation.
- No unrelated extension capture, messaging, or backend capture changes.
- No new packaging dependencies.

## Implementation Notes

- Backend availability now uses the same packageability check as the download route: `download_available` is true only when `apps/extension-douyin-capture/dist` exists and contains at least one file.
- The existing backend ZIP route remains the stable artifact route. When build output is present, it returns `reup-douyin-extension-0.1.0.zip` with ZIP content.
- Added a shared web install-state helper so both setup surfaces render the same truthful states: loading, available, or unavailable.
- The Extension Manager and Extension Setup pages only render a clickable download link when status says a ZIP is available.
- When unavailable, the UI renders a disabled/status message and clear manual `Load unpacked` steps for `apps/extension-douyin-capture/dist`.
- Added backend tests for missing and empty build output, and added a focused web state test for the download UI contract.

## Verification

- Initial command failed because it was run from the repository root and the API tests import `src` relative to `apps/api`:
  - `python -m unittest apps.api.tests.test_douyin_extension_setup_service`
  - Result: failed with `ModuleNotFoundError: No module named 'src'`.
- Correct backend command:
  - `python -m unittest tests.test_douyin_extension_setup_service` from `apps/api`
  - Result: passed, 11 tests.
- Web tests:
  - `npm --workspace @reup-douyin/web run test`
  - Result: passed, including `douyin-extension install state tests passed`.
- Web typecheck:
  - `npm --workspace @reup-douyin/web run typecheck`
  - Result: passed.

## Re-Audit Verification

Re-audited after the repeated download-flow request. The current implementation still satisfies the requested truthful strategy without further code changes:

- `python -m unittest tests.test_douyin_extension_setup_service` from `apps/api`: passed, 11 tests.
- `npm --workspace @reup-douyin/web run test`: passed.
- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm run extension:build`: passed and regenerated packageable unpacked output in `apps/extension-douyin-capture/dist`.

## Final Status

The download flow is now truthful. A real download remains available through `GET /douyin-extension/download` when the built extension output contains files. If the extension build output is missing or empty, both web setup surfaces avoid a broken clickable link and direct the operator to run `npm run extension:build` and manually load `apps/extension-douyin-capture/dist` with the browser `Load unpacked` workflow.
