# Douyin Extension Download Fix Resume

## Current Goal

Make the Extension Manager and setup pages truthful: a Download extension action must only be clickable when it can fetch a real ZIP from the backend; otherwise the operator must see manual Load unpacked instructions for `apps/extension-douyin-capture/dist`.

## Relevant Files

- `apps/api/src/services/douyin_extension_setup_service.py`
- `apps/api/src/api/routes/douyin_extension.py`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/tests/test_douyin_extension_setup_service.py`
- `apps/web/src/components/douyin-extension-manager/DouyinExtensionManagerPage.tsx`
- `apps/web/src/components/douyin-extension-setup/DouyinExtensionSetupPage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/douyinExtensionInstall.ts`
- `apps/web/src/test/douyin-extension-install.test.ts`
- `apps/web/src/types/douyin-extension-setup.ts`
- `apps/web/package.json`
- `apps/extension-douyin-capture/package.json`

## Audit Findings

- Backend route exists at `GET /douyin-extension/download`.
- Backend already creates an on-demand ZIP from `apps/extension-douyin-capture/dist`.
- Extension build currently creates unpacked `dist` output with `npm run extension:build`.
- Web pages currently render download links unconditionally.
- Backend status can report `download_available` for an existing but empty `dist` directory, while the download route rejects empty builds.

## Completed Work

- Made backend `download_available` reflect an actually packageable build directory.
- Kept the download route stable and serving a real ZIP when available.
- Disabled clickable download links when the ZIP is unavailable.
- Preserved and clarified the manual Load unpacked path from `apps/extension-douyin-capture/dist`.
- Added focused backend and web tests.

## Verification

- `python -m unittest tests.test_douyin_extension_setup_service` from `apps/api`: passed, 11 tests.
- `npm --workspace @reup-douyin/web run test`: passed.
- `npm --workspace @reup-douyin/web run typecheck`: passed.

## Re-Audit Verification

The repeated download-flow request was re-audited against the current repo. No additional code changes were required because the backend and web surfaces already implement the requested truthful behavior.

- `python -m unittest tests.test_douyin_extension_setup_service` from `apps/api`: passed, 11 tests.
- `npm --workspace @reup-douyin/web run test`: passed.
- `npm --workspace @reup-douyin/web run typecheck`: passed.
- `npm run extension:build`: passed.

## Resume Point

This task is complete. The Extension Manager and Extension Setup pages now render a real download link only when the backend reports packageable extension output. Otherwise they render a clear unavailable/manual Load unpacked workflow.
