export type OpsBacklogSummary = {
  queued: number;
  retryable: number;
  running: number;
};

export type OpsFailureCategory = {
  error_code: string;
  count: number;
};

export type OpsAssetReuseSummary = {
  asset_type: string;
  current_count: number;
  historical_count: number;
};

export type OpsFetchHealthReasonCount = {
  reason: string;
  count: number;
};

export type OpsFetchHealthAccountSummary = {
  douyin_account_connection_id: string | null;
  runs_total: number;
  blocked_runs: number;
  parse_warning_runs: number;
  failed_runs: number;
};

export type OpsFetchHealthSummary = {
  window_runs: number;
  blocked_runs: number;
  parse_warning_runs: number;
  failed_runs: number;
  blocked_ratio_percent: number;
  top_blocked_reasons: OpsFetchHealthReasonCount[];
  by_account: OpsFetchHealthAccountSummary[];
};

export type OperationalMetrics = {
  generated_at: string;
  job_counts_by_type_status: Record<string, Record<string, number>>;
  job_failure_rate_percent_by_type: Record<string, number>;
  queue_backlog: OpsBacklogSummary;
  retryable_jobs: number;
  total_retry_attempts: number;
  step_duration_by_job_type: Record<string, Record<string, number>>;
  average_processing_seconds_per_source_video: number;
  common_failure_categories: OpsFailureCategory[];
  asset_reuse_by_type: OpsAssetReuseSummary[];
  render_counts_by_status: Record<string, number>;
  publish_draft_counts_by_status: Record<string, number>;
  open_risk_counts_by_severity: Record<string, number>;
  douyin_fetch_health: OpsFetchHealthSummary;
};

export type PipelineDashboardStatus = "healthy" | "needs_attention" | "blocked" | "quiet" | "in_progress";

export type PipelineDashboardSeverity = "info" | "warning" | "critical";

export type PipelineStageKey = "capture" | "review" | "reup_queue" | "export_package" | "publish_handoff" | "publish_progress";

export type PipelineDashboardMetric = {
  key: string;
  label: string;
  value: number;
  detail: string | null;
};

export type PipelineDashboardStage = {
  key: PipelineStageKey;
  label: string;
  description: string;
  status: PipelineDashboardStatus;
  primary_count: number;
  primary_label: string;
  secondary_count: number;
  secondary_label: string;
  metrics: PipelineDashboardMetric[];
  attention_count: number;
  href: string;
  next_action: string;
};

export type PipelineDashboardAttentionItem = {
  id: string;
  severity: PipelineDashboardSeverity;
  stage_key: PipelineStageKey;
  title: string;
  detail: string;
  count: number;
  href: string;
  recommended_action: string;
};

export type PipelineDashboardActivityItem = {
  id: string;
  stage_key: PipelineStageKey;
  title: string;
  detail: string;
  occurred_at: string;
  href: string;
};

export type PipelineDashboardQuickLink = {
  label: string;
  href: string;
  description: string;
  stage_key: PipelineStageKey | null;
};

export type PipelineDashboardResponse = {
  generated_at: string;
  overall_status: PipelineDashboardStatus;
  headline: string;
  summary_metrics: PipelineDashboardMetric[];
  stages: PipelineDashboardStage[];
  attention_items: PipelineDashboardAttentionItem[];
  recent_activity: PipelineDashboardActivityItem[];
  quick_links: PipelineDashboardQuickLink[];
};
