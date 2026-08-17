"use client";

import { useEffect, useMemo, useRef, useState, useCallback, useTransition } from "react";
import { fetchReupQueueIntakeSessions, fetchReupQueueItems, purgeClearableReupQueueItems, revealSourceVideoLocalAsset, runReupQueueAction, runReupQueueBatchAction } from "../../lib/api";
import { EMPTY_INTAKE_FILTERS, type IntakeFilterState } from "../../lib/reviewBoardIntake";
import type { CaptureSession } from "../../types/capture-inbox";
import { IntakeFilterRow } from "../shared/IntakeFilterRow";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import {
  actionLabel,
  buildReupQueueSummary,
  buildReupQueueSummaryFromStatusCounts,
  buildSelectionEligibility,
  bulkCancelConfirmMessage,
  bulkDismissConfirmMessage,
  bulkPurgeConfirmMessage,
  bulkSelectionGuidance,
  cancellableReupQueueItems,
  clearablePurgeReupQueueItems,
  dismissableReupQueueItems,
  formatBatchResultSummary,
  formatDateTime,
  buildInspectorWorkflowLinks,
  buildPipelineStages,
  buildQueueInspectorEngagementStats,
  buildQueueTileSecondaryLinks,
  pipelineStageInteraction,
  buildQuickPathHeroStats,
  automationModeOptions,
  canChangeAutomation,
  currentAutomationMode,
  capStartProcessingBatchIds,
  downloadJobProgressPercent,
  formatJobChipLabel,
  groupInspectorLifecycleActions,
  filterInspectorCompanionActions,
  hasActiveDownloadJob,
  hasActivePipelineJob,
  hasAnyBatchEligibility,
  itemTitle,
  metadataString,
  operatorStatusLabel,
  primaryBulkEligibilityTotal,
  markMediaReadyNotice,
  primaryQueueAction,
  primaryQueueActionLabel,
  queueTilePrimaryButtonClassName,
  queueTilePrimaryButtonTone,
  resolveInitialReupQueueFilter,
  queueStageLabel,
  queueStageTone,
  queueTileDurationLabel,
  queueTileFailureAlert,
  queueTileFailureStrip,
  pipelineFailureRecoveryLink,
  queueTilePostedLabel,
  queueTileThumbnailUrl,
  queueTileTranscriptCta,
  worklistStageLabel,
  worklistStageTone,
  worklistTranscriptHref,
  worklistFinalReviewHref,
  pipelineStepChipLabel,
  pipelineRecipeChipLabel,
  queueTileNextStepHint,
  shouldShowQueueTileDetailsButton,
  REUP_QUEUE_ATTENTION_FILTERS,
  REUP_QUEUE_PIPELINE_FILTERS,
  REUP_QUEUE_START_PROCESSING_BATCH_LIMIT,
  REUP_QUEUE_STATUS_FILTERS,
  secondaryBulkEligibilityTotal,
  selectAllActionableReupQueueItems,
  selectedVisibleReupQueueIds,
  selectableReupQueueItems,
  startProcessingBatchCapNotice,
  statusesForReupQueueFilter,
  supportsBulkCancelVisibleScope,
  supportsBulkDismissVisibleScope,
  supportsBulkPurgeVisibleScope,
  terminalQueueDismissAction,
  toggleReupQueueSelection,
  visibleReupQueueItems,
  type ReupPipelineMode,
  type ReupQueueOperatorFilter,
  type ReupQueueSortMode
} from "../../lib/reupQueueStudioState";
import { useQueueTileScoreBadge } from "../../lib/useCaptureItemReupScore";
import { hasMoreOffsetItems, resolveOffsetPageMerge } from "../../lib/offsetListPagination";
import {
  applyMarqueeSelection,
  autoScrollVelocity,
  dragDistance,
  intersectingSelectionIds,
  normalizeSelectionRect,
  selectSelectionRange,
  type MarqueeSelectionMode,
  type SelectionPoint,
  type SelectionRect,
  type SelectionRectEntry
} from "../../lib/reupQueueDragSelection";
import {
  REUP_QUEUE_VIEW_MODE_LABELS,
  readReupQueueViewMode,
  writeReupQueueViewMode,
  type ReupQueueViewMode
} from "../../lib/reupQueueViewMode";
import type { BatchOperationResponse, ReupQueueBatchAction } from "../../types/export-handoff";
import type { ReupQueueAction, ReupQueueItem } from "../../types/reup-queue";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { CaptureInboxFilterChipIcon, type CaptureInboxFilterChipIconKind } from "../capture-inbox/CaptureInboxFilterChipIcon";
import { OpsConsolePage, OpsMetadataList } from "../ops-console/OpsShared";
import { WorkItemActionIcon, type WorkItemActionIconKind } from "../shared/WorkItemActionIcon";
import { AsyncButton } from "../shared/AsyncButton";
import { AsyncContentBoundary } from "../shared/AsyncContentBoundary";
import { useNotice } from "../shared/NoticeCenter";
import { OffsetLoadMoreFooter } from "../shared/OffsetLoadMoreFooter";
import { WorkItemDetailsDrawer } from "../shared/WorkItemDetailsDrawer";
import { WorkMediaTileOverlay } from "../shared/WorkMediaTileOverlay";
import { WorkBulkActionBar, WorkGalleryEmptyState, WorkGalleryHeader, WorkStudioDeck, WorkViewToggle } from "../shared/WorkStudioChrome";
import { useOffsetLoadMoreOnScroll } from "../shared/useOffsetLoadMoreOnScroll";
import { useAsyncAction } from "../../lib/useAsyncAction";

const UI_VERSION = "22H-1R";
const DEFAULT_HANDOFF_PLATFORM = "FACEBOOK_REELS";
const REVIEW_BOARD_HREF = "/selection/review-board";
const ACTIVE_DOWNLOAD_POLL_MS = 8_000;
const REUP_QUEUE_LOAD_BATCH_SIZE = 50;
const WORKLIST_MARQUEE_DRAG_THRESHOLD_PX = 6;

type WorklistDragSession = {
  anchorDocument: SelectionPoint;
  currentClient: SelectionPoint;
  mode: MarqueeSelectionMode;
  pointerId: number;
  selectionEntries: SelectionRectEntry[];
  selectionAtDragStart: Set<string>;
  started: boolean;
};

