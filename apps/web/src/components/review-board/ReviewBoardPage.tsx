"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition, type KeyboardEvent } from "react";
import { useT } from "../../lib/i18n";
import { applyCandidatePreset, bulkUpdateCandidateStatus, deleteCandidate, enqueueReupCandidates, fetchCandidateDetail, fetchCandidates } from "../../lib/api";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { getDouyinMetadataCompletenessForItem } from "../../lib/captureInboxFilterMetadata";
import { buildCapturedItemFromReviewCandidate } from "../../lib/operatorReupScore";
import { formatReupScoreBadgeValue, reupScoreBadgeLevelForCaptureItem, reupScoreBadgeTier } from "../../lib/reupScoreBadge";
import { formatReviewEstimatedViews, formatReviewPostedLabel, getReviewCandidateMetadata, reviewCandidateDisplayScore, type ReviewCandidateMetadata } from "../../lib/reviewCandidateMetadata";
import { formatExactEngagementMetric } from "../../lib/captureInboxCanonical";
import { pickBestBenchCandidateId, splitApproveBestTargets } from "../../lib/reviewBoardBenchState";
import { canOpenCompare, removeStars } from "../../lib/reviewBoardDecisionState";
import { approvedCandidatesFromIds, applyQueuedMembershipToCandidates, candidatesPendingApproval, formatApproveAndEnqueueNotice, formatReupQueueEnqueueNotice, isCandidateInReupQueue, selectableBoardCandidates } from "../../lib/reviewBoardQueueState";
import {
  DEFAULT_FILTERS,
  applyCandidateStatusUpdate,
  effectiveReviewStatusFilter,
  selectAllOnPage,
  selectedVisibleIds,
  toggleSelection,
  visibleCandidates
} from "../../lib/reviewBoardState";
import type { BulkActionStatus, Candidate, CandidateFilters, CandidateStatus } from "../../types/review-board";
import { ReviewBoardTileActions } from "./ReviewBoardTileActions";
import { CaptureInboxFilterChipIcon, type CaptureInboxFilterChipIconKind } from "../capture-inbox/CaptureInboxFilterChipIcon";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { OpsConsolePage, statusTone } from "../ops-console/OpsShared";
import { OffsetLoadMoreFooter } from "../shared/OffsetLoadMoreFooter";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";
import { WorkItemDetailsDrawer } from "../shared/WorkItemDetailsDrawer";
import { WorkMediaTileOverlay } from "../shared/WorkMediaTileOverlay";
import { WorkBulkActionBar, WorkGalleryEmptyState, WorkGalleryHeader, WorkStudioDeck } from "../shared/WorkStudioChrome";
import { useOffsetLoadMoreOnScroll } from "../shared/useOffsetLoadMoreOnScroll";
import { useReviewCandidateTileScoreBadge } from "../../lib/useCaptureItemReupScore";
import { hasMoreOffsetItems, mergeOffsetItemsById } from "../../lib/offsetListPagination";
import { useAsyncAction } from "../../lib/useAsyncAction";

type ReviewFilterKey = "" | CandidateStatus;
type ReviewBulkAction = "reject" | "remove";

type ReviewSummary = {
  total: number;
  approved: number;
  rejected: number;
  inReview: number;
  newItems: number;
  shortlisted: number;
};

const REVIEW_STATUS_FILTERS: Array<{ key: ReviewFilterKey; label: string }> = [
  { key: "", label: "All" },
  { key: "NEW", label: "New" },
  { key: "SHORTLISTED", label: "Shortlisted" },
  { key: "IN_REVIEW", label: "In review" },
  { key: "APPROVED", label: "Approved" },
  { key: "REJECTED", label: "Rejected" }
];

const REVIEW_STATUS_STAT_BAR_PATTERNS: Partial<Record<ReviewFilterKey, readonly number[]>> = {
  "": [0.88, 0.92, 0.9, 0.86, 0.91],
  NEW: [0.42, 0.58, 0.74, 0.9, 1],
  SHORTLISTED: [0.34, 0.52, 0.72, 0.88, 1],
  IN_REVIEW: [0.28, 0.72, 0.46, 0.86, 0.62],
  APPROVED: [1, 0.82, 0.66, 0.48, 0.32],
  REJECTED: [0.82, 0.38, 0.74, 0.3, 0.58]
};

const UI_VERSION = "22F-7R";
const CANDIDATE_PAGE_SIZE = 200;

