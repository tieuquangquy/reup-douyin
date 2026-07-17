import assert from "node:assert/strict";

import {
  CAPTURE_CURRENT_PAGE_SCHEMA_VERSION,
  FULL_MODAL_HARVEST_SCHEMA_VERSION,
  HARVEST_PLAN_SCHEMA_VERSION,
  buildCaptureCurrentPageRequestPayload,
  buildFullModalHarvestRequestPayload,
  buildHarvestPlanRequestPayload,
  validateHarvestPlanRequestPayload
} from "./requestPayloads.js";
import type { ExtensionCapturePayload, FullModalHarvestRequestPayload } from "./types.js";

function capturePayloadFixture(): ExtensionCapturePayload {
  return {
    schema_version: CAPTURE_CURRENT_PAGE_SCHEMA_VERSION,
    capture_id: "capture-phase17d-fixture",
    captured_at: "2026-05-04T09:00:00.000Z",
    page: {
      url: "https://www.douyin.com/user/test",
      title: "fixture profile",
      body_text_sample: "fixture",
      page_type: "profile_page",
      profile_url: "https://www.douyin.com/user/test",
      profile_external_id: "test",
      handle: "test",
      display_name: "Test Profile",
      video_link_count: 0
    },
    profile: null,
    capture_context: {
      capture_id: "capture-phase17d-fixture",
      captured_at: "2026-05-04T09:00:00.000Z",
      page_url: "https://www.douyin.com/user/test"
    },
    videos: [],
    diagnostics: {
      extension_version: "0.1.0",
      extractor: "phase17d_fixture"
    },
    harvest_mode: "new_and_incomplete"
  };
}

const capturePayload = capturePayloadFixture();
const harvestPlanPayload = buildHarvestPlanRequestPayload(capturePayload);
const captureCurrentPagePayload = buildCaptureCurrentPageRequestPayload(capturePayload);
const fullModalPayload = buildFullModalHarvestRequestPayload({
  capture_session_id: "session-phase17d-fixture",
  started_at: "2026-05-04T09:01:00.000Z",
  page: capturePayload.page,
  capture_context: capturePayload.capture_context,
  items: [],
  progress: {
    running: false,
    current_state: "completed",
    phase: "completed",
    target_count: 0,
    current_index: 0,
    current_aweme_id: null,
    harvested_count: 0,
    updated_count: 0,
    pending_count: 0,
    duplicate_count: 0,
    failed_count: 0,
    flushed_count: 0,
    last_error: null,
    stopped_reason: "completed_noop",
    last_flush_status: "none",
    next_flush_in_items: 0
  },
  diagnostics: {
    extension_source: "phase17d_fixture"
  },
  commit_policy: "finalized_only"
} satisfies Omit<FullModalHarvestRequestPayload, "schema_version">);

assert.equal(HARVEST_PLAN_SCHEMA_VERSION, "douyin_extension_harvest_plan.v1");
assert.equal(CAPTURE_CURRENT_PAGE_SCHEMA_VERSION, "douyin_extension_capture.v1");
assert.equal(FULL_MODAL_HARVEST_SCHEMA_VERSION, "douyin_full_modal_harvest.v1");
assert.equal(harvestPlanPayload.schema_version, HARVEST_PLAN_SCHEMA_VERSION, "harvest-plan builder must return harvest-plan schema");
assert.equal(captureCurrentPagePayload.schema_version, CAPTURE_CURRENT_PAGE_SCHEMA_VERSION, "capture-current-page builder must return capture schema");
assert.equal(fullModalPayload.schema_version, FULL_MODAL_HARVEST_SCHEMA_VERSION, "full-modal harvest builder must return backend full-modal schema");
assert.notEqual(harvestPlanPayload.schema_version, CAPTURE_CURRENT_PAGE_SCHEMA_VERSION, "harvest-plan request must never use capture schema");
assert.doesNotThrow(() => validateHarvestPlanRequestPayload(harvestPlanPayload));
assert.throws(
  () => validateHarvestPlanRequestPayload(captureCurrentPagePayload),
  /harvest_plan_schema_version_mismatch: expected=douyin_extension_harvest_plan\.v1, got=douyin_extension_capture\.v1/,
  "preflight must block harvest-plan payloads with the capture schema before sending"
);

console.log("request payload schema tests passed");
