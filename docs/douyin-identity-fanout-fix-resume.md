# Douyin Identity Fan-out Fix Resume

## Current Task

Hard-fix the Douyin capture pipeline identity/mapping/fan-out bug so each captured item is bound to the correct `aweme_id`, network JSON is merged only into the matching item, duplicate fan-out is prevented, and thumbnail/posted/stats are taken from the correct real item.

## Implementation Checklist

- [x] Re-read repository rules in `AGENTS.md`.
- [x] Audit extension DOM extraction, network cache, backend staging/serialization, and frontend rendering identity paths.
- [x] Create docs first for the identity fan-out fix.
- [x] Refactor extension canonical item storage around `Map<aweme_id, CanonicalItem>`.
- [x] Harden DOM-to-network merge so both sides must have the same non-empty `aweme_id`.
- [x] Add anti-fan-out safeguards and suspicious duplicate payload diagnostics.
- [x] Add backend batch-level identity/fan-out diagnostics.
- [x] Add frontend stable-render regression coverage.
- [x] Add focused extension/backend/frontend tests.
- [x] Run verification commands.
- [x] Update docs with final result and limitations.

## Key Findings

- The main risk was at the extension merge boundary: the caller looked up network records by DOM ID, but `mergeDomAndNetworkVideo()` did not independently guard mismatched IDs.
- Network cache and injected page hook flows needed explicit invalid-ID filtering and cloned array/object outputs to reduce reference-sharing risk.
- Backend staging preserved one item per payload, but needed provenance schema fields and a batch-level warning when distinct IDs shared network-backed metadata signatures.
- Frontend rendering already used stable backend item IDs, but tests now explicitly guard stable key/focus identity and item-local metadata resolution.

## Files Changed

- `apps/extension-douyin-capture/src/types.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/networkCache.ts`
- `apps/extension-douyin-capture/src/pageNetworkHook.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/extractor.test.ts`
- `apps/api/src/schemas/douyin_extension.py`
- `apps/api/src/schemas/capture_inbox.py`
- `apps/api/src/services/capture_inbox_service.py`
- `apps/api/tests/test_douyin_extension_capture_service.py`
- `apps/web/src/types/capture-inbox.ts`
- `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
- `apps/web/src/test/capture-inbox.test.ts`
- `apps/web/src/test/capture-inbox-canonical.test.ts`
- `docs/douyin-identity-fanout-fix-log.md`
- `docs/douyin-identity-fanout-fix-resume.md`
- `docs/douyin-identity-fanout-fix-architecture.md`

## Verification Results

Passed:

- `npm --prefix apps/extension-douyin-capture test`
- `python -m unittest tests.test_douyin_extension_capture_service` from `apps/api`
- `npx tsx src/test/capture-inbox.test.ts && npx tsx src/test/capture-inbox-canonical.test.ts` from `apps/web`
- `npm --prefix apps/web run typecheck`

## Resume State

No pending implementation work remains for this task. Future work should treat `suspicious_duplicate_payload_mapping` as an operator/debug warning and should not convert it to a blocking error unless product requirements explicitly require stricter capture rejection.
