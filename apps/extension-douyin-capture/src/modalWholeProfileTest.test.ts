import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION,
  createModalWholeProfileTestRun,
  extractAwemeIdsFromString,
  isModalWholeProfileTestRun,
  isDouyinProfileGridReadyFromProbe,
  modalWholeProfileProbeToDryRunResult,
  modalWholeProfileSamplingModeFor,
  parseDouyinExpectedProfileVideoCountText,
  validateDouyinAwemeCandidate
} from "./modalWholeProfileTest.js";

const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf-8");
const backgroundSource = readFileSync(new URL("./background.ts", import.meta.url), "utf-8");
const contentScriptSource = readFileSync(new URL("./contentScript.ts", import.meta.url), "utf-8");
const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf-8");
const viewModelSource = readFileSync(new URL("./wholeProfileHarvest/viewModel.ts", import.meta.url), "utf-8");

{
  assert.match(popupSource, /SCANNER_RUNTIME_VERSION = "22C-12F"[\s\S]*STATE_MACHINE_VERSION = "22C-12F"[\s\S]*SCAN_CONTROLLER_VERSION = "22C-12F-unified-runtime"/, "22C-12F popup diagnostics must use consistent unified runtime version markers");
  assert.match(backgroundSource, /SCAN_PROFILE_BACKGROUND_TRACE_VERSION: ProfileScanTraceVersion = "22C-12F"[\s\S]*SCAN_PROFILE_BACKGROUND_CONTROLLER_VERSION = "22C-12F-unified-runtime"/, "22C-12F background route must use consistent unified runtime version markers");
  assert.match(backgroundSource, /DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B[\s\S]*scan_profile_22C11B_[\s\S]*persistCanonicalScanAccepted22C11B[\s\S]*runScanProfile22C11B/, "22C-12F background route must preserve the accepted ACK workflow without legacy scan dispatch");
  assert.match(backgroundSource, /network_probe_live_status_query/, "22C-12F background route must persist live authority status diagnostics");
  assert.doesNotMatch(backgroundSource, /type: "DOUYIN_NETWORK_PROBE_STATUS_22C12A_R3"/, "22C-12F background route must not use the stale passive probe status route as authority");
  assert.match(backgroundSource, /active_scan_profile_engine: "minimal_active_works_grid_scanner_22C11B"/, "22C-12F background diagnostics must expose the current unified runtime active engine marker");
  assert.match(backgroundSource, /active_profile_post_only[\s\S]*dom_scoped_fallback_degraded/, "22C-12F fresh Scan Profile must enforce canonical queue authority modes for network-post-only and degraded DOM fallback");
  assert.doesNotMatch(backgroundSource.match(/export async function handleMessage[\s\S]*?return \{ ok: false, error: "Unsupported extension message\."\;/)?.[0] ?? "", /DOUYIN_RUN_DIRECT_LEGACY_PROFILE_SCAN_22C9Z10|runDirectLegacyProfileScan22C9Z10/, "22C-12F active Scan Profile route must not dispatch the broken direct legacy scanner");
}

{
  assert.match(contentScriptSource, /classifyPassiveNetworkEndpointKind22C12A[\s\S]*live_network_stream_profile_collector_22C13A/, "22C-13A content script must classify network endpoint provenance and expose manual pagination verification diagnostics");
  assert.match(contentScriptSource, /network_stream_queue_adapter_22C12D/, "22C-13A content script must preserve the 22C-12D live stream queue adapter");
  assert.match(contentScriptSource, /runtime_health_status/, "22C-12F content script must expose runtime health diagnostics");
  assert.match(contentScriptSource, /activation_truth_probe_version/, "22C-12F content script must preserve activation truth probe diagnostics");
  assert.match(contentScriptSource, /human_vs_extension_scroll_differences/, "22C-12F content script must preserve activation truth probe differential diagnostics");
  assert.match(contentScriptSource, /toModalWholeProfileCard22C11B[\s\S]*mergeModalWholeProfileCards22C11B/, "22C-13A modal scan must normalize and merge canonical scanner cards with resolver targets");
  assert.match(contentScriptSource, /verified_targets:\s*finalAwemeIds[\s\S]*verified_target_details:\s*mergedCards\.cards[\s\S]*cards:\s*mergedCards\.cards/, "22C-13A modal scan response must use merged canonical cards as source of truth");
  assert.match(contentScriptSource, /final_found_count:\s*finalFoundCount[\s\S]*missing_expected_count:\s*missingExpectedCount[\s\S]*final_aweme_ids:\s*finalAwemeIds[\s\S]*partial_scan:\s*partialScan/, "22C-13A modal scan diagnostics must emit queue-critical final counters from merged cards");
  assert.match(contentScriptSource, /const\s+missingExpectedCount\s*=\s*expectedProfileVideoCount\s*!=\s*null[\s\S]*Math\.max\(expectedProfileVideoCount\s*-\s*finalFoundCount,\s*0\)[\s\S]*const\s+partialScan\s*=\s*missingExpectedCount\s*!=\s*null\s*\?\s*missingExpectedCount\s*>\s*0\s*:\s*false/, "22C-13A modal scan must derive incomplete-state diagnostics from merged final counts");
  assert.match(contentScriptSource, /const\s+merged\s*=\s*new Map<string,\s*ModalWholeProfileCard22C11B>\(\)[\s\S]*merged\.get\(candidate\.aweme_id\)/, "22C-13A modal card merge must dedupe by aweme_id");
  assert.match(contentScriptSource, /if\s*\(source\s*===\s*"scanner"\)\s*\{[\s\S]*\.\.\.existing,[\s\S]*\.\.\.candidate/, "22C-13A modal card merge must prefer richer scanner/DOM metadata when aweme ids collide");
  assert.match(contentScriptSource, /for\s*\(const\s+target\s+of\s+resolverTargets\)\s*\{[\s\S]*aweme_id:\s*target\.aweme_id[\s\S]*\}\),\s*"resolver"\)/, "22C-13A modal card merge must include valid resolver/network-only targets");
  assert.match(contentScriptSource, /fallbackVisitLimit\s*=\s*180[\s\S]*fallbackDepthLimit\s*=\s*6[\s\S]*aweme\(\?:_id\)\?\|awemeId\|post\|works\?\|list\|items\?\|card\|data\|result\|payload\|response\|detail/i, "22C-13A active profile-post parser fallback must stay bounded and aweme-oriented");
  assert.match(viewModelSource, /Network profile post unique count[\s\S]*Network favorite unique count[\s\S]*Network favorite excluded count[\s\S]*Network collection stop reason/, "22C-12F diagnostics UI must surface endpoint-scoped network collection metrics");
  assert.ok(typesSource.length > 0, "types source must be readable for modal whole profile static verification");
}

