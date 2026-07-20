"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useT } from "../../lib/i18n";
import { applyCandidatePreset, bulkUpdateCandidateStatus, deleteCandidate, enqueueReupCandidates, fetchCandidateDetail, fetchCandidates } from "../../lib/api";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { getDouyinMetadataCompletenessForItem } from "../../lib/captureInboxFilterMetadata";
import { buildCapturedItemFromReviewCandidate } from "../../lib/operatorReupScore";
import { formatReupScoreBadgeValue, reupScoreBadgeLevelForCaptureItem, reupScoreBadgeTier } from "../../lib/reupScoreBadge";
import { formatReviewEstimatedViews, formatReviewPostedLabel, getReviewCandidateMetadata, reviewCandidateDisplayScore, type ReviewCandidateMetadata } from "../../lib/reviewCandidateMetadata";
import { formatExactEngagementMetric } from "../../lib/captureInboxCanonical";
import { pickBestBenchCandidateId, splitApproveBestTargets } from "../../lib/reviewBoardBenchState";
import { canOpenCompare, removeStars, toggleCompareStar } from "../../lib/reviewBoardDecisionState";
import { approvedCandidatesFromIds, applyQueuedMembershipToCandidates, candidatesPendingApproval, formatApproveAndEnqueueNotice, formatReupQueueEnqueueNotice, isApprovedForReupQueue, isCandidateInReupQueue, selectableBoardCandidates } from "../../lib/reviewBoardQueueState";
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
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { OpsConsolePage, OpsDetailPanel, OpsDetailSection, OpsMetadataList, OpsStatePanel, statusTone } from "../ops-console/OpsShared";
import { OffsetLoadMoreFooter } from "../shared/OffsetLoadMoreFooter";
import { WorkItemDetailsDrawer } from "../shared/WorkItemDetailsDrawer";
import { WorkMediaTileOverlay } from "../shared/WorkMediaTileOverlay";
import { useOffsetLoadMoreOnScroll } from "../shared/useOffsetLoadMoreOnScroll";
import { getOperatorTileScoreBadge } from "../../lib/operatorTileScore";
import { hasMoreOffsetItems, resolveOffsetPageMerge } from "../../lib/offsetListPagination";

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

const SORT_LABELS: Record<CandidateFilters["sort"], string> = {
  score_desc: "Reup Score",
  newest_first: "Newest",
  views_desc: "Est. Views"
};

const UI_VERSION = "22F-7R";
const CANDIDATE_PAGE_SIZE = 200;

