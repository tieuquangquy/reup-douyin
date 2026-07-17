import assert from "node:assert/strict";
import {
  DEFAULT_INTAKE_FORM,
  buildIntakeDiscoverRequest,
  formatPresetName,
  isValidDouyinProfileUrl,
  parseRecentIntakeSetup,
  validateIntakeForm
} from "../lib/intakeState";

assert.equal(isValidDouyinProfileUrl("https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid"), true);
assert.equal(isValidDouyinProfileUrl("https://example.com/user/MS4wLjABAAAAfixture-sec-uid"), false);
assert.equal(isValidDouyinProfileUrl("not-a-url"), false);

assert.deepEqual(validateIntakeForm({
  ...DEFAULT_INTAKE_FORM,
  profileUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
  minViews: "10",
  maxViews: "20",
  minLikes: "1",
  maxLikes: "2"
}), {});

const badRange = validateIntakeForm({
  ...DEFAULT_INTAKE_FORM,
  profileUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
  minViews: "100",
  maxViews: "10",
  minComments: "50",
  maxComments: "5",
  minEngagementRate: "12",
  maxEngagementRate: "5",
  dateFrom: "2026-04-22",
  dateTo: "2026-04-21"
});
assert.equal(badRange.maxViews, "Max views must be greater than or equal to min views.");
assert.equal(badRange.maxComments, "Max comments must be greater than or equal to min comments.");
assert.equal(badRange.maxEngagementRate, "Max engagement rate must be greater than or equal to min engagement rate.");
assert.equal(badRange.dateTo, "To date must be after from date.");

const payload = buildIntakeDiscoverRequest({
  ...DEFAULT_INTAKE_FORM,
  profileUrl: " https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid ",
  dateFrom: "2026-04-01",
  dateTo: "2026-04-22",
  minViews: "10000",
  maxViews: "",
  minLikes: "500",
  maxLikes: "",
  minComments: "25",
  maxComments: "",
  minShares: "10",
  maxShares: "",
  minDurationSeconds: "8",
  maxDurationSeconds: "90",
  minEngagementRate: "3.5",
  maxEngagementRate: "",
  hasSpeech: "yes",
  maxTextDensity: "medium",
  excludeHeavyWatermark: true,
  excludeHighProcessingComplexity: true,
  excludeHighCopyrightRisk: true,
  forceLiveRefresh: true,
  douyinAccountConnectionId: "account-1"
});

assert.equal(payload.profile_url, "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid");
assert.equal(payload.preset_name, "viral_discovery");
assert.equal(payload.filter_config.date_mode, "absolute_range");
assert.equal(payload.filter_config.start_date, "2026-04-01T00:00:00.000Z");
assert.equal(payload.filter_config.end_date, "2026-04-22T23:59:59.999Z");
assert.equal(payload.filter_config.min_views, 10000);
assert.equal(payload.filter_config.min_likes, 500);
assert.equal(payload.filter_config.min_comments, 25);
assert.equal(payload.filter_config.min_shares, 10);
assert.equal(payload.filter_config.min_duration_seconds, 8);
assert.equal(payload.filter_config.max_duration_seconds, 90);
assert.equal(payload.filter_config.min_engagement_rate, 0.035);
assert.equal(payload.filter_config.has_speech, true);
assert.equal(payload.filter_config.max_text_density, "medium");
assert.equal(payload.filter_config.exclude_heavy_watermark, true);
assert.equal(payload.filter_config.exclude_high_processing_complexity, true);
assert.equal(payload.filter_config.exclude_high_copyright_risk, true);
assert.equal(payload.filter_config.limit, 50);
assert.equal(payload.force_live_refresh, true);
assert.equal(payload.douyin_account_connection_id, "account-1");

assert.equal(formatPresetName("viral_discovery"), "Viral Discovery");
assert.equal(formatPresetName("safe_reup"), "Safe Reup");
assert.equal(formatPresetName(""), "No preset");

assert.deepEqual(parseRecentIntakeSetup(JSON.stringify({
  profileUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
  presetName: "safe_reup",
  discoveredAt: "2026-04-22T00:00:00.000Z"
})), {
  profileUrl: "https://www.douyin.com/user/MS4wLjABAAAAfixture-sec-uid",
  presetName: "safe_reup",
  discoveredAt: "2026-04-22T00:00:00.000Z"
});
assert.equal(parseRecentIntakeSetup("not-json"), null);

console.log("intake state tests passed");
