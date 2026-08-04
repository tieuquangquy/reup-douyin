export type OpsBacklogSummary = {
  queued: number;
  retryable: number;
  running: number;
  oldest_queued_at?: string | null;
  running_with_lock?: number;
  running_without_lock?: number;
  active_worker_count?: number;
  stale_running?: number;
  stale_running_job_ids?: string[];
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
  oldest_job_at_by_status: Record<string, string>;
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

export type OpsHomeTone = "good" | "warn" | "danger" | "muted" | "active";
export type OpsHomeStatus = "healthy" | "needs_attention" | "blocked" | "quiet";
export type OpsHomeSeverity = "critical" | "warning" | "info";

export type OpsHomeOverall = {
  status: OpsHomeStatus;
  headline: string;
  detail: string;
  critical_count: number;
  warning_count: number;
};

export type OpsHomeKpi = {
  key: string;
  label: string;
  value: number | null;
  display_value: string;
  detail: string;
  tone: OpsHomeTone;
  href: string;
};

export type OpsHomeActionItem = {
  id: string;
  severity: OpsHomeSeverity;
  area: string;
  title: string;
  detail: string;
  count: number;
  href: string;
  recommended_action: string;
  oldest_at: string | null;
};

export type OpsHomeJobHealthRow = {
  job_type: string;
  queued: number;
  running: number;
  retryable: number;
  failed: number;
  waiting_review: number;
  completed: number;
  total: number;
  failure_rate_percent: number;
  average_step_seconds: number;
  max_step_seconds: number;
  tone: OpsHomeTone;
  href: string;
};

export type OpsHomeAccountHealthRow = {
  platform_account_id: string;
  display_name: string;
  platform: string;
  account_status: string;
  health_status: string;
  priority: number;
  is_on_hold: boolean;
  cooldown_until: string | null;
  attempts_7d: number;
  succeeded_7d: number;
  failed_7d: number;
  success_rate_percent: number;
  needs_reconciliation_count: number;
  assigned_draft_count: number;
  scheduled_draft_count: number;
  recent_error_code: string | null;
  reasons: string[];
};

export type OpsHomeTrendDay = {
  day: string;
  attempts: number;
  succeeded: number;
  failed: number;
  needs_reconciliation: number;
};

export type OpsHomeFailureSignature = {
  source: string;
  error_code: string;
  label: string;
  count: number;
  href: string;
};

export type OpsHomeFetchHealth = {
  window_runs: number;
  blocked_runs: number;
  parse_warning_runs: number;
  failed_runs: number;
  blocked_ratio_percent: number;
  top_blocked_reasons: Array<{ reason: string; count: number }>;
  by_account: Array<{
    account_id: string | null;
    runs_total: number;
    blocked_runs: number;
    parse_warning_runs: number;
    failed_runs: number;
    blocked_rate_percent: number;
  }>;
};

export type OpsHomeOperationalStatus = {
  key: string;
  label: string;
  status: "ready" | "active" | "warning" | "critical" | "quiet";
  detail: string;
  href: string;
};

export type OpsHomeQueueHealth = {
  queued: number;
  running: number;
  retryable: number;
  waiting_review: number;
  failed: number;
  oldest_queued_at: string | null;
  running_with_lock: number;
  running_without_lock: number;
  busy_worker_count: number;
  total_retry_attempts: number;
};

export type OpsHomeDependencySignal = {
  key: string;
  label: string;
  state: "ready" | "warning" | "critical" | "not_observed";
  signal: string;
  impact: string;
  observed_at: string | null;
  href: string | null;
};

export type OpsHomeStorageCapacity = {
  state: "ready" | "warning" | "critical" | "not_observed";
  total_gb: number | null;
  free_gb: number | null;
  used_percent: number | null;
  minimum_free_gb: number | null;
  detail: string;
};

export type OpsHomeHiddenRisk = {
  key: string;
  label: string;
  state: "clear" | "watch" | "critical" | "not_observed";
  value: number | null;
  display_value: string;
  detail: string;
  href: string;
  segments: Array<{ key: string; label: string; value: number }>;
};

export type OpsHomeAdmissionVerdict = {
  status: "safe" | "caution" | "pause";
  label: string;
  detail: string;
  reasons: string[];
};

export type OpsHomeSummaryResponse = {
  overall: OpsHomeOverall;
  freshness: {
    generated_at: string;
    metrics_generated_at: string;
    publish_health_generated_at: string;
    control_queue_generated_at: string;
  };
  kpis: OpsHomeKpi[];
  action_items: OpsHomeActionItem[];
  job_health: OpsHomeJobHealthRow[];
  account_health: OpsHomeAccountHealthRow[];
  publish_trend: OpsHomeTrendDay[];
  failure_signatures: OpsHomeFailureSignature[];
  fetch_health: OpsHomeFetchHealth;
  operational_status: OpsHomeOperationalStatus[];
  queue_health: OpsHomeQueueHealth;
  dependencies: OpsHomeDependencySignal[];
  storage_capacity: OpsHomeStorageCapacity;
  hidden_risks: OpsHomeHiddenRisk[];
  admission_verdict: OpsHomeAdmissionVerdict;
};

export type PipelineDashboardStatus = "healthy" | "needs_attention" | "blocked" | "quiet" | "in_progress";

export type PipelineDashboardSeverity = "info" | "warning" | "critical";

export type PipelineStageKey =
  | "capture"
  | "review"
  | "reup_queue"
  | "download"
  | "audio_analysis"
  | "translate"
  | "tts"
  | "ocr"
  | "render"
  | "output_review"
  | "draft"
  | "export_package"
  | "publish_handoff";

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
  waiting_count: number;
  running_count: number;
  review_count: number;
  failed_count: number;
  ready_count: number;
  total_count: number;
  href: string;
  next_action: string;
};

