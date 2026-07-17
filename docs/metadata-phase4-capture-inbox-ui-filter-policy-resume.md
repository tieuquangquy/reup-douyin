# Metadata Phase 4 Capture Inbox UI + Filter Policy Resume

## Current Phase

Phase 4 frontend-only implementation: Capture Inbox metadata usability UX and filter policy alignment to Phase 3 backend fields.

## Completed So Far

1. Read and applied repository guardrails from `AGENTS.md`.
2. Completed frontend audit across:
   - `apps/web/src/types/capture-inbox.ts`
   - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
   - `apps/web/src/lib/captureInboxCanonical.ts`
   - `apps/web/src/test/capture-inbox.test.ts`
3. Documented gaps and Phase 4 UI/filter policy design in:
   - `docs/metadata-phase4-capture-inbox-ui-filter-policy-log.md`
4. Completed Phase 4 frontend implementation in:
   - `apps/web/src/types/capture-inbox.ts`
   - `apps/web/src/components/capture-inbox/CaptureInboxPage.tsx`
   - `apps/web/src/test/capture-inbox.test.ts`
5. Ran targeted frontend verification:
   - `npx tsx apps/web/src/test/capture-inbox.test.ts` (passed)

## Implemented Changes

- Added typed `raw_evidence_summary` to `CapturedItem`.
- Expanded metadata provenance/source unions for Phase 3-compatible literals, including `dom_snapshot`, `existing_canonical`, and `missing` where applicable.
- Added metadata grouping filter controls in Studio filters (`all`, `complete`, `partial`, `needs-metadata`, `failed`) and matching filter logic.
- Added compact grouped metadata missing line on cards to reduce repeated missing-field spam.
- Renamed inspector metadata section to `Metadata quality` and added `Raw evidence` summary row.
- Added advanced filter helper copy for missing metadata behavior.
- Updated focused Capture Inbox test assertions to cover the new metadata UI/filter policy behavior.

## Next Implementation Steps

1. No additional Phase 4 implementation steps pending for this scope.
2. Continue only if a broader regression run is explicitly requested.

## Scope Guardrails

- No edits to `apps/extension-douyin-capture`.
- No backend normalizer logic edits.
- No hydration job/queue implementation.
- Keep cards compact and avoid repeated missing-field spam.
- Do not treat unknown metadata as zero/false.
