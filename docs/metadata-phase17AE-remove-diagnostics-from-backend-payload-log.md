# Phase 17AE Remove Diagnostics From Backend Payload Log

Date: 2026-05-05
Status: Completed

## Scope

- Harden the extension V2 whole-profile full-modal harvest backend write path for [`/douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/extensionBackendClient.ts:90).
- Remove backend-bound `diagnostics`, `debug`, `state`, `runtime`, and secret-like fields from full-modal harvest payloads.
- Keep Phase 17AE scoped to [`apps/extension-douyin-capture`](apps/extension-douyin-capture) and docs; no backend schema, database, queue, crawler, or publishing changes were introduced.

## Problem

The full-modal harvest flow needed an explicit transport boundary that guarantees the final backend request body is a safe contract payload rather than an operational/debug snapshot. Phase 17AE closes that gap by ensuring only a V2 popup direct flow can submit full-modal harvest data and by blocking disallowed fields locally before `fetch`.

## Implementation Summary

1. Added a central full-modal guard in [`guardFullModalHarvestRequestBody()`](apps/extension-douyin-capture/src/extensionBackendClient.ts:90).
2. Wired the guard into [`postBackendJson()`](apps/extension-douyin-capture/src/extensionBackendClient.ts:115) for every [`/douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/extensionBackendClient.ts:115) request.
3. Enforced V2-only caller provenance with the allowed caller [`whole_profile_staged_harvest_v2_direct`](apps/extension-douyin-capture/src/popup.ts:1563).
4. Required final request body preview and final request fingerprint before transport in [`flushWholeProfileFinalizedPayloadV2Direct()`](apps/extension-douyin-capture/src/popup.ts:1520).
5. Added the allowlist-only V2 request builder [`buildWholeProfileFullModalHarvestRequestBodyV2Safe()`](apps/extension-douyin-capture/src/popup.ts:1459).
6. Added final request sanitization through [`sanitizeFinalFullModalHarvestRequestBodyV2()`](apps/extension-douyin-capture/src/popup.ts:1940) and recursive disallowed-field checks through [`findDisallowedPayloadFields()`](apps/extension-douyin-capture/src/popup.ts:1923).
7. Sanitized profile-card evidence through [`sanitizeProfileCardEvidenceV2()`](apps/extension-douyin-capture/src/popup.ts:1584) and raw profile-card data through [`sanitizeProfileCardRawV2()`](apps/extension-douyin-capture/src/popup.ts:1602).
8. Blocked legacy/non-V2 content-script full-modal flushing in [`flushPendingRuntimeItems()`](apps/extension-douyin-capture/src/contentScript.ts:1130) with a deterministic local pause reason.
9. Made backend-bound full-modal payload diagnostics optional at the type boundary in [`FullModalHarvestRequestPayload`](apps/extension-douyin-capture/src/types.ts:1287), because V2 backend payloads intentionally omit diagnostics.
10. Added direct guard coverage in [`extensionBackendClient.test.ts`](apps/extension-douyin-capture/src/extensionBackendClient.test.ts:1).
11. Updated architecture/source-string coverage in [`modalWholeProfileTest.test.ts`](apps/extension-douyin-capture/src/modalWholeProfileTest.test.ts:1), [`background.test.ts`](apps/extension-douyin-capture/src/background.test.ts:1), and [`popupSmartWorkflow.test.ts`](apps/extension-douyin-capture/src/popupSmartWorkflow.test.ts:1).

## Guarded Payload Contract

Allowed top-level full-modal harvest payload keys are limited to the backend contract fields required for finalized V2 harvest writes:

- `schema_version`
- `capture_session_id`
- `run_id`
- `profile_url`
- `target_aweme_id`
- `source_video_external_id`
- `started_at`
- `page`
- `capture_context`
- `items`
- `progress`
- `commit_policy`

The guard recursively blocks `diagnostics`, `debug`, `state`, `runtime`, capture-session source aliases, and secret-like keys such as `token`, `api_key`, `cookie`, `authorization`, and `password`.

## Error Surfacing

The popup V2 direct path now separates local payload blocks from backend schema rejects:

- `payload_contains_disallowed_field_local`
- `payload_contains_disallowed_field_backend`
- `backend_schema_rejected`
- `capture_session_not_found`
- `finalized_metadata_required`
- `backend_network_error`

This keeps operator-facing runtime status actionable and avoids conflating local sanitization failure with backend validation failure.

## Verification

Executed from [`apps/extension-douyin-capture`](apps/extension-douyin-capture):

```text
npm run typecheck && npm run build && npm test
```

Result: pass, exit code `0`.

Successful coverage included typecheck, extension build, existing extractor/network/modal/popup/background/runtime tests, new full-modal backend guard tests, and dist module resolution.

## Non-Goals

- No crawler implementation.
- No video processing implementation.
- No backend schema/database/queue changes.
- No auto-publish integration.
- No broad UI redesign beyond error/status surfacing required by Phase 17AE.
