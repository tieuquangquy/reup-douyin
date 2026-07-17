# Phase 21D-4 Google Sans Typography Resume

## Phase

21D-4 — Apply Google Sans typography system

## Completed changes

- Added shared popup typography tokens to the active popup CSS.
- Added the required Google Sans / Google Sans Text / Google Sans Flex stack with Roboto and Arial fallbacks.
- Added a mono/debug token for code and raw-state style areas.
- Applied the UI font token to body, the active scanner shell, deck overlay panels, and the existing `dh-shell` popup class.
- Applied the UI font token to buttons, selects, inputs, and textareas.
- Applied the mono font token to pre, code, debug JSON, and raw-state areas.
- Standardized the active scanner control panel typography scale.
- Reduced over-bold Phase 21D-3 weights from 850/900/950 toward 600/700/800.
- Added static CSS tests for font tokens, fallbacks, controls, mono areas, no remote Google import, and typography scale.

## Font stack used

```css
--font-ui: "Google Sans", "Google Sans Text", "Google Sans Flex", "Roboto", "Arial", sans-serif;
--font-mono: "Google Sans Mono", "Google Sans Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace;
```

## Why fallback is needed

Google Sans is not guaranteed to exist on the operator machine. The fallback stack ensures the extension popup remains readable and functional when Google Sans or Google Sans Flex is unavailable.

## Why no remote CDN import was added

No remote font import was added because extension CSP/build policy should not be changed for this typography-only phase, and the repository does not currently provide an approved font-loading strategy for remote Google Fonts.

## Validation status

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Manual retest focus

1. Open the extension popup.
2. Confirm the UI still renders without loading remote fonts.
3. Confirm the scanner hero/title/action card uses cleaner Google-style typography.
4. Confirm controls use the same UI font stack.
5. Confirm debug/code text remains monospaced.
6. Confirm there is no visual regression in the compact Phase 21D-3 layout.
