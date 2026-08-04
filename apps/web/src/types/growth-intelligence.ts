import type { Job } from "./jobs";

export type GrowthAssessmentStatus = "INSUFFICIENT_DATA" | "READY" | "STALE" | "COUNTER_REGRESSION";
export type GrowthConfidence = "LOW" | "MEDIUM" | "HIGH";
export type OpportunityRecommendation = "PRIORITY" | "MONITOR" | "DO_NOT_PLACE" | "INSUFFICIENT_DATA";

export type PublicationGrowthAssessment = {
  id: string;
  workspace_id: string;
  platform_publication_id: string;
  score_version: string;
  input_fingerprint_sha256: string;
  latest_metric_snapshot_id: string | null;
  created_by_job_id: string | null;
  status: GrowthAssessmentStatus;
  confidence: GrowthConfidence;
  growth_score: number | null;
  snapshot_count: number;
  observation_hours: number | null;
  measurement_age_seconds: number | null;
  score_breakdown: Record<string, number>;
  evidence: string[];
  input_snapshot_ids: string[];
  is_current: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type GrowthScoreRunResponse = {
  reused: boolean;
  growth_assessment: PublicationGrowthAssessment | null;
  job: Job | null;
};

export type GrowthScoreJobSummary = {
  id: string;
  status: string;
  progress_percent: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
};

export type AffiliateOpportunityItem = {
  platform_publication_id: string;
  platform_account_id: string;
  page_display_name: string;
  external_reel_id: string | null;
  external_permalink: string | null;
  caption: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  product_match_id: string;
  product_match_decision: string;
  selected_product_id: string;
  selected_product_name: string;
  selected_product_platform: string;
  selected_product_affiliate_url: string;
  selected_product_image_url: string | null;
  selected_product_availability: string;
  selected_product_active: boolean;
  affiliate_fit_score: number | null;
  growth_assessment: PublicationGrowthAssessment | null;
  growth_is_stale: boolean;
  recommendation: OpportunityRecommendation;
  recommendation_reason: string;
  latest_job: GrowthScoreJobSummary | null;
};

export type AffiliateOpportunityQueueResponse = {
  items: AffiliateOpportunityItem[];
  total: number;
  limit: number;
  offset: number;
  kpis: {
    eligible_count: number;
    priority_count: number;
    monitor_count: number;
    do_not_place_count: number;
    insufficient_data_count: number;
    stale_count: number;
  };
};
