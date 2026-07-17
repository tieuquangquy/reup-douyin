# Intake Filters Expansion Log

## Findings

- Presets are backend-defined in `apps/api/src/services/filter_presets.py`.
- `/intake` currently loads presets through `GET /filter-presets` and submits discovery to `POST /intake/discover`.
- Candidate discovery is backed by `CandidateEvaluationService`, `FilterConfig`, and `apply_candidate_filter`.
- Metrics available from `VideoMetricSnapshot`: views, likes, comments, shares, favorites.
- Source-video suitability signals are read from `SourceVideo.metadata_json`: `has_speech`, `text_density`, `is_live_replay`, `is_slideshow`, `has_heavy_watermark`, `processing_complexity`.
- Risk filter support currently checks open high/blocking copyright flags, not a generic risk-level selector.

## Current Filters Available

- Date: absolute range, last N days, latest N videos.
- Metrics: min/max views, likes, comments, shares.
- Duration: min/max seconds.
- Ratios: min like rate, min comment rate, min share rate.
- Suitability: speech required/no-speech disallowed, max text density.
- Exclusions: live replay, slideshow, heavy watermark, high copyright risk, high processing complexity.
- Sorting: score, newest, views, engagement.

## Current Preset Semantics

- No preset: use only manually entered filters.
- Viral Discovery: recent, enough views, like/share quality, score sorting.
- Safe Reup: speech required, manageable duration, medium-or-lower text density, no heavy watermark, no high copyright risk, no high processing complexity.
- Affiliate Priority: medium duration, comment/share quality, medium-or-lower text density, no slideshow/heavy watermark/high copyright risk.

## Fields Added

- `/intake` UI now exposes comments, shares, duration, aggregate engagement rate, speech required/excluded, max text density, heavy watermark exclusion, high processing complexity exclusion, and high copyright risk exclusion.
- Backend `FilterConfig` now supports `min_engagement_rate`, `max_engagement_rate`, and explicit `has_speech`.
- `POST /intake/discover` response now includes `filters_applied_summary` and `unsupported_filters_ignored`.
- Frontend validation now checks non-negative numeric values and min/max ordering for comments, shares, duration, and engagement rate.

## Fields Intentionally Skipped

- Speech density: no field in `ContentSignals` or persisted metadata contract yet.
- Watermark level `none/light/heavy`: only `has_heavy_watermark` boolean is supported.
- Generic risk level: only high/blocking copyright risk exclusion is implemented in candidate filtering.
- Content type: no normalized source-video field or filter contract yet.
- Commercial intent: no normalized source-video field or scoring/filter contract yet.

## Files Touched

- `apps/api/src/api/routes/intake.py`
- `apps/api/src/schemas/candidates.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/services/candidate_filter.py`
- `apps/api/src/services/candidate_types.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/tests/test_candidate_filter_score.py`
- `apps/web/src/app/globals.css`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/lib/intakeState.ts`
- `apps/web/src/test/intake.test.ts`
- `apps/web/src/types/intake.ts`
- `docs/intake-filters-expansion-log.md`
- `docs/intake-filters-expansion-resume.md`
- `docs/intake-filters-spec.md`

## Verification Notes

- `python -m compileall apps/api/src` passed.
- `$env:PYTHONPATH='apps/api'; python -m unittest apps/api/tests/test_candidate_filter_score.py` passed.
- `npm --workspace @reup-douyin/web run typecheck` passed.
- `npm --workspace @reup-douyin/web test` passed.
- `npm --workspace @reup-douyin/web run build` passed.
- Restarted the web dev listener on port 3000 and smoke-checked `/`, `/intake`, `/review-board`, `/ops`, `/ops/publish-health`, `/ops/publish-control`, `/optimization`.
- `GET http://127.0.0.1:8000/filter-presets` returned 200.
- `POST /intake/discover` with invalid comments min/max returned a specific 422 validation error.

## Status

Completed for this step.
