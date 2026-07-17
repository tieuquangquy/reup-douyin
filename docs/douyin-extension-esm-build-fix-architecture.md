# Douyin Extension ESM Build Fix Architecture

## Summary

The browser extension uses native browser ESM for the popup and MV3 module service worker. Because there is no bundling step, emitted JavaScript must contain import specifiers that browsers can resolve exactly.

## Browser ESM Rule

Chrome and Edge do not perform Node-style extension resolution for browser modules. An import such as:

```js
import { runPopupAction } from "./popupActions";
```

requests a resource literally named `popupActions`. It does not fall back to `popupActions.js`.

Correct browser-safe output is:

```js
import { runPopupAction } from "./popupActions.js";
```

## Build Strategy

The extension keeps a simple local-first build:

```powershell
npm --workspace @reup-douyin/extension-douyin-capture run build
```

The build uses TypeScript direct emit into `dist`, then copies static files from `public`.

No bundler is introduced. Instead, source TypeScript uses `.js` relative specifiers for local modules. TypeScript resolves them to `.ts` source files during compilation and preserves `.js` in emitted browser ESM.

## Popup Loading Contract

- `popup.html` loads `popup.js` with `type="module"`.
- `popup.js` imports local popup helpers with `.js` extensions.
- Every emitted relative local import must resolve to an existing file in `dist`.
- The dist verification test checks this contract after build.

## Scope Boundaries

- This fix is limited to `apps/extension-douyin-capture` build/module resolution and docs.
- It does not change backend handshake behavior.
- It does not rewrite popup action logic, capture behavior, or unrelated app systems.
