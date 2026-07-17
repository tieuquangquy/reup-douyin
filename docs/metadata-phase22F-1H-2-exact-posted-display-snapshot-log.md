# Phase 22F-1H-2 Exact Posted Display Snapshot Log

## Trace
- Capture item: `e138dbf6-493a-42ad-91e9-6c0c9ad80424` / aweme `7634938045598289206`.
- Caption prefix: `103麝牛 无法抵抗的命运`.
- Metrics: likes `103`, comments `5`, shares `11`, duration `10:37`, score `43`, estimated views `2.1K-10.3K`.
- Capture DB fields before this phase: `posted_at=2026-05-03 02:40:00+00`, `metadata_json.posted_display=03/05/2026`, `posted_text_raw=1周前`.
- Capture Inbox UI source: `apps/web/src/lib/captureInboxCanonical.ts`, `resolvePosted(item)` calls `formatDateTime(item.posted_at)`, which calls `new Date(value).toLocaleString()`.
- Exact visible value for the user timezone: `09:40:00 3/5/2026`.

## Cause
Review Board copied `metadata_json.posted_display` / `source_metadata.posted_display` (`03/05/2026`) instead of the Capture Inbox card's exact posted-at display path, so the time was lost during promotion/backfill snapshot hydration.

## Implementation
- Added `posted_display_exact` and `posted_display_source` to Capture Inbox snapshot metadata.
- `posted_display` now mirrors `posted_display_exact` when exact display is available.
- API hydration prefers `source_metadata.posted_display_exact` and exposes `posted_display_exact`, `posted_display`, `postedDisplay`, `postedDisplayExactValue`, and `postedDisplayWasFormatted`.
- Review Board frontend adapter now prioritizes exact source metadata before any date-only display.

## Buffalo/Yak Result
The fixture case expects Review Board `Posted 09:40:00 3/5/2026` while preserving score `43`, views `2.1K-10.3K`, metrics `103/5/11`, and duration `10:37`.
