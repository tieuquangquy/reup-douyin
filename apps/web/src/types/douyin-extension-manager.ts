import type { DouyinExtensionStatusResponse } from "./douyin-extension-setup";

export type DouyinExtensionPageType =
  | "login_page"
  | "challenge_page"
  | "home_feed_page"
  | "profile_page"
  | "profile_feed_page"
  | "video_detail_page"
  | "unsupported_page"
  | "unknown_page";

export type DouyinExtensionPageSnapshot = {
  url?: string | null;
  title?: string | null;
  body_text_sample?: string | null;
  page_type?: DouyinExtensionPageType | null;
  profile_url?: string | null;
  profile_external_id?: string | null;
  handle?: string | null;
  display_name?: string | null;
  video_link_count?: number;
};

export type DouyinExtensionDetectPageRequest = {
  page: DouyinExtensionPageSnapshot;
  diagnostics?: Record<string, unknown>;
};

export type DouyinExtensionDetectPageResponse = {
  diagnostics_id: string;
  detected_page_type: DouyinExtensionPageType;
  supported_capture: boolean;
  recommended_action: string;
  recommended_action_label: string;
  operator_message: string;
  page_url: string | null;
  normalized_profile_url: string | null;
  title: string | null;
  video_link_count: number;
  detected_at: string;
};

export type DouyinExtensionProfilePayload = {
  id?: string | null;
  sec_uid?: string | null;
  handle?: string | null;
  unique_id?: string | null;
  display_name?: string | null;
  nickname?: string | null;
};

export type DouyinExtensionVideoPayload = {
  aweme_id?: string | null;
  source_video_url?: string | null;
  share_url?: string | null;
  url?: string | null;
  desc?: string | null;
  statistics?: Record<string, unknown>;
};

export type DouyinExtensionCaptureRequest = {
  schema_version?: "douyin_extension_capture.v1";
  capture_id?: string | null;
  captured_at?: string | null;
  persist?: boolean;
  page: DouyinExtensionPageSnapshot;
  profile?: DouyinExtensionProfilePayload | null;
  videos?: DouyinExtensionVideoPayload[];
  diagnostics?: Record<string, unknown>;
};

export type DouyinExtensionCaptureFailureSummary = {
  stage: string;
  item_index: number | null;
  code: string;
  message: string;
};

export type DouyinExtensionCaptureResponse = {
  success: boolean;
  diagnostics_id: string;
  capture_id: string | null;
  detected_page_type: DouyinExtensionPageType;
  capture_session_id: string | null;
  source_profile_id: string | null;
  crawl_session_id: string | null;
  submitted_profile_url: string;
  normalized_profile_identifier: string | null;
  videos_discovered_count: number;
  videos_created_count: number;
  videos_updated_count: number;
  candidates_total_count: number;
  candidates_matched_count: number;
  candidates_rejected_count: number;
  candidate_results_count: number;
  captured_item_count: number;
  normalized_item_count: number;
  duplicate_item_count: number;
  ready_item_count: number;
  skipped_item_count: number;
  promoted_item_count: number;
  candidate_created_count: number;
  failed_item_count: number;
  stage: string;
  error_code: string | null;
  warning_codes: string[];
  failure_summaries: DouyinExtensionCaptureFailureSummary[];
  visible_captured_count: number;
  submitted_count: number;
  staged_count: number;
  deduped_count: number;
  skipped_count: number;
  failed_count: number;
  warning: string | null;
  discovered_at: string;
  current_page_url: string | null;
  current_page_title: string | null;
  current_page_video_link_count: number;
  next_suggested_route: string;
};

export type DouyinExtensionManagerHistoryItem = {
  event_id: string;
  event_type: "handshake" | "detect" | "capture";
  status: "success" | "failed";
  created_at: string;
  page_type: DouyinExtensionPageType | null;
  page_url: string | null;
  page_title: string | null;
  supported_capture: boolean | null;
  imported_profile_count: number;
  videos_discovered_count: number;
  videos_created_count: number;
  videos_updated_count: number;
  candidates_matched_count: number;
  error_code: string | null;
  error_message: string | null;
  warning: string | null;
  recommended_next_action: string | null;
  recommended_next_action_label: string | null;
  diagnostics_id: string | null;
};

export type DouyinExtensionManagerHistoryResponse = {
  items: DouyinExtensionManagerHistoryItem[];
  total_count: number;
};

export type DouyinExtensionManagerState = {
  status: DouyinExtensionStatusResponse | null;
  history: DouyinExtensionManagerHistoryResponse | null;
};
