import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildPassiveNetworkStoredTarget22C12A,
  classifyPassiveNetworkEndpointKind22C12A,
  createPassiveNetworkProbeSummary22C12A,
  extractPassiveNetworkBatch22C12A,
  markPassiveNetworkProbeListenerReady22C12A,
  markPassiveNetworkProbeReady22C12A,
  mergePassiveNetworkProbeBatch22C12A
} from "./networkProbe22C12A.js";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageNetworkHookSource = readFileSync(join(testDir, "pageNetworkHook.ts"), "utf-8");
const contentScriptSource = readFileSync(join(testDir, "contentScript.ts"), "utf-8");
const backgroundSource = readFileSync(join(testDir, "background.ts"), "utf-8");
const popupSource = readFileSync(join(testDir, "popup.ts"), "utf-8");

{
  assert.equal(classifyPassiveNetworkEndpointKind22C12A("/aweme/v1/web/aweme/post/"), "profile_post");
  assert.equal(classifyPassiveNetworkEndpointKind22C12A("/aweme/v1/web/aweme/favorite/"), "favorite");
  assert.equal(classifyPassiveNetworkEndpointKind22C12A("/aweme/v1/web/aweme/list/"), "other_aweme_list");
}

{
  const batch = extractPassiveNetworkBatch22C12A({
    urlPath: "/aweme/v1/web/aweme/post/",
    method: "GET",
    status: 200,
    payload: {
      aweme_list: [
        {
          aweme_id: "7634192733514501001",
          desc: "one",
          create_time: 1767225600,
          video: { duration: 24000, cover: { url_list: ["https://p3.douyinpic.com/cover-1.webp"] } },
          statistics: { digg_count: 1, comment_count: 2, share_count: 3 }
        }
      ]
    }
  });
  assert.equal(batch?.detectedShape, "aweme_list");
  assert.equal(batch?.awemeCount, 1);
  assert.equal(batch?.targets[0]?.aweme_id, "7634192733514501001");
  assert.equal(batch?.targets[0]?.duration, 24);
}

{
  const requestUrl = "https://www.douyin.com/aweme/v1/web/aweme/post/?sec_user_id=MS4wLjABCD&count=18&max_cursor=0&msToken=token";
  const batch = extractPassiveNetworkBatch22C12A({
    urlPath: requestUrl,
    requestUrl,
    method: "GET",
    status: 200,
    payload: { aweme_list: [{ aweme_id: "7634192733514501777" }] }
  });
  assert.equal(batch?.requestUrl, requestUrl, "passive batch must carry the real same-origin request URL for template recovery");
  assert.equal(batch?.targets[0]?.request_url, requestUrl, "profile-post targets must carry the real request URL, not only synthesized video source_url");
}

{
  const batch = extractPassiveNetworkBatch22C12A({
    urlPath: "/aweme/v1/web/aweme/post/",
    method: "GET",
    status: 200,
    payload: {
      data: {
        aweme_list: [{ aweme_id: "7634192733514501011" }],
        max_cursor: "1700000000",
        min_cursor: 123,
        has_more: 1,
        next_cursor: "1700000100"
      }
    }
  });
  assert.equal(batch?.cursor, "1700000000", "profile post extractor must preserve max_cursor for pagination");
  assert.equal(batch?.hasMore, true, "profile post extractor must normalize has_more for pagination");
  assert.deepEqual(batch?.cursorFields, {
    cursor: null,
    max_cursor: "1700000000",
    min_cursor: 123,
    next_cursor: "1700000100",
    has_more: true,
    hasMore: null,
    offset: null,
    page: null,
    next: null
  });
}

{
  const batch = extractPassiveNetworkBatch22C12A({
    urlPath: "/aweme/v1/web/aweme/post/",
    method: "POST",
    status: 200,
    payload: {
      data: {
        list: [
          {
            awemeId: "7634192733514501002",
            title: "two",
            createTime: 1767225601,
            videoInfo: { duration: 11_000, origin_cover: { url_list: ["https://p3.douyinpic.com/cover-2.webp"] } },
            stats: { likeCount: "7", commentCount: "8", shareCount: "9" }
          }
        ]
      }
    }
  });
  assert.equal(batch?.detectedShape, "data.list");
  assert.equal(batch?.targets[0]?.aweme_id, "7634192733514501002");
  assert.equal(batch?.targets[0]?.like_count, 7);
}

