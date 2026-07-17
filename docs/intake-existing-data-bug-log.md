# Intake Existing Data Bug Log

## Step
Fix intake discovery existing-data reuse for empty or unusable Douyin profiles.

## Findings
- `/intake` calls `POST /intake/discover`.
- The route maps `IntakeDiscoverRequest` to `IntakeDiscoveryService.discover`.
- `IntakeDiscoveryService` currently finds an existing `SourceProfile` and immediately sets `used_existing_profile = True`.
- The existing reuse path does not check whether the profile has any `SourceVideo` rows.
- The existing reuse path does not check whether the latest `CrawlSession` failed.
- Existing-data responses report `videos_discovered_count = 0` because no crawl summary is loaded for reused profiles.

## Root Cause
An existing `SourceProfile` record is treated as reusable by identity alone. Empty or previously failed profiles can therefore suppress live fetch and produce `Existing data / 0 videos / 0 candidates`.

## Decisions
- Add `force_live_refresh` to the intake request contract.
- Use existing data only when the existing profile is usable.
- Minimum usable definition for this step:
  - profile has at least one `SourceVideo`
  - latest crawl session is not `FAILED`
- If an existing profile is unusable, run the canonical `SourceIngestService.ingest_profile` path instead of adding a separate pipeline.
- Keep candidate discovery through `CandidateEvaluationService.apply`.
- Fetch mode labels become explicit: `existing_data`, `live_fetch`, `forced_live_fetch`.

## Files Touched
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/intakeState.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/test/intake.test.ts`
- `docs/intake-existing-data-bug-log.md`
- `docs/intake-existing-data-bug-resume.md`

## Implementation
- Added `force_live_refresh` to `IntakeDiscoverRequest`.
- Passed `force_live_refresh` from the API route into `IntakeDiscoveryService.discover`.
- Added `ExistingProfileUsability` and `_existing_profile_usability`.
- Existing data is now reusable only when:
  - there is at least one `SourceVideo` for the profile
  - the latest crawl session is not `FAILED`
- Empty existing profiles now fall through to the existing canonical ingest path via `SourceIngestService.ingest_profile`.
- Explicit final fetch modes:
  - `existing_data`
  - `live_fetch`
  - `forced_live_fetch`
- `/intake` now has a `Force live refresh` checkbox.
- `/intake` status panel renders final fetch mode from `response.fetch_mode`.
- Added a defensive UI warning if an `existing_data` response ever returns zero videos.

## Verification Notes
- API unit tests passed:
  - `python -m unittest apps/api/tests/test_intake_discovery_service.py apps/api/tests/test_douyin_adapter.py`
- Web state tests passed:
  - `npm run test` in `apps/web`
- Web typecheck passed:
  - `npm run typecheck` in `apps/web`
- i18n JSON parse check passed for English and Vietnamese files.
- Runtime API smoke:
  - `POST http://127.0.0.1:8000/intake/discover`
  - fixture profile with usable existing videos returned:
    - `fetch_mode: existing_data`
    - `videos_discovered_count: 2`
    - `candidates_matched_count: 2`
- Review board/candidate path still responds:
  - `GET http://127.0.0.1:8000/candidates?limit=5`
  - `GET http://localhost:3000/intake`
  - `GET http://localhost:3000/review-board`

## Known Remaining Rough Edge
- This step does not add a time-based stale threshold. Stale currently means unusable by content/state: no source videos or latest crawl failed. A future step can add an age threshold such as `refresh if last_crawled_at older than N days`.

## Status
Completed.
