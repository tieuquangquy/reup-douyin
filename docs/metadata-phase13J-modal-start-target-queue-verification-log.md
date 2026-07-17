# Phase 13J Modal-Start Target Queue Verification Log

## Scope

Phase 13J is limited to the extension workspace in [`apps/extension-douyin-capture`](apps/extension-douyin-capture) and phase documentation in [`docs`](docs). It adds modal-start queue resolution and target-coverage verification for Smart Capture & Harvest without changing backend APIs, queue architecture, or worker responsibilities.

## Problem

Smart Capture & Harvest could be started while the active tab was a Douyin modal URL, but if the extension did not already have a known capture session + target queue, the operator had no explicit, guided modal-start resolution path and no dedicated popup diagnostic to verify whether the current modal could safely run the selected harvest mode.

## Implementation Summary

### 1) Modal URL resolution and queue-aware start behavior

In [`runSmartCaptureHarvest()`](apps/extension-douyin-capture/src/popup.ts:333), popup startup now branches by page type and queue knowledge:

- Parse modal context with [`getProfileUrlFromModalUrl()`](apps/extension-douyin-capture/src/modalStart.ts:23).
- Gate modal-start profile capture resolution using [`hasKnownTargetQueue()`](apps/extension-douyin-capture/src/modalStart.ts:42).
- Persist interim state `current_state: "resolving_profile_queue"` before resolving profile queue from a modal start.

If started from modal and queue is unknown, the popup runs [`resolveProfileQueueFromModal()`](apps/extension-douyin-capture/src/popup.ts:1290), which:

1. Navigates to `profile_url_without_modal_id`.
2. Waits deterministically with [`waitForActiveTabUrl()`](apps/extension-douyin-capture/src/popup.ts:1307).
3. Executes profile capture via [`runCaptureCurrentPage()`](apps/extension-douyin-capture/src/popup.ts:1316).
4. Restores the original modal URL in `finally` and waits again.

This guarantees queue resolution does not strand the operator away from modal context.

### 2) Hard queue precondition before modal harvest start

Before invoking harvest start, popup enforces queue presence and blocks with:

- `Target queue missing; resolve profile queue before modal harvest.`

This guard exists in [`runSmartCaptureHarvest()`](apps/extension-douyin-capture/src/popup.ts:572).

### 3) Current-modal coverage behavior for selected mode

Coverage evaluation is centralized in [`buildModalHarvestCoverage()`](apps/extension-douyin-capture/src/modalStart.ts:46), including reasons for blocked starts:

- Missing/invalid modal URL.
- Missing capture session.
- Missing target queue.
- Current modal excluded from selected target queue.

If the current modal is not in queue, Smart Capture completes as no-op with explicit status messaging in [`runSmartCaptureHarvest()`](apps/extension-douyin-capture/src/popup.ts:415).

### 4) Verify Modal Harvest Coverage popup action

Added dedicated operator action:

- Button in [`popup.html`](apps/extension-douyin-capture/public/popup.html) with `id="verifyModalHarvestCoverageButton"`.
- Production ID registry update in [`PRODUCTION_BUTTON_IDS`](apps/extension-douyin-capture/src/popupWorkflow.ts:19).
- Handler in [`verifyModalHarvestCoverageFromPopup()`](apps/extension-douyin-capture/src/popup.ts:734) to render formatted coverage diagnostics via [`formatModalHarvestCoverage()`](apps/extension-douyin-capture/src/modalStart.ts:86).

## Test Coverage Added/Updated

- New direct modal-start helper coverage: [`modalStart.test.ts`](apps/extension-douyin-capture/src/modalStart.test.ts).
- Smart workflow contract assertions: [`popupSmartWorkflow.test.ts`](apps/extension-douyin-capture/src/popupSmartWorkflow.test.ts).
- Popup UI/contract assertions (button presence + source wiring): [`popupWorkflow.test.ts`](apps/extension-douyin-capture/src/popupWorkflow.test.ts).
- Test script includes new suite in [`package.json`](apps/extension-douyin-capture/package.json:8).

## Verification Commands

All required extension checks passed from repository root:

- `npm --workspace @reup-douyin/extension-douyin-capture run typecheck`
- `npm --workspace @reup-douyin/extension-douyin-capture run test`
- `npm --workspace @reup-douyin/extension-douyin-capture run build`

## Non-Goals Preserved

Phase 13J does **not** introduce crawler logic, scoring/filtering logic, worker orchestration changes, schema redesign, or auto-publish behavior. It remains a popup-side orchestration and operator-verification hardening step.
