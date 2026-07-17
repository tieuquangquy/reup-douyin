# Intake Productivity Log

## Step
Implement `/intake` productivity helpers (saved presets, recent profiles, latest successful fetch shortcuts) while preserving canonical intake/discovery architecture and avoiding duplicated logic.

## Findings
- `/intake` currently has canonical submission flow through [`discover_intake_candidates()`](apps/api/src/api/routes/intake.py:35) and [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:77).
- Existing local-only helper from prior polish is intentionally limited and not backend-canonical for team-visible productivity state.
- Filter semantics are already canonicalized in API request/validation and must not be redefined in UI-only state.
- Existing ingestion entities already contain useful history signals (`source_profiles`, `crawl_sessions`) for recent and latest-success shortcuts.

## Existing Architecture Inventory
- Intake request/response schema: [`IntakeDiscoverRequest`](apps/api/src/schemas/intake.py:10), [`IntakeDiscoverResponse`](apps/api/src/schemas/intake.py:50)
- Intake HTTP boundary: [`/intake/discover`](apps/api/src/api/routes/intake.py:34)
- Intake orchestration and account resolution: [`IntakeDiscoveryService`](apps/api/src/services/intake_discovery_service.py:73)
- Ingestion persistence primitives: [`SourceProfile`](apps/api/src/models/ingestion.py:28), [`CrawlSession`](apps/api/src/models/ingestion.py:63)
- Web intake client and form helpers: [`discoverIntakeCandidates()`](apps/web/src/lib/api.ts:85), [`buildIntakeDiscoverRequest()`](apps/web/src/lib/intakeState.ts:95), [`IntakePage()`](apps/web/src/components/intake/IntakePage.tsx:27)

## Decisions Made
- Docs-first workflow is mandatory before implementation.
- Productivity features will extend canonical intake contracts minimally instead of introducing a second discovery endpoint.
- Saved intake presets will persist backend-side to avoid device-only drift.
- Recent profiles and latest-success shortcuts will be derived from canonical ingestion history.
- `/intake` remains action-first (fill + explicit discover), not an analytics dashboard.

## Non-Goals (This Step)
- No crawler redesign.
- No candidate scoring/filter engine rewrite.
- No queue/job architecture migration.
- No cross-screen dashboard merge into `/intake`.

## Files Touched
- `docs/intake-productivity-log.md`
- `docs/intake-productivity-resume.md`
- `docs/intake-productivity-architecture.md`
- `docs/intake-productivity-user-guide.md`
- `apps/api/src/models/intake.py`
- `apps/api/alembic/versions/0020_intake_saved_presets.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/services/intake_productivity_service.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/tests/test_intake_productivity_service.py`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`

## Verification Notes
- `npm run typecheck` passed.
- `npm --workspace @reup-douyin/web run test` passed.
- `set PYTHONPATH=apps/api&& python -m unittest apps/api/tests/test_intake_productivity_service.py -v` passed.
- `set PYTHONPATH=apps/api&& python -m unittest discover -s apps/api/tests -p "test_intake_discovery_service.py"` passed.

## Status
Completed.
