# Intake Productivity Architecture

## Objective
Add lightweight `/intake` productivity helpers that reduce repetitive operator setup while preserving canonical discovery behavior and data contracts.

## Scope
- Saved intake presets (operator-defined reusable setup templates).
- Recent profiles (recently used source profile URLs/IDs for quick refill).
- Latest successful fetch shortcuts (prefill from last known-good intake fetch context, but still require explicit discover action).

## Canonical Boundaries
- Discovery execution remains canonical in [`IntakeDiscoveryService.discover()`](apps/api/src/services/intake_discovery_service.py:77).
- HTTP discover boundary remains [`POST /intake/discover`](apps/api/src/api/routes/intake.py:34).
- Filter semantics remain canonical in [`IntakeDiscoverRequest`](apps/api/src/schemas/intake.py:10) and existing filter models.
- Source history signals are reused from canonical ingestion entities ([`SourceProfile`](apps/api/src/models/ingestion.py:28), [`CrawlSession`](apps/api/src/models/ingestion.py:63)).

## No-Duplication Strategy
- Do not duplicate filter interpretation logic in UI.
- Do not add parallel discovery orchestration endpoint.
- Do not create ad hoc profile-history store detached from ingestion data.
- Keep one source of truth for account-resolution and live-fetch result semantics in backend intake service.

## Concrete Implementation Plan (No-Duplication)

### Backend API Surface
- Add productivity bootstrap endpoint: [`GET /intake/bootstrap`](apps/api/src/api/routes/intake.py:34)
  - Returns one compact payload for initial `/intake` load:
    - saved presets (persisted)
    - recent profiles (derived from canonical source profiles)
    - latest successful fetch shortcuts (derived from canonical crawl sessions)
- Add saved preset endpoints:
  - [`GET /intake/saved-presets`](apps/api/src/api/routes/intake.py:34)
  - [`POST /intake/saved-presets`](apps/api/src/api/routes/intake.py:34)
  - [`PATCH /intake/saved-presets/{preset_id}`](apps/api/src/api/routes/intake.py:34)
  - [`DELETE /intake/saved-presets/{preset_id}`](apps/api/src/api/routes/intake.py:34)

### Backend Persistence
- Add new model `IntakeSavedPreset` in [`apps/api/src/models/intake.py`](apps/api/src/models/intake.py) with:
  - `workspace_id`
  - `name` (unique within workspace)
  - `profile_url`
  - `preset_name`
  - `filter_config_json` (canonical intake-compatible fields only)
  - `douyin_account_connection_id` (nullable)
  - `force_live_refresh`
  - optional `notes`
- Add Alembic migration for table + workspace/name uniqueness.
- Keep recent/latest-success data fully derived from existing [`SourceProfile`](apps/api/src/models/ingestion.py:28) and [`CrawlSession`](apps/api/src/models/ingestion.py:63), with no duplicate history table.

### Backend Services and Contracts
- Add `IntakeProductivityService` (new file) to centralize:
  - bootstrap aggregation queries
  - saved preset CRUD validation
  - conversion between JSON payload and canonical filter config request shape
- Extend intake schemas in [`apps/api/src/schemas/intake.py`](apps/api/src/schemas/intake.py:10) with:
  - saved preset request/response models
  - bootstrap response model
  - recent profile / latest-success shortcut response models
- Keep discover semantics unchanged in [`IntakeDiscoverRequest`](apps/api/src/schemas/intake.py:10).

### Web API and State
- Extend [`apps/web/src/lib/api.ts`](apps/web/src/lib/api.ts:85) with intake productivity API functions.
- Extend [`apps/web/src/types/intake.ts`](apps/web/src/types/intake.ts:1) with bootstrap/saved-preset types.
- Extend [`apps/web/src/lib/intakeState.ts`](apps/web/src/lib/intakeState.ts:95) with helper mappers to apply shortcut/preset into [`IntakeFormValues`](apps/web/src/types/intake.ts:64).

### `/intake` UX Composition
- Add compact side panels in [`IntakePage()`](apps/web/src/components/intake/IntakePage.tsx:27):
  - Saved Presets (apply/save/rename/delete)
  - Recent Profiles (apply to form)
  - Latest Successful Fetch (apply to form)
- Preserve explicit discover submit path in [`submit()`](apps/web/src/components/intake/IntakePage.tsx:95).
- Keep old localStorage recent helper only as fallback if bootstrap unavailable.

## UI Interaction Model (`/intake`)
- Add three compact panels near existing source/preset area:
  - Saved Presets
  - Recent Profiles
  - Latest Successful Fetch
- Selecting any shortcut only prefills form fields.
- Discover still requires explicit submit via current form action.

## Data Safety and UX Guardrails
- Never auto-submit discover from shortcut click.
- Surface stale or unavailable shortcut data safely.
- Preserve current account/fallback explainability in status panel.

## Verification Strategy
- API tests for bootstrap derivation and preset CRUD behavior.
- Web wiring tests for prefill behavior and explicit-discover guardrail.
- Typecheck + focused test runs + smoke of `/intake`.

## Implemented Verification
- Added [`IntakeProductivityServiceTests`](apps/api/tests/test_intake_productivity_service.py:12) for bootstrap aggregation, duplicate preset-name protection, not-found update guard, and latest-success mapping.
- Re-ran existing intake discovery safety coverage in [`IntakeDiscoveryServiceTests`](apps/api/tests/test_intake_discovery_service.py:38).
- Re-ran web state coverage in [`intake.test.ts`](apps/web/src/test/intake.test.ts:1) and full web state suite.

## Non-Goals
- Multi-user tenancy policy expansion.
- Background intake job mode migration.
- Review board redesign.
