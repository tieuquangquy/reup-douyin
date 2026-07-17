# Douyin Extension ESM Build Fix Resume

## Current Goal

Ensure the built extension popup resolves local browser ESM modules correctly so Chrome/Edge no longer report `ERR_FILE_NOT_FOUND` for local modules such as `popupActions` and `popupTransport`.

## Relevant Files

- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/manifest.json`
- `apps/extension-douyin-capture/tsconfig.json`
- `apps/extension-douyin-capture/package.json`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupActions.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/background.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/distModuleResolution.test.ts`

## Root Cause

The TypeScript direct ESM build preserved extensionless relative imports in emitted JavaScript. Browser ESM does not append `.js`, so `dist/popup.js` attempted to load `./popupActions` and `./popupTransport` instead of `./popupActions.js` and `./popupTransport.js`.

## Completed Work

- Audited popup HTML, manifest, tsconfig, source imports, and emitted `dist` files.
- Updated runtime extension source imports to use `.js` relative specifiers.
- Added built-output verification for emitted ESM imports and popup HTML module loading.
- Updated extension test script to run the dist module-resolution verification after build.

## Verification

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`: passed.
- `npm --workspace @reup-douyin/extension-douyin-capture run test`: passed, including `extension dist module resolution tests passed`.
- `npm run extension:build`: passed.
- Dist inspection confirmed `dist/popup.js` now imports `./popupActions.js` and `./popupTransport.js`.

## Resume Point

This task is complete. Reload the unpacked extension from `apps/extension-douyin-capture/dist` in Chrome/Edge so the browser uses the rebuilt popup files.
