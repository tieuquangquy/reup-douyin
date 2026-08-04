import type { PlatformPublication } from "./publish-draft";

export type PlatformPublicationListResponse = {
  publications: PlatformPublication[];
  total_count: number;
  limit: number;
  offset: number;
};

export type FacebookReelDiscoveryItem = {
  reel_id: string;
  description: string | null;
  created_time: string | null;
  permalink_url: string | null;
  thumbnail_url: string | null;
  already_imported: boolean;
  platform_publication_id: string | null;
};

export type FacebookReelDiscoveryResponse = {
  platform_account_id: string;
  items: FacebookReelDiscoveryItem[];
  next_cursor: string | null;
  network_used: boolean;
};

export type PublicationMetricSnapshot = {
  id: string;
  observed_at: string;
  collection_source: string;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  share_count: number | null;
  save_count: number | null;
  impression_count: number | null;
  reach_count: number | null;
  total_watch_time_seconds: number | null;
  average_watch_time_seconds: number | null;
  completion_rate_percent: number | null;
  views_per_hour: number | null;
  engagement_rate_percent: number | null;
  data_quality: string;
  unavailable_metrics_json: string[] | null;
};

export type PublicationMetricSnapshotListResponse = {
  snapshots: PublicationMetricSnapshot[];
  total: number;
};

export type PublicationMetricSchedule = {
  id: string;
  workspace_id: string;
  platform_publication_id: string;
  collector_name: string;
  status: "ACTIVE" | "PAUSED" | "COMPLETED" | "BLOCKED";
  policy_version: string;
  next_collection_at: string | null;
  last_enqueued_at: string | null;
  last_completed_at: string | null;
  last_collection_job_id: string | null;
  last_metric_snapshot_id: string | null;
  collection_count: number;
  consecutive_flat_count: number;
  max_age_hours: number;
  tracking_started_at: string | null;
  tracking_ends_at: string | null;
  last_decision_json: Record<string, unknown> | null;
};

export type PublicationMetricTrackingHealth =
  | "HEALTHY"
  | "WAITING"
  | "DELAYED"
  | "COOLDOWN"
  | "BLOCKED"
  | "PAUSED"
  | "COMPLETED";

export type PublicationMetricTrackingJobSummary = {
  id: string;
  status: string;
  progress_percent: number;
  attempts: number;
  max_attempts: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type PublicationMetricTrackingMonitorItem = {
  schedule: PublicationMetricSchedule;
  platform_account_id: string;
  page_display_name: string;
  external_reel_id: string | null;
  external_permalink: string | null;
  caption: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  health_status: PublicationMetricTrackingHealth;
  health_reason: string;
  growth: PublicationGrowthSummary;
  last_job: PublicationMetricTrackingJobSummary | null;
};

export type PublicationMetricTrackingMonitorResponse = {
  items: PublicationMetricTrackingMonitorItem[];
  total: number;
  limit: number;
  offset: number;
  kpis: {
    active_count: number;
    due_soon_count: number;
    needs_attention_count: number;
    paused_count: number;
    completed_count: number;
    snapshots_today_count: number;
  };
};

export type PublicationGrowthSummary = {
  platform_publication_id: string;
  snapshot_count: number;
  first_observed_at: string | null;
  latest_observed_at: string | null;
  observation_hours: number | null;
  measurement_age_seconds: number | null;
  trend_label: "NO_DATA" | "BASELINE_ONLY" | "INSUFFICIENT_DATA" | "GROWING" | "FLAT" | "COUNTER_REGRESSION";
  velocity_status: "NO_DATA" | "BASELINE_ONLY" | "INSUFFICIENT_INTERVAL" | "STABLE" | "COUNTER_REGRESSION";
  minimum_velocity_interval_seconds: number;
  velocity_observation_seconds: number | null;
  next_stable_measurement_at: string | null;
  latest_view_count: number | null;
  latest_like_count: number | null;
  latest_comment_count: number | null;
  latest_share_count: number | null;
  latest_save_count: number | null;
  absolute_view_growth: number | null;
  views_per_hour_since_first: number | null;
  recent_views_per_hour: number | null;
  latest_engagement_rate_percent: number | null;
  latest_data_quality: string | null;
  counter_regression_detected: boolean;
};