export type PipelineDashboardOutputQaSummary = {
  passed: number;
  warned: number;
  failed: number;
  ungraded: number;
  total: number;
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
  output_qa_summary: PipelineDashboardOutputQaSummary;
  recent_activity: PipelineDashboardActivityItem[];
  quick_links: PipelineDashboardQuickLink[];
};

export type OperatorHomeTone = "good" | "warning" | "critical" | "neutral";

export type OperatorHomeStageKey = PipelineStageKey;

export type OperatorHomeOverall = {
  status: PipelineDashboardStatus;
  headline: string;
  critical_count: number;
  running_count: number;
  generated_at: string;
};

export type OperatorHomeMetric = {
  key: string;
  label: string;
  value: number;
  detail: string;
  tone: OperatorHomeTone;
  href: string | null;
};

export type OperatorHomePriorityItem = {
  id: string;
  severity: PipelineDashboardSeverity;
  stage_key: OperatorHomeStageKey;
  title: string;
  detail: string;
  count: number;
  href: string;
  recommended_action: string;
  oldest_at: string | null;
};

export type OperatorHomeStage = {
  key: OperatorHomeStageKey;
  label: string;
  status: PipelineDashboardStatus;
  waiting_count: number;
  running_count: number;
  failed_count: number;
  review_count: number;
  ready_count: number;
  href: string;
};

export type OperatorHomeActiveWork = {
  job_id: string;
  source_video_id: string | null;
  title: string;
  stage_key: OperatorHomeStageKey;
  status: string;
  progress_percent: number;
  current_step: string | null;
  started_at: string | null;
  updated_at: string;
  next_action: string;
  href: string;
};

export type OperatorHomeCheckpoint = {
  key: string;
  label: string;
  count: number;
  detail: string;
  tone: OperatorHomeTone;
  href: string;
  oldest_at: string | null;
};

export type OperatorHomeOutputQaSummary = {
  passed: number;
  warned: number;
  failed: number;
  ungraded: number;
  total: number;
};

export type OperatorHomeAttentionBreakdown = {
  critical: number;
  warning: number;
  manual_review: number;
  total: number;
};

export type OperatorHomeRecentOutput = {
  render_output_id: string;
  source_video_id: string;
  title: string;
  render_status: string;
  qa_status: "pass" | "warn" | "fail" | "ungraded";
  duration_seconds: number | null;
  finished_at: string | null;
  href: string;
};

export type OperatorHomeReadinessItem = {
  key: string;
  label: string;
  status: "ready" | "warning" | "blocked" | "unknown";
  detail: string;
  href: string | null;
};

export type OperatorHomeSummaryResponse = {
  overall: OperatorHomeOverall;
  decision_metrics: OperatorHomeMetric[];
  priority_items: OperatorHomePriorityItem[];
  stages: OperatorHomeStage[];
  active_work: OperatorHomeActiveWork | null;
  manual_checkpoints: OperatorHomeCheckpoint[];
  output_qa_summary: OperatorHomeOutputQaSummary;
  attention_breakdown: OperatorHomeAttentionBreakdown;
  recent_outputs: OperatorHomeRecentOutput[];
  system_readiness: OperatorHomeReadinessItem[];
  partial_errors: string[];
};
