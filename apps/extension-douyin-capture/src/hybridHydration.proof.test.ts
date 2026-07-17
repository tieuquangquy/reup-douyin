// Standalone Node test: chứng minh Hybrid hydration sinh finalized payload
// đủ cả 5 required fields (duration_seconds, like, comment, favorite, share)
// từ network cache thật của profile Douyin.
//
// Chạy: cd apps/extension-douyin-capture && npx tsx src/hybridHydration.proof.test.ts
// Không cần Chrome, không cần backend, không kẹt state.

import { strict as assert } from "node:assert";
import test from "node:test";
import {
  hydrateNonModalForAwemeId,
  buildFinalizedMetadataFromHybridHydration,
  buildHybridProfileCardEvidence,
  promoteDouyinThumbnailToCdnUrl,
  countQueueItemsWithHybridMetrics,
  HYBRID_REQUIRED_METRIC_FIELDS,
  type HybridHydrationSourceBundle
} from "./wholeProfileHarvest/hybridHydration.js";

// ----------------------------------------------------------------------------
// Fixture: 1 record copy y nguyên từ window.__REUP_DOUYIN_NETWORK_CACHE__ thật
// (profile có 127 video, đã xác minh 103/103 đủ field qua DevTools).
// Chỉ giữ field hydration đọc, để fixture nhỏ và rõ.
// ----------------------------------------------------------------------------
const REAL_NETWORK_CACHE_ITEM = {
  aweme_id: "7620255788623203630",
  desc: "《再见阿里》 ...",
  duration_seconds: 263,
  duration_text: null,
  like_count: 1662,
  comment_count: 104,
  share_count: 304,
  view_count: null,
  posted_at: "2025-03-19T...",
  thumbnail_url: "https://www.douyin.com/tos-cn-i-dy/d7909e9470d242c38270ae9a30c1bd8b",
  origin_cover: "https://www.douyin.com/tos-cn-i-dy/d7909e9470d242c38270ae9a30c1bd8b",
  url_list: ["https://www.douyin.com/tos-cn-i-dy/d7909e9470d242c38270ae9a30c1bd8b"],
  raw_source: "/aweme/v1/web/aweme/post/",
  raw_network_aweme: {
    aweme_id: "7620255788623203630",
    desc: "《再见阿里》 ...",
    create_time: 1774229066,
    video: { duration: 263000 },
    statistics: {
      aweme_id: "7620255788623203630",
      comment_count: 104,
      digg_count: 1662,
      share_count: 304,
      collect_count: 27,           // <-- favorite_count thật, qua collect_count
      play_count: 0,
      admire_count: 0,
      recommend_count: 0
    }
  }
} as const;

// ----------------------------------------------------------------------------
test("hybrid_hydration: required 5 fields đầy đủ từ network cache thật", () => {
  const bundle: HybridHydrationSourceBundle = {
    profile_repository: {},
    network_cache: REAL_NETWORK_CACHE_ITEM as never,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  };

  const result = hydrateNonModalForAwemeId(REAL_NETWORK_CACHE_ITEM.aweme_id, bundle);

  console.log("\n--- HYBRID HYDRATION RESULT ---");
  console.log("aweme_id:                      ", result.aweme_id);
  console.log("pending_reason:                ", result.pending_reason);
  console.log("missing_required_fields:       ", result.missing_required_fields);
  console.log("sources_attempted:             ", result.sources_attempted);
  console.log("sources_used:                  ", result.sources_used);
  console.log("fields:");
  console.log("  duration_seconds:            ", result.fields.duration_seconds);
  console.log("  like_count:                  ", result.fields.like_count);
  console.log("  comment_count:               ", result.fields.comment_count);
  console.log("  favorite_count (collect_count):", result.fields.favorite_count);
  console.log("  share_count:                 ", result.fields.share_count);
  console.log("metric_value_source:           ", result.metric_value_source);
  console.log("thumbnail.present:             ", result.thumbnail.present);
  console.log("thumbnail.source:              ", result.thumbnail.source);
  console.log("estimated_views:               ", result.estimated_views_diagnostics.estimated_views);
  console.log("estimated_views_formula:       ", result.estimated_views_diagnostics.estimated_views_formula);

  for (const field of HYBRID_REQUIRED_METRIC_FIELDS) {
    assert.notEqual(
      result.fields[field],
      null,
      `Required field "${field}" must not be null. Got result.fields = ${JSON.stringify(result.fields)}`
    );
  }
  assert.equal(result.pending_reason, null, `pending_reason must be null when all 5 fields present, got: ${result.pending_reason}`);
  assert.equal(result.missing_required_fields.length, 0, `missing_required_fields must be empty, got: ${JSON.stringify(result.missing_required_fields)}`);
  assert.ok(result.sources_used.includes("network_cache"), `sources_used must include "network_cache", got: ${JSON.stringify(result.sources_used)}`);
});

