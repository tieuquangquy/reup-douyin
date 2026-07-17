import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  appendRecentItem,
  completeHarvestRuntimeV2,
  createHarvestRuntimeV2,
  createIdleHarvestRuntimeV2,
  firstPendingTarget,
  HARVEST_RUNTIME_V2_KEY,
  LEGACY_HARVEST_STORAGE_KEYS,
  normalizeHarvestRuntimeV2,
  pauseHarvestRuntimeV2,
  runtimeV2ToProgress,
  touchHarvestRuntimeV2,
  transitionHarvestRuntime,
  updateTargetStatus
} from "./harvestRuntimeV2.js";

const contentScriptSource = readFileSync(new URL("./contentScript.ts", import.meta.url), "utf-8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf-8");
const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf-8");

{
  const runtime = createHarvestRuntimeV2("run-1", ["a1", "a2", "a3"], new Date(), {
    a1: {
      aweme_id: "a1",
      source_url: "https://www.douyin.com/video/a1",
      title: "Profile card a1",
      thumbnail_url: "https://p3.douyinpic.com/obj/a1"
    }
  });
  assert.equal(runtime.schema_version, "phase17c_safe_runner");
  assert.equal(runtime.status, "running");
  assert.equal(runtime.phase, "opening_target");
  assert.equal(runtime.counts.target, 3);
  assert.equal(runtime.current_target_index, 1);
  assert.deepEqual(Object.keys(runtime.target_status), ["a1", "a2", "a3"]);
  assert.equal(runtime.profile_card_evidence_by_aweme_id.a1?.title, "Profile card a1");
}

{
  let runtime = createHarvestRuntimeV2("run-2", ["a1", "a2", "a3"]);
  runtime = updateTargetStatus(runtime, "a1", "updated");
  runtime = updateTargetStatus(runtime, "a2", "updated");
  runtime = updateTargetStatus(runtime, "a3", "pending");
  const progress = runtimeV2ToProgress(runtime, []);
  assert.equal(progress.current_index, 3, "current index derives from first pending target");
  assert.equal(progress.updated_count, 2);
  assert.equal(progress.processed_count, 2);
  assert.equal(progress.remaining_count, 1);
}

{
  let runtime = createHarvestRuntimeV2("run-3", ["a1", "a2"]);
  runtime = updateTargetStatus(runtime, "a1", "updated");
  runtime = touchHarvestRuntimeV2(runtime, { current_target_index: 15 });
  const progress = runtimeV2ToProgress(runtime, []);
  assert.equal(progress.current_index, 2, "invalid target index repairs from target_status map");
  assert.match(JSON.stringify(progress.runtime_transition_log ?? []), /repaired_target_index/);
}

{
  const unauthorizedPause = transitionHarvestRuntime(
    createHarvestRuntimeV2("run-4", ["a1"]),
    {
      status: "paused",
      phase: "paused",
      pause_reason: null
    },
    {
      caller: "test.unauthorized_pause",
      reason: "unauthorized",
      stack_or_location: "harvestRuntimeV2.test"
    }
  );
  assert.equal(unauthorizedPause.status, "running", "unauthorized pause is rejected");
  assert.equal(unauthorizedPause.phase, "opening_target");
  assert.match(JSON.stringify(unauthorizedPause.state_transition_log ?? []), /rejected_unauthorized_pause/);
}

{
  const paused = pauseHarvestRuntimeV2(createHarvestRuntimeV2("run-5", ["a1"]), "operator_stop", null, new Date(), "test.operator_stop");
  const progress = runtimeV2ToProgress(paused, []);
  assert.equal(progress.harvest_status, "paused");
  assert.equal(progress.stopped_reason, "operator_stop");
  assert.equal(progress.can_resume, true);
}

{
  const recovered = normalizeHarvestRuntimeV2({
    ...createHarvestRuntimeV2("run-6", ["a1", "a2"]),
    status: "paused",
    phase: "paused",
    pause_reason: null,
    last_error: null
  });
  assert.equal(recovered.status, "running", "paused without pause_reason auto-recovers");
  assert.equal(recovered.phase, "opening_target");
  assert.match(JSON.stringify(recovered.state_transition_log ?? []), /auto_recovered_unauthorized_pause/);
}

{
  let runtime = createHarvestRuntimeV2("run-7", ["a1", "a2", "a3"]);
  runtime = updateTargetStatus(runtime, "a1", "processing", { attemptsDelta: 1 });
  runtime = updateTargetStatus(runtime, "a1", "updated");
  runtime = updateTargetStatus(runtime, "a2", "processing", { attemptsDelta: 1 });
  runtime = updateTargetStatus(runtime, "a2", "updated");
  runtime = updateTargetStatus(runtime, "a3", "processing", { attemptsDelta: 1 });
  runtime = updateTargetStatus(runtime, "a3", "updated");
  const progress = runtimeV2ToProgress(runtime, []);
  assert.equal(progress.updated_count, 3);
  assert.equal(progress.processed_count, 3);
  assert.equal(progress.current_index, 3, "fully processed queue lands on final target index");
}

