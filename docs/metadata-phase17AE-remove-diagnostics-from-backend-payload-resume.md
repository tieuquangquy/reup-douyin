# Phase 17AE Remove Diagnostics From Backend Payload Resume

Date: 2026-05-05
Status: Completed

## Scope Lock

- Completed Phase 17AE hardening for extension full-modal harvest backend payloads.
- Primary touched area: [`apps/extension-douyin-capture`](apps/extension-douyin-capture).
- Documentation added under [`docs`](docs).
- No backend, database, crawler, queue, worker, or publishing implementation was added.

## Completed Implementation

1. Central full-modal harvest request guard added in [`guardFullModalHarvestRequestBody()`](apps/extension-douyin-capture/src/extensionBackendClient.ts:90).
2. Guard invoked from [`postBackendJson()`](apps/extension-douyin-capture/src/extensionBackendClient.ts:115) for [`/douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/extensionBackendClient.ts:115).
3. V2-only caller enforcement added for [`whole_profile_staged_harvest_v2_direct`](apps/extension-douyin-capture/src/popup.ts:1563).
4. Safe allowlist-only backend request builder added in [`buildWholeProfileFullModalHarvestRequestBodyV2Safe()`](apps/extension-douyin-capture/src/popup.ts:1459).
5. Final request body preview and request fingerprint are required before fetch in [`flushWholeProfileFinalizedPayloadV2Direct()`](apps/extension-douyin-capture/src/popup.ts:1520).
6. Recursive final-body sanitization added in [`sanitizeFinalFullModalHarvestRequestBodyV2()`](apps/extension-douyin-capture/src/popup.ts:1940).
7. Recursive local disallowed-field detection added in [`findDisallowedPayloadFields()`](apps/extension-douyin-capture/src/popup.ts:1923).
8. Profile-card evidence and raw profile-card data are sanitized through [`sanitizeProfileCardEvidenceV2()`](apps/extension-douyin-capture/src/popup.ts:1584) and [`sanitizeProfileCardRawV2()`](apps/extension-douyin-capture/src/popup.ts:1602).
9. Legacy content-script full-modal runtime flush is blocked in [`flushPendingRuntimeItems()`](apps/extension-douyin-capture/src/contentScript.ts:1130), directing operators to popup V2 staged harvest.
10. Type contract updated so [`FullModalHarvestRequestPayload`](apps/extension-douyin-capture/src/types.ts:1287) no longer requires backend-bound diagnostics.
11. New direct guard test added at [`extensionBackendClient.test.ts`](apps/extension-douyin-capture/src/extensionBackendClient.test.ts:1).
12. Existing source-string and transport tests updated in [`modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts:1), [`background.test.ts`](apps/extension-douyin-capture/src/background.test.ts:1), and [`popupSmartWorkflow.test.ts`](apps/extension-douyin-capture/src/popupSmartWorkflow.test.ts:1).

## Validation Evidence

Latest successful command from [`apps/extension-douyin-capture`](apps/extension-douyin-capture):

```text
npm run typecheck && npm run build && npm test
```

Result: pass, exit code `0`.

Key passing outputs included:

- extension extractor tests passed
- modal whole-profile beta tests passed
- background backend post and cdp lifecycle tests passed
- popup smart capture and harvest workflow tests passed
- harvest runtime v2 tests passed
- extension backend full-modal guard tests passed
- extension dist module resolution tests passed

## Operational Notes

- Backend-bound V2 full-modal payloads must not include `diagnostics`, `debug`, `state`, `runtime`, capture-session source aliases, or secret-like fields.
- Full-modal transport requires caller context, final body preview, and final request fingerprint.
- Non-V2 full-modal caller paths should remain blocked until a future phase explicitly designs and tests another safe backend-bound contract path.
- Local payload block errors should continue to surface separately from backend schema rejects.

## Next-Step Recommendation

If Phase 17AF or a later phase resumes from here, start with regression validation around [`guardFullModalHarvestRequestBody()`](apps/extension-douyin-capture/src/extensionBackendClient.ts:90) and [`flushWholeProfileFinalizedPayloadV2Direct()`](apps/extension-douyin-capture/src/popup.ts:1520), then decide whether additional full-modal writers are needed. Do not unblock legacy content-script full-modal flushing without a new allowlisted request builder, caller context, final preview, final fingerprint, and focused tests.
