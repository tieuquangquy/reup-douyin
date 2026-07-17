# Intake Existing Data Bug Resume

## Current Step
Completed: fix `/intake` existing-data reuse so empty/unusable profiles fall through to live fetch.

## Done
- Audited `apps/api/src/services/intake_discovery_service.py`.
- Audited `apps/api/src/schemas/intake.py`.
- Audited `/intake` UI state/types/components.
- Confirmed root cause: existing `SourceProfile` identity match is reused without video/crawl usability checks.
- Added backend `force_live_refresh` support.
- Added backend reusable-profile guard:
  - must have source videos
  - latest crawl must not be failed
- Added explicit fetch modes:
  - `existing_data`
  - `live_fetch`
  - `forced_live_fetch`
- Added `/intake` `Force live refresh` checkbox.
- Added focused API service tests and updated web intake state test.
- Verified API unit tests, web tests, web typecheck, i18n JSON, and runtime smoke.

## In Progress
- None.

## Next Exact Task
If the real Douyin profile still returns zero videos after this fix, run the same profile with `Force live refresh` enabled and inspect live fetch output/config (`DOUYIN_SESSION_COOKIE`, `DOUYIN_PROXY_URL`) because the backend will no longer reuse an empty existing profile.

## Key Files To Continue
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/src/api/routes/intake.py`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/intakeState.ts`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `apps/web/src/test/intake.test.ts`
