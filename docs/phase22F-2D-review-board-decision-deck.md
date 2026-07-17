# Phase 22F-2D Review Board Decision Deck

## What changed

- Reworked Review Board from the 22F-2C full-width creative inbox into a three-zone Decision Deck.
- Added a left Queue Rail for fast candidate navigation and multi-select state.
- Promoted the active candidate into a center Review Deck with the existing approval/review/reject controls.
- Added a right Insight Panel that keeps canonical metadata and diagnostics visible without opening a drawer.
- Kept the details drawer available from More > Inspect details for focused deep dives.

## UI contract

- `data-review-board-decision-deck="22F-2D"` marks the new workspace shell.
- `data-review-board-ui-version="22F-2D"` marks the dev-only visible version line.
- `data-review-board-card-list="22F-2D"` marks the Queue Rail list.
- `data-review-board-trace-version="22F-2D"` marks row-level frontend trace metadata.

## QA notes

- Desktop layout uses Queue Rail / Review Deck / Insight Panel columns.
- Tablet layout folds the Insight Panel below the first two columns.
- Mobile layout stacks all zones and caps Queue Rail height for quick scanning.
- Candidate status updates, delete confirmation, drawer inspection, and bulk actions preserve the 22F-2C behavior.

## Validation

- `npm run test`
- `npm run typecheck`
- `npm run build`

Build completed with pre-existing autoprefixer warnings in `globals.css` about `start`/`end` alignment values.
