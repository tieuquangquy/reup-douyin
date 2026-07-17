import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { classifyPage } from "./extractor";
import { normalizeDouyinNetworkPayload } from "./networkCache";

const testDir = dirname(fileURLToPath(import.meta.url));
const extractorSource = readFileSync(join(testDir, "extractor.ts"), "utf-8");
const popupTransportSource = readFileSync(join(testDir, "popupTransport.ts"), "utf-8");
const typeSource = readFileSync(join(testDir, "types.ts"), "utf-8");
const contentScriptSource = readFileSync(join(testDir, "contentScript.ts"), "utf-8");
const pageNetworkHookSource = readFileSync(join(testDir, "pageNetworkHook.ts"), "utf-8");
const detailHydrationSource = readFileSync(join(testDir, "detailHydration.ts"), "utf-8");
const manifestSource = readFileSync(join(testDir, "..", "public", "manifest.json"), "utf-8");

assert.equal(classifyPage("https://www.douyin.com/user/MS4wLjABAAAAfixture", "Creator", "", 0), "profile_page");
assert.equal(classifyPage("https://www.douyin.com/user/MS4wLjABAAAAfixture", "Creator", "", 2), "profile_feed_page");
assert.equal(classifyPage("https://www.douyin.com/video/123456", "Video", "", 0), "video_detail_page");
assert.equal(classifyPage("https://www.douyin.com/", "Login", "登录", 0), "login_page");
assert.equal(classifyPage("https://www.douyin.com/", "Captcha", "验证码", 0), "challenge_page");
assert.equal(classifyPage("https://example.com/", "Example", "", 0), "unsupported_page");

