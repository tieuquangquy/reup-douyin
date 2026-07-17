# Douyin Capture Inbox Wording Cleanup Log

## Scope

Cleanup and normalize visible English wording across the Capture Inbox page at `/ops/extensions/douyin/capture-inbox`.

## Explicit Non-Goals

- No layout redesign.
- No new workflows or actions.
- No business logic changes.
- No API or persistence changes.
- No new dependencies.
- No changes to Review Board or Reup Queue beyond tone reference.

## Files Changed

- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `docs/douyin-capture-inbox-wording-cleanup-log.md`
- `docs/douyin-capture-inbox-wording-cleanup-resume.md`
- `docs/douyin-capture-inbox-wording-cleanup-user-guide.md`

## Tone References

Review Board and Reup Queue use short, action-oriented copy:

- `Keep`, `Reject`, `Details`, `Apply`, `Reset`
- `Find candidates`, `Find queue work`
- `Overview`, `Metadata`, `Diagnostics`
- Honest fallback text such as `Not captured`, `Pending`, and `No action needed`

Capture Inbox now follows that style while preserving Capture Inbox-specific states and workflow meaning.

## Audit Findings And Implementation

### Page Title And Subtitle

Findings:

- Shell and page descriptions were too long and repetitive.
- Page helper text described UI structure instead of operator purpose.

Changes:

- Kept `Douyin Capture Inbox` as the visible page title.
- Shortened shell description to: `Stage Douyin captures, fix incomplete items, and promote ready work to Review Board.`
- Shortened page description to: `Review staged Douyin videos before they move to Review Board.`

### Summary Cards

Findings:

- `Needs enrichment` was too narrow for a bucket that also includes raw and preview-pending rows.
- Some helper text repeated labels.

Changes:

- Kept `Captured`, `Ready`, `Duplicates`, `Failed`, and `Promoted`.
- Normalized `Needs enrichment` to `Needs action`.
- Shortened descriptions:
  - `All staged items in this session.`
  - `Ready for Review Board.`
  - `Already known or repeated.`
  - `Needs follow-up or preview.`
  - `Needs retry or exclusion.`
  - `Sent to Review Board.`

### Search And Filters

Findings:

- `Search and filters` was generic.
- Placeholder and helper text were repetitive.

Changes:

- Renamed section to `Find captured items`.
- Shortened helper text to `Search by caption, video ID, source, or status.`
- Shortened placeholder to `Caption, video ID, or source`.

### Status Chips And Tabs

Findings:

- `Needs enrichment` was too narrow for raw and unfinished rows.
- `Preview pending` remained useful and accurate.

Changes:

- Mapped `RAW` and `NEEDS_ENRICHMENT` to `Needs action`.
- Kept `Preview pending`, `Duplicate`, `Failed`, `Ready`, `Promoted`, and `Excluded`.
- Preserved backend session enum values in the session status dropdown because they are explicit session states.

### Item Cards

Findings:

- Card copy was mostly compact, but missing-thumbnail copy could be shorter.

Changes:

- Kept standardized `Details` labels.
- Shortened missing thumbnail copy from `No thumbnail available` to `No thumbnail`.
- Kept `Next:` for scan speed.

### Next Action Text

Findings:

- Next-action sentences mixed review, promotion, and action-required wording.

Changes:

- Normalized next-action copy:
  - `Promote to Review Board.`
  - `Retry enrich.`
  - `Retry preview.`
  - `Exclude if not needed.`
  - `Retry enrich or exclude.`
  - `Open in Review Board.`
  - `No action needed.`

### Session List And Menu

Findings:

- `compact session card(s)` described UI instead of content.
- `dup` was too terse.

Changes:

- Changed section description to `{n} session(s) shown.`
- Changed `dup` to `duplicates`.
- Shortened the session menu aria label to `Session actions for ...`.
- Kept `Delete session` for the destructive menu action.

### Detail Drawer

Findings:

