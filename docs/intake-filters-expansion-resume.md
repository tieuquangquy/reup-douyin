# Intake Filters Expansion Resume

## Current Step

Completed: expanded `/intake` filters, preset explanation, API contracts, validation, and docs while preserving the existing discovery flow.

## Done

- Read `AGENTS.md`.
- Read existing intake docs: log, resume, API map.
- Audited backend preset registry, candidate filter types, filter engine, intake schema/route/service, source video models, candidate models, risk taxonomy.
- Audited frontend `/intake`, intake state/types, review board toolbar, review board metrics/risk presentation.
- Created expansion log/resume/spec docs before code changes.
- Added backend support for aggregate engagement-rate filtering and explicit speech tri-state filtering.
- Added applied-filter summary and unsupported-filter summary fields to intake discovery responses.
- Expanded `/intake` UI into source, preset, core metrics, audience signals, and processing suitability groups.
- Added frontend validation and tests for comments, shares, duration, engagement rate, and suitability controls.
- Verified API compile, candidate filter tests, web typecheck, web tests, production build, and live route smoke checks.

## In Progress

- None for this step.

## Next Exact Task

Polish the review board filter and candidate-card wording so the same comments/shares/engagement/suitability semantics are visible after an intake run.

## Key Files To Continue

- `apps/api/src/services/candidate_types.py`
- `apps/api/src/services/candidate_filter.py`
- `apps/api/src/schemas/candidates.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/api/routes/intake.py`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/intakeState.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/intake-filters-spec.md`
- `docs/intake-filters-expansion-log.md`
- `docs/intake-filters-expansion-resume.md`
