import assert from "node:assert/strict";
import { automationReadinessLabel, groupTone, optimizationHeadline } from "../lib/optimizationState";
import type { OptimizationDashboard, RoutingHints } from "../types/optimization";

const dashboard: OptimizationDashboard = {
  generated_at: "2026-04-21T00:00:00Z",
  outcome_summaries: {
    generated_at: "2026-04-21T00:00:00Z",
    score_version: "OUTCOME_SCORE_V1",
    by_source_profile: [],
    by_niche: [],
    by_account: [],
    by_score_bucket: [],
    by_preset: [
      {
        group_key: "safe_reup",
        label: "safe_reup",
        item_count: 4,
        average_outcome_score: 82,
        strong_count: 3,
        weak_count: 0,
        published_count: 3,
        needs_attention_count: 0,
        hints: ["Strong recent outcomes"]
      }
    ]
  },
  preset_feedback: {
    generated_at: "2026-04-21T00:00:00Z",
    items: []
  },
  manual_touch_summary: {
    generated_at: "2026-04-21T00:00:00Z",
    hotspots: []
  },
  ready_draft_routing_hints: []
};

assert.equal(optimizationHeadline(dashboard), "safe_reup is leading with 82 average outcome");
assert.equal(groupTone(dashboard.outcome_summaries.by_preset[0]), "good");
assert.equal(groupTone({ ...dashboard.outcome_summaries.by_preset[0], average_outcome_score: 55 }), "danger");

const hint: RoutingHints = {
  publish_draft_id: "draft-1",
  recommended_accounts: [
    {
      platform_account_id: "account-1",
      display_name: "Page A",
      confidence_score: 88,
      confidence_label: "high",
      health_status: "HEALTHY",
      reasons: [],
      warnings: []
    }
  ],
  blocked_accounts: [],
  automation_policy: {
    can_auto_assign: true,
    requires_manual_review: false,
    blocking_reasons: [],
    warnings: [],
    policy: "phase1_guarded_semi_automation"
  },
  explanation: []
};

assert.equal(automationReadinessLabel(hint), "Safe to auto-assign");
assert.equal(automationReadinessLabel({ ...hint, automation_policy: { ...hint.automation_policy, can_auto_assign: false } }), "High confidence, review guardrails");

console.log("optimization state tests passed");
