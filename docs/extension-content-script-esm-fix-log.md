# Extension Content Script ESM Fix Log

## Scope
- Task: Fix only the extension runtime build/load mismatch causing `Uncaught SyntaxError: Cannot use import statement outside a module` from [`contentScript.js`](apps/extension-douyin-capture/dist/contentScript.js).
- In-scope area: [`apps/extension-douyin-capture`](apps/extension-douyin-capture) build/runtime assets and related docs only.

## Audit (Before Fix)

### 1) Manifest content script entry
- Manifest content scripts currently load [`contentScript.js`](apps/extension-douyin-capture/public/manifest.json:25) as a classic content script via [`content_scripts`](apps/extension-douyin-capture/public/manifest.json:22).

### 2) Build pipeline
- Current build script is [`"build": "tsc -p tsconfig.json && node scripts/copy-static.mjs"`](apps/extension-douyin-capture/package.json:6).
- TypeScript output is emitted to [`dist`](apps/extension-douyin-capture/tsconfig.json:10) with module target [`"module": "ES2022"`](apps/extension-douyin-capture/tsconfig.json:4).

### 3) Whether raw `tsc` output is used directly
- Yes. Static assets are copied into dist by [`copy-static.mjs`](apps/extension-douyin-capture/scripts/copy-static.mjs:8), and Chrome loads generated dist files directly.

### 4) Directly injected scripts and module format
- Content script source imports modules at top level in [`contentScript.ts`](apps/extension-douyin-capture/src/contentScript.ts:1).
- Built [`dist/contentScript.js`](apps/extension-douyin-capture/dist/contentScript.js:1) still contains top-level `import` statements.
- Injected page script [`pageNetworkHook.js`](apps/extension-douyin-capture/public/manifest.json:14) is currently classic/IIFE output and does not begin with ESM imports in [`dist/pageNetworkHook.js`](apps/extension-douyin-capture/dist/pageNetworkHook.js:1).

### 5) File Chrome actually loads
- Manifest points to [`contentScript.js`](apps/extension-douyin-capture/public/manifest.json:25), which currently resolves to raw ESM-like `tsc` output in dist.

## Exact Root Cause
- **Primary root cause:** manifest loads content script as classic script, but build pipeline emits ESM JS (`module: ES2022`) and ships it directly.
- **Technical mismatch:** no bundling step converts [`contentScript.ts`](apps/extension-douyin-capture/src/contentScript.ts:1) and its imports into a classic browser-executable single runtime asset.

## Planned Fix
- Replace raw `tsc` runtime emission path with a bundling step that outputs classic scripts for content-script runtime entrypoints.
- Keep manifest runtime paths stable, but ensure generated file at that path is non-ESM for content script.
- Verify final built files used by manifest/injection paths contain no top-level `import`/`export` where classic loading is required.

## Build/load path after fix
- Build pipeline now runs:
  - [`tsc -p tsconfig.json`](apps/extension-douyin-capture/package.json:6)
  - [`node scripts/bundle-content-script.mjs`](apps/extension-douyin-capture/package.json:6)
  - [`node scripts/copy-static.mjs`](apps/extension-douyin-capture/package.json:6)
- Bundling step emits a classic bundled content script at [`dist/contentScript.js`](apps/extension-douyin-capture/scripts/bundle-content-script.mjs:15).
- Manifest still points to [`contentScript.js`](apps/extension-douyin-capture/public/manifest.json:25), but that file is now bundle-generated classic runtime output.

## Files Changed
- [`apps/extension-douyin-capture/package.json`](apps/extension-douyin-capture/package.json)
  - Updated build script to include bundling step.
  - Added `esbuild` dev dependency.
- [`apps/extension-douyin-capture/scripts/bundle-content-script.mjs`](apps/extension-douyin-capture/scripts/bundle-content-script.mjs)
  - Added deterministic esbuild bundling for content script to IIFE/classic output.
- [`docs/extension-content-script-esm-fix-log.md`](docs/extension-content-script-esm-fix-log.md)
- [`docs/extension-content-script-esm-fix-resume.md`](docs/extension-content-script-esm-fix-resume.md)

## Verification Result
- Build passes via [`npm run build`](apps/extension-douyin-capture/package.json:6).
- Manifest dist still references:
  - [`contentScript.js`](apps/extension-douyin-capture/dist/manifest.json:25)
  - [`pageNetworkHook.js`](apps/extension-douyin-capture/dist/manifest.json:14)
- Runtime content script bundle has no top-level ESM import/export:
  - confirmed by command `findstr /R /N "^import ^export" dist\\contentScript.js` => `NO_TOP_LEVEL_ESM`.
- Injected script file also has no top-level ESM import/export:
  - confirmed by command `findstr /R /N "^import ^export" dist\\pageNetworkHook.js` => `PAGE_HOOK_NO_TOP_LEVEL_ESM`.