// ----------------------------------------------------------------------------
test("hybrid_hydration: build finalized payload không null + giữ invariant", () => {
  const bundle: HybridHydrationSourceBundle = {
    profile_repository: {},
    network_cache: REAL_NETWORK_CACHE_ITEM as never,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  };
  const hydration = hydrateNonModalForAwemeId(REAL_NETWORK_CACHE_ITEM.aweme_id, bundle);
  const payload = buildFinalizedMetadataFromHybridHydration(hydration, {
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAA"
  });

  console.log("\n--- FINALIZED PAYLOAD ---");
  console.log("payload null?                  ", payload === null);
  if (payload) {
    console.log("aweme_id:                      ", payload.aweme_id);
    console.log("source_url:                    ", payload.source_url);
    console.log("metadata_status:               ", payload.metadata_status);
    console.log("data_integrity_status:         ", payload.data_integrity_status);
    console.log("view_count:                    ", payload.view_count);
    console.log("estimated_views:               ", payload.estimated_views);
    console.log("estimated_views_formula:       ", payload.estimated_views_formula);
    console.log("estimated_views_used:          ", payload.estimated_views_used);
    console.log("real_view_count_overwritten:   ", payload.real_view_count_overwritten);
    console.log("raw_dom_detail_metrics:");
    console.log("  duration_seconds:            ", payload.raw_dom_detail_metrics.duration_seconds);
    console.log("  like_count:                  ", payload.raw_dom_detail_metrics.like_count);
    console.log("  comment_count:               ", payload.raw_dom_detail_metrics.comment_count);
    console.log("  favorite_count:              ", payload.raw_dom_detail_metrics.favorite_count);
    console.log("  share_count:                 ", payload.raw_dom_detail_metrics.share_count);
  }

  assert.notEqual(payload, null, "buildFinalizedMetadataFromHybridHydration must return non-null when hydration is finalized");
  if (!payload) return;

  // Invariants quan trọng
  assert.equal(payload.estimated_views_formula, "tiered_like_multiplier_v1", "estimated_views_formula must stay tiered_like_multiplier_v1");
  assert.equal(payload.real_view_count_overwritten, false, "real_view_count_overwritten must be false");
  assert.notEqual(payload.estimated_views, payload.view_count, "estimated_views must NOT be copied into view_count (unless both null)");

  // Duration phải > 0 — đây là field mà modal runner fail (lần chạy thật trước)
  assert.ok(
    typeof payload.raw_dom_detail_metrics.duration_seconds === "number" &&
    payload.raw_dom_detail_metrics.duration_seconds > 0,
    `duration_seconds must be > 0 (modal failed here), got: ${payload.raw_dom_detail_metrics.duration_seconds}`
  );

  // Tất cả 4 engagement metrics phải >= 0
  for (const k of ["like_count", "comment_count", "favorite_count", "share_count"] as const) {
    const v = payload.raw_dom_detail_metrics[k];
    assert.ok(typeof v === "number" && v >= 0, `${k} must be number >=0, got: ${v}`);
  }
});

// ----------------------------------------------------------------------------
test("hybrid_hydration: thiếu collect_count -> pending (chứng minh guard)", () => {
  const noCollectCount = {
    ...REAL_NETWORK_CACHE_ITEM,
    raw_network_aweme: {
      ...REAL_NETWORK_CACHE_ITEM.raw_network_aweme,
      statistics: {
        ...REAL_NETWORK_CACHE_ITEM.raw_network_aweme.statistics,
        collect_count: undefined as unknown as number
      }
    }
  };
  const bundle: HybridHydrationSourceBundle = {
    profile_repository: {},
    network_cache: noCollectCount as never,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  };
  const result = hydrateNonModalForAwemeId(noCollectCount.aweme_id, bundle);
  console.log("\n--- NEGATIVE CASE (no collect_count) ---");
  console.log("favorite_count:               ", result.fields.favorite_count);
  console.log("missing_required_fields:      ", result.missing_required_fields);
  console.log("pending_reason:               ", result.pending_reason);

  assert.equal(result.fields.favorite_count, null, "favorite_count must fall to null when collect_count absent");
  assert.ok(
    result.missing_required_fields.includes("favorite_count"),
    `missing_required_fields must list favorite_count, got: ${JSON.stringify(result.missing_required_fields)}`
  );
  assert.notEqual(result.pending_reason, null, "pending_reason must be set when a required field is missing");

  const payload = buildFinalizedMetadataFromHybridHydration(result, { profile_url: null });
  assert.equal(payload, null, "finalized payload must be null when pending");
});

