# Phase 21D-4 Google Sans Typography Log

## Scope

Implemented Phase 21D-4 only for the Douyin Capture extension popup. This phase was limited to popup CSS typography tokens, font application, typography scale cleanup, tests, and documentation.

## Font stack used

UI font stack:

```css
"Google Sans", "Google Sans Text", "Google Sans Flex", "Roboto", "Arial", sans-serif
```

Mono/debug font stack:

```css
"Google Sans Mono", "Google Sans Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace
```

## Why fallback is needed

Google Sans and Google Sans Flex are not guaranteed to be installed on every Windows operator machine or browser environment. The popup therefore uses a CSS font-family stack that tries Google-style fonts first and falls back to Roboto, Arial, and generic sans-serif without breaking rendering.

## Why no remote CDN import was added

No remote Google Fonts or fonts.googleapis.com import was added. Browser extensions must respect CSP/build policy, and this repository does not currently define an approved remote font-loading strategy for the popup. This phase intentionally uses safe local font-family fallbacks only.

## Typography scale changes

- Main scanner title: 20px, 800 weight, -0.03em letter spacing, 1.1 line height.
- Subtitle: 12px, 500 weight, 1.35 line height.
- Section eyebrow: 11px, 700 weight, 0.06em letter spacing, uppercase.
- Primary action title: 20px, 800 weight, -0.03em letter spacing, 1.12 line height.
- Body/action helper text: 12px, 400 weight, 1.45 line height.
- Buttons: 14px, 700 weight.
- Counter numbers: 18px, 800 weight.
- Select controls: 12px, 600 weight.
- Chips/stat labels were reduced from over-bold weights to 600/700 ranges.

## Tests run

Passed:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Files changed

- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts`
- `docs/metadata-phase21D-4-google-sans-typography-log.md`
- `docs/metadata-phase21D-4-google-sans-typography-resume.md`