export function ReviewBoardPage() {
  const t = useT();
  const pathname = usePathname();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<CandidateFilters>(DEFAULT_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<CandidateFilters>(DEFAULT_FILTERS);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [totalCount, setTotalCount] = useState(0);
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
  const [notice, setNotice] = useState<string | null>(null);
  const [bulkDialog, setBulkDialog] = useState<ReviewBulkAction | null>(null);
  const [scoreRangeOpen, setScoreRangeOpen] = useState(false);
  const [showQueuedInApproved, setShowQueuedInApproved] = useState(false);

  const loadData = useCallback(async (intent: "initial" | "refresh" | "filter" = "filter") => {
    const preserveUi = intent === "refresh";
    if (preserveUi) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      if (!preserveUi && appliedFilters.presetName) {
        await applyCandidatePreset(appliedFilters);
      }
      const { candidates: nextCandidates, totalCount: nextTotalCount } = await fetchCandidates(appliedFilters, {
        limit: CANDIDATE_PAGE_SIZE,
        offset: 0
      });
      setCandidates(nextCandidates);
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
      setError(err instanceof Error ? err.message : t("reviewBoardPage.loadError"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [appliedFilters, t]);

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
      const { candidates: nextPage, totalCount: nextTotalCount } = await fetchCandidates(appliedFilters, {
        limit: CANDIDATE_PAGE_SIZE,
        offset: currentCandidates.length
      });
      const { merged, totalCount: resolvedTotalCount } = resolveOffsetPageMerge(
        currentCandidates,
        nextPage,
        nextTotalCount
      );
      setCandidates(merged);
      setTotalCount(resolvedTotalCount);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reviewBoardPage.loadError"));
    } finally {
      loadMoreInFlightRef.current = false;
      setLoadingMore(false);
    }
  }, [appliedFilters, loading, loadingMore, t, totalCount]);

  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  useOffsetLoadMoreOnScroll({
    sentinelRef: loadMoreRef,
    hasMore: hasMoreCandidates,
    loading: loadingMore,
    disabled: mutating || loading,
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
  const serverSearchActive = appliedFilters.search.trim().length > 0;

  const statusSummaryBase = useMemo(
    () => visibleCandidates(candidates, { ...filters, status: "" }, { serverSearch: serverSearchActive }),
    [candidates, filters, serverSearchActive]
  );
  const visible = useMemo(() => filterCandidatesByReviewStatus(statusSummaryBase, effectiveStatus), [effectiveStatus, statusSummaryBase]);
  const queuedInViewCount = useMemo(() => visible.filter((candidate) => isCandidateInReupQueue(candidate)).length, [visible]);
  const displayVisible = useMemo(() => {
    if (filters.status !== "APPROVED" || showQueuedInApproved) return visible;
    return visible.filter((candidate) => !isCandidateInReupQueue(candidate));
  }, [filters.status, showQueuedInApproved, visible]);
  const selectableVisible = useMemo(() => selectableBoardCandidates(displayVisible), [displayVisible]);
  const summary = useMemo(() => buildSummary(statusSummaryBase), [statusSummaryBase]);
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

  async function updateCandidateStatuses(ids: string[], status: BulkActionStatus) {
    if (ids.length === 0) return;
    setMutating(true);
    setError(null);
    setNotice(null);
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
      setNotice(`${ids.length} candidate${ids.length === 1 ? "" : "s"} updated to ${candidateStatusLabel(status)}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reviewBoardPage.updateError"));
    } finally {
      setMutating(false);
    }
  }

  async function bulkRemoveSelected() {
    if (bulkSelectedIds.length === 0) return;
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
      setNotice(`${bulkSelectedIds.length} candidate${bulkSelectedIds.length === 1 ? "" : "s"} removed from Review Board.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove selected candidates");
    } finally {
      setMutating(false);
      setBulkDialog(null);
    }
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

  async function sendCandidatesToReupQueue(ids: string[]) {
    const approvedIds = approvedCandidatesFromIds(candidatePool, ids);
    if (approvedIds.length === 0) {
      setError("Only approved candidates can be sent to Reup Queue. Approve first, then use Send to queue.");
      return;
    }
    setMutating(true);
    setError(null);
    setNotice(null);
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
      setNotice(formatReupQueueEnqueueNotice(result));
      if (result.queued_count > 0 || result.already_queued_count > 0) {
        setSelectedIds((current) => {
          const next = new Set(current);
          for (const id of approvedIds) next.delete(id);
          return next;
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send candidates to Reup Queue");
    } finally {
      setMutating(false);
    }
  }

  async function bulkSendApprovedToReupQueue() {
    if (bulkApprovedQueueIds.length === 0) return;
    await sendCandidatesToReupQueue(bulkApprovedQueueIds);
  }

  async function approveAndSendCandidatesToReupQueue(ids: string[]) {
    if (ids.length === 0) return;
    const knownIds = ids.filter((id) => {
      const candidate = candidatePool.find((entry) => entry.id === id);
      return candidate ? !isCandidateInReupQueue(candidate) : false;
    });
    if (knownIds.length === 0) return;
    const pendingApproval = candidatesPendingApproval(candidatePool, knownIds);
    setMutating(true);
    setError(null);
    setNotice(null);
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
      setNotice(formatApproveAndEnqueueNotice(pendingApproval.length, result));
      if (result.queued_count > 0 || result.already_queued_count > 0) {
        setSelectedIds((current) => {
          const next = new Set(current);
          for (const id of knownIds) next.delete(id);
          return next;
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to approve and send candidates to Reup Queue");
    } finally {
      setMutating(false);
    }
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
    setNotice(null);
    try {
      if (rejectIds.length > 0) await bulkUpdateCandidateStatus(rejectIds, "REJECTED");
      await bulkUpdateCandidateStatus([approveId], "APPROVED");
      setCandidates((current) => applyCandidateStatusUpdate(applyCandidateStatusUpdate(current, rejectIds, "REJECTED"), [approveId], "APPROVED"));
      setStarredIds([]);
      setCompareOpen(false);
      setNotice(`Approved best finalist (${formatReupScoreBadgeValue(reviewCandidateDisplayScore(candidateDetails[approveId] ?? visible.find((c) => c.id === approveId) ?? null))}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("reviewBoardPage.updateError"));
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

  const primaryActions = (
    <TopbarRefreshButton busy={refreshing} disabled={loading} onClick={() => void loadData("refresh")} />
  );

  return (
    <OperatorStudioShell actions={primaryActions} description="Triage shortlisted clips in a Capture Inbox-style studio and approve reup picks." title={t("reviewBoardPage.pageTitle")}>
      <OpsConsolePage>
        {refreshing ? <p className="review-board-refreshing-banner" role="status">Refreshing candidates…</p> : null}
        <ReviewStudioCommandDeck
          activeFilter={effectiveStatus}
          approvedQueueCount={bulkApprovedQueueIds.length}
          filters={filters}
          mutating={mutating}
          onApply={applyFilters}
          onApprove={() => void bulkApproveSelected()}
          onApproveAndSend={() => void bulkApproveAndSendToReupQueue()}
          onChange={setFilters}
          onClear={() => setSelectedIds(new Set())}
          onFilter={(status) => setFilters({ ...filters, status })}
          onLater={() => void bulkLaterSelected()}
          onReject={() => setBulkDialog("reject")}
          onRemove={() => setBulkDialog("remove")}
          onReset={resetFilters}
          onSendToQueue={() => void bulkSendApprovedToReupQueue()}
          onSelectVisible={() => setSelectedIds(selectAllOnPage(selectableVisible))}
          onToggleScoreRange={() => setScoreRangeOpen((open) => !open)}
          queuedInViewCount={queuedInViewCount}
          scoreRangeOpen={scoreRangeOpen}
          selectedCount={bulkSelectedIds.length}
          sortLabel={SORT_LABELS[filters.sort]}
          starredCount={starredIds.length}
          summary={summary}
          loadedCount={candidates.length}
          totalCount={totalCount}
          visibleCount={selectableVisible.length}
        />
        {notice ? <section className="operator-panel intake-status good"><strong>{notice}</strong></section> : null}
        {error && !loading ? <section className="operator-panel intake-status danger"><strong>Review Board error:</strong> {error}</section> : null}

        <div className="capture-inbox-review-workspace review-board-studio-workspace" data-review-board-ui-version={UI_VERSION}>
          <main className="capture-inbox-review-main" aria-busy={loading || refreshing} aria-label="Review Board candidate gallery" data-review-board-studio={UI_VERSION}>
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
                      mutating={mutating}
                      onApprove={() => void updateCandidateStatuses([candidate.id], "APPROVED")}
                      onApproveAndSend={() => void approveAndSendCandidatesToReupQueue([candidate.id])}
                      onDetails={() => openInspector(candidate.id)}
                      onLater={() => void updateCandidateStatuses([candidate.id], "IN_REVIEW")}
                      onReject={() => void updateCandidateStatuses([candidate.id], "REJECTED")}
                      onSendToQueue={() => void sendCandidatesToReupQueue([candidate.id])}
                      onToggleSelect={() => {}}
                      onToggleStar={() => setStarredIds((current) => toggleCompareStar(current, candidate.id))}
                      routePath={pathname}
                      selected={false}
                      showSelect={false}
                      starred
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

            {loading && candidates.length === 0 ? <OpsStatePanel detail="Loading candidates…" title="Review Board" variant="loading" /> : null}
            {!loading && error && candidates.length === 0 ? <OpsStatePanel action={<button onClick={() => void loadData("filter")} type="button">Retry</button>} detail={error} title="Review Board unavailable" variant="error" /> : null}
            {!loading && !error && candidates.length === 0 ? (
              <OpsStatePanel
                action={<a href="/ops/extensions/douyin/capture-inbox">Open Capture Inbox</a>}
                detail={
                  appliedFilters.search.trim()
                    ? "No candidates match this video ID or search text. Promote from Capture Inbox or try Open candidate on a promoted tile."
                    : "Promote ready videos from Capture Inbox to populate Review Board."
                }
                title={appliedFilters.search.trim() ? "No search matches" : "No candidates in Review Board"}
                variant="empty"
              />
            ) : null}
            {!loading && displayVisible.length === 0 && candidates.length > 0 ? (
              <OpsStatePanel
                action={filters.status === "APPROVED" && queuedInViewCount > 0 ? (
                  <button onClick={() => setShowQueuedInApproved(true)} type="button">Show {queuedInViewCount} in queue</button>
                ) : undefined}
                detail={filters.status === "APPROVED" && queuedInViewCount > 0 ? "Approved clips already in Reup Queue are hidden by default." : "Try another status tab or reset filters."}
                title={filters.status === "APPROVED" && queuedInViewCount > 0 ? "All approved clips are already in Reup Queue" : "No candidates in this view"}
                variant="empty"
              />
            ) : null}

            {displayVisible.length > 0 ? (
              <section className="capture-inbox-media-gallery" aria-label="Candidate tile gallery">
                <div className="capture-inbox-media-gallery-heading">
                  <h2>Candidate tiles</h2>
                  <span>{displayVisible.length.toLocaleString()} tile(s) shown</span>
                  {filters.status === "APPROVED" && queuedInViewCount > 0 ? (
                    <button className="review-board-show-queued-toggle" onClick={() => setShowQueuedInApproved((current) => !current)} type="button">
                      {showQueuedInApproved ? "Hide in queue" : `Show in queue (${queuedInViewCount})`}
                    </button>
                  ) : null}
                </div>
                <div className="capture-inbox-media-tile-grid">
                  {displayVisible.map((candidate) => {
                    const detail = candidateDetails[candidate.id] ?? candidate;
                    return (
                      <CandidateMediaTile
                        candidate={detail}
                        focused={activeCandidateId === candidate.id}
                        key={candidate.id}
                        mutating={mutating}
                        onApprove={() => void updateCandidateStatuses([candidate.id], "APPROVED")}
                        onApproveAndSend={() => void approveAndSendCandidatesToReupQueue([candidate.id])}
                        onDetails={() => openInspector(candidate.id)}
                        onLater={() => void updateCandidateStatuses([candidate.id], "IN_REVIEW")}
                        onReject={() => void updateCandidateStatuses([candidate.id], "REJECTED")}
                        onSendToQueue={() => void sendCandidatesToReupQueue([candidate.id])}
                        onToggleSelect={() => setSelectedIds((current) => toggleSelection(current, candidate.id))}
                        onToggleStar={() => setStarredIds((current) => toggleCompareStar(current, candidate.id))}
                        routePath={pathname}
                        selected={selectedIds.has(candidate.id)}
                        showSelect={!isCandidateInReupQueue(detail)}
                        starred={starredIds.includes(candidate.id)}
                      />
                    );
                  })}
                </div>
                {hasMoreCandidates || totalCount > 0 ? (
                  <OffsetLoadMoreFooter
                    ref={loadMoreRef}
                    autoLoad
                    disabled={mutating}
                    loadedCount={candidates.length}
                    loadingMore={loadingMore}
                    noun="candidates"
                    onLoadMore={loadMoreCandidates}
                    pageSize={CANDIDATE_PAGE_SIZE}
                    totalCount={totalCount}
                    variant="studio"
                  />
                ) : null}
              </section>
            ) : null}
          </main>
        </div>
        <ReviewRightInspector
          candidate={activeCandidate}
          mutating={mutating}
          onApprove={(candidate) => void updateCandidateStatuses([candidate.id], "APPROVED")}
          onClose={closeInspector}
          onLater={(candidate) => void updateCandidateStatuses([candidate.id], "IN_REVIEW")}
          onReject={(candidate) => void updateCandidateStatuses([candidate.id], "REJECTED")}
          onSendToQueue={(candidate) => void sendCandidatesToReupQueue([candidate.id])}
          open={rightInspectorOpen && Boolean(activeCandidate)}
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
  onSelectVisible,
  onToggleScoreRange,
  queuedInViewCount,
  scoreRangeOpen,
  selectedCount,
  sortLabel,
  starredCount,
  summary,
  loadedCount,
  totalCount,
  visibleCount
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
  onSelectVisible: () => void;
  onToggleScoreRange: () => void;
  queuedInViewCount: number;
  scoreRangeOpen: boolean;
  selectedCount: number;
  sortLabel: string;
  starredCount: number;
  summary: ReviewSummary;
  loadedCount: number;
  totalCount: number;
  visibleCount: number;
}) {
  const hasSelection = selectedCount > 0;
  const disabled = mutating;

  function update(partial: Partial<CandidateFilters>) {
    onChange({ ...filters, ...partial });
  }

  return (
    <section
      className={`review-board-command-deck ${hasSelection ? "has-selection" : ""}`}
      aria-label="Review Board studio controls"
      data-sticky="true"
    >
      <div className="review-board-command-deck-top">
        <div className="review-board-command-deck-title">
          <span className="review-board-command-deck-kicker">Review studio</span>
          <p className="review-board-command-deck-meta">
            <strong>{summary.shortlisted}</strong> shortlisted · Loaded <strong>{loadedCount.toLocaleString("en-US")}</strong> / <strong>{totalCount.toLocaleString("en-US")}</strong> · <strong>{visibleCount}</strong> in view · {sortLabel}
            {starredCount > 0 ? <> · <strong>{starredCount}</strong> starred</> : null}
            {queuedInViewCount > 0 ? <> · <strong>{queuedInViewCount}</strong> in queue</> : null}
          </p>
        </div>
        {visibleCount > 0 ? (
          <div className="review-board-command-deck-quick">
            <button className="review-board-deck-btn" disabled={disabled} onClick={onSelectVisible} type="button">
              Select visible ({visibleCount})
            </button>
            {hasSelection ? (
              <button className="review-board-deck-btn is-ghost" disabled={disabled} onClick={onClear} type="button">
                Clear
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      <div
        className="capture-inbox-status-strip reup-queue-hero-stats review-board-command-deck-segments"
        aria-label="Review Board status strip"
        role="tablist"
      >
        {REVIEW_STATUS_FILTERS.map((entry) => {
          const count = reviewSummaryValue(summary, entry.key);
          const isActive = activeFilter === entry.key;
          const tone = reviewBoardFilterTone(entry.key, count);
          return (
            <button
              aria-pressed={isActive}
              aria-selected={isActive}
              className={`capture-inbox-status-pill reup-queue-hero-stat is-tone-${tone}${isActive ? " is-active" : ""}`}
              key={entry.key || "all"}
              onClick={() => onFilter(entry.key)}
              role="tab"
              type="button"
            >
              <span>{entry.label}</span>
              <strong>{count}</strong>
            </button>
          );
        })}
      </div>

      <div className="review-board-command-deck-filters" aria-label="Review filters">
        <input
          aria-label="Search Review Board candidates"
          className="review-board-deck-input review-board-deck-search"
          onChange={(event) => update({ search: event.target.value })}
          placeholder="Search video ID, candidate UUID, caption, profile, URL…"
          type="search"
          value={filters.search}
        />
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
        {scoreRangeOpen ? (
          <>
            <input
              aria-label="Minimum score"
              className="review-board-deck-input review-board-deck-score"
              onChange={(event) => update({ minScore: event.target.value })}
              placeholder="Min"
              type="number"
              value={filters.minScore}
            />
            <input
              aria-label="Maximum score"
              className="review-board-deck-input review-board-deck-score"
              onChange={(event) => update({ maxScore: event.target.value })}
              placeholder="Max"
              type="number"
              value={filters.maxScore}
            />
          </>
        ) : null}
        <div className="review-board-command-deck-filter-actions">
          <button className="review-board-deck-btn" onClick={onToggleScoreRange} type="button">
            {scoreRangeOpen ? "Hide score" : "Score"}
          </button>
          <button className="review-board-deck-btn is-primary" onClick={onApply} type="button">Apply</button>
          <button className="review-board-deck-btn is-ghost" onClick={onReset} type="button">Reset</button>
        </div>
      </div>

      {hasSelection ? (
        <div className="review-board-command-deck-bulk capture-inbox-command-bar review-board-bulk-command-bar is-compact is-active" aria-label="Bulk actions">
          <div className="review-board-command-deck-bulk-head">
            <span className="review-board-command-deck-selection">{selectedCount} selected</span>
            <span className="review-board-command-deck-bulk-hint">Fast path: Approve &amp; send to Reup Queue</span>
          </div>
          <div className="review-board-command-deck-bulk-actions">
            <button className="review-board-deck-btn is-primary" disabled={disabled} onClick={onApproveAndSend} title="Approve selected candidates and send to Reup Queue" type="button">
              Approve &amp; send ({selectedCount})
            </button>
            <button className="review-board-deck-btn" disabled={disabled} onClick={onApprove} title="Approve selected candidates without queueing" type="button">
              Approve
            </button>
            <button
              className="review-board-deck-btn is-accent"
              disabled={disabled || approvedQueueCount === 0}
              onClick={onSendToQueue}
              title="Send already-approved selections to Reup Queue"
              type="button"
            >
              Queue{approvedQueueCount > 0 ? ` (${approvedQueueCount})` : ""}
            </button>
            <button className="review-board-deck-btn" disabled={disabled} onClick={onLater} title="Mark selected as in review" type="button">
              Later
            </button>
            <button className="review-board-deck-btn is-danger" disabled={disabled} onClick={onReject} title="Reject selected candidates" type="button">
              Reject
            </button>
            <button className="review-board-deck-btn is-link" disabled={disabled} onClick={onRemove} title="Remove selected from Review Board" type="button">
              Remove from board
            </button>
          </div>
        </div>
      ) : null}
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
  onToggleStar,
  routePath,
  selected,
  showSelect,
  starred
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
  onToggleStar: () => void;
  routePath: string;
  selected: boolean;
  showSelect: boolean;
  starred: boolean;
}) {
  const metadata = getReviewCandidateMetadata(candidate);
  const title = candidateTitle(candidate);
  const scoreBadge = getOperatorTileScoreBadge(buildCapturedItemFromReviewCandidate(candidate));
  const thumbnailUrl = metadata.thumbnailUrl;
  const approvedForQueue = isApprovedForReupQueue(candidate);
  const inReupQueue = isCandidateInReupQueue(candidate);
  return (
    <article className={`capture-inbox-media-tile capture-inbox-compact-card review-board-media-tile ${selected ? "is-bulk-selected" : ""} ${focused ? "is-inspector-focused" : ""} ${inReupQueue ? "is-in-reup-queue" : ""}`}>
      <div className="capture-inbox-media-frame">
        <button className="capture-inbox-media-thumbnail" onClick={onDetails} type="button">
          {thumbnailUrl ? <img alt={`Thumbnail for ${title}`} src={thumbnailUrl} /> : <span className="capture-inbox-thumbnail-placeholder"><strong>No thumbnail</strong></span>}
        </button>
        <WorkMediaTileOverlay
          onToggleSelect={onToggleSelect}
          rightSlot={(
            <button aria-label={starred ? "Unstar finalist" : "Star finalist"} aria-pressed={starred} className={`review-board-tile-star ${starred ? "active" : ""}`} onClick={onToggleStar} type="button">★</button>
          )}
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
        <div className="capture-inbox-tile-quick-meta" aria-label="Compact quick metadata">
          <span className="capture-inbox-tile-quick-chip"><strong>Posted</strong><span>{formatReviewPostedLabel(metadata)}</span></span>
          <span className="capture-inbox-tile-quick-chip"><strong>Duration</strong><span>{metadata.durationText ?? "—"}</span></span>
          <span className="capture-inbox-tile-quick-chip"><strong>Est. Views</strong><span>{formatEstimatedViews(metadata)}</span></span>
        </div>
        <div className="capture-inbox-tile-metrics" aria-label="Item metrics">
          <div className="capture-inbox-tile-metric-cell"><span className="capture-inbox-tile-metric-label">Likes</span><strong className="capture-inbox-tile-metric-value">{formatExactEngagementMetric(metadata.likeCount, metadata.likeCountText)}</strong></div>
          <div className="capture-inbox-tile-metric-cell"><span className="capture-inbox-tile-metric-label">Comments</span><strong className="capture-inbox-tile-metric-value">{formatExactEngagementMetric(metadata.commentCount, metadata.commentCountText)}</strong></div>
          <div className="capture-inbox-tile-metric-cell"><span className="capture-inbox-tile-metric-label">Shares</span><strong className="capture-inbox-tile-metric-value">{formatExactEngagementMetric(metadata.shareCount, metadata.shareCountText)}</strong></div>
        </div>
      </div>
      <div className="capture-inbox-tile-footer capture-inbox-compact-actions">
        <ReviewBoardTileActions
          approvedForQueue={approvedForQueue}
          inReupQueue={inReupQueue}
          mutating={mutating}
          onApprove={onApprove}
          onApproveAndSend={onApproveAndSend}
          onDetails={onDetails}
          onLater={onLater}
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

function ReviewRightInspector({ candidate, mutating, onApprove, onClose, onLater, onReject, onSendToQueue, open }: { candidate: Candidate | null; mutating: boolean; onApprove: (candidate: Candidate) => void; onClose: () => void; onLater: (candidate: Candidate) => void; onReject: (candidate: Candidate) => void; onSendToQueue: (candidate: Candidate) => void; open: boolean }) {
  const metadata = candidate ? getReviewCandidateMetadata(candidate) : null;
  const scoreBadge = candidate ? reviewCandidateScoreBadge(candidate) : null;
  const approvedForQueue = candidate ? isApprovedForReupQueue(candidate) : false;
  const inReupQueue = candidate ? isCandidateInReupQueue(candidate) : false;
  return (
    <WorkItemDetailsDrawer
      eyebrow="Candidate inspector"
      footer={
        candidate ? (
          <div className="review-board-inspector-queue-actions">
            <ReviewBoardTileActions
              approvedForQueue={approvedForQueue}
              inReupQueue={inReupQueue}
              mutating={mutating}
              onApprove={() => onApprove(candidate)}
              onDetails={() => undefined}
              onLater={() => onLater(candidate)}
              onReject={() => onReject(candidate)}
              onSendToQueue={() => onSendToQueue(candidate)}
              variant="inspector"
            />
          </div>
        ) : null
      }
      open={open}
      title="Review details"
      titleId="review-board-details-title"
      onClose={onClose}
    >
      <OpsDetailPanel emptyDetail={!candidate ? "Select a tile to inspect details." : undefined} title="Candidate details">
        {candidate && metadata ? (
          <>
            <div className="capture-inbox-detail-hero compact">
              <div className="capture-inbox-detail-hero-topline">
                <span className={`capture-inbox-reup-score-badge is-${scoreBadge?.level ?? "needs_metadata"} ${scoreBadge?.score == null ? "missing" : "ready"}`}>
                  <strong>{formatReupScoreBadgeValue(scoreBadge?.score)}</strong>
                  <small>{reupScoreBadgeTier(scoreBadge?.score)}</small>
                </span>
                <span className={`status-badge review-board-status-badge ${statusTone(candidate.status)}`}>{candidateStatusLabel(candidate.status)}</span>
                {inReupQueue ? <span className="status-badge review-board-status-badge good">In Reup Queue</span> : null}
              </div>
              <p>{candidateTitle(candidate)}</p>
            </div>
            <OpsDetailSection title="Core metadata">
              <OpsMetadataList items={[
                { label: "Posted", value: formatReviewPostedLabel(metadata) },
                { label: "Duration", value: metadata.durationText ?? "—" },
                { label: "Est. Views", value: formatEstimatedViews(metadata) },
                { label: "Likes", value: formatExactEngagementMetric(metadata.likeCount, metadata.likeCountText) },
                { label: "Comments", value: formatExactEngagementMetric(metadata.commentCount, metadata.commentCountText) },
                { label: "Shares", value: formatExactEngagementMetric(metadata.shareCount, metadata.shareCountText) }
              ]} />
            </OpsDetailSection>
          </>
        ) : null}
      </OpsDetailPanel>
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

function buildSummary(candidates: Candidate[]): ReviewSummary {
  return {
    total: candidates.length,
    approved: candidates.filter((candidate) => normalizeReviewStatus(candidate) === "APPROVED").length,
    rejected: candidates.filter((candidate) => normalizeReviewStatus(candidate) === "REJECTED").length,
    inReview: candidates.filter((candidate) => normalizeReviewStatus(candidate) === "IN_REVIEW").length,
    newItems: candidates.filter((candidate) => normalizeReviewStatus(candidate) === "NEW").length,
    shortlisted: candidates.filter((candidate) => normalizeReviewStatus(candidate) === "SHORTLISTED").length
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