// ----------------------------------------------------------------------------
// Production: last N queue items often exist only in passive profile_post probe
// (network cache rotated). Passive previously hard-coded favorite_count=null so
// those items stayed skipped_pending forever no matter how many Start Collecting clicks.
test("hybrid_hydration: passive-only target with collect_count finalizes", () => {
  const passiveOnly = {
    aweme_id: "7649243220485242547",
    source_url: "https://www.douyin.com/video/7649243220485242547",
    desc: "tail video",
    cover_url: "https://p3-sign.douyinpic.com/obj/tail-cover.jpg",
    duration: 15,
    create_time: 1774229066,
    like_count: 10,
    comment_count: 2,
    favorite_count: 1,
    share_count: 0,
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAA",
    endpoint_path: "/aweme/v1/web/aweme/post/",
    endpoint_kind: "profile_post" as const,
    captured_at: "2026-07-04T00:00:00.000Z",
    trace_version: "22C-12A-R3" as const
  };
  const bundle: HybridHydrationSourceBundle = {
    profile_repository: {},
    network_cache: null,
    passive_aweme: passiveOnly,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  };
  const result = hydrateNonModalForAwemeId(passiveOnly.aweme_id, bundle);
  assert.equal(result.pending_reason, null, `passive-only must finalize, got pending_reason=${result.pending_reason}`);
  assert.equal(result.fields.favorite_count, 1);
  assert.ok(result.sources_used.includes("passive_aweme"));
  const payload = buildFinalizedMetadataFromHybridHydration(result, {
    profile_url: passiveOnly.profile_url
  });
  assert.notEqual(payload, null, "passive-only finalized payload must not be null");
});

