# Phase 22F-2E Review Board Review Theater

## Summary

Phase 22F-2E replaces the 22F-2D three-column Decision Deck with a Review Theater interface focused on one selected creative at a time.

## Layout

- Compact Review Board header remains at the top.
- Status navigation remains a slim segmented strip with normalized counts.
- Toolbar remains compact with search, sort, preset, filters, reset, and apply.
- Main content is a large Review Theater stage with the selected candidate preview as the visual focus.
- Right side is a concise Decision Panel for actions and facts.
- Bottom Filmstrip Queue replaces the left Queue Rail as the primary queue UI.

## Filmstrip Queue

- Horizontal scroll queue at the bottom of the theater shell.
- Each item shows index, thumbnail or placeholder, visible Reup Score/Unscored, and status.
- Active candidate is highlighted.
- Clicking an item updates the Review Theater and Decision Panel.

## Decision Panel

- Shows score and status in the header.
- Keeps Approve candidate, Review later, and Reject candidate as the visible decision actions.
- Shows concise snapshot, metrics, source link, and full caption.
- Remove from board is low-emphasis and still uses the existing explicit confirmation.

## Selection Behavior

- Initial load selects the first visible candidate.
- Refresh keeps the selected candidate if still loaded.
- Search, filter, and status changes preserve the selected candidate if visible; otherwise select the first visible candidate.
- Empty/no-match states render in the theater area.

## Data Contract Safeguards

- Visible score continues to use `reviewCandidateDisplayScore(candidate)`, which is based on canonical `reup_score` and shows `Unscored` when missing.
- Est. Views uses the existing `formatEstimatedViews(metadata)` helper and never labels values as real views.
- Missing metrics use `formatMetric(..., null)` and display `—`.
- Posted and duration use hydrated display values from `getReviewCandidateMetadata`.
- Internal `candidate.score` remains diagnostic-only in the drawer.

## Deferred

- Reject reasons workflow.
- Bulk action redesign.
- Reup Queue handoff.
- Keyboard shortcuts.
- Alternate compact table/list view.