{
  const batch = extractPassiveNetworkBatch22C12A({
    urlPath: "/aweme/v1/web/aweme/post/",
    method: "GET",
    status: 200,
    payload: {
      items: [
        { aweme_id_str: "7634192733514501003", desc: "same" },
        { aweme_id: "7634192733514501003", desc: "duplicate" }
      ]
    }
  });
  assert.equal(batch?.awemeCount, 1, "probe extractor must dedupe aweme ids");
}

{
  const batch = extractPassiveNetworkBatch22C12A({
    urlPath: "/aweme/v1/web/aweme/post/?msToken=secret",
    method: "GET",
    status: 200,
    payload: {
      aweme_list: [{ aweme_id: "7634192733514501004", desc: "long".repeat(200) }]
    }
  });
  assert.ok(batch);
  assert.equal("headers" in batch!, false, "probe batch must not include headers");
  assert.equal("cookies" in batch!, false, "probe batch must not include cookies");
  assert.equal("rawResponse" in batch!, false, "probe batch must not include raw responses");
  assert.equal("raw_response" in batch!, false, "probe batch must not include raw responses");
  assert.equal("authorization" in batch!, false, "probe batch must not include authorization");
  assert.equal(batch?.urlPath.includes("?"), false, "probe batch urlPath must be path-only without query secrets");
  assert.ok((batch!.targets[0]?.desc?.length ?? 0) <= 283, "probe desc must be truncated");
}

{
  const stored = buildPassiveNetworkStoredTarget22C12A({
    target: {
      aweme_id: "7634192733514501999",
      source_url: "https://www.douyin.com/video/7634192733514501999",
      desc: "favorite item",
      cover_url: null,
      duration: null,
      create_time: null,
      like_count: null,
      comment_count: null,
      favorite_count: null,
      share_count: null
    },
    profileUrl: "https://www.douyin.com/user/MS4wLjABCD",
    urlPath: "/aweme/v1/web/aweme/favorite/",
    capturedAt: "2026-05-14T05:00:00.000Z"
  });
  assert.equal(stored.endpoint_kind, "favorite");
  assert.equal(stored.endpoint_path, "/aweme/v1/web/aweme/favorite/");
  assert.equal(stored.profile_url, "https://www.douyin.com/user/MS4wLjABCD");
}

{
  const base = createPassiveNetworkProbeSummary22C12A();
  const listenerReady = markPassiveNetworkProbeListenerReady22C12A(base);
  const bridgeReady = markPassiveNetworkProbeReady22C12A(listenerReady, "2026-05-14T04:59:00.000Z");
  const batch = extractPassiveNetworkBatch22C12A({
    urlPath: "/aweme/v1/web/aweme/post/",
    method: "GET",
    status: 200,
    payload: { aweme_list: [{ aweme_id: "7634192733514501005" }, { aweme_id: "7634192733514501006" }] }
  });
  assert.equal(bridgeReady.network_probe_version, "22C-12A-R3");
  assert.equal(bridgeReady.network_probe_content_listener_ready, "yes");
  assert.equal(bridgeReady.network_probe_bridge_ready, "yes");
  const merged = mergePassiveNetworkProbeBatch22C12A(bridgeReady, { type: "REUP_DOUYIN_NETWORK_AWEME_BATCH_22C12A_R3", traceVersion: "22C-12A-R3", ...batch! }, "2026-05-14T05:00:00.000Z");
  assert.equal(merged.network_probe_batches_seen, 1);
  assert.equal(merged.network_probe_unique_aweme_count, 2);
  assert.deepEqual(merged.network_probe_endpoint_samples, ["/aweme/v1/web/aweme/post/"]);
  assert.equal(merged.network_probe_endpoint_count, 1);
}

