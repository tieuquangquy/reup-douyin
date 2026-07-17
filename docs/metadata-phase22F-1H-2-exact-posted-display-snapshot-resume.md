# Phase 22F-1H-2 Exact Posted Display Snapshot Resume

## Completed
- Traced Capture Inbox exact Posted source for aweme `7634938045598289206`: `apps/web/src/lib/captureInboxCanonical.ts`, `resolvePosted(item)` -> `formatDateTime(item.posted_at)`.
- Traced Review Board candidate `283cd213-2854-473a-aafc-bbdf03024f64`: stale `posted_display=03/05/2026`, no `posted_display_exact`, `posted_at=2026-05-03T02:40:00+00:00`.
- Added backend snapshot fields: `posted_display_exact`, `posted_display_source`, `posted_display`, `posted_at`, `posted_text_raw`.
- Updated self-heal/backfill field list and source metadata version to `22F-1H-2`.
- Updated Candidate API and Review Board frontend adapter to prefer `posted_display_exact`.
- Added buffalo/yak backend and frontend fixtures.

## Validation Status
- Passing: `cd apps/api && python -m unittest tests.test_phase22f_review_candidate_contract && python -m compileall src`.
- Passing: `npm --workspace @reup-douyin/web run test`.
- Pending at handoff if needed: web typecheck and build.

## Manual Retest
1. Open Capture Inbox and confirm the buffalo/yak card shows `Posted 09:40:00 3/5/2026`.
2. Promote or refresh Review Board so self-heal runs.
3. Open Review Board and confirm the same card shows `Posted 09:40:00 3/5/2026`.
4. Confirm score `43`, estimated views `2.1K-10.3K`, metrics `103/5/11`, and duration `10:37` remain unchanged.
