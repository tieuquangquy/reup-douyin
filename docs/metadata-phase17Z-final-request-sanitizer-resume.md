# Phase 17Z Resume — Final Request Sanitizer at Fetch Boundary

## Objective
Fix V2 contradiction where UI showed sanitized payload but backend still rejected `payload.capture_session_source` by sanitizing/asserting the exact final request body immediately before fetch.

## Implemented
- Added deep recursive inspector [`findDisallowedPayloadFields()`](apps/extension-douyin-capture/src/popup.ts:1661).
- Added deep recursive final-body sanitizer [`sanitizeFinalFullModalHarvestRequestBodyV2()`](apps/extension-douyin-capture/src/popup.ts:1681).
- Updated [`flushWholeProfileFinalizedPayloadV2()`](apps/extension-douyin-capture/src/popup.ts:1422) to:
  - capture `finalRequestBodyBeforeSanitize`
  - sanitize final body
  - assert no disallowed fields remain
  - block request locally if still present
  - send sanitized `finalBody` only
- Updated failure mapping in [`processWholeProfileTargetV2()`](apps/extension-douyin-capture/src/popup.ts:1308) to distinguish:
  - local: `payload_contains_disallowed_field_local`
  - backend: `payload_contains_disallowed_field_backend`
- Updated V2 diagnostics render in [`renderWholeProfileStagedHarvestV2()`](apps/extension-douyin-capture/src/popup.ts:1426) to include final request truth fields.
- Updated source assertions in [`modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts:334).

## Contract outcome
For V2 full-modal flush, final request retains required fields (e.g. `capture_session_id`, `commit_policy`, item identity/metrics) and must not contain `capture_session_source` at any depth.

## Verification commands
- `npm --workspace @reup-douyin/extension-douyin-capture run test` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck` ✅
- `npm --workspace @reup-douyin/extension-douyin-capture run build` ✅

## Files changed
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts)
- [`docs/metadata-phase17Z-final-request-sanitizer-log.md`](docs/metadata-phase17Z-final-request-sanitizer-log.md)
- [`docs/metadata-phase17Z-final-request-sanitizer-resume.md`](docs/metadata-phase17Z-final-request-sanitizer-resume.md)
