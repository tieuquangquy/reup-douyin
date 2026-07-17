import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { createWholeProfileHarvestIdleState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import { getHarvestQueueAndResultsViewModel } from "./wholeProfileHarvest/viewModel.js";

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");
const viewModelSource = readFileSync(new URL("./wholeProfileHarvest/viewModel.ts", import.meta.url), "utf8");

function baseState(): WholeProfileHarvestState {
  return createWholeProfileHarvestIdleState("2026-05-06T14:00:00.000Z");
}

function withRows(state: WholeProfileHarvestState): WholeProfileHarvestState {
  return {
    ...state,
    verify: { ...state.verify, status: "success", verified_target_count: 10, accepted_target_count: 10 },
    harvest_options: { ...state.harvest_options, mode: "new_and_incomplete" },
    harvest: {
      ...state.harvest,
      queue_preview: Array.from({ length: 7 }, (_, index) => ({
        index,
        aweme_id: `76352942674133681${String(index).padStart(2, "0")}`,
        capture_status: index === 0 ? "new" as const : index === 1 ? "incomplete" as const : "complete" as const,
        source_url: `https://www.douyin.com/video/${index}`,
        title: index === 0 ? "A very long title for a queue preview row that should truncate cleanly in the popup layout" : `Title ${index + 1}`,
        thumbnail_url: null
      })),
      backend: {
        ...state.harvest.backend,
        batch_flush: {
          ...state.harvest.backend.batch_flush,
          succeeded: 1,
          skipped: 1,
          failed: 1
        }
      },
      results: [
        {
          index: 1,
          aweme_id: "7635294267413368100",
          status: "extracted",
          stage: "build_payload",
          attempts: 1,
          checkpoint_sequence: 1,
          error: null,
          error_code: null,
          error_message: null,
          modal_opened: true,
          modal_id_matched: true,
          metrics_extracted: true,
          payload_built: true,
          backend_called: false,
          backend_status: null,
          backend_error_code: null,
          capture_inbox_item_id: null,
          target_url: null,
          data_integrity_status: "passed",
          profile_card_evidence: {},
          started_at: null,
          completed_at: "2026-05-06T14:02:00.000Z",
          duration_seconds: 803,
          duration_text: "13:23",
          like_count: 409,
          comment_count: 12,
          favorite_count: 58,
          share_count: 19,
          current_modal_id_before: "7635294267413368100",
          current_modal_id_after: "7635294267413368100",
          extracted_aweme_id: "7635294267413368100",
          source_used: "calibrated_point_dom"
        },
        {
          index: 2,
          aweme_id: "7635208422245338409",
          status: "failed",
          stage: "open_modal",
          attempts: 1,
          checkpoint_sequence: 2,
          error: "modal_navigation_timeout",
          error_code: "modal_navigation_timeout",
          error_message: "modal_navigation_timeout",
          modal_opened: false,
          modal_id_matched: false,
          metrics_extracted: false,
          payload_built: false,
          backend_called: false,
          backend_status: null,
          backend_error_code: null,
          capture_inbox_item_id: null,
          target_url: null,
          data_integrity_status: "not_checked",
          profile_card_evidence: {},
          started_at: null,
          completed_at: "2026-05-06T14:03:00.000Z",
          duration_seconds: null,
          duration_text: null,
          like_count: null,
          comment_count: null,
          favorite_count: null,
          share_count: null,
          current_modal_id_before: null,
          current_modal_id_after: null,
          extracted_aweme_id: null,
          source_used: null
        },
        {
          index: 3,
          aweme_id: "7635207774633823530",
          status: "skipped",
          stage: "verify_backend_item",
          attempts: 1,
          checkpoint_sequence: 3,
          error: "already_complete",
          error_code: "already_complete",
          error_message: "already_complete",
          modal_opened: true,
          modal_id_matched: true,
          metrics_extracted: false,
          payload_built: false,
          backend_called: true,
          backend_status: 200,
          backend_error_code: null,
          capture_inbox_item_id: null,
          target_url: null,
          data_integrity_status: "passed",
          profile_card_evidence: {},
          started_at: null,
          completed_at: "2026-05-06T14:04:00.000Z",
          duration_seconds: null,
          duration_text: null,
          like_count: null,
          comment_count: null,
          favorite_count: null,
          share_count: null,
          current_modal_id_before: null,
          current_modal_id_after: null,
          extracted_aweme_id: null,
          source_used: null
        },
        {
          index: 4,
          aweme_id: "7635201111111111111",
          status: "extracted",
          stage: "flush_backend",
          attempts: 1,
          checkpoint_sequence: 4,
          error: null,
          error_code: null,
          error_message: null,
          modal_opened: true,
          modal_id_matched: true,
          metrics_extracted: true,
          payload_built: true,
          backend_called: true,
          backend_status: 200,
          backend_error_code: null,
          capture_inbox_item_id: "abc1234567",
          target_url: null,
          data_integrity_status: "passed",
          profile_card_evidence: {},
          started_at: null,
          completed_at: "2026-05-06T14:05:00.000Z",
          duration_seconds: 120,
          duration_text: "02:00",
          like_count: 1,
          comment_count: 2,
          favorite_count: 3,
          share_count: 4,
          current_modal_id_before: null,
          current_modal_id_after: null,
          extracted_aweme_id: null,
          source_used: "calibrated_point_dom"
        }
      ]
    }
  };
}

{
  const vm = getHarvestQueueAndResultsViewModel(withRows(baseState()));
  assert.equal(vm.queue_preview.rows.length, 5);
  assert.equal(vm.queue_preview.remaining_count, 2);
  assert.equal(vm.queue_preview.rows[0]?.badge, "NEW");
  assert.match(vm.queue_preview.rows[0]?.aweme_short ?? "", /\.\.\./);
  assert.match(vm.queue_preview.rows[0]?.title_short ?? "", /Title|…|\.\.\./);
  assert.equal(vm.extraction_results.rows[0]?.status, "extracted");
  assert.equal(vm.extraction_results.rows[0]?.like_count, 409);
  assert.equal(vm.extraction_results.rows[1]?.error_code, "modal_navigation_timeout");
  assert.equal(vm.backend_results.rows.some((row) => row.status === "flushed" && row.item_id_short === "abc1234567"), true);
  assert.equal(vm.backend_results.rows.some((row) => row.status === "skipped_complete"), true);
  assert.match(vm.backend_results.summary, /Flushed 1/);
}

{
  const vm = getHarvestQueueAndResultsViewModel(baseState());
  assert.equal(vm.queue_preview.empty_message, "No videos queued yet. Scan Profile first.");
  assert.equal(vm.extraction_results.empty_message, "No metrics extracted yet. Run Extract Next 10 after a successful test.");
  assert.equal(vm.backend_results.empty_message, "No saved videos yet.");
}

{
  const state = withRows(baseState());
  const vm = getHarvestQueueAndResultsViewModel({
    ...state,
    verify: { ...state.verify, verified_target_count: 1001 },
    harvest: { ...state.harvest, planned_total: 1001, pending: 1001 },
    profile_scan: {
      ...state.profile_scan,
      diagnostics: {
        large_profile_mode: "yes",
        scan_total_found: 1001,
        scan_total_expected: 1001,
        scan_total_missing: 0,
        queue_window_size: 100,
        queue_window_offset: 0,
        queue_total_persisted: 1001,
        queue_total_visible: 100,
        large_profile_storage_degraded: "yes",
        large_profile_storage_backend: "local",
        large_profile_storage_degraded_reason: "indexeddb_unavailable_using_local_memory_fallback",
        large_profile_durable_persistence: "no"
      }
    }
  });
  assert.equal(vm.queue_preview.total, 1001, "large profile queue total must not be preview length");
  assert.equal(vm.queue_preview.rows.length, 5, "visible UI rows stay compact");
  assert.match(vm.queue_preview.subtitle, /Found 1001 \/ Expected 1001/);
  assert.match(vm.queue_preview.subtitle, /Queue total 1001/);
  assert.match(vm.queue_preview.subtitle, /Preview window 100/);
  assert.match(vm.queue_preview.subtitle, /Large profile mode: showing first 100 queued items/);
  assert.match(vm.queue_preview.subtitle, /Storage degraded: local fallback; durable persistence not guaranteed/);
  assert.match(vm.queue_preview.subtitle, /indexeddb_unavailable_using_local_memory_fallback/);
}

assert.match(popupHtml, /id="wholeProfileQueuePreviewPanel"/, "results panel must render queue preview section");
assert.match(popupHtml, /id="wholeProfileExtractionResultsSection"/, "results panel must render extraction results section");
assert.match(popupHtml, /id="wholeProfileBackendResultsSection"/, "results panel must render backend results section");
assert.match(popupHtml, /id="wholeProfileQueuePreviewRows"/, "results panel must retain queue preview rows");
assert.match(popupHtml, /id="wholeProfileExtractionResultsRows"/, "results panel must retain extraction results rows");
assert.match(popupHtml, /id="wholeProfileBackendResultsRows"/, "results panel must retain backend results rows");
assert.doesNotMatch(popupHtml, /id="wholeProfileQueueDetailsRows"/, "legacy queue details rows markup must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileExtractionDetailsRows"/, "legacy extraction details rows markup must be removed");
assert.doesNotMatch(popupHtml, /id="wholeProfileBackendResultDetailsRows"/, "legacy backend details rows markup must be removed");
assert.doesNotMatch(popupHtml, /<ul id="wholeProfileRecentRows"/, "main progress must not use old recent text blob list");

assert.match(popupCss, /\.compact-table\s*\{[\s\S]*display:\s*grid;/, "compact tables must use grid layout");
assert.match(popupCss, /\.compact-row__line/, "compact rows must expose truncation-friendly line layout");
assert.match(popupCss, /\.compact-row__error/, "compact rows must style error text");
assert.doesNotMatch(popupCss, /word-break:\s*break-all/, "compact tables must not force single-character wrapping");

assert.match(popupSource, /renderCompactRows\(/, "popup must render queue/results through compact row renderer");
assert.doesNotMatch(popupSource, /setList\(wholeProfileRecentRowsEl/, "popup must not render old recent string blob list");
assert.doesNotMatch(viewModelSource, /douyinHarvestRuntimeV2|douyinSafeHarvestRun|smartHarvestState|harvestProgress/, "queue/results view model must not depend on legacy runtimes");

console.log("wholeProfileHarvest queue/results table tests passed");
