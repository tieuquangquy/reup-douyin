# Phase 21D-8 — Google Sans Typography Log

## Scope

Applied Google Sans / Google Sans Flex typography to the active Douyin Scanner extension popup CSS only.

## Active CSS File

- `apps/extension-douyin-capture/public/popup.css`

The active popup CSS was confirmed by searching for the scanner popup classes: `scanner-shell`, `scanner-hero`, `scanner-title`, `scanner-subtitle`, `scanner-primary-card`, `scanner-primary-button`, `scp-shell`, and `scp-`.

## Font Stack Used

UI stack:

```css
"Google Sans", "Google Sans Text", "Google Sans Flex", "Roboto", "Arial", sans-serif
```

Mono/debug stack:

```css
"Google Sans Mono", "Google Sans Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace
```

## Why Fallback Is Needed

The popup cannot assume Google Sans is installed on every operator machine or available in every browser runtime. The stack uses Google Sans and related names when locally available, then falls back to Roboto, Arial, and generic system sans-serif fonts so the popup remains readable and stable without bundling fonts.

## Remote Google Fonts Import Status

No remote Google Fonts import was added. Extension CSP/build policy must explicitly support any remote font loading before it is introduced. This phase intentionally avoids `fonts.googleapis.com`, runtime font fetches, binary font files, and CSP changes.

## Typography Weight Changes

Added Phase 21D-8 weight aliases:

- `--fw-regular: 400`
- `--fw-medium: 500`
- `--fw-semibold: 600`
- `--fw-bold: 700`
- `--fw-black: 800`

Applied the requested scanner typography emphasis:

- Title uses `var(--fw-black)` with tighter letter spacing.
- Subtitle uses `var(--fw-medium)`.
- Chips and stat labels use `var(--fw-semibold)`.
- Eyebrow text uses `var(--fw-bold)`, uppercase tracking, and compact line height.
- Primary action title uses `var(--fw-black)`.
- Buttons use `var(--fw-bold)`.
- Stat numbers use `var(--fw-black)` and an 18px scale.
- Selects use `var(--fw-semibold)`.

## Tests Updated

Updated static popup CSS assertions in `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts` to verify:

- `--font-ui` exists.
- `--font-ui` includes Google Sans, Google Sans Text, Google Sans Flex, Roboto, and Arial.
- Scanner popup roots use `font-family: var(--font-ui)`.
- Scanner controls inherit `var(--font-ui)`.
- Debug/code areas use `var(--font-mono)`.
- Remote Google Fonts imports are absent.
- Binary font file references are absent.
- Requested scanner typography weights and sizes are present.

## Validation

Pending at creation time:

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```
