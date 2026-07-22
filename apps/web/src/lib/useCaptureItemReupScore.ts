import { useMemo } from "react";

import { getReupScoreForCaptureItem, type DouyinReupScore } from "./captureInboxReupScore";
import { getOperatorTileScoreBadge, type OperatorTileScoreBadge } from "./operatorTileScore";
import { buildCapturedItemFromReupQueueItem, buildCapturedItemFromReviewCandidate } from "./operatorReupScore";
import type { CapturedItem } from "../types/capture-inbox";
import type { Candidate } from "../types/review-board";
import type { ReupQueueItem } from "../types/reup-queue";

/** Core metadata fields that affect Reup Score — stable memo deps for tile rendering. */
export function buildReupScoreMemoDeps(item: CapturedItem | null): unknown[] {
  return [
    item?.id ?? null,
    item?.view_count ?? null,
    item?.estimated_views_mid ?? null,
    item?.estimated_views_min ?? null,
    item?.estimated_views_max ?? null,
    item?.like_count ?? null,
    item?.comment_count ?? null,
    item?.share_count ?? null,
    item?.favorite_count ?? null,
    item?.follower_count ?? null,
    item?.duration_seconds ?? null,
    item?.posted_at ?? null,
    item?.status ?? null,
    item?.metadata_status ?? null,
    item?.thumbnail_url ?? null,
    item?.duplicate_of_item_id ?? null,
    item?.existing_source_video_id ?? null
  ];
}

export function useOptionalReupScoreForCaptureItem(item: CapturedItem | null): DouyinReupScore | null {
  return useMemo(
    () => (item ? getReupScoreForCaptureItem(item) : null),
    buildReupScoreMemoDeps(item)
  );
}

export function useReupScoreForCaptureItem(item: CapturedItem): DouyinReupScore {
  return useMemo(() => getReupScoreForCaptureItem(item), buildReupScoreMemoDeps(item));
}

export function useOperatorTileScoreBadge(item: CapturedItem): OperatorTileScoreBadge {
  return useMemo(() => getOperatorTileScoreBadge(item), buildReupScoreMemoDeps(item));
}

export function useReviewCandidateTileScoreBadge(candidate: Candidate): OperatorTileScoreBadge {
  return useMemo(
    () => getOperatorTileScoreBadge(buildCapturedItemFromReviewCandidate(candidate)),
    [
      candidate.id,
      candidate.score,
      candidate.metadata_json,
      candidate.source_video_id,
      candidate.status
    ]
  );
}

export function useQueueTileScoreBadge(item: ReupQueueItem): OperatorTileScoreBadge {
  return useMemo(
    () => getOperatorTileScoreBadge(buildCapturedItemFromReupQueueItem(item)),
    [
      item.id,
      item.priority,
      item.status,
      item.metadata_json,
      item.source_video_id
    ]
  );
}
