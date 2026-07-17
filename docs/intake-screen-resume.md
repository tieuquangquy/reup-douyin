# Intake Screen Resume

## Current Step

Completed `/intake` as the Operator Studio entry for Douyin profile intake and candidate discovery.

## Done

- Read repository instructions from `AGENTS.md`.
- Audited `apps/web` route/navigation structure.
- Audited `apps/api` source ingest and candidate filter endpoints/services.
- Chosen minimal API orchestration strategy: add `POST /intake/discover` and reuse existing services.
- Created intake log/resume/API map docs before code changes.
- Added backend intake schema/service/route and included the router in FastAPI.
- Replaced the `/intake` placeholder with a real Operator Studio form.
- Added frontend intake types/helper/API client wiring.
- Added `/intake` to Operator sidebar, topbar quick actions, and Operator Home quick launch.
- Added intake state tests and updated nav/home tests.
- Verified typecheck, tests, API compile, Next build, and live smoke.

## In Progress

- None for this step.

## Next Exact Task

Recommended next UI step: polish review-board intake feedback, such as a small banner when opened with `?fresh=1`, optional source-profile filtering from the intake result, and clearer live/fallback fetch state.

## Key Files To Continue

- `apps/api/src/api/routes/intake.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/main.py`
- `apps/web/src/app/intake/page.tsx`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/api.ts`
- `apps/web/src/lib/navigationConfig.ts`
- `apps/web/src/lib/operatorHomeState.ts`
- `docs/intake-screen-log.md`
- `docs/intake-screen-api-map.md`
