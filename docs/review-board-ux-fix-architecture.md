# Review Board UX Fix Architecture

## Objective

Make Review Board a dense, scan-friendly operator workspace while preserving existing review semantics.

## Layout Pattern

The Review Board page keeps the shared Ops Console shell and becomes:

1. Page header actions: refresh and Reup Queue link.
2. Compact status strip: loaded, approved, in review, new, rejected, and archived only when explicitly filtered.
3. Compact filter bar.
4. Main review workspace: dense horizontal candidate row-cards.
5. Right-side details inspector for long-form metadata and diagnostics.
6. Batch action bar for selected candidates.

## Candidate Row-Card Structure

Each row-card uses a Review Board-specific layout rather than the generic item-card layout:

- Left rail: checkbox and stable preview block.
- Middle content: title/caption, score, source, posted date, reason, operator hint, metrics chips.
- Header-right tools: status chip and visible Delete button.
- Footer actions: Keep, Mark in review, Reject, Details; Send to Reup Queue only when approved.

## Action Hierarchy

- Primary: Keep, or Send to Reup Queue for approved candidates.
- Secondary: Mark in review and Details.
- Destructive review decision: Reject as danger-outline/secondary destructive.
- Destructive cleanup: Delete in header tools, separated from the main footer actions.

## Delete Semantics

`Delete` is implemented as safe candidate-level archive/remove from Review Board:

- Updates `VideoCandidate.status` to `ARCHIVED`.
- Adds review-board delete metadata on the candidate.
- Excludes archived candidates from the default `/candidates` list.
- Does not delete upstream source media or canonical records.
- Does not delete queue records or downstream handoff records.

## State Sync

After delete succeeds:

- The item is removed from the local candidate list.
- Summary counts recompute from the local list.
- Selection set removes the candidate id.
- If the deleted candidate is open in details, the inspector is closed and cleared.
- The delete confirmation is cleared after the card disappears.

## Edge Cases

- Missing candidate: backend returns not found.
- Already archived candidate: delete remains idempotent and returns archived candidate state.
- Downstream queued candidate: delete still archives the Review Board candidate only; source media and queue records remain untouched.
