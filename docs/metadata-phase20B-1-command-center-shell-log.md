# Phase 20B-1 — Command Center Shell Log

## Goal
Create a new popup UI shell for the Douyin extension called **"Douyin Harvest Command Center"**. This is a purely structural and presentational rebrand — no harvest logic, backend API, scanner, extraction, or save handlers were changed.

## Scope
- `apps/extension-douyin-capture/public/popup.html`
- `apps/extension-douyin-capture/public/popup.css`
- `apps/extension-douyin-capture/src/popup.ts` — no runtime logic changes, only preserved existing tab switching
- `apps/extension-douyin-capture/src/wholeProfileHarvest.tabs.test.ts`
- `apps/extension-douyin-capture/src/wholeProfileHarvest.wording.test.ts`
- `apps/extension-douyin-capture/src/phase18aPopupCleanup.test.ts`
- `apps/extension-douyin-capture/src/ui20B1CommandCenterShell.test.ts` (new)
- `apps/extension-douyin-capture/package.json` (test script ordering)
- `docs/metadata-phase20B-1-command-center-shell-log.md` (this file)
- `docs/metadata-phase20B-1-command-center-shell-resume.md`

## Non-Goals
- No crawler implementation changes.
- No video processing changes.
- No scoring or filtering changes.
- No backend API contract changes.
- No queue, database, or worker changes.
- No new JavaScript/TypeScript runtime behavior in popup.ts.
- No changes to tab-switching persistence mechanism (`chrome.storage.local`).

## Changes Made

### 1. popup.html — Header Rebrand and Shell Classes
- `<title>` changed from `Douyin Profile Harvester` to `Douyin Harvest Command Center`.
- `<h1>` changed from `Douyin Profile Harvester` to `Douyin Harvest`.
- Subtitle changed from `Operator dashboard for scan, extract, and save.` to `Scan → Extract → Save`.
- Added `.dh-shell` to `<main>`.
- Added `.dh-header` to `<header>`.
- Added `.dh-tabs` to `<nav>` tab bar.
- Added `.dh-tab-panel` to all three tab panels (`Run`, `Results`, `Advanced`).
- Added `.dh-card` to key dashboard cards in each tab to establish the card container pattern.
- Preserved all existing `id`, `data-feature`, and `data-tab-panel` attributes.
- No DOM reordering or content removal beyond the subtitle swap.

### 2. popup.css — Design Token Shell
Added new `.dh-*` selectors alongside existing selectors to preserve backward compatibility:
- `.dh-shell` — alongside `.app-shell`
- `.dh-header` — alongside `.app-header, .popup-header`
- `.dh-tabs` — alongside `.tabbar`
- `.dh-tabs .tab` — alongside `.tab`
- `.dh-tabs .tab.active` — alongside `.tab.active`
- `.dh-tab-panel` — alongside `.tab-panel`
- `.dh-card` — alongside `.panel`
- `.dh-card--compact` — alongside `.panel--compact`

The additive approach means existing tests and any runtime code that queries by legacy class names continue to work.

### 3. popup.ts — No Logic Changes
- Verified that [`applyWholeProfileActiveTab()`](apps/extension-douyin-capture/src/popup.ts:323) and [`setWholeProfileActiveTab()`](apps/extension-douyin-capture/src/popup.ts:338) remain unchanged.
- Tab switching still persists via [`saveWholeProfileHarvestUiPrefs()`](apps/extension-douyin-capture/src/popup.ts:338).
- No new event listeners or DOM queries were added.

### 4. Test Updates
- `wholeProfileHarvest.wording.test.ts` — updated expected strings for the new product name and subtitle.
- `phase18aPopupCleanup.test.ts` — updated regex expectations for:
  - `advancedDiagnostics` class string (now includes `.dh-card`).
  - Subtitle text match.
- `wholeProfileHarvest.tabs.test.ts` — updated CSS regexes to tolerate comma-separated multi-selector rules:
  - `.tabbar[^{]*\{` instead of `.tabbar\s*\{`.
  - `.tab-panel[^{]*\{` instead of `.tab-panel\s*\{`.

### 5. New Test — ui20B1CommandCenterShell.test.ts
Validates:
- Title tag: `Douyin Harvest Command Center`.
- Header: `Douyin Harvest` and `Scan → Extract → Save`.
- Presence of `.dh-shell`, `.dh-header`, `.dh-tabs`, `.dh-tab-panel`, `.dh-card` classes in HTML.
- Presence of corresponding CSS rules.
- Absence of old wording (`Douyin Profile Harvester`, `Operator dashboard for scan, extract, and save.`).
- Persistence of tab-switching functions in `popup.ts`.

### 6. package.json
- Added `tsx src/ui20B1CommandCenterShell.test.ts` to the test script before the build step.

## Validation
- `npm --workspace @reup-douyin/extension-douyin-capture run test` — **PASS** (all 25 test suites).
- `npm --workspace @reup-douyin/extension-douyin-capture run build` — **PASS**.
- `npm --workspace @reup-douyin/web run typecheck` — **PASS**.
- Web app tests have a pre-existing failure (`review-board.test.ts` double path bug) unrelated to this change.

## Decisions and Trade-offs
1. **Additive CSS vs. Replacement**: We added `.dh-*` classes alongside existing ones rather than replacing them. This avoids a breaking change across existing tests and runtime DOM queries. Future phases can migrate queries incrementally.
2. **No JS Wiring Changes**: The task explicitly forbade harvest logic changes. Tab switching already worked from Phase 20A, so no wiring changes were needed.
3. **Subtitle Format**: Used `Scan → Extract → Save` instead of a sentence because it matches the compact command-center aesthetic and is easier to localize later.

## Risks
- **Low**. This is a cosmetic shell change. All functional tests pass. The additive CSS approach means legacy selectors still work.

## Follow-Up Work
- Phase 20B-2 may replace legacy class names in JS queries with `.dh-*` equivalents.
- Future work can add dark-mode tokens under `.dh-shell`.
- The `.dh-card` pattern can be extended with elevation variants when the design system matures.
