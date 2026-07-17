# Intake 500 Root Cause Log

## Step: stop `/intake` generic 500 and fix the real discovery failure

Started: 2026-04-23

Status: completed

## Exact Reproduction

1. Open `/accounts/douyin`.
2. Use a manually imported Douyin account that appears healthy in the UI.
3. Open `/intake`.
4. Submit a Douyin profile with:
   - `force_live_refresh=true`
   - `douyin_account_connection_id=<manual account id>`
5. The UI shows:
   - `Discovery failed: Failed to discover intake candidates: 500`

## Exact Backend Root Cause

Reproduced through a direct service call and through `POST /intake/discover`.

Traceback root exception:

```text
TypeError: SourceIngestService.ingest_profile() got an unexpected keyword argument 'adapters'
```

Failing location:

- `apps/api/src/services/intake_discovery_service.py`

Failing stage:

- canonical live fetch -> source ingest handoff

## Why It Became A Generic 500

- The exception was thrown before the code path converted the failure into `IntakeDiscoveryError`.
- FastAPI therefore returned a raw internal server error instead of a classified domain error.

## Secondary Risk Identified

- Manual-imported accounts appear to store session material that may be a JSON cookie export rather than a ready-to-send Cookie header string.
- Even after the `TypeError` is fixed, this can still make live fetch fragile or inconsistent unless normalized into the canonical runtime shape.

## Decisions

- Fix the real live-fetch wiring bug first.
- Add structured intake discovery error mapping with:
  - `code`
  - `message`
  - `stage`
  - `diagnostics_id`
- Normalize manual import session input into a canonical Cookie header string.
- Keep one canonical:
  - `DouyinAccountConnection`
  - `IntakeDiscoveryService`
  - `SourceIngestService`
  - `SourceProfile` / `SourceVideo` / `VideoCandidate` pipeline

## Files Touched

- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/douyin_account_service.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/tests/test_douyin_account_service.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/types/intake.ts`
- `docs/intake-500-root-cause-log.md`
- `docs/intake-500-root-cause-resume.md`
- `docs/intake-500-root-cause-architecture.md`
- `docs/intake-500-troubleshooting.md`

## Verification Notes

- Before the fix, `POST /intake/discover` returned HTTP 500 with an empty body in the reproduced case.
- Focused tests passed:
  - `python -m unittest tests.test_douyin_account_service tests.test_intake_discovery_service`
- API compile sanity passed:
  - `python -m compileall src`
- Web typecheck passed:
  - `npm --workspace @reup-douyin/web run typecheck`
- Reproduced original request after the fix:
  - `POST /intake/discover` returned `200`
  - response now includes `diagnostics_id`
  - no generic 500
- Reproduced classified failure after the fix:
  - invalid account id now returns `422`
  - payload includes `code=account_resolution_failed`, `stage=resolve_account`, `diagnostics_id=<uuid>`
