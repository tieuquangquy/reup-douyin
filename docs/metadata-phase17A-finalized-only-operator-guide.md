# Metadata Phase 17A — Finalized-Only Operator Guide

## What Changed
Smart Capture now separates profile discovery from visible Capture Inbox creation.

Before this phase, Smart Capture could stage profile-card-only items that looked partial or rubbish in the Capture Inbox / Tile Gallery. In Phase 17A, normal Smart Capture first creates a Harvest Plan, then only creates visible items after modal harvest collects complete metadata.

## Normal Smart Capture Flow
1. Open the Douyin profile or modal flow as usual.
2. Click Smart Capture.
3. The extension asks the backend for a Harvest Plan.
4. If the plan has no new or incomplete targets, Smart Capture completes as a no-op.
5. If targets exist, open/confirm the modal and continue the modal harvest.
6. Visible Capture Inbox / Tile Gallery items appear only after full modal metadata is finalized.

## What Counts As Finalized
A visible item requires:
- aweme id;
- page/source URL;
- title, caption, or description;
- thumbnail when available from the profile card;
- positive duration;
- like/comment/favorite/share counts present and non-negative;
- modal integrity checks passing.

View count is not required in this phase.

## When Nothing Appears In Capture Inbox
This can be expected when:
- the Harvest Plan found no new or incomplete videos;
- modal harvest has not run yet;
- modal metadata was incomplete;
- integrity checks failed.

For incomplete modal metadata, the backend reports item failure reason `finalized_metadata_required` instead of creating a partial visible item.

## Advanced Manual Capture
The advanced/manual "Capture current page" action can still create staged current-page capture rows. Use it only when you explicitly want the old staging behavior for diagnosis or manual workflows.

Normal Smart Capture should be used for clean finalized-only Capture Inbox / Tile Gallery results.

## Operator Safety Notes
- Do not interpret an empty Capture Inbox after profile scan as data loss; the profile scan now creates a plan rather than visible rows.
- Run or resume modal harvest to finalize items.
- If Smart Capture completes with no targets, the backend classified existing items as already complete or found no eligible aweme ids.
- If many items fail with `finalized_metadata_required`, verify the modal is open, calibrated, and showing real video metadata.