assert.match(pageNetworkHookSource, /win\.fetch = async \(\.\.\.args\) => \{[\s\S]*observeResponse\(response\.url \|\| String\(args\[0\] \|\| "fetch"\), response\.clone\(\), methodFromFetchArgs\(args\), response\.status \|\| null\)/, "fetch interceptor must feed passive 22C-12A-R3 probe extraction");
assert.match(pageNetworkHookSource, /function safeXhrResponseText\(xhr\) \{[\s\S]*const responseType = xhr\.responseType \|\| "";[\s\S]*responseType !== "" && responseType !== "text"[\s\S]*try \{[\s\S]*xhr\.responseText[\s\S]*catch/, "XHR interceptor must guard responseText access for non-text response types");
assert.match(pageNetworkHookSource, /OriginalXHR\.prototype\.send = function send\(body\) \{[\s\S]*const text = safeXhrResponseText\(this\);[\s\S]*observeJson\(responseUrl, safeParseJson\(text\), this\.__reupDouyinMethod \|\| "GET", typeof this\.status === "number" \? this\.status : null\)/, "XHR interceptor must feed text responses into passive 22C-12A-R3 probe extraction");
assert.match(pageNetworkHookSource, /REUP_DOUYIN_NETWORK_PROBE_READY_22C12A_R3/, "page hook must publish a ready handshake event");
assert.match(pageNetworkHookSource, /type: PROBE_EVENT_TYPE, traceVersion: "22C-12A-R3"/, "page hook must post passive probe batches across the page bridge");
assert.match(pageNetworkHookSource, /cursorFields/, "page hook must expose cursor fields for 22C-12B-R2 post pagination");
assert.match(contentScriptSource, /REUP_DOUYIN_NETWORK_AWEME_BATCH_22C12A_R3/, "content script must listen for passive 22C-12A-R3 probe events");
assert.match(contentScriptSource, /DOUYIN_NETWORK_PROBE_STATUS_22C12A_R3/, "content script must preserve the compatibility passive probe status handler");
assert.match(contentScriptSource, /__REUP_RUNTIME_AUTHORITY_22C11B__/, "content script must expose the current unified runtime authority");
assert.match(contentScriptSource, /DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B/, "content script must expose the current unified runtime authority snapshot message");
assert.match(contentScriptSource, /function getRuntimeSnapshot\(\)/, "content script must expose the canonical live runtime snapshot API");
assert.match(contentScriptSource, /runtime_authority_version/, "runtime authority snapshot must include its version");
assert.match(contentScriptSource, /diagnostics_runtime_version/, "runtime authority snapshot must include diagnostics version");
assert.match(contentScriptSource, /runtime_health_status/, "runtime authority snapshot must include health status");
assert.match(popupSource, /DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B/, "popup must query live runtime authority from the active tab");
assert.doesNotMatch(popupSource, /sendMessage\(tab\.id, \{ type: "DOUYIN_NETWORK_PROBE_STATUS_22C12A_R3"/, "popup must not use the stale passive probe status route as its authority");
assert.match(popupSource, /active_tab_runtime_authority_snapshot_22C11B/, "popup diagnostics must identify the authority snapshot sync source");
const popupLiveProbeSyncBody = popupSource.match(/async function syncLiveNetworkProbeDiagnosticsIntoState\(state: WholeProfileHarvestState\): Promise<WholeProfileHarvestState> \{[\s\S]*?\n\}/)?.[0] ?? "";
assert.match(popupLiveProbeSyncBody, /diagnostics_channel: "runtime_debug_diagnostics"/, "popup live probe sync must isolate runtime debug diagnostics");
assert.match(popupLiveProbeSyncBody, /readWholeProfileHarvestState\(chrome\.storage\.local, now\)/, "popup live probe sync must re-read fresh storage before writing");
assert.match(popupLiveProbeSyncBody, /profile_scan: fresh\.profile_scan/, "popup live probe sync must preserve profile_scan authority diagnostics from fresh storage");
assert.match(popupLiveProbeSyncBody, /verify: fresh\.verify/, "popup live probe sync must preserve verify authority diagnostics from fresh storage");
assert.match(contentScriptSource, /createPassiveNetworkProbeSummary22C12A/, "content script must initialize passive probe summary state");
assert.match(contentScriptSource, /persistPassiveNetworkProbeDiagnostics22C12A/, "content script must persist passive probe summary diagnostics");
const passiveProbePersistBody = contentScriptSource.match(/async function persistPassiveNetworkProbeDiagnostics22C12A\(\): Promise<void> \{[\s\S]*?\n\}/)?.[0] ?? "";
assert.match(passiveProbePersistBody, /diagnostics_channel: "runtime_debug_diagnostics"/, "passive probe persistence must write only runtime debug diagnostics");
assert.match(passiveProbePersistBody, /profile_scan: state\.profile_scan/, "passive probe persistence must preserve profile_scan authority diagnostics untouched");
assert.match(passiveProbePersistBody, /verify: state\.verify/, "passive probe persistence must preserve verify authority diagnostics untouched");
assert.doesNotMatch(passiveProbePersistBody, /profile_scan:[\s\S]*diagnostics:\s*\{[\s\S]*\.\.\.summary/, "passive probe persistence must not merge probe summary into profile_scan.diagnostics");
assert.doesNotMatch(passiveProbePersistBody, /verify:[\s\S]*diagnostics:\s*\{[\s\S]*\.\.\.summary/, "passive probe persistence must not merge probe summary into verify.diagnostics");
assert.match(contentScriptSource, /stale_update_rejected/, "passive probe persistence must record stale write rejections");
assert.match(contentScriptSource, /lower_priority_than_terminal_stage/, "passive probe persistence must reject lower-priority writes after terminal stages");
assert.match(contentScriptSource, /older_scan_run_id/, "passive probe persistence must reject stale run-id writes");
assert.match(contentScriptSource, /older_updated_at/, "passive probe persistence must reject older timestamp writes");
assert.match(contentScriptSource, /MINIMAL_SCAN_NETWORK_PROBE_READY_WAIT_MS_22C12B/, "minimal scanner must define a bounded probe-ready wait budget");
assert.match(contentScriptSource, /waitForPassiveNetworkProbeForMinimalScan22C12B/, "minimal scanner must include a dedicated probe wait helper");
assert.match(contentScriptSource, /initializePassiveNetworkProbe22C12AR2\(\);[\s\S]*waitForPassiveNetworkProbeForMinimalScan22C12B/, "minimal scanner must re-check passive probe readiness at scan start");
assert.match(contentScriptSource, /network_probe_page_script_injection_attempted/, "minimal scanner diagnostics must expose page-script injection-attempted status");
assert.match(contentScriptSource, /minimal_scan_network_probe_wait_result_22C12B/, "minimal scanner diagnostics must expose probe wait result");
assert.match(contentScriptSource, /minimal_scan_network_probe_post_scroll_settle_observed_new_profile_post_batch_22C12B/, "minimal scanner diagnostics must expose post-scroll network settle evidence");
assert.match(contentScriptSource, /network_collection_stop_reason/, "minimal scanner diagnostics must emit network collection stop reason");
assert.match(contentScriptSource, /MINIMAL_SCAN_ACTIVE_PROFILE_POST_FETCH_MAX_PAGES_22C12B/, "minimal scanner must bound active profile-post fetch pagination pages");
assert.match(contentScriptSource, /runActiveSameOriginProfilePostFetch22C12B/, "minimal scanner must include active same-origin profile-post fetch helper");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_stop_reason_22C12B/, "minimal scanner diagnostics must expose active profile-post fetch stop reason");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_only_aweme_count_22C12B/, "minimal scanner diagnostics must expose active-only aweme supplementation counts");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B/, "minimal scanner diagnostics must expose endpoint variant attempt counts");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B/, "minimal scanner diagnostics must expose endpoint variant success route");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_route_22C12B/, "minimal scanner diagnostics must expose parser route selection");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B/, "minimal scanner diagnostics must expose parser routes tried");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B/, "minimal scanner diagnostics must expose parser direct routes tried");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B/, "minimal scanner diagnostics must expose parser direct match counts");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B/, "minimal scanner diagnostics must expose parser fallback attempted state");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B/, "minimal scanner diagnostics must expose parser fallback match count");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B/, "minimal scanner diagnostics must expose parser fallback candidate counts");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B/, "minimal scanner diagnostics must expose parser fallback visited-node evidence");
assert.match(contentScriptSource, /network_profile_post_active_count/, "scan source ledger must expose active profile-post contribution");
assert.match(contentScriptSource, /required_query_keys_unavailable/, "active profile-post fetch must expose required query-key preflight blocking");
assert.match(contentScriptSource, /active_profile_post_response_status_non_zero/, "active profile-post fetch must classify non-zero response status explicitly");
assert.match(contentScriptSource, /active_profile_post_template_recovery_attempted/, "active profile-post diagnostics must expose template recovery attempted state");
assert.match(contentScriptSource, /active_profile_post_template_recovery_steps/, "active profile-post diagnostics must expose template recovery steps");
assert.match(contentScriptSource, /active_profile_post_template_recovery_result/, "active profile-post diagnostics must expose template recovery result");
assert.match(contentScriptSource, /active_profile_post_template_recovery_error/, "active profile-post diagnostics must expose template recovery errors");
assert.match(contentScriptSource, /active_profile_post_template_query_key_sources/, "active profile-post diagnostics must expose query-key sources");
assert.match(contentScriptSource, /active_profile_post_template_added_default_count/, "active profile-post diagnostics must expose default count recovery");
assert.match(contentScriptSource, /active_profile_post_template_added_default_max_cursor/, "active profile-post diagnostics must expose default max_cursor recovery");
assert.match(contentScriptSource, /active_profile_post_template_derived_sec_user_id/, "active profile-post diagnostics must expose profile-derived sec_user_id recovery");
assert.match(contentScriptSource, /active_profile_post_canonical_profile_url/, "active profile-post diagnostics must expose canonical profile URL");
assert.match(contentScriptSource, /active_profile_post_original_profile_url/, "active profile-post diagnostics must expose original profile URL with extra params");
assert.match(contentScriptSource, /active_profile_post_warmup_scroll_attempted/, "active profile-post diagnostics must expose bounded warm-up scroll attempts");
assert.match(contentScriptSource, /active_profile_post_warmup_performance_resource_count/, "active profile-post diagnostics must expose warm-up performance resource count");
assert.match(contentScriptSource, /active_profile_post_warmup_network_probe_ready/, "active profile-post diagnostics must expose network probe ready state during warm-up");
assert.match(contentScriptSource, /active_profile_post_warmup_post_endpoint_seen/, "active profile-post diagnostics must expose whether warm-up saw the post endpoint");
assert.match(contentScriptSource, /active_profile_post_start_blocked_reason/, "active profile-post diagnostics must expose startup block reason");
assert.match(pageNetworkHookSource, /const requestUrl = safeRequestUrl22C13B\(source\);[\s\S]*request_url: requestUrl[\s\S]*requestUrl,/, "page hook must bridge the real profile-post request URL into passive probe batches and targets");
assert.match(contentScriptSource, /for \(const target of passiveNetworkProbeTargetsByKind22C12A\.profile_post\.values\(\)\) \{\s*if \(target\.request_url\) addCandidate\(target\.request_url, "passive_network_metadata_cache"\);\s*\}/, "template discovery must use real passive probe request_url instead of synthesized video source_url");
assert.doesNotMatch(contentScriptSource, /addCandidate\(target\.source_url, "passive_network_metadata_cache"\)/, "template discovery must not reinterpret synthesized video source_url as an API request template");
assert.match(contentScriptSource, /syntheticFallback/, "active profile-post templates must explicitly track synthetic fallback state");
assert.match(contentScriptSource, /synthetic_fallback_not_usable/, "synthetic fallback templates must be diagnosed as unusable");
assert.match(contentScriptSource, /active_profile_post_template_usable/, "active profile-post diagnostics must expose template usability authority");
assert.match(contentScriptSource, /active_profile_post_template_usable_reason/, "active profile-post diagnostics must expose template usability reason");
assert.match(contentScriptSource, /active_profile_post_template_is_synthetic/, "active profile-post diagnostics must expose synthetic template status");
assert.match(contentScriptSource, /function isUsableActiveProfilePostTemplate22C13B[\s\S]*Synthetic fallback query keys are not enough; active pagination requires a real, cached, or same-run default direct API profile-post template\./, "usable-template predicate must document that synthetic fallback query keys are insufficient while allowing direct API recovery");
assert.match(contentScriptSource, /function isUsableActiveProfilePostTemplate22C13B[\s\S]*template\.syntheticFallback !== true[\s\S]*template\.requestUrl !== null[\s\S]*template\.requiredQueryKeysAvailable === true/, "usable-template predicate must reject synthetic fallback even when required keys were filled");
assert.match(contentScriptSource, /warmupActiveProfilePostTemplate22C13B[\s\S]*isUsableActiveProfilePostTemplate22C13B\(template\) \? "template_ready_initial"/, "warm-up must only skip when the template is usable, not merely when fallback keys are present");
assert.match(contentScriptSource, /profile_post_endpoint_seen_but_source_url_missing/, "active startup diagnostics must expose profile-post endpoint evidence without a recoverable real request URL");
assert.match(backgroundSource, /if \(rawCanonical\.template_found === "no"\)[\s\S]*rawCanonical\.template_required_query_keys_available = "no"[\s\S]*template_ready_initial/, "canonical diagnostics must prevent template_found=no from reporting required keys available or template_ready_initial");
assert.match(contentScriptSource, /derived_sec_user_id_from_profile_url/, "captured post URL missing sec_user_id must recover from the profile URL");
assert.match(contentScriptSource, /added_default_count/, "captured post URL missing count must add the default page size");
assert.match(contentScriptSource, /added_default_max_cursor/, "captured post URL missing max_cursor must add the initial cursor");
assert.match(contentScriptSource, /canonicalProfileUrl22C12B\(\(message\.profileUrl[\s\S]*active_profile_post_original_profile_url/, "profile URLs with extra query params must keep original diagnostics while using a canonical fetch scope");
assert.match(contentScriptSource, /warmupActiveProfilePostTemplate22C13B[\s\S]*ACTIVE_PROFILE_POST_TEMPLATE_WARMUP_MAX_ATTEMPTS_22C13B/, "template acquisition warm-up must be bounded");
assert.match(contentScriptSource, /warmupActiveProfilePostTemplate22C13B[\s\S]*template_not_found_after_warmup/, "no-template-after-warm-up path must report a stable failure reason");
assert.match(contentScriptSource, /defaultDirectActiveProfilePostTemplate22C13B[\s\S]*\/aweme\/v1\/web\/aweme\/post\/[\s\S]*sec_user_id[\s\S]*max_cursor[\s\S]*count/, "template warm-up fallback must build a same-origin default direct profile-post GET template with required query keys");
assert.match(contentScriptSource, /warmupActiveProfilePostTemplate22C13B[\s\S]*discoverActiveProfilePostRequestTemplate22C13B\(input\.secUserId, \{ includeDefaultDirectApiFallback: false \}\)[\s\S]*defaultDirectActiveProfilePostTemplate22C13B/, "template recovery must escalate from page/cache discovery to default direct API instead of repeating the same unavailable path");
assert.match(contentScriptSource, /template_recovery_strategy_attempted[\s\S]*template_recovery_strategies_tried[\s\S]*template_recovery_final_strategy[\s\S]*template_recovery_result[\s\S]*direct_api_fallback_attempted/, "active profile-post diagnostics must expose direct API fallback recovery strategy fields");
assert.match(contentScriptSource, /activeProfilePostTemplateFromUrl22C13B[\s\S]*recoveryResult:[\s\S]*not_needed/, "complete captured profile-post templates must remain usable without recovery");
assert.match(contentScriptSource, /\/\/ active profile-post API > same-run profile-post network template > DOM fallback evidence/, "warm-up/template acquisition block must include the required source-priority comment");
assert.doesNotMatch(contentScriptSource.match(/function buildActiveProfilePostRequestUrl22C13B[\s\S]*?\n\}/)?.[0] ?? "", /isSensitiveProfilePostQueryKey22C13B\(key\)[\s\S]*delete\(key\)/, "active profile-post request builder must preserve sensitive anti-bot query params from captured templates");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_expected_count_retry_eligible_22C13B/, "minimal scanner diagnostics must expose expected-count retry eligibility");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_expected_count_retry_attempted_22C13B/, "minimal scanner diagnostics must expose expected-count retry attempted state");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_expected_count_retry_reason_22C13B/, "minimal scanner diagnostics must expose expected-count retry reason");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_before_22C13B/, "minimal scanner diagnostics must expose expected-count retry target count before retry");
assert.match(contentScriptSource, /minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_after_22C13B/, "minimal scanner diagnostics must expose expected-count retry target count after retry");
assert.match(backgroundSource, /DOUYIN_SCAN_PROFILE_MINIMAL_22C11B/, "active Scan Profile route must use the protected 22C-11B scanner message");
assert.match(contentScriptSource, /CONTENT_SCRIPT_VERSION = "22C-13A"/, "content script must expose the 22C-13A manual pagination verification runtime marker");
assert.match(contentScriptSource, /SCAN_PROFILE_PIPELINE_LOCK_22C13A/, "content script must freeze the 22C-12D live stream queue adapter and collector finalization pipeline during 22C-13A");
assert.match(contentScriptSource, /DOUYIN_MANUAL_PAGINATION_TRUTH_TEST_22C13A/, "content script must expose the 22C-13A manual pagination truth test message");
assert.match(contentScriptSource, /runManualPaginationTruthTest/, "content script must implement the dedicated 22C-13A manual pagination verifier");
assert.match(contentScriptSource, /manual_scroll_generated_additional_post_requests/, "manual verifier must persist whether real manual scroll generated additional post requests");
assert.match(contentScriptSource, /post_request_sequence/, "manual verifier must persist compact post request sequence forensics");
assert.match(contentScriptSource, /post_request_cursor_chain/, "manual verifier must persist cursor progression tracking");
assert.match(contentScriptSource, /post_request_has_more_chain/, "manual verifier must persist has_more progression tracking");
assert.match(contentScriptSource, /real_moving_scroll_container/, "manual verifier must persist the real moving scroll container");
assert.match(contentScriptSource, /synthetic_moving_scroll_container/, "manual verifier must persist synthetic scroll container observations");
assert.match(contentScriptSource, /synthetic_missing_momentum/, "manual verifier must persist human-vs-synthetic momentum differences");
assert.match(contentScriptSource, /pagination_activation_results/, "manual verifier must persist isolated controlled experiment results");
assert.match(contentScriptSource, /real_wheel_cadence_replay/, "manual verifier must include the real wheel cadence replay experiment");
assert.match(contentScriptSource, /scroll_real_container/, "manual verifier must include the real container synthetic scroll experiment");
assert.match(contentScriptSource, /scroll_into_view_last_visible_card/, "manual verifier must include the last visible card scrollIntoView experiment");
assert.match(contentScriptSource, /pointer_movement_wheel_combined/, "manual verifier must include the pointer movement plus wheel experiment");
assert.match(contentScriptSource, /const ENABLE_SCAN_DEBUG_INSTRUMENTATION = false;/, "heavy debug instrumentation must be hard-gated off by default");
assert.match(contentScriptSource, /function installDebugScanInstrumentation22C13D\(\): void \{[\s\S]*installPaginationReverseEngineering22C12C\(\);[\s\S]*installActivationTruthProbe22C12E\(\);[\s\S]*installManualPaginationVerifier22C13A\(\);[\s\S]*\}\s*if \(ENABLE_SCAN_DEBUG_INSTRUMENTATION\) \{\s*installDebugScanInstrumentation22C13D\(\);\s*\}/, "all heavy debug installers must run only inside the ENABLE_SCAN_DEBUG_INSTRUMENTATION bootstrap");
assert.match(contentScriptSource, /if \(!ENABLE_SCAN_DEBUG_INSTRUMENTATION\) \{[\s\S]*reason: "scan_debug_instrumentation_disabled"[\s\S]*scan_debug_instrumentation_installers_ran: \[\.\.\.scanDebugInstrumentationInstallersRan\][\s\S]*\}\);[\s\S]*return true;[\s\S]*\}\s*void runManualPaginationTruthTest\(\)/, "manual pagination truth test runtime must be disabled when heavy debug instrumentation is off");
assert.match(contentScriptSource, /scan_debug_instrumentation_enabled: ENABLE_SCAN_DEBUG_INSTRUMENTATION \? "yes" : "no"/, "runtime diagnostics must expose whether heavy debug instrumentation is enabled");
assert.match(contentScriptSource, /scan_debug_instrumentation_installers_ran: \[\.\.\.scanDebugInstrumentationInstallersRan\]/, "runtime diagnostics must expose exactly which heavy debug installers ran");
assert.match(contentScriptSource, /__REUP_MANUAL_PARITY_TRACE_22C12E__/, "content script must expose the 22C-12E manual parity trace runtime");
assert.match(contentScriptSource, /__REUP_DEBUG_PAGINATION_22C12E__/, "content script must expose the 22C-12E debug pagination API");
assert.match(contentScriptSource, /activation_truth_probe_version/, "content script must persist activation truth probe diagnostics");
assert.match(contentScriptSource, /interaction_trace_runtime_version/, "content script must persist interaction trace runtime diagnostics");
assert.match(contentScriptSource, /pre_post_request_event_sequence/, "content script must capture pre-request activation buffers for post batches");
assert.match(contentScriptSource, /candidate_scroll_container_matrix/, "content script must expose active container discovery V2 diagnostics");
assert.match(contentScriptSource, /profile_intersection_observer_count/, "content script must expose IntersectionObserver reverse engineering diagnostics");
assert.match(contentScriptSource, /human_vs_extension_scroll_differences/, "content script must expose human-vs-synthetic differential diagnostics");
assert.match(contentScriptSource, /network_stream_total_batches/, "content script must diagnose consumed live network stream batches");
assert.match(contentScriptSource, /__REUP_TRACE_PAGINATION_22C12C__/, "content script must expose 22C-12C pagination trace mode");
assert.match(contentScriptSource, /__REUP_PAGINATION_DEBUG_22C12C__/, "content script must expose 22C-12C manual QA helper");
assert.match(contentScriptSource, /detectScrollContainers22C12C/, "content script must detect active scroll containers");
assert.match(contentScriptSource, /window\.IntersectionObserver = class ReupIntersectionObserver22C12C/, "content script must instrument IntersectionObserver without removing callbacks");
assert.match(contentScriptSource, /network_post_cursor_timeline/, "content script must persist compact network post cursor timeline");
assert.match(contentScriptSource, /pagination_activation_experiment_results/, "content script must persist isolated pagination experiment results");
assert.doesNotMatch(contentScriptSource.match(/getPaginationReverseEngineeringDiagnostics22C12C[\s\S]*?\n\}/)?.[0] ?? "", /rawResponse|raw_response|responseText|raw_body/, "22C-12C diagnostics must not persist raw response bodies");
assert.match(contentScriptSource, /collector_idle_after_last_live_batch/, "content script must prove stop decisions use live idle-after-last-batch semantics");
assert.match(contentScriptSource, /NETWORK_STREAM_IDLE_AFTER_LAST_BATCH_MS_22C12D/, "content script must preserve the idle-after-last-batch timeout constant");
assert.match(contentScriptSource, /network_stream_total_batches/, "content script must track live stream batch counts for pagination proof");
assert.match(contentScriptSource, /__REUP_NETWORK_STREAM_22C12D__/, "content script must expose the 22C-12D live network stream runtime");
assert.match(contentScriptSource, /subscribe\(listener\)/, "live stream runtime must support event-driven subscribers");
assert.match(contentScriptSource, /getRecentBatches\(\)/, "live stream runtime must expose recent compact batches");
assert.match(contentScriptSource, /getRecentTargets\(\)/, "live stream runtime must expose recent compact targets");
assert.match(contentScriptSource, /getLiveNetworkStreamRuntime22C12D\(\)\.emit\(batch, endpointKind, batch\.urlPath, now, newAwemeCount\)/, "content script must emit live network batches immediately from the page bridge path");
assert.match(contentScriptSource, /liveNetworkStreamProfileCollector22C13A/, "collector diagnostics must expose the 22C-13A manual pagination verification engine marker");
assert.match(contentScriptSource, /collector_idle_after_last_live_batch/, "collector must preserve live idle-after-last-batch semantics");
assert.match(contentScriptSource, /network_stream_queue_adapter_22C12D/, "queue must be built through the 22C-12D live stream adapter");
assert.match(contentScriptSource, /\.filter\(\(target\) => target\.endpoint_kind === "profile_post"\)/, "live stream queue adapter must exclude favorite endpoint targets");
assert.doesNotMatch(contentScriptSource.match(/getLiveNetworkStreamDiagnostics22C12D[\s\S]*?\n\}/)?.[0] ?? "", /rawResponse|raw_response|responseText|raw_body|cookies|headers|authorization/i, "22C-12D stream diagnostics must not persist raw responses or secrets");
assert.match(popupSource, /runtime_authority_snapshot[\s\S]*popupRuntimeVersionDiagnostics\(\)/, "popup diagnostics must merge live runtime authority snapshot state");
assert.match(popupSource, /popup_live_runtime_connected/, "popup diagnostics must persist live runtime connectivity");
assert.match(popupSource, /popup_runtime_last_sync_at/, "popup diagnostics must persist the last live runtime sync timestamp");
assert.match(popupSource, /popup_runtime_sync_source/, "popup diagnostics must persist the live runtime sync source");

console.log("passive network probe 22C-12A-R3, unified runtime authority 22C-11B, and pagination verifier 22C-13A tests passed");