export function ReupQueuePage({
  initialFilter
}: {
  initialFilter?: ReupQueueOperatorFilter;
} = {}) {
  const asyncActions = useAsyncAction();
  const { notify } = useNotice();
  const [items, setItems] = useState<ReupQueueItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [operatorFilter, setOperatorFilter] = useState<ReupQueueOperatorFilter>(
    initialFilter ?? "all"
  );
  const [pendingFilter, setPendingFilter] = useState<ReupQueueOperatorFilter | null>(null);
  const [isFilterPending, startFilterTransition] = useTransition();
  const [searchQuery, setSearchQuery] = useState("");
  const [intake, setIntake] = useState<IntakeFilterState>(EMPTY_INTAKE_FILTERS);
  const [intakeSessions, setIntakeSessions] = useState<CaptureSession[]>([]);
  const [sortMode, setSortMode] = useState<ReupQueueSortMode>("active-first");
  const [viewMode, setViewMode] = useState<ReupQueueViewMode>(() => readReupQueueViewMode());
  const [collapsedWorklistStages, setCollapsedWorklistStages] = useState<Set<string>>(() => new Set());
  const [worklistMarquee, setWorklistMarquee] = useState<SelectionRect | null>(null);
  const [worklistDragging, setWorklistDragging] = useState(false);
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [queueInspectorOpen, setQueueInspectorOpen] = useState(false);
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [batchResult, setBatchResult] = useState<BatchOperationResponse | null>(null);
  const [mutatingAction, setMutatingAction] = useState<ReupQueueAction | null>(null);
  const [batchWorkingAction, setBatchWorkingAction] = useState<ReupQueueBatchAction | null>(null);
  const initialFilterApplied = useRef(Boolean(initialFilter));
  const loadedCountRef = useRef(0);
  const loadMoreInFlightRef = useRef(false);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const worklistSurfaceRef = useRef<HTMLDivElement | null>(null);
  const worklistDragSessionRef = useRef<WorklistDragSession | null>(null);
  const worklistAutoScrollFrameRef = useRef<number | null>(null);
  const worklistSelectionFrameRef = useRef<number | null>(null);
  const worklistSelectionAnchorRef = useRef<string | null>(null);
  const worklistSuppressClickRef = useRef(false);
  const selectedItemIdsRef = useRef(selectedItemIds);
  selectedItemIdsRef.current = selectedItemIds;
  const itemsRef = useRef(items);
  const totalCountRef = useRef(totalCount);
  itemsRef.current = items;
  totalCountRef.current = totalCount;
  const operatorFilterRef = useRef(operatorFilter);
  operatorFilterRef.current = operatorFilter;
  // Scroll paging and the background poll both fire from stale closures, so they read
  // the intake filter from a ref instead of capturing it.
  const intakeRef = useRef(intake);
  intakeRef.current = intake;
  const queueHasMore = hasMoreOffsetItems(items.length, totalCount);
  const queuePagerDisabled = mutatingAction !== null || batchWorkingAction !== null;

  function queueItemActionKey(item: ReupQueueItem, action: ReupQueueAction | ReupQueueBatchAction) {
    return `queue-item:${item.id}:${action}`;
  }

  function queueItemPending(itemId: string) {
    return [...asyncActions.pendingKeys].some((key) => key.startsWith(`queue-item:${itemId}:`));
  }

  function toggleWorklistStage(stageLabel: string) {
    setCollapsedWorklistStages((current) => {
      const next = new Set(current);
      if (next.has(stageLabel)) next.delete(stageLabel);
      else next.add(stageLabel);
      return next;
    });
  }

  const updateWorklistMarqueeSelection = useCallback((session: WorklistDragSession) => {
    const currentDocument = clientPointToDocument(session.currentClient);
    const selectionRect = normalizeSelectionRect(session.anchorDocument, currentDocument);
    const intersectingIds = intersectingSelectionIds(selectionRect, session.selectionEntries);

    setSelectedItemIds(applyMarqueeSelection(session.selectionAtDragStart, intersectingIds, session.mode));
    setWorklistMarquee({
      bottom: selectionRect.bottom - window.scrollY,
      left: selectionRect.left - window.scrollX,
      right: selectionRect.right - window.scrollX,
      top: selectionRect.top - window.scrollY
    });
  }, []);

  const stopWorklistAutoScroll = useCallback(() => {
    if (worklistAutoScrollFrameRef.current == null) return;
    window.cancelAnimationFrame(worklistAutoScrollFrameRef.current);
    worklistAutoScrollFrameRef.current = null;
  }, []);

  const stopWorklistSelectionFrame = useCallback(() => {
    if (worklistSelectionFrameRef.current == null) return;
    window.cancelAnimationFrame(worklistSelectionFrameRef.current);
    worklistSelectionFrameRef.current = null;
  }, []);

  const scheduleWorklistMarqueeUpdate = useCallback(() => {
    if (worklistSelectionFrameRef.current != null) return;
    worklistSelectionFrameRef.current = window.requestAnimationFrame(() => {
      worklistSelectionFrameRef.current = null;
      const session = worklistDragSessionRef.current;
      if (session?.started) updateWorklistMarqueeSelection(session);
    });
  }, [updateWorklistMarqueeSelection]);

  const ensureWorklistAutoScroll = useCallback(() => {
    if (worklistAutoScrollFrameRef.current != null) return;

    const tick = () => {
      const session = worklistDragSessionRef.current;
      if (!session?.started) {
        worklistAutoScrollFrameRef.current = null;
        return;
      }
      const velocity = autoScrollVelocity(session.currentClient.y, window.innerHeight);
      if (velocity === 0) {
        worklistAutoScrollFrameRef.current = null;
        return;
      }
      window.scrollBy({ behavior: "auto", left: 0, top: velocity });
      scheduleWorklistMarqueeUpdate();
      worklistAutoScrollFrameRef.current = window.requestAnimationFrame(tick);
    };

    worklistAutoScrollFrameRef.current = window.requestAnimationFrame(tick);
  }, [scheduleWorklistMarqueeUpdate]);

  useEffect(() => {
    function handlePagePointerDown(event: globalThis.PointerEvent) {
      if (viewMode !== "worklist" || !worklistSurfaceRef.current) return;
      if (event.button !== 0 || event.pointerType !== "mouse" || pageDragTargetBlocksMarquee(event.target)) return;

      const currentClient = { x: event.clientX, y: event.clientY };
      worklistDragSessionRef.current = {
        anchorDocument: clientPointToDocument(currentClient),
        currentClient,
        mode: event.ctrlKey || event.metaKey ? "toggle" : "replace",
        pointerId: event.pointerId,
        selectionEntries: readWorklistSelectionEntries(worklistSurfaceRef.current),
        selectionAtDragStart: new Set(selectedItemIdsRef.current),
        started: false
      };
    }

    function handlePagePointerMove(event: globalThis.PointerEvent) {
      const session = worklistDragSessionRef.current;
      if (!session || session.pointerId !== event.pointerId) return;

      session.currentClient = { x: event.clientX, y: event.clientY };
      const currentDocument = clientPointToDocument(session.currentClient);
      if (!session.started) {
        if (dragDistance(session.anchorDocument, currentDocument) < WORKLIST_MARQUEE_DRAG_THRESHOLD_PX) return;
        session.started = true;
        try {
          document.documentElement.setPointerCapture(event.pointerId);
        } catch {
          // Document-level listeners still keep the gesture active inside the viewport.
        }
        setWorklistDragging(true);
        document.body.classList.add("is-reup-queue-marquee-selecting");
        window.getSelection()?.removeAllRanges();
      }

      event.preventDefault();
      scheduleWorklistMarqueeUpdate();
      const velocity = autoScrollVelocity(session.currentClient.y, window.innerHeight);
      if (velocity === 0) stopWorklistAutoScroll();
      else ensureWorklistAutoScroll();
    }

    function handlePagePointerEnd(event: globalThis.PointerEvent) {
      const session = worklistDragSessionRef.current;
      if (!session || session.pointerId !== event.pointerId) return;

      if (session.started) {
        event.preventDefault();
        stopWorklistSelectionFrame();
        updateWorklistMarqueeSelection(session);
        worklistSuppressClickRef.current = true;
        window.setTimeout(() => {
          worklistSuppressClickRef.current = false;
        }, 0);
      }
      try {
        if (document.documentElement.hasPointerCapture(event.pointerId)) document.documentElement.releasePointerCapture(event.pointerId);
      } catch {
        // Pointer capture may already be gone after a native cancellation.
      }
      worklistDragSessionRef.current = null;
      stopWorklistAutoScroll();
      document.body.classList.remove("is-reup-queue-marquee-selecting");
      setWorklistDragging(false);
      setWorklistMarquee(null);
    }

    function handlePageClickCapture(event: globalThis.MouseEvent) {
      if (!worklistSuppressClickRef.current) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      worklistSuppressClickRef.current = false;
    }

    function handlePageDragStart(event: globalThis.DragEvent) {
      if (worklistDragSessionRef.current) event.preventDefault();
    }

    document.addEventListener("pointerdown", handlePagePointerDown, true);
    document.addEventListener("pointermove", handlePagePointerMove, true);
    document.addEventListener("pointerup", handlePagePointerEnd, true);
    document.addEventListener("pointercancel", handlePagePointerEnd, true);
    document.addEventListener("click", handlePageClickCapture, true);
    document.addEventListener("dragstart", handlePageDragStart, true);
    return () => {
      document.removeEventListener("pointerdown", handlePagePointerDown, true);
      document.removeEventListener("pointermove", handlePagePointerMove, true);
      document.removeEventListener("pointerup", handlePagePointerEnd, true);
      document.removeEventListener("pointercancel", handlePagePointerEnd, true);
      document.removeEventListener("click", handlePageClickCapture, true);
      document.removeEventListener("dragstart", handlePageDragStart, true);
      worklistDragSessionRef.current = null;
      stopWorklistAutoScroll();
      stopWorklistSelectionFrame();
      document.body.classList.remove("is-reup-queue-marquee-selecting");
    };
  }, [ensureWorklistAutoScroll, scheduleWorklistMarqueeUpdate, stopWorklistAutoScroll, stopWorklistSelectionFrame, updateWorklistMarqueeSelection, viewMode]);

  const loadMoreQueue = useCallback(async () => {
    const currentItems = itemsRef.current;
    const currentTotal = totalCountRef.current;
    if (loadMoreInFlightRef.current || !hasMoreOffsetItems(currentItems.length, currentTotal)) return;
    loadMoreInFlightRef.current = true;
    setLoadingMore(true);
    setError(null);
    try {
      const statuses = statusesForReupQueueFilter(operatorFilterRef.current);
      const payload = await fetchReupQueueItems({
        limit: REUP_QUEUE_LOAD_BATCH_SIZE,
        offset: currentItems.length,
        statuses,
        sort: sortMode,
        ...intakeRef.current,
      });
      setStatusCounts(payload.status_counts ?? {});
      const { merged, totalCount: nextTotalCount } = resolveOffsetPageMerge(
        currentItems,
        payload.items,
        payload.total_count
      );
      loadedCountRef.current = merged.length;
      setItems(merged);
      setTotalCount(nextTotalCount);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load more Reup Queue items";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      loadMoreInFlightRef.current = false;
      setLoadingMore(false);
    }
  }, [notify, sortMode]);

  useOffsetLoadMoreOnScroll({
    sentinelRef: loadMoreRef,
    hasMore: queueHasMore,
    loading: loadingMore,
    disabled: queuePagerDisabled,
    loadedCount: items.length,
    onLoadMore: loadMoreQueue,
  });

  async function loadQueue(preserveUi = false, filter = operatorFilter, sort = sortMode) {
    if (preserveUi) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const statuses = statusesForReupQueueFilter(filter);
      const windowLimit = Math.max(REUP_QUEUE_LOAD_BATCH_SIZE, preserveUi ? loadedCountRef.current || REUP_QUEUE_LOAD_BATCH_SIZE : REUP_QUEUE_LOAD_BATCH_SIZE);
      const payload = await fetchReupQueueItems({ limit: windowLimit, offset: 0, statuses, sort, ...intakeRef.current });
      setStatusCounts(payload.status_counts ?? {});
      const nextSummary = buildReupQueueSummaryFromStatusCounts(payload.status_counts);
      if (!initialFilterApplied.current) {
        const resolvedFilter = resolveInitialReupQueueFilter(nextSummary);
        initialFilterApplied.current = true;
        if (resolvedFilter !== filter) {
          setOperatorFilter(resolvedFilter);
          // Effect on operatorFilter will reload with the resolved tab statuses.
          return;
        }
      }
      setItems(payload.items);
      setTotalCount(payload.total_count);
      loadedCountRef.current = payload.items.length;
      setActiveItemId((current) => {
        const stillLoaded = current && payload.items.some((item) => item.id === current);
        setQueueInspectorOpen((open) => open && Boolean(stillLoaded));
        return stillLoaded ? current : null;
      });
      setSelectedItemIds((current) => new Set([...current].filter((id) => payload.items.some((item) => item.id === id))));
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load Reup Queue";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setLoading(false);
      setRefreshing(false);
      if (!preserveUi) setPendingFilter(null);
    }
  }

  function handleOperatorFilterChange(nextFilter: ReupQueueOperatorFilter) {
    if (nextFilter === operatorFilter) return;
    setPendingFilter(nextFilter);
    startFilterTransition(() => {
      setOperatorFilter(nextFilter);
      loadedCountRef.current = 0;
    });
  }

  function handleSortModeChange(nextSort: ReupQueueSortMode) {
    if (nextSort === sortMode) return;
    setSortMode(nextSort);
    loadedCountRef.current = 0;
  }

  function applyIntakeChange(partial: Partial<IntakeFilterState>) {
    setIntake((current) => ({ ...current, ...partial }));
    loadedCountRef.current = 0;
  }

  function clearIntakeFilters() {
    applyIntakeChange(EMPTY_INTAKE_FILTERS);
  }

  function handleViewModeChange(nextMode: ReupQueueViewMode) {
    if (nextMode === viewMode) return;
    setViewMode(nextMode);
    writeReupQueueViewMode(nextMode);
  }

  useEffect(() => {
    void loadQueue(false, operatorFilter, sortMode);
  }, [operatorFilter, sortMode, intake]);

  useEffect(() => {
    let cancelled = false;
    void fetchReupQueueIntakeSessions({ limit: 50 })
      .then((response) => {
        // The API already drops empty promotes and remaps the count to queue membership.
        if (!cancelled) setIntakeSessions(response.sessions);
      })
      .catch(() => {
        // The picker is an optional refinement; the queue still works without it.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto pipeline keeps working after download (analyze → translate → TTS), so the
  // queue must keep refreshing for those steps too, not only while media downloads.
  const hasActiveWork = useMemo(
    () => items.some((item) => hasActiveDownloadJob(item) || hasActivePipelineJob(item)),
    [items]
  );

  useEffect(() => {
    if (!hasActiveWork) return;
    const timer = window.setInterval(() => {
      void loadQueue(true, operatorFilterRef.current, sortMode);
    }, ACTIVE_DOWNLOAD_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hasActiveWork, sortMode]);

  useEffect(() => {
    if (!queueInspectorOpen) return;
    function onKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === "Escape") closeItemDetails();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [queueInspectorOpen]);

  const summary = useMemo(() => buildReupQueueSummaryFromStatusCounts(statusCounts), [statusCounts]);
  const visibleItems = useMemo(
    () => visibleReupQueueItems(items, operatorFilter, searchQuery, sortMode),
    [items, operatorFilter, searchQuery, sortMode]
  );
  const worklistGroups = useMemo(() => groupReupQueueWorklistItems(visibleItems), [visibleItems]);
  const worklistSelectableIds = useMemo(
    () => worklistGroups.flatMap((group) => group.items.filter(hasAnyBatchEligibility).map((item) => item.id)),
    [worklistGroups]
  );
  const bulkSelectedIds = useMemo(() => selectedVisibleReupQueueIds(visibleItems, selectedItemIds), [selectedItemIds, visibleItems]);
  const selectedItems = useMemo(() => items.filter((item) => selectedItemIds.has(item.id)), [items, selectedItemIds]);
  const activeItem = useMemo(() => {
    if (!activeItemId) return null;
    return items.find((item) => item.id === activeItemId) ?? visibleItems.find((item) => item.id === activeItemId) ?? null;
  }, [activeItemId, items, visibleItems]);

  useEffect(() => {
    if (!activeItemId || activeItem) return;
    setQueueInspectorOpen(false);
    setActiveItemId(null);
  }, [activeItem, activeItemId]);

  useEffect(() => {
    if (!worklistDragging) return;
    function handleScroll() {
      const session = worklistDragSessionRef.current;
      if (session?.started) scheduleWorklistMarqueeUpdate();
    }
    window.addEventListener("scroll", handleScroll, true);
    return () => window.removeEventListener("scroll", handleScroll, true);
  }, [scheduleWorklistMarqueeUpdate, worklistDragging]);

  useEffect(() => () => {
    stopWorklistAutoScroll();
    stopWorklistSelectionFrame();
  }, [stopWorklistAutoScroll, stopWorklistSelectionFrame]);

  function handleWorklistRowSelection(itemId: string, modifiers: { additive: boolean; range: boolean }) {
    const anchorId = worklistSelectionAnchorRef.current;
    if (modifiers.range && anchorId) {
      setSelectedItemIds((current) => selectSelectionRange(current, worklistSelectableIds, anchorId, itemId, modifiers.additive));
    } else if (modifiers.additive) {
      setSelectedItemIds((current) => toggleReupQueueSelection(current, itemId));
    } else {
      setSelectedItemIds(new Set([itemId]));
    }
    worklistSelectionAnchorRef.current = itemId;
  }

  async function applyQueueAction(
    item: ReupQueueItem,
    action: ReupQueueAction,
    options?: { pipelineMode?: ReupPipelineMode }
  ) {
    if (action === "CANCEL" && !window.confirm(bulkCancelConfirmMessage(1, operatorFilter))) {
      return;
    }
    if (action === "DISMISS" && !window.confirm(bulkDismissConfirmMessage(1, operatorFilter))) {
      return;
    }
    await asyncActions.run(queueItemActionKey(item, action), async () => {
    setMutatingAction(action);
    setError(null);
    setBatchResult(null);
    try {
      const result = await runReupQueueAction(item.id, {
        action,
        note: defaultActionNote(action),
        blocked_reason: action === "MARK_BLOCKED" || action === "CANCEL" ? defaultActionNote(action) : null,
        media_prep_notes: action === "MARK_MEDIA_READY" ? "Operator confirmed media; enqueue audio analysis." : null,
        media_prep_status: action === "MARK_MEDIA_READY" ? "WAITING_FOR_METADATA" : null,
        pipeline_mode:
          action === "SET_AUTOMATION"
            ? (options?.pipelineMode ?? "auto_to_render")
            : action === "START_AUTO_PIPELINE"
              ? (options?.pipelineMode ?? "auto_to_render")
              : null
      });
      setItems((current) => current.map((existing) => (existing.id === result.item.id ? result.item : existing)));
      if (queueInspectorOpen) {
        setActiveItemId(result.item.id);
      }
      notify({
        message: action === "MARK_MEDIA_READY"
          ? markMediaReadyNotice(result.item)
          : `${actionLabel(action)} applied. Current state: ${operatorStatusLabel(result.item.status)}.`,
        tone: "success"
      });
      await loadQueue(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to run Reup Queue action";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setMutatingAction(null);
    }
    });
  }

  async function applyBatchAction(
    action: ReupQueueBatchAction,
    itemIds = bulkSelectedIds,
    pendingKey = `bulk:${action}`,
    options?: { pipelineMode?: string | null }
  ) {
    if (itemIds.length === 0) {
      notify({ message: "Select at least one queue item before running a batch action.", tone: "info" });
      return;
    }
    if (action === "CANCEL" && !window.confirm(bulkCancelConfirmMessage(itemIds.length, operatorFilter))) {
      return;
    }
    if (action === "DISMISS" && !window.confirm(bulkDismissConfirmMessage(itemIds.length, operatorFilter))) {
      return;
    }
    if (action === "PURGE" && !window.confirm(bulkPurgeConfirmMessage(itemIds.length, operatorFilter))) {
      return;
    }
    let requestIds = itemIds;
    let preflightCapNotice: string | null = null;
    // Auto keeps every selected clip: the lane parks what it cannot start yet and admits
    // it later. Only the manual start still shares one download session worth capping.
    if (action === "START_PROCESSING") {
      const capped = capStartProcessingBatchIds(itemIds);
      requestIds = capped.acceptedIds;
      if (capped.overflowCount > 0) {
        preflightCapNotice = startProcessingBatchCapNotice(
          capped.acceptedIds.length,
          capped.overflowCount,
          REUP_QUEUE_START_PROCESSING_BATCH_LIMIT
        );
      }
    }
    await asyncActions.run(pendingKey, async () => {
    setBatchWorkingAction(action);
    setError(null);
    if (preflightCapNotice) notify({ message: preflightCapNotice, tone: "info" });
    setBatchResult(null);
    try {
      const result = await runReupQueueBatchAction({
        action,
        item_ids: requestIds,
        note: defaultBatchActionNote(action),
        target_platform: action === "CREATE_PUBLISH_HANDOFF" ? DEFAULT_HANDOFF_PLATFORM : null,
        pipeline_mode:
          action === "SET_AUTOMATION" || action === "START_AUTO_PIPELINE"
            ? (options?.pipelineMode ?? "auto_to_render")
            : null
      });
      setBatchResult(result);
      const summary = batchSummary(action, result);
      notify({ message: preflightCapNotice ? `${preflightCapNotice} ${summary}` : summary, tone: "success" });
      setSelectedItemIds(new Set());
      await loadQueue(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to run Reup Queue batch action";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setBatchWorkingAction(null);
    }
    });
  }

  async function purgeVisibleClearableItems() {
    const itemIds = clearablePurgeReupQueueItems(visibleItems).map((item) => item.id);
    if (itemIds.length === 0) {
      notify({ message: "No clearable queue records in the current view.", tone: "info" });
      return;
    }
    if (!window.confirm(bulkPurgeConfirmMessage(itemIds.length, operatorFilter))) {
      return;
    }
    await asyncActions.run("bulk:PURGE", async () => {
    setBatchWorkingAction("PURGE");
    setError(null);
    setBatchResult(null);
    try {
      const result = await purgeClearableReupQueueItems({ item_ids: itemIds, scope: "selected" });
      const skippedNote = result.skipped_count > 0 ? ` Skipped ${result.skipped_count} linked to export packages.` : "";
      notify({ message: `Permanently deleted ${result.purged_count}/${result.requested_count} queue record(s).${skippedNote}`, tone: "success" });
      setSelectedItemIds(new Set());
      await loadQueue(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to purge Reup Queue items";
      setError(message);
      notify({ message, tone: "error" });
    } finally {
      setBatchWorkingAction(null);
    }
    });
  }

  async function runTilePrimaryAction(item: ReupQueueItem) {
    const action = primaryQueueAction(item);
    if (action === "inspect" || action === null) {
      const finalHref = worklistFinalReviewHref(item);
      if (finalHref) {
        window.location.href = finalHref;
        return;
      }
      openItemDetails(item.id);
      return;
    }
    if (action === "CREATE_EXPORT_PACKAGE" || action === "CREATE_PUBLISH_HANDOFF" || action === "PURGE") {
      await applyBatchAction(action, [item.id], queueItemActionKey(item, action));
      return;
    }
    await applyQueueAction(item, action);
  }

  function openItemDetails(itemId: string) {
    if (!visibleItems.some((item) => item.id === itemId)) return;
    setActiveItemId(itemId);
    setQueueInspectorOpen(true);
  }

  function closeItemDetails() {
    setQueueInspectorOpen(false);
    setActiveItemId(null);
  }

  const primaryActions = (
    <TopbarRefreshButton busy={refreshing} disabled={loading} onClick={() => void loadQueue(true)} />
  );

  const selectionEligibility = useMemo(() => buildSelectionEligibility(selectedItems), [selectedItems]);
  const actionableVisibleCount = useMemo(() => selectableReupQueueItems(visibleItems).length, [visibleItems]);
  const cancellableVisibleItems = useMemo(() => cancellableReupQueueItems(visibleItems), [visibleItems]);
  const dismissableVisibleItems = useMemo(() => dismissableReupQueueItems(visibleItems), [visibleItems]);
  const purgeableVisibleItems = useMemo(() => clearablePurgeReupQueueItems(visibleItems), [visibleItems]);
  const bulkHint = useMemo(() => bulkSelectionGuidance(bulkSelectedIds.length, selectionEligibility), [bulkSelectedIds.length, selectionEligibility]);
  // Status tabs use a transition; intake filters flip `loading` while prior tiles remain.
  const intakeBusy = loading && items.length > 0 && !refreshing;
  const filterPreloading = isFilterPending || pendingFilter !== null || intakeBusy;
  const pendingFilterLabel =
    intakeBusy && !isFilterPending && pendingFilter === null
      ? "filtered"
      : (REUP_QUEUE_STATUS_FILTERS.find((entry) => entry.key === (pendingFilter ?? operatorFilter))?.label ?? "queue");

  return (
    <OperatorStudioShell
      actions={primaryActions}
      description="Prepare approved work for export package and manual publish handoff."
      title="Reup Queue"
    >
      <OpsConsolePage>
        {refreshing ? <p className="review-board-refreshing-banner" role="status">Refreshing queue…</p> : null}
        <ReupQueueQuickPathBar
          activeFilter={operatorFilter}
          onFilter={handleOperatorFilterChange}
          onStartAutoReady={() =>
            void applyBatchAction(
              "START_AUTO_PIPELINE",
              items.filter((item) => item.status === "READY_FOR_PROCESSING").map((item) => item.id),
              "bulk:START_AUTO_PIPELINE_RENDER",
              { pipelineMode: "auto_to_render" }
            )
          }
          onStartAutoTtsOnlyReady={() =>
            void applyBatchAction(
              "START_AUTO_PIPELINE",
              items.filter((item) => item.status === "READY_FOR_PROCESSING").map((item) => item.id),
              "bulk:START_AUTO_PIPELINE",
              { pipelineMode: "auto_to_tts" }
            )
          }
          onStartReady={() =>
            void applyBatchAction(
              "START_PROCESSING",
              items.filter((item) => item.status === "READY_FOR_PROCESSING").map((item) => item.id)
            )
          }
          summary={summary}
          working={
            batchWorkingAction === "START_PROCESSING" || batchWorkingAction === "START_AUTO_PIPELINE"
          }
          workingAuto={batchWorkingAction === "START_AUTO_PIPELINE"}
        />
        <ReupQueueStudioFilters
          intake={intake}
          intakeBusy={filterPreloading}
          intakeSessions={intakeSessions}
          onClearIntake={clearIntakeFilters}
          onIntakeChange={applyIntakeChange}
          onSearch={setSearchQuery}
          onSort={handleSortModeChange}
          searchQuery={searchQuery}
          sortMode={sortMode}
        />
        <div className="capture-inbox-review-workspace reup-queue-studio-workspace" data-reup-queue-ui-version={UI_VERSION}>
          <main className="capture-inbox-review-main" aria-busy={loading || refreshing || filterPreloading} aria-label="Reup Queue items">
            <ReupQueueBatchActionBar
              actionableVisibleCount={actionableVisibleCount}
              batchResult={batchResult}
              cancellableVisibleCount={cancellableVisibleItems.length}
              dismissableVisibleCount={dismissableVisibleItems.length}
              eligibility={selectionEligibility}
              guidance={bulkHint}
              mutating={batchWorkingAction !== null || mutatingAction !== null}
              onBatchAction={(action, options) => void applyBatchAction(action, bulkSelectedIds, `bulk:${action}`, options)}
              onCancelVisible={() => void applyBatchAction("CANCEL", cancellableVisibleItems.map((item) => item.id))}
              onClear={() => setSelectedItemIds(new Set())}
              onDismissVisible={() => void applyBatchAction("DISMISS", dismissableVisibleItems.map((item) => item.id))}
              onDismissBatchResult={() => setBatchResult(null)}
              onPurgeVisible={() => void purgeVisibleClearableItems()}
              onSelectActionable={() => setSelectedItemIds(selectAllActionableReupQueueItems(visibleItems))}
              operatorFilter={operatorFilter}
              purgeableVisibleCount={purgeableVisibleItems.length}
              selectedCount={bulkSelectedIds.length}
              visibleCount={visibleItems.length}
              workingAction={batchWorkingAction}
            />

            <AsyncContentBoundary
              emptyState={(
                <WorkGalleryEmptyState
                  action={(
                    <a className="reup-queue-empty-review-link" href={REVIEW_BOARD_HREF}>
                      <WorkItemActionIcon className="reup-queue-empty-review-link__icon" kind="open" />
                      <span>Open Review Board</span>
                    </a>
                  )}
                  className="reup-queue-gallery-empty"
                  detail="Approve candidates in Review Board, then use Send to queue or Approve & send."
                  glyph={(
                    <svg fill="none" height="28" viewBox="0 0 28 28" width="28" xmlns="http://www.w3.org/2000/svg">
                      <rect height="12" rx="2.5" stroke="currentColor" strokeWidth="1.75" width="16" x="6" y="8" />
                      <path d="M10 12h8M10 16h5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.75" />
                      <path d="M9 20.5h10M11 23h6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
                    </svg>
                  )}
                  title="No queued reup work"
                />
              )}
              errorState={<WorkGalleryEmptyState action={<button onClick={() => void loadQueue()} type="button">Retry</button>} detail={error ?? "Unknown error"} eyebrow="Queue unavailable" title="Could not load production work" />}
              refreshing={refreshing}
              skeleton={<WorkGalleryEmptyState detail="Collecting approved downstream work." loading title="Loading Reup Queue" />}
              status={loading && items.length === 0 ? "loading" : error && items.length === 0 ? "error" : items.length === 0 ? "empty" : "success"}
            >
            {!loading && !filterPreloading && visibleItems.length === 0 && items.length > 0 ? (
              <WorkGalleryEmptyState detail="Try another status tab or reset search." eyebrow="Filtered view" title="No items in this view" />
            ) : null}

            {visibleItems.length > 0 || filterPreloading ? (
              <section
                className={`operator-panel capture-inbox-media-gallery reup-queue-gallery-shell is-view-${viewMode}${filterPreloading ? " is-preloading" : ""}`}
                aria-busy={filterPreloading}
                aria-label={viewMode === "worklist" ? "Reup Queue worklist" : "Reup Queue tile gallery"}
              >
                <WorkGalleryHeader
                  actions={(
                    <>
                      <button
                        className="review-board-deck-btn reup-queue-gallery-select-visible"
                        disabled={queuePagerDisabled || filterPreloading || actionableVisibleCount === 0}
                        onClick={() => setSelectedItemIds(selectAllActionableReupQueueItems(visibleItems))}
                        type="button"
                      >
                        <WorkItemActionIcon className="reup-queue-gallery-action__icon" kind="select-visible" />
                        Select visible ({actionableVisibleCount})
                      </button>
                      <WorkViewToggle
                        ariaLabel="Queue view mode"
                        onChange={handleViewModeChange}
                        options={(Object.keys(REUP_QUEUE_VIEW_MODE_LABELS) as ReupQueueViewMode[]).map((mode) => ({ key: mode, label: REUP_QUEUE_VIEW_MODE_LABELS[mode] }))}
                        value={viewMode}
                      />
                    </>
                  )}
                  eyebrow={viewMode === "worklist" ? "Worklist" : "Tile gallery"}
                  meta={filterPreloading ? `Preparing ${pendingFilterLabel} queue items…` : searchQuery.trim() ? `${visibleItems.length.toLocaleString()} search match${visibleItems.length === 1 ? "" : "es"}` : `${visibleItems.length.toLocaleString()} shown · ${totalCount.toLocaleString()} total`}
                  title={viewMode === "worklist" ? "Queue worklist" : "Queue tiles"}
                />
                {filterPreloading ? (
                  <ReupQueueGalleryPreloading statusLabel={pendingFilterLabel} viewMode={viewMode} />
                ) : viewMode === "worklist" ? (
                  <div
                    className={`reup-queue-worklist work-studio-worklist is-rail is-dense is-stage-stack${worklistDragging ? " is-marquee-selecting" : ""}`}
                    ref={worklistSurfaceRef}
                  >
                    {worklistGroups.map((group) => {
                      const collapsed = collapsedWorklistStages.has(group.label);
                      const panelId = worklistStagePanelId(group.label);
                      return (
                        <section className={`reup-queue-stage-group${collapsed ? " is-collapsed" : ""}`} data-tone={group.tone} key={group.label}>
                          <button
                            aria-controls={panelId}
                            aria-expanded={!collapsed}
                            className="reup-queue-stage-heading"
                            onClick={() => toggleWorklistStage(group.label)}
                            title={`${collapsed ? "Show" : "Hide"} ${group.label} queue items`}
                            type="button"
                          >
                            <span aria-hidden="true" className="reup-queue-stage-marker" />
                            <span className="reup-queue-stage-copy">
                              <span className="reup-queue-stage-title">{group.label}</span>
                              <span>{worklistStageGroupHint(group.label, group.tone)}</span>
                            </span>
                            <span className="reup-queue-stage-count" title={`${group.items.length} visible queue item${group.items.length === 1 ? "" : "s"}`}>
                              {group.items.length}
                            </span>
                            <span className="reup-queue-stage-context">{collapsed ? "Show items" : "Hide items"}</span>
                            <svg aria-hidden="true" className="reup-queue-stage-chevron" viewBox="0 0 20 20">
                              <path d="m5.5 7.5 4.5 4.5 4.5-4.5" />
                            </svg>
                          </button>
                          <div aria-label={`${group.label} queue items`} className="reup-queue-stage-items" hidden={collapsed} id={panelId} role="list">
                            {group.items.map((item) => (
                              <ReupQueueWorklistRow
                                focused={activeItemId === item.id}
                                item={item}
                                key={item.id}
                                mutating={batchWorkingAction !== null}
                                onDetails={() => openItemDetails(item.id)}
                                onDismiss={() => void applyQueueAction(item, "DISMISS")}
                                onPrimary={() => void runTilePrimaryAction(item)}
                                onSelectionClick={(modifiers) => handleWorklistRowSelection(item.id, modifiers)}
                                onToggleSelect={(range) => handleWorklistRowSelection(item.id, { additive: !range, range })}
                                pending={queueItemPending(item.id)}
                                selected={selectedItemIds.has(item.id)}
                              />
                            ))}
                          </div>
                        </section>
                      );
                    })}
                    {worklistMarquee ? (
                      <div
                        aria-hidden="true"
                        className="reup-queue-selection-marquee"
                        style={{
                          height: Math.max(0, worklistMarquee.bottom - worklistMarquee.top),
                          left: worklistMarquee.left,
                          top: worklistMarquee.top,
                          width: Math.max(0, worklistMarquee.right - worklistMarquee.left)
                        }}
                      />
                    ) : null}
                  </div>
                ) : (
                <div className="capture-inbox-media-tile-grid">
                  {visibleItems.map((item) => (
                    <ReupQueueMediaTile
                      focused={activeItemId === item.id}
                      item={item}
                      key={item.id}
                      mutating={batchWorkingAction !== null}
                      onDetails={() => openItemDetails(item.id)}
                      onDismiss={() => void applyQueueAction(item, "DISMISS")}
                      onPrimary={() => void runTilePrimaryAction(item)}
                      onToggleSelect={() => setSelectedItemIds((current) => toggleReupQueueSelection(current, item.id))}
                      pending={queueItemPending(item.id)}
                      selected={selectedItemIds.has(item.id)}
                    />
                  ))}
                </div>
                )}
                {!filterPreloading && (totalCount > 0 || items.length > 0) ? (
                  <OffsetLoadMoreFooter
                    ref={loadMoreRef}
                    autoLoad
                    disabled={queuePagerDisabled}
                    loadedCount={items.length}
                    loadingMore={loadingMore}
                    noun="queue items"
                    onLoadMore={loadMoreQueue}
                    pageSize={REUP_QUEUE_LOAD_BATCH_SIZE}
                    totalCount={totalCount}
                    variant="studio"
                  />
                ) : null}
              </section>
            ) : null}
            </AsyncContentBoundary>
          </main>
        </div>

        <ReupQueueRightInspector
          item={activeItem}
          mutatingAction={mutatingAction}
          onApplyAction={(target, action) => void applyQueueAction(target, action)}
          onBatchAction={(action) => void applyBatchAction(action, activeItem ? [activeItem.id] : [])}
          onClose={closeItemDetails}
          open={queueInspectorOpen && Boolean(activeItem)}
        />
      </OpsConsolePage>
    </OperatorStudioShell>
  );
}

function ReupQueueQuickPathBar({
  activeFilter,
  onFilter,
  onStartAutoReady,
  onStartAutoTtsOnlyReady,
  onStartReady,
  summary,
  working,
  workingAuto
}: {
  activeFilter: ReupQueueOperatorFilter;
  onFilter: (filter: ReupQueueOperatorFilter) => void;
  onStartAutoReady: () => void;
  onStartAutoTtsOnlyReady: () => void;
  onStartReady: () => void;
  summary: ReturnType<typeof buildReupQueueSummary>;
  working: boolean;
  workingAuto: boolean;
}) {
  const needsStartCount = summary.needs_start;
  const startBatchCount = Math.min(needsStartCount, REUP_QUEUE_START_PROCESSING_BATCH_LIMIT);
  const startCapped = needsStartCount > REUP_QUEUE_START_PROCESSING_BATCH_LIMIT;
  const heroStats = buildQuickPathHeroStats(summary);

  const pipelineStats = heroStats.filter((stat) => REUP_QUEUE_PIPELINE_FILTERS.includes(stat.key));
  const attentionStats = heroStats.filter((stat) => REUP_QUEUE_ATTENTION_FILTERS.includes(stat.key));

  function renderStat(stat: (typeof heroStats)[number], variant: "pipeline" | "attention") {
    const isActive = activeFilter === stat.key;
    return (
      <button
        aria-pressed={isActive}
        className={`capture-inbox-stat-card is-${variant} is-tone-${stat.tone}${stat.count === 0 ? " is-empty" : ""}${isActive ? " is-active" : ""}`}
        key={stat.key}
        onClick={() => onFilter(stat.key)}
        role="tab"
        type="button"
      >
        <span className="capture-inbox-stat-card__copy">
          <span className="capture-inbox-stat-card__label">{stat.label}</span>
          <strong className="capture-inbox-stat-card__value">{stat.count}</strong>
        </span>
        <ReupQueueStatusStatBars ratio={summary.all > 0 ? stat.count / summary.all : 0} status={stat.key} />
      </button>
    );
  }

  return (
    <WorkStudioDeck
      actions={(
        <div className="capture-inbox-hero-action-rail reup-queue-hero-action-rail" aria-label="Queue shortcuts" role="group">
          <AsyncButton
            className="capture-inbox-hero-action-rail__item is-primary reup-queue-hero-cta"
            disabled={working || needsStartCount === 0}
            leadingIcon={(
              <span aria-hidden="true" className="capture-inbox-hero-action-rail__icon">
                <WorkItemActionIcon className="capture-inbox-hero-action-rail__glyph" kind="auto-render" />
              </span>
            )}
            onClick={onStartAutoReady}
            pending={workingAuto}
            pendingLabel="Starting auto…"
            title={
              needsStartCount === 0
                ? "No clips are ready to start right now"
                : startCapped
                  ? `Safe batch limit ${REUP_QUEUE_START_PROCESSING_BATCH_LIMIT} — auto Download→Render`
                  : "Auto Download → ASR → Translate → TTS → OCR → Render, then just review the finished video"
            }
            type="button"
          >
            {startCapped
              ? `Start auto (${startBatchCount}/${needsStartCount})`
              : `Start auto (${needsStartCount})`}
          </AsyncButton>
          <AsyncButton
            className="capture-inbox-hero-action-rail__item reup-queue-hero-cta"
            disabled={working || needsStartCount === 0}
            leadingIcon={(
              <span aria-hidden="true" className="capture-inbox-hero-action-rail__icon">
                <WorkItemActionIcon className="capture-inbox-hero-action-rail__glyph" kind="auto-run" />
              </span>
            )}
            onClick={onStartAutoTtsOnlyReady}
            pending={false}
            title="Stop after TTS so you can edit transcript or voice before OCR + Render"
            type="button"
          >
            Auto→TTS
          </AsyncButton>
          <AsyncButton
            className="capture-inbox-hero-action-rail__item reup-queue-hero-cta"
            disabled={working || needsStartCount === 0}
            leadingIcon={(
              <span aria-hidden="true" className="capture-inbox-hero-action-rail__icon">
                <WorkItemActionIcon className="capture-inbox-hero-action-rail__glyph" kind="step" />
              </span>
            )}
            onClick={onStartReady}
            pending={working && !workingAuto}
            pendingLabel="Starting…"
            title={needsStartCount === 0 ? "No clips are ready to start right now" : "Manual Start processing (download only)"}
            type="button"
          >
            {startCapped ? `Start manual (${startBatchCount})` : "Start manual"}
          </AsyncButton>
          <a className="capture-inbox-hero-action-rail__item" href={REVIEW_BOARD_HREF}>
            <span aria-hidden="true" className="capture-inbox-hero-action-rail__icon">
              <WorkItemActionIcon className="capture-inbox-hero-action-rail__glyph" kind="open" />
            </span>
            <span className="capture-inbox-hero-action-rail__label">Open Review Board</span>
          </a>
        </div>
      )}
      ariaLabel="Reup Queue quick path"
      className="reup-queue-command-deck reup-queue-hero-panel"
      kicker="Production queue"
    >
      <section className="capture-inbox-status-flow reup-queue-status-flow" aria-label="Reup Queue status flow">
        <div className="capture-inbox-status-flow__lane is-pipeline">
          <div className="capture-inbox-status-flow__lane-head">
            <p className="capture-inbox-status-flow__lane-title">Pipeline</p>
            <p className="capture-inbox-status-flow__lane-meta">Production stages</p>
          </div>
          <div className="capture-inbox-status-flow__track" role="tablist">{pipelineStats.map((stat) => renderStat(stat, "pipeline"))}</div>
        </div>
        <div className="capture-inbox-status-flow__lane is-attention">
          <div className="capture-inbox-status-flow__lane-head">
            <p className="capture-inbox-status-flow__lane-title">Attention</p>
            <p className="capture-inbox-status-flow__lane-meta">Handoff, exceptions, and completed work</p>
          </div>
          <div className="capture-inbox-status-flow__track is-compact" role="tablist">{attentionStats.map((stat) => renderStat(stat, "attention"))}</div>
        </div>
      </section>
    </WorkStudioDeck>
  );
}

const REUP_QUEUE_STATUS_BAR_PATTERNS: Record<ReupQueueOperatorFilter, readonly number[]> = {
  all: [0.88, 0.92, 0.84, 0.94, 0.78],
  download: [0.3, 0.48, 0.66, 0.82, 1],
  transcript: [0.38, 0.62, 0.78, 0.54, 0.9],
  render: [0.42, 0.76, 0.58, 0.92, 0.7],
  export: [0.36, 0.52, 0.72, 0.88, 1],
  handoff: [0.34, 0.5, 0.68, 0.84, 1],
  attention: [0.8, 0.38, 0.7, 0.34, 0.58],
  done: [1, 0.82, 0.64, 0.46, 0.3]
};

function ReupQueueStatusStatBars({ ratio, status }: { ratio: number; status: ReupQueueOperatorFilter }) {
  const clamped = Math.max(0, Math.min(1, ratio));
  const displayRatio = clamped > 0 ? clamped : 0.16;
  return (
    <span aria-hidden="true" className="capture-inbox-stat-card__viz" data-status={status}>
      {REUP_QUEUE_STATUS_BAR_PATTERNS[status].map((slot, index) => (
        <span className="capture-inbox-stat-card__bar" key={index}>
          <span className="capture-inbox-stat-card__bar-fill" style={{ height: `${Math.round(slot * displayRatio * 100)}%` }} />
        </span>
      ))}
    </span>
  );
}

function ReupQueueStudioFilters({
  intake,
  intakeBusy,
  intakeSessions,
  onClearIntake,
  onIntakeChange,
  onSearch,
  onSort,
  searchQuery,
  sortMode
}: {
  intake: IntakeFilterState;
  intakeBusy: boolean;
  intakeSessions: CaptureSession[];
  onClearIntake: () => void;
  onIntakeChange: (partial: Partial<IntakeFilterState>) => void;
  onSearch: (query: string) => void;
  onSort: (sortMode: ReupQueueSortMode) => void;
  searchQuery: string;
  sortMode: ReupQueueSortMode;
}) {
  return (
    <section className="work-studio-filter-deck review-board-filter-deck reup-queue-filter-deck capture-inbox-gallery-filter-deck" aria-label="Queue filters">
      <div className="work-studio-filter-deck__header">
        <div className="work-studio-filter-deck__copy">
          <span className="work-studio-filter-deck__kicker">Tile filters</span>
          <span className="work-studio-filter-deck__title">Search and arrange production work</span>
        </div>
        <span className="reup-queue-filter-deck__hint">Refine the current production lane</span>
      </div>
      <div className="work-studio-filter-deck__query review-board-command-deck-filters reup-queue-filter-controls">
        <label className="review-board-filter-control reup-queue-filter-control is-search">
          <span aria-hidden="true" className="review-board-filter-search-icon reup-queue-filter-search-icon">
            <svg viewBox="0 0 24 24">
              <path d="m20 20-4.4-4.4m2.4-5.1a7.5 7.5 0 1 1-15 0 7.5 7.5 0 0 1 15 0Z" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="2" />
            </svg>
          </span>
          <span className="capture-inbox-sr-only">Search queue items</span>
          <input
            aria-label="Search queue items"
            className="review-board-deck-input review-board-deck-search"
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Search title, source, candidate, package, handoff..."
            type="search"
            value={searchQuery}
          />
        </label>
        <label className="review-board-filter-control reup-queue-filter-control is-sort">
          <span className="review-board-filter-control__label reup-queue-filter-control__label">Sort by</span>
          <select aria-label="Sort queue items" className="review-board-deck-input review-board-deck-sort" onChange={(event) => onSort(event.target.value as ReupQueueSortMode)} value={sortMode}>
            <option value="active-first">Active first</option>
            <option value="newest">Newest</option>
            <option value="ready-first">Ready first</option>
            <option value="needs-attention-first">Needs attention first</option>
            <option value="export-ready-first">Export ready first</option>
          </select>
        </label>
      </div>
      <IntakeFilterRow
        addedLabel="Queued"
        busy={intakeBusy}
        onChange={onIntakeChange}
        onClear={onClearIntake}
        sessions={intakeSessions}
        state={intake}
      />
    </section>
  );
}

function ReupQueueGalleryPreloading({ statusLabel, viewMode }: { statusLabel: string; viewMode: ReupQueueViewMode }) {
  return (
    <div className={`reup-queue-gallery-preloading is-${viewMode}`} role="status" aria-live="polite">
      <div className="reup-queue-gallery-preloading__status">
        <span aria-hidden="true" className="reup-queue-gallery-preloading__spinner" />
        <span className="reup-queue-gallery-preloading__copy">
          <strong>Preparing {statusLabel} queue items</strong>
          <span>Updating the production view while preserving your current workspace…</span>
        </span>
      </div>
      <div aria-hidden="true" className="reup-queue-gallery-preloading__grid">
        {Array.from({ length: viewMode === "worklist" ? 5 : 8 }, (_, index) => (
          <span className="reup-queue-gallery-preloading__item" key={index}>
            <span className="reup-queue-gallery-preloading__media" />
            <span className="reup-queue-gallery-preloading__lines">
              <span />
              <span />
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

function ReupQueueBatchActionBar({
  actionableVisibleCount,
  batchResult,
  cancellableVisibleCount,
  dismissableVisibleCount,
  eligibility,
  guidance,
  mutating,
  onBatchAction,
  onCancelVisible,
  onClear,
  onDismissVisible,
  onDismissBatchResult,
  onPurgeVisible,
  onSelectActionable,
  operatorFilter,
  purgeableVisibleCount,
  selectedCount,
  visibleCount,
  workingAction
}: {
  actionableVisibleCount: number;
  batchResult: BatchOperationResponse | null;
  cancellableVisibleCount: number;
  dismissableVisibleCount: number;
  eligibility: ReturnType<typeof buildSelectionEligibility>;
  guidance: string | null;
  mutating: boolean;
  onBatchAction: (action: ReupQueueBatchAction, options?: { pipelineMode?: ReupPipelineMode }) => void;
  onCancelVisible: () => void;
  onClear: () => void;
  onDismissVisible: () => void;
  onDismissBatchResult: () => void;
  onPurgeVisible: () => void;
  onSelectActionable: () => void;
  operatorFilter: ReupQueueOperatorFilter;
  purgeableVisibleCount: number;
  selectedCount: number;
  visibleCount: number;
  workingAction: ReupQueueBatchAction | null;
}) {
  if (!selectedCount) return null;
  const hasSelection = selectedCount > 0;
  const disabled = mutating;
  const primaryTotal = primaryBulkEligibilityTotal(eligibility);
  const secondaryTotal = secondaryBulkEligibilityTotal(eligibility);
  const showCancelVisible = !hasSelection && supportsBulkCancelVisibleScope(operatorFilter) && cancellableVisibleCount > 0;
  const showDismissVisible = !hasSelection && supportsBulkDismissVisibleScope(operatorFilter) && dismissableVisibleCount > 0;
  const showPurgeVisible = !hasSelection && supportsBulkPurgeVisibleScope(operatorFilter) && purgeableVisibleCount > 0;
  const primaryActionOptions: BulkActionOption[] = [
    {
      key: "START_AUTO_PIPELINE",
      action: "START_AUTO_PIPELINE",
      label: "Start auto",
      count: eligibility.startAuto,
      pipelineMode: "auto_to_render"
    },
    { key: "START_PROCESSING", action: "START_PROCESSING", label: "Start manual", count: eligibility.start },
    { key: "CREATE_EXPORT_PACKAGE", action: "CREATE_EXPORT_PACKAGE", label: "Export", count: eligibility.export },
    { key: "CREATE_PUBLISH_HANDOFF", action: "CREATE_PUBLISH_HANDOFF", label: "Handoff", count: eligibility.handoff }
  ];
  const primaryActions = primaryActionOptions.filter((entry) => entry.count > 0);
  const secondaryActionOptions: BulkActionOption[] = [
    { key: "HOLD", action: "HOLD", label: "Pause", count: eligibility.hold },
    { key: "RESUME", action: "RESUME", label: "Resume", count: eligibility.resume },
    {
      key: "SET_AUTOMATION:auto_to_render",
      action: "SET_AUTOMATION",
      label: "Hand to full auto",
      count: eligibility.setAutomation,
      icon: "auto-render",
      pipelineMode: "auto_to_render"
    },
    {
      key: "SET_AUTOMATION:manual",
      action: "SET_AUTOMATION",
      label: "Take over manually",
      count: eligibility.setAutomation,
      icon: "step",
      pipelineMode: "manual"
    },
    { key: "RETRY", action: "RETRY", label: "Retry", count: eligibility.retry },
    { key: "MARK_MEDIA_READY", action: "MARK_MEDIA_READY", label: "Media ready", count: eligibility.markMediaReady },
    { key: "CANCEL", action: "CANCEL", label: "Cancel", count: eligibility.cancel },
    { key: "DISMISS", action: "DISMISS", label: "Clear", count: eligibility.dismiss }
  ];
  const secondaryActions = secondaryActionOptions.filter((entry) => entry.count > 0);
  const decisionActions = hasSelection && primaryTotal + secondaryTotal > 0 ? [...primaryActions, ...secondaryActions] : [];
  const compactGuidance = hasSelection
    ? guidance ?? `${selectedCount} selected item${selectedCount === 1 ? "" : "s"} can run a bulk action.`
    : `${actionableVisibleCount} of ${visibleCount} visible item${visibleCount === 1 ? "" : "s"} can run a bulk action.`;

  return (
    <div className="reup-queue-bulk-stack is-sticky">
      <WorkBulkActionBar
        active={hasSelection}
        ariaLabel="Bulk queue actions"
        className="review-board-command-deck-bulk review-board-bulk-command-bar reup-queue-bulk-command-bar"
        guidance={compactGuidance}
        selectedCount={selectedCount}
        toolbar={(
          hasSelection ? (
            <button className="review-board-deck-btn is-ghost reup-queue-bulk-btn" disabled={disabled} onClick={onClear} type="button">
              <WorkItemActionIcon className="review-board-bulk-action__icon" kind="clear-selection" />
              Clear
            </button>
          ) : (
            <button className="review-board-deck-btn reup-queue-bulk-btn is-queue-primary" disabled={disabled || actionableVisibleCount === 0} onClick={onSelectActionable} type="button">
              <WorkItemActionIcon className="review-board-bulk-action__icon" kind="select-visible" />
              Select actionable{actionableVisibleCount > 0 ? ` (${actionableVisibleCount})` : ""}
            </button>
          )
        )}
      >
        <div className="reup-queue-bulk-actions">
          {!hasSelection && showCancelVisible ? (
            <AsyncButton
              className="review-board-deck-btn reup-queue-bulk-btn is-queue-danger"
              disabled={disabled || workingAction !== null}
              leadingIcon={<WorkItemActionIcon className="review-board-bulk-action__icon" kind="reject" />}
              onClick={onCancelVisible}
              pending={workingAction === "CANCEL"}
              pendingLabel="Cancelling…"
              type="button"
            >
              Cancel visible ({cancellableVisibleCount})
            </AsyncButton>
          ) : null}
          {!hasSelection && showDismissVisible ? (
            <AsyncButton
              className="review-board-deck-btn reup-queue-bulk-btn is-queue-neutral"
              disabled={disabled || workingAction !== null}
              leadingIcon={<WorkItemActionIcon className="review-board-bulk-action__icon" kind="dismiss" />}
              onClick={onDismissVisible}
              pending={workingAction === "DISMISS"}
              pendingLabel="Clearing…"
              type="button"
            >
              Clear visible ({dismissableVisibleCount})
            </AsyncButton>
          ) : null}
          {!hasSelection && showPurgeVisible ? (
            <AsyncButton
              className="review-board-deck-btn reup-queue-bulk-btn is-queue-danger"
              disabled={disabled || workingAction !== null}
              leadingIcon={<WorkItemActionIcon className="review-board-bulk-action__icon" kind="delete" />}
              onClick={onPurgeVisible}
              pending={workingAction === "PURGE"}
              pendingLabel="Deleting…"
              type="button"
            >
              Delete permanently ({purgeableVisibleCount})
            </AsyncButton>
          ) : null}
          {decisionActions.map((entry) => (
            <AsyncButton
              className={`review-board-deck-btn reup-queue-bulk-btn ${bulkActionButtonTone(entry.action)}`}
              disabled={disabled || entry.count === 0 || (workingAction !== null && workingAction !== entry.action)}
              key={entry.key}
              leadingIcon={(
                <WorkItemActionIcon
                  className="review-board-bulk-action__icon"
                  kind={entry.icon ?? bulkActionIconKind(entry.action)}
                />
              )}
              onClick={() => onBatchAction(entry.action, entry.pipelineMode ? { pipelineMode: entry.pipelineMode } : undefined)}
              pending={workingAction === entry.action}
              pendingLabel={`${entry.label}…`}
              type="button"
            >
              {entry.label} ({entry.count})
            </AsyncButton>
          ))}
        </div>
      </WorkBulkActionBar>
      {batchResult ? <BatchResultPanel onDismiss={onDismissBatchResult} result={batchResult} /> : null}
    </div>
  );
}

type BulkActionOption = {
  key: string;
  action: ReupQueueBatchAction;
  label: string;
  count: number;
  icon?: WorkItemActionIconKind;
  pipelineMode?: ReupPipelineMode;
};

function bulkActionIconKind(action: ReupQueueBatchAction): WorkItemActionIconKind {
  if (action === "START_PROCESSING" || action === "START_AUTO_PIPELINE" || action === "RESUME") return "process";
  if (action === "CREATE_EXPORT_PACKAGE" || action === "CREATE_PUBLISH_HANDOFF") return "send";
  if (action === "HOLD") return "pause";
  if (action === "RETRY") return "retry";
  if (action === "MARK_MEDIA_READY") return "approve";
  if (action === "DISMISS") return "dismiss";
  if (action === "PURGE") return "delete";
  return "reject";
}

function bulkActionButtonTone(action: ReupQueueBatchAction): string {
  if (action === "START_AUTO_PIPELINE" || action === "START_PROCESSING" || action === "RESUME") return "is-queue-primary";
  if (action === "CREATE_EXPORT_PACKAGE" || action === "CREATE_PUBLISH_HANDOFF") return "is-queue-info";
  if (action === "MARK_MEDIA_READY") return "is-queue-success";
  if (action === "HOLD" || action === "RETRY") return "is-queue-warning";
  if (action === "CANCEL" || action === "PURGE") return "is-queue-danger";
  return "is-queue-neutral";
}

type ReupQueueWorklistGroup = {
  items: ReupQueueItem[];
  label: string;
  tone: ReturnType<typeof worklistStageTone>;
};

const WORKLIST_STAGE_TONE_PRIORITY: Record<ReupQueueWorklistGroup["tone"], number> = {
  danger: 5,
  active: 4,
  warn: 3,
  good: 2,
  muted: 1
};

function groupReupQueueWorklistItems(items: ReupQueueItem[]): ReupQueueWorklistGroup[] {
  const groups = new Map<string, ReupQueueWorklistGroup>();

  for (const item of items) {
    const label = worklistStageLabel(item);
    const tone = worklistStageTone(item);
    const current = groups.get(label);
    if (!current) {
      groups.set(label, { items: [item], label, tone });
      continue;
    }

    current.items.push(item);
    if (WORKLIST_STAGE_TONE_PRIORITY[tone] > WORKLIST_STAGE_TONE_PRIORITY[current.tone]) {
      current.tone = tone;
    }
  }

  return [...groups.values()];
}

function worklistStageGroupHint(label: string, tone: ReupQueueWorklistGroup["tone"]): string {
  if (label === "No dialogue") return "Skip dubbing and continue";
  if (label === "Transcript ready") return "Ready for review";
  if (tone === "danger") return "Recovery needed";
  if (tone === "active") return "In progress";
  if (tone === "warn") return "Operator check";
  if (tone === "good") return "Ready for action";
  return "Paused or finished";
}

function worklistStagePanelId(label: string): string {
  const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `reup-queue-stage-${slug || "items"}`;
}

function clientPointToDocument(point: SelectionPoint): SelectionPoint {
  return { x: point.x + window.scrollX, y: point.y + window.scrollY };
}

function pageDragTargetBlocksMarquee(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return Boolean(target.closest("input:not([type='checkbox']):not([type='radio']), textarea, select, [contenteditable='true']"));
}

function readWorklistSelectionEntries(surface: HTMLDivElement): SelectionRectEntry[] {
  return Array.from(surface.querySelectorAll<HTMLElement>('[data-queue-item-id][data-selectable="true"]')).map((element) => {
    const bounds = element.getBoundingClientRect();
    return {
      id: element.dataset.queueItemId ?? "",
      rect: {
        bottom: bounds.bottom + window.scrollY,
        left: bounds.left + window.scrollX,
        right: bounds.right + window.scrollX,
        top: bounds.top + window.scrollY
      }
    };
  }).filter((entry) => entry.id.length > 0);
}

function worklistTargetIsInteractive(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return Boolean(target.closest("button, a, input, label, select, textarea, [role='button']"));
}

function ReupQueueWorklistRow({
  focused,
  item,
  mutating,
  onDetails,
  onDismiss,
  onPrimary,
  onSelectionClick,
  onToggleSelect,
  pending,
  selected
}: {
  focused: boolean;
  item: ReupQueueItem;
  mutating: boolean;
  onDetails: () => void;
  onDismiss: () => void;
  onPrimary: () => void;
  onSelectionClick: (modifiers: { additive: boolean; range: boolean }) => void;
  onToggleSelect: (range: boolean) => void;
  pending: boolean;
  selected: boolean;
}) {
  const thumbnailUrl = queueTileThumbnailUrl(item);
  const stageTone = worklistStageTone(item);
  const selectable = hasAnyBatchEligibility(item);
  const downloadProgress = downloadJobProgressPercent(item);
  const dismissAction = terminalQueueDismissAction(item);
  const primaryAction = primaryQueueAction(item);
  const showPrimaryAction = primaryAction !== null && primaryAction !== "inspect";
  const primaryLabel = primaryQueueActionLabel(item);
  const buttonTone = queueTilePrimaryButtonTone(item);
  const primaryTone = buttonTone === "recover" ? "is-recover" : buttonTone === "forward" ? "is-primary" : "is-quiet";
  const primaryIconKind = worklistPrimaryIconKind(item);
  const transcriptHref = worklistTranscriptHref(item);

  return (
    <article
      className={`reup-queue-worklist-row work-studio-worklist-row ${selected ? "is-bulk-selected" : ""} ${focused ? "is-inspector-focused" : ""} ${!selectable ? "is-terminal-queue-tile" : ""}`}
      data-queue-item-id={item.id}
      data-selectable={selectable ? "true" : "false"}
      data-tone={stageTone}
      onClick={(event) => {
        if (!selectable || worklistTargetIsInteractive(event.target)) return;
        onSelectionClick({ additive: event.ctrlKey || event.metaKey, range: event.shiftKey });
      }}
      role="listitem"
    >
      <div className="reup-queue-worklist-select">
        {selectable ? (
          <label className={`reup-queue-worklist-check ${selected ? "is-selected" : ""}`} title={selected ? "Deselect for bulk actions" : "Select for bulk actions"}>
            <input
              aria-label={selected ? "Deselect queue item" : "Select queue item"}
              checked={selected}
              onChange={(event) => onToggleSelect(Boolean((event.nativeEvent as globalThis.MouseEvent).shiftKey))}
              type="checkbox"
            />
          </label>
        ) : (
          <span className="reup-queue-worklist-select-spacer" aria-hidden="true" />
        )}
      </div>
      <button className="reup-queue-worklist-thumb" onClick={onDetails} type="button">
        {thumbnailUrl ? <img alt="" src={thumbnailUrl} /> : <span className="reup-queue-worklist-thumb-fallback">—</span>}
      </button>
      <div className="reup-queue-worklist-main">
        <button className="link-button reup-queue-worklist-title" onClick={onDetails} title={itemTitle(item)} type="button">
          <span className="reup-queue-worklist-title-text">{itemTitle(item)}</span>
        </button>
      </div>
      {downloadProgress != null ? (
        <div
          className="reup-queue-worklist-status-col has-progress"
          title={item.job_id ? `${(item.job_type ?? "JOB").toUpperCase()} · ${item.job_status ?? "unknown"} · ${item.job_id.slice(0, 8)}` : undefined}
        >
          <WorklistProgressRing percent={downloadProgress} tone={stageTone} />
        </div>
      ) : null}
      <div className="reup-queue-worklist-actions">
        {transcriptHref ? (
          <a className="reup-queue-worklist-action is-primary is-with-icon" href={transcriptHref}>
            <WorkItemActionIcon className="reup-queue-worklist-action__icon" kind="transcript" />
            Transcript
          </a>
        ) : null}
        {dismissAction ? (
          <AsyncButton className="reup-queue-worklist-action is-quiet is-with-icon" disabled={mutating} leadingIcon={<WorkItemActionIcon className="reup-queue-worklist-action__icon" kind="dismiss" />} onClick={onDismiss} pending={pending} pendingLabel="Dismissing…" type="button">
            Dismiss
          </AsyncButton>
        ) : null}
        {showPrimaryAction && !transcriptHref ? (
          <AsyncButton className={`reup-queue-worklist-action ${primaryTone} is-with-icon`} disabled={mutating} leadingIcon={<WorkItemActionIcon className="reup-queue-worklist-action__icon" kind={primaryIconKind} />} onClick={onPrimary} pending={pending} pendingLabel="Working…" type="button">
            {primaryLabel}
          </AsyncButton>
        ) : null}
      </div>
    </article>
  );
}

function WorklistProgressRing({ percent, tone }: { percent: number; tone: string }) {
  const radius = 15;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(100, percent));
  const offset = circumference - (clamped / 100) * circumference;

  return (
    <div
      aria-label={`Download progress ${clamped} percent`}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={clamped}
      className={`reup-queue-worklist-progress-ring is-${tone}`}
      role="progressbar"
    >
      <svg aria-hidden="true" className="reup-queue-worklist-progress-ring-svg" viewBox="0 0 36 36">
        <circle className="reup-queue-worklist-progress-ring-track" cx="18" cy="18" r={radius} />
        <circle
          className="reup-queue-worklist-progress-ring-fill"
          cx="18"
          cy="18"
          r={radius}
          style={{ strokeDasharray: circumference, strokeDashoffset: offset }}
        />
      </svg>
      <span className="reup-queue-worklist-progress-ring-value">{clamped}%</span>
    </div>
  );
}

function worklistPrimaryIconKind(item: ReupQueueItem): WorkItemActionIconKind {
  const action = primaryQueueAction(item);
  if (action === "HOLD") return "pause";
  if (action === "RESUME" || action === "START_PROCESSING" || action === "MARK_MEDIA_READY") return "process";
  if (action === "RETRY") return "retry";
  if (action === "DISMISS") return "dismiss";
  if (action === "CREATE_EXPORT_PACKAGE" || action === "CREATE_PUBLISH_HANDOFF") return "send";
  if (action === "inspect") return "details";
  return "process";
}

function ReupQueueMediaTile({
  focused,
  item,
  mutating,
  onDetails,
  onDismiss,
  onPrimary,
  onToggleSelect,
  pending,
  selected
}: {
  focused: boolean;
  item: ReupQueueItem;
  mutating: boolean;
  onDetails: () => void;
  onDismiss: () => void;
  onPrimary: () => void;
  onToggleSelect: () => void;
  pending: boolean;
  selected: boolean;
}) {
  const thumbnailUrl = queueTileThumbnailUrl(item);
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const publishHandoffId = metadataString(item.metadata_json, "publish_handoff_id");
  const stageTone = queueStageTone(item);
  const selectable = hasAnyBatchEligibility(item);
  const pipelineStages = buildPipelineStages(item);
  const downloadProgress = downloadJobProgressPercent(item);
  const dismissAction = terminalQueueDismissAction(item);
  const secondaryLinks = buildQueueTileSecondaryLinks(item);
  const primaryAction = primaryQueueAction(item);
  const showPrimaryAction = primaryAction !== null && primaryAction !== "inspect";
  const primaryLabel = primaryQueueActionLabel(item);
  const primaryButtonClass = queueTilePrimaryButtonClassName(item);
  const transcriptCta = queueTileTranscriptCta(item);
  const recoveryLink = pipelineFailureRecoveryLink(item);
  const failureAlert = queueTileFailureAlert(item);
  const failureStrip = queueTileFailureStrip(item);
  const nextStepHint = failureAlert ? null : queueTileNextStepHint(item);
  const showOpenDetails = shouldShowQueueTileDetailsButton(item);
  const scoreBadge = useQueueTileScoreBadge(item);
  const { notify } = useNotice();
  const [revealingDownload, setRevealingDownload] = useState(false);

  async function revealDownloadedVideo() {
    if (revealingDownload) return;
    setRevealingDownload(true);
    try {
      await revealSourceVideoLocalAsset(item.source_video_id);
      notify({ id: `queue-reveal-${item.id}`, message: "Opened downloaded video in Explorer.", tone: "success" });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not open the downloaded video.";
      notify({ id: `queue-reveal-${item.id}`, message, tone: "error" });
    } finally {
      setRevealingDownload(false);
    }
  }

  return (
    <article
      className={`capture-inbox-media-tile capture-inbox-compact-card reup-queue-media-tile ${selected ? "is-bulk-selected" : ""} ${focused ? "is-inspector-focused" : ""} ${!selectable ? "is-terminal-queue-tile" : ""}`}
      data-tone={stageTone}
    >
      <div className="capture-inbox-media-frame">
        <button className="capture-inbox-media-thumbnail" onClick={onDetails} type="button">
          {thumbnailUrl ? (
            <img alt={`Thumbnail for ${itemTitle(item)}`} src={thumbnailUrl} />
          ) : (
            <span className="capture-inbox-thumbnail-placeholder"><strong>No thumbnail</strong><small>{queueStageLabel(item)}</small></span>
          )}
        </button>
        <WorkMediaTileOverlay
          onToggleSelect={onToggleSelect}
          scoreBadge={scoreBadge}
          scoreBadgeClassName="reup-queue-score-badge"
          selectAriaLabel={selected ? "Deselect queue item" : "Select queue item"}
          selectTitle={selected ? "Deselect for bulk actions" : "Select for bulk actions"}
          selectable={selectable}
          selected={selected}
          statusChips={[
            { label: queueStageLabel(item), tone: stageTone },
            ...(pipelineStepChipLabel(item)
              ? [{ label: pipelineStepChipLabel(item)!, tone: "ready" as const }]
              : []),
            ...(pipelineRecipeChipLabel(item)
              ? [{ label: pipelineRecipeChipLabel(item)!, tone: "ready" as const }]
              : [])
          ]}
        />
        {failureStrip ? (
          <p className="reup-queue-tile-failure-strip" title={failureStrip.detail}>
            <span aria-hidden="true" className="reup-queue-tile-failure-strip__icon">
              <svg viewBox="0 0 16 16">
                <circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" strokeWidth="1.4" />
                <path d="M8 4.75v4.1" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.5" />
                <circle cx="8" cy="11.15" r="0.85" fill="currentColor" />
              </svg>
            </span>
            <span className="reup-queue-tile-failure-strip__text">{failureStrip.message}</span>
          </p>
        ) : downloadProgress != null ? (
          <div
            aria-label={`Download progress ${downloadProgress} percent`}
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={downloadProgress}
            className="reup-queue-download-progress"
            role="progressbar"
          >
            <span className="reup-queue-download-progress-fill" style={{ width: `${downloadProgress}%` }} />
            <span className="reup-queue-download-progress-label">{downloadProgress}%</span>
          </div>
        ) : null}
      </div>
      <div className={`capture-inbox-tile-main capture-inbox-compact-main${failureAlert ? " is-queue-failed" : ""}`}>
        <button
          className={`link-button capture-inbox-tile-title${failureAlert ? " is-muted-failed" : ""}`}
          onClick={onDetails}
          title={itemTitle(item)}
          type="button"
        >
          {itemTitle(item)}
        </button>
        <p className="capture-inbox-tile-meta-line" aria-label="Duration and posted">
          <span className="capture-inbox-tile-meta-stat" title={`Duration: ${queueTileDurationLabel(item)}`}>
            <span aria-hidden="true" className="capture-inbox-tile-perf-stat-icon">
                <CaptureInboxFilterChipIcon className="capture-inbox-tile-perf-stat-icon__glyph" kind="meta-duration" />
            </span>
            <span className="capture-inbox-tile-meta-copy">
              <span className="capture-inbox-tile-meta-label">Duration</span>
              <span className="capture-inbox-tile-meta-value">{queueTileDurationLabel(item)}</span>
            </span>
          </span>
          <span className="capture-inbox-tile-meta-stat" title={`Posted: ${queueTilePostedLabel(item)}`}>
            <span aria-hidden="true" className="capture-inbox-tile-perf-stat-icon">
                <CaptureInboxFilterChipIcon className="capture-inbox-tile-perf-stat-icon__glyph" kind="meta-posted" />
            </span>
            <span className="capture-inbox-tile-meta-copy">
              <span className="capture-inbox-tile-meta-label">Posted</span>
              <span className="capture-inbox-tile-meta-value">{queueTilePostedLabel(item)}</span>
            </span>
          </span>
        </p>
        {(exportPackageId || publishHandoffId) ? (
          <p className="reup-queue-tile-handoff-note">
            {exportPackageId ? "Export package linked" : null}
            {exportPackageId && publishHandoffId ? " · " : null}
            {publishHandoffId ? "Handoff linked" : null}
          </p>
        ) : null}
      </div>
      <div className="reup-queue-tile-bottom">
        <div className="reup-queue-pipeline-strip is-tile" aria-label="Production pipeline progress">
          <ol className="reup-queue-pipeline-stepper">
            {pipelineStages.map((stage, index) => {
              const interaction = pipelineStageInteraction(item, stage);
              const interactive = interaction.kind !== "disabled";
              const stepClass = `reup-queue-pipeline-stepper__step is-${stage.state} ${interactive ? "is-interactive" : "is-disabled"}`;
              const node = (
                <>
                  <span aria-hidden="true" className="reup-queue-pipeline-stepper__node">
                    {stage.state === "done" ? (
                      <svg className="reup-queue-pipeline-stepper__check" viewBox="0 0 16 16">
                        <path d="M3.5 8.2 6.4 11l6.1-6.4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
                      </svg>
                    ) : stage.state === "failed" ? (
                      <svg className="reup-queue-pipeline-stepper__fail" viewBox="0 0 16 16">
                        <path d="M4.5 4.5 11.5 11.5M11.5 4.5 4.5 11.5" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
                      </svg>
                    ) : (
                      <span className="reup-queue-pipeline-stepper__index">{index + 1}</span>
                    )}
                  </span>
                  <span className="reup-queue-pipeline-stepper__label">{stage.label}</span>
                  <span className="capture-inbox-sr-only">{stage.label}: {stage.state}</span>
                </>
              );

              if (interaction.kind === "href") {
                return (
                  <li className={stepClass} key={stage.key}>
                    <a className="reup-queue-pipeline-stepper__hit" href={interaction.href} rel="noopener noreferrer" target="_blank" title={interaction.title}>
                      {node}
                    </a>
                  </li>
                );
              }

              if (interaction.kind === "reveal-download") {
                return (
                  <li className={stepClass} key={stage.key}>
                    <button
                      className="reup-queue-pipeline-stepper__hit"
                      disabled={revealingDownload}
                      onClick={() => void revealDownloadedVideo()}
                      title={interaction.title}
                      type="button"
                    >
                      {node}
                    </button>
                  </li>
                );
              }

              return (
                <li className={stepClass} key={stage.key}>
                  <span className="reup-queue-pipeline-stepper__hit is-static" title={interaction.title}>
                    {node}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
        {nextStepHint ? <p className="reup-queue-tile-stage-hint">{nextStepHint}</p> : null}
        {secondaryLinks.length > 0 || dismissAction || showPrimaryAction || recoveryLink || transcriptCta || showOpenDetails ? (
          <div className="capture-inbox-tile-footer capture-inbox-compact-actions">
            {secondaryLinks.length > 0 ? (
              <div className="reup-queue-tile-quick-links" aria-label="Workflow shortcuts">
                {secondaryLinks.map((link) => (
                  <a
                    className="reup-queue-tile-quick-link"
                    href={link.href}
                    key={link.href}
                    rel={link.external ? "noreferrer" : undefined}
                    target={link.external ? "_blank" : undefined}
                  >
                    {link.label}
                  </a>
                ))}
              </div>
            ) : null}
            {dismissAction || showPrimaryAction || recoveryLink || transcriptCta || showOpenDetails ? (
              <div
                aria-label="Queue item actions"
                className="review-board-tile-action-bar review-board-tile-action-grid is-tile reup-queue-tile-action-bar"
              >
                <div className="review-board-tile-action-primary">
                  {dismissAction ? (
                    <AsyncButton
                      className="review-board-tile-btn is-muted"
                      disabled={mutating}
                      leadingIcon={<WorkItemActionIcon kind="dismiss" />}
                      onClick={onDismiss}
                      pending={pending}
                      pendingLabel="Dismissing…"
                      title="Hide this item from Reup Queue"
                      type="button"
                    >
                      Dismiss
                    </AsyncButton>
                  ) : recoveryLink ? (
                    <a
                      className="review-board-tile-btn is-primary is-promoted-open"
                      href={recoveryLink.href}
                      title={recoveryLink.detail}
                    >
                      <WorkItemActionIcon kind="open" />
                      {recoveryLink.label}
                    </a>
                  ) : transcriptCta ? (
                    <a
                      className="review-board-tile-btn is-primary is-promoted-open reup-queue-tile-transcript-cta"
                      href={transcriptCta.href}
                      rel="noopener noreferrer"
                      target="_blank"
                      title="Open transcript editor"
                    >
                      <WorkItemActionIcon kind="transcript" />
                      Open Transcript
                    </a>
                  ) : showPrimaryAction ? (
                    <AsyncButton
                      className={primaryButtonClass}
                      disabled={mutating}
                      leadingIcon={<WorkItemActionIcon kind={worklistPrimaryIconKind(item)} />}
                      onClick={onPrimary}
                      pending={pending}
                      pendingLabel="Working…"
                      type="button"
                    >
                      {primaryLabel}
                    </AsyncButton>
                  ) : (
                    <button
                      className="review-board-tile-btn is-muted"
                      onClick={onDetails}
                      title="Open production details"
                      type="button"
                    >
                      <WorkItemActionIcon kind="open" />
                      Open details
                    </button>
                  )}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function ReupQueueRightInspector({
  item,
  mutatingAction,
  onApplyAction,
  onBatchAction,
  onClose,
  open
}: {
  item: ReupQueueItem | null;
  mutatingAction: ReupQueueAction | null;
  onApplyAction: (item: ReupQueueItem, action: ReupQueueAction) => void;
  onBatchAction: (action: ReupQueueBatchAction) => void;
  onClose: () => void;
  open: boolean;
}) {
  return (
    <WorkItemDetailsDrawer
      eyebrow="Queue item inspector"
      footer={item ? (
        <ReupQueueInspectorActions item={item} mutatingAction={mutatingAction} onApplyAction={onApplyAction} onBatchAction={onBatchAction} />
      ) : null}
      open={open}
      title="Production details"
      titleId="reup-queue-details-title"
      onClose={onClose}
    >
      <QueueDetailPanel item={item} mutatingAction={mutatingAction} onApplyAction={onApplyAction} onBatchAction={onBatchAction} />
    </WorkItemDetailsDrawer>
  );
}

function QueueDetailPanel({
  item,
  mutatingAction,
  onApplyAction,
  onBatchAction
}: {
  item: ReupQueueItem | null;
  mutatingAction: ReupQueueAction | null;
  onApplyAction: (item: ReupQueueItem, action: ReupQueueAction) => void;
  onBatchAction: (action: ReupQueueBatchAction) => void;
}) {
  if (!item) {
    return <p className="reup-queue-inspector-empty">Select a queue tile to inspect downstream readiness, source links, errors, and future job references.</p>;
  }

  const source = item.source_video;
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const publishHandoffId = metadataString(item.metadata_json, "publish_handoff_id");
  const thumbnailUrl = queueTileThumbnailUrl(item);
  const engagementStats = buildQueueInspectorEngagementStats(item);
  const inspectorStats: Array<{ icon: CaptureInboxFilterChipIconKind; label: string; value: string }> = [
    { icon: "meta-complete", label: "Status", value: operatorStatusLabel(item.status) },
    { icon: "lane-metadata-health", label: "Queue stage", value: queueStageLabel(item) },
    { icon: "meta-actionable", label: "Next action", value: item.next_action || "Needs action" },
    { icon: "perf-rates", label: "Priority", value: String(item.priority) },
    { icon: "meta-duration", label: "Progress", value: typeof item.job_progress_percent === "number" ? `${item.job_progress_percent}%` : "Not running" },
    { icon: "lane-captured", label: "Worker job", value: item.job_id ? formatJobChipLabel(item) ?? item.job_status ?? "Attached" : "Not attached" }
  ];

  return (
    <div className="reup-queue-inspector">
      <section className="reup-queue-inspector-summary-card" aria-label="Queue item summary">
        <div className="reup-queue-inspector-media">
          {thumbnailUrl ? <img alt={`Thumbnail for ${itemTitle(item)}`} src={thumbnailUrl} /> : <span aria-hidden="true">No preview</span>}
        </div>
        <div className="reup-queue-inspector-summary">
          <div className="reup-queue-inspector-summary-topline">
            <span className={`review-board-tile-status-chip is-${queueStageTone(item)}`}>{queueStageLabel(item)}</span>
            <span className="reup-queue-inspector-priority">Priority {item.priority}</span>
          </div>
          <p className="reup-queue-inspector-caption">{itemTitle(item)}</p>
          <div className="reup-queue-inspector-next">
            <span>Next action</span>
            <strong>{item.next_action || "Needs action"}</strong>
          </div>
          {typeof item.job_progress_percent === "number" ? (
            <div className="reup-queue-inspector-progress" aria-label={`Worker progress ${item.job_progress_percent}%`}>
              <span style={{ width: `${Math.max(0, Math.min(100, item.job_progress_percent))}%` }} />
            </div>
          ) : null}
        </div>
      </section>

      <section className="reup-queue-inspector-metadata" aria-labelledby="reup-queue-inspector-metadata-title">
        <div className="reup-queue-inspector-section-heading">
          <div>
            <span>Production</span>
            <h3 id="reup-queue-inspector-metadata-title">Queue overview</h3>
          </div>
          <small>Authoritative queue values</small>
        </div>
        <div className="reup-queue-inspector-metadata-grid">
          {inspectorStats.map((stat) => (
            <article className="reup-queue-inspector-stat" key={stat.label}>
              <span aria-hidden="true" className="reup-queue-inspector-stat__icon">
                <CaptureInboxFilterChipIcon kind={stat.icon} />
              </span>
              <span className="reup-queue-inspector-stat__copy">
                <small>{stat.label}</small>
                <strong>{stat.value}</strong>
              </span>
            </article>
          ))}
        </div>
      </section>

      <section className="reup-queue-inspector-metadata" aria-labelledby="reup-queue-inspector-engagement-title">
        <div className="reup-queue-inspector-section-heading">
          <div>
            <span>Source</span>
            <h3 id="reup-queue-inspector-engagement-title">Source engagement</h3>
          </div>
          <small>Captured social metrics</small>
        </div>
        <div className="reup-queue-inspector-metadata-grid">
          {engagementStats.map((stat) => (
            <article className="reup-queue-inspector-stat" key={stat.label}>
              <span aria-hidden="true" className="reup-queue-inspector-stat__icon">
                <CaptureInboxFilterChipIcon kind={stat.icon} />
              </span>
              <span className="reup-queue-inspector-stat__copy">
                <small>{stat.label}</small>
                <strong>{stat.value}</strong>
              </span>
            </article>
          ))}
        </div>
      </section>

      <section className="reup-queue-inspector-detail-grid" aria-label="Queue operational details">
        <article className="reup-queue-inspector-detail-card is-wide">
          <div className="reup-queue-inspector-card-heading">
            <span>Workflow</span>
            <h3>Production pipeline</h3>
          </div>
          <div className="reup-queue-pipeline-strip reup-queue-pipeline-strip-detail" aria-label="Pipeline progress">
            {buildPipelineStages(item).map((stage) => (
              <span className={`reup-queue-pipeline-step is-${stage.state}`} key={stage.key}>{stage.label}</span>
            ))}
          </div>
        </article>

        <article className="reup-queue-inspector-detail-card">
          <div className="reup-queue-inspector-card-heading">
            <span>Timeline</span>
            <h3>Queue lifecycle</h3>
          </div>
          <OpsMetadataList items={[
            { label: "Queued", value: formatDateTime(item.queued_at) },
            { label: "Started", value: formatDateTime(item.started_at) },
            { label: "Held", value: formatDateTime(item.held_at) },
            { label: "Completed", value: formatDateTime(item.completed_at) },
            { label: "Last action", value: item.last_action ? actionLabel(item.last_action) : "No operator action yet" },
            { label: "Action note", value: item.last_action_note ?? "No note recorded" }
          ]} />
        </article>

        <article className="reup-queue-inspector-detail-card">
          <div className="reup-queue-inspector-card-heading">
            <span>Worker</span>
            <h3>Media prep</h3>
          </div>
          <OpsMetadataList items={[
            { label: "Status", value: operatorStatusLabel(item.media_prep_status) },
            { label: "Media-prep notes", value: item.media_prep_notes ?? "Not prepared yet" },
            { label: "Media ready", value: formatDateTime(item.media_ready_at) },
            { label: "Linked job", value: item.job_id ? `${(item.job_type ?? "JOB").toUpperCase()} · ${formatJobChipLabel(item) ?? item.job_status ?? "Attached"}` : "No worker job attached yet" },
            { label: "Render output", value: item.render_output_id ?? "Not rendered yet" },
            { label: "Publish draft", value: item.publish_draft_id ?? "No publish draft yet" },
            { label: "Job error", value: item.job_error_message ?? item.job_error_code ?? item.last_error_message ?? "No job error" }
          ]} />
        </article>

        <article className="reup-queue-inspector-detail-card">
          <div className="reup-queue-inspector-card-heading">
            <span>Origin</span>
            <h3>Source / review origin</h3>
          </div>
          <OpsMetadataList items={[
            { label: "Source video", value: item.source_video_id },
            { label: "External source", value: source?.source_video_external_id ?? "Not captured" },
            { label: "Source profile", value: source?.source_profile_id ?? "Not captured" },
            { label: "Candidate", value: item.video_candidate_id },
            { label: "Queued reason", value: item.queued_reason ?? "Review Board approved" },
            { label: "Operator note", value: item.operator_note ?? "No note recorded" }
          ]} />
        </article>

        <article className="reup-queue-inspector-detail-card">
          <div className="reup-queue-inspector-card-heading">
            <span>Delivery</span>
            <h3>Export &amp; handoff</h3>
          </div>
          <OpsMetadataList items={[
            { label: "Export Package", value: exportPackageId ? <a href={`/publishing/export-packages/${exportPackageId}`}>Open package</a> : item.status === "READY_TO_EXPORT" ? "Ready to create" : "Not packaged" },
            { label: "Publish Handoff", value: publishHandoffId ? <a href={`/publishing/publish-handoffs/${publishHandoffId}`}>Open handoff</a> : item.status === "READY_TO_PUBLISH" ? "Ready to create" : "No handoff" },
            { label: "Automation", value: "Not triggered here" }
          ]} />
        </article>

        <details className="reup-queue-inspector-diagnostics">
          <summary>Diagnostics</summary>
          <OpsMetadataList items={[
            { label: "Blocked reason", value: item.blocked_reason ?? "No blocked reason recorded" },
            { label: "Blocked at", value: formatDateTime(item.blocked_at) },
            { label: "Failed at", value: formatDateTime(item.failed_at) },
            { label: "Cancelled at", value: formatDateTime(item.cancelled_at) },
            { label: "Last error", value: item.last_error_message ?? item.last_error_code ?? "No error recorded" }
          ]} />
          <details>
            <summary>View raw queue details</summary>
            <pre>{JSON.stringify(item, null, 2)}</pre>
          </details>
        </details>
      </section>
    </div>
  );
}

function ReupQueueInspectorActions({
  item,
  mutatingAction,
  onApplyAction,
  onBatchAction
}: {
  item: ReupQueueItem;
  mutatingAction: ReupQueueAction | null;
  onApplyAction: (item: ReupQueueItem, action: ReupQueueAction, options?: { pipelineMode?: ReupPipelineMode }) => void;
  onBatchAction: (action: ReupQueueBatchAction) => void;
}) {
  const disabled = mutatingAction !== null;
  const dismissAction = terminalQueueDismissAction(item);
  const transcriptCta = queueTileTranscriptCta(item);
  const recoveryLink = pipelineFailureRecoveryLink(item);
  const primaryAction = primaryQueueAction(item);
  const showPrimaryAction = primaryAction !== null && primaryAction !== "inspect";
  const primaryLabel = primaryQueueActionLabel(item);
  const primaryButtonClass = queueTilePrimaryButtonClassName(item);
  const workflowLinks = buildInspectorWorkflowLinks(item);

  const shownPrimaryKey =
    dismissAction ??
    (recoveryLink ? "OPEN_RECOVERY" : null) ??
    (transcriptCta ? "OPEN_TRANSCRIPT" : null) ??
    (typeof primaryAction === "string" && primaryAction !== "inspect" ? primaryAction : null);

  const remainingActions = filterInspectorCompanionActions(
    item,
    item.available_actions.filter((entry) => {
      if (shownPrimaryKey && entry.action === shownPrimaryKey) return false;
      if (dismissAction && entry.action === "DISMISS") return false;
      return true;
    })
  );
  const { primary, neutral, danger, quiet } = groupInspectorLifecycleActions(remainingActions);
  const moreTransitions = [...primary, ...neutral];
  const showExportPackage =
    item.status === "READY_TO_EXPORT" &&
    item.media_prep_status === "READY_FOR_EXPORT" &&
    shownPrimaryKey !== "CREATE_EXPORT_PACKAGE";
  const showPublishHandoff = item.status === "READY_TO_PUBLISH" && shownPrimaryKey !== "CREATE_PUBLISH_HANDOFF";
  const attentionCompact = item.status === "FAILED_NEEDS_ATTENTION";
  const transcriptCompact = Boolean(transcriptCta);
  const useCompactCompanions = attentionCompact || transcriptCompact;
  const compactCompanions = useCompactCompanions ? [...moreTransitions, ...danger, ...quiet] : [];
  const hasPrimary = Boolean(dismissAction || recoveryLink || transcriptCta || showPrimaryAction);
  const hasSecondary = useCompactCompanions
    ? compactCompanions.length > 0 || showExportPackage || showPublishHandoff
    : moreTransitions.length > 0 || danger.length > 0 || quiet.length > 0 || showExportPackage || showPublishHandoff;
  const hasWorkflow = workflowLinks.length > 0;

  function companionButtonClass(action: ReupQueueAction): string {
    if (action === "CANCEL" || action === "MARK_BLOCKED") return "review-board-tile-btn is-danger";
    if (action === "DISMISS" || action === "HOLD") return "review-board-tile-btn is-muted";
    return `review-board-tile-btn ${queueLifecycleActionTone(action).replace("is-primary", "is-secondary").replace("is-success", "is-secondary").replace("is-warning", "is-muted").replace("is-neutral", "is-muted")}`;
  }

  function runPrimaryAction() {
    if (dismissAction) {
      onApplyAction(item, "DISMISS");
      return;
    }
    if (!primaryAction || primaryAction === "inspect") return;
    if (primaryAction === "CREATE_EXPORT_PACKAGE" || primaryAction === "CREATE_PUBLISH_HANDOFF" || primaryAction === "PURGE") {
      onBatchAction(primaryAction);
      return;
    }
    onApplyAction(item, primaryAction);
  }

  const automationMode = currentAutomationMode(item);

  return (
    <div className="reup-queue-inspector-footer-actions" aria-label="Queue item actions">
      {canChangeAutomation(item) ? (
        <div className="reup-queue-automation-picker" aria-label="Automation level" role="group">
          <p className="reup-queue-automation-picker__label">Automation</p>
          <div className="reup-queue-automation-picker__options">
            {automationModeOptions().map((option) => (
              <button
                aria-pressed={option.mode === automationMode}
                className={`review-board-tile-btn is-muted reup-queue-automation-picker__option${
                  option.mode === automationMode ? " is-active" : ""
                }`}
                disabled={disabled || option.mode === automationMode}
                key={option.mode}
                onClick={() => onApplyAction(item, "SET_AUTOMATION", { pipelineMode: option.mode })}
                title={option.description}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      {!hasPrimary && !hasSecondary && !hasWorkflow ? (
        <p className="reup-queue-inspector-empty">No lifecycle actions are currently available.</p>
      ) : (
        <div
          aria-label="Queue item actions"
          className="review-board-tile-action-bar review-board-tile-action-grid is-inspector reup-queue-tile-action-bar"
        >
          {hasPrimary ? (
            <div className="review-board-tile-action-primary">
              {dismissAction ? (
                <AsyncButton
                  className="review-board-tile-btn is-muted"
                  disabled={disabled}
                  leadingIcon={<WorkItemActionIcon kind="dismiss" />}
                  onClick={() => onApplyAction(item, "DISMISS")}
                  pending={mutatingAction === "DISMISS"}
                  pendingLabel="Dismissing…"
                  title="Hide this item from Reup Queue"
                  type="button"
                >
                  Dismiss
                </AsyncButton>
              ) : recoveryLink ? (
                <a
                  className="review-board-tile-btn is-primary is-promoted-open"
                  href={recoveryLink.href}
                  title={recoveryLink.detail}
                >
                  <WorkItemActionIcon kind="open" />
                  {recoveryLink.label}
                </a>
              ) : transcriptCta ? (
                <a
                  className="review-board-tile-btn is-primary is-promoted-open reup-queue-tile-transcript-cta"
                  href={transcriptCta.href}
                  rel="noopener noreferrer"
                  target="_blank"
                  title="Open transcript editor"
                >
                  <WorkItemActionIcon kind="transcript" />
                  Open Transcript
                </a>
              ) : (
                <AsyncButton
                  className={primaryButtonClass}
                  disabled={disabled}
                  leadingIcon={<WorkItemActionIcon kind={worklistPrimaryIconKind(item)} />}
                  onClick={runPrimaryAction}
                  pending={
                    typeof primaryAction === "string" && primaryAction !== "inspect"
                      ? mutatingAction === primaryAction
                      : false
                  }
                  pendingLabel="Working…"
                  type="button"
                >
                  {primaryLabel}
                </AsyncButton>
              )}
            </div>
          ) : null}

          {useCompactCompanions && compactCompanions.length > 0 ? (
            <div
              className={`review-board-tile-action-row ${
                compactCompanions.length >= 3 ? "is-attention-compact" : compactCompanions.length === 2 ? "is-split" : "is-secondary"
              }`}
            >
              {compactCompanions.map((available) => (
                <AsyncButton
                  className={companionButtonClass(available.action)}
                  disabled={disabled}
                  key={available.action}
                  leadingIcon={<WorkItemActionIcon kind={queueLifecycleActionIconKind(available.action)} />}
                  onClick={() => onApplyAction(item, available.action)}
                  pending={mutatingAction === available.action}
                  pendingLabel="Working…"
                  title={available.description}
                  type="button"
                >
                  {mutatingAction === available.action ? "Working..." : available.label}
                </AsyncButton>
              ))}
            </div>
          ) : null}

          {!useCompactCompanions && (showExportPackage || showPublishHandoff || moreTransitions.length > 0) ? (
            <div className="review-board-tile-action-row is-secondary">
              {showExportPackage ? (
                <AsyncButton
                  className="review-board-tile-btn is-secondary"
                  disabled={disabled}
                  leadingIcon={<WorkItemActionIcon kind="send" />}
                  onClick={() => onBatchAction("CREATE_EXPORT_PACKAGE")}
                  type="button"
                >
                  Create export package
                </AsyncButton>
              ) : null}
              {showPublishHandoff ? (
                <AsyncButton
                  className="review-board-tile-btn is-secondary"
                  disabled={disabled}
                  leadingIcon={<WorkItemActionIcon kind="send" />}
                  onClick={() => onBatchAction("CREATE_PUBLISH_HANDOFF")}
                  type="button"
                >
                  Create publish handoff
                </AsyncButton>
              ) : null}
              {moreTransitions.map((available) => (
                <AsyncButton
                  className={`review-board-tile-btn ${queueLifecycleActionTone(available.action).replace("is-primary", "is-secondary").replace("is-success", "is-secondary").replace("is-warning", "is-muted").replace("is-neutral", "is-muted")}`}
                  disabled={disabled}
                  key={available.action}
                  leadingIcon={<WorkItemActionIcon kind={queueLifecycleActionIconKind(available.action)} />}
                  onClick={() => onApplyAction(item, available.action)}
                  pending={mutatingAction === available.action}
                  pendingLabel="Working…"
                  title={available.description}
                  type="button"
                >
                  {mutatingAction === available.action ? "Working..." : available.label}
                </AsyncButton>
              ))}
            </div>
          ) : null}

          {!useCompactCompanions && danger.length > 0 ? (
            <div className={`review-board-tile-action-row ${danger.length > 1 ? "is-split" : "is-secondary"}`}>
              {danger.map((available) => (
                <AsyncButton
                  className="review-board-tile-btn is-danger"
                  disabled={disabled}
                  key={available.action}
                  leadingIcon={<WorkItemActionIcon kind={queueLifecycleActionIconKind(available.action)} />}
                  onClick={() => onApplyAction(item, available.action)}
                  pending={mutatingAction === available.action}
                  pendingLabel="Working…"
                  title={available.description}
                  type="button"
                >
                  {mutatingAction === available.action ? "Working..." : available.label}
                </AsyncButton>
              ))}
            </div>
          ) : null}

          {!useCompactCompanions && quiet.length > 0 ? (
            <div className="review-board-tile-action-row is-secondary">
              {quiet.map((available) => (
                <AsyncButton
                  className="review-board-tile-btn is-muted"
                  disabled={disabled}
                  key={available.action}
                  leadingIcon={<WorkItemActionIcon kind={queueLifecycleActionIconKind(available.action)} />}
                  onClick={() => onApplyAction(item, available.action)}
                  pending={mutatingAction === available.action}
                  pendingLabel="Working…"
                  title={available.description}
                  type="button"
                >
                  {mutatingAction === available.action ? "Working..." : available.label}
                </AsyncButton>
              ))}
            </div>
          ) : null}

          {hasWorkflow ? (
            <div className="reup-queue-inspector-workflow-chips" aria-label="Open workflows">
              {workflowLinks.map((link) => (
                <a
                  className="reup-queue-inspector-workflow-chip"
                  href={link.href}
                  key={link.href}
                  rel={link.external ? "noreferrer" : undefined}
                  target={link.external ? "_blank" : undefined}
                >
                  {link.label}
                </a>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function queueLifecycleActionIconKind(action: ReupQueueAction): WorkItemActionIconKind {
  if (action === "START_PROCESSING" || action === "RESUME" || action === "MARK_COMPLETED") return "process";
  if (action === "HOLD") return "pause";
  if (action === "RETRY") return "retry";
  if (action === "MARK_MEDIA_READY") return "approve";
  if (action === "DISMISS") return "dismiss";
  return "reject";
}

function queueLifecycleActionTone(action: ReupQueueAction): string {
  if (action === "START_PROCESSING" || action === "RESUME") return "is-primary";
  if (action === "MARK_MEDIA_READY" || action === "MARK_COMPLETED") return "is-success";
  if (action === "HOLD" || action === "RETRY") return "is-warning";
  if (action === "CANCEL" || action === "MARK_BLOCKED") return "is-danger";
  return "is-neutral";
}

function BatchResultPanel({ onDismiss, result }: { onDismiss: () => void; result: BatchOperationResponse }) {
  return (
    <div className="reup-queue-batch-banner" role="status">
      <span className="reup-queue-batch-banner-summary">
        <strong>Last batch</strong> {formatBatchResultSummary(result)}
      </span>
      <span className="reup-queue-batch-banner-artifacts">
        {result.export_package_id ? (
          <a href={`/publishing/export-packages/${result.export_package_id}`}>Export package</a>
        ) : (
          <span className="reup-queue-batch-banner-muted">No export package</span>
        )}
        {result.publish_handoff_id ? (
          <a href={`/publishing/publish-handoffs/${result.publish_handoff_id}`}>Handoff</a>
        ) : (
          <span className="reup-queue-batch-banner-muted">No handoff</span>
        )}
      </span>
      <button className="reup-queue-batch-banner-dismiss" onClick={onDismiss} type="button">
        Dismiss
      </button>
    </div>
  );
}

function defaultActionNote(action: ReupQueueAction): string | null {
  if (action === "MARK_BLOCKED") return "Operator marked the item blocked from Reup Queue.";
  if (action === "HOLD") return "Operator paused download progress from Reup Queue.";
  if (action === "CANCEL") return "Operator cancelled downstream queue work.";
  if (action === "MARK_MEDIA_READY") return "Operator confirmed media; start audio analysis.";
  if (action === "START_AUTO_PIPELINE") return "Operator started the configured auto pipeline (Download through TTS or Final Render).";
  return null;
}

function defaultBatchActionNote(action: ReupQueueBatchAction): string | null {
  if (action === "HOLD") return "Operator batch-paused download progress from Reup Queue.";
  if (action === "CANCEL") return "Operator batch-cancelled downstream queue work.";
  if (action === "MARK_MEDIA_READY") return "Operator batch-confirmed media; start audio analysis.";
  if (action === "START_AUTO_PIPELINE") return "Operator batch-started the configured auto pipeline (Download through TTS or Final Render).";
  if (action === "CREATE_EXPORT_PACKAGE") return "Operator created an Export Package from selected Reup Queue items.";
  if (action === "CREATE_PUBLISH_HANDOFF") return "Operator created a Publish Handoff payload from selected Reup Queue items.";
  if (action === "DISMISS") return "Operator cleared queue items from the active Reup Queue view.";
  if (action === "PURGE") return "Operator permanently deleted clearable queue records.";
  return null;
}

function batchSummary(action: ReupQueueBatchAction, result: BatchOperationResponse): string {
  const packageText = result.export_package_id ? ` Export Package: ${result.export_package_id}.` : "";
  const handoffText = result.publish_handoff_id ? ` Publish Handoff: ${result.publish_handoff_id}.` : "";
  const parkedCount = action === "START_AUTO_PIPELINE"
    ? result.results.filter((entry) => entry.message?.toLowerCase().includes("waiting for a free lane slot")).length
    : 0;
  const parkedText = parkedCount > 0 ? ` ${parkedCount} queued for an auto lane slot.` : "";
  return `${actionLabel(action)} completed: ${result.succeeded_count} succeeded, ${result.skipped_count} skipped, ${result.failed_count} failed.${parkedText}${packageText}${handoffText}`;
}