{
  assert.equal(parseDouyinExpectedProfileVideoCountText("作品 45"), 45);
  assert.equal(parseDouyinExpectedProfileVideoCountText("作品 1.2万"), 12000);
  assert.equal(parseDouyinExpectedProfileVideoCountText("喜欢 45"), null);
  assert.equal(parseDouyinExpectedProfileVideoCountText("  作 品   45  "), 45);
  assert.equal(parseDouyinExpectedProfileVideoCountText("作品：1,234"), 1234);
  assert.equal(parseDouyinExpectedProfileVideoCountText("posts: 56"), 56);
  assert.equal(parseDouyinExpectedProfileVideoCountText("videos 7.5k"), 7500);
  assert.equal(parseDouyinExpectedProfileVideoCountText("45 作品"), 45);
  assert.equal(parseDouyinExpectedProfileVideoCountText("作品 : 0"), null);
}

{
  assert.deepEqual(extractAwemeIdsFromString("video/7634192733514501001 modal_id=7634192733514501002"), ["7634192733514501001", "7634192733514501002"]);
  assert.equal(validateDouyinAwemeCandidate({
    candidate_id: "7634192733514501001",
    source: "video_link",
    source_url: "https://www.douyin.com/video/7634192733514501001",
    card_context: true,
    has_video_context: true
  }).status, "accepted");
  assert.equal(validateDouyinAwemeCandidate({
    candidate_id: "short",
    source: "video_link",
    source_url: "https://www.douyin.com/video/short",
    card_context: true,
    has_video_context: true
  }).status, "rejected");
}

{
  const probe = {
    traceVersion: "22C-9A" as const,
    url: "https://www.douyin.com/user/MS4wLjABCD",
    pathname: "/user/MS4wLjABCD",
    search: "",
    documentReadyState: "complete",
    bodyTextLength: 200,
    pageTypeDetected: "profile" as const,
    profileContainerFound: true,
    profileContainerSelector: "main",
    profileGridFound: true,
    profileGridSelector: "a[href*=\"/video/\"]",
    videoAnchorCount: 2,
    videoAnchors: [],
    videoAnchorsSample: [],
    modalIdLinkCount: 0,
    modalIdLinks: [],
    modalIdLinksSample: [],
    awemeIdCount: 2,
    awemeIds: ["7634192733514501001", "7634192733514501002"],
    awemeIdsSample: ["7634192733514501001", "7634192733514501002"],
    gridCardCandidateCount: 2,
    gridCards: [],
    gridCardSelectorHits: {},
    scrollContainerFound: true,
    scrollContainerSelector: "main",
    scrollTop: 0,
    scrollHeight: 1200,
    clientHeight: 800,
    emptyProfileDetected: false,
    loginWallDetected: false,
    captchaDetected: false,
    checkpointDetected: false,
    networkOrPageBlockedDetected: false,
    probeError: null
  };
  assert.equal(isDouyinProfileGridReadyFromProbe(probe), true);
  const dryRun = modalWholeProfileProbeToDryRunResult(
    1,
    "7634192733514501001",
    "https://www.douyin.com/video/7634192733514501001",
    {
      aweme_id: "7634192733514501001",
      probe_status: "PASS",
      ready_for_full_harvest: true,
      duration_seconds: 24,
      duration_text: "00:24",
      like_count: 1,
      comment_count: 2,
      favorite_count: 3,
      share_count: 4,
      posted_text: "posted",
      action_blocks_found: 4,
      current_modal_id_before: "7634192733514501001",
      current_modal_id_after: "7634192733514501001",
      extracted_aweme_id: "7634192733514501001"
    },
    "2026-05-14T00:00:00.000Z",
    "2026-05-14T00:00:02.000Z"
  );
  assert.equal(dryRun.status, "pass");
  assert.equal(dryRun.aweme_id, "7634192733514501001");
}

{
  assert.equal(modalWholeProfileSamplingModeFor("dry_run_random_n", "random_n"), "random_n");
}

{
  const run = createModalWholeProfileTestRun({
    expected_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
    resolved_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
    verified_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
    mode: "dry_run_first_n",
    dry_run_limit: 3,
    dry_run_sampling_mode: "first_n"
  });
  assert.equal(run.schema_version, MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION);
  assert.equal(isModalWholeProfileTestRun(run), true);
}

console.log("modal whole profile 22C-12B source and utility tests passed");