test("hybrid_hydration: image post without video.duration uses slide fallback", () => {
  // Production log: all 4 remaining items missing_required_fields:duration_seconds
  // while network_cache was present — typical Douyin image/slide posts.
  const imagePostCache = {
    aweme_id: "7649243220485242547",
    like_count: 10,
    comment_count: 2,
    favorite_count: 1,
    share_count: 0,
    thumbnail_url: "https://p3-sign.douyinpic.com/obj/image-cover.jpg",
    posted_at: "2026-03-19T00:00:00.000Z",
    duration_seconds: null,
    duration_text: null,
    raw_network_aweme: {
      aweme_id: "7649243220485242547",
      aweme_type: 68,
      create_time: 1774229066,
      images: [{}, {}, {}],
      statistics: {
        digg_count: 10,
        comment_count: 2,
        collect_count: 1,
        share_count: 0
      }
    }
  };
  const result = hydrateNonModalForAwemeId(imagePostCache.aweme_id, {
    profile_repository: {},
    network_cache: imagePostCache as never,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(result.pending_reason, null, `image post must finalize, got ${result.pending_reason}`);
  assert.equal(result.fields.duration_seconds, 9, "3 slides × 3s default");
  assert.notEqual(
    buildFinalizedMetadataFromHybridHydration(result, { profile_url: "https://www.douyin.com/user/x" }),
    null
  );
});

test("hybrid_hydration: protocol-relative cover URL is accepted", () => {
  // Douyin often emits //p3-sign.douyinpic.com/... — previously rejected as
  // missing_valid_thumbnail even when a cover existed.
  const protocolRelative = {
    aweme_id: "7626663620256091430",
    like_count: 1,
    comment_count: 0,
    favorite_count: 0,
    share_count: 0,
    duration_seconds: 12,
    thumbnail_url: "//p3-sign.douyinpic.com/obj/cover-protocol-relative.jpg",
    posted_at: "2026-03-19T00:00:00.000Z",
    raw_network_aweme: {
      aweme_id: "7626663620256091430",
      create_time: 1774229066,
      statistics: { digg_count: 1, comment_count: 0, collect_count: 0, share_count: 0 }
    }
  };
  const result = hydrateNonModalForAwemeId(protocolRelative.aweme_id, {
    profile_repository: {},
    network_cache: protocolRelative as never,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(result.pending_reason, null, `got ${result.pending_reason}`);
  assert.equal(result.thumbnail.valid_url, "yes");
  assert.match(result.thumbnail.url ?? "", /^https:\/\/p3-sign\.douyinpic\.com\//);
});

test("hybrid_hydration: skips bare tos uri and uses later https cover", () => {
  const mixedCovers = {
    aweme_id: "7380349221578378534",
    like_count: 1,
    comment_count: 0,
    favorite_count: 0,
    share_count: 0,
    duration_seconds: 8,
    thumbnail_url: "tos-cn-i-dy/bare-uri-without-host",
    cover_url: "https://p3-sign.douyinpic.com/obj/good-cover.jpg",
    posted_at: "2026-03-19T00:00:00.000Z",
    raw_network_aweme: {
      aweme_id: "7380349221578378534",
      create_time: 1774229066,
      statistics: { digg_count: 1, comment_count: 0, collect_count: 0, share_count: 0 }
    }
  };
  const result = hydrateNonModalForAwemeId(mixedCovers.aweme_id, {
    profile_repository: {},
    network_cache: mixedCovers as never,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(result.pending_reason, null);
  assert.equal(result.thumbnail.field_used, "cover_url");
  assert.equal(result.thumbnail.url, "https://p3-sign.douyinpic.com/obj/good-cover.jpg");
});

test("hybrid_hydration: duration_text is parsed when numeric duration is absent", () => {
  const textOnly = {
    aweme_id: "7654550998895709338",
    like_count: 1,
    comment_count: 0,
    favorite_count: 0,
    share_count: 0,
    duration_seconds: null,
    duration_text: "0:15",
    thumbnail_url: "https://p3-sign.douyinpic.com/obj/cover.jpg",
    posted_at: "2026-03-19T00:00:00.000Z",
    raw_network_aweme: {
      aweme_id: "7654550998895709338",
      create_time: 1774229066,
      statistics: { digg_count: 1, comment_count: 0, collect_count: 0, share_count: 0 }
    }
  };
  const result = hydrateNonModalForAwemeId(textOnly.aweme_id, {
    profile_repository: {},
    network_cache: textOnly as never,
    passive_aweme: null,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.equal(result.fields.duration_seconds, 15);
  assert.equal(result.pending_reason, null);
});

test("hybrid_hydration: passive-only without favorite_count stays pending", () => {
  const passiveMissingFavorite = {
    aweme_id: "7654550998895709338",
    source_url: "https://www.douyin.com/video/7654550998895709338",
    desc: "tail video",
    cover_url: "https://p3-sign.douyinpic.com/obj/tail-cover.jpg",
    duration: 15,
    create_time: 1774229066,
    like_count: 10,
    comment_count: 2,
    favorite_count: null,
    share_count: 0,
    profile_url: "https://www.douyin.com/user/MS4wLjABAAAA",
    endpoint_path: "/aweme/v1/web/aweme/post/",
    endpoint_kind: "profile_post" as const,
    captured_at: "2026-07-04T00:00:00.000Z",
    trace_version: "22C-12A-R3" as const
  };
  const result = hydrateNonModalForAwemeId(passiveMissingFavorite.aweme_id, {
    profile_repository: {},
    network_cache: null,
    passive_aweme: passiveMissingFavorite,
    profile_post_api: null,
    calibrated_non_modal_dom: null
  });
  assert.ok(result.missing_required_fields.includes("favorite_count"));
  assert.match(result.pending_reason ?? "", /missing_required_fields:.*favorite_count/);
});

test("promoteDouyinThumbnailToCdnUrl: preserves bare www.douyin.com/tos paths (no unsigned CDN synthesis)", () => {
  const raw = "https://www.douyin.com/tos-cn-p-0015/15ec77b7a8aa4c0b9d0bc116ce1dc908_1613485990";
  const promoted = promoteDouyinThumbnailToCdnUrl(raw);
  assert.equal(promoted, raw);
});

test("promoteDouyinThumbnailToCdnUrl: preserves signed douyinpic URLs with query params", () => {
  const signed = "https://p3-sign.douyinpic.com/tos-cn-i-dy/abc~tplv-dy-360p.jpeg?x-expires=1770000000&x-signature=abc";
  assert.equal(promoteDouyinThumbnailToCdnUrl(signed), signed);
});

test("buildHybridProfileCardEvidence: preserves scan metrics on queue evidence", () => {
  const evidence = buildHybridProfileCardEvidence(null, [{
    aweme_id: "6929869163355802887",
    like_count: 1000,
    comment_count: 50,
    favorite_count: 80,
    share_count: 12,
    duration_seconds: 120,
    thumbnail_url: "https://www.douyin.com/tos-cn-p-0015/abc_test"
  }]);
  assert.equal(evidence.like_count, 1000);
  assert.equal(evidence.duration_seconds, 120);
  assert.match(String(evidence.thumbnail_url), /www\.douyin\.com\/tos-cn-p-0015\//);
});

test("countQueueItemsWithHybridMetrics: counts actionable items with full metrics", () => {
  const ready = countQueueItemsWithHybridMetrics([
    { status: "pending", profile_card_evidence: { duration_seconds: 10, like_count: 1, comment_count: 0, favorite_count: 0, share_count: 0 } },
    { status: "pending", profile_card_evidence: { duration_seconds: 0, like_count: 1, comment_count: 0, favorite_count: 0, share_count: 0 } },
    { status: "already_collected", profile_card_evidence: { duration_seconds: 10, like_count: 1, comment_count: 0, favorite_count: 0, share_count: 0 } }
  ]);
  assert.equal(ready, 1);
});
