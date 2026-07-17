# Phase 17Y Resume — Whole Profile Staged Harvest V2 Payload Secret-Field Sanitizer

## Objective
Prevent V2 `/douyin-extension/full-modal-harvest` 422 `extension_payload_contains_secret_field` by ensuring backend-bound payload excludes `capture_session_source` and other disallowed/secret-like fields.

## What Was Done
- Added [`sanitizeWholeProfileFullModalPayloadV2()`](apps/extension-douyin-capture/src/popup.ts:1629) and wired it into V2 target processing before flush.
- Added [`assertNoDisallowedPayloadFields()`](apps/extension-douyin-capture/src/popup.ts:1653) preflight guard to block local flush if disallowed fields remain.
- Updated [`buildWholeProfileFullModalRequestV2()`](apps/extension-douyin-capture/src/popup.ts:1381) so backend payload no longer includes `capture_session_source`.
- Kept `capture_session_source` as local runtime/UI diagnostic only (not outbound backend payload).
- Updated V2 catch classification in [`processWholeProfileTargetV2()`](apps/extension-douyin-capture/src/popup.ts:1244) to map backend secret-field errors to `payload_contains_disallowed_field`.
- Updated V2 diagnostics rendering in [`renderWholeProfileStagedHarvestV2()`](apps/extension-douyin-capture/src/popup.ts:1426) to show payload capture-session-source presence (expected false) and removed sanitized fields.
- Updated source assertions in [`modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts:342) for Phase 17Y contract.

## Validation Performed
- Ran extension suite via workspace script chain (`test` includes typecheck/build tail in package script flow).
- Command: `npm --workspace @reup-douyin/extension-douyin-capture run test`
- Result: pass.

## Files Changed
- [`apps/extension-douyin-capture/src/popup.ts`](apps/extension-douyin-capture/src/popup.ts)
- [`apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts)
- [`docs/metadata-phase17Y-v2-payload-secret-field-sanitizer-log.md`](docs/metadata-phase17Y-v2-payload-secret-field-sanitizer-log.md)
- [`docs/metadata-phase17Y-v2-payload-secret-field-sanitizer-resume.md`](docs/metadata-phase17Y-v2-payload-secret-field-sanitizer-resume.md)

## API Touch Status
No API code changes required for this phase; fix is fully at extension payload-shaping boundary.

## Expected Runtime Outcome
V2 staged harvest flush now sends backend-safe payloads. If disallowed fields are detected locally or via backend secret-field rejection signature, failure is classified explicitly as `payload_contains_disallowed_field` rather than generic schema rejection.
