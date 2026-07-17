# Phase 18I-F Backend Session + Payload Guard Resume

## Current State
Phase 18I-F is implemented and validated in the extension whole-profile harvest flow:
- The active run path still uses extraction-only mode [`real_modal_extraction_no_backend`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:659).
- The run now creates or reuses a canonical capture session through [`createCanonicalHarvestSession()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:521).
- Extracted targets now build a sanitized payload preview with local guard evaluation in [`checkpointLocalHarvestTarget()`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts:1097).
- Progress output now exposes capture-session and payload-preview diagnostics in [`wholeProfileProgressSummary()`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts:3).
- Popup status strings now describe preview/session behavior rather than pure extraction-only wording in [`popup.ts`](apps/extension-douyin-capture/src/popup.ts).
- No real backend item flush is allowed in this phase.
- No Capture Inbox items are created in the active path.
- Validation commands completed successfully for the current edits.

## What Was Delivered
- Nested backend session/preview state in [`state.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/state.ts).
- Sanitizer, raw evidence summary builder, payload preview builder, and recursive local guard in [`canonicalHarvest.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/canonicalHarvest.ts).
- Canonical session preflight plus preview-only extraction-path integration in [`controller.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).
- Progress and popup visibility updates in [`progress.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest/progress.ts) and [`popup.ts`](apps/extension-douyin-capture/src/popup.ts).
- Test updates in [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts).

## Remaining Work
1. Only touch API capture-session support if a future validation pass proves the existing `whole_profile_harvest` source contract is insufficient.
2. Keep later phases scoped to reintroducing real backend submission separately from this preview-only Phase 18I-F baseline.

## Validation Snapshot
- [`npm --workspace @reup-douyin/extension-douyin-capture run typecheck`](apps/extension-douyin-capture/package.json): passed.
- [`npm --workspace @reup-douyin/extension-douyin-capture run test`](apps/extension-douyin-capture/package.json): passed.
- [`wholeProfileHarvest.test.ts`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts) expectations were aligned with the sanitizer allowlist behavior, including removed-field reporting for [`$.profile_card_evidence.aweme_id`](apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts:246).

## Guardrails
- Do not add a real call to [`/douyin-extension/full-modal-harvest`](apps/extension-douyin-capture/src/popup.ts).
- Do not create Capture Inbox items.
- Do not switch to legacy runtime or V2 staged-harvest logic.
- Keep work scoped to Phase 18I-F preview/session behavior only.
