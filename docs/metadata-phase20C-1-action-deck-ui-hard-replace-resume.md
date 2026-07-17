# Phase 20C-1 — Action Deck UI Hard-Replace Resume

## Status
Completed. Tests pass and build succeeds.

## What Was Done
1. Hard-replaced `popup.html` with the Action Deck 7-section layout.
2. Added `deck-*` CSS to `popup.css`.
3. Implemented `renderActionDeck` and supporting helpers in `popup.ts`.
4. Added `getActionDeckViewModel(state)` in `viewModel.ts`.
5. Wired primary action, settings bar, bottom-dock panel switching, and alert banner.
6. Moved all legacy content into the Advanced panel so nothing is lost.
7. Updated every affected test file to match the new markup, CSS classes, and wording.
8. Added `ui20C1ActionDeck.test.ts` as the dedicated contract test.
9. Ran `npm test -- --runInBand && npm run build`; both pass.
10. Wrote `metadata-phase20C-1-action-deck-ui-hard-replace-log.md`.

## Next Steps (none for this phase)
- This phase is complete. Any future popup refinements should open a new phase document.
