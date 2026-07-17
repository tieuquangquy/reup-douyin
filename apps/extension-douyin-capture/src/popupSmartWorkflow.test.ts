import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf-8");
const contentScriptSource = readFileSync(new URL("./contentScript.ts", import.meta.url), "utf-8");
const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf-8");

assert.doesNotMatch(popupSource, /async function runSmartCaptureHarvest/, "legacy Smart Capture orchestration must be removed from popup");
assert.doesNotMatch(popupSource, /async function resumeHarvest\(/, "legacy modal resume harvest must be removed from popup");
assert.doesNotMatch(popupSource, /async function runHarvestPlanCurrentPage/, "legacy harvest-plan popup helper must be removed");
assert.doesNotMatch(popupSource, /async function runProfileScanRequest/, "legacy profile scan request helper must be removed");
assert.match(popupSource, /buildHarvestPlanRequestPayload/, "modal dev tools must still build harvest-plan payloads");
assert.match(popupSource, /validateHarvestPlanRequestPayload/, "harvest-plan preflight must validate schema before sending");
assert.match(popupSource, /postJson<[^>]*HarvestPlanResponse>/, "modal dev tools must still post harvest-plan requests");
assert.match(popupSource, /buildModalWholeProfileHarvestPlanPayload/, "modal whole-profile test must build harvest plans from scanned cards");
assert.match(popupSource, /resolveModalWholeProfileTestPlan/, "modal whole-profile test must resolve plans from profile grid");
assert.doesNotMatch(popupHtml, /Flush Pending/, "popup must not expose legacy flush pending in Phase 18A UI");
assert.match(popupSource, /GET_DOUYIN_PAGE_VIEWPORT/, "popup must obtain current page viewport from content script");
assert.doesNotMatch(popupSource, /globalThis\.window\.innerWidth/, "popup must never compare against popup viewport width");
assert.doesNotMatch(popupSource, /globalThis\.window\.innerHeight/, "popup must never compare against popup viewport height");
assert.match(popupSource, /CONTENT_SCRIPT_VIEWPORT_RETRY_MESSAGE/, "popup must block with refresh-tab retry message when viewport bridge is unavailable");

assert.match(contentScriptSource, /options\.capture_session_id/, "content script must accept explicit capture_session_id binding");
assert.match(contentScriptSource, /options\.capture_id/, "content script must accept explicit capture_id binding");
assert.match(contentScriptSource, /profile_card_evidence_by_aweme_id/, "content script runtime must carry profile-card evidence into modal harvest");
assert.match(contentScriptSource, /full_modal_harvest_non_v2_caller_blocked/, "content script modal flush must be locally blocked in Phase 17AE");
assert.match(contentScriptSource, /GET_DOUYIN_PAGE_VIEWPORT/, "content script must answer viewport bridge messages");
assert.match(contentScriptSource, /const viewport = getDouyinPageViewport\(\)/, "probe and calibration point ratios must be calculated in content script from page viewport helper");
assert.match(popupSource, /getProfileUrlFromModalUrl\(/, "modal dev tools must parse modal URL before profile work");
assert.match(popupSource, /waitForActiveTabUrl\(/, "modal dev tools must wait for deterministic profile/modal navigation");
assert.doesNotMatch(popupHtml, /Verify Modal Harvest Coverage/, "popup must not expose legacy modal harvest coverage action in Phase 18A UI");
assert.match(popupSource, /SMART_CAPTURE_HARVEST_STATE_KEY/, "operational status must still use canonical smart harvest storage key for migration");
assert.doesNotMatch(
  popupSource,
  /douyinSmartCaptureHarvestState:\s*nextState/,
  "smart workflow must not dual-write legacy smart harvest state key"
);
assert.match(
  popupSource,
  /const runtimeSmartState = normalizedProgress[\s\S]*smartStateFromHarvestProgress\(/,
  "operational status must derive runtime smart state from harvest progress before rendering"
);

console.log("popup smart capture and harvest workflow tests passed");