{
  let runtime = createHarvestRuntimeV2("run-8", ["a1", "a2"]);
  runtime = updateTargetStatus(runtime, "a1", "updated");
  const progress = runtimeV2ToProgress(runtime, [
    {
      aweme_id: "a1",
      raw_dom_detail_metrics: {
        duration_seconds: 123,
        like_count: 12,
        comment_count: 3,
        favorite_count: 4,
        share_count: 5,
        extraction_source: "calibrated_point_dom",
        confidence: "high"
      },
      raw_evidence_summary: {
        has_dom_detail_metrics: true,
        has_network_aweme: false,
        has_detail_aweme: false,
        has_dom_snapshot: false,
        network_keys: [],
        detail_keys: [],
        dom_detail_metric_keys: ["duration_seconds", "like_count", "comment_count", "favorite_count", "share_count"],
        evidence_sources: ["calibrated_point_modal_counts", "full_modal_auto_harvest"],
        evidence_collection_version: "phase11a_production_stabilized_calibrated_harvest"
      }
    }
  ]);
  assert.equal(progress.flushed_count, 1, "flushed items derive only after updated status because safe runner marks updated after backend flush");
  assert.equal(progress.flush_attempt_count, 0);
}

{
  let runtime = createHarvestRuntimeV2("run-9", ["a1", "a2"]);
  runtime = appendRecentItem(runtime, {
    index: 1,
    aweme_id: "a1",
    duration_seconds: 20,
    like_count: 2,
    comment_count: 1,
    favorite_count: 1,
    share_count: 1,
    extraction_warning: null,
    status: "ok"
  });
  runtime = appendRecentItem(runtime, {
    index: 2,
    aweme_id: "a2",
    duration_seconds: 30,
    like_count: 4,
    comment_count: 2,
    favorite_count: 2,
    share_count: 2,
    extraction_warning: null,
    status: "ok"
  });
  assert.equal(runtime.recent_items.length, 2);
}

{
  let runtime = createHarvestRuntimeV2("run-10", ["a1", "a2"]);
  runtime = updateTargetStatus(runtime, "a1", "updated");
  runtime = updateTargetStatus(runtime, "a2", "updated");
  runtime = completeHarvestRuntimeV2(runtime, new Date(), "test.complete");
  const progress = runtimeV2ToProgress(runtime, []);
  assert.equal(progress.running, false);
  assert.equal(progress.harvest_status, "completed");
  assert.equal(progress.can_resume, false);
}

assert.deepEqual(createIdleHarvestRuntimeV2().profile_card_evidence_by_aweme_id, {}, "idle runtime must default profile-card evidence to an empty map");
assert.match(contentScriptSource, /HARVEST_RUNTIME_V2_KEY/, "content script must use canonical runtime v2 key");
assert.match(contentScriptSource, /__REUP_DOUYIN_SAFE_HARVEST_RUNNER/, "content script must own safe harvest singleton runner");
assert.match(contentScriptSource, /drainHarvestQueueV2/, "content script must drain queue continuously");
assert.match(contentScriptSource, /while \(true\)/, "runner must continuously drain target queue");
assert.match(contentScriptSource, /transitionHarvestRuntime/, "content script must use transition gate");
assert.doesNotMatch(popupHtml, /Show Runtime Transitions/, "popup must not expose legacy runtime transition diagnostics in Phase 18A UI");
assert.doesNotMatch(contentScriptSource, /status:\s*"paused"/, "content script must not directly write paused status");
assert.doesNotMatch(contentScriptSource, /phase:\s*"paused"/, "content script must not directly write paused phase");
assert.match(contentScriptSource, /REUP_DOUYIN_START_HARVEST_V2/, "content script must expose start v2 command");
assert.match(contentScriptSource, /REUP_DOUYIN_RESUME_HARVEST_V2/, "content script must expose resume v2 command");
assert.match(contentScriptSource, /REUP_DOUYIN_STOP_HARVEST_V2/, "content script must expose stop v2 command");
assert.match(contentScriptSource, /REUP_DOUYIN_RESET_HARVEST_RUNTIME_V2/, "content script must expose reset v2 command");
assert.match(popupSource, /REUP_DOUYIN_GET_SAFE_HARVEST_RUN/, "popup must read harvest runtime from safe-run command");
assert.match(popupSource, /REUP_DOUYIN_START_SAFE_HARVEST_RUN/, "popup must start harvest through safe-run command");
assert.match(popupSource, /REUP_DOUYIN_RESUME_SAFE_HARVEST_RUN/, "popup must resume harvest through safe-run command");
assert.ok(LEGACY_HARVEST_STORAGE_KEYS.includes("harvestProgress"));
assert.equal(HARVEST_RUNTIME_V2_KEY, "douyinSafeHarvestRun");

console.log("harvest runtime v2 tests passed");
