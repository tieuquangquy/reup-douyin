"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { fetchReupQueueItems, purgeClearableReupQueueItems, runReupQueueAction, runReupQueueBatchAction } from "../../lib/api";
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
  formatBulkBarScopeMeta,
  formatDateTime,
  buildInspectorWorkflowLinks,
  buildPipelineStages,
  buildQueueTileSecondaryLinks,
  buildQuickPathHeroStats,
  capStartProcessingBatchIds,
  downloadJobErrorLine,
  downloadJobProgressPercent,
  formatJobChipLabel,
  groupInspectorLifecycleActions,
  hasActiveDownloadJob,
  hasAnyBatchEligibility,
  jobChipTone,
  itemTitle,
  metadataString,
  operatorStatusLabel,
  pickInspectorSpotlightAction,
  primaryBulkEligibilityTotal,
  markMediaReadyNotice,
  primaryQueueAction,
  primaryQueueActionLabel,
  queueTilePrimaryButtonClassName,
  queueTilePrimaryButtonTone,
  quickPathGuidance,
  quickPathGuidanceTone,
  quickPathSuggestedFilter,
  resolveInitialReupQueueFilter,
  queueStageLabel,
  queueStageTone,
  queueTileDurationLabel,
  queueTilePostedLabel,
  queueTileThumbnailUrl,
  queueTileViewsLabel,
  queueTileScoreBadge,
  worklistStageLabel,
  worklistStageTone,
  worklistTranscriptHref,
  worklistNoDialogueHint,
  shouldShowWorklistOpenJobLink,
  REUP_QUEUE_START_PROCESSING_BATCH_LIMIT,
  REUP_QUEUE_STATUS_FILTERS,
  secondaryBulkEligibilityTotal,
  selectAllActionableReupQueueItems,
  selectedVisibleReupQueueIds,
  selectableReupQueueItems,
  shouldShowQueueTileDetailsButton,
  startProcessingBatchCapNotice,
  statusesForReupQueueFilter,
  supportsBulkCancelVisibleScope,
  supportsBulkDismissVisibleScope,
  supportsBulkPurgeVisibleScope,
  terminalQueueDismissAction,
  toggleReupQueueSelection,
  visibleReupQueueItems,
  type ReupQueueOperatorFilter,
  type ReupQueueSortMode
} from "../../lib/reupQueueStudioState";
import { hasMoreOffsetItems, mergeOffsetItemsById } from "../../lib/offsetListPagination";
import {
  OPERATOR_LIST_PAGE_SIZE_PRESETS,
  REUP_QUEUE_PAGE_SIZE_STORAGE_KEY,
  readOperatorListPageSize,
  writeOperatorListPageSize,
} from "../../lib/operatorListPageSize";
import {
  REUP_QUEUE_VIEW_MODE_LABELS,
  readReupQueueViewMode,
  writeReupQueueViewMode,
  type ReupQueueViewMode
} from "../../lib/reupQueueViewMode";
import type { BatchOperationResponse, ReupQueueBatchAction } from "../../types/export-handoff";
import type { ReupQueueAction, ReupQueueItem } from "../../types/reup-queue";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { OpsConsolePage, OpsDetailPanel, OpsDetailSection, OpsFilterBar, OpsMetadataList, OpsStatePanel } from "../ops-console/OpsShared";
import { OffsetLoadMoreFooter } from "../shared/OffsetLoadMoreFooter";

const UI_VERSION = "22G-2K";
const DEFAULT_HANDOFF_PLATFORM = "FACEBOOK_REELS";
const REVIEW_BOARD_HREF = "/selection/review-board";
const ACTIVE_DOWNLOAD_POLL_MS = 8_000;
const REUP_QUEUE_PAGE_SIZE_DEFAULT = 50;

