import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { clearLegacyState, getLegacyStateSummary, LEGACY_STATE_KEYS } from "./legacy/legacyStateKeys.js";
import { WHOLE_PROFILE_HARVEST_FEATURES } from "./wholeProfileHarvest/featureMap.js";
import { createWholeProfileHarvestIdleState, WHOLE_PROFILE_HARVEST_STATE_KEY } from "./wholeProfileHarvest/state.js";

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");

for (const legacyText of [
  "Capture current page",
  "Capture current page only",
  "Attach CDP",
  "Detach CDP",
  "Probe Current Modal via CDP",
  "Start Full Modal Harvest",
  "Resume Full Modal Harvest",
  "Flush Harvested Metadata",
  "Smart Capture & Harvest",
  "Run Staged Harvest V2",
  "Test Modal → Whole Profile Harvest"
]) {
  assert.doesNotMatch(popupHtml, new RegExp(legacyText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"), `popup must not render legacy button text: ${legacyText}`);
}

for (const productText of [
  "Douyin Scanner",
  "Scan",
  "Capture Inbox",
  "Save",
  "Mode",
  "Batch",
  "Speed",
  "Reset",
  "Copy Debug JSON",
  "Clear Legacy State"
]) {
  assert.match(popupHtml, new RegExp(productText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")), `popup must render product text: ${productText}`);
}

assert.match(popupHtml, /<details class="panel maintenance dh-card" id="advancedDiagnostics"/, "advanced diagnostics must be a details element");
assert.doesNotMatch(popupHtml, /<details class="panel maintenance" id="advancedDiagnostics"[^>]*open/, "advanced diagnostics must be collapsed by default");

assert.equal(WHOLE_PROFILE_HARVEST_FEATURES.verifyProfile, true);
assert.equal(WHOLE_PROFILE_HARVEST_FEATURES.legacyCaptureCurrentPage, false);
assert.equal(WHOLE_PROFILE_HARVEST_FEATURES.legacyFullModalHarvest, false);
assert.equal(WHOLE_PROFILE_HARVEST_FEATURES.legacySmartCapture, false);
assert.equal(WHOLE_PROFILE_HARVEST_FEATURES.legacySafeRunner, false);
assert.equal(WHOLE_PROFILE_HARVEST_FEATURES.legacyCDP, false);
assert.equal(WHOLE_PROFILE_HARVEST_FEATURES.legacyProbeModal, false);

const removed: string[][] = [];
const storage = {
  async get(keys: string | string[]) {
    const result: Record<string, unknown> = {};
    for (const key of Array.isArray(keys) ? keys : [keys]) {
      if (key === "douyinSafeHarvestRun") result[key] = { present: true };
    }
    return result;
  },
  async remove(keys: string[]) {
    removed.push(keys);
  }
};

const summary = await getLegacyStateSummary(storage);
assert.equal(summary.has_legacy_state, true);
assert.equal(summary.present_count, 1);
assert.deepEqual(summary.present_keys, ["douyinSafeHarvestRun"]);
await clearLegacyState(storage);
assert.ok(removed[0]?.includes("douyinSafeHarvestRun"));
assert.equal(removed[0]?.includes("douyinRightRailCalibration"), false, "Clear Legacy State must not clear calibration");
assert.equal(removed[0]?.includes("rightRailCalibration"), false, "Clear Legacy State must not clear legacy calibration aliases");
assert.ok(LEGACY_STATE_KEYS.includes("douyinHarvestPendingFlushQueueV2"));

const idle = createWholeProfileHarvestIdleState("2026-05-05T08:00:00.000Z");
assert.equal(WHOLE_PROFILE_HARVEST_STATE_KEY, "douyinWholeProfileHarvest");
assert.equal(idle.schema_version, "phase18i_a_three_layer_harvest_design");
assert.equal(idle.status, "idle");
assert.equal(idle.dry_run.sample_size, 0);
assert.equal(idle.harvest.flushed, 0);

assert.match(popupSource, /const wholeProfileHarvestModeSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestMode"\);/, "popup must keep friendly Mode option wiring");
assert.match(popupSource, /const wholeProfileHarvestBatchSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestBatch"\);/, "popup must keep friendly Batch option wiring");
assert.match(popupSource, /const wholeProfileHarvestSpeedSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestSpeed"\);/, "popup must keep friendly Speed option wiring");
assert.match(popupHtml, /id="scannerPrimaryActionTitle"/, "popup must render the scanner primary action title");
assert.match(popupHtml, /id="scannerPrimaryActionReason"/, "popup must render the scanner primary action helper message");
assert.match(popupHtml, /id="scannerPrimaryActionButton"/, "popup must render the scanner primary action button");
assert.match(popupHtml, /id="scannerHeaderStatus"/, "popup must render the scanner header status label");
assert.match(popupHtml, /id="scannerStatsGrid"/, "popup must render the scanner counters grid");
assert.match(popupSource, /runWholeProfilePrimaryActionFromPopup/, "popup must route dynamic stop and resume behavior through the scanner primary action flow");
assert.match(popupHtml, /Collect profile videos for Capture Inbox/, "popup must render the compact scanner subtitle");
assert.match(popupHtml, /Advanced Details/, "popup must keep advanced details collapsed");

assert.match(popupCss, /\.summary\s*\{[\s\S]*grid-template-columns:\s*minmax\(110px, 140px\) minmax\(0, 1fr\)/, "progress summaries must reserve a usable value column");
assert.match(popupCss, /\.summary dd\s*\{[\s\S]*min-width:\s*0;[\s\S]*word-break:\s*normal;[\s\S]*overflow-wrap:\s*anywhere;/, "summary values must not collapse into one-character vertical wrapping");
assert.doesNotMatch(popupCss, /word-break:\s*break-all/, "popup progress must not use global break-all wrapping");
assert.match(popupSource, /summary__value--short/, "popup renderer must tag status-like summary values");
assert.match(popupSource, /summary__value--url/, "popup renderer must tag URL summary values");
assert.match(popupSource, /dd\.title = value/, "URL summary values must expose full text in title");
assert.match(popupSource, /setHeaderStatusChips\(/, "compact status chips must be rendered from popup state");

assert.match(popupSource, /Clear Legacy State must not clear calibration|Calibration will NOT be cleared/, "clear legacy state confirmation must document calibration preservation");

const primaryDispatchTargetBody = popupSource.match(/function primaryActionDispatchTarget\(actionKey: ScannerActionKey\): string \{[\s\S]*?\n\}/)?.[0] ?? "";
assert.match(primaryDispatchTargetBody, /case "scan_profile": return "dispatchBackgroundScanProfileAction22C11B"/, "primary Scan Profile action must keep the canonical background dispatch target");
assert.match(primaryDispatchTargetBody, /case "start_collecting": return "runStartCollectingWorkflow"/, "primary Start Collecting action must keep the canonical collection dispatch target");
assert.doesNotMatch(primaryDispatchTargetBody, /runRealModalExtractionHarvest|REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE|REUP_DOUYIN_START_FULL_MODAL_HARVEST|REUP_DOUYIN_START_SMART_CAPTURE|REUP_DOUYIN_CAPTURE|REUP_DOUYIN_CDP/, "popup primary action dispatch target must not reference legacy modal, harvest, capture, or CDP runners");

const primaryActionBody = popupSource.match(/async function handlePrimaryActionClick\(actionKey: ScannerActionKey, label: string\): Promise<void> \{[\s\S]*?\n\}/)?.[0] ?? "";
assert.match(primaryActionBody, /case "scan_profile":[\s\S]*return scanProfileFromPopupWithProfileContextReset\(\)/, "primary action handler must route Scan Profile through profile-context reset then canonical 22C11B dispatch");
assert.match(popupSource, /async function scanProfileFromPopupWithProfileContextReset[\s\S]*dispatchBackgroundScanProfileAction22C11B\(\)/, "scan profile context reset must still end at canonical background dispatch");
assert.match(primaryActionBody, /case "start_collecting":[\s\S]*return runWholeProfileHarvestProductFromPopup\(\)/, "primary action handler must route Start Collecting through the canonical product workflow");
assert.doesNotMatch(primaryActionBody, /runRealModalExtractionHarvest|REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE|REUP_DOUYIN_START_FULL_MODAL_HARVEST|REUP_DOUYIN_START_SMART_CAPTURE|REUP_DOUYIN_CAPTURE|REUP_DOUYIN_CDP/, "popup primary action handler must not dispatch forbidden legacy modal, harvest, capture, or CDP runners");

assert.match(popupSource, /chrome\.runtime\.sendMessage\(\{ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"/, "popup Scan Profile route string must remain canonical");
assert.match(popupSource, /backgroundMessageType: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"/, "popup Scan Profile diagnostics must keep the canonical background route string");

console.log("Phase 18A popup cleanup tests passed");
