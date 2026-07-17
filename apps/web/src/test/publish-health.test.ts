import { buildFeedbackPayload, healthStatusLabel, needsAttentionCount } from "../lib/publishHealthState";
import type { PublishHealthDashboard } from "../types/analytics";

const snapshot: PublishHealthDashboard = {
  generated_at: "2026-04-21T00:00:00Z",
  window: "last_7_days",
  window_start: "2026-04-14T00:00:00Z",
  window_end: "2026-04-21T00:00:00Z",
  overview: {
    total_attempts: 3,
    succeeded_attempts: 1,
    failed_attempts: 1,
    needs_reconciliation_attempts: 1,
    canonical_published_count: 1,
    drafts_ready_not_published: 2,
    drafts_blocked_by_risk: 1,
    success_rate_percent: 33.33
  },
  by_day: [],
  account_health: [],
  failure_categories: [],
  action_queue: {
    needs_reconciliation: [],
    drafts_ready: [],
    blocked_by_risk_count: 1,
    recent_successes: []
  },
  pipeline_feedback: {
    by_source_profile: [],
    by_niche: [],
    by_preset: []
  }
};

if (healthStatusLabel(snapshot) !== "Needs reconciliation") {
  throw new Error("Expected reconciliation status label");
}

if (needsAttentionCount(snapshot) !== 1) {
  throw new Error("Expected blocked-by-risk attention count");
}

const payload = buildFeedbackPayload(
  {
    publish_draft_id: "draft-1",
    source_video_id: "video-1",
    render_output_id: null,
    platform: "FACEBOOK_REELS",
    status: "PUBLISHED",
    external_status: "PUBLISHED",
    external_publish_id: "post-1",
    external_permalink: "https://facebook.com/reel/post-1",
    canonical_publish_attempt_id: "attempt-1",
    platform_account_id: "account-1",
    source_profile_name: "Demo",
    preset_name: "safe_reup",
    niche_label: "food",
    score: 88,
    published_at: "2026-04-21T00:00:00Z",
    last_publish_synced_at: "2026-04-21T00:00:00Z",
    feedback_quality_label: null,
    feedback_confidence: null
  },
  {
    qualityLabel: "GOOD",
    confidence: "SCALABLE",
    rootCause: "",
    note: "  Useful pattern  "
  }
);

if (payload.target_type !== "PUBLISH_DRAFT" || payload.note !== "Useful pattern") {
  throw new Error("Expected feedback payload to target publish draft and trim note");
}

console.log("publish-health state tests passed");
