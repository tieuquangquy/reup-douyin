import type { WholeProfileHarvestCaptureStatus, WholeProfileHarvestQueueItem, WholeProfileHarvestQueuePreviewItem, WholeProfileHarvestTargetDetail } from "./state.js";

export type DouyinProfileVideoClassificationStatus = WholeProfileHarvestCaptureStatus;
export type DouyinProfileVideoCollectionMode = "new_incomplete_failed" | "new_and_incomplete" | "new_only" | "failed_only" | "refresh_all";

export type DouyinProfileVideoClassificationCandidate = {
  aweme_id: string;
  video_url: string | null;
  source_url: string | null;
  thumbnail_url: string | null;
  caption: string | null;
  posted_text: string | null;
  posted_at: string | null;
  view_count: number | null;
};

export type DouyinProfileVideoClassificationRequest = {
  schema_version: "douyin_profile_video_classification.v1";
  profile_url: string;
  sec_uid: string | null;
  collection_mode: "new_incomplete_failed";
  candidates: DouyinProfileVideoClassificationCandidate[];
  include_unknown: false;
  dry_run: true;
};

export type DouyinProfileVideoClassificationCounts = Record<WholeProfileHarvestCaptureStatus, number> & {
  collect: number;
  skip: number;
};

export type DouyinProfileVideoClassificationTarget = {
  aweme_id: string;
  classification: DouyinProfileVideoClassificationStatus;
  collect: boolean;
  reason: string;
  required_missing_fields: string[];
  existing_item_id: string | null;
  metadata_status: string | null;
  review_status: string | null;
  video_url: string | null;
  source_url: string | null;
  thumbnail_url: string | null;
  caption: string | null;
};

export type DouyinProfileVideoClassificationResponse = {
  schema_version: "douyin_profile_video_classification_result.v1";
  profile_url: string;
  sec_uid: string | null;
  collection_mode: string;
  database_lookup_status: string;
  total_candidates: number;
  counts: DouyinProfileVideoClassificationCounts;
  targets: DouyinProfileVideoClassificationTarget[];
  collect_aweme_ids: string[];
  skip_aweme_ids: string[];
  diagnostics: Record<string, unknown>;
};

export function emptyDouyinProfileVideoClassificationCounts(): DouyinProfileVideoClassificationCounts {
  return { new: 0, incomplete: 0, complete: 0, failed: 0, skipped: 0, unknown: 0, collect: 0, skip: 0 };
}

export function buildDouyinProfileVideoClassificationRequest(args: {
  profileUrl: string;
  secUid?: string | null;
  targetDetails: WholeProfileHarvestTargetDetail[];
}): DouyinProfileVideoClassificationRequest {
  const seen = new Set<string>();
  const candidates: DouyinProfileVideoClassificationCandidate[] = [];
  for (const target of args.targetDetails) {
    const awemeId = String(target.aweme_id ?? "").trim();
    if (!awemeId || seen.has(awemeId)) continue;
    seen.add(awemeId);
    const sourceUrl = target.source_url ?? null;
    candidates.push({
      aweme_id: awemeId,
      video_url: sourceUrl ?? `https://www.douyin.com/video/${awemeId}`,
      source_url: sourceUrl,
      thumbnail_url: target.thumbnail_url ?? null,
      caption: target.caption ?? target.title ?? target.text_sample ?? null,
      posted_text: target.posted_text ?? null,
      posted_at: target.posted_at ?? null,
      view_count: typeof target.view_count === "number" ? target.view_count : null
    });
  }
  return {
    schema_version: "douyin_profile_video_classification.v1",
    profile_url: args.profileUrl,
    sec_uid: args.secUid ?? null,
    collection_mode: "new_incomplete_failed",
    candidates,
    include_unknown: false,
    dry_run: true
  };
}

export function applyProfileVideoClassificationToTargets(
  targetDetails: WholeProfileHarvestTargetDetail[],
  response: DouyinProfileVideoClassificationResponse
): WholeProfileHarvestTargetDetail[] {
  const byAwemeId = new Map(response.targets.map((target) => [target.aweme_id, target]));
  return targetDetails.map((target) => {
    const classified = byAwemeId.get(target.aweme_id);
    if (!classified) return { ...target, capture_status: "unknown" as const };
    return {
      ...target,
      capture_status: classified.classification,
      backend_item: {
        item_id: classified.existing_item_id,
        metadata_status: classified.metadata_status,
        missing_fields: classified.required_missing_fields,
        existing_fields: {},
        updated_at: null
      }
    };
  });
}

export function buildCollectQueueFromClassification(args: {
  targetDetails: WholeProfileHarvestTargetDetail[];
  responseTargets: DouyinProfileVideoClassificationTarget[];
  batchLimit?: number | "all";
}): WholeProfileHarvestQueueItem[] {
  const detailByAwemeId = new Map(args.targetDetails.map((detail) => [detail.aweme_id, detail]));
  const collectTargets = args.responseTargets.filter((target) => target.collect === true);
  const limited = args.batchLimit === "all" ? collectTargets : collectTargets.slice(0, typeof args.batchLimit === "number" ? args.batchLimit : collectTargets.length);
  return limited.map((target, index) => {
    const detail = detailByAwemeId.get(target.aweme_id);
    return {
      index: detail?.index ?? index + 1,
      aweme_id: target.aweme_id,
      capture_status: target.classification,
      status: "pending",
      attempts: 0,
      checkpoint_sequence: null,
      extraction_result: null,
      last_error: null,
      capture_inbox_item_id: null,
      source_url: target.source_url ?? detail?.source_url ?? target.video_url ?? `https://www.douyin.com/video/${target.aweme_id}`,
      profile_card_evidence: detail?.profile_card_evidence ?? {}
    };
  });
}

export function buildCollectQueuePreviewFromQueue(queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[]): WholeProfileHarvestQueuePreviewItem[] {
  const detailByAwemeId = new Map(targetDetails.map((detail) => [detail.aweme_id, detail]));
  return queue.map((item) => {
    const detail = detailByAwemeId.get(item.aweme_id);
    return {
      index: item.index,
      aweme_id: item.aweme_id,
      capture_status: item.capture_status,
      source_url: item.source_url,
      title: detail?.title ?? detail?.caption ?? null,
      thumbnail_url: detail?.thumbnail_url ?? null
    };
  });
}
