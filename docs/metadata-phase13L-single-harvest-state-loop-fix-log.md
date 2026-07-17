# Phase 13L single harvest state and loop-owner fix log

## Scope

Phase 13L is limited to `apps/extension-douyin-capture` smart-harvest state storage, popup state derivation, and extension tests. No backend API contracts, crawler logic, extraction algorithm behavior, queue infrastructure, or web app modules were changed.

## Root cause

Two coupled ownership problems caused unstable operator state:

1. Smart state was transitioning from legacy key usage (`douyinSmartCaptureHarvestState`) while canonical migration targeted `douyinSmartHarvestState`. During transition, popup read/write paths could disagree on source-of-truth.
2. Popup status header and harvest panel could diverge because header relied on stored smart state while panel reflected live harvest progress normalization. This created inconsistent operator guidance when runtime progress had advanced but stored state had not yet reconciled.

## Canonical storage migration

Canonical state key is now `douyinSmartHarvestState`.

- Canonical key source constants are centralized in `storageKeys.ts`.
- Popup runtime reads canonical first and supports legacy fallback for migration-safe restore.
- Legacy dual-write was removed from popup save path; new writes persist only canonical key.
- Reset and workflow key references were aligned to canonical key naming.

## Single UI derivation path

`renderOperationalStatus()` now computes runtime-effective smart state from normalized harvest progress before presenting status summary fields.

This ensures:

- `Current state`
- `Next required action`
- `Last error`

are aligned with runtime progression, reducing header/panel contradictions.

## Loop-owner semantics

Loop ownership remains in content script/controller (`FullModalHarvestController` lifecycle). Popup derives and renders state but does not become harvest-loop authority. This prevents popup lifecycle artifacts from being interpreted as controller pause/failure ownership.

## Files changed

- `apps/extension-douyin-capture/src/storageKeys.ts`
- `apps/extension-douyin-capture/src/popupWorkflow.ts`
- `apps/extension-douyin-capture/src/extensionReset.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupSmartWorkflow.test.ts`

## Validation

Executed successfully:

```bash
npm run -w apps/extension-douyin-capture test
```

The command includes extension tests, build, and dist module-resolution verification.

## Operator verification checklist

1. Reload extension build.
2. Open popup with existing canonical smart state and verify status summary fields reflect harvest runtime updates.
3. Verify no new writes are produced under legacy key `douyinSmartCaptureHarvestState`.
4. Resume/stop/flush harvest and confirm popup panel + status header remain semantically aligned.
5. Reopen popup during active harvesting and confirm controller loop ownership remains stable.