assert.match(typeSource, /thumbnail_url\?: string \| null/, "VideoPayload must expose canonical thumbnail_url");
assert.match(typeSource, /poster_url\?: string \| null/, "VideoPayload must expose poster_url alias");
assert.match(typeSource, /cover_url\?: string \| null/, "VideoPayload must expose cover_url alias");
assert.match(typeSource, /url_list\?: string\[\]/, "VideoPayload must preserve captured thumbnail URL lists");
assert.match(typeSource, /thumbnail_source_types\?: string\[\]/, "VideoPayload must preserve safe thumbnail source diagnostics");
assert.match(typeSource, /interface NetworkVideoMetadata/, "Extension types must expose network video metadata");
assert.match(typeSource, /thumbnail_source_type\?: string \| null/, "VideoPayload must expose the winning thumbnail source type");
assert.match(extractorSource, /export function discoverGridVideos\(document: Document, diagnostics: DiscoveryDiagnostics = createDiscoveryDiagnostics\(\)\): GridDiscoveryRecord\[\]/, "Extractor must expose a discovery-only grid scan");
assert.match(extractorSource, /type GridDiscoveryRecord = \{[\s\S]*aweme_id: string;[\s\S]*source_url: string;[\s\S]*visible_order: number;[\s\S]*link: HTMLAnchorElement;/, "Grid discovery records must contain identity and order, not primary metadata");
assert.match(extractorSource, /function buildDomFallbackMetadata\(discovery: GridDiscoveryRecord\): DomFallbackMetadata/, "Extractor must keep DOM metadata extraction in a fallback phase after discovery");
assert.match(extractorSource, /thumbnailFromCard\(card, discovery\.link\)/, "DOM fallback must map card thumbnails only after discovery");
assert.match(extractorSource, /querySelectorAll<HTMLImageElement>\("img"\)/, "Extractor must inspect card images for last-resort DOM fallback");
assert.match(extractorSource, /image\.currentSrc/, "Extractor must inspect img.currentSrc");
assert.match(extractorSource, /image\.src/, "Extractor must inspect img.src");
assert.match(extractorSource, /image\.getAttribute\("src"\)/, "Extractor must inspect raw img src attributes");
assert.match(extractorSource, /image\.getAttribute\("data-src"\)/, "Extractor must inspect lazy data-src attributes");
assert.match(extractorSource, /querySelectorAll<HTMLVideoElement>\("video\[poster\]"\)/, "Extractor must inspect video posters");
assert.match(extractorSource, /Object\.entries\(element\.dataset\)/, "Extractor must inspect image-like dataset values");
assert.match(extractorSource, /imageCandidatesFromAttributes/, "Extractor must inspect safe image-like data attributes");
assert.match(extractorSource, /imageCandidatesFromBackgrounds/, "Extractor must inspect inline and computed background images");
assert.match(extractorSource, /window\.getComputedStyle\(element\)\.backgroundImage/, "Extractor must inspect computed background-image values");
assert.match(extractorSource, /backgroundImageCandidates/, "Extractor must parse CSS background-image URLs");
assert.match(extractorSource, /thumbnail_url: thumbnailUrl/, "Extractor must emit canonical thumbnail_url when found");
assert.match(extractorSource, /poster_url: thumbnailUrl/, "Extractor must mirror the canonical thumbnail into poster_url for portrait card posters");
assert.match(extractorSource, /thumbnail_source_type: thumbnailSource \?\? dom\?\.thumbnail\.thumbnail_source_type \?\? null/, "Extractor must record the winning thumbnail source type");
assert.match(extractorSource, /thumbnailCandidateScore/, "Extractor must score candidates instead of trusting the first image-like URL");
assert.match(extractorSource, /isLocalCardForLink[\s\S]*distinctIds\.length === 1/, "Extractor must reject shared card ancestors containing multiple distinct video links");
assert.match(extractorSource, /extractDuration\(text\)/, "Extractor must derive visible duration text from card text");
assert.match(extractorSource, /extractPosted\(text\)/, "Extractor must derive visible posted date text from card text");
assert.match(extractorSource, /view_count_text/, "Extractor must preserve raw visible view-count text");
assert.match(extractorSource, /like_count_text/, "Extractor must preserve raw visible like-count text");
assert.match(extractorSource, /comment_count_text/, "Extractor must preserve raw visible comment-count text");
assert.match(extractorSource, /preview_status: thumbnailUrl \? "ready" : "missing"/, "Extractor preview readiness must depend on a real thumbnail");
assert.match(extractorSource, /source_link_status: discovery\.source_url \|\| shareUrl \? "captured" : "missing"/, "Extractor must emit source-link capture readiness separately");
assert.match(extractorSource, /media_asset_status: "not_generated"/, "Extractor must not mark internal media assets ready from source-link capture alone");
assert.match(extractorSource, /media_status: discovery\.source_url \|\| shareUrl \? "source_link_captured" : "missing"/, "Extractor must preserve legacy media_status compatibility truthfully");
assert.match(extractorSource, /thumbnail_candidate_video_count/, "Extractor diagnostics must include safe thumbnail video counts");
assert.match(extractorSource, /duration_text_video_count/, "Extractor diagnostics must include safe duration counts");
assert.match(extractorSource, /posted_text_video_count/, "Extractor diagnostics must include safe posted-text counts");
assert.match(extractorSource, /thumbnail_source_types/, "Extractor must emit safe thumbnail source diagnostics");
assert.match(extractorSource, /network_metadata_video_count/, "Extractor diagnostics must count network-backed videos");
assert.match(extractorSource, /function buildCanonicalVideoPayload\(item: HydratedItem, context\?: CaptureContext\): VideoPayload/, "Extractor must assemble canonical payloads only after per-aweme hydration");
assert.match(extractorSource, /grid_metadata_primary: false/, "Extractor diagnostics must state that grid metadata is not primary truth");
assert.match(extractorSource, /console\.debug\("\[reup-douyin\] visible grid capture"/, "Extractor must emit safe representative debug logging");
assert.match(extractorSource, /preview_status_counts/, "Extractor debug logging must include safe preview status counts");
assert.match(extractorSource, /source_link_status_counts/, "Extractor debug logging must include safe source-link status counts");
assert.match(extractorSource, /media_asset_status_counts/, "Extractor debug logging must include safe media-asset status counts");
assert.match(popupTransportSource, /tryContentScriptAction/, "Popup transport should prefer the content-script bridge before direct fallback");
assert.match(manifestSource, /"run_at": "document_start"/, "Content script must inject the page hook at document_start so page-world network responses are not missed");
assert.match(contentScriptSource, /event\.data\?\.type !== "REUP_DOUYIN_NETWORK_CACHE_UPDATE"/, "Content script must listen for the page-world network cache bridge event");
assert.match(contentScriptSource, /mergeNetworkCacheItems\(event\.data\.items\.slice\(0, 240\)\)/, "Content script must merge bridged page-world network evidence into the extractor cache");
assert.match(contentScriptSource, /hydrateDetailEvidenceForDiscoveries\(discoveries\)/, "Content script capture path must trigger detail hydration fallback for discovered aweme_ids");
assert.match(pageNetworkHookSource, /normalizeDouyinNetworkPayload\(json, safeSource\(source\)\)/, "Page hook must normalize intercepted responses into canonical network metadata");
assert.match(pageNetworkHookSource, /win\.__REUP_DOUYIN_NETWORK_CACHE__ = mergeItems\(\[\.\.\.normalized, \.\.\.current\]\)\.slice\(0, MAX_CACHE_ITEMS\)/, "Page hook must write normalized aweme evidence into the shared network cache");
assert.match(pageNetworkHookSource, /publishCache\(win\.__REUP_DOUYIN_NETWORK_CACHE__\)/, "Page hook must publish normalized aweme evidence across the bridge");
assert.match(pageNetworkHookSource, /function stringValue\(value\)[\s\S]*typeof value === "number"[\s\S]*String\(value\)\.trim\(\)/, "Page hook must normalize numeric aweme_id values into strings");
assert.match(popupTransportSource, /function discoverGridVideos\(diagnostics: DiscoveryDiagnostics = createDiscoveryDiagnostics\(\)\): GridDiscoveryRecord\[\]/, "Direct execute-script capture must split discovery from fallback metadata extraction");
assert.match(popupTransportSource, /function buildDomFallbackMetadata\(discovery: GridDiscoveryRecord\): DomFallbackMetadata/, "Direct execute-script capture must keep grid DOM metadata as fallback only");
assert.match(popupTransportSource, /thumbnailFromCard\(card, discovery\.link\)/, "Direct execute-script fallback must map card thumbnails only after discovery");
assert.match(popupTransportSource, /grid_metadata_primary: false/, "Direct execute-script diagnostics must state that grid metadata is not primary truth");
assert.match(popupTransportSource, /isLocalCardForLink[\s\S]*distinctIds\.length === 1/, "Direct execute-script capture must reject shared card ancestors containing multiple distinct video links");
assert.match(popupTransportSource, /const roots = \[card \?\? link\]/, "Direct execute-script capture must keep thumbnail extraction inside the local card or link-only fallback");
assert.match(popupTransportSource, /image\.getAttribute\("data-src"\)/, "Direct execute-script capture must inspect lazy data-src attributes");
assert.match(popupTransportSource, /imageCandidatesFromBackgrounds/, "Direct execute-script capture must inspect background images");
assert.match(popupTransportSource, /thumbnail_url: thumbnailUrl/, "Direct execute-script capture must emit canonical thumbnail_url when found");
assert.match(popupTransportSource, /extractDuration\(text\)/, "Direct execute-script capture must derive visible duration text");
assert.match(popupTransportSource, /extractPosted\(text\)/, "Direct execute-script capture must derive visible posted text");
assert.match(popupTransportSource, /source_link_status: discovery\.source_url \? "captured" : "missing"/, "Direct execute-script capture must emit source-link status");
assert.match(popupTransportSource, /media_asset_status: "not_generated"/, "Direct execute-script capture must not mark internal media assets ready");
assert.match(popupTransportSource, /media_status: discovery\.source_url \? "source_link_captured" : "missing"/, "Direct execute-script capture must preserve truthful legacy media readiness");
assert.match(popupTransportSource, /raw_network_aweme: null/, "Direct execute-script fallback must remain safe and must not fake raw network aweme evidence");
assert.match(popupTransportSource, /raw_detail_aweme: null/, "Direct execute-script fallback must remain safe and must not fake raw detail aweme evidence");
assert.match(detailHydrationSource, /fetchWithTimeout\(fetchImpl, sourceUrl, timeoutMs\)/, "Detail hydration must fetch the source URL with a bounded timeout");
assert.match(detailHydrationSource, /normalizeDouyinNetworkPayload\(root, "detail_hydrate"\)/, "Detail hydration must reuse canonical network normalization for detail evidence");
assert.match(detailHydrationSource, /runWithConcurrencyLimit\(tasks, concurrency\)/, "Detail hydration must respect a concurrency limit");
assert.doesNotMatch(extractorSource, /No thumbnail/, "Extractor must not fabricate UI placeholder thumbnail text");

{
  const networkItems = normalizeDouyinNetworkPayload({
    aweme_list: [
      {
        aweme_id: "1234567890",
        desc: "Network title wins",
        share_info: { share_url: "https://www.douyin.com/video/1234567890" },
        create_time: 1767225600,
        video: {
          duration: 18500,
          cover: { url_list: ["//p3.douyinpic.com/aweme/cover-network.webp"] },
          origin_cover: { url_list: ["//p3.douyinpic.com/aweme/origin-cover-network.webp"] }
        },
        statistics: {
          play_count: "12000",
          digg_count: 345,
          comment_count: "67"
        }
      }
    ]
  });
  assert.equal(networkItems.length, 1, "Network normalizer must find aweme-like payloads");
  assert.equal(networkItems[0]?.aweme_id, "1234567890");
  assert.equal(networkItems[0]?.thumbnail_url, "https://p3.douyinpic.com/aweme/origin-cover-network.webp");
  assert.equal(networkItems[0]?.poster_aspect_ratio, 9 / 16);
  assert.equal(networkItems[0]?.duration_seconds, 19);
  assert.equal(networkItems[0]?.view_count, 12000);
  assert.equal(networkItems[0]?.share_count, null);
}

assert.match(extractorSource, /const networkById = canonicalNetworkMap\(filterNetworkItemsForContext\(networkItems, context\)\)/, "Extractor must context-scope and canonicalize network metadata by aweme_id before hydrate");
assert.match(extractorSource, /const detailById = canonicalNetworkMap\(filterNetworkItemsForContext\(detailHydrateItems, context\)\)/, "Extractor must context-scope and canonicalize detail hydrate metadata by aweme_id before fallback use");
assert.match(extractorSource, /const discoveries = new Map<string, GridDiscoveryRecord>\(\)/, "Grid discovery must store discovered items in a Map keyed by aweme_id");
assert.match(extractorSource, /function exactHydrateForDiscovery\(metadata: NetworkVideoMetadata \| undefined, discovery: GridDiscoveryRecord, warningCode: string\): NetworkVideoMetadata \| undefined/, "Canonical assembly must reject hydrate metadata whose aweme_id does not match discovery aweme_id");
assert.match(extractorSource, /rejected_network_identity_mismatch: Boolean\(rejectedNetworkAwemeId\)/, "Merged output must expose safe rejected network identity mismatch diagnostics");
assert.match(extractorSource, /rejected_detail_identity_mismatch: Boolean\(rejectedDetailAwemeId\)/, "Merged output must expose safe rejected detail identity mismatch diagnostics");
assert.match(
  extractorSource,
  /const thumbnailUrl = networkThumbnail \?\? detailThumbnail \?\? domThumbnail \?\? null/,
  "Merged output must prefer matching network thumbnails, then detail hydrate, before DOM fallback"
);
assert.match(
  extractorSource,
  /thumbnail_source: thumbnailSource/,
  "Merged output must emit explicit thumbnail provenance"
);
assert.match(
  extractorSource,
  /posted_source: postedSource/,
  "Merged output must emit explicit posted provenance"
);
assert.match(
  extractorSource,
  /const title = network\?\.title \?\? network\?\.desc \?\? detail\?\.title \?\? detail\?\.desc \?\? dom\?\.title \?\? null/,
  "Merged output must prefer matching network title or desc, then detail hydrate, before DOM fallback"
);
assert.match(
  extractorSource,
  /const durationText = hasCachedAweme \? \(typeof durationSeconds === "number" \? formatDuration\(durationSeconds\) : null\) : networkDurationText \?\? detailDurationText \?\? domDurationText \?\? \(typeof durationSeconds === "number" \? formatDuration\(durationSeconds\) : null\)/,
  "Merged output must prefer cache duration when present, otherwise matching network duration text, then detail hydrate, then DOM text, then derived text"
);
assert.match(
  extractorSource,
  /const durationSeconds = hasCachedAweme \? cachedDurationSeconds : networkDurationSeconds \?\? detailDurationSeconds \?\? domDurationSeconds \?\? null/,
  "Merged output must prefer cache duration when present, otherwise matching network duration seconds, then detail hydrate, before DOM fallback"
);
assert.match(
  extractorSource,
  /posted_text: hasCachedAweme \? postedAt : networkPostedAt \?\? detailPostedAt \?\? dom\?\.posted\.posted_text \?\? null/,
  "Merged output must preserve cache or authoritative posted timestamps before DOM posted text fallback"
);
assert.match(
  extractorSource,
  /const postedAt = hasCachedAweme \? cachedPostedAt : networkPostedAt \?\? detailPostedAt \?\? domPostedAt \?\? null/,
  "Merged output must prefer cache posted timestamp when present, otherwise valid matching network posted timestamps, then detail hydrate, before parsed DOM fallback"
);
assert.match(
  extractorSource,
  /const postedSource: PostedSource = hasCachedAweme \? cachedPostedAt \? "network_json" : "fallback_none" : networkPostedAt \? "network_json" : detailPostedAt \? "detail_hydrate" : domPostedAt \? "dom_text" : "fallback_none"/,
  "Merged output must use cache/network/detail timestamps before parsed DOM posted source signal"
);
assert.match(
  extractorSource,
  /const networkViewCount = validCount\(network\?\.view_count\);[\s\S]*const detailViewCount = validCount\(detail\?\.view_count\);[\s\S]*const domViewCount = hasCachedAweme \? null : validCount\(dom\?\.metrics\.view_count\);[\s\S]*const viewCount = hasCachedAweme \? cachedViewCount : networkViewCount \?\? detailViewCount \?\? domViewCount \?\? null/,
  "Merged output must prefer cache view count when present, otherwise matching network view count, then detail hydrate, before DOM fallback"
);
assert.match(
  extractorSource,
  /const networkLikeCount = validCount\(network\?\.like_count\);[\s\S]*const detailLikeCount = validCount\(detail\?\.like_count\);[\s\S]*const domLikeCount = hasCachedAweme \? null : validCount\(dom\?\.metrics\.like_count\);[\s\S]*const likeCount = hasCachedAweme \? cachedLikeCount : networkLikeCount \?\? detailLikeCount \?\? domLikeCount \?\? null/,
  "Merged output must prefer cache like count when present, otherwise matching network like count, then detail hydrate, before DOM fallback"
);
assert.match(
  extractorSource,
  /const networkCommentCount = validCount\(network\?\.comment_count\);[\s\S]*const detailCommentCount = validCount\(detail\?\.comment_count\);[\s\S]*const domCommentCount = hasCachedAweme \? null : validCount\(dom\?\.metrics\.comment_count\);[\s\S]*const commentCount = hasCachedAweme \? cachedCommentCount : networkCommentCount \?\? detailCommentCount \?\? domCommentCount \?\? null/,
  "Merged output must prefer cache comment count when present, otherwise matching network comment count, then detail hydrate, before DOM fallback"
);
assert.match(
  extractorSource,
  /const networkShareCount = validCount\(network\?\.share_count\);[\s\S]*const detailShareCount = validCount\(detail\?\.share_count\);[\s\S]*const domShareCount = hasCachedAweme \? null : validCount\(dom\?\.metrics\.share_count\);[\s\S]*const shareCount = hasCachedAweme \? cachedShareCount : networkShareCount \?\? detailShareCount \?\? domShareCount \?\? null/,
  "Merged output must prefer cache share count when present, otherwise matching network share count, then detail hydrate, before DOM fallback"
);
assert.match(
  extractorSource,
  /const engagementRate = deriveEngagementRate\(\{[\s\S]*view_count: viewCount,[\s\S]*like_count: likeCount,[\s\S]*comment_count: commentCount,[\s\S]*share_count: shareCount[\s\S]*\}\)/,
  "Merged output must derive engagement rate from canonical engagement counts"
);
assert.match(extractorSource, /suspiciousDuplicatePayloadMappingCount\(videos\)/, "Extractor diagnostics must count suspicious duplicate network metadata fan-out signatures");
assert.match(
  extractorSource,
  /normalizeImageUrl\(candidate\.url\)/,
  "DOM extraction must normalize protocol-relative thumbnail URLs"
);
assert.match(
  extractorSource,
  /pushCandidate\(values, image\.src, "img\.src"\)[\s\S]*pushCandidate\(values, image\.getAttribute\("data-src"\), "img\.getAttribute\(data-src\)"\)/,
  "DOM extraction must deterministically inspect img.src before lazy data-src fallback"
);
assert.doesNotMatch(
  extractorSource,
  /like\.value \?\? compact\.like_count|comment\.value \?\? compact\.comment_count|view\.value \?\? compact\.view_count/,
  "DOM metric extraction must not fall back to unlabeled compact numeric fragments"
);
assert.match(extractorSource, /const roots = \[card \?\? link\]/, "DOM extraction must keep thumbnail extraction inside the local card or link-only fallback");
assert.match(extractorSource, /duration_source: durationSource/, "Merged output must emit explicit duration provenance");
assert.match(extractorSource, /view_count_source: viewCountSource/, "Merged output must emit explicit view-count provenance");
assert.match(extractorSource, /like_count_source: likeCountSource/, "Merged output must emit explicit like-count provenance");
assert.match(extractorSource, /comment_count_source: commentCountSource/, "Merged output must emit explicit comment-count provenance");
assert.match(extractorSource, /share_count_source: shareCountSource/, "Merged output must emit explicit share-count provenance");
assert.match(extractorSource, /engagement_rate_source: engagementRateSource/, "Merged output must emit explicit engagement-rate provenance");
assert.match(extractorSource, /has_speech: null/, "Merged output must keep unsupported has_speech explicitly null");
assert.match(extractorSource, /text_density: null/, "Merged output must keep unsupported text_density explicitly null");
assert.match(extractorSource, /has_heavy_watermark: null/, "Merged output must keep unsupported has_heavy_watermark explicitly null");
assert.match(extractorSource, /processing_complexity: null/, "Merged output must keep unsupported processing_complexity explicitly null");
assert.match(extractorSource, /copyright_risk: null/, "Merged output must keep unsupported copyright_risk explicitly null");
assert.match(popupTransportSource, /duration_source: durationSource/, "Direct execute-script path must emit duration provenance");
assert.match(popupTransportSource, /view_count_source: viewCount !== null \? "dom_text" : "fallback_none"/, "Direct execute-script path must emit view-count provenance");
assert.match(popupTransportSource, /engagement_rate_source: engagementRate !== null \? "derived_from_canonical_counts" : "fallback_none"/, "Direct execute-script path must emit engagement-rate provenance");
assert.match(typeSource, /duration_source\?: DurationSource \| null/, "VideoPayload must expose duration_source");
assert.match(typeSource, /view_count_source\?: MetricSource \| null/, "VideoPayload must expose view_count_source");
assert.match(typeSource, /engagement_rate_source\?: EngagementRateSource \| null/, "VideoPayload must expose engagement_rate_source");
assert.match(typeSource, /has_speech\?: boolean \| null/, "VideoPayload must expose nullable has_speech");

console.log("extension extractor tests passed");
