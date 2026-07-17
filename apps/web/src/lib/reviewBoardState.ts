import { getReviewCandidateMetadata, reviewCandidateDisplayScore, reviewCandidateViewsForSort } from "./reviewCandidateMetadata";
import type { Candidate, CandidateFilters, CandidateStatus } from "../types/review-board";

export const DEFAULT_FILTERS: CandidateFilters = {
  status: "SHORTLISTED",
  minScore: "",
  maxScore: "",
  sourceProfileId: "",
  search: "",
  sort: "score_desc",
  presetName: ""
};

export function toggleSelection(selection: Set<string>, candidateId: string): Set<string> {
  const next = new Set(selection);
  if (next.has(candidateId)) {
    next.delete(candidateId);
  } else {
    next.add(candidateId);
  }
  return next;
}

export function selectAllOnPage(candidates: Candidate[]): Set<string> {
  return new Set(candidates.map((candidate) => candidate.id));
}

export function allVisibleSelected(visible: Candidate[], selection: Set<string>): boolean {
  return visible.length > 0 && visible.every((candidate) => selection.has(candidate.id));
}

export function toggleSelectAllVisible(visible: Candidate[], selection: Set<string>): Set<string> {
  if (allVisibleSelected(visible, selection)) return new Set();
  return selectAllOnPage(visible);
}

export function selectedVisibleIds(visible: Candidate[], selection: Set<string>): string[] {
  const visibleIds = new Set(visible.map((candidate) => candidate.id));
  return [...selection].filter((id) => visibleIds.has(id));
}

export function applyCandidateStatusUpdate(
  candidates: Candidate[],
  candidateIds: string[],
  status: CandidateStatus
): Candidate[] {
  const ids = new Set(candidateIds);
  return candidates.map((candidate) => (ids.has(candidate.id) ? { ...candidate, status } : candidate));
}

export function candidateMatchesReviewBoardSearch(candidate: Candidate, search: string): boolean {
  const query = search.trim().toLowerCase();
  if (!query) return true;
  const metadata = getReviewCandidateMetadata(candidate);
  const haystacks = [
    candidate.id,
    metadata.captureItemId,
    metadata.awemeId,
    metadata.sourceVideoExternalId,
    metadata.caption,
    metadata.title,
    metadata.description,
    metadata.profileName,
    metadata.profileUrl,
    metadata.sourceUrl,
    metadata.videoUrl,
    metadata.postedDisplay,
    metadata.postedText,
    metadata.durationText,
    metadata.estimatedViewsDisplay,
    metadata.thumbnailUrl,
    candidate.source_video?.caption,
    candidate.source_video?.source_url,
    candidate.source_video?.source_video_external_id
  ]
    .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
    .map((value) => value.toLowerCase());
  if (haystacks.some((value) => value.includes(query))) return true;
  const metadataBlob = JSON.stringify({
    candidate: candidate.metadata_json ?? null,
    source_video: candidate.source_video?.metadata_json ?? null,
    source_metadata: (candidate as Candidate & { source_metadata?: unknown }).source_metadata ?? null
  }).toLowerCase();
  return metadataBlob.includes(query);
}

export function filterCandidatesForSearch(candidates: Candidate[], search: string): Candidate[] {
  const query = search.trim();
  if (!query) return candidates;
  return candidates.filter((candidate) => candidateMatchesReviewBoardSearch(candidate, query));
}

export function sortCandidates(candidates: Candidate[], sort: CandidateFilters["sort"]): Candidate[] {
  const copy = [...candidates];
  if (sort === "newest_first") {
    return copy.sort((a, b) => dateValue(b.source_video?.posted_at) - dateValue(a.source_video?.posted_at));
  }
  if (sort === "views_desc") {
    return copy.sort((a, b) => reviewCandidateViewsForSort(b) - reviewCandidateViewsForSort(a));
  }
  return copy.sort((a, b) => (reviewCandidateDisplayScore(b) ?? -1) - (reviewCandidateDisplayScore(a) ?? -1));
}

export function effectiveReviewStatusFilter(filters: CandidateFilters): CandidateFilters["status"] {
  return filters.search.trim() ? "" : filters.status;
}

export function visibleCandidates(
  candidates: Candidate[],
  filters: CandidateFilters,
  options?: { serverSearch?: boolean }
): Candidate[] {
  const query = filters.search.trim();
  const filtered = !query ? candidates : options?.serverSearch ? candidates : filterCandidatesForSearch(candidates, query);
  return sortCandidates(filtered, filters.sort);
}

function dateValue(value: string | null | undefined): number {
  return value ? new Date(value).getTime() : 0;
}

