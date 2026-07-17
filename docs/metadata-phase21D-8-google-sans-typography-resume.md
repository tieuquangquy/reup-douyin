# Phase 21D-8 — Google Sans Typography Resume

## Phase

21D-8 — Apply Google Sans typography to Douyin Scanner popup

## Completed Work

- Confirmed the active scanner popup CSS is `apps/extension-douyin-capture/public/popup.css`.
- Added the required typography comment at the top of the active popup CSS.
- Merged the required UI and mono font stacks into the existing root tokens.
- Added Phase 21D-8 weight aliases: `--fw-regular`, `--fw-medium`, `--fw-semibold`, `--fw-bold`, and `--fw-black`.
- Preserved previous `--font-weight-*` variables as aliases to reduce churn for existing popup styles.
- Applied `font-family: var(--font-ui)`, font synthesis, text rendering, and font smoothing to the popup root/shell selectors.
- Scoped scanner controls to inherit `var(--font-ui)`.
- Applied `var(--font-mono)` to scanner/debug/code areas.
- Updated scanner title, subtitle, chip, eyebrow, primary action title, body text, buttons, stat labels, stat numbers, and selects to the requested Google-style weights/scales.
- Updated static CSS tests in `apps/extension-douyin-capture/src/ui20C1ActionDeck.test.ts` for the Phase 21D-8 font and no-remote-font guardrails.

## Font Stack Used

UI stack:

```css
"Google Sans", "Google Sans Text", "Google Sans Flex", "Roboto", "Arial", sans-serif
```

Mono stack:

```css
"Google Sans Mono", "Google Sans Code", "SFMono-Regular", Consolas, "Liberation Mono", monospace
```

## Why Fallback Is Needed

Google Sans may not be installed locally and was not bundled by this phase. Roboto and Arial provide stable local/system fallbacks so the popup remains usable without changing extension packaging or CSP.

## Why No Remote Google Fonts Import Was Added

This extension popup should remain CSP-safe and local-first. Remote `fonts.googleapis.com` imports, runtime font fetches, unlicensed binary font files, and CSP changes were explicitly out of scope for this CSS-only typography phase.

## Typography Weight Changes

- Title: `var(--fw-black)`, 20px, 1.1 line height, `-0.03em` letter spacing.
- Subtitle: `var(--fw-medium)`, 12px, 1.35 line height.
- Chip: `var(--fw-semibold)`.
- Eyebrow: `var(--fw-bold)`, 11px, 1.2 line height, uppercase, `0.06em` tracking.
- Primary action title: `var(--fw-black)`, 20px, 1.12 line height.
- Body/description: `var(--fw-regular)`, 12px, 1.45 line height.
- Button: `var(--fw-bold)`, 14px, 1 line height.
- Stat label: `var(--fw-semibold)`.
- Stat number: `var(--fw-black)`, 18px.
- Select: `var(--fw-semibold)`, 12px.

## Tests To Run

```bash
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Non-Goals Preserved

- No scanner logic changes.
- No calibration logic changes.
- No collect/extract logic changes.
- No backend logic changes.
- No API contract changes.
- No handler or state machine changes.
- No layout restructuring or element movement.
- No button renames or action priority changes.
- No disabled behavior changes.
