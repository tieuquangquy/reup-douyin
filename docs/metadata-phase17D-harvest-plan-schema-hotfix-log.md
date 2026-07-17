# Phase 17D Harvest Plan Schema Hotfix Log

## Scope

Phase 17D is a narrow extension-only hotfix for the harvest-plan request schema version mismatch. The backend endpoint `/douyin-extension/harvest-plan` expects `douyin_extension_harvest_plan.v1`, while the extension was previously forwarding the captured page payload schema `douyin_extension_capture.v1` to that endpoint.

## Root Cause

The popup profile scan helper reused the raw `ExtensionCapturePayload` returned by the content script/direct execution capture path for both `/douyin-extension/capture-current-page` and `/douyin-extension/harvest-plan`. That raw payload is correct for capture-current-page, but its `schema_version` is `douyin_extension_capture.v1`, which violates the harvest-plan endpoint contract.

## Changes

- Added centralized schema constants and endpoint-specific request builders in `apps/extension-douyin-capture/src/requestPayloads.ts`.
- Routed `/douyin-extension/harvest-plan` through `buildHarvestPlanRequestPayload()`.
- Kept `/douyin-extension/capture-current-page` routed through `buildCaptureCurrentPageRequestPayload()`.
- Kept full modal harvest routed through `buildFullModalHarvestRequestPayload()` using `douyin_full_modal_harvest.v1`.
- Added harvest-plan preflight validation that throws `harvest_plan_schema_version_mismatch` before a backend request is sent if the payload schema is not `douyin_extension_harvest_plan.v1`.
- Updated popup backend error diagnostics so harvest-plan errors use `request_url` and `request_stage: harvest_plan`; only full-modal flush errors keep `flush_url`.
- Updated capture payload creation sites to consume the centralized capture schema constant while preserving capture-current-page behavior.
- Added focused schema builder tests and source-level Smart Capture routing/diagnostic assertions.

## Non-Goals

- No backend changes.
- No modal metric extraction changes.
- No broad Safe Runner behavior changes.
- No calibration workflow changes.
- No Tile Gallery changes.
- No CDP/debug workflow reintroduction.
