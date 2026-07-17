# Phase 22F-1 Review Board Data Contract Hardening Log

## Scope
- Hardened the Capture Inbox to Review Board promotion contract only.
- Preserved Douyin metadata needed by Review Board candidate cards and detail panels.
- Kept missing source metrics as null instead of manufacturing zero values.

## Promote Flow Audit
- Frontend Promote actions call `runCaptureInboxAction()` with `promote_now`.
- Backend route `run_capture_inbox_action()` delegates to `CaptureInboxService.promote()`.
- Promotion builds adapter payloads in `_adapter_payload_for_items()` and ingests them through `SourceIngestService.ingest_profile()`.
- `DouyinProfileAdapter` normalizes promoted payload rows into `SourceVideo` and metric snapshots.
- `CandidateEvaluationService.apply()` creates or updates `VideoCandidate` rows.
- `/candidates` returns `CandidateDetailResponse`, which Review Board renders in `ReviewBoardPage.tsx`.

## Root Cause
- Scoring and filtering paths coerce missing metrics with `or 0` for score calculation.
- Review Board metric pills previously read `score_breakdown_json.engagement_quality.raw_input`, so missing source metrics could appear as fake zeros.
- Candidate metadata previously discarded most source metadata during candidate upsert.

## Backend Changes
- Expanded Capture Inbox adapter payload mapping for estimated views, text counts, engagement data, Reup Score label/components/reasons, posted text/display, duration, thumbnail, and source identity.
- Expanded Douyin adapter metadata preservation so promoted canonical fields survive into `SourceVideo.metadata_json`.
- Preserved normalized source metadata in `VideoCandidate.metadata_json` during upsert.
- Added lazy canonical aliases to `CandidateDetailResponse` so legacy candidates can hydrate Review Board fields from candidate/source metadata without a destructive migration.
- Added source identity validation before promotion: at least `source_video_external_id`, `source_url`, or `share_url` must exist.
- Added duplicate detection by `capture_item_id` in candidate metadata, alongside existing source video external id and source URL checks.

## Frontend Changes
- Added `getReviewCandidateMetadata(candidate)` as the Review Board adapter.
- Review Board cards, previews, detail panels, and views sorting now read canonical/metadata fields before conservative legacy fallbacks.
- Score-breakdown zero values are not accepted as source metric fallbacks.
- Missing metrics display as `--`; missing Capture Reup Score displays as `Not captured`.
- Changed Review Board views label to `Est. Views`.

## Tests
- Added backend response contract test for canonical alias hydration and null/zero handling.
- Expanded promotion test assertions for newly mapped canonical metadata fields.
- Added frontend adapter test for canonical precedence, explicit zero preservation, missing null preservation, conservative score fallback behavior, legacy metadata fallback, and estimated views sorting.
- Added the frontend adapter test to the web `test` script.
