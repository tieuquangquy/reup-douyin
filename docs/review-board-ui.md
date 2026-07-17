# Review Board UI

The review board is the operator screen for scanning scored candidates before expensive steps like download, transcript work, OCR, TTS, and render.

## Route

```text
/review-board
```

The root web route redirects to this page for Phase 1.

## Screen Structure

- Header and toolbar.
- Preset/status/score/search/sort controls.
- Candidate grid.
- Bulk selection bar.
- Detail drawer.
- Loading, empty, and error states.

## Candidate Card

Each card shows:

- thumbnail or preview fallback
- Reup Score and score label
- title/caption excerpt
- posted date and duration
- latest metrics from score breakdown
- speech/text signals when present
- risk/watermark warning summary
- inclusion/warning reasons
- current candidate status
- keep/reject/details/preview actions

The card is optimized for fast scanning. Full breakdown lives in the detail drawer.

## Bulk Actions

Operators can:

- select one card
- select all visible cards
- clear selection
- keep selected
- reject selected
- mark selected for next step

Bulk actions call `POST /candidates/bulk-status`.

## Detail Drawer

The drawer keeps the operator in the review flow. It includes:

- larger preview area
- source link
- keep/reject actions
- inclusion/exclusion/warning reasons
- full score breakdown
- metadata signals

## Phase 1 Limits

- No local downloaded video playback yet.
- Source preview may rely on source URL or thumbnail fallback.
- No transcript editor, OCR editor, final review, or render status.

