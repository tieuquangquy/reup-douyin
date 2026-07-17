import assert from "node:assert/strict";
import { findExactAwemeCandidates, mapCdpAwemeMetrics, parseCdpResponseBodyJson, sanitizeAwemeEvidence } from "./cdpAweme.js";

const aweme = {
  aweme_id: "7420001",
  desc: "caption",
  create_time: 1_700_000_000,
  video: { duration: 12345 },
  statistics: {
    digg_count: "1,234",
    comment_count: 56,
    collect_count: 78,
    share_count: 9,
    play_count: 10_000
  },
  cookie: "secret-cookie",
  author: { nickname: "creator", authorization: "secret-auth" }
};

{
  const parsed = parseCdpResponseBodyJson(JSON.stringify({ data: { aweme_detail: aweme } }));
  const result = findExactAwemeCandidates(parsed, "7420001", "cdp_network_aweme", "https://www.douyin.com/aweme/detail");
  assert.equal(result.stats.candidate_count, 1);
  assert.equal(result.stats.exact_match_count, 1);
  assert.equal(result.candidates.length, 1);
  assert.equal(result.candidates[0]?.aweme_id, "7420001");
  assert.equal(result.candidates[0]?.source_used, "cdp_network_aweme");
  assert.equal(result.candidates[0]?.response_url, "https://www.douyin.com/aweme/detail");
}

{
  const encoded = Buffer.from(JSON.stringify({ item: aweme }), "utf8").toString("base64");
  const parsed = parseCdpResponseBodyJson(encoded, true);
  const result = findExactAwemeCandidates(parsed, "7420001", "cdp_runtime_aweme");
  assert.equal(result.candidates.length, 1);
}

{
  const result = findExactAwemeCandidates({ aweme_list: [aweme] }, "mismatched", "cdp_network_aweme");
  assert.equal(result.stats.candidate_count, 1);
  assert.equal(result.stats.exact_match_count, 0);
  assert.equal(result.candidates.length, 0);
}

{
  const mapped = mapCdpAwemeMetrics(aweme);
  assert.equal(mapped.duration_seconds, 12.345);
  assert.equal(mapped.duration_text, "0:12");
  assert.equal(mapped.duration_raw, 12345);
  assert.equal(mapped.duration_validation_result, "accepted_exact_aweme");
  assert.deepEqual(mapped.duration_candidate_list, [
    {
      source: "aweme.video.duration",
      raw_value: 12345,
      normalized_seconds: 12.345,
      accepted: true,
      reason: "selected_exact_aweme"
    },
    {
      source: "aweme.video.duration_millis",
      raw_value: null,
      normalized_seconds: null,
      accepted: false,
      reason: "missing"
    },
    {
      source: "aweme.video.duration_ms",
      raw_value: null,
      normalized_seconds: null,
      accepted: false,
      reason: "missing"
    },
    {
      source: "aweme.duration",
      raw_value: null,
      normalized_seconds: null,
      accepted: false,
      reason: "missing"
    },
    {
      source: "aweme.duration_millis",
      raw_value: null,
      normalized_seconds: null,
      accepted: false,
      reason: "missing"
    }
  ]);
  assert.equal(mapped.like_count, 1234);
  assert.equal(mapped.comment_count, 56);
  assert.equal(mapped.favorite_count, 78);
  assert.equal(mapped.share_count, 9);
  assert.equal(mapped.view_count, 10000);
  assert.equal(mapped.posted_text, null);
  assert.equal(mapped.posted_at, "2023-11-14T22:13:20.000Z");
}

{
  const sanitized = sanitizeAwemeEvidence(aweme);
  assert.equal("cookie" in sanitized, false);
  assert.equal((sanitized.author as Record<string, unknown>).authorization, undefined);
  assert.equal((sanitized.author as Record<string, unknown>).nickname, "creator");
}

{
  const circular: Record<string, unknown> = { aweme_id: "7420001", video: { duration: 1000 }, statistics: { digg_count: 1 } };
  circular.self = circular;
  const result = findExactAwemeCandidates(circular, "7420001", "cdp_runtime_aweme", null, { maxDepth: 4, maxObjects: 20, timeoutMs: 100 });
  assert.equal(result.candidates.length, 1);
}

console.log("cdp aweme tests passed");