export function ReupQueuePage() {
  const [pageSize, setPageSize] = useState(() =>
    readOperatorListPageSize(REUP_QUEUE_PAGE_SIZE_STORAGE_KEY, OPERATOR_LIST_PAGE_SIZE_PRESETS, REUP_QUEUE_PAGE_SIZE_DEFAULT)
  );
  const [items, setItems] = useState<ReupQueueItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [operatorFilter, setOperatorFilter] = useState<ReupQueueOperatorFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortMode, setSortMode] = useState<ReupQueueSortMode>("active-first");
  const [viewMode, setViewMode] = useState<ReupQueueViewMode>(() => readReupQueueViewMode());
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [queueInspectorOpen, setQueueInspectorOpen] = useState(false);
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [batchResult, setBatchResult] = useState<BatchOperationResponse | null>(null);
  const [mutatingAction, setMutatingAction] = useState<ReupQueueAction | null>(null);
  const [batchWorkingAction, setBatchWorkingAction] = useState<ReupQueueBatchAction | null>(null);
  const initialFilterApplied = useRef(false);
  const loadedCountRef = useRef(0);
  const operatorFilterRef = useRef(operatorFilter);
  operatorFilterRef.current = operatorFilter;

  async function loadQueue(preserveUi = false, nextPageSize = pageSize, filter = operatorFilter, sort = sortMode) {
    if (preserveUi) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const statuses = statusesForReupQueueFilter(filter);
      const windowLimit = Math.max(nextPageSize, preserveUi ? loadedCountRef.current || nextPageSize : nextPageSize);
      const payload = await fetchReupQueueItems({ limit: windowLimit, offset: 0, statuses, sort });
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
      setError(err instanceof Error ? err.message : "Failed to load Reup Queue");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function loadMoreQueue() {
    if (loadingMore || !hasMoreOffsetItems(items.length, totalCount)) return;
    setLoadingMore(true);
    setError(null);
    try {
      const statuses = statusesForReupQueueFilter(operatorFilter);
      const payload = await fetchReupQueueItems({ limit: pageSize, offset: items.length, statuses, sort: sortMode });
      setStatusCounts(payload.status_counts ?? {});
      setItems((current) => {
        const merged = mergeOffsetItemsById(current, payload.items);
        loadedCountRef.current = merged.length;
        return merged;
      });
      setTotalCount(payload.total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load more Reup Queue items");
    } finally {
      setLoadingMore(false);
    }
  }

  function handlePageSizeChange(nextPageSize: number) {
    if (nextPageSize === pageSize) return;
    writeOperatorListPageSize(REUP_QUEUE_PAGE_SIZE_STORAGE_KEY, nextPageSize, OPERATOR_LIST_PAGE_SIZE_PRESETS);
    setPageSize(nextPageSize);
    loadedCountRef.current = 0;
    void loadQueue(false, nextPageSize, operatorFilter, sortMode);
  }

  function handleOperatorFilterChange(nextFilter: ReupQueueOperatorFilter) {
    if (nextFilter === operatorFilter) return;
    setOperatorFilter(nextFilter);
    setItems([]);
    setTotalCount(0);
    loadedCountRef.current = 0;
  }

  function handleSortModeChange(nextSort: ReupQueueSortMode) {
    if (nextSort === sortMode) return;
    setSortMode(nextSort);
    loadedCountRef.current = 0;
  }

  function handleViewModeChange(nextMode: ReupQueueViewMode) {
    if (nextMode === viewMode) return;
    setViewMode(nextMode);
    writeReupQueueViewMode(nextMode);
  }

  useEffect(() => {
    void loadQueue(false, pageSize, operatorFilter, sortMode);
  }, [operatorFilter, sortMode]);

  const hasActiveDownloads = useMemo(() => items.some((item) => hasActiveDownloadJob(item)), [items]);

  useEffect(() => {
    if (!hasActiveDownloads) return;
    const timer = window.setInterval(() => {
      void loadQueue(true, pageSize, operatorFilterRef.current, sortMode);
    }, ACTIVE_DOWNLOAD_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hasActiveDownloads, pageSize, sortMode]);

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

  async function applyQueueAction(item: ReupQueueItem, action: ReupQueueAction) {
    if (action === "CANCEL" && !window.confirm(bulkCancelConfirmMessage(1, operatorFilter))) {
      return;
    }
    if (action === "DISMISS" && !window.confirm(bulkDismissConfirmMessage(1, operatorFilter))) {
      return;
    }
    setMutatingAction(action);
    setError(null);
    setNotice(null);
    setBatchResult(null);
    try {
      const result = await runReupQueueAction(item.id, {
        action,
        note: defaultActionNote(action),
        blocked_reason: action === "MARK_BLOCKED" || action === "CANCEL" ? defaultActionNote(action) : null,
        media_prep_notes: action === "MARK_MEDIA_READY" ? "Operator confirmed media; enqueue audio analysis." : null,
        media_prep_status: action === "MARK_MEDIA_READY" ? "WAITING_FOR_METADATA" : null
      });
      setItems((current) => current.map((existing) => (existing.id === result.item.id ? result.item : existing)));
      setActiveItemId(result.item.id);
      setQueueInspectorOpen(true);
      setNotice(
        action === "MARK_MEDIA_READY"
          ? markMediaReadyNotice(result.item)
          : `${actionLabel(action)} applied. Current state: ${operatorStatusLabel(result.item.status)}.`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Reup Queue action");
    } finally {
      setMutatingAction(null);
    }
  }

  async function applyBatchAction(action: ReupQueueBatchAction, itemIds = bulkSelectedIds) {
    if (itemIds.length === 0) {
      setNotice("Select at least one queue item before running a batch action.");
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
    setBatchWorkingAction(action);
    setError(null);
    setNotice(preflightCapNotice);
    setBatchResult(null);
    try {
      const result = await runReupQueueBatchAction({
        action,
        item_ids: requestIds,
        note: defaultBatchActionNote(action),
        target_platform: action === "CREATE_PUBLISH_HANDOFF" ? DEFAULT_HANDOFF_PLATFORM : null
      });
      setBatchResult(result);
      const summary = batchSummary(action, result);
      setNotice(preflightCapNotice ? `${preflightCapNotice} ${summary}` : summary);
      setSelectedItemIds(new Set());
      await loadQueue(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Reup Queue batch action");
    } finally {
      setBatchWorkingAction(null);
    }
  }

  async function purgeVisibleClearableItems() {
    const itemIds = clearablePurgeReupQueueItems(visibleItems).map((item) => item.id);
    if (itemIds.length === 0) {
      setNotice("No clearable queue records in the current view.");
      return;
    }
    if (!window.confirm(bulkPurgeConfirmMessage(itemIds.length, operatorFilter))) {
      return;
    }
    setBatchWorkingAction("PURGE");
    setError(null);
    setNotice(null);
    setBatchResult(null);
    try {
      const result = await purgeClearableReupQueueItems({ item_ids: itemIds, scope: "selected" });
      const skippedNote = result.skipped_count > 0 ? ` Skipped ${result.skipped_count} linked to export packages.` : "";
      setNotice(`Permanently deleted ${result.purged_count}/${result.requested_count} queue record(s).${skippedNote}`);
      setSelectedItemIds(new Set());
      await loadQueue(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to purge Reup Queue items");
    } finally {
      setBatchWorkingAction(null);
    }
  }

  async function runTilePrimaryAction(item: ReupQueueItem) {
    const action = primaryQueueAction(item);
    if (action === "inspect" || action === null) {
      openItemDetails(item.id);
      return;
    }
    if (action === "CREATE_EXPORT_PACKAGE" || action === "CREATE_PUBLISH_HANDOFF") {
      await applyBatchAction(action, [item.id]);
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
  const quickPathHint = useMemo(() => quickPathGuidance(summary, operatorFilter), [operatorFilter, summary]);
  const bulkHint = useMemo(() => bulkSelectionGuidance(bulkSelectedIds.length, selectionEligibility), [bulkSelectedIds.length, selectionEligibility]);

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
          onStartReady={() => void applyBatchAction("START_PROCESSING", items.filter((item) => item.status === "READY_FOR_PROCESSING").map((item) => item.id))}
          guidance={quickPathHint}
          summary={summary}
          working={batchWorkingAction !== null || mutatingAction !== null}
        />
        <ReupQueueStudioFilters onSearch={setSearchQuery} onSort={handleSortModeChange} searchQuery={searchQuery} sortMode={sortMode} />
        {notice ? <section className="operator-panel intake-status good"><strong>{notice}</strong></section> : null}
        {error && !loading ? <section className="operator-panel intake-status danger"><strong>Reup Queue error:</strong> {error}</section> : null}

        <div className="capture-inbox-review-workspace reup-queue-studio-workspace" data-reup-queue-ui-version={UI_VERSION}>
          <main className="capture-inbox-review-main" aria-busy={loading || refreshing} aria-label="Reup Queue items">
            <ReupQueueBatchActionBar
              actionableVisibleCount={actionableVisibleCount}
              batchResult={batchResult}
              cancellableVisibleCount={cancellableVisibleItems.length}
              dismissableVisibleCount={dismissableVisibleItems.length}
              eligibility={selectionEligibility}
              guidance={bulkHint}
              mutating={batchWorkingAction !== null || mutatingAction !== null}
              onBatchAction={(action) => void applyBatchAction(action)}
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

            {loading && items.length === 0 ? <OpsStatePanel detail="Collecting approved downstream work." title="Loading Reup Queue" variant="loading" /> : null}
            {!loading && error && items.length === 0 ? (
              <OpsStatePanel action={<button onClick={() => void loadQueue()} type="button">Retry</button>} detail={error} title="Reup Queue unavailable" variant="error" />
            ) : null}
            {!loading && !error && items.length === 0 ? (
              <OpsStatePanel
                action={<a href={REVIEW_BOARD_HREF}>Open Review Board</a>}
                detail="Approve candidates in Review Board, then use Send to queue or Approve & send."
                title="No queued reup work"
                variant="empty"
              />
            ) : null}
            {!loading && visibleItems.length === 0 && items.length > 0 ? (
              <OpsStatePanel detail="Try another status tab or reset search." title="No items in this view" variant="empty" />
            ) : null}

            {visibleItems.length > 0 ? (
              <section
                className={`capture-inbox-media-gallery reup-queue-gallery-shell is-view-${viewMode}`}
                aria-label={viewMode === "worklist" ? "Reup Queue worklist" : "Reup Queue tile gallery"}
              >
                <div className="capture-inbox-media-gallery-heading reup-queue-gallery-heading">
                  <div className="reup-queue-gallery-heading-copy">
                    <h2>{viewMode === "worklist" ? "Queue worklist" : "Queue tiles"}</h2>
                    {searchQuery.trim() ? (
                      <span>{visibleItems.length.toLocaleString()} match{visibleItems.length === 1 ? "" : "es"} for search</span>
                    ) : null}
                  </div>
                  <div className="reup-queue-view-toggle" role="group" aria-label="Queue view mode">
                    {(Object.keys(REUP_QUEUE_VIEW_MODE_LABELS) as ReupQueueViewMode[]).map((mode) => (
                      <button
                        aria-pressed={viewMode === mode}
                        className={`reup-queue-view-toggle-btn ${viewMode === mode ? "is-active" : ""}`}
                        key={mode}
                        onClick={() => handleViewModeChange(mode)}
                        type="button"
                      >
                        {REUP_QUEUE_VIEW_MODE_LABELS[mode]}
                      </button>
                    ))}
                  </div>
                </div>
                {viewMode === "worklist" ? (
                  <div className="reup-queue-worklist is-rail is-dense is-soft" role="list">
                    {visibleItems.map((item) => (
                      <ReupQueueWorklistRow
                        focused={activeItemId === item.id}
                        item={item}
                        key={item.id}
                        mutating={mutatingAction !== null || batchWorkingAction !== null}
                        onDetails={() => openItemDetails(item.id)}
                        onDismiss={() => void applyQueueAction(item, "DISMISS")}
                        onPrimary={() => void runTilePrimaryAction(item)}
                        onToggleSelect={() => setSelectedItemIds((current) => toggleReupQueueSelection(current, item.id))}
                        selected={selectedItemIds.has(item.id)}
                      />
                    ))}
                  </div>
                ) : (
                <div className="capture-inbox-media-tile-grid">
                  {visibleItems.map((item) => (
                    <ReupQueueMediaTile
                      focused={activeItemId === item.id}
                      item={item}
                      key={item.id}
                      mutating={mutatingAction !== null || batchWorkingAction !== null}
                      onDetails={() => openItemDetails(item.id)}
                      onDismiss={() => void applyQueueAction(item, "DISMISS")}
                      onPrimary={() => void runTilePrimaryAction(item)}
                      onToggleSelect={() => setSelectedItemIds((current) => toggleReupQueueSelection(current, item.id))}
                      selected={selectedItemIds.has(item.id)}
                    />
                  ))}
                </div>
                )}
                {(totalCount > 0 || items.length > 0) ? (
                  <OffsetLoadMoreFooter
                    disabled={mutatingAction !== null || batchWorkingAction !== null || refreshing}
                    loadedCount={items.length}
                    loadingMore={loadingMore}
                    noun="queue items"
                    onLoadMore={() => void loadMoreQueue()}
                    onPageSizeChange={handlePageSizeChange}
                    pageSize={pageSize}
                    pageSizeOptions={OPERATOR_LIST_PAGE_SIZE_PRESETS}
                    totalCount={totalCount}
                  />
                ) : null}
              </section>
            ) : null}
          </main>

          <aside className="capture-inbox-review-side" aria-label="Right-side sticky inspector">
            <ReupQueueRightInspector
              item={activeItem}
              mutatingAction={mutatingAction}
              onApplyAction={(target, action) => void applyQueueAction(target, action)}
              onBatchAction={(action) => void applyBatchAction(action, activeItem ? [activeItem.id] : [])}
              onClose={closeItemDetails}
              open={queueInspectorOpen && Boolean(activeItem)}
            />
          </aside>
        </div>
      </OpsConsolePage>
    </OperatorStudioShell>
  );
}

function ReupQueueQuickPathBar({
  activeFilter,
  guidance,
  onFilter,
  onStartReady,
  summary,
  working
}: {
  activeFilter: ReupQueueOperatorFilter;
  guidance: string | null;
  onFilter: (filter: ReupQueueOperatorFilter) => void;
  onStartReady: () => void;
  summary: ReturnType<typeof buildReupQueueSummary>;
  working: boolean;
}) {
  const needsStartCount = summary.needs_start;
  const startBatchCount = Math.min(needsStartCount, REUP_QUEUE_START_PROCESSING_BATCH_LIMIT);
  const startCapped = needsStartCount > REUP_QUEUE_START_PROCESSING_BATCH_LIMIT;
  const heroStats = buildQuickPathHeroStats(summary);
  const suggestedFilter = quickPathSuggestedFilter(summary, activeFilter);
  const suggestedFilterLabel = suggestedFilter
    ? REUP_QUEUE_STATUS_FILTERS.find((entry) => entry.key === suggestedFilter)?.label
    : null;
  const guidanceTone = quickPathGuidanceTone(summary);

  return (
    <section className="operator-panel reup-queue-hero-panel is-compact" aria-label="Reup Queue quick path">
      <div className="reup-queue-hero-toolbar">
        <div className="reup-queue-hero-head-compact">
          <span className="reup-queue-hero-kicker">Workflow</span>
          <p className="reup-queue-hero-steps-inline">Start processing → track media → export &amp; handoff</p>
        </div>
        <button
          className="primary reup-queue-hero-cta"
          disabled={working || needsStartCount === 0}
          onClick={onStartReady}
          title={
            needsStartCount === 0
              ? "No clips are in Needs start right now"
              : startCapped
                ? `Safe batch limit ${REUP_QUEUE_START_PROCESSING_BATCH_LIMIT}: starts first ${startBatchCount} of ${needsStartCount} ready clips`
                : undefined
          }
          type="button"
        >
          {startCapped
            ? `Start ready (${startBatchCount}/${needsStartCount})`
            : `Start all ready (${needsStartCount})`}
        </button>
      </div>

      <div className="reup-queue-hero-stats" role="list">
        {heroStats.map((stat) => {
          const isActive = activeFilter === stat.key;
          return (
            <button
              aria-pressed={isActive}
              className={`reup-queue-hero-stat is-tone-${stat.tone}${isActive ? " is-active" : ""}`}
              key={stat.key}
              onClick={() => onFilter(stat.key)}
              role="listitem"
              type="button"
            >
              <span>{stat.label}</span>
              <strong>{stat.count}</strong>
            </button>
          );
        })}
      </div>

      {guidance ? (
        <div className={`reup-queue-hero-alert is-tone-${guidanceTone} is-compact`} role="status">
          <p className="reup-queue-hero-alert-copy">{guidance}</p>
          {suggestedFilter && suggestedFilterLabel ? (
            <button className="reup-queue-hero-alert-action" disabled={working} onClick={() => onFilter(suggestedFilter)} type="button">
              Open {suggestedFilterLabel}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function ReupQueueStudioFilters({
  onSearch,
  onSort,
  searchQuery,
  sortMode
}: {
  onSearch: (query: string) => void;
  onSort: (sortMode: ReupQueueSortMode) => void;
  searchQuery: string;
  sortMode: ReupQueueSortMode;
}) {
  return (
    <OpsFilterBar description="Search queue items and choose sort order. Use the stage chips above to filter by pipeline stage." title="Queue filters">
      <label className="field reup-queue-toolbar-search">
        <span>Search</span>
        <input
          onChange={(event) => onSearch(event.target.value)}
          placeholder="Search title, source, candidate, package, handoff..."
          value={searchQuery}
        />
      </label>
      <label className="field">
        <span>Sort</span>
        <select onChange={(event) => onSort(event.target.value as ReupQueueSortMode)} value={sortMode}>
          <option value="active-first">Active first</option>
          <option value="newest">Newest</option>
          <option value="ready-first">Ready first</option>
          <option value="needs-attention-first">Needs attention first</option>
          <option value="export-ready-first">Export ready first</option>
        </select>
      </label>
    </OpsFilterBar>
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
  onBatchAction: (action: ReupQueueBatchAction) => void;
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
  if (!visibleCount) return null;
  const hasSelection = selectedCount > 0;
  const disabled = mutating;
  const primaryTotal = primaryBulkEligibilityTotal(eligibility);
  const secondaryTotal = secondaryBulkEligibilityTotal(eligibility);
  const showCancelVisible = !hasSelection && supportsBulkCancelVisibleScope(operatorFilter) && cancellableVisibleCount > 0;
  const showDismissVisible = !hasSelection && supportsBulkDismissVisibleScope(operatorFilter) && dismissableVisibleCount > 0;
  const showPurgeVisible = !hasSelection && supportsBulkPurgeVisibleScope(operatorFilter) && purgeableVisibleCount > 0;
  const scopeMeta = formatBulkBarScopeMeta(actionableVisibleCount, visibleCount, selectedCount);
  const primaryActions: Array<{ action: ReupQueueBatchAction; label: string; count: number; primary?: boolean }> = [
    { action: "START_PROCESSING", label: "Start", count: eligibility.start, primary: true },
    { action: "CREATE_EXPORT_PACKAGE", label: "Export", count: eligibility.export },
    { action: "CREATE_PUBLISH_HANDOFF", label: "Handoff", count: eligibility.handoff }
  ].filter((entry) => !hasSelection || entry.count > 0);
  const secondaryActions: Array<{ action: ReupQueueBatchAction; label: string; count: number; danger?: boolean }> = [
    { action: "HOLD", label: "Pause", count: eligibility.hold },
    { action: "RESUME", label: "Resume", count: eligibility.resume },
    { action: "RETRY", label: "Retry", count: eligibility.retry },
    { action: "MARK_MEDIA_READY", label: "Media ready", count: eligibility.markMediaReady },
    { action: "CANCEL", label: "Cancel", count: eligibility.cancel, danger: true },
    { action: "DISMISS", label: "Clear", count: eligibility.dismiss, danger: true }
  ].filter((entry) => !hasSelection || entry.count > 0);
  const decisionActions = hasSelection && primaryTotal + secondaryTotal > 0 ? [...primaryActions, ...secondaryActions] : [];

  return (
    <div className="reup-queue-bulk-stack">
      <section
        className={`capture-inbox-command-bar reup-queue-bulk-command-bar is-compact ${hasSelection ? "is-active" : "is-idle"}`}
        aria-label="Bulk queue actions"
        data-selection-scope="actionable_items"
        data-sticky="true"
      >
        <div className="reup-queue-bulk-toolbar">
          <strong>Bulk</strong>
          <span className="reup-queue-bulk-meta">{scopeMeta}</span>
          <div className="reup-queue-bulk-toolbar-actions">
            <button className="reup-queue-bulk-btn" disabled={disabled || actionableVisibleCount === 0} onClick={onSelectActionable} type="button">
              Select actionable{actionableVisibleCount > 0 ? ` (${actionableVisibleCount})` : ""}
            </button>
            {showCancelVisible ? (
              <button
                className="danger review-board-action-danger-outline reup-queue-bulk-btn"
                disabled={disabled || workingAction !== null}
                onClick={onCancelVisible}
                type="button"
              >
                {workingAction === "CANCEL" ? "Working..." : `Cancel visible (${cancellableVisibleCount})`}
              </button>
            ) : null}
            {showDismissVisible ? (
              <button
                className="reup-queue-bulk-btn"
                disabled={disabled || workingAction !== null}
                onClick={onDismissVisible}
                type="button"
              >
                {workingAction === "DISMISS" ? "Working..." : `Clear visible (${dismissableVisibleCount})`}
              </button>
            ) : null}
            {showPurgeVisible ? (
              <button
                className="danger review-board-action-danger-outline reup-queue-bulk-btn"
                disabled={disabled || workingAction !== null}
                onClick={onPurgeVisible}
                type="button"
              >
                {workingAction === "PURGE" ? "Working..." : `Delete permanently (${purgeableVisibleCount})`}
              </button>
            ) : null}
            {hasSelection ? (
              <button className="capture-inbox-command-bar-clear reup-queue-bulk-btn" disabled={disabled} onClick={onClear} type="button">
                Clear
              </button>
            ) : null}
          </div>
        </div>

        {hasSelection && guidance ? <p className="reup-queue-bulk-hint">{guidance}</p> : null}

        {decisionActions.length > 0 ? (
          <div className="reup-queue-bulk-action-row">
            {decisionActions.map((entry) => (
              <button
                className={`reup-queue-bulk-btn ${entry.primary ? "primary" : ""} ${"danger" in entry && entry.danger ? "danger review-board-action-danger-outline" : ""}`.trim()}
                disabled={disabled || entry.count === 0 || (workingAction !== null && workingAction !== entry.action)}
                key={entry.action}
                onClick={() => onBatchAction(entry.action)}
                type="button"
              >
                {workingAction === entry.action ? "Working..." : `${entry.label} (${entry.count})`}
              </button>
            ))}
          </div>
        ) : null}
      </section>
      {batchResult ? <BatchResultPanel onDismiss={onDismissBatchResult} result={batchResult} /> : null}
    </div>
  );
}

function ReupQueueWorklistRow({
  focused,
  item,
  mutating,
  onDetails,
  onDismiss,
  onPrimary,
  onToggleSelect,
  selected
}: {
  focused: boolean;
  item: ReupQueueItem;
  mutating: boolean;
  onDetails: () => void;
  onDismiss: () => void;
  onPrimary: () => void;
  onToggleSelect: () => void;
  selected: boolean;
}) {
  const thumbnailUrl = queueTileThumbnailUrl(item);
  const stageTone = worklistStageTone(item);
  const selectable = hasAnyBatchEligibility(item);
  const downloadProgress = downloadJobProgressPercent(item);
  const showDetailsButton = shouldShowQueueTileDetailsButton(item);
  const dismissAction = terminalQueueDismissAction(item);
  const primaryLabel = primaryQueueActionLabel(item);
  const primaryAction = primaryQueueAction(item);
  const terminalDismissPair = Boolean(dismissAction) && !showDetailsButton;
  const buttonTone = queueTilePrimaryButtonTone(item);
  const primaryTone = buttonTone === "recover" ? "is-recover" : buttonTone === "forward" ? "is-primary" : "is-quiet";
  const primaryAsIcon = primaryAction === "HOLD" || primaryAction === "RESUME";
  const primaryIconKind: WorklistActionIconKind | null =
    primaryAction === "HOLD" ? "pause" : primaryAction === "RESUME" ? "play" : null;
  const transcriptHref = worklistTranscriptHref(item);
  const noDialogueHint = worklistNoDialogueHint(item);
  const showOpenJob = shouldShowWorklistOpenJobLink(item);

  return (
    <article
      className={`reup-queue-worklist-row ${selected ? "is-bulk-selected" : ""} ${focused ? "is-inspector-focused" : ""} ${!selectable ? "is-terminal-queue-tile" : ""}`}
      role="listitem"
    >
      <div className="reup-queue-worklist-select">
        {selectable ? (
          <label className={`reup-queue-worklist-check ${selected ? "is-selected" : ""}`} title={selected ? "Deselect for bulk actions" : "Select for bulk actions"}>
            <input aria-label={selected ? "Deselect queue item" : "Select queue item"} checked={selected} onChange={onToggleSelect} type="checkbox" />
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
      <div className={`reup-queue-worklist-status-col ${downloadProgress != null ? "has-progress" : ""}`}>
        {downloadProgress != null ? <WorklistProgressRing percent={downloadProgress} tone={stageTone} /> : null}
        <span
          className={`reup-queue-worklist-status is-${stageTone}`}
          title={
            item.job_id
              ? `${(item.job_type ?? "JOB").toUpperCase()} · ${item.job_status ?? "unknown"} · ${item.job_id.slice(0, 8)}`
              : undefined
          }
        >
          {downloadProgress == null ? <span aria-hidden="true" className="reup-queue-worklist-status-dot" /> : null}
          {worklistStageLabel(item)}
        </span>
      </div>
      <div className="reup-queue-worklist-actions">
        {showOpenJob && item.job_id ? (
          <a className="reup-queue-worklist-action is-quiet" href={`/ops/jobs?job_id=${item.job_id}`}>
            Open job
          </a>
        ) : null}
        {noDialogueHint ? (
          <span className="reup-queue-worklist-action is-quiet reup-queue-worklist-no-dialogue" title={noDialogueHint}>
            {noDialogueHint}
          </span>
        ) : null}
        {transcriptHref ? (
          <>
            <a className="reup-queue-worklist-action is-primary" href={transcriptHref}>
              Transcript
            </a>
            <button aria-label="Details" className="reup-queue-worklist-icon-action" disabled={mutating} onClick={onDetails} title="Details" type="button">
              <span aria-hidden="true" className="reup-queue-worklist-icon-ring">
                <WorklistActionIcon kind="details" />
              </span>
            </button>
          </>
        ) : terminalDismissPair ? (
          <>
            <button aria-label="Details" className="reup-queue-worklist-icon-action" disabled={mutating} onClick={onDetails} title="Details" type="button">
              <span aria-hidden="true" className="reup-queue-worklist-icon-ring">
                <WorklistActionIcon kind="details" />
              </span>
            </button>
            <button aria-label="Dismiss" className="reup-queue-worklist-icon-action" disabled={mutating} onClick={onDismiss} title="Dismiss" type="button">
              <span aria-hidden="true" className="reup-queue-worklist-icon-ring">
                <WorklistActionIcon kind="dismiss" />
              </span>
            </button>
          </>
        ) : (
          <>
            {primaryAsIcon && primaryIconKind ? (
              <button
                aria-label={primaryLabel}
                className="reup-queue-worklist-icon-action"
                disabled={mutating}
                onClick={onPrimary}
                title={primaryLabel}
                type="button"
              >
                <span aria-hidden="true" className="reup-queue-worklist-icon-ring">
                  <WorklistActionIcon kind={primaryIconKind} />
                </span>
              </button>
            ) : (
              <button className={`reup-queue-worklist-action ${primaryTone}`} disabled={mutating} onClick={onPrimary} type="button">
                {primaryLabel}
              </button>
            )}
            {showDetailsButton ? (
              <button aria-label="Details" className="reup-queue-worklist-icon-action" disabled={mutating} onClick={onDetails} title="Details" type="button">
                <span aria-hidden="true" className="reup-queue-worklist-icon-ring">
                  <WorklistActionIcon kind="details" />
                </span>
              </button>
            ) : null}
          </>
        )}
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

type WorklistActionIconKind = "pause" | "play" | "details" | "dismiss";

function WorklistActionIcon({ kind }: { kind: WorklistActionIconKind }) {
  if (kind === "pause") {
    return (
      <svg aria-hidden="true" className="reup-queue-worklist-icon" fill="currentColor" viewBox="0 0 24 24">
        <rect height="14" rx="1.5" width="3.5" x="7" y="5" />
        <rect height="14" rx="1.5" width="3.5" x="13.5" y="5" />
      </svg>
    );
  }
  if (kind === "play") {
    return (
      <svg aria-hidden="true" className="reup-queue-worklist-icon" fill="currentColor" viewBox="0 0 24 24">
        <path d="M8.5 5.8v12.4c0 .7.8 1.1 1.4.7l9.2-6.2c.5-.4.5-1.1 0-1.4L9.9 5.1c-.6-.4-1.4 0-1.4.7Z" />
      </svg>
    );
  }
  if (kind === "dismiss") {
    return (
      <svg aria-hidden="true" className="reup-queue-worklist-icon" fill="none" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" viewBox="0 0 24 24">
        <path d="M7 7l10 10M17 7 7 17" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="reup-queue-worklist-icon" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" viewBox="0 0 24 24">
      <rect height="7" rx="1.2" width="7" x="4" y="4" />
      <rect height="7" rx="1.2" width="7" x="13" y="4" />
      <rect height="7" rx="1.2" width="7" x="4" y="13" />
      <rect height="7" rx="1.2" width="7" x="13" y="13" />
    </svg>
  );
}

function ReupQueueMediaTile({
  focused,
  item,
  mutating,
  onDetails,
  onDismiss,
  onPrimary,
  onToggleSelect,
  selected
}: {
  focused: boolean;
  item: ReupQueueItem;
  mutating: boolean;
  onDetails: () => void;
  onDismiss: () => void;
  onPrimary: () => void;
  onToggleSelect: () => void;
  selected: boolean;
}) {
  const thumbnailUrl = queueTileThumbnailUrl(item);
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const publishHandoffId = metadataString(item.metadata_json, "publish_handoff_id");
  const stageTone = queueStageTone(item);
  const selectable = hasAnyBatchEligibility(item);
  const pipelineStages = buildPipelineStages(item);
  const jobChip = formatJobChipLabel(item);
  const downloadProgress = downloadJobProgressPercent(item);
  const downloadError = downloadJobErrorLine(item);
  const showDetailsButton = shouldShowQueueTileDetailsButton(item);
  const dismissAction = terminalQueueDismissAction(item);
  const secondaryLinks = buildQueueTileSecondaryLinks(item);
  const primaryLabel = primaryQueueActionLabel(item);
  const primaryButtonClass = queueTilePrimaryButtonClassName(item);
  const scoreBadge = queueTileScoreBadge(item);
  const terminalDismissPair = Boolean(dismissAction) && !showDetailsButton;
  const actionPair = showDetailsButton || terminalDismissPair;

  return (
    <article className={`capture-inbox-media-tile capture-inbox-compact-card reup-queue-media-tile ${selected ? "is-bulk-selected" : ""} ${focused ? "is-inspector-focused" : ""} ${!selectable ? "is-terminal-queue-tile" : ""}`}>
      <div className="capture-inbox-media-frame">
        <button className="capture-inbox-media-thumbnail" onClick={onDetails} type="button">
          {thumbnailUrl ? (
            <img alt={`Thumbnail for ${itemTitle(item)}`} src={thumbnailUrl} />
          ) : (
            <span className="capture-inbox-thumbnail-placeholder"><strong>No thumbnail</strong><small>{queueStageLabel(item)}</small></span>
          )}
        </button>
        <div className="capture-inbox-media-overlay top" aria-label="Tile overlay controls">
          <div className="capture-inbox-media-overlay-scrim review-board-tile-overlay-scrim" aria-hidden="true" />
          <div className="capture-inbox-overlay-left-group review-board-tile-overlay-meta">
            {selectable ? (
              <label className={`review-board-tile-select-toggle ${selected ? "is-selected" : ""}`} title={selected ? "Deselect for bulk actions" : "Select for bulk actions"}>
                <input aria-label={selected ? "Deselect queue item" : "Select queue item"} checked={selected} onChange={onToggleSelect} type="checkbox" />
                <span aria-hidden="true" className="review-board-tile-select-visual" />
              </label>
            ) : null}
            <span className={`review-board-tile-status-chip is-${stageTone}`}>{queueStageLabel(item)}</span>
            {jobChip ? <span className={`review-board-tile-status-chip is-${jobChipTone(item)} reup-queue-job-chip`}>{jobChip}</span> : null}
          </div>
          <div className="capture-inbox-overlay-right-group">
            <span
              className={`capture-inbox-reup-score-badge is-${scoreBadge.level} ${scoreBadge.score == null ? "missing" : "ready"} reup-queue-score-badge`}
              title={scoreBadge.title}
            >
              <strong>{scoreBadge.valueLabel}</strong>
              <small>{scoreBadge.tierLabel}</small>
            </span>
          </div>
        </div>
        {downloadProgress != null ? (
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
      <div className="capture-inbox-tile-main capture-inbox-compact-main">
        <button className="link-button capture-inbox-tile-title" onClick={onDetails} title={itemTitle(item)} type="button">{itemTitle(item)}</button>
        {downloadError ? (
          <p className="reup-queue-tile-job-error" title={downloadError}>
            {downloadError}
          </p>
        ) : null}
        <div className="capture-inbox-tile-quick-meta" aria-label="Compact quick metadata">
          <span className="capture-inbox-tile-quick-chip"><strong>Posted</strong><span>{queueTilePostedLabel(item)}</span></span>
          <span className="capture-inbox-tile-quick-chip"><strong>Duration</strong><span>{queueTileDurationLabel(item)}</span></span>
          <span className="capture-inbox-tile-quick-chip"><strong>Est. Views</strong><span>{queueTileViewsLabel(item)}</span></span>
        </div>
        <div className="reup-queue-pipeline-strip" aria-label="Production pipeline progress">
          {pipelineStages.map((stage) => (
            <span className={`reup-queue-pipeline-step is-${stage.state}`} key={stage.key} title={stage.label}>
              {stage.label}
            </span>
          ))}
        </div>
        {(exportPackageId || publishHandoffId) ? (
          <p className="reup-queue-tile-handoff-note">
            {exportPackageId ? "Export package linked" : null}
            {exportPackageId && publishHandoffId ? " · " : null}
            {publishHandoffId ? "Handoff linked" : null}
          </p>
        ) : null}
      </div>
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
        {actionPair ? (
          <div
            aria-label="Queue item actions"
            className="review-board-tile-action-bar review-board-tile-action-grid is-tile is-promoted-pair reup-queue-tile-action-bar"
          >
            {terminalDismissPair ? (
              <>
                <button
                  className="review-board-tile-btn is-secondary is-promoted-details"
                  disabled={mutating}
                  onClick={onDetails}
                  title="Inspect queue item details"
                  type="button"
                >
                  Details
                </button>
                <button
                  className="review-board-tile-btn is-muted"
                  disabled={mutating}
                  onClick={onDismiss}
                  title="Hide this item from Reup Queue"
                  type="button"
                >
                  Dismiss
                </button>
              </>
            ) : (
              <>
                <button
                  className={primaryButtonClass}
                  disabled={mutating}
                  onClick={onPrimary}
                  type="button"
                >
                  {primaryLabel}
                </button>
                <button
                  className="review-board-tile-btn is-secondary is-promoted-details"
                  disabled={mutating}
                  onClick={onDetails}
                  title="Inspect queue item details"
                  type="button"
                >
                  Details
                </button>
              </>
            )}
          </div>
        ) : (
          <div
            aria-label="Queue item actions"
            className="review-board-tile-action-bar review-board-tile-action-grid is-tile reup-queue-tile-action-bar"
          >
            <div className="review-board-tile-action-primary">
              <button
                className={primaryButtonClass}
                disabled={mutating}
                onClick={onPrimary}
                type="button"
              >
                {primaryLabel}
              </button>
            </div>
          </div>
        )}
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
    <div className={`capture-inbox-right-inspector reup-queue-right-inspector ${open ? "open" : "closed"}`} aria-hidden={!open && !item}>
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Queue item inspector</p>
          <h2>Production details</h2>
        </div>
        <button disabled={!item && !open} onClick={onClose} type="button">Close details</button>
      </div>
      <QueueDetailPanel item={item} mutatingAction={mutatingAction} onApplyAction={onApplyAction} onBatchAction={onBatchAction} />
    </div>
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
    return <OpsDetailPanel emptyDetail="Select a queue tile to inspect downstream readiness, source links, errors, and future job references." title="Queue detail panel" />;
  }

  const source = item.source_video;
  const exportPackageId = metadataString(item.metadata_json, "export_package_id");
  const publishHandoffId = metadataString(item.metadata_json, "publish_handoff_id");
  const thumbnailUrl = queueTileThumbnailUrl(item);

  return (
    <OpsDetailPanel title="Queue detail panel">
      <div className="capture-inbox-detail-hero compact reup-queue-detail-hero">
        {thumbnailUrl ? <img alt="" className="reup-queue-detail-thumb" src={thumbnailUrl} /> : null}
        <div>
          <div className="capture-inbox-detail-hero-topline">
            <span className={`review-board-tile-status-chip is-${queueStageTone(item)}`}>{queueStageLabel(item)}</span>
          </div>
          <p>{itemTitle(item)}</p>
          <p className="card-meta">Next: {item.next_action || "Needs action"}</p>
        </div>
      </div>

      <OpsDetailSection title="Overview">
        <OpsMetadataList items={[
          { label: "Status", value: operatorStatusLabel(item.status) },
          { label: "Queue stage", value: queueStageLabel(item) },
          { label: "Next action", value: item.next_action || "Needs action" },
          { label: "Priority", value: item.priority }
        ]} />
      </OpsDetailSection>

      <OpsDetailSection title="Queue lifecycle">
        <OpsMetadataList items={[
          { label: "Queued at", value: formatDateTime(item.queued_at) },
          { label: "Started at", value: formatDateTime(item.started_at) },
          { label: "Held at", value: formatDateTime(item.held_at) },
          { label: "Failed at", value: formatDateTime(item.failed_at) },
          { label: "Completed at", value: formatDateTime(item.completed_at) },
          { label: "Cancelled at", value: formatDateTime(item.cancelled_at) },
          { label: "Last action", value: item.last_action ? actionLabel(item.last_action) : "No operator action yet" },
          { label: "Last action note", value: item.last_action_note ?? "No note recorded" }
        ]} />
      </OpsDetailSection>

      <OpsDetailSection title="Source / review origin">
        <OpsMetadataList items={[
          { label: "Source video", value: item.source_video_id },
          { label: "External source id", value: source?.source_video_external_id ?? "Not captured" },
          { label: "Source profile", value: source?.source_profile_id ?? "Not captured" },
          { label: "Video candidate", value: item.video_candidate_id },
          { label: "Queued reason", value: item.queued_reason ?? "Review Board approved" },
          { label: "Operator note", value: item.operator_note ?? "No note recorded" }
        ]} />
      </OpsDetailSection>

      <OpsDetailSection title="Production pipeline">
        <div className="reup-queue-pipeline-strip reup-queue-pipeline-strip-detail" aria-label="Pipeline progress">
          {buildPipelineStages(item).map((stage) => (
            <span className={`reup-queue-pipeline-step is-${stage.state}`} key={stage.key}>{stage.label}</span>
          ))}
        </div>
      </OpsDetailSection>

      <OpsDetailSection title="Media prep">
        <OpsMetadataList items={[
          { label: "Media-prep status", value: operatorStatusLabel(item.media_prep_status) },
          { label: "Media-prep notes", value: item.media_prep_notes ?? "Not prepared yet" },
          { label: "Media ready at", value: formatDateTime(item.media_ready_at) },
          { label: "Linked job", value: item.job_id ? (
            <>
              {(item.job_type ?? "JOB").toUpperCase()}
              {" · "}
              {formatJobChipLabel(item) ?? item.job_status ?? "Attached"}
              {typeof item.job_progress_percent === "number" ? ` · ${item.job_progress_percent}%` : ""}
              {" · "}
              <a href={`/ops/jobs?job_id=${item.job_id}`}>Open job</a>
            </>
          ) : "No worker job attached yet" },
          { label: "Job error", value: item.job_error_message ?? item.job_error_code ?? item.last_error_message ?? "No job error" },
          { label: "Render output", value: item.render_output_id ?? "Not rendered yet" },
          { label: "Publish draft", value: item.publish_draft_id ?? "No publish draft yet" }
        ]} />
      </OpsDetailSection>

      <OpsDetailSection title="Export Package">
        <OpsMetadataList items={[
          { label: "Package status", value: exportPackageId ? "Export Package created" : item.status === "READY_TO_EXPORT" ? "Ready for Export Package" : "Not packaged" },
          { label: "Package link", value: exportPackageId ? <a href={`/publishing/export-packages/${exportPackageId}`}>{exportPackageId}</a> : "Not packaged" }
        ]} />
      </OpsDetailSection>

      <OpsDetailSection title="Publish Handoff">
        <OpsMetadataList items={[
          { label: "Handoff status", value: publishHandoffId ? "Handoff created" : item.status === "READY_TO_PUBLISH" ? "Ready for handoff" : "No handoff" },
          { label: "Handoff link", value: publishHandoffId ? <a href={`/publishing/publish-handoffs/${publishHandoffId}`}>{publishHandoffId}</a> : "No handoff" },
          { label: "Publish automation", value: "Not triggered here" }
        ]} />
      </OpsDetailSection>

      <ReupQueueInspectorActions item={item} mutatingAction={mutatingAction} onApplyAction={onApplyAction} onBatchAction={onBatchAction} />

      <OpsDetailSection collapsed title="Diagnostics">
        <OpsMetadataList items={[
          { label: "Blocked reason", value: item.blocked_reason ?? "No blocked reason recorded" },
          { label: "Blocked at", value: formatDateTime(item.blocked_at) },
          { label: "Last error", value: item.last_error_message ?? item.last_error_code ?? "No error recorded" }
        ]} />
        <details>
          <summary>View raw queue details</summary>
          <pre>{JSON.stringify(item, null, 2)}</pre>
        </details>
      </OpsDetailSection>
    </OpsDetailPanel>
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
  onApplyAction: (item: ReupQueueItem, action: ReupQueueAction) => void;
  onBatchAction: (action: ReupQueueBatchAction) => void;
}) {
  const disabled = mutatingAction !== null;
  const spotlight = pickInspectorSpotlightAction(item.available_actions);
  const remainingActions = spotlight
    ? item.available_actions.filter((entry) => entry.action !== spotlight.action)
    : item.available_actions;
  const { primary, neutral, danger } = groupInspectorLifecycleActions(remainingActions);
  const moreTransitions = [...primary, ...neutral];
  const workflowLinks = buildInspectorWorkflowLinks(item);
  const showExportPackage = item.status === "READY_TO_EXPORT" && item.media_prep_status === "READY_FOR_EXPORT";
  const showPublishHandoff = item.status === "READY_TO_PUBLISH";
  const hasLifecycle = Boolean(spotlight || moreTransitions.length || danger.length || showExportPackage || showPublishHandoff);

  const lifecycleButtons: Array<{ key: string; label: string; onClick: () => void; primary?: boolean; title?: string; working?: boolean }> = [];
  if (spotlight) {
    lifecycleButtons.push({
      key: spotlight.action,
      label: mutatingAction === spotlight.action ? "Working..." : spotlight.label,
      onClick: () => onApplyAction(item, spotlight.action),
      primary: true,
      title: spotlight.description,
      working: mutatingAction === spotlight.action
    });
  }
  if (showExportPackage) {
    lifecycleButtons.push({
      key: "CREATE_EXPORT_PACKAGE",
      label: "Create export package",
      onClick: () => onBatchAction("CREATE_EXPORT_PACKAGE"),
      primary: true
    });
  }
  if (showPublishHandoff) {
    lifecycleButtons.push({
      key: "CREATE_PUBLISH_HANDOFF",
      label: "Create publish handoff",
      onClick: () => onBatchAction("CREATE_PUBLISH_HANDOFF"),
      primary: true
    });
  }
  for (const available of moreTransitions) {
    lifecycleButtons.push({
      key: available.action,
      label: mutatingAction === available.action ? "Working..." : available.label,
      onClick: () => onApplyAction(item, available.action),
      primary: actionButtonClass(available.action) === "primary",
      title: available.description
    });
  }

  return (
    <OpsDetailSection title="Actions">
      <div className="reup-queue-inspector-actions is-compact">
        {!hasLifecycle && workflowLinks.length === 0 ? (
          <p className="reup-queue-inspector-empty">No lifecycle actions are currently available.</p>
        ) : null}

        {lifecycleButtons.length > 0 ? (
          <div className="reup-queue-inspector-btn-grid" data-count={String(lifecycleButtons.length)}>
            {lifecycleButtons.map((entry) => (
              <button
                className={`reup-queue-inspector-btn ${entry.primary ? "primary" : ""}`.trim()}
                disabled={disabled}
                key={entry.key}
                onClick={entry.onClick}
                title={entry.title}
                type="button"
              >
                {entry.label}
              </button>
            ))}
          </div>
        ) : null}

        {danger.length > 0 ? (
          <div className="reup-queue-inspector-btn-grid is-danger" data-count={String(danger.length)}>
            {danger.map((available) => (
              <button
                className="danger reup-queue-inspector-btn"
                disabled={disabled}
                key={available.action}
                onClick={() => onApplyAction(item, available.action)}
                title={available.description}
                type="button"
              >
                {mutatingAction === available.action ? "Working..." : available.label}
              </button>
            ))}
          </div>
        ) : null}

        {workflowLinks.length > 0 ? (
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
    </OpsDetailSection>
  );
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
  return null;
}

function defaultBatchActionNote(action: ReupQueueBatchAction): string | null {
  if (action === "HOLD") return "Operator batch-paused download progress from Reup Queue.";
  if (action === "CANCEL") return "Operator batch-cancelled downstream queue work.";
  if (action === "MARK_MEDIA_READY") return "Operator batch-confirmed media; start audio analysis.";
  if (action === "CREATE_EXPORT_PACKAGE") return "Operator created an Export Package from selected Reup Queue items.";
  if (action === "CREATE_PUBLISH_HANDOFF") return "Operator created a Publish Handoff payload from selected Reup Queue items.";
  if (action === "DISMISS") return "Operator cleared queue items from the active Reup Queue view.";
  if (action === "PURGE") return "Operator permanently deleted clearable queue records.";
  return null;
}

function batchSummary(action: ReupQueueBatchAction, result: BatchOperationResponse): string {
  const packageText = result.export_package_id ? ` Export Package: ${result.export_package_id}.` : "";
  const handoffText = result.publish_handoff_id ? ` Publish Handoff: ${result.publish_handoff_id}.` : "";
  return `${actionLabel(action)} completed: ${result.succeeded_count} succeeded, ${result.skipped_count} skipped, ${result.failed_count} failed.${packageText}${handoffText}`;
}

function actionButtonClass(action: ReupQueueAction): "primary" | "danger" | undefined {
  if (action === "CANCEL" || action === "MARK_BLOCKED") return "danger";
  if (action === "START_PROCESSING" || action === "MARK_MEDIA_READY" || action === "RETRY" || action === "RESUME") return "primary";
  return undefined;
}