export function ReviewBoardPage() {
  const t = useT();
  const asyncActions = useAsyncAction();
  const { notify } = useNotice();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<CandidateFilters>(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<CandidateFilters>(DEFAULT_FILTERS);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [statusCounts, setStatusCounts] = useState<Partial<Record<CandidateStatus, number>>>({});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [starredIds, setStarredIds] = useState<string[]>([]);
  const [compareOpen, setCompareOpen] = useState(false);
  const [activeCandidateId, setActiveCandidateId] = useState<string | null>(null);
  const [rightInspectorOpen, setRightInspectorOpen] = useState(false);
  const [candidateDetails, setCandidateDetails] = useState<Record<string, Candidate>>({});
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);
  const [bulkDialog, setBulkDialog] = useState<ReviewBulkAction | null>(null);
  const [scoreRangeOpen, setScoreRangeOpen] = useState(false);
  const [showQueuedInApproved, setShowQueuedInApproved] = useState(false);
  const [pendingStatus, setPendingStatus] = useState<ReviewFilterKey | null>(null);
  const [isStatusPending, startStatusTransition] = useTransition();

  function candidateActionKey(candidateId: string, action: string) {
    return `candidate:${candidateId}:${action}`;
  }

  function candidatePendingAction(candidateId: string): string | null {
    const prefix = `candidate:${candidateId}:`;
    const key = [...asyncActions.pendingKeys].find((entry) => entry.startsWith(prefix));
    return key?.slice(prefix.length) ?? null;
  }

  const loadData = useCallback(async (intent: "initial" | "refresh" | "filter" = "filter") => {
    const preserveUi = intent === "refresh";
    if (preserveUi) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      if (!preserveUi && appliedFilters.presetName) {
        await applyCandidatePreset(appliedFilters);
      }
      const { candidates: nextCandidates, statusCounts: nextStatusCounts, totalCount: nextTotalCount } = await fetchCandidates(appliedFilters, {
        limit: CANDIDATE_PAGE_SIZE,
        offset: 0
      });
      setCandidates(nextCandidates);
      setStatusCounts(nextStatusCounts);
      setTotalCount(nextTotalCount);
      if (!preserveUi) {
        setCandidateDetails({});
        setStarredIds([]);
        setCompareOpen(false);
        setRightInspectorOpen(false);
        setSelectedIds(new Set());
        setActiveCandidateId(null);
      }
      const loadedIds = new Set(nextCandidates.map((candidate) => candidate.id));
      setStarredIds((current) => current.filter((id) => loadedIds.has(id)));
      setSelectedIds((current) => new Set([...current].filter((id) => loadedIds.has(id) && !nextCandidates.find((c) => c.id === id && c.in_reup_queue))));
    } catch (err) {
      const message = err instanceof Error ? err.message : t("reviewBoardPage.loadError");
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [appliedFilters, notify, t]);

  const hasMoreCandidates = hasMoreOffsetItems(candidates.length, totalCount);
  const candidatesRef = useRef(candidates);
  const loadMoreInFlightRef = useRef(false);
  candidatesRef.current = candidates;

  const loadMoreCandidates = useCallback(async () => {
    const currentCandidates = candidatesRef.current;
    if (loadMoreInFlightRef.current || loadingMore || loading || !hasMoreOffsetItems(currentCandidates.length, totalCount)) return;
    loadMoreInFlightRef.current = true;
    setLoadingMore(true);
    setError(null);
    try {
      const { candidates: nextPage, statusCounts: nextStatusCounts, totalCount: nextTotalCount } = await fetchCandidates(appliedFilters, {
        limit: CANDIDATE_PAGE_SIZE,
        offset: currentCandidates.length
      });
      const merged = mergeOffsetItemsById(currentCandidates, nextPage);
      setCandidates(merged);
      setStatusCounts(nextStatusCounts);
      setTotalCount(nextTotalCount);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("reviewBoardPage.loadError");
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      loadMoreInFlightRef.current = false;
      setLoadingMore(false);
    }
  }, [appliedFilters, loading, loadingMore, notify, t, totalCount]);

  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  useOffsetLoadMoreOnScroll({
    sentinelRef: loadMoreRef,
    hasMore: hasMoreCandidates,
    loading: loadingMore,
    disabled: mutating || loading || isStatusPending,
    loadedCount: candidates.length,
    onLoadMore: loadMoreCandidates,
  });

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    const term = filters.search.trim();
    if (term === appliedFilters.search.trim()) return;
    const handle = window.setTimeout(() => {
      setAppliedFilters((current) => ({
        ...current,
        search: filters.search,
        status: term ? "" : current.status
      }));
      if (term) {
        setFilters((current) => ({ ...current, status: "" }));
      }
    }, 300);
    return () => window.clearTimeout(handle);
  }, [appliedFilters.search, filters.search]);

  useEffect(() => {
    const candidateId = searchParams.get("candidate")?.trim();
    if (!candidateId) return;
    let cancelled = false;
    void (async () => {
      try {
        const detail = await fetchCandidateDetail(candidateId);
        if (cancelled) return;
        setCandidates((current) => (current.some((candidate) => candidate.id === detail.id) ? current : [detail, ...current]));
        setCandidateDetails((current) => ({ ...current, [detail.id]: detail }));
        setActiveCandidateId(detail.id);
        setRightInspectorOpen(true);
        const videoId =
          detail.aweme_id ??
          detail.source_video_external_id ??
          detail.source_video?.source_video_external_id ??
          "";
        if (videoId) {
          const nextSearch = videoId;
          setFilters((current) => ({ ...current, search: nextSearch, status: "" }));
          setAppliedFilters((current) => ({ ...current, search: nextSearch, status: "" }));
        }
      } catch {
        if (!cancelled) {
          setError(`Candidate ${candidateId} was not found on Review Board.`);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [searchParams]);

  const effectiveStatus = effectiveReviewStatusFilter(filters);
  const pendingStatusLabel = REVIEW_STATUS_FILTERS.find((entry) => entry.key === (pendingStatus ?? effectiveStatus))?.label ?? "All";
  const footerCandidateNoun = effectiveStatus
    ? `${(REVIEW_STATUS_FILTERS.find((entry) => entry.key === effectiveStatus)?.label ?? effectiveStatus).toLocaleLowerCase()} candidates`
    : "candidates";
  const serverSearchActive = appliedFilters.search.trim().length > 0;
  const statusIndependentFilters = useMemo<CandidateFilters>(
    () => ({ ...filters, status: "" }),
    [filters.maxScore, filters.minScore, filters.presetName, filters.search, filters.sort, filters.sourceProfileId]
  );

  const statusSummaryBase = useMemo(
    () => visibleCandidates(candidates, statusIndependentFilters, { serverSearch: serverSearchActive }),
    [candidates, serverSearchActive, statusIndependentFilters]
  );
  const visible = useMemo(() => filterCandidatesByReviewStatus(statusSummaryBase, effectiveStatus), [effectiveStatus, statusSummaryBase]);
  const queuedInViewCount = useMemo(() => visible.filter((candidate) => isCandidateInReupQueue(candidate)).length, [visible]);
  const displayVisible = useMemo(() => {
    if (filters.status !== "APPROVED" || showQueuedInApproved) return visible;
    return visible.filter((candidate) => !isCandidateInReupQueue(candidate));
  }, [filters.status, showQueuedInApproved, visible]);
  const selectableVisible = useMemo(() => selectableBoardCandidates(displayVisible), [displayVisible]);
  const summary = useMemo(() => buildSummaryFromStatusCounts(statusCounts), [statusCounts]);
  const bulkSelectedIds = useMemo(() => selectedVisibleIds(selectableVisible, selectedIds), [selectedIds, selectableVisible]);
  const candidatePool = useMemo(() => mergeCandidatePool(candidates, candidateDetails), [candidateDetails, candidates]);
  const bulkApprovedQueueIds = useMemo(() => approvedCandidatesFromIds(candidatePool, bulkSelectedIds), [bulkSelectedIds, candidatePool]);
  const activeCandidate = useMemo(() => {
    if (!activeCandidateId) return null;
    return candidateDetails[activeCandidateId] ?? visible.find((candidate) => candidate.id === activeCandidateId) ?? null;
  }, [activeCandidateId, candidateDetails, visible]);
  const starredCandidates = useMemo(
    () => starredIds.map((id) => candidateDetails[id] ?? visible.find((candidate) => candidate.id === id)).filter(Boolean) as Candidate[],
    [candidateDetails, starredIds, visible]
  );

  useEffect(() => {
    if (filters.status !== "APPROVED") setShowQueuedInApproved(false);
  }, [filters.status]);

  useEffect(() => {
    if (!isStatusPending) setPendingStatus(null);
  }, [isStatusPending]);

  useEffect(() => {
    if (!canOpenCompare(starredIds)) setCompareOpen(false);
  }, [starredIds]);

  useEffect(() => {
    if (!activeCandidateId) return;
    if (candidateDetails[activeCandidateId]) return;
    void fetchCandidateDetail(activeCandidateId)
      .then((candidate) => setCandidateDetails((current) => ({ ...current, [activeCandidateId]: candidate })))
      .catch(() => {
        const fallback = visible.find((candidate) => candidate.id === activeCandidateId);
        if (fallback) setCandidateDetails((current) => ({ ...current, [activeCandidateId]: fallback }));
      });
  }, [activeCandidateId, candidateDetails, visible]);

  useEffect(() => {
    if (!rightInspectorOpen) return;
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") closeInspector();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [rightInspectorOpen]);

  function closeInspector() {
    setRightInspectorOpen(false);
    setActiveCandidateId(null);
    if (!searchParams.get("candidate")) return;
    const params = new URLSearchParams(searchParams.toString());
    params.delete("candidate");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  async function updateCandidateStatuses(
    ids: string[],
    status: BulkActionStatus,
    pendingKey = ids.length === 1 ? candidateActionKey(ids[0], status.toLowerCase()) : `bulk:${status.toLowerCase()}`
  ) {
    if (ids.length === 0) return;
    await asyncActions.run(pendingKey, async () => {
    setMutating(true);
    setError(null);
    try {
      await bulkUpdateCandidateStatus(ids, status);
      setCandidates((current) => applyCandidateStatusUpdate(current, ids, status));
      setCandidateDetails((current) => {
        const next = { ...current };
        for (const id of ids) {
          if (next[id]) next[id] = { ...next[id], status };
        }
        return next;
      });
      if (status === "APPROVED" || status === "REJECTED") {
        setStarredIds((current) => removeStars(current, ids));
      }
      notify({ message: `${ids.length} candidate${ids.length === 1 ? "" : "s"} updated to ${candidateStatusLabel(status)}.`, tone: "success" });
      await loadData("refresh");
    } catch (err) {
      const message = err instanceof Error ? err.message : t("reviewBoardPage.updateError");
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setMutating(false);
    }
    });
  }

  async function bulkRemoveSelected() {
    if (bulkSelectedIds.length === 0) return;
    await asyncActions.run("bulk:remove", async () => {
    setMutating(true);
    setError(null);
    try {
      for (const candidateId of bulkSelectedIds) {
        await deleteCandidate(candidateId);
      }
      const remove = new Set(bulkSelectedIds);
      setCandidates((current) => current.filter((candidate) => !remove.has(candidate.id)));
      setStarredIds((current) => current.filter((id) => !remove.has(id)));
      setCandidateDetails((current) => {
        const next = { ...current };
        for (const id of bulkSelectedIds) delete next[id];
        return next;
      });
      setSelectedIds(new Set());
      notify({ message: `${bulkSelectedIds.length} candidate${bulkSelectedIds.length === 1 ? "" : "s"} removed from Review Board.`, tone: "success" });
      await loadData("refresh");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to remove selected candidates";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setMutating(false);
      setBulkDialog(null);
    }
    });
  }

  async function confirmBulkDialog() {
    if (!bulkDialog || bulkSelectedIds.length === 0) return;
    if (bulkDialog === "remove") {
      await bulkRemoveSelected();
      return;
    }
    await updateCandidateStatuses(bulkSelectedIds, "REJECTED");
    setSelectedIds(new Set());
    setBulkDialog(null);
  }

  async function bulkApproveSelected() {
    if (bulkSelectedIds.length === 0) return;
    await updateCandidateStatuses(bulkSelectedIds, "APPROVED");
    setSelectedIds(new Set());
  }

  async function bulkLaterSelected() {
    if (bulkSelectedIds.length === 0) return;
    await updateCandidateStatuses(bulkSelectedIds, "IN_REVIEW");
    setSelectedIds(new Set());
  }

  async function sendCandidatesToReupQueue(
    ids: string[],
    pendingKey = ids.length === 1 ? candidateActionKey(ids[0], "send") : "bulk:send"
  ) {
    const approvedIds = approvedCandidatesFromIds(candidatePool, ids);
    if (approvedIds.length === 0) {
      setError("Only approved candidates can be sent to Reup Queue. Approve first, then use Send to queue.");
      return;
    }
    await asyncActions.run(pendingKey, async () => {
    setMutating(true);
    setError(null);
    try {
      const result = await enqueueReupCandidates({
        candidate_ids: approvedIds,
        queued_reason: "review_board_approved"
      });
      const queuedIds = [...approvedIds];
      setCandidates((current) => applyQueuedMembershipToCandidates(current, queuedIds, result.items));
      setCandidateDetails((current) => {
        const next = { ...current };
        for (const id of queuedIds) {
          if (next[id]) {
            next[id] = applyQueuedMembershipToCandidates([next[id]], [id], result.items)[0];
          }
        }
        return next;
      });
      notify({ message: formatReupQueueEnqueueNotice(result), tone: "success" });
      if (result.queued_count > 0 || result.already_queued_count > 0) {
        setSelectedIds((current) => {
          const next = new Set(current);
          for (const id of approvedIds) next.delete(id);
          return next;
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to send candidates to Reup Queue";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setMutating(false);
    }
    });
  }

  async function bulkSendApprovedToReupQueue() {
    if (bulkApprovedQueueIds.length === 0) return;
    await sendCandidatesToReupQueue(bulkApprovedQueueIds);
  }

  async function approveAndSendCandidatesToReupQueue(
    ids: string[],
    pendingKey = ids.length === 1 ? candidateActionKey(ids[0], "approve-and-send") : "bulk:approve-and-send"
  ) {
    if (ids.length === 0) return;
    const knownIds = ids.filter((id) => {
      const candidate = candidatePool.find((entry) => entry.id === id);
      return candidate ? !isCandidateInReupQueue(candidate) : false;
    });
    if (knownIds.length === 0) return;
    const pendingApproval = candidatesPendingApproval(candidatePool, knownIds);
    await asyncActions.run(pendingKey, async () => {
    setMutating(true);
    setError(null);
    try {
      if (pendingApproval.length > 0) {
        await bulkUpdateCandidateStatus(pendingApproval, "APPROVED");
        setCandidates((current) => applyCandidateStatusUpdate(current, pendingApproval, "APPROVED"));
        setCandidateDetails((current) => {
          const next = { ...current };
          for (const id of pendingApproval) {
            if (next[id]) next[id] = { ...next[id], status: "APPROVED" };
          }
          return next;
        });
        setStarredIds((current) => removeStars(current, pendingApproval));
      }
      const result = await enqueueReupCandidates({
        candidate_ids: knownIds,
        queued_reason: "review_board_approved"
      });
      setCandidates((current) => applyQueuedMembershipToCandidates(current, knownIds, result.items));
      setCandidateDetails((current) => {
        const next = { ...current };
        for (const id of knownIds) {
          if (next[id]) {
            next[id] = applyQueuedMembershipToCandidates([next[id]], [id], result.items)[0];
          }
        }
        return next;
      });
      notify({ message: formatApproveAndEnqueueNotice(pendingApproval.length, result), tone: "success" });
      await loadData("refresh");
      if (result.queued_count > 0 || result.already_queued_count > 0) {
        setSelectedIds((current) => {
          const next = new Set(current);
          for (const id of knownIds) next.delete(id);
          return next;
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to approve and send candidates to Reup Queue";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setMutating(false);
    }
    });
  }

  async function bulkApproveAndSendToReupQueue() {
    if (bulkSelectedIds.length === 0) return;
    await approveAndSendCandidatesToReupQueue(bulkSelectedIds);
  }

  async function approveBestAmongStarred() {
    if (starredIds.length === 0) return;
    const bestId = pickBestBenchCandidateId(starredCandidates, starredIds);
    if (!bestId) return;
    const { approveId, rejectIds } = splitApproveBestTargets(starredIds, bestId);
    setMutating(true);
    setError(null);
    try {
      if (rejectIds.length > 0) await bulkUpdateCandidateStatus(rejectIds, "REJECTED");
      await bulkUpdateCandidateStatus([approveId], "APPROVED");
      setCandidates((current) => applyCandidateStatusUpdate(applyCandidateStatusUpdate(current, rejectIds, "REJECTED"), [approveId], "APPROVED"));
      setStarredIds([]);
      setCompareOpen(false);
      notify({ message: `Approved best finalist (${formatReupScoreBadgeValue(reviewCandidateDisplayScore(candidateDetails[approveId] ?? visible.find((c) => c.id === approveId) ?? null))}).`, tone: "success" });
      await loadData("refresh");
    } catch (err) {
      const message = err instanceof Error ? err.message : t("reviewBoardPage.updateError");
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setMutating(false);
    }
  }

  function openInspector(candidateId: string) {
    setActiveCandidateId(candidateId);
    setRightInspectorOpen(true);
  }

  function applyFilters() {
    const search = filters.search.trim();
    setAppliedFilters({ ...filters, status: search ? "" : filters.status });
    if (search) {
      setFilters((current) => ({ ...current, status: "" }));
    }
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
    setAppliedFilters(DEFAULT_FILTERS);
  }

  function selectReviewStatus(status: ReviewFilterKey) {
    setPendingStatus(status);
    startStatusTransition(() => {
      setFilters((current) => ({ ...current, status }));
      setAppliedFilters((current) => ({ ...current, status }));
    });
  }

  const primaryActions = (
    <TopbarRefreshButton busy={refreshing} disabled={loading} onClick={() => void loadData("refresh")} />
  );

  return (
    <OperatorStudioShell actions={primaryActions} description="Triage shortlisted clips in a Capture Inbox-style studio and approve reup picks." title={t("reviewBoardPage.pageTitle")}>
      <OpsConsolePage>
        {refreshing ? <p className="review-board-refreshing-banner" role="status">Refreshing candidates…</p> : null}
        <ReviewStudioCommandDeck
          activeFilter={pendingStatus ?? effectiveStatus}
          approvedQueueCount={bulkApprovedQueueIds.length}
          filters={filters}
          mutating={mutating}
          onApply={applyFilters}
          onApprove={() => void bulkApproveSelected()}
          onApproveAndSend={() => void bulkApproveAndSendToReupQueue()}
          onChange={setFilters}
          onClear={() => setSelectedIds(new Set())}
          onFilter={selectReviewStatus}
          onLater={() => void bulkLaterSelected()}
          onReject={() => setBulkDialog("reject")}
          onRemove={() => setBulkDialog("remove")}
          onReset={resetFilters}
          onSendToQueue={() => void bulkSendApprovedToReupQueue()}
          onToggleScoreRange={() => setScoreRangeOpen((open) => !open)}
          pendingKey={asyncActions.pendingKey}
          scoreRangeOpen={scoreRangeOpen}
          selectedCount={bulkSelectedIds.length}
          summary={summary}
        />
        <div className="capture-inbox-review-workspace review-board-studio-workspace" data-review-board-ui-version={UI_VERSION}>
          <main className="capture-inbox-review-main" aria-busy={loading || refreshing} aria-label="Review Board candidate gallery" data-review-board-studio={UI_VERSION}>
            <AsyncContentBoundary
              emptyState={(
                <WorkGalleryEmptyState
                  action={(
                    <a className="review-board-empty-capture-link" href="/ops/extensions/douyin/capture-inbox">
                      <WorkItemActionIcon className="review-board-empty-capture-link__icon" kind="open" />
                      <span>Open Capture Inbox</span>
                    </a>
                  )}
                  className="review-board-gallery-empty"
                  detail={appliedFilters.search.trim()
                    ? "No candidates match this video ID or search text. Promote from Capture Inbox or try Open candidate on a promoted tile."
                    : "Promote ready videos from Capture Inbox to populate Review Board."}
                  title={appliedFilters.search.trim() ? "No search matches" : "No candidates in Review Board"}
                />
              )}
              errorState={<WorkGalleryEmptyState action={<button onClick={() => void loadData("filter")} type="button">Retry</button>} className="review-board-gallery-empty" detail={error ?? "Unknown error"} eyebrow="Review unavailable" title="Could not load candidates" />}
              refreshing={refreshing}
              skeleton={<WorkGalleryEmptyState className="review-board-gallery-empty" detail="Fetching candidates and score metadata." loading title="Loading candidates…" />}
              status={loading && candidates.length === 0 ? "loading" : error && candidates.length === 0 ? "error" : candidates.length === 0 ? "empty" : "success"}
            >
            {compareOpen && canOpenCompare(starredIds) ? (
              <section className="operator-panel review-board-compare-strip" aria-label="Finalist comparison">
                <div className="review-board-compare-strip-toolbar">
                  <strong>Compare finalists ({starredIds.length})</strong>
                  <div className="actions-row">
                    <button className="primary" disabled={mutating} onClick={() => void approveBestAmongStarred()} type="button">Approve best</button>
                    <button onClick={() => setCompareOpen(false)} type="button">Close</button>
                  </div>
                </div>
                <div className="capture-inbox-media-tile-grid review-board-compare-tile-grid">
                  {starredCandidates.map((candidate) => (
                    <CandidateMediaTile
                      candidate={candidate}
                      focused={activeCandidateId === candidate.id}
                      key={candidate.id}
                      mutating={Boolean(candidatePendingAction(candidate.id))}
                      onApprove={() => void updateCandidateStatuses([candidate.id], "APPROVED")}
                      onApproveAndSend={() => void approveAndSendCandidatesToReupQueue([candidate.id])}
                      onDetails={() => openInspector(candidate.id)}
                      onLater={() => void updateCandidateStatuses([candidate.id], "IN_REVIEW")}
                      onReject={() => void updateCandidateStatuses([candidate.id], "REJECTED")}
                      onSendToQueue={() => void sendCandidatesToReupQueue([candidate.id])}
                      onToggleSelect={() => {}}
                      pendingAction={candidatePendingAction(candidate.id)}
                      routePath={pathname}
                      selected={false}
                      showSelect={false}
                    />
                  ))}
                </div>
              </section>
            ) : null}
            {starredIds.length >= 2 && !compareOpen ? (
              <div className="review-board-compare-launch">
                <button onClick={() => setCompareOpen(true)} type="button">Compare {starredIds.length} starred finalists</button>
              </div>
            ) : null}

            {!loading && !isStatusPending && displayVisible.length === 0 && candidates.length > 0 ? (
              <WorkGalleryEmptyState
                action={filters.status === "APPROVED" && queuedInViewCount > 0 ? (
                  <button onClick={() => setShowQueuedInApproved(true)} type="button">Show {queuedInViewCount} in queue</button>
                ) : undefined}
                className="review-board-gallery-empty"
                detail={filters.status === "APPROVED" && queuedInViewCount > 0 ? "Approved clips already in Reup Queue are hidden by default." : "Try another status tab or reset filters."}
                eyebrow="Filtered view"
                title={filters.status === "APPROVED" && queuedInViewCount > 0 ? "All approved clips are already in Reup Queue" : "No candidates in this view"}
              />
            ) : null}

            {displayVisible.length > 0 || isStatusPending ? (
              <section
                aria-busy={isStatusPending}
                aria-label="Candidate tile gallery"
                className={`operator-panel capture-inbox-media-gallery review-board-candidate-gallery${isStatusPending ? " is-preloading" : ""}`}
              >
                <WorkGalleryHeader
                  actions={(
                    <div className="review-board-gallery-actions">
                      {filters.status === "APPROVED" && queuedInViewCount > 0 ? (
                        <button className="review-board-show-queued-toggle" onClick={() => setShowQueuedInApproved((current) => !current)} type="button">
                          {showQueuedInApproved ? "Hide in queue" : `Show in queue (${queuedInViewCount})`}
                        </button>
                      ) : null}
                      <button
                        className="review-board-deck-btn review-board-gallery-select-visible"
                        disabled={mutating || isStatusPending}
                        onClick={() => setSelectedIds(selectAllOnPage(selectableVisible))}
                        type="button"
                      >
                        <WorkItemActionIcon className="review-board-gallery-action__icon" kind="select-visible" />
                        Select visible ({selectableVisible.length})
                      </button>
                    </div>
                  )}
                  meta={isStatusPending ? `Preparing ${pendingStatusLabel} candidates…` : `${displayVisible.length.toLocaleString()} shown · ${totalCount.toLocaleString()} total`}
                  title="Candidate tiles"
                />
                {isStatusPending ? (
                  <ReviewGalleryPreloading statusLabel={pendingStatusLabel} />
                ) : (
                  <>
                    <div className="capture-inbox-media-tile-grid">
                      {displayVisible.map((candidate) => {
                        const detail = candidateDetails[candidate.id] ?? candidate;
                        return (
                          <CandidateMediaTile
                            candidate={detail}
                            focused={activeCandidateId === candidate.id}
                            key={candidate.id}
                            mutating={Boolean(candidatePendingAction(candidate.id))}
                            onApprove={() => void updateCandidateStatuses([candidate.id], "APPROVED")}
                            onApproveAndSend={() => void approveAndSendCandidatesToReupQueue([candidate.id])}
                            onDetails={() => openInspector(candidate.id)}
                            onLater={() => void updateCandidateStatuses([candidate.id], "IN_REVIEW")}
                            onReject={() => void updateCandidateStatuses([candidate.id], "REJECTED")}
                            onSendToQueue={() => void sendCandidatesToReupQueue([candidate.id])}
                            onToggleSelect={() => setSelectedIds((current) => toggleSelection(current, candidate.id))}
                            pendingAction={candidatePendingAction(candidate.id)}
                            routePath={pathname}
                            selected={selectedIds.has(candidate.id)}
                            showSelect={!isCandidateInReupQueue(detail)}
                          />
                        );
                      })}
                    </div>
                  </>
                )}
                {hasMoreCandidates || totalCount > 0 ? (
                  <OffsetLoadMoreFooter
                    ref={loadMoreRef}
                    autoLoad
                    disabled={mutating || isStatusPending}
                    loadedCount={candidates.length}
                    loadingMore={loadingMore}
                    noun={footerCandidateNoun}
                    onLoadMore={loadMoreCandidates}
                    pageSize={CANDIDATE_PAGE_SIZE}
                    totalCount={totalCount}
                    variant="studio"
                  />
                ) : null}
              </section>
            ) : null}
            </AsyncContentBoundary>
          </main>
        </div>
        <ReviewRightInspector
          candidate={activeCandidate}
          mutating={activeCandidate ? Boolean(candidatePendingAction(activeCandidate.id)) : false}
          onApprove={(candidate) => void updateCandidateStatuses([candidate.id], "APPROVED")}
          onApproveAndSend={(candidate) => void approveAndSendCandidatesToReupQueue([candidate.id])}
          onClose={closeInspector}
          onLater={(candidate) => void updateCandidateStatuses([candidate.id], "IN_REVIEW")}
          onReject={(candidate) => void updateCandidateStatuses([candidate.id], "REJECTED")}
          onSendToQueue={(candidate) => void sendCandidatesToReupQueue([candidate.id])}
          open={rightInspectorOpen && Boolean(activeCandidate)}
          pendingAction={activeCandidate ? candidatePendingAction(activeCandidate.id) : null}
        />
        <ReviewBulkDialog
          action={bulkDialog}
          count={bulkSelectedIds.length}
          mutating={mutating}
          onClose={() => setBulkDialog(null)}
          onConfirm={() => void confirmBulkDialog()}
        />
      </OpsConsolePage>
    </OperatorStudioShell>
  );
}

function ReviewGalleryPreloading({ statusLabel }: { statusLabel: string }) {
  return (
    <div className="review-board-gallery-preloading" role="status" aria-live="polite">
      <div className="review-board-gallery-preloading__status">
        <span aria-hidden="true" className="review-board-gallery-preloading__spinner" />
        <span className="review-board-gallery-preloading__copy">
          <strong>Preparing {statusLabel} candidates</strong>
          <span>Building the tile view and preserving your current position…</span>
        </span>
      </div>
      <div aria-hidden="true" className="review-board-gallery-preloading__grid">
        {Array.from({ length: 8 }, (_, index) => (
          <span className="review-board-gallery-preloading__tile" key={index}>
            <span className="review-board-gallery-preloading__media" />
            <span className="review-board-gallery-preloading__line is-title" />
            <span className="review-board-gallery-preloading__line is-meta" />
            <span className="review-board-gallery-preloading__pills">
              <span />
              <span />
              <span />
              <span />
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ReviewStudioCommandDeck({
  activeFilter,
  approvedQueueCount,
  filters,
  mutating,
  onApply,
  onApprove,
  onApproveAndSend,
  onChange,
  onClear,
  onFilter,
  onLater,
  onReject,
  onRemove,
  onReset,
  onSendToQueue,
  onToggleScoreRange,
  pendingKey,
  scoreRangeOpen,
  selectedCount,
  summary
}: {
  activeFilter: ReviewFilterKey;
  approvedQueueCount: number;
  filters: CandidateFilters;
  mutating: boolean;
  onApply: () => void;
  onApprove: () => void;
  onApproveAndSend: () => void;
  onChange: (filters: CandidateFilters) => void;
  onClear: () => void;
  onFilter: (filter: ReviewFilterKey) => void;
  onLater: () => void;
  onReject: () => void;
  onRemove: () => void;
  onReset: () => void;
  onSendToQueue: () => void;
  onToggleScoreRange: () => void;
  pendingKey?: string;
  scoreRangeOpen: boolean;
  selectedCount: number;
  summary: ReviewSummary;
}) {
  const hasSelection = selectedCount > 0;
  const disabled = mutating;

  function update(partial: Partial<CandidateFilters>) {
    onChange({ ...filters, ...partial });
  }

  return (
    <>
      <WorkStudioDeck
        actions={(
          <div className="capture-inbox-hero-action-rail review-board-hero-action-rail" aria-label="Review shortcuts" role="group">
            <a className="capture-inbox-hero-action-rail__item" href="/selection/reup-queue">
              <span aria-hidden="true" className="capture-inbox-hero-action-rail__icon">
                <WorkItemActionIcon className="capture-inbox-hero-action-rail__glyph" kind="open" />
              </span>
              <span className="capture-inbox-hero-action-rail__label">Open Reup Queue</span>
            </a>
          </div>
        )}
        ariaLabel="Review Board studio controls"
        className={`review-board-command-deck ${hasSelection ? "has-selection" : ""}`}
        kicker="Review studio"
      >
        <ReviewStatusFlow activeFilter={activeFilter} onFilter={onFilter} summary={summary} />
      </WorkStudioDeck>

      <section className="work-studio-filter-deck review-board-filter-deck capture-inbox-gallery-filter-deck" aria-label="Review filters">
        <div className="work-studio-filter-deck__header">
          <div className="work-studio-filter-deck__copy">
            <span className="work-studio-filter-deck__kicker">Tile filters</span>
            <span className="work-studio-filter-deck__title">Search, rank, and focus candidates</span>
          </div>
          <span className="review-board-filter-deck__hint">Refine the current pipeline view</span>
        </div>
        <div className="work-studio-filter-deck__query review-board-command-deck-filters">
          <label className="review-board-filter-control is-search">
            <span aria-hidden="true" className="review-board-filter-search-icon">
              <svg viewBox="0 0 24 24">
                <path d="m20 20-4.4-4.4m2.4-5.1a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
              </svg>
            </span>
            <span className="capture-inbox-sr-only">Search candidates</span>
            <input
              aria-label="Search Review Board candidates"
              className="review-board-deck-input review-board-deck-search"
              onChange={(event) => update({ search: event.target.value })}
              placeholder="Search video ID, caption, profile, URL…"
              type="search"
              value={filters.search}
            />
          </label>
          <label className="review-board-filter-control is-sort">
            <span className="review-board-filter-control__label">Sort by</span>
            <select
              aria-label="Sort Review Board candidates"
              className="review-board-deck-input review-board-deck-sort"
              onChange={(event) => update({ sort: event.target.value as CandidateFilters["sort"] })}
              value={filters.sort}
            >
              <option value="score_desc">Reup Score</option>
              <option value="newest_first">Newest</option>
              <option value="views_desc">Est. Views</option>
            </select>
          </label>
          <div className="review-board-command-deck-filter-actions">
            <button aria-expanded={scoreRangeOpen} className={`review-board-deck-btn is-score-toggle ${scoreRangeOpen ? "is-active" : ""}`} onClick={onToggleScoreRange} type="button">
              <WorkItemActionIcon className="review-board-filter-action__icon" kind="details" />
              Score range
            </button>
            <button className="review-board-deck-btn is-primary" onClick={onApply} type="button">
              <WorkItemActionIcon className="review-board-filter-action__icon" kind="approve" />
              Apply filters
            </button>
            <button className="review-board-deck-btn is-ghost" onClick={onReset} type="button">
              <WorkItemActionIcon className="review-board-filter-action__icon" kind="retry" />
              Reset
            </button>
          </div>
        </div>
        {scoreRangeOpen ? (
          <div className="review-board-score-range">
            <span className="review-board-score-range__title">Score range</span>
            <label className="review-board-score-range__field">
              <span>Minimum</span>
              <input aria-label="Minimum score" className="review-board-deck-input review-board-deck-score" max="100" min="0" onChange={(event) => update({ minScore: event.target.value })} placeholder="0" type="number" value={filters.minScore} />
            </label>
            <span aria-hidden="true" className="review-board-score-range__separator">to</span>
            <label className="review-board-score-range__field">
              <span>Maximum</span>
              <input aria-label="Maximum score" className="review-board-deck-input review-board-deck-score" max="100" min="0" onChange={(event) => update({ maxScore: event.target.value })} placeholder="100" type="number" value={filters.maxScore} />
            </label>
          </div>
        ) : null}
      </section>

      {hasSelection ? (
        <WorkBulkActionBar
          active
          ariaLabel="Bulk actions"
          className="review-board-command-deck-bulk review-board-bulk-command-bar"
          guidance="Fast path: Approve & send to Reup Queue"
          selectedCount={selectedCount}
          toolbar={(
            <button className="review-board-deck-btn is-ghost" disabled={disabled} onClick={onClear} type="button">
              <WorkItemActionIcon className="review-board-bulk-action__icon" kind="clear-selection" />
              Clear
            </button>
          )}
        >
          <>
            <AsyncButton className="review-board-deck-btn is-primary" disabled={disabled} leadingIcon={<WorkItemActionIcon className="review-board-bulk-action__icon" kind="send" />} onClick={onApproveAndSend} pending={pendingKey === "bulk:approve-and-send"} pendingLabel="Sending…" title="Approve selected candidates and send to Reup Queue" type="button">
              Approve &amp; send ({selectedCount})
            </AsyncButton>
            <AsyncButton className="review-board-deck-btn" disabled={disabled} leadingIcon={<WorkItemActionIcon className="review-board-bulk-action__icon" kind="approve" />} onClick={onApprove} pending={pendingKey === "bulk:approved"} pendingLabel="Approving…" title="Approve selected candidates without queueing" type="button">
              Approve
            </AsyncButton>
            <AsyncButton className="review-board-deck-btn is-accent" disabled={disabled || approvedQueueCount === 0} leadingIcon={<WorkItemActionIcon className="review-board-bulk-action__icon" kind="send" />} onClick={onSendToQueue} pending={pendingKey === "bulk:send"} pendingLabel="Queueing…" title="Send already-approved selections to Reup Queue" type="button">
              Queue{approvedQueueCount > 0 ? ` (${approvedQueueCount})` : ""}
            </AsyncButton>
            <AsyncButton className="review-board-deck-btn" disabled={disabled} leadingIcon={<WorkItemActionIcon className="review-board-bulk-action__icon" kind="later" />} onClick={onLater} pending={pendingKey === "bulk:in_review"} pendingLabel="Updating…" title="Mark selected as in review" type="button">
              Later
            </AsyncButton>
            <button className="review-board-deck-btn is-danger" disabled={disabled} onClick={onReject} title="Reject selected candidates" type="button">
              <WorkItemActionIcon className="review-board-bulk-action__icon" kind="reject" />
              Reject
            </button>
            <button className="review-board-deck-btn is-link" disabled={disabled} onClick={onRemove} title="Remove selected from Review Board" type="button">
              <WorkItemActionIcon className="review-board-bulk-action__icon" kind="delete" />
              Remove from board
            </button>
          </>
        </WorkBulkActionBar>
      ) : null}
    </>
  );
}

function ReviewStatusStatBars({ ratio, status }: { ratio: number; status: ReviewFilterKey }) {
  const pattern = REVIEW_STATUS_STAT_BAR_PATTERNS[status] ?? REVIEW_STATUS_STAT_BAR_PATTERNS[""]!;
  const clamped = Math.max(0, Math.min(1, ratio));
  const displayRatio = clamped > 0 ? clamped : 0.16;
  return (
    <span aria-hidden="true" className="capture-inbox-stat-card__viz" data-status={status || "all"}>
      {pattern.map((slot, index) => (
        <span className="capture-inbox-stat-card__bar" key={index}>
          <span className="capture-inbox-stat-card__bar-fill" style={{ height: `${Math.round(slot * displayRatio * 100)}%` }} />
        </span>
      ))}
    </span>
  );
}

function ReviewStatusFlow({ activeFilter, onFilter, summary }: { activeFilter: ReviewFilterKey; onFilter: (filter: ReviewFilterKey) => void; summary: ReviewSummary }) {
  function renderCard(entry: { key: ReviewFilterKey; label: string }, variant: "pipeline" | "attention") {
    const count = reviewSummaryValue(summary, entry.key);
    const active = activeFilter === entry.key;
    const ratio = entry.key === "" ? 1 : summary.total > 0 ? count / summary.total : 0;
    return (
      <button
        aria-pressed={active}
        className={`capture-inbox-stat-card is-${variant} is-tone-${reviewBoardFilterTone(entry.key, count)}${count === 0 ? " is-empty" : ""}${active ? " is-active" : ""}`}
        key={entry.key || "all"}
        onClick={() => onFilter(entry.key)}
        role="tab"
        type="button"
      >
        <span className="capture-inbox-stat-card__copy">
          <span className="capture-inbox-stat-card__label">{entry.label}</span>
          <strong className="capture-inbox-stat-card__value">{count}</strong>
        </span>
        <ReviewStatusStatBars ratio={ratio} status={entry.key} />
      </button>
    );
  }

  return (
    <section className="capture-inbox-status-flow review-board-status-flow" aria-label="Review Board status flow">
      <div className="capture-inbox-status-flow__lane is-pipeline">
        <div className="capture-inbox-status-flow__lane-head">
          <p className="capture-inbox-status-flow__lane-title">Pipeline</p>
          <p className="capture-inbox-status-flow__lane-meta">Candidate decisions</p>
        </div>
        <div className="capture-inbox-status-flow__track" role="tablist">{REVIEW_STATUS_FILTERS.map((entry) => renderCard(entry, entry.key === "REJECTED" ? "attention" : "pipeline"))}</div>
      </div>
    </section>
  );
}

function ReviewBulkDialog({ action, count, mutating, onClose, onConfirm }: { action: ReviewBulkAction | null; count: number; mutating: boolean; onClose: () => void; onConfirm: () => void }) {
  if (!action) return null;
  const isRemove = action === "remove";
  const title = isRemove ? "Remove from Review Board?" : "Reject selected candidates?";
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") onClose();
  };
  return (
    <div className="capture-inbox-bulk-dialog-backdrop review-board-bulk-dialog-backdrop" onClick={onClose} onKeyDown={onKeyDown} role="presentation">
      <section
        aria-labelledby="review-board-bulk-dialog-title"
        aria-modal="true"
        className="capture-inbox-bulk-dialog review-board-bulk-dialog"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        tabIndex={-1}
      >
        <h2 id="review-board-bulk-dialog-title">{title}</h2>
        <p>
          {isRemove
            ? <>Remove <strong>{count}</strong> candidate{count === 1 ? "" : "s"} from this Review Board view.</>
            : <>Reject <strong>{count}</strong> candidate{count === 1 ? "" : "s"} in the current view.</>}
        </p>
        {isRemove ? (
          <p className="capture-inbox-bulk-dialog-danger">Source media and upstream capture records are not deleted — only the Review Board candidate rows.</p>
        ) : (
          <p className="capture-inbox-bulk-dialog-muted">Rejected clips stay in the board under the Rejected tab for audit.</p>
        )}
        <div className="review-board-bulk-dialog-actions">
          <button className="capture-inbox-command-bar-clear" disabled={mutating} onClick={onClose} type="button">Cancel</button>
          <button className="danger" disabled={mutating} onClick={onConfirm} type="button">{mutating ? "Working..." : isRemove ? "Remove" : "Reject"}</button>
        </div>
      </section>
    </div>
  );
}

function CandidateMediaTile({
  candidate,
  focused,
  mutating,
  onApprove,
  onApproveAndSend,
  onDetails,
  onLater,
  onReject,
  onSendToQueue,
  onToggleSelect,
  pendingAction,
  routePath,
  selected,
  showSelect
}: {
  candidate: Candidate;
  focused: boolean;
  mutating: boolean;
  onApprove: () => void;
  onApproveAndSend: () => void;
  onDetails: () => void;
  onLater: () => void;
  onReject: () => void;
  onSendToQueue: () => void;
  onToggleSelect: () => void;
  pendingAction: string | null;
  routePath: string;
  selected: boolean;
  showSelect: boolean;
}) {
  const metadata = getReviewCandidateMetadata(candidate);
  const title = candidateTitle(candidate);
  const scoreBadge = useReviewCandidateTileScoreBadge(candidate);
  const thumbnailUrl = metadata.thumbnailUrl;
  const inReupQueue = isCandidateInReupQueue(candidate);
  const perfStats = reviewTilePerfStats(metadata);
  return (
    <article className={`capture-inbox-media-tile capture-inbox-compact-card review-board-media-tile ${selected ? "is-bulk-selected" : ""} ${focused ? "is-inspector-focused" : ""} ${inReupQueue ? "is-in-reup-queue" : ""}`}>
      <div className="capture-inbox-media-frame">
        <button className="capture-inbox-media-thumbnail" onClick={onDetails} type="button">
          {thumbnailUrl ? <img alt={`Thumbnail for ${title}`} src={thumbnailUrl} /> : <span className="capture-inbox-thumbnail-placeholder"><strong>No thumbnail</strong></span>}
        </button>
        <WorkMediaTileOverlay
          onToggleSelect={onToggleSelect}
          scoreBadge={scoreBadge}
          selectAriaLabel={selected ? "Deselect candidate" : "Select candidate"}
          selectTitle={selected ? "Deselect for bulk actions" : "Select for bulk actions"}
          selectable={showSelect}
          selected={selected}
          statusChips={[
            { label: candidateStatusLabel(candidate.status), tone: reviewBoardStatusTone(candidate.status) },
          ]}
        />
      </div>
      <div className="capture-inbox-tile-main capture-inbox-compact-main">
        <button className="link-button capture-inbox-tile-title" onClick={onDetails} title={title} type="button">{title}</button>
        <div className="capture-inbox-tile-stats">
          <p className="capture-inbox-tile-meta-line" aria-label="Duration and posted">
            <span className="capture-inbox-tile-meta-stat" title={`Duration: ${metadata.durationText ?? "Not captured"}`}>
              <span aria-hidden="true" className="capture-inbox-tile-perf-stat-icon">
                <CaptureInboxFilterChipIcon className="capture-inbox-tile-perf-stat-icon__glyph" kind="stat-duration" />
              </span>
              <span className="capture-inbox-tile-meta-copy">
                <span className="capture-inbox-tile-meta-label">Duration</span>
                <span className="capture-inbox-tile-meta-value">{metadata.durationText ?? "—"}</span>
              </span>
            </span>
            <span className="capture-inbox-tile-meta-stat" title={`Posted: ${formatReviewPostedLabel(metadata)}`}>
              <span aria-hidden="true" className="capture-inbox-tile-perf-stat-icon">
                <CaptureInboxFilterChipIcon className="capture-inbox-tile-perf-stat-icon__glyph" kind="stat-posted" />
              </span>
              <span className="capture-inbox-tile-meta-copy">
                <span className="capture-inbox-tile-meta-label">Posted</span>
                <span className="capture-inbox-tile-meta-value">{formatReviewPostedLabel(metadata)}</span>
              </span>
            </span>
          </p>
          <div className="capture-inbox-tile-perf-rail" aria-label="Performance">
            {perfStats.map((stat) => (
              <span className="capture-inbox-tile-perf-stat" key={stat.label} title={`${stat.label}: ${stat.value}`}>
                <span aria-hidden="true" className="capture-inbox-tile-perf-stat-icon">
                  <CaptureInboxFilterChipIcon className="capture-inbox-tile-perf-stat-icon__glyph" kind={stat.icon} />
                </span>
                <span className="capture-inbox-tile-perf-stat-value">{stat.value}</span>
                <span className="capture-inbox-sr-only">{stat.label}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="capture-inbox-tile-footer capture-inbox-compact-actions">
        <ReviewBoardTileActions
          candidate={candidate}
          mutating={mutating}
          onApprove={onApprove}
          onApproveAndSend={onApproveAndSend}
          onLater={onLater}
          pendingAction={pendingAction}
          onReject={onReject}
          onSendToQueue={onSendToQueue}
        />
      </div>
      {process.env.NODE_ENV !== "production" ? <span hidden data-review-board-trace-version={UI_VERSION} data-review-candidate-debug={JSON.stringify(reviewCandidateVisibleDebug(candidate, metadata, routePath))} /> : null}
    </article>
  );
}

function reviewCandidateScoreBadge(candidate: Candidate) {
  const score = reviewCandidateDisplayScore(candidate);
  const level = reupScoreBadgeLevelForCaptureItem(
    score,
    getDouyinMetadataCompletenessForItem(buildCapturedItemFromReviewCandidate(candidate))
  );
  return { score, level };
}

function ReviewRightInspector({
  candidate,
  mutating,
  onApprove,
  onApproveAndSend,
  onClose,
  onLater,
  onReject,
  onSendToQueue,
  open,
  pendingAction
}: {
  candidate: Candidate | null;
  mutating: boolean;
  onApprove: (candidate: Candidate) => void;
  onApproveAndSend: (candidate: Candidate) => void;
  onClose: () => void;
  onLater: (candidate: Candidate) => void;
  onReject: (candidate: Candidate) => void;
  onSendToQueue: (candidate: Candidate) => void;
  open: boolean;
  pendingAction: string | null;
}) {
  const metadata = candidate ? getReviewCandidateMetadata(candidate) : null;
  const scoreBadge = candidate ? reviewCandidateScoreBadge(candidate) : null;
  const inReupQueue = candidate ? isCandidateInReupQueue(candidate) : false;
  const inspectorStats: Array<{ icon: CaptureInboxFilterChipIconKind; label: string; value: string }> = metadata ? [
    { icon: "meta-posted", label: "Posted", value: formatReviewPostedLabel(metadata) },
    { icon: "meta-duration", label: "Duration", value: metadata.durationText ?? "—" },
    { icon: "perf-views", label: "Est. Views", value: formatEstimatedViews(metadata) },
    { icon: "perf-engagement", label: "Likes", value: formatExactEngagementMetric(metadata.likeCount, metadata.likeCountText) },
    { icon: "stat-comments", label: "Comments", value: formatExactEngagementMetric(metadata.commentCount, metadata.commentCountText) },
    { icon: "stat-shares", label: "Shares", value: formatExactEngagementMetric(metadata.shareCount, metadata.shareCountText) },
  ] : [];
  return (
    <WorkItemDetailsDrawer
      eyebrow="Review Board"
      footer={
        candidate ? (
          <div className="review-board-inspector-queue-actions">
            <ReviewBoardTileActions
              candidate={candidate}
              mutating={mutating}
              onApprove={() => onApprove(candidate)}
              onApproveAndSend={() => onApproveAndSend(candidate)}
              onLater={() => onLater(candidate)}
              pendingAction={pendingAction}
              onReject={() => onReject(candidate)}
              onSendToQueue={() => onSendToQueue(candidate)}
              variant="inspector"
            />
          </div>
        ) : null
      }
      open={open}
      title="Candidate details"
      titleId="review-board-details-title"
      onClose={onClose}
    >
      <div className="review-board-inspector">
        {candidate && metadata ? (
          <>
            <section className="review-board-inspector-summary-card" aria-label="Candidate summary">
              {metadata.thumbnailUrl ? (
                <div className="review-board-inspector-media">
                  <img alt={`Thumbnail for ${candidateTitle(candidate)}`} src={metadata.thumbnailUrl} />
                </div>
              ) : null}
              <div className="review-board-inspector-summary">
                <div className="review-board-inspector-summary-topline">
                <span className={`capture-inbox-reup-score-badge is-${scoreBadge?.level ?? "needs_metadata"} ${scoreBadge?.score == null ? "missing" : "ready"}`}>
                  <strong>{formatReupScoreBadgeValue(scoreBadge?.score)}</strong>
                  <small>{reupScoreBadgeTier(scoreBadge?.score)}</small>
                </span>
                  <div className="review-board-inspector-statuses">
                    <span className={`status-badge review-board-status-badge ${statusTone(candidate.status)}`}>{candidateStatusLabel(candidate.status)}</span>
                    {inReupQueue ? <span className="status-badge review-board-status-badge good">In Reup Queue</span> : null}
                  </div>
                </div>
                <p className="review-board-inspector-caption">{candidateTitle(candidate)}</p>
              </div>
            </section>
            <section className="review-board-inspector-metadata" aria-labelledby="review-board-inspector-metadata-title">
              <div className="review-board-inspector-section-heading">
                <div>
                  <span>Performance</span>
                  <h3 id="review-board-inspector-metadata-title">Core metadata</h3>
                </div>
                <small>Captured source values</small>
              </div>
              <div className="review-board-inspector-metadata-grid">
                {inspectorStats.map((stat) => (
                  <article className="review-board-inspector-stat" key={stat.label}>
                    <span aria-hidden="true" className="review-board-inspector-stat__icon">
                      <CaptureInboxFilterChipIcon kind={stat.icon} />
                    </span>
                    <span className="review-board-inspector-stat__copy">
                      <small>{stat.label}</small>
                      <strong>{stat.value}</strong>
                    </span>
                  </article>
                ))}
              </div>
            </section>
          </>
        ) : <p className="review-board-inspector-empty">Select a tile to inspect details.</p>}
      </div>
    </WorkItemDetailsDrawer>
  );
}

function candidateTitle(candidate: Candidate): string {
  return candidate.source_video?.caption ?? candidate.caption ?? candidate.title ?? `Candidate ${candidate.id.slice(0, 8)}`;
}

function reviewCandidateVisibleDebug(candidate: Candidate, metadata: ReviewCandidateMetadata, routePath: string) {
  return {
    traceVersion: UI_VERSION,
    routePath,
    apiEndpoint: "GET /candidates?view=summary",
    candidateId: candidate.id,
    awemeId: metadata.awemeId,
    visibleScore: reviewCandidateDisplayScore(candidate)
  };
}

function buildSummaryFromStatusCounts(
  statusCounts: Partial<Record<CandidateStatus, number>>
): ReviewSummary {
  return {
    total: Object.values(statusCounts).reduce((sum, count) => sum + (count ?? 0), 0),
    approved: statusCounts.APPROVED ?? 0,
    rejected: statusCounts.REJECTED ?? 0,
    inReview: statusCounts.IN_REVIEW ?? 0,
    newItems: statusCounts.NEW ?? 0,
    shortlisted: statusCounts.SHORTLISTED ?? 0
  };
}

function filterCandidatesByReviewStatus(candidates: Candidate[], status: ReviewFilterKey): Candidate[] {
  if (!status) return candidates;
  return candidates.filter((candidate) => normalizeReviewStatus(candidate) === status);
}

function normalizeReviewStatus(candidate: Candidate): CandidateStatus {
  if (candidate.status === "APPROVED" || candidate.decision_status === "APPROVED") return "APPROVED";
  if (candidate.status === "REJECTED" || candidate.decision_status === "REJECTED") return "REJECTED";
  if (candidate.status === "IN_REVIEW" || candidate.review_status === "IN_REVIEW") return "IN_REVIEW";
  if (candidate.status === "SHORTLISTED" || candidate.review_status === "SHORTLISTED") return "SHORTLISTED";
  return candidate.status === "ARCHIVED" ? "ARCHIVED" : "NEW";
}

function reviewSummaryValue(summary: ReviewSummary, key: ReviewFilterKey): number {
  if (key === "") return summary.total;
  if (key === "NEW") return summary.newItems;
  if (key === "SHORTLISTED") return summary.shortlisted;
  if (key === "IN_REVIEW") return summary.inReview;
  if (key === "APPROVED") return summary.approved;
  if (key === "REJECTED") return summary.rejected;
  return 0;
}

function formatEstimatedViews(metadata: ReviewCandidateMetadata): string {
  return formatReviewEstimatedViews(metadata);
}

function reviewTilePerfStats(metadata: ReviewCandidateMetadata): Array<{
  label: string;
  value: string;
  icon: CaptureInboxFilterChipIconKind;
}> {
  return [
    { label: "Estimated views", value: formatEstimatedViews(metadata), icon: "perf-views" },
    { label: "Likes", value: formatExactEngagementMetric(metadata.likeCount, metadata.likeCountText), icon: "perf-engagement" },
    { label: "Comments", value: formatExactEngagementMetric(metadata.commentCount, metadata.commentCountText), icon: "stat-comments" },
    { label: "Shares", value: formatExactEngagementMetric(metadata.shareCount, metadata.shareCountText), icon: "stat-shares" }
  ];
}

function formatNumber(value: number | null, empty = "—"): string {
  if (value == null) return empty;
  return new Intl.NumberFormat("en", { notation: value >= 10000 ? "compact" : "standard" }).format(value);
}

function mergeCandidatePool(candidates: Candidate[], details: Record<string, Candidate>): Candidate[] {
  const byId = new Map(candidates.map((candidate) => [candidate.id, candidate]));
  for (const candidate of Object.values(details)) {
    byId.set(candidate.id, candidate);
  }
  return [...byId.values()];
}

function reviewBoardFilterTone(filter: ReviewFilterKey, count: number): "good" | "warn" | "danger" | "muted" | "neutral" {
  if (count === 0) return "muted";
  if (filter === "REJECTED") return "danger";
  if (filter === "IN_REVIEW" || filter === "NEW") return "warn";
  if (filter === "SHORTLISTED" || filter === "APPROVED") return "good";
  return "neutral";
}

function reviewBoardStatusTone(status: CandidateStatus): "good" | "warn" | "danger" | "muted" {
  if (status === "APPROVED" || status === "SHORTLISTED") return "good";
  if (status === "IN_REVIEW" || status === "NEW") return "warn";
  if (status === "REJECTED") return "danger";
  return "muted";
}

function candidateStatusLabel(status: CandidateStatus): string {
  return status.toLowerCase().replace(/_/g, " ").replace(/^./, (letter) => letter.toUpperCase());
}
