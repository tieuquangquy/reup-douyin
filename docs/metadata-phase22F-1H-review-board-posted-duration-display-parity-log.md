# Phase 22F-1H Review Board Posted and Duration Display Parity Log

## Audit

- Active Review Board card is `ReviewCandidateCard` in `apps/web/src/components/review-board/ReviewBoardPage.tsx`.
- Before this phase, the card rendered `Posted {metadata.postedDisplay ?? formatDate(source?.posted_at)}`.
- `formatDate` parsed strings with `new Date(value)` and returned `toLocaleDateString()`, so an ISO `posted_at` fallback could display as a locale/date-shifted value such as `03/04/2026` instead of the Capture Inbox text `23:00:00 2/4/2026`.
- The adapter already read `source_metadata`, but it did not expose display provenance and allowed less explicit posted fallback ordering.
- Duration existed in the details panel, but the Review Board card primary metadata row did not render Duration at all.
- Backend `CandidateDetailResponse` already flattened `source_metadata.posted_display`, `posted_at`, `posted_text_raw`, `duration_text`, and `duration_seconds`; this phase added camelCase aliases and source debug fields.

## Display Contract

Posted priority:
1. `candidate.source_metadata.posted_display`
2. `candidate.posted_display`
3. `candidate.postedDisplay`
4. `candidate.metadata_json.posted_display`
5. `candidate.source_metadata.posted_text_raw`
6. other captured posted text aliases
7. `candidate.posted_at` / `source_video.posted_at` only when no display text exists
8. `Not captured`

Duration priority:
1. `candidate.source_metadata.duration_text`
2. `candidate.duration_text`
3. `candidate.durationText`
4. `candidate.metadata_json.duration_text`
5. duration aliases
6. formatted `source_metadata.duration_seconds`
7. formatted candidate/source duration seconds
8. `Not captured`

## Backend Changes

- Added flattened aliases on `CandidateDetailResponse`: `postedDisplay`, `durationText`, and `durationSeconds`.
- Updated Review Board trace/debug version to `22F-1H`.
- Added `review_candidate_debug.postedDisplaySource`, `postedDisplayValue`, `durationSource`, and `durationValue`.
- Preserved `source_metadata.posted_display` verbatim; the `source_video.posted_at` ISO fallback only applies when no posted display text exists.
- Kept existing hydration path intact; posted/duration fields remain included in Review Board hydration fields.

## Frontend Changes

- Added adapter provenance fields `postedSource` and `durationSource`.
- Updated posted display priority to preserve `source_metadata.posted_display` before any timestamp fallback.
- Added duration text fallback from seconds only when duration text is missing.
- Changed the Review Board card to render `Posted {metadata.postedDisplay ?? "Not captured"}` and to show `Duration {metadata.durationText}` when captured.
- Updated details/diagnostics to include posted source, raw posted text, duration source, and duration seconds.

## Raccoon Case

Fixture caption: `114浣熊与黑熊`.

Expected Review Board display:
- Posted: `23:00:00 2/4/2026`
- Duration: `12:14`
- Must not display: `03/04/2026`

Backend and frontend tests were added for this fixture.

## Validation

Passed:
- `cd apps/api && python -m unittest tests.test_phase22f_review_candidate_contract`
- `cd apps/api && python -m compileall src`
- `npm --workspace @reup-douyin/web run test`
- `npm --workspace @reup-douyin/web run typecheck`
- `npm --workspace @reup-douyin/web run build`

Build warnings were pre-existing webpack path-casing cache warnings and autoprefixer mixed-support warnings in `apps/web/src/app/globals.css`.
