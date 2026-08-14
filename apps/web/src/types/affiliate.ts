import type { Job } from "./jobs";


export type AffiliatePlatform = "FACEBOOK" | "TIKTOK_SHOP" | "SHOPEE" | "OTHER";
export type AffiliateAvailability = "IN_STOCK" | "OUT_OF_STOCK" | "UNKNOWN";

export type AffiliateProduct = {
  id: string;
  workspace_id: string;
  catalog_version: string;
  platform: AffiliatePlatform;
  external_product_id: string | null;
  merchant_name: string | null;
  name: string;
  description: string | null;
  image_url: string | null;
  product_url: string | null;
  affiliate_url: string;
  currency_code: string;
  price_amount: number | null;
  commission_rate_percent: number | null;
  commission_amount: number | null;
  availability_status: AffiliateAvailability;
  keywords: string[];
  supported_platforms: string[];
  topic_ids: string[];
  topic_codes: string[];
  topic_names: string[];
  fingerprint_sha256: string;
  is_active: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AffiliateProductInput = {
  catalog_version?: string;
  platform: AffiliatePlatform;
  external_product_id?: string | null;
  merchant_name?: string | null;
  name: string;
  description?: string | null;
  image_url?: string | null;
  product_url?: string | null;
  affiliate_url: string;
  currency_code?: string;
  price_amount?: number | null;
  commission_rate_percent?: number | null;
  commission_amount?: number | null;
  availability_status: AffiliateAvailability;
  keywords?: string[];
  supported_platforms?: string[];
  topic_ids?: string[];
  is_active?: boolean;
};

export type AffiliateProductListResponse = {
  products: AffiliateProduct[];
  total: number;
  limit: number;
  offset: number;
  active_count: number;
  out_of_stock_count: number;
};

export type AffiliateProductBulkImportResponse = {
  created_count: number;
  updated_count: number;
  skipped_count: number;
  products: AffiliateProduct[];
};

export type AffiliateProductImageUpload = {
  id: string;
  image_url: string;
  public_path: string;
  content_type: string;
  size_bytes: number;
  checksum_sha256: string;
  created_at: string;
};

export type AffiliateProductMatchSuggestion = {
  rank: number;
  product_id: string;
  product_name: string;
  merchant_name: string | null;
  platform: string;
  affiliate_url: string;
  image_url: string | null;
  price_amount: number | null;
  currency_code: string;
  commission_rate_percent: number | null;
  availability_status: string;
  affiliate_fit_score: number;
  score_breakdown: Record<string, number>;
  evidence: string[];
};

export type AffiliateProductMatch = {
  id: string;
  workspace_id: string;
  platform_publication_id: string;
  content_classification_id: string;
  matcher_version: string;
  catalog_version: string;
  catalog_fingerprint_sha256: string;
  decision_status: "NEEDS_REVIEW" | "APPROVED" | "REJECTED" | "OVERRIDDEN";
  suggestions: AffiliateProductMatchSuggestion[];
  selected_product_id: string | null;
  selected_fit_score: number | null;
  created_by_job_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  decision_reason: string | null;
  is_current: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AffiliateProductMatchRunResponse = {
  reused: boolean;
  product_match: AffiliateProductMatch | null;
  job: Job | null;
};

export type AffiliateProductMatchJobSummary = {
  id: string;
  status: string;
  progress_percent: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
};

export type AffiliateProductMatchQueueItem = {
  platform_publication_id: string;
  platform_account_id: string;
  page_display_name: string;
  external_reel_id: string | null;
  external_permalink: string | null;
  caption: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  classification_id: string;
  classification_status: string;
  primary_topic_code: string | null;
  primary_topic_name: string | null;
  product_match: AffiliateProductMatch | null;
  latest_job: AffiliateProductMatchJobSummary | null;
};

export type AffiliateProductMatchQueueResponse = {
  items: AffiliateProductMatchQueueItem[];
  total: number;
  limit: number;
  offset: number;
  kpis: {
    eligible_publications: number;
    unmatched_count: number;
    needs_review_count: number;
    approved_count: number;
    rejected_count: number;
    overridden_count: number;
    stale_count: number;
  };
};
