# Phase 17D Harvest Plan Schema Hotfix Resume

## Status

Phase 17D implementation is complete pending verification commands. The extension now builds distinct request payloads for harvest-plan, capture-current-page, and full-modal-harvest endpoint contracts.

## Files Changed

- `apps/extension-douyin-capture/src/requestPayloads.ts`
- `apps/extension-douyin-capture/src/requestPayloads.test.ts`
- `apps/extension-douyin-capture/src/popup.ts`
- `apps/extension-douyin-capture/src/popupSmartWorkflow.test.ts`
- `apps/extension-douyin-capture/src/extractor.ts`
- `apps/extension-douyin-capture/src/popupTransport.ts`
- `apps/extension-douyin-capture/src/contentScript.ts`
- `apps/extension-douyin-capture/src/modalHarvest.ts`
- `docs/metadata-phase17D-harvest-plan-schema-hotfix-log.md`
- `docs/metadata-phase17D-harvest-plan-schema-hotfix-resume.md`

## Schema Constants

- `HARVEST_PLAN_SCHEMA_VERSION = "douyin_extension_harvest_plan.v1"`
- `CAPTURE_CURRENT_PAGE_SCHEMA_VERSION = "douyin_extension_capture.v1"`
- `FULL_MODAL_HARVEST_SCHEMA_VERSION = "douyin_full_modal_harvest.v1"`

## Payload Builders

- `buildHarvestPlanRequestPayload()` converts a captured page payload into a harvest-plan request with `douyin_extension_harvest_plan.v1`.
- `buildCaptureCurrentPageRequestPayload()` keeps manual capture-current-page requests on `douyin_extension_capture.v1`.
- `buildFullModalHarvestRequestPayload()` builds full-modal harvest flush payloads with `douyin_full_modal_harvest.v1`.
- `validateHarvestPlanRequestPayload()` blocks harvest-plan sends locally with `harvest_plan_schema_version_mismatch` if the schema is wrong.

## Verification To Run

```cmd
npm --workspace @reup-douyin/extension-douyin-capture run test
npm --workspace @reup-douyin/extension-douyin-capture run typecheck
npm --workspace @reup-douyin/extension-douyin-capture run build
```

## Live Retest

1. Rebuild the extension.
2. Reload the unpacked extension in Chrome.
3. Open a Douyin profile page.
4. Click Smart Capture & Harvest from the extension popup.
5. Confirm the backend receives `/douyin-extension/harvest-plan` with `schema_version: "douyin_extension_harvest_plan.v1"`.
6. Confirm no 422 literal schema error is returned for harvest-plan.
7. Use the manual Capture current page button and confirm `/douyin-extension/capture-current-page` still sends `schema_version: "douyin_extension_capture.v1"`.
