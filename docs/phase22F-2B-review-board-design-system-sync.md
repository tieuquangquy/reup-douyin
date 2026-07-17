# Phase 22F-2B - Review Board design-system sync + inspector/action UX fix

## Summary
Phase 22F-2B refines the Review Board frontend only. The page now follows Capture Inbox visual patterns more closely, fixes inspector close/open state, clarifies status tab semantics, and improves action hierarchy without changing backend data contracts or queue handoff behavior.

## Capture Inbox design-system sync
Audited and reused patterns from `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx` and `apps/web/src/app/globals.css`:

- Status tabs now use the Capture Inbox `capture-inbox-status-strip` / `capture-inbox-status-pill` language and `aria-pressed` semantics.
- Candidate rows share Capture Inbox compact card styling with white panels, `var(--line)` borders, `var(--accent)` selected state, and `var(--shadow)` emphasis.
- Score badges reuse Capture Inbox `capture-inbox-reup-score-badge` level classes.
- Filter controls are aligned with Capture Inbox field/search styling.
- Row and inspector actions use Capture Inbox tile action button sizing and tone hierarchy.

## Inspector close/open behavior
The Review Board now uses the explicit frontend model requested for 22F-2B:

- `selectedCandidateId` tracks the selected row.
- `isInspectorOpen` tracks whether the right inspector is rendered.
- Initial candidate load selects the first loaded candidate and opens the inspector.
- Row click and Inspect click select that candidate and open details.
- Close sets `isInspectorOpen` to false and keeps `selectedCandidateId` unchanged.
- When closed, the right panel is not rendered, avoiding a blank column.
- A `Show details` button reopens the selected candidate or the first visible candidate.
- If filters hide the selected candidate, the first visible candidate is selected while preserving the closed/open preference where possible.
- If no candidates remain visible, selection is cleared and the inspector closes.

## Status tab mapping
Status counts are based on the visible/loaded candidate set before applying the status tab filter. Frontend status semantics are normalized by `normalizeReviewStatus(candidate)`:

- All: all visible/loaded candidates before the status tab filter.
- New: candidates not otherwise approved, rejected, in review, shortlisted, or archived.
- Shortlisted: `SHORTLISTED` status/review state.
- In review: `IN_REVIEW` status/review state.
- Approved: `APPROVED` status/decision state.
- Rejected: `REJECTED` status/decision state.

Status tab clicks now update frontend status filtering without forcing a backend refetch scoped to only that status, so the strip can keep meaningful counts.

## Action hierarchy
- Approve is primary.
- Review / Mark in review is secondary.
- Reject is a danger outline.
- Inspect is ghost/details level.
- Remove remains a muted low-emphasis link with explicit confirmation and safe-remove copy.

## Data contract safeguards
The frontend continues to preserve the locked Review Board metadata contract:

- Visible score uses `reviewCandidateDisplayScore(candidate)` and therefore `reup_score`.
- Internal `candidate.score` is not displayed except as diagnostic-only text.
- Missing estimated views render `—`; no midpoint/view-count fallback is used for display.
- Missing likes/comments/shares render `—`; real zero values can still render as `0`.
- Estimated views label remains `Est. Views`.
- Remove still only removes the candidate from Review Board UI/backend candidate records and does not delete source media/upstream capture records.

## Deferred items
The following remain intentionally out of scope for 22F-2B:

- Reject reasons workflow.
- Bulk review reason capture.
- Approved-to-Reup-Queue handoff.
- Backend statuses or schema changes.
- Capture Inbox data logic changes.