- `Details drawer`, `Item detail panel`, and `Item detail drawer` repeated the same idea.
- `Source / References` and `Outputs / Downstream artifacts` were longer than needed.
- Empty detail text was too long.

Changes:

- Changed eyebrow to `Details`.
- Changed heading and panel title to `Item details`.
- Changed empty detail fallback to `Select an item to view details.`
- Changed `Source / References` to `Source`.
- Changed `Outputs / Downstream artifacts` to `Outputs`.
- Changed `Video id` and `Item id` to `Video ID` and `Item ID`.

### Metadata Labels

Findings:

- Most metadata labels were useful and should remain.
- `Dedupe` and `Readiness` are technical but operator-relevant.

Changes:

- Preserved technical metadata labels that map to real diagnostics/workflow meaning.
- Normalized ID capitalization.

### Diagnostics And Raw Details

Findings:

- Technical wording is appropriate in diagnostics/raw sections.

Changes:

- Preserved `Diagnostics`, `Raw details`, `Action source URLs`, and `Latest raw action details`.
- Preserved JSON payload display.

### Empty, Loading, Error, Fallback Text

Findings:

- Empty states were honest but longer than needed.

Changes:

- Item empty state now says `No matching items` with detail `Try All or clear search.`
- Session empty state now says `No sessions found` with detail `Try another session status.`
- Preserved `Not captured`, `Pending`, `Not analyzed yet`, and `None`.

### Confirm Dialogs

Findings:

- Delete confirmations were safe but verbose.

Changes:

- Session delete confirmation now starts with `Delete session?` and keeps the safety promise: promoted Review Board records are not deleted.
- Item delete confirmation now uses `Delete {n} staged item(s)? Promoted items are skipped.`

### Actions And Bulk Bar

Findings:

- Single-item retry action used `Retry enrich`, while batch used `Retry selected`.
- Batch helper text was mechanical.

Changes:

- Changed batch retry to `Retry enrich selected ({n})`.
- Kept `Promote selected`, `Exclude selected`, and `Delete selected`.
- Changed batch helper text to `Only eligible items are changed.`
- Changed internal action fallback label from `Exclude / skip` to `Exclude`.

## Normalized Terminology

- Details: standard inspect/open-detail action.
- Ready: can be promoted to Review Board.
- Needs action: unfinished enrichment, raw capture, or preview work.
- Preview pending: preview readiness is not complete.
- Failed: enrichment/action failed and needs operator decision.
- Promoted: already sent to Review Board.
- Not captured: source data is absent.
- Pending: work or readiness is not complete yet.
- Not analyzed yet: analysis has not produced a result.
- Promote: send ready staged items to Review Board.
- Retry enrich: rerun enrichment for selected items.
- Retry preview: rerun preview readiness.
- Exclude: keep out of promotion.
- Delete: remove staged local Capture Inbox records.

## Test Updates

Updated `apps/web/src/test/capture-inbox.test.ts` source-based checks for:

- `Needs action` wording.
- `Find captured items` filter title.
- `No thumbnail` fallback.
- `Item details` drawer title.
- `Source` and `Outputs` section titles.
- `Retry enrich selected` batch label.
- Shortened delete confirmations.
- Concise drawer fallback and search helper wording.

## Verification

Command run from `c:/Users/PC/Desktop/reup_douyin`:

```powershell
npx tsx apps/web/src/test/capture-inbox.test.ts && npm run typecheck --workspace apps/web
```

Result:

```text
capture inbox UX redesign, action hierarchy, and polish tests passed

> typecheck
> tsc --noEmit -p tsconfig.typecheck.json
```

## Issue Encountered

Initial verification failed because the test rejected `Needs enrichment`, and the phrase still appeared in the `Needs action` summary helper text. Fixed by changing that helper to `Needs follow-up or preview.`

## Final Status

Complete. Capture Inbox wording is shorter, more consistent, and aligned with Review Board/Reup Queue tone while preserving workflow meaning and technical diagnostics.
