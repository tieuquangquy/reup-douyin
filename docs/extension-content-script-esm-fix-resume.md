# Extension Content Script ESM Fix Resume

Date: 2026-04-29
Status: Completed

## Scope lock

- Fix only extension runtime build/load mismatch causing `Cannot use import statement outside a module` in [`contentScript.js`](apps/extension-douyin-capture/dist/contentScript.js).
- In-scope: [`apps/extension-douyin-capture`](apps/extension-douyin-capture) build config, manifest/runtime asset paths, and extension docs/tests related to this bug.
- Out-of-scope: backend, web app UI redesign, capture business-logic refactors.

## Root-cause summary (audited)

1. Manifest loads [`contentScript.js`](apps/extension-douyin-capture/public/manifest.json:25) as a standard content script (classic script semantics).
2. Build script currently uses raw TypeScript emit ([`package.json`](apps/extension-douyin-capture/package.json:6)) with [`"module": "ES2022"`](apps/extension-douyin-capture/tsconfig.json:4).
3. Built runtime file still contains top-level imports at [`dist/contentScript.js`](apps/extension-douyin-capture/dist/contentScript.js:1).
4. Therefore Chrome content script loader executes classic script while file is ESM-style output, triggering syntax error at line 1.

## Before-fix load path

- Build: `tsc -p tsconfig.json && node scripts/copy-static.mjs`
- Manifest path: `content_scripts[].js -> contentScript.js`
- Loaded file in dist: [`dist/contentScript.js`](apps/extension-douyin-capture/dist/contentScript.js)
- Problem: top-level `import` remains.

## Implementation summary

1. Updated build pipeline in [`package.json`](apps/extension-douyin-capture/package.json:6) to add a bundling step before static copy.
2. Added [`bundle-content-script.mjs`](apps/extension-douyin-capture/scripts/bundle-content-script.mjs:1) to bundle [`contentScript.ts`](apps/extension-douyin-capture/src/contentScript.ts:1) into classic IIFE output at [`dist/contentScript.js`](apps/extension-douyin-capture/scripts/bundle-content-script.mjs:15).
3. Kept manifest runtime path unchanged at [`contentScript.js`](apps/extension-douyin-capture/public/manifest.json:25), ensuring Chrome now loads classic bundled output at the same path.
4. Verified injected page script path [`pageNetworkHook.js`](apps/extension-douyin-capture/public/manifest.json:14) remains classic-compatible with no top-level ESM import/export.

## Verification status

- Build command passed: `npm run build` in [`apps/extension-douyin-capture`](apps/extension-douyin-capture).
- Dist manifest points to expected runtime files in [`dist/manifest.json`](apps/extension-douyin-capture/dist/manifest.json:14) and [`dist/manifest.json`](apps/extension-douyin-capture/dist/manifest.json:25).
- Top-level ESM checks:
  - `findstr /R /N "^import ^export" dist\\contentScript.js` => `NO_TOP_LEVEL_ESM`
  - `findstr /R /N "^import ^export" dist\\pageNetworkHook.js` => `PAGE_HOOK_NO_TOP_LEVEL_ESM`
- Content script line 1 is no longer ESM import; runtime syntax mismatch condition is removed.
