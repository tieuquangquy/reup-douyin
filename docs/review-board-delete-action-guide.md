# Review Board Delete Action Guide

## Operator Meaning

The per-item `Delete` action removes a candidate from the active Review Board list. It is a safe cleanup action, not a source-data deletion.

## UI Placement

`Delete` appears on each candidate card in the header-right tool area next to the status chip. This keeps it visible on every item while separating it from the main review decisions.

## Confirmation Copy

- Title: `Delete candidate?`
- Body: `This removes the candidate from Review Board. Source media and upstream records are not deleted.`
- Confirm CTA: `Delete candidate`
- Cancel CTA: `Cancel`

## Backend Semantics

- Candidate status is set to `ARCHIVED`.
- Candidate metadata records `removed_from_review_board`, `removed_from_review_board_at`, and `removed_from_review_board_reason`.
- `SourceVideo`, source profile, raw capture records, Reup Queue records, export records, and publish records are not deleted.

## After Success

- The card disappears from the active list.
- Summary counts update.
- Selection state is cleared for that item.
- If the item detail panel was open, it closes.

## If The Candidate Has Downstream Records

The action remains safe because it only archives the Review Board candidate. Existing Reup Queue or downstream records are not deleted or cancelled by this action.

## Troubleshooting

- If a deleted candidate still appears, check whether the status filter is explicitly set to `Archived`.
- If the API returns not found, refresh the page; another action may have already removed or changed the candidate.
- If deletion fails, no local item is removed and the error banner explains the failure.
