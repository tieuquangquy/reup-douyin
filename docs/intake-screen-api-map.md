# Intake Screen API Map

## Backend Endpoints Reused

- `GET /filter-presets`
  - Used by `/intake` to populate the optional preset select.
- `POST /source-profiles/ingest`
  - Reused internally by the intake discovery service when a submitted profile is not already known.
- `POST /candidates/filter/apply`
  - Reused conceptually through `CandidateEvaluationService.apply` to create/update `VideoCandidate` records.
- `GET /candidates`
  - Used by the review board after successful discovery.

## Backend Endpoints Added

- `POST /intake/discover`
  - Purpose: one Operator-facing action that validates a Douyin profile URL, resolves or ingests the profile, applies candidate discovery filters, and returns a workflow summary.
  - Canonical route for the `/intake` form.
  - Preset handling: when a preset and custom filters are both sent, backend starts from the preset config and overlays only explicitly submitted form filters.
  - Implementation files:
    - `apps/api/src/api/routes/intake.py`
    - `apps/api/src/schemas/intake.py`
    - `apps/api/src/services/intake_discovery_service.py`

## Frontend Hooks / Services Used

- Existing:
  - `fetchFilterPresets()` from `apps/web/src/lib/api.ts`
- Added:
  - `discoverIntakeCandidates()` in `apps/web/src/lib/api.ts`
  - `buildIntakeDiscoverRequest()` and `validateIntakeForm()` in `apps/web/src/lib/intakeState.ts`

## Request Shape

```json
{
  "profile_url": "https://www.douyin.com/user/MS4wLjABAAAA...",
  "preset_name": "viral_discovery",
  "filter_config": {
    "date_mode": "absolute_range",
    "start_date": "2026-03-01T00:00:00.000Z",
    "end_date": "2026-04-22T23:59:59.999Z",
    "min_views": 10000,
    "max_views": 500000,
    "min_likes": 500,
    "max_likes": null,
    "sort": "score_desc",
    "limit": 50,
    "offset": 0
  },
  "persist": true
}
```

## Response Shape

```json
{
  "success": true,
  "source_profile_id": "uuid",
  "crawl_session_id": "uuid-or-null",
  "submitted_profile_url": "https://www.douyin.com/user/MS4wLjABAAAA...",
  "normalized_profile_identifier": "MS4wLjABAAAA...",
  "videos_discovered_count": 12,
  "videos_created_count": 0,
  "videos_updated_count": 0,
  "candidates_total_count": 12,
  "candidates_matched_count": 6,
  "candidates_rejected_count": 6,
  "candidate_results_count": 12,
  "filters_applied_summary": {},
  "unsupported_filters_ignored": [],
  "fetch_mode": "live_or_fixture_ingest",
  "used_existing_profile": false,
  "next_suggested_route": "/review-board?fresh=1",
  "warning": null
}
```

## Notes

- If a profile already exists, `crawl_session_id` can be `null` and discovery runs against existing `SourceVideo` + `VideoMetricSnapshot` data.
- If a profile does not exist and live fetch is disabled or unavailable, the API returns a clear failure from the existing source ingest service. No fake candidate generation is introduced.
- If `DOUYIN_ENABLE_LIVE_FETCH=true`, the default Douyin adapter uses the live HTML fetch client and still persists through the same canonical source ingest service.
- Success UX remains explicit: `/intake` shows a summary and links to `/review-board?fresh=1` instead of forcing an immediate redirect.
