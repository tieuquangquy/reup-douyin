# Douyin Intake Account Selection Log

## Step
Implement health-aware account selection for `/intake` with backend-canonical fallback and explainability.

## Findings
- Intake live fetch was previously resolved in `IntakeDiscoveryService._resolve_live_fetch_account_id` with no health-aware fallback.
- Canonical account health projection already exists in `DouyinAccountService.health_summary` and was reused.
- Canonical account usability signal (`can_use_for_live_fetch`) already existed and was used for resolver decisions.
- Web intake now reads backend-resolved selection metadata instead of relying only on local warning heuristics.

## Current Architecture Inventory
- Intake orchestrator: `apps/api/src/services/intake_discovery_service.py`
- Intake HTTP route/schema: `apps/api/src/api/routes/intake.py`, `apps/api/src/schemas/intake.py`
- Canonical account health: `apps/api/src/services/douyin_account_service.py`
- Canonical account contracts: `apps/api/src/schemas/douyin_accounts.py`
- Intake UI and client contracts: `apps/web/src/components/intake/IntakePage.tsx`, `apps/web/src/types/intake.ts`, `apps/web/src/lib/intakeState.ts`, `apps/web/src/lib/api.ts`
- Existing intake tests: `apps/api/tests/test_intake_discovery_service.py`

## Decisions Made
- Backend will be canonical source for final account resolution.
- Intake request semantics:
  - `selected_account_id` = operator-selected candidate (or null when “use default”).
  - `resolved_account_id` = account actually used for live fetch after backend policy.
- Fallback is explicit, never silent:
  - response includes `selection_mode`, `selection_reason`, and `fallback_notice`.
- Policy reuse only:
  - no duplicate health engine in intake service;
  - reuse `DouyinAccountService` health projection and account list ordering/data.

## Policy Draft (V1)
- Usable for live fetch: `HEALTHY`, `STALE`, `EXPIRING_SOON`.
- Unusable for live fetch: `INVALID`, `EXPIRED`, `BLOCKED`, `DISABLED`, `UNKNOWN`.
- Ranking priority among usable accounts:
  1. Operator-selected usable account.
  2. Default usable account.
  3. Best-health usable account by deterministic rank: `HEALTHY` > `STALE` > `EXPIRING_SOON`, then newest `last_successful_validation_at`, then newest `updated_at`.
- If no usable account exists, return actionable 422 error with CTA guidance to `/accounts/douyin`.

## Files Touched
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/types/intake.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
- `docs/douyin-intake-account-selection-log.md`
- `docs/douyin-intake-account-selection-resume.md`
- `docs/douyin-intake-account-selection-architecture.md`
- `docs/douyin-intake-account-selection-user-guide.md`

## Verification Notes
- API tests passed:
  - `python -m unittest tests.test_intake_discovery_service` (run in `apps/api`)
- Web typecheck passed:
  - `npm run typecheck` (run in `apps/web`)

## Status
Implemented and verified for targeted scope.
