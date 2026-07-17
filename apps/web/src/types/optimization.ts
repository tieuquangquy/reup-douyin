import type { PublishDraftStatus } from "./publish-draft";

export type OutcomeScoreComponent = {
  key: string;
  label: string;
  raw_input: Record<string, unknown>;
  subscore: number;
  weight: number;
  weighted_contribution: number;
};

export type OutcomeScore = {
  target_id: string;
  target_type: string;
  publish_draft_id: string;
  source_video_id: string;
  score_version: string;
  total_outcome_score: number;
  outcome_label: "strong" | "usable" | "needs_work" | "weak";
  breakdown: OutcomeScoreComponent[];
  improvement_hints: string[];
  warnings: string[];
};

export type OutcomeGroupSummary = {
  group_key: string;
  label: string;
  item_count: number;
  average_outcome_score: number | null;
  strong_count: number;
  weak_count: number;
  published_count: number;
  needs_attention_count: number;
  hints: string[];
};

export type OutcomeSummaries = {
  generated_at: string;
  score_version: string;
  by_source_profile: OutcomeGroupSummary[];
  by_niche: OutcomeGroupSummary[];
  by_preset: OutcomeGroupSummary[];
  by_account: OutcomeGroupSummary[];
  by_score_bucket: OutcomeGroupSummary[];
};

export type RoutingHintAccount = {
  platform_account_id: string;
  display_name: string;
  confidence_score: number;
  confidence_label: "high" | "medium" | "low" | "blocked";
  health_status: string;
  reasons: string[];
  warnings: string[];
};

export type RoutingHints = {
  publish_draft_id: string;
  recommended_accounts: RoutingHintAccount[];
  blocked_accounts: RoutingHintAccount[];
  automation_policy: {
    can_auto_assign?: boolean;
    requires_manual_review?: boolean;
    blocking_reasons?: string[];
    warnings?: string[];
    policy: string;
  };
  explanation: string[];
};

export type SchedulingSlotHint = {
  platform_account_id: string | null;
  account_name: string | null;
  suggested_publish_at: string;
  confidence_label: "high" | "medium" | "low";
  reasons: string[];
  warnings: string[];
};

export type SchedulingHints = {
  publish_draft_id: string;
  suggested_slots: SchedulingSlotHint[];
  automation_policy: {
    can_auto_fill_schedule?: boolean;
    requires_manual_review?: boolean;
    blocking_reasons?: string[];
    policy: string;
  };
  explanation: string[];
};

export type ManualTouchHotspot = {
  area: string;
  count: number;
  severity: "low" | "medium" | "high";
  hint: string;
};

export type ManualTouchSummary = {
  generated_at: string;
  hotspots: ManualTouchHotspot[];
};

export type PresetFeedbackItem = {
  preset_name: string;
  item_count: number;
  average_outcome_score: number | null;
  strong_count: number;
  weak_count: number;
  tuning_hints: string[];
};

export type PresetFeedback = {
  generated_at: string;
  items: PresetFeedbackItem[];
};

export type OptimizationDashboard = {
  generated_at: string;
  outcome_summaries: OutcomeSummaries;
  preset_feedback: PresetFeedback;
  manual_touch_summary: ManualTouchSummary;
  ready_draft_routing_hints: RoutingHints[];
};

export type OptimizationStatus = PublishDraftStatus | "NO_DATA";

