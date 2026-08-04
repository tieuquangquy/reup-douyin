import type { PublishTargetPlatform } from "./publish-draft";

export type ExportPackageStatus =
  | "DRAFT"
  | "READY_FOR_HANDOFF"
  | "HANDOFF_CREATED"
  | "FAILED_NEEDS_ATTENTION"
  | "CANCELLED";

export type PublishHandoffStatus =
  | "DRAFT"
  | "READY_FOR_OPERATOR"
  | "ACCEPTED"
  | "FAILED_NEEDS_ATTENTION"
  | "CANCELLED";

export type ReupQueueBatchAction =
  | "START_PROCESSING"
  | "START_AUTO_PIPELINE"
  | "SET_AUTOMATION"
  | "HOLD"
  | "RESUME"
  | "RETRY"
  | "CANCEL"
  | "MARK_MEDIA_READY"
  | "CREATE_EXPORT_PACKAGE"
  | "CREATE_PUBLISH_HANDOFF"
  | "DISMISS"
  | "PURGE";

export type BatchItemResult = {
  item_id: string;
  result: "succeeded" | "skipped" | "failed" | string;
  status: string | null;
  reason_code: string | null;
  message: string | null;
  export_package_id: string | null;
  publish_handoff_id: string | null;
};

export type BatchOperationResponse = {
  requested_count: number;
  succeeded_count: number;
  skipped_count: number;
  failed_count: number;
  export_package_id: string | null;
  publish_handoff_id: string | null;
  results: BatchItemResult[];
};

export type ReupQueueBatchActionRequest = {
  action: ReupQueueBatchAction;
  item_ids: string[];
  note?: string | null;
  target_platform?: PublishTargetPlatform | null;
  pipeline_mode?: string | null;
};

export type ExportPackageCreateRequest = {
  item_ids: string[];
  label?: string | null;
  operator_note?: string | null;
};

export type ExportPackageItem = {
  id: string;
  workspace_id: string;
  export_package_id: string;
  reup_queue_item_id: string;
  source_video_id: string;
  video_candidate_id: string;
  render_output_id: string | null;
  publish_draft_id: string | null;
  item_status: string;
  manifest_json: Record<string, unknown> | null;
  diagnostics_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type ExportPackage = {
  id: string;
  workspace_id: string;
  status: ExportPackageStatus;
  label: string | null;
  operator_note: string | null;
  item_count: number;
  manifest_json: Record<string, unknown> | null;
  diagnostics_json: Record<string, unknown> | null;
  ready_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
  items: ExportPackageItem[];
  publish_handoff_ids: string[];
  created_at: string;
  updated_at: string;
};

export type ExportPackageListResponse = {
  items: ExportPackage[];
  total_count: number;
  limit: number;
  offset: number;
};

export type PublishHandoffCreateRequest = {
  export_package_id: string;
  target_platform?: PublishTargetPlatform;
  operator_note?: string | null;
};

export type PublishHandoff = {
  id: string;
  workspace_id: string;
  export_package_id: string;
  target_platform: PublishTargetPlatform;
  status: PublishHandoffStatus;
  operator_note: string | null;
  payload_json: Record<string, unknown> | null;
  diagnostics_json: Record<string, unknown> | null;
  ready_at: string | null;
  accepted_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PublishHandoffListResponse = {
  items: PublishHandoff[];
  total_count: number;
  limit: number;
  offset: number;
};
