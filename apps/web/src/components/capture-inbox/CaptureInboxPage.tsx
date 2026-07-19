"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "next/navigation";

import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import {
  OpsConsolePage,
  OpsDetailPanel,
  OpsDetailSection,
  OpsEmptyState,
  OpsFilterBar,
  OpsMetadataList,
  OpsSection,
  OpsToolbarGroup
} from "../ops-console/OpsShared";
import { CaptureInboxTileActions } from "./CaptureInboxTileActions";
import {
  deleteCaptureInboxSession,
  fetchCaptureInboxItem,
  fetchCaptureInboxItems,
  fetchCaptureInboxProfileItems,
  fetchCaptureInboxProfileSummary,
  fetchCaptureInboxSession,
  fetchCaptureInboxSessions,
  queryCaptureInboxItems,
  runCaptureInboxAction
} from "../../lib/api";
import { hasMoreOffsetItems, mergeOffsetItemsById } from "../../lib/offsetListPagination";
import { OffsetLoadMoreFooter } from "../shared/OffsetLoadMoreFooter";
import {
  hasMoreCapturedItems,
  hasMoreCapturedItemsAfterPage,
  mergeCapturedItemsPage,
  pickProfileMatchedSessionId,
  reconcileGalleryTotalAfterStall,
  resolveGalleryTotalCount,
  resolveItemsLoadScopeForSession,
  shouldAutoLoadCaptureTail,
  shouldKeepManualSessionSelection,
  shouldUseProfileItemsScope,
  type CaptureInboxItemsLoadScope
} from "../../lib/captureInboxPagination";
import {
  resolveCommentCount,
  resolveDuration,
  exactEngagementMetricDisplay,
  resolveKnownViewCountValue,
  resolveLikeCount,
  resolveMediaAssetStatus,
  resolvePosted,
  resolvePreviewStatus,
  resolveShareCount,
  resolveSourceLinkStatus,
  resolveThumbnailDisplayUrl,
  resolveThumbnailUrl,
  resolveViewCount
} from "../../lib/captureInboxCanonical";
import {
  inspectorMetadataQualityItems,
  inspectorPerformanceItems,
  itemNeedsInspectorHydration
} from "../../lib/captureInboxInspector";
import {
  estimatedViewsRangeMatches,
  getDouyinItemMetadataForFilters,
  getDouyinMetadataCompletenessForItem,
  formatCaptureInboxTileMetadataGap,
  getEstimatedViewsForItem,
  metadataHealthCounts,
  metadataHealthMatches,
  parseCompactNumber,
  parseCompactNumberInput,
  type ComparableEstimatedViews,
  type MetadataHealthFilter
} from "../../lib/captureInboxFilterMetadata";
import { getReupScoreForCaptureItem } from "../../lib/captureInboxReupScore";
import {
  formatReupScoreBadgeValue,
  reupScoreBadgeLevelForCaptureItem,
  reupScoreBadgeTier
} from "../../lib/reupScoreBadge";
import {
  DOUYIN_REVIEW_PRESETS,
  getDouyinReviewPresetConfig,
  getDouyinReviewPresetCounts,
  matchesDouyinReviewPreset,
  type DouyinReviewPreset,
  type DouyinReviewPresetId
} from "../../lib/captureInboxReviewPresets";
import {
  buildPromoteSuccessSummary,
  CAPTURE_INBOX_REVIEW_BOARD_HREF,
  promoteSuccessFollowUpLabel,
  type PromoteSuccessSummary
} from "../../lib/captureInboxPromoteNotice";
import {
  buildReupScoreBreakdownBars,
  shouldShowCaptureInboxTileMetrics
} from "../../lib/captureInboxPresentation";
import {
  CAPTURE_INBOX_POWER_DEFAULT_SORT,
  pickLatestCaptureSessionId,
  selectTopPromotableCaptureItems,
  sortCaptureSessionsNewestFirst
} from "../../lib/captureInboxUx";
import type {
  CapturedItem,
  CapturedItemStatus,
  CaptureInboxAction,
  CaptureInboxAdvancedFilter,
  CaptureInboxProfileSummaryResponse,
  CaptureSession,
  CaptureSessionDetail,
  CaptureSessionStatus
} from "../../types/capture-inbox";

type StudioItemStatusFilter = "all" | "ready" | "needs_action" | "failed" | "duplicate" | "promoted";
type MetadataStatusFilter = "all" | "complete" | "missing_posted" | "missing_thumbnail" | "missing_duration" | "missing_metrics";
type SortMode = "ready_first" | "recently_captured" | "newest_posted" | "oldest_posted" | "highest_views" | "highest_likes" | "highest_comments" | "highest_shares" | "highest_engagement" | "highest_reup_score" | "lowest_reup_score" | "shortest_duration" | "longest_duration";
type StudioFilters = {
  searchQuery: string;
  itemStatus: StudioItemStatusFilter;
  metadataFilter: MetadataStatusFilter;
  onlyActionable: boolean;
  onlyWithThumbnail: boolean;
  hideDuplicates: boolean;
  sort: SortMode;
};
type OperatorBadge = "Ready" | "Duplicate" | "Needs action" | "Failed" | "Promoted" | "Preview pending" | "Excluded";
type BulkAction = "promote" | "recheck" | "delete";
type BulkActionDialog = { action: BulkAction; eligibility: BulkActionEligibility } | null;
type BulkActionEligibility = {
  selectedItems: CapturedItem[];
  promotableItems: CapturedItem[];
  recheckableItems: CapturedItem[];
  deletableItems: CapturedItem[];
  blockedItems: CapturedItem[];
  reasonsByItemId: Record<string, string>;
};
type BulkActionResultSummary = {
  action: BulkAction;
  requestedCount: number;
  eligibleCount: number;
  affectedCount: number;
  skippedCount: number;
  backendMessage: string;
};
type TileQuickMetaChip = { label: string; value: string };
type TileMetricCell = { label: "Views" | "Est. Views" | "Likes" | "Comments" | "Shares"; value: string; title?: string };
type TileCardModel = {
  metadataGap: string | null;
  metrics: TileMetricCell[];
  quickMetaChips: TileQuickMetaChip[];
};

const SESSION_STATUS_OPTIONS: Array<"all" | CaptureSessionStatus> = [
  "all",
  "RECEIVED",
  "ENRICHING",
  "READY_FOR_REVIEW",
  "PARTIALLY_PROMOTED",
  "PROMOTED",
  "FAILED"
];

const SESSION_PAGE_SIZE = 25;

const SORT_OPTIONS: Array<{ key: SortMode; label: string }> = [
  { key: "ready_first", label: "Ready first" },
  { key: "recently_captured", label: "Recently captured" },
  { key: "newest_posted", label: "Newest posted" },
  { key: "oldest_posted", label: "Oldest posted" },
  { key: "highest_views", label: "Highest views" },
  { key: "highest_likes", label: "Highest likes" },
  { key: "highest_comments", label: "Highest comments" },
  { key: "highest_shares", label: "Highest shares" },
  { key: "highest_engagement", label: "Highest engagement" },
  { key: "highest_reup_score", label: "Highest Reup Score" },
  { key: "lowest_reup_score", label: "Lowest Reup Score" },
  { key: "shortest_duration", label: "Shortest duration" },
  { key: "longest_duration", label: "Longest duration" }
];

const SUMMARY_FILTERS: Array<{ key: StudioItemStatusFilter; label: string }> = [
  { key: "all", label: "Captured" },
  { key: "ready", label: "Ready" },
  { key: "duplicate", label: "Duplicates" },
  { key: "needs_action", label: "Needs action" },
  { key: "failed", label: "Failed" },
  { key: "promoted", label: "Promoted" }
];

const TARGET_DEBUG_AWEME_IDS = new Set(["7628281732369796388", "7631223404342857006", "7628596519502892307"]);

const CAPTURE_INBOX_ITEMS_PAGE_SIZE = 100;
const CAPTURE_INBOX_VIRTUAL_ROW_HEIGHT = 520;
const CAPTURE_INBOX_VIRTUAL_OVERSCAN_ROWS = 2;
const CAPTURE_INBOX_VIRTUAL_MIN_COLUMN_WIDTH = 260;
const CAPTURE_INBOX_PROMOTE_TOP_BATCHES = [5, 10, 20] as const;
const CAPTURE_INBOX_UI_VERSION = "22G-3C";
const CAPTURE_INBOX_PRIMARY_PRESET_IDS: DouyinReviewPresetId[] = ["ready_to_promote", "high_potential", "needs_cleanup"];

const METADATA_STATUS_OPTIONS: Array<{ key: MetadataStatusFilter; label: string; title: string }> = [
  { key: "all", label: "All", title: "All metadata" },
  { key: "complete", label: "Complete", title: "Complete metadata" },
  { key: "missing_posted", label: "No date", title: "Missing posted date" },
  { key: "missing_thumbnail", label: "No thumb", title: "Missing thumbnail" },
  { key: "missing_duration", label: "No duration", title: "Missing duration" },
  { key: "missing_metrics", label: "No metrics", title: "Missing metrics" }
];

type MetadataHealthCountMap = Record<MetadataHealthFilter, number>;

type AdvancedFilterDraft = {
  postedFrom: string;
  postedTo: string;
  capturedFrom: string;
  capturedTo: string;
  minDurationSeconds: string;
  maxDurationSeconds: string;
  minEstimatedViews: string;
  maxEstimatedViews: string;
  minLikes: string;
  maxLikes: string;
  minComments: string;
  maxComments: string;
  minShares: string;
  maxShares: string;
  minEngagementScore: string;
  maxEngagementScore: string;
  minEngagementRate: string;
  maxEngagementRate: string;
  metadataHealthFilters: MetadataHealthFilter[];
};

type AdvancedAppliedFilters = {
  postedFrom: string | null;
  postedTo: string | null;
  capturedFrom: string | null;
  capturedTo: string | null;
  minDurationSeconds: number | null;
  maxDurationSeconds: number | null;
  minEstimatedViews: number | null;
  maxEstimatedViews: number | null;
  minLikes: number | null;
  maxLikes: number | null;
  minComments: number | null;
  maxComments: number | null;
  minShares: number | null;
  maxShares: number | null;
  minEngagementScore: number | null;
  maxEngagementScore: number | null;
  minEngagementRate: number | null;
  maxEngagementRate: number | null;
  metadataHealthFilters: MetadataHealthFilter[];
};

const DEFAULT_ADVANCED_FILTER_DRAFT: AdvancedFilterDraft = {
  postedFrom: "",
  postedTo: "",
  capturedFrom: "",
  capturedTo: "",
  minDurationSeconds: "",
  maxDurationSeconds: "",
  minEstimatedViews: "",
  maxEstimatedViews: "",
  minLikes: "",
  maxLikes: "",
  minComments: "",
  maxComments: "",
  minShares: "",
  maxShares: "",
  minEngagementScore: "",
  maxEngagementScore: "",
  minEngagementRate: "",
  maxEngagementRate: "",
  metadataHealthFilters: []
};

function advancedFilterValidationMessage(draft: AdvancedFilterDraft): string | null {
  const postedRangeError = validateDateRange("Posted date", draft.postedFrom, draft.postedTo);
  if (postedRangeError) return postedRangeError;

  const minViews = parseCompactNumberInput(draft.minEstimatedViews);
  const maxViews = parseCompactNumberInput(draft.maxEstimatedViews);
  if (!minViews.valid || !maxViews.valid) return "Invalid estimated views format. Try 10000, 10K, 1.2M, or 3万.";
  if (minViews.value !== null && maxViews.value !== null && minViews.value > maxViews.value) return "Min estimated views must be less than Max estimated views.";

  const rangeChecks: Array<{ label: string; min: string; max: string; parser: (value: string) => number | null }> = [
    { label: "Duration", min: draft.minDurationSeconds, max: draft.maxDurationSeconds, parser: parseDurationFilterInput },
    { label: "Likes", min: draft.minLikes, max: draft.maxLikes, parser: parseCompactNumber }
  ];

  for (const check of rangeChecks) {
    const message = validateNumericRange(check.label, check.min, check.max, check.parser);
    if (message) return message;
  }

  return null;
}

function validateDateRange(label: string, fromValue: string, toValue: string): string | null {
  const from = fromValue ? dateInputStartValue(fromValue) : null;
  const to = toValue ? dateInputEndValue(toValue) : null;
  if (fromValue && from === null) return `${label} from is invalid.`;
  if (toValue && to === null) return `${label} to is invalid.`;
  if (from !== null && to !== null && from > to) return `${label} from must be before or equal to ${label.toLowerCase()} to.`;
  return null;
}

function validateNumericRange(label: string, minValue: string, maxValue: string, parser: (value: string) => number | null): string | null {
  const min = minValue.trim() ? parser(minValue) : null;
  const max = maxValue.trim() ? parser(maxValue) : null;
  if (minValue.trim() && min === null) return `${label} minimum is invalid.`;
  if (maxValue.trim() && max === null) return `${label} maximum is invalid.`;
  if (min !== null && max !== null && min > max) return `${label} minimum must be less than or equal to maximum.`;
  return null;
}

function advancedFilterSummaryItems(filters: AdvancedAppliedFilters | null): string[] {
  if (!filters) return [];
  const items: string[] = [];

  pushDateRangeSummary(items, "Posted", filters.postedFrom, filters.postedTo);
  pushDateRangeSummary(items, "Captured", filters.capturedFrom, filters.capturedTo);
  pushNumericRangeSummary(items, "Duration", filters.minDurationSeconds, filters.maxDurationSeconds, formatDurationSummaryValue);
  pushNumericRangeSummary(items, "Est. views", filters.minEstimatedViews, filters.maxEstimatedViews, formatCompactNumber);
  pushNumericRangeSummary(items, "Likes", filters.minLikes, filters.maxLikes, formatCompactNumber);
  pushNumericRangeSummary(items, "Comments", filters.minComments, filters.maxComments, formatCompactNumber);
  pushNumericRangeSummary(items, "Shares", filters.minShares, filters.maxShares, formatCompactNumber);
  pushNumericRangeSummary(items, "Engagement score", filters.minEngagementScore, filters.maxEngagementScore, formatCompactNumber);
  pushNumericRangeSummary(items, "Engagement rate", filters.minEngagementRate, filters.maxEngagementRate, (value) => `${formatNumber(value * 100, "0")}%`);

  for (const filter of filters.metadataHealthFilters) {
    if (filter === "complete") items.push("Metadata: Complete");
    if (filter === "missing_posted") items.push("Missing posted");
    if (filter === "missing_thumbnail") items.push("Missing thumbnail");
    if (filter === "missing_duration") items.push("Missing duration");
    if (filter === "missing_views") items.push("Missing views");
    if (filter === "missing_metrics") items.push("Missing metrics");
    if (filter === "actionable") items.push("Actionable only");
  }

  return items;
}

function countCaptureInboxActiveFilters({
  activePreset,
  appliedAdvancedFilter,
  baselineFilter,
  baselineSort,
  filter,
  hideDuplicates,
  onlyActionable,
  onlyWithThumbnail,
  searchQuery,
  sortMode
}: {
  activePreset: DouyinReviewPreset;
  appliedAdvancedFilter: AdvancedAppliedFilters | null;
  baselineFilter: StudioItemStatusFilter;
  baselineSort: SortMode;
  filter: StudioItemStatusFilter;
  hideDuplicates: boolean;
  onlyActionable: boolean;
  onlyWithThumbnail: boolean;
  searchQuery: string;
  sortMode: SortMode;
}): number {
  let count = 0;
  if (filter !== baselineFilter) count += 1;
  if (searchQuery.trim()) count += 1;
  if (sortMode !== baselineSort) count += 1;
  if (onlyActionable) count += 1;
  if (onlyWithThumbnail) count += 1;
  if (hideDuplicates) count += 1;
  if (activePreset !== "none") count += 1;
  if (appliedAdvancedFilter) count += advancedFilterSummaryItems(appliedAdvancedFilter).length;
  return count;
}

function pushDateRangeSummary(items: string[], label: string, fromValue: string | null, toValue: string | null): void {
  if (!fromValue && !toValue) return;
  if (fromValue && toValue) {
    items.push(`${label}: ${formatDateChip(fromValue)} → ${formatDateChip(toValue)}`);
    return;
  }
  if (fromValue) {
    items.push(`${label}: ≥ ${formatDateChip(fromValue)}`);
    return;
  }
  items.push(`${label}: ≤ ${formatDateChip(toValue as string)}`);
}

function pushNumericRangeSummary(items: string[], label: string, min: number | null, max: number | null, formatValue: (value: number) => string = formatCompactNumber): void {
  if (min === null && max === null) return;

  if (min !== null && max !== null) {
    items.push(`${label} ${formatValue(min)}–${formatValue(max)}`);
    return;
  }
  if (min !== null) {
    items.push(`${label} ≥ ${formatValue(min)}`);
    return;
  }
  items.push(`${label} ≤ ${formatValue(max as number)}`);
}

function formatDateChip(value: string): string {
  const [year, month, day] = value.split("-");
  return year && month && day ? `${day}/${month}/${year}` : value;
}

function formatDurationSummaryValue(value: number): string {
  if (value >= 3600) return `${Math.round(value / 3600)}h`;
  if (value >= 60) return `${Math.round(value / 60)} min`;
  return `${value}s`;
}

function formatCompactNumber(value: number): string {
  return new Intl.NumberFormat("en", { maximumFractionDigits: 1, notation: "compact" }).format(value);
}

type SessionItemsPage = {
  items: CapturedItem[];
  total_count: number;
  unique_video_count?: number | null;
};

function resolveSessionItemsGalleryTotal(
  loadScope: CaptureInboxItemsLoadScope,
  page: SessionItemsPage,
  sessionCapturedCount?: number | null,
  itemStatusFilter: StudioItemStatusFilter = "all"
): number {
  if (loadScope === "session" && !usesServerStatusFilter(itemStatusFilter) && sessionCapturedCount != null) {
    return sessionCapturedCount;
  }
  return resolveGalleryTotalCount(loadScope, page.total_count, page.unique_video_count);
}

function studioFilterToApiStatus(filter: StudioItemStatusFilter): CapturedItemStatus | undefined {
  if (filter === "ready") return "READY";
  if (filter === "duplicate") return "DUPLICATE";
  if (filter === "failed") return "FAILED";
  if (filter === "promoted") return "PROMOTED";
  return undefined;
}

function usesServerStatusFilter(filter: StudioItemStatusFilter): boolean {
  return filter === "ready" || filter === "duplicate" || filter === "failed" || filter === "promoted";
}

export function CaptureInboxPage() {
  const searchParams = useSearchParams();
  const profileUrlFromQuery = searchParams.get("profile_url")?.trim() || null;
  const [sessions, setSessions] = useState<CaptureSession[]>([]);
  const [sessionsTotalCount, setSessionsTotalCount] = useState(0);
  const [loadingMoreSessions, setLoadingMoreSessions] = useState(false);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [selectedSession, setSelectedSession] = useState<CaptureSessionDetail | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | CaptureSessionStatus>("all");
  const [operatorFilter, setOperatorFilter] = useState<StudioItemStatusFilter>("all");
  const [metadataFilter, setMetadataFilter] = useState<MetadataStatusFilter>("all");
  const [searchQuery, setSearchQuery] = useState<StudioFilters["searchQuery"]>("");
  const [sortMode, setSortMode] = useState<SortMode>(CAPTURE_INBOX_POWER_DEFAULT_SORT);
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([]);
  const [lastSelectedAt, setLastSelectedAt] = useState<string | null>(null);
  const selectionScope = "visible_items" as const;
  const [onlyActionable, setOnlyActionable] = useState(false);
  const [onlyWithThumbnail, setOnlyWithThumbnail] = useState(false);
  const [hideDuplicates, setHideDuplicates] = useState(false);
  const [activeItemId, setActiveItemId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<CaptureInboxAction | "delete_session" | "refresh" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [promoteSuccess, setPromoteSuccess] = useState<PromoteSuccessSummary | null>(null);
  const [rawDetails, setRawDetails] = useState<Array<Record<string, unknown>>>([]);
  const [sourceUrls, setSourceUrls] = useState<string[]>([]);
  const [rightInspectorOpen, setRightInspectorOpen] = useState(false);
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(true);
  const [advancedFilterDraft, setAdvancedFilterDraft] = useState<AdvancedFilterDraft>(DEFAULT_ADVANCED_FILTER_DRAFT);
  const [appliedAdvancedFilter, setAppliedAdvancedFilter] = useState<AdvancedAppliedFilters | null>(null);
  const [queryLoading, setQueryLoading] = useState(false);
  const [activePreset, setActivePreset] = useState<DouyinReviewPreset>("none");
  const [sortTouched, setSortTouched] = useState(false);
  const [bulkActionDialog, setBulkActionDialog] = useState<BulkActionDialog>(null);
  const [profileSummary, setProfileSummary] = useState<CaptureInboxProfileSummaryResponse | null>(null);
  const [profileSummaryLoading, setProfileSummaryLoading] = useState(false);
  const [profileSummaryError, setProfileSummaryError] = useState<string | null>(null);
  const [sessionItems, setSessionItems] = useState<CapturedItem[]>([]);
  const [sessionItemsTotalCount, setSessionItemsTotalCount] = useState(0);
  const [hasMoreSessionItems, setHasMoreSessionItems] = useState(false);
  const [sessionItemsLoadingMore, setSessionItemsLoadingMore] = useState(false);
  const inspectorHydrationRef = useRef<Set<string>>(new Set());
  const manualSessionSelectionRef = useRef<string | null>(null);
  const loadMoreInFlightRef = useRef(false);
  const itemsLoadGenerationRef = useRef(0);
  const [itemsLoadScope, setItemsLoadScope] = useState<CaptureInboxItemsLoadScope>("session");
  const [inspectorDetailLoading, setInspectorDetailLoading] = useState(false);
  const [inspectorPinnedItem, setInspectorPinnedItem] = useState<CapturedItem | null>(null);

  async function loadSessions(preferredSessionId?: string | null) {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchCaptureInboxSessions({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: SESSION_PAGE_SIZE,
        offset: 0
      });
      const sortedSessions = sortCaptureSessionsNewestFirst(payload.sessions);
      setSessions(sortedSessions);
      setSessionsTotalCount(payload.total_count);
      const profileIdentifier = profileSummary?.profile_identifier ?? null;
      const profileMatchedSessionId = profileUrlFromQuery
        ? pickProfileMatchedSessionId(sortedSessions, profileUrlFromQuery, profileIdentifier)
        : null;
      const nextSessionId =
        preferredSessionId ??
        selectedSessionId ??
        profileMatchedSessionId ??
        pickLatestCaptureSessionId(sortedSessions);
      const loadScope = resolveItemsLoadScopeForSession(profileUrlFromQuery, nextSessionId, profileMatchedSessionId);
      setSelectedSessionId(nextSessionId);
      if (nextSessionId) {
        await loadSession(nextSessionId, operatorFilter, loadScope);
      } else {
        setSelectedSession(null);
        setSessionItems([]);
        setSessionItemsTotalCount(0);
        setHasMoreSessionItems(false);
        setSelectedItemIds([]);
        setActiveItemId(null);
        setRightInspectorOpen(false);
        setRawDetails([]);
        setSourceUrls([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load Capture Inbox");
    } finally {
      setLoading(false);
    }
  }

  async function loadMoreSessions() {
    if (loadingMoreSessions || !hasMoreOffsetItems(sessions.length, sessionsTotalCount)) return;
    setLoadingMoreSessions(true);
    setError(null);
    try {
      const payload = await fetchCaptureInboxSessions({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: SESSION_PAGE_SIZE,
        offset: sessions.length
      });
      setSessions((current) =>
        sortCaptureSessionsNewestFirst(mergeOffsetItemsById(current, payload.sessions))
      );
      setSessionsTotalCount(payload.total_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load more capture sessions");
    } finally {
      setLoadingMoreSessions(false);
    }
  }

  const profileMatchedSessionId = useMemo(() => {
    if (!profileUrlFromQuery || sessions.length === 0) return null;
    return pickProfileMatchedSessionId(sessions, profileUrlFromQuery, profileSummary?.profile_identifier ?? null);
  }, [profileSummary?.profile_identifier, profileUrlFromQuery, sessions]);

  async function fetchSessionItemsPage(
    sessionId: string,
    offset: number,
    itemStatusFilter: StudioItemStatusFilter,
    loadScope: CaptureInboxItemsLoadScope = itemsLoadScope
  ): Promise<SessionItemsPage> {
    const apiStatus = studioFilterToApiStatus(itemStatusFilter);
    const serverStatus = usesServerStatusFilter(itemStatusFilter) ? apiStatus : undefined;
    if (shouldUseProfileItemsScope(profileUrlFromQuery, loadScope)) {
      if (serverStatus) {
        const page = await fetchCaptureInboxItems({
          profileUrl: profileUrlFromQuery!,
          status: serverStatus,
          limit: CAPTURE_INBOX_ITEMS_PAGE_SIZE,
          offset
        });
        return { items: page.items, total_count: page.total_count };
      }
      const page = await fetchCaptureInboxProfileItems({
        profileUrl: profileUrlFromQuery!,
        limit: CAPTURE_INBOX_ITEMS_PAGE_SIZE,
        offset
      });
      return {
        items: page.items,
        total_count: page.total_count,
        unique_video_count: page.unique_video_count
      };
    }
    const page = await fetchCaptureInboxItems({
      captureSessionId: sessionId,
      status: serverStatus,
      limit: CAPTURE_INBOX_ITEMS_PAGE_SIZE,
      offset
    });
    return { items: page.items, total_count: page.total_count };
  }

  async function loadSession(
    sessionId: string,
    itemStatusFilter: StudioItemStatusFilter = operatorFilter,
    loadScope: CaptureInboxItemsLoadScope = resolveItemsLoadScopeForSession(
      profileUrlFromQuery,
      sessionId,
      profileMatchedSessionId
    )
  ) {
    const generation = ++itemsLoadGenerationRef.current;
    setItemsLoadScope(loadScope);
    setSessionItems([]);
    setSessionItemsTotalCount(0);
    setHasMoreSessionItems(false);
    loadMoreInFlightRef.current = false;
    const detail = await fetchCaptureInboxSession(sessionId);
    if (generation !== itemsLoadGenerationRef.current) return;
    setSelectedSession({ ...detail, items: [] });
    setSelectedSessionId(detail.id);
    const firstPage = await fetchSessionItemsPage(sessionId, 0, itemStatusFilter, loadScope);
    if (generation !== itemsLoadGenerationRef.current) return;
    const items = firstPage.items;
    const galleryTotal = resolveSessionItemsGalleryTotal(loadScope, firstPage, detail.captured_item_count, itemStatusFilter);
    setSessionItems(items);
    setSessionItemsTotalCount(galleryTotal);
    setHasMoreSessionItems(hasMoreCapturedItems(items.length, galleryTotal));
    const hydratedDetail: CaptureSessionDetail = {
      ...detail,
      items,
      captured_item_count: detail.captured_item_count,
      ready_item_count: detail.ready_item_count,
      duplicate_item_count: detail.duplicate_item_count,
      failed_item_count: detail.failed_item_count
    };
    const itemIds = new Set(hydratedDetail.items.map((item) => item.id));
    setSelectedSession(hydratedDetail);
    clearSelectionState();
    setActiveItemId((current) => {
      const nextActiveItemId = current && itemIds.has(current) ? current : null;
      setRightInspectorOpen((open) => open && Boolean(nextActiveItemId));
      return nextActiveItemId;
    });
    setAppliedAdvancedFilter(null);
  }

  const loadMoreSessionItems = useCallback(async () => {
    if (!selectedSessionId || sessionItemsLoadingMore || !hasMoreSessionItems || loadMoreInFlightRef.current) {
      return;
    }
    const generation = itemsLoadGenerationRef.current;
    loadMoreInFlightRef.current = true;
    setSessionItemsLoadingMore(true);
    setError(null);
    try {
      const offset = sessionItems.length;
      const nextPage = await fetchSessionItemsPage(selectedSessionId, offset, operatorFilter, itemsLoadScope);
      if (generation !== itemsLoadGenerationRef.current) return;
      const { merged, appendedCount } = mergeCapturedItemsPage(sessionItems, nextPage.items, itemsLoadScope);
      let galleryTotal = resolveSessionItemsGalleryTotal(
        itemsLoadScope,
        nextPage,
        selectedSession?.captured_item_count,
        operatorFilter
      );
      let hasMore = hasMoreCapturedItemsAfterPage(merged.length, galleryTotal, nextPage.items.length, appendedCount);
      if (!hasMore && appendedCount === 0 && merged.length < galleryTotal) {
        galleryTotal = reconcileGalleryTotalAfterStall(merged.length, galleryTotal);
        hasMore = false;
      }
      setSessionItems(merged);
      setSessionItemsTotalCount(galleryTotal);
      setHasMoreSessionItems(hasMore);
      setSelectedSession((current) => {
        if (!current) return current;
        const { merged: mergedSessionItems } = mergeCapturedItemsPage(current.items, nextPage.items, itemsLoadScope);
        return { ...current, items: mergedSessionItems };
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load more Capture Inbox items");
    } finally {
      loadMoreInFlightRef.current = false;
      setSessionItemsLoadingMore(false);
    }
  }, [hasMoreSessionItems, itemsLoadScope, operatorFilter, profileUrlFromQuery, selectedSessionId, sessionItems.length, sessionItemsLoadingMore]);

  useEffect(() => {
    if (!selectedSessionId || loading || sessionItemsLoadingMore || !hasMoreSessionItems) {
      return;
    }
    if (!shouldAutoLoadCaptureTail(sessionItems.length, sessionItemsTotalCount, CAPTURE_INBOX_ITEMS_PAGE_SIZE)) {
      return;
    }
    void loadMoreSessionItems();
  }, [
    hasMoreSessionItems,
    loadMoreSessionItems,
    loading,
    selectedSessionId,
    sessionItems.length,
    sessionItemsLoadingMore,
    sessionItemsTotalCount
  ]);

  useEffect(() => {
    manualSessionSelectionRef.current = null;
    setItemsLoadScope(profileUrlFromQuery ? "profile" : "session");
  }, [profileUrlFromQuery]);

  useEffect(() => {
    if (!selectedSessionId || !usesServerStatusFilter(operatorFilter)) {
      return;
    }
    void loadSession(selectedSessionId, operatorFilter, itemsLoadScope).catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to reload Capture Inbox items");
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operatorFilter, selectedSessionId]);

  useEffect(() => {
    void loadSessions(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  useEffect(() => {
    if (!profileUrlFromQuery) {
      setProfileSummary(null);
      setProfileSummaryError(null);
      setProfileSummaryLoading(false);
      return;
    }
    let cancelled = false;
    setProfileSummaryLoading(true);
    void fetchCaptureInboxProfileSummary(profileUrlFromQuery)
      .then((summary) => {
        if (cancelled) return;
        setProfileSummary(summary);
        setProfileSummaryError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setProfileSummary(null);
        setProfileSummaryError(err instanceof Error ? err.message : "Failed to load profile summary");
      })
      .finally(() => {
        if (!cancelled) {
          setProfileSummaryLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [profileUrlFromQuery]);

  useEffect(() => {
    if (!profileUrlFromQuery || sessions.length === 0) {
      return;
    }
    const profileIdentifier = profileSummary?.profile_identifier ?? null;
    const matchedSessionId = pickProfileMatchedSessionId(sessions, profileUrlFromQuery, profileIdentifier);
    if (!matchedSessionId || matchedSessionId === selectedSessionId) {
      return;
    }
    if (
      shouldKeepManualSessionSelection(
        manualSessionSelectionRef.current,
        matchedSessionId,
        selectedSessionId
      )
    ) {
      return;
    }
    void selectSession(matchedSessionId, { manual: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profileUrlFromQuery, profileSummary?.profile_identifier, sessions, selectedSessionId]);

  const summary = useMemo(
    () => buildAuthoritativeSummary(selectedSession, profileSummary, profileUrlFromQuery, sessionItems, itemsLoadScope),
    [itemsLoadScope, profileSummary, profileUrlFromQuery, selectedSession, sessionItems]
  );
  const latestSessionId = useMemo(() => pickLatestCaptureSessionId(sessions), [sessions]);
  const operatorFilterBaseline: StudioItemStatusFilter = "all";
  const sortModeBaseline: SortMode = CAPTURE_INBOX_POWER_DEFAULT_SORT;

  const baseItems = sessionItems;

  const studioFilteredItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return [...baseItems]
      .filter((item) => usesServerStatusFilter(operatorFilter) || matchesItemStatusFilter(item, operatorFilter))
      .filter((item) => matchesMetadataFilter(item, metadataFilter))
      .filter((item) => !query || searchableText(item).includes(query))
      .filter((item) => !onlyActionable || isActionableItem(item))
      .filter((item) => !onlyWithThumbnail || hasUsableThumbnail(item))
      .filter((item) => !hideDuplicates || item.status !== "DUPLICATE");
  }, [baseItems, hideDuplicates, metadataFilter, onlyActionable, onlyWithThumbnail, operatorFilter, searchQuery]);

  const metadataHealthCountMap = useMemo(() => metadataHealthCounts(studioFilteredItems), [studioFilteredItems]);
  const presetCountMap = useMemo(() => getDouyinReviewPresetCounts(studioFilteredItems), [studioFilteredItems]);

  const advancedFilterDebug = useMemo(() => buildAdvancedFilterDebug(studioFilteredItems, appliedAdvancedFilter, advancedFilterDraft), [appliedAdvancedFilter, advancedFilterDraft, studioFilteredItems]);

  useEffect(() => {
    if (process.env.NODE_ENV === "production" || !advancedFilterDebug.estimatedViews.filterActive) return;
    console.debug("capture_inbox_advanced_filter_debug", advancedFilterDebug);
  }, [advancedFilterDebug]);

  const visibleItems = useMemo(() => {
    return [...studioFilteredItems]
      .filter((item) => matchesDouyinReviewPreset(item, activePreset))
      .filter((item) => matchesAdvancedAppliedFilters(item, appliedAdvancedFilter))
      .sort((left, right) => compareItems(left, right, sortMode));
  }, [activePreset, appliedAdvancedFilter, studioFilteredItems, sortMode]);

  const bulkActionEligibility = useMemo(() => getBulkActionEligibility(visibleItems, selectedItemIds), [selectedItemIds, visibleItems]);

  const activeItem = useMemo(() => {
    if (!activeItemId) return null;
    return sessionItems.find((item) => item.id === activeItemId)
      ?? inspectorPinnedItem
      ?? visibleItems.find((item) => item.id === activeItemId)
      ?? null;
  }, [activeItemId, inspectorPinnedItem, sessionItems, visibleItems]);

  useEffect(() => {
    if (!activeItemId) return;
    if (!sessionItems.some((item) => item.id === activeItemId)) {
      setRightInspectorOpen(false);
      setActiveItemId(null);
      setInspectorPinnedItem(null);
    }
  }, [activeItemId, sessionItems]);

  useEffect(() => {
    inspectorHydrationRef.current.clear();
  }, [selectedSessionId, profileUrlFromQuery]);

  useEffect(() => {
    if (!activeItem || !rightInspectorOpen || !itemNeedsInspectorHydration(activeItem)) {
      setInspectorDetailLoading(false);
      return;
    }
    if (inspectorHydrationRef.current.has(activeItem.id)) return;

    let cancelled = false;
    setInspectorDetailLoading(true);
    void (async () => {
      try {
        const detail = await fetchCaptureInboxItem(activeItem.id);
        if (cancelled) return;
        inspectorHydrationRef.current.add(activeItem.id);
        setSessionItems((current) => mergeSessionItemDetail(current, detail));
        setSelectedSession((current) => {
          if (!current) return current;
          return { ...current, items: mergeSessionItemDetail(current.items, detail) };
        });
        setInspectorPinnedItem((current) => (current?.id === detail.id ? { ...current, ...detail } : current));
      } catch (err) {
        if (!cancelled) {
          setNotice(err instanceof Error ? err.message : "Failed to load item details");
        }
      } finally {
        if (!cancelled) setInspectorDetailLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [activeItem, rightInspectorOpen]);

  useEffect(() => {
    clearSelectionState();
    setBulkActionDialog(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedSessionId, operatorFilter, metadataFilter, searchQuery, onlyActionable, onlyWithThumbnail, hideDuplicates, activePreset, appliedAdvancedFilter, sortMode]);

  async function selectSession(sessionId: string, options?: { manual?: boolean }) {
    const manual = options?.manual ?? true;
    if (manual) {
      manualSessionSelectionRef.current = sessionId;
    }
    const loadScope = resolveItemsLoadScopeForSession(
      profileUrlFromQuery,
      sessionId,
      profileMatchedSessionId,
      manual
    );
    itemsLoadGenerationRef.current += 1;
    setSelectedSessionId(sessionId);
    setItemsLoadScope(loadScope);
    setSessionItems([]);
    setHasMoreSessionItems(false);
    loadMoreInFlightRef.current = false;
    const sessionMeta = sessions.find((session) => session.id === sessionId);
    if (sessionMeta) {
      setSelectedSession({ ...sessionMeta, items: [] });
      setSessionItemsTotalCount(sessionMeta.captured_item_count);
    } else {
      setSelectedSession(null);
      setSessionItemsTotalCount(0);
    }
    setWorking("refresh");
    setError(null);
    setNotice(null);
    setRawDetails([]);
    setSourceUrls([]);
    try {
      await loadSession(sessionId, operatorFilter, loadScope);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load capture session");
    } finally {
      setWorking(null);
    }
  }

  function updateAdvancedFilterDraft<K extends keyof AdvancedFilterDraft>(key: K, value: AdvancedFilterDraft[K]) {
    setAdvancedFilterDraft((current) => ({ ...current, [key]: value }));
  }

  function clearSelectionState() {
    setSelectedItemIds([]);
    setLastSelectedAt(null);
  }

  async function applyAdvancedFilters() {
    setQueryLoading(true);
    setError(null);
    try {
      const validationMessage = advancedFilterValidationMessage(advancedFilterDraft);
      if (validationMessage) {
        setError(validationMessage);
        return;
      }
      const advancedFilter = buildAdvancedFilterPayload(advancedFilterDraft);
      const filteredItemIds = new Set(baseItems.filter((item) => matchesAdvancedAppliedFilters(item, advancedFilter)).map((item) => item.id));
      setAppliedAdvancedFilter(advancedFilter);
      clearSelectionState();
      setNotice(`Applied advanced filters to ${filteredItemIds.size.toLocaleString()} item(s).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply advanced filters");
    } finally {
      setQueryLoading(false);
    }
  }

  function resetAdvancedFilters() {
    setAdvancedFilterDraft(DEFAULT_ADVANCED_FILTER_DRAFT);
    setAppliedAdvancedFilter(null);
  }

  function toggleSmartPreset(preset: DouyinReviewPresetId) {
    setActivePreset((current) => {
      const nextPreset: DouyinReviewPreset = current === preset ? "none" : preset;
      const config = getDouyinReviewPresetConfig(nextPreset);
      if (config && !sortTouched && sortMode === sortModeBaseline) {
        setSortMode(config.sortHint);
      }
      return nextPreset;
    });
  }

  function clearSmartPreset() {
    setActivePreset("none");
  }

  function updateSortMode(nextSortMode: SortMode) {
    setSortTouched(true);
    setSortMode(nextSortMode);
  }

  function clearOperatorFilters() {
    setOperatorFilter(operatorFilterBaseline);
    setMetadataFilter("all");
    setSearchQuery("");
    setStatusFilter("all");
    setSortMode(sortModeBaseline);
    setSortTouched(false);
    setActivePreset("none");
    setOnlyActionable(false);
    setOnlyWithThumbnail(false);
    setHideDuplicates(false);
    resetAdvancedFilters();
  }

  function toggleReadyFocus() {
    setOperatorFilter((current) => (current === "ready" ? operatorFilterBaseline : "ready"));
  }

  function promoteTopVisible(limit: number) {
    const topItems = selectTopPromotableCaptureItems(visibleItems, limit);
    if (!topItems.length) return;
    void runAction("promote_now", topItems.map((item) => item.id));
  }

  async function runAction(action: CaptureInboxAction, itemIds?: string[], resultSummary?: BulkActionResultSummary) {
    if (!selectedSession) return;
    const actionSessionId = selectedSession.id;
    setWorking(action);
    setError(null);
    setNotice(null);
    setPromoteSuccess(null);
    setRawDetails([]);
    setSourceUrls([]);
    try {
      const targetItemIds = itemIds ?? selectedItemIds;
      const response = await runCaptureInboxAction(actionSessionId, {
        action,
        item_ids: targetItemIds,
        exclude_reason: action === "exclude" ? "Excluded by operator from Capture Inbox" : undefined
      });
      if (action === "promote_now") {
        setPromoteSuccess(buildPromoteSuccessSummary(response));
      } else {
        setNotice(resultSummary ? formatBulkActionResultSummary({ ...resultSummary, affectedCount: response.affected_item_ids.length, backendMessage: response.message }) : response.message);
      }
      setRawDetails(response.raw_details);
      setSourceUrls(response.source_urls);
      if (action === "delete_items") {
        applyDeletedItems(response.affected_item_ids.length ? response.affected_item_ids : targetItemIds);
      }
      if (resultSummary) clearSelectionState();
      await loadSessions(actionSessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to run ${actionLabel(action)}`);
    } finally {
      setWorking(null);
    }
  }

  function toggleItem(itemId: string) {
    setSelectedItemIds((current) => {
      const next = current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId];
      setLastSelectedAt(next.length ? new Date().toISOString() : null);
      return next;
    });
  }

  function openItemDetails(itemId: string) {
    const item = sessionItems.find((entry) => entry.id === itemId) ?? visibleItems.find((entry) => entry.id === itemId);
    if (!item) return;
    setInspectorPinnedItem(item);
    setActiveItemId(itemId);
    setRightInspectorOpen(true);
  }

  function closeItemDetails() {
    setRightInspectorOpen(false);
    setActiveItemId(null);
    setInspectorPinnedItem(null);
  }

  function applyDeletedItems(itemIds: string[]) {
    if (!itemIds.length) return;
    const deleted = new Set(itemIds);
    const currentSessionId = selectedSessionId;
    setSessionItems((current) => current.filter((item) => !deleted.has(item.id)));
    setSessionItemsTotalCount((current) => Math.max(0, current - itemIds.length));
    setSelectedSession((current) => {
      if (!current) return current;
      const remainingItems = current.items.filter((item) => !deleted.has(item.id));
      return patchSessionCounts({
        ...current,
        items: remainingItems
      }, remainingItems);
    });
    setSessions((current) => current.map((session) => {
      if (session.id !== currentSessionId || !selectedSession) return session;
      const remainingItems = sessionItems.filter((item) => !deleted.has(item.id));
      return patchSessionCounts(session, remainingItems);
    }));
    setSelectedItemIds((current) => current.filter((id) => !deleted.has(id)));
    setActiveItemId((current) => {
      const nextActiveItemId = current && deleted.has(current) ? null : current;
      setRightInspectorOpen((open) => open && Boolean(nextActiveItemId));
      return nextActiveItemId;
    });
  }

  async function deleteSession(sessionId: string) {
    const deletingActiveSession = selectedSessionId === sessionId;
    const nextSessionId = sessions.find((session) => session.id !== sessionId)?.id ?? null;
    setWorking("delete_session");
    setError(null);
    setNotice(null);
    setRawDetails([]);
    setSourceUrls([]);
    try {
      await deleteCaptureInboxSession(sessionId);
      const remainingSessions = sortCaptureSessionsNewestFirst(sessions.filter((session) => session.id !== sessionId));
      setSessions(remainingSessions);
      setSessionsTotalCount((current) => Math.max(0, current - 1));
      setSelectedItemIds([]);
      setActiveItemId(null);
      setRightInspectorOpen(false);
      setRawDetails([]);
      setSourceUrls([]);
      setNotice("Deleted session and staged items.");
      if (deletingActiveSession) {
        setSelectedSession(null);
        setSelectedSessionId(nextSessionId);
        if (nextSessionId) {
          const loadScope = resolveItemsLoadScopeForSession(
            profileUrlFromQuery,
            nextSessionId,
            profileMatchedSessionId
          );
          await loadSession(nextSessionId, operatorFilter, loadScope);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete capture session");
    } finally {
      setWorking(null);
    }
  }

  function requestDeleteSession(session: CaptureSession) {
    const confirmed = window.confirm(`Delete session?\n\nThis removes the local staged session and staged items. Promoted Review Board records are not deleted.\n\nSession: ${shortSessionLabel(session)}\nStaged items: ${formatNumber(session.captured_item_count, "0")}`);
    if (confirmed) void deleteSession(session.id);
  }

  function requestDeleteItems(itemIds: string[]) {
    if (!itemIds.length) return;
    void runAction("delete_items", itemIds);
  }

  function clearSelection() {
    clearSelectionState();
  }

  function selectVisibleItems() {
    const nextItemIds = visibleItems.map((item) => item.id);
    setSelectedItemIds(nextItemIds);
    setLastSelectedAt(nextItemIds.length ? new Date().toISOString() : null);
  }

  function requestBulkAction(action: BulkAction) {
    const eligibility = getBulkActionEligibility(visibleItems, selectedItemIds);
    const eligibleItems = bulkEligibleItemsForAction(eligibility, action);
    if (!eligibleItems.length) return;
    setBulkActionDialog({ action, eligibility });
  }

  function closeBulkActionDialog() {
    setBulkActionDialog(null);
  }

  function confirmBulkAction() {
    if (!bulkActionDialog) return;
    const { action, eligibility } = bulkActionDialog;
    const eligibleItems = bulkEligibleItemsForAction(eligibility, action);
    const itemIds = eligibleItems.map((item) => item.id);
    const apiAction: CaptureInboxAction = action === "promote" ? "promote_now" : action === "recheck" ? "re_evaluate_intake" : "delete_items";
    setBulkActionDialog(null);
    void runAction(apiAction, itemIds, {
      action,
      requestedCount: eligibility.selectedItems.length,
      eligibleCount: eligibleItems.length,
      affectedCount: 0,
      skippedCount: eligibility.selectedItems.length - eligibleItems.length,
      backendMessage: ""
    });
  }

  const primaryActions = (
    <>
      <TopbarRefreshButton busy={working === "refresh"} disabled={loading || working !== null} onClick={() => void loadSessions(selectedSessionId)} />
      <button className="app-topbar-btn is-primary" disabled={!selectedSession || working !== null || summary.ready === 0} onClick={() => void runAction("promote_now", readyItems(sessionItems).map((item) => item.id))} type="button">
        {working === "promote_now" ? "Promoting..." : "Promote ready"}
      </button>
    </>
  );

  return (
    <OperatorStudioShell
      actions={primaryActions}
      description="Review captured Douyin items before sending them forward"
      title="Capture Inbox"
    >
        <OpsConsolePage>
          {error ? <section className="operator-panel intake-status danger"><strong>Capture Inbox error:</strong> {error}</section> : null}
          {promoteSuccess ? (
            <section className="operator-panel intake-status good capture-inbox-promote-success capture-inbox-promote-toast">
              <strong>Promoted:</strong> {promoteSuccess.message}
              {promoteSuccessFollowUpLabel(promoteSuccess) ? (
                <p className="capture-inbox-promote-follow-up">
                  <a className="primary" href={CAPTURE_INBOX_REVIEW_BOARD_HREF}>{promoteSuccessFollowUpLabel(promoteSuccess)}</a>
                </p>
              ) : null}
            </section>
          ) : notice ? <section className="operator-panel intake-status good"><strong>Action complete:</strong> {notice}</section> : null}
          <CaptureInboxCommandDeck
            activePreset={activePreset}
            advancedApplied={appliedAdvancedFilter}
            advancedDraft={advancedFilterDraft}
            advancedLoading={queryLoading || working === "refresh"}
            advancedOpen={showAdvancedFilters}
            baselineFilter={operatorFilterBaseline}
            baselineSort={sortModeBaseline}
            filter={operatorFilter}
            hideDuplicates={hideDuplicates}
            itemsLoadScope={itemsLoadScope}
            latestSessionId={latestSessionId}
            loading={loading}
            loadingMoreSessions={loadingMoreSessions}
            metadataFilter={metadataFilter}
            metadataHealthCounts={metadataHealthCountMap}
            onApplyAdvanced={() => void applyAdvancedFilters()}
            onClearFilters={clearOperatorFilters}
            onClearSmartPreset={clearSmartPreset}
            onDeleteSession={requestDeleteSession}
            onFilter={setOperatorFilter}
            onHideDuplicates={setHideDuplicates}
            onLoadMoreSessions={() => void loadMoreSessions()}
            onMetadataFilter={setMetadataFilter}
            onOnlyActionable={setOnlyActionable}
            onOnlyWithThumbnail={setOnlyWithThumbnail}
            onPromoteTop={promoteTopVisible}
            onResetAdvanced={resetAdvancedFilters}
            onSearch={setSearchQuery}
            onSelectSession={(sessionId) => void selectSession(sessionId)}
            onSessionStatus={setStatusFilter}
            onSmartPreset={toggleSmartPreset}
            onSort={updateSortMode}
            onToggleAdvanced={() => setShowAdvancedFilters((value) => !value)}
            onToggleReadyFocus={toggleReadyFocus}
            onUpdateAdvanced={updateAdvancedFilterDraft}
            onlyActionable={onlyActionable}
            onlyWithThumbnail={onlyWithThumbnail}
            presetCounts={presetCountMap}
            profileSummary={profileSummary}
            profileSummaryError={profileSummaryError}
            profileSummaryLoading={profileSummaryLoading}
            profileUrlFromQuery={profileUrlFromQuery}
            searchQuery={searchQuery}
            selectedSessionId={selectedSessionId}
            sessionStatus={statusFilter}
            sessions={sessions}
            sessionsTotalCount={sessionsTotalCount}
            sortMode={sortMode}
            summary={summary}
            visibleCount={visibleItems.length}
            working={working}
          />
          <div className="capture-inbox-review-workspace">
            <main className="capture-inbox-review-main" aria-label="Capture Inbox item gallery">
              <BatchActionBar
                eligibility={bulkActionEligibility}
                lastSelectedAt={lastSelectedAt}
                onAction={requestBulkAction}
                onClear={clearSelection}
                onSelectVisible={selectVisibleItems}
                selectionScope={selectionScope}
                visibleCount={visibleItems.length}
                working={working}
              />
              {baseItems.length === 0 && selectedSession ? (
                <section className="operator-panel" aria-label="Capture Inbox session empty state">
                  <h3>No items in this session yet.</h3>
                  <p>session exists: yes</p>
                  <p>loaded from: {shouldUseProfileItemsScope(profileUrlFromQuery, itemsLoadScope) ? "/douyin-extension/capture-inbox/profile-items" : `/capture-inbox/items?capture_session_id=${selectedSession.id}`}</p>
                  <p>captured count: {selectedSession.captured_item_count}</p>
                  <p>likely reasons: no finalized harvest payload has succeeded yet; backend item creation failed; current filter hides items</p>
                </section>
              ) : null}
              {baseItems.length > 0 && visibleItems.length === 0 ? (
                <section className="operator-panel" aria-label="Capture Inbox filtered-empty state">
                  <p>Items exist but are hidden by filters.</p>
                  <button onClick={clearOperatorFilters} type="button">Clear filters</button>
                </section>
              ) : null}
              <MediaTileGallery
                activeItemId={activeItemId}
                hasMoreItems={hasMoreSessionItems}
                items={visibleItems}
                itemsTotalCount={sessionItemsTotalCount}
                loadingMoreItems={sessionItemsLoadingMore}
                onAction={(item, action) => action === "delete_items" ? requestDeleteItems([item.id]) : void runAction(action, [item.id])}
                onFocusItem={openItemDetails}
                onLoadMore={() => void loadMoreSessionItems()}
                onToggleItem={toggleItem}
                selectedItemIds={selectedItemIds}
                working={working}
              />
            </main>
            <aside className="capture-inbox-review-side" aria-label="Right-side sticky inspector">
              <RightInspector
                detailLoading={inspectorDetailLoading}
                item={activeItem}
                onClose={closeItemDetails}
                open={rightInspectorOpen && Boolean(activeItemId)}
                rawDetails={rawDetails}
                sourceUrls={sourceUrls}
              />
            </aside>
          </div>
          <BulkActionConfirmationDialog dialog={bulkActionDialog} onClose={closeBulkActionDialog} onConfirm={confirmBulkAction} working={working} />
        </OpsConsolePage>
    </OperatorStudioShell>
  );
}

function ProfileSummaryHeader({
  profileUrl,
  summary,
  loading,
  error
}: {
  profileUrl: string;
  summary: CaptureInboxProfileSummaryResponse | null;
  loading: boolean;
  error: string | null;
}) {
  const displayUrl = summary?.normalized_profile_url ?? profileUrl;
  const uniqueCount = summary?.unique_video_count ?? summary?.total_count ?? 0;
  const stagedCount = summary?.total_count ?? 0;
  const stagedMeta =
    !loading && !error && stagedCount > 0
      ? uniqueCount !== stagedCount
        ? `${formatNumber(uniqueCount)} unique · ${formatNumber(stagedCount)} staged`
        : `${formatNumber(stagedCount)} staged`
      : null;
  return (
    <div className="capture-inbox-command-deck-scope capture-inbox-context-strip capture-inbox-scope-context is-inline" aria-label="Profile summary from extension deep link">
      <a
        className="capture-inbox-studio-profile-link"
        href={displayUrl}
        rel="noopener noreferrer"
        target="_blank"
        title={displayUrl}
      >
        {truncateInlineLabel(displayUrl, 44)}
      </a>
      {loading ? <span className="capture-inbox-command-deck-scope-meta">Loading…</span> : null}
      {error ? <span className="capture-inbox-command-deck-scope-meta is-danger">{error}</span> : null}
      {stagedMeta ? <span className="capture-inbox-command-deck-scope-meta">{stagedMeta}</span> : null}
    </div>
  );
}

function CaptureInboxCommandDeck({
  activePreset,
  advancedApplied,
  advancedDraft,
  advancedLoading,
  advancedOpen,
  baselineFilter,
  baselineSort,
  filter,
  hideDuplicates,
  itemsLoadScope,
  latestSessionId,
  loading,
  loadingMoreSessions,
  metadataFilter,
  metadataHealthCounts,
  onApplyAdvanced,
  onClearFilters,
  onClearSmartPreset,
  onDeleteSession,
  onFilter,
  onHideDuplicates,
  onLoadMoreSessions,
  onMetadataFilter,
  onOnlyActionable,
  onOnlyWithThumbnail,
  onPromoteTop,
  onResetAdvanced,
  onSearch,
  onSelectSession,
  onSessionStatus,
  onSmartPreset,
  onSort,
  onToggleAdvanced,
  onToggleReadyFocus,
  onUpdateAdvanced,
  onlyActionable,
  onlyWithThumbnail,
  presetCounts,
  profileSummary,
  profileSummaryError,
  profileSummaryLoading,
  profileUrlFromQuery,
  searchQuery,
  selectedSessionId,
  sessionStatus,
  sessions,
  sessionsTotalCount,
  sortMode,
  summary,
  visibleCount,
  working
}: {
  activePreset: DouyinReviewPreset;
  advancedApplied: AdvancedAppliedFilters | null;
  advancedDraft: AdvancedFilterDraft;
  advancedLoading: boolean;
  advancedOpen: boolean;
  baselineFilter: StudioItemStatusFilter;
  baselineSort: SortMode;
  filter: StudioItemStatusFilter;
  hideDuplicates: boolean;
  itemsLoadScope: CaptureInboxItemsLoadScope;
  latestSessionId: string | null;
  loading: boolean;
  loadingMoreSessions: boolean;
  metadataFilter: MetadataStatusFilter;
  metadataHealthCounts: MetadataHealthCountMap;
  onApplyAdvanced: () => void;
  onClearFilters: () => void;
  onClearSmartPreset: () => void;
  onDeleteSession: (session: CaptureSession) => void;
  onFilter: (filter: StudioItemStatusFilter) => void;
  onHideDuplicates: (enabled: boolean) => void;
  onLoadMoreSessions: () => void;
  onMetadataFilter: (filter: MetadataStatusFilter) => void;
  onOnlyActionable: (enabled: boolean) => void;
  onOnlyWithThumbnail: (enabled: boolean) => void;
  onPromoteTop: (limit: number) => void;
  onResetAdvanced: () => void;
  onSearch: (query: string) => void;
  onSelectSession: (sessionId: string) => void;
  onSessionStatus: (status: "all" | CaptureSessionStatus) => void;
  onSmartPreset: (preset: DouyinReviewPresetId) => void;
  onSort: (sortMode: SortMode) => void;
  onToggleAdvanced: () => void;
  onToggleReadyFocus: () => void;
  onUpdateAdvanced: <K extends keyof AdvancedFilterDraft>(key: K, value: AdvancedFilterDraft[K]) => void;
  onlyActionable: boolean;
  onlyWithThumbnail: boolean;
  presetCounts: Record<DouyinReviewPresetId, number>;
  profileSummary: CaptureInboxProfileSummaryResponse | null;
  profileSummaryError: string | null;
  profileSummaryLoading: boolean;
  profileUrlFromQuery: string | null;
  searchQuery: string;
  selectedSessionId: string | null;
  sessionStatus: "all" | CaptureSessionStatus;
  sessions: CaptureSession[];
  sessionsTotalCount: number;
  sortMode: SortMode;
  summary: CaptureSummary;
  visibleCount: number;
  working: CaptureInboxAction | "delete_session" | "refresh" | null;
}) {
  const readyFocusActive = filter === "ready";

  return (
    <section
      className="capture-inbox-command-deck capture-inbox-studio-deck capture-inbox-hero-panel is-compact"
      aria-label="Capture Inbox studio controls"
      data-capture-inbox-ui-version={CAPTURE_INBOX_UI_VERSION}
    >
      <div className="capture-inbox-command-deck-top capture-inbox-hero-toolbar">
        <div className="capture-inbox-command-deck-title capture-inbox-hero-head-compact capture-inbox-studio-hero-copy">
          <div className="capture-inbox-studio-hero-headline">
            <span className="capture-inbox-command-deck-kicker capture-inbox-hero-kicker">Capture studio</span>
            {profileUrlFromQuery && itemsLoadScope === "profile" ? (
              <ProfileSummaryHeader
                error={profileSummaryError}
                loading={profileSummaryLoading}
                profileUrl={profileUrlFromQuery}
                summary={profileSummary}
              />
            ) : null}
          </div>
          <p className="capture-inbox-command-deck-hint capture-inbox-hero-steps-inline capture-inbox-sr-only">
            Review ready videos → promote top candidates → continue in Review Board
          </p>
        </div>
        <div className="capture-inbox-command-deck-quick capture-inbox-hero-actions">
          <CaptureInboxQuickPathBar onPromoteTop={onPromoteTop} visibleCount={visibleCount} working={working} />
          <button
            aria-pressed={readyFocusActive}
            className={`capture-inbox-hero-btn capture-inbox-hero-btn-ghost${readyFocusActive ? " is-active" : ""}`}
            onClick={onToggleReadyFocus}
            type="button"
          >
            Ready focus
          </button>
        </div>
      </div>

      <StatusStrip activeFilter={filter} className="capture-inbox-command-deck-segments" onFilter={onFilter} summary={summary} />

      <SessionRibbon
        latestSessionId={latestSessionId}
        loading={loading}
        loadingMore={loadingMoreSessions}
        onDelete={onDeleteSession}
        onLoadMore={onLoadMoreSessions}
        onSelect={onSelectSession}
        selectedSessionId={selectedSessionId}
        sessions={sessions}
        sessionsTotalCount={sessionsTotalCount}
        working={working}
      />

      <div className="capture-inbox-filter-deck">
        <StudioFilterToolbar
          baselineFilter={baselineFilter}
          baselineSort={baselineSort}
          filter={filter}
          hideDuplicates={hideDuplicates}
          metadataFilter={metadataFilter}
          onClearFilters={onClearFilters}
          onHideDuplicates={onHideDuplicates}
          onMetadataFilter={onMetadataFilter}
          onOnlyActionable={onOnlyActionable}
          onOnlyWithThumbnail={onOnlyWithThumbnail}
          onSearch={onSearch}
          onSessionStatus={onSessionStatus}
          onSort={onSort}
          onlyActionable={onlyActionable}
          onlyWithThumbnail={onlyWithThumbnail}
          searchQuery={searchQuery}
          sessionStatus={sessionStatus}
          sortMode={sortMode}
        />
        <SmartPresetBar activePreset={activePreset} counts={presetCounts} onClear={onClearSmartPreset} onPreset={onSmartPreset} />
      </div>

      <AdvancedFilterPanel
        applied={advancedApplied}
        draft={advancedDraft}
        loading={advancedLoading}
        metadataHealthCounts={metadataHealthCounts}
        onApply={onApplyAdvanced}
        onReset={onResetAdvanced}
        onToggle={onToggleAdvanced}
        onUpdate={onUpdateAdvanced}
        open={advancedOpen}
      />
    </section>
  );
}

function CaptureInboxQuickPathBar({
  onPromoteTop,
  visibleCount,
  working
}: {
  onPromoteTop: (limit: number) => void;
  visibleCount: number;
  working: CaptureInboxAction | "delete_session" | "refresh" | null;
}) {
  const busy = working !== null;
  const promoting = working === "promote_now";
  return (
    <div className="capture-inbox-hero-actions capture-inbox-quick-path capture-inbox-command-deck-quick" aria-label="Capture Inbox quick path">
      <div className="capture-inbox-promote-group" role="group" aria-label="Promote top candidates">
        {CAPTURE_INBOX_PROMOTE_TOP_BATCHES.map((n, index) => (
          <button
            aria-label={promoting ? "Promoting capture items" : `Promote top ${n}`}
            className={`capture-inbox-promote-seg${index === 1 ? " is-primary" : ""}`}
            disabled={busy || visibleCount === 0}
            key={n}
            onClick={() => onPromoteTop(n)}
            title={`Promote top ${n}`}
            type="button"
          >
            {promoting ? "…" : `Top ${n}`}
          </button>
        ))}
      </div>
      <a className="capture-inbox-hero-btn capture-inbox-hero-btn-secondary" href={CAPTURE_INBOX_REVIEW_BOARD_HREF}>
        Open Review Board
      </a>
    </div>
  );
}

function StatusStrip({
  activeFilter,
  className,
  onFilter,
  summary
}: {
  activeFilter: StudioItemStatusFilter;
  className?: string;
  onFilter: (filter: StudioItemStatusFilter) => void;
  summary: CaptureSummary;
}) {
  return (
    <section
      className={`capture-inbox-status-strip reup-queue-hero-stats capture-inbox-studio-status ${className ?? ""}`.trim()}
      aria-label="Capture Inbox Status Strip"
      role="tablist"
    >
      {SUMMARY_FILTERS.map((entry) => {
        const count = captureInboxSummaryCount(summary, entry.key);
        const isActive = activeFilter === entry.key;
        const tone = captureInboxStatusTone(entry.key, count);
        return (
          <button
            aria-pressed={isActive}
            aria-selected={isActive}
            className={`capture-inbox-status-pill reup-queue-hero-stat is-tone-${tone}${isActive ? " active is-active" : ""}`}
            key={entry.key}
            onClick={() => onFilter(entry.key)}
            role="tab"
            type="button"
          >
            <span>{entry.label}</span>
            <strong>{summaryValue(summary, entry.key)}</strong>
          </button>
        );
      })}
    </section>
  );
}

function CaptureInboxTriageBar({
  activePreset,
  baselineFilter,
  baselineSort,
  filter,
  hideDuplicates,
  onClearFilters,
  onClearSmartPreset,
  onHideDuplicates,
  onOnlyActionable,
  onOnlyWithThumbnail,
  onPromoteTop,
  onSearch,
  onSmartPreset,
  onSort,
  onlyActionable,
  onlyWithThumbnail,
  presetCounts,
  searchQuery,
  sortMode,
  visibleCount,
  working
}: {
  activePreset: DouyinReviewPreset;
  baselineFilter: StudioItemStatusFilter;
  baselineSort: SortMode;
  filter: StudioItemStatusFilter;
  hideDuplicates: boolean;
  onClearFilters: () => void;
  onClearSmartPreset: () => void;
  onHideDuplicates: (enabled: boolean) => void;
  onOnlyActionable: (enabled: boolean) => void;
  onOnlyWithThumbnail: (enabled: boolean) => void;
  onPromoteTop: (limit: number) => void;
  onSearch: (query: string) => void;
  onSmartPreset: (preset: DouyinReviewPresetId) => void;
  onSort: (sortMode: SortMode) => void;
  onlyActionable: boolean;
  onlyWithThumbnail: boolean;
  presetCounts: Record<DouyinReviewPresetId, number>;
  searchQuery: string;
  sortMode: SortMode;
  visibleCount: number;
  working: CaptureInboxAction | "delete_session" | "refresh" | null;
}) {
  const filtersAreClear = filter === baselineFilter && !searchQuery && sortMode === baselineSort && !onlyActionable && !onlyWithThumbnail && !hideDuplicates;

  return (
    <div className="capture-inbox-triage-bar capture-inbox-filter-deck">
      <div className="capture-inbox-triage-toolbar">
        <div className="capture-inbox-triage-search-row">
          <label className="capture-inbox-filter-field capture-inbox-toolbar-search">
            <input
              aria-label="Search capture items"
              className="review-board-deck-input capture-inbox-filter-search"
              onChange={(event) => onSearch(event.target.value)}
              placeholder="Caption, video ID, profile, source URL"
              type="search"
              value={searchQuery}
            />
          </label>
          <label className="capture-inbox-filter-field">
            <select
              aria-label="Sort capture items"
              className="review-board-deck-input capture-inbox-filter-sort"
              onChange={(event) => onSort(event.target.value as SortMode)}
              value={sortMode}
            >
              {SORT_OPTIONS.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
            </select>
          </label>
          <button className="review-board-deck-btn is-ghost capture-inbox-filter-clear" disabled={filtersAreClear} onClick={onClearFilters} type="button">
            Clear filters
          </button>
        </div>
        <div className="capture-inbox-triage-actions-row">
          <div className="capture-inbox-filter-secondary capture-inbox-filter-tuning-panel is-compact capture-inbox-triage-quick">
            <OpsToolbarGroup label="Quick filters">
              <div className="capture-inbox-quick-toggle-rail is-inline" role="group" aria-label="Quick filters">
                <label className={`capture-inbox-quick-toggle${onlyActionable ? " is-active" : ""}`}>
                  <span className="capture-inbox-quick-toggle-label">Only actionable</span>
                  <input checked={onlyActionable} onChange={(event) => onOnlyActionable(event.target.checked)} type="checkbox" />
                </label>
                <label className={`capture-inbox-quick-toggle${onlyWithThumbnail ? " is-active" : ""}`}>
                  <span className="capture-inbox-quick-toggle-label">Only with thumbnail</span>
                  <input checked={onlyWithThumbnail} onChange={(event) => onOnlyWithThumbnail(event.target.checked)} type="checkbox" />
                </label>
                <label className={`capture-inbox-quick-toggle${hideDuplicates ? " is-active" : ""}`}>
                  <span className="capture-inbox-quick-toggle-label">Hide duplicates</span>
                  <input checked={hideDuplicates} onChange={(event) => onHideDuplicates(event.target.checked)} type="checkbox" />
                </label>
              </div>
            </OpsToolbarGroup>
          </div>
          <CaptureInboxQuickPathBar onPromoteTop={onPromoteTop} visibleCount={visibleCount} working={working} />
        </div>
        <SmartPresetBar activePreset={activePreset} counts={presetCounts} onClear={onClearSmartPreset} onPreset={onSmartPreset} />
      </div>
    </div>
  );
}

function StudioFilterToolbar({
  baselineFilter,
  baselineSort,
  filter,
  hideDuplicates,
  metadataFilter,
  onClearFilters,
  onHideDuplicates,
  onMetadataFilter,
  onOnlyActionable,
  onOnlyWithThumbnail,
  onSearch,
  onSessionStatus,
  onSort,
  onlyActionable,
  onlyWithThumbnail,
  searchQuery,
  sessionStatus,
  sortMode
}: {
  baselineFilter: StudioItemStatusFilter;
  baselineSort: SortMode;
  filter: StudioItemStatusFilter;
  hideDuplicates: boolean;
  metadataFilter: MetadataStatusFilter;
  onClearFilters: () => void;
  onHideDuplicates: (enabled: boolean) => void;
  onMetadataFilter: (filter: MetadataStatusFilter) => void;
  onOnlyActionable: (enabled: boolean) => void;
  onOnlyWithThumbnail: (enabled: boolean) => void;
  onSearch: (query: string) => void;
  onSessionStatus: (status: "all" | CaptureSessionStatus) => void;
  onSort: (sortMode: SortMode) => void;
  onlyActionable: boolean;
  onlyWithThumbnail: boolean;
  searchQuery: string;
  sessionStatus: "all" | CaptureSessionStatus;
  sortMode: SortMode;
}) {
  const filtersAreClear = filter === baselineFilter && metadataFilter === "all" && !searchQuery && sortMode === baselineSort && sessionStatus === "all" && !onlyActionable && !onlyWithThumbnail && !hideDuplicates;
  return (
    <div className="capture-inbox-filter-deck-toolbar">
    <OpsFilterBar
      description="Search, filter, sort, and tune the media-first triage gallery."
      title="Studio filters"
    >
      <div className="capture-inbox-filter-primary">
        <label className="capture-inbox-filter-field capture-inbox-toolbar-search">
          <input
            aria-label="Search capture items"
            className="review-board-deck-input capture-inbox-filter-search"
            onChange={(event) => onSearch(event.target.value)}
            placeholder="Caption, video ID, profile, source URL"
            type="search"
            value={searchQuery}
          />
        </label>
        <label className="capture-inbox-filter-field">
          <select
            aria-label="Filter capture sessions"
            className="review-board-deck-input capture-inbox-filter-select"
            onChange={(event) => onSessionStatus(event.target.value as "all" | CaptureSessionStatus)}
            value={sessionStatus}
          >
            <option value="all">All sessions</option>
            {SESSION_STATUS_OPTIONS.filter((option) => option !== "all").map((option) => (
              <option key={option} value={option}>{formatCaptureSessionStatusLabel(option)}</option>
            ))}
          </select>
        </label>
        <label className="capture-inbox-filter-field">
          <select
            aria-label="Sort capture items"
            className="review-board-deck-input capture-inbox-filter-sort"
            onChange={(event) => onSort(event.target.value as SortMode)}
            value={sortMode}
          >
            {SORT_OPTIONS.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}
          </select>
        </label>
        <button className="review-board-deck-btn is-ghost capture-inbox-filter-clear" disabled={filtersAreClear} onClick={onClearFilters} type="button">
          Clear filters
        </button>
      </div>
      <div className="capture-inbox-filter-secondary capture-inbox-filter-tuning-panel is-compact">
        <OpsToolbarGroup label="Metadata status">
          <div className="capture-inbox-filter-chip-rail" role="group" aria-label="Metadata status">
            {METADATA_STATUS_OPTIONS.map((option) => (
              <button
                aria-pressed={metadataFilter === option.key}
                className={`capture-inbox-filter-chip${metadataFilter === option.key ? " is-active" : ""}`}
                key={option.key}
                onClick={() => onMetadataFilter(option.key)}
                title={option.title}
                type="button"
              >
                {option.label}
              </button>
            ))}
          </div>
        </OpsToolbarGroup>
        <OpsToolbarGroup label="Quick filters">
          <div className="capture-inbox-quick-toggle-rail is-inline" role="group" aria-label="Quick filters">
            <label className={`capture-inbox-quick-toggle${onlyActionable ? " is-active" : ""}`}>
              <span className="capture-inbox-quick-toggle-label">Only actionable</span>
              <input checked={onlyActionable} onChange={(event) => onOnlyActionable(event.target.checked)} type="checkbox" />
            </label>
            <label className={`capture-inbox-quick-toggle${onlyWithThumbnail ? " is-active" : ""}`}>
              <span className="capture-inbox-quick-toggle-label">Only with thumbnail</span>
              <input checked={onlyWithThumbnail} onChange={(event) => onOnlyWithThumbnail(event.target.checked)} type="checkbox" />
            </label>
            <label className={`capture-inbox-quick-toggle${hideDuplicates ? " is-active" : ""}`}>
              <span className="capture-inbox-quick-toggle-label">Hide duplicates</span>
              <input checked={hideDuplicates} onChange={(event) => onHideDuplicates(event.target.checked)} type="checkbox" />
            </label>
          </div>
        </OpsToolbarGroup>
      </div>
    </OpsFilterBar>
    </div>
  );
}

function SmartPresetBar({ activePreset, counts, onClear, onPreset }: { activePreset: DouyinReviewPreset; counts: Record<DouyinReviewPresetId, number>; onClear: () => void; onPreset: (preset: DouyinReviewPresetId) => void }) {
  const activeConfig = getDouyinReviewPresetConfig(activePreset);

  return (
    <section className="capture-inbox-filter-presets capture-inbox-smart-presets is-compact" aria-label="Smart presets">
      <span className="capture-inbox-filter-row-label">Smart presets</span>
      <div className="capture-inbox-smart-preset-row">
        {DOUYIN_REVIEW_PRESETS.map((preset) => {
          const selected = activePreset === preset.id;
          return (
            <button
              aria-pressed={selected}
              className={`capture-inbox-filter-chip capture-inbox-smart-preset-chip${selected ? " primary is-active" : ""}`}
              key={preset.id}
              onClick={() => onPreset(preset.id)}
              title={`${preset.description} Sort hint: ${preset.sortHint.replaceAll("_", " ")}.`}
              type="button"
            >
              <span>{preset.shortLabel}</span>
              <b>{counts[preset.id].toLocaleString()}</b>
            </button>
          );
        })}
        {activeConfig ? (
          <>
            <span className="capture-inbox-active-preset-chip">Preset: {activeConfig.label}</span>
            <button className="capture-inbox-smart-preset-clear review-board-deck-btn is-ghost" onClick={onClear} type="button">Clear preset</button>
          </>
        ) : null}
      </div>
    </section>
  );
}

function AdvancedFilterPanel({
  applied,
  draft,
  loading,
  metadataHealthCounts,
  onApply,
  onReset,
  onToggle,
  onUpdate,
  open
}: {
  applied: AdvancedAppliedFilters | null;
  draft: AdvancedFilterDraft;
  loading: boolean;
  metadataHealthCounts: MetadataHealthCountMap;
  onApply: () => void;
  onReset: () => void;
  onToggle: () => void;
  onUpdate: <K extends keyof AdvancedFilterDraft>(key: K, value: AdvancedFilterDraft[K]) => void;
  open: boolean;
}) {
  const summaryItems = advancedFilterSummaryItems(applied);
  const validationMessage = advancedFilterValidationMessage(draft);
  const metadataHealthOptions: Array<{ key: MetadataHealthFilter; label: string; detail: string }> = [
    { key: "complete", label: "Complete", detail: "All key fields" },
    { key: "missing_posted", label: "Missing posted", detail: "No posted date" },
    { key: "missing_thumbnail", label: "Missing thumbnail", detail: "No thumbnail" },
    { key: "missing_duration", label: "Missing duration", detail: "No duration" },
    { key: "missing_views", label: "Missing views", detail: "No estimate" },
    { key: "missing_metrics", label: "Missing metrics", detail: "likes/comments/shares" },
    { key: "actionable", label: "Actionable", detail: "Needs review/fix" }
  ];
  const toggleMetadataHealth = (filter: MetadataHealthFilter) => {
    const nextFilters = draft.metadataHealthFilters.includes(filter)
      ? draft.metadataHealthFilters.filter((item) => item !== filter)
      : [...draft.metadataHealthFilters, filter];
    onUpdate("metadataHealthFilters", nextFilters);
  };

  return (
    <section className={`operator-panel capture-inbox-advanced-panel capture-inbox-advanced-deck is-compact${open ? " is-expanded" : " is-collapsed"}`} aria-label="More filters">
      <div className="capture-inbox-advanced-header">
        <div className="capture-inbox-advanced-header-top">
          <div className="capture-inbox-advanced-heading">
            <h2>Advanced filters</h2>
            <p className="capture-inbox-advanced-subtitle">Filter by posted date, duration, performance, and metadata health.</p>
          </div>
          <div className="capture-inbox-advanced-actions" aria-label="Advanced filter actions">
            <button className="review-board-deck-btn is-primary" disabled={loading || Boolean(validationMessage)} onClick={onApply} type="button">{loading ? "Applying..." : "Apply"}</button>
            <button className="review-board-deck-btn" disabled={loading} onClick={onReset} type="button">Reset</button>
            <button className="review-board-deck-btn is-ghost" onClick={onToggle} type="button">{open ? "Collapse" : "Expand"}</button>
          </div>
        </div>
        <div
          className={`capture-inbox-advanced-summary${summaryItems.length ? " has-active" : " is-empty"}`}
          aria-label="Active filter summary"
        >
          {summaryItems.length ? (
            <>
              <strong>Active filters</strong>
              <div className="capture-inbox-advanced-summary-chips">
                {summaryItems.map((item) => (
                  <span className="capture-inbox-advanced-summary-chip" key={item}>{item}</span>
                ))}
              </div>
            </>
          ) : (
            <span>No advanced filters applied</span>
          )}
        </div>
      </div>
      {validationMessage ? <p className="capture-inbox-advanced-validation" role="alert">{validationMessage}</p> : null}
      {open ? (
        <div className="capture-inbox-advanced-workspace compact-priority">
          <div className="capture-inbox-advanced-workspace-row capture-inbox-advanced-workspace-row-top">
            <section className="capture-inbox-advanced-group capture-inbox-advanced-card compact-group">
              <div className="capture-inbox-advanced-group-heading"><h3>Time</h3></div>
              <div className="capture-inbox-advanced-grid two-up">
                <label className="field"><span>Posted from</span><input className="capture-inbox-advanced-input" type="date" value={draft.postedFrom} onChange={(e) => onUpdate("postedFrom", e.target.value)} /></label>
                <label className="field"><span>Posted to</span><input className="capture-inbox-advanced-input" type="date" value={draft.postedTo} onChange={(e) => onUpdate("postedTo", e.target.value)} /></label>
                <label className="field"><span>Captured from</span><input className="capture-inbox-advanced-input" type="date" value={draft.capturedFrom} onChange={(e) => onUpdate("capturedFrom", e.target.value)} /></label>
                <label className="field"><span>Captured to</span><input className="capture-inbox-advanced-input" type="date" value={draft.capturedTo} onChange={(e) => onUpdate("capturedTo", e.target.value)} /></label>
              </div>
            </section>
            <section className="capture-inbox-advanced-group capture-inbox-advanced-card compact-group">
              <div className="capture-inbox-advanced-group-heading">
                <h3>Duration</h3>
                <p>Numeric input means minutes; mm:ss and hh:mm:ss are also accepted.</p>
              </div>
              <div className="capture-inbox-advanced-pair capture-inbox-advanced-pair-stacked">
                <NumberInput label="Min duration (minutes or mm:ss)" placeholder="e.g. 10 or 10:47" value={draft.minDurationSeconds} onChange={(v) => onUpdate("minDurationSeconds", v)} />
                <NumberInput label="Max duration (minutes or mm:ss)" placeholder="No limit" value={draft.maxDurationSeconds} onChange={(v) => onUpdate("maxDurationSeconds", v)} />
              </div>
            </section>
            <section className="capture-inbox-advanced-group capture-inbox-advanced-card compact-group">
              <div className="capture-inbox-advanced-group-heading">
                <h3>Metadata health</h3>
                <p>Find items that are ready, incomplete, or missing key Douyin fields.</p>
                <p className="capture-inbox-advanced-policy">Missing metadata policy: items lacking time/performance/processing-fit evidence remain visible and can be grouped with metadata health filters.</p>
              </div>
              <div className="capture-inbox-metadata-health-grid">
                {metadataHealthOptions.map((option) => {
                  const selected = draft.metadataHealthFilters.includes(option.key);
                  return (
                    <button
                      aria-pressed={selected}
                      className={`capture-inbox-filter-chip capture-inbox-metadata-health-card ${selected ? "is-active" : ""}`}
                      key={option.key}
                      onClick={() => toggleMetadataHealth(option.key)}
                      title={option.detail}
                      type="button"
                    >
                      <span>{option.label}</span>
                      <b>{metadataHealthCounts[option.key].toLocaleString()}</b>
                    </button>
                  );
                })}
              </div>
            </section>
          </div>
          <section className="capture-inbox-advanced-group capture-inbox-advanced-card compact-group primary-performance">
            <div className="capture-inbox-advanced-group-heading">
              <h3>Performance</h3>
              <p className="capture-inbox-advanced-help">Supports 10K, 1.2M, 3万. Estimated ranges use overlap matching.</p>
            </div>
            <div className="capture-inbox-advanced-grid capture-inbox-performance-grid is-dense">
              <div className="capture-inbox-advanced-pair">
                <NumberInput label="Min estimated views" placeholder="e.g. 10000, 10K, or 3万" value={draft.minEstimatedViews} onChange={(v) => onUpdate("minEstimatedViews", v)} />
                <NumberInput label="Max estimated views" placeholder="No limit" value={draft.maxEstimatedViews} onChange={(v) => onUpdate("maxEstimatedViews", v)} />
              </div>
              <div className="capture-inbox-advanced-pair">
                <NumberInput label="Min likes" placeholder="e.g. 500" value={draft.minLikes} onChange={(v) => onUpdate("minLikes", v)} />
                <NumberInput label="Max likes" placeholder="No limit" value={draft.maxLikes} onChange={(v) => onUpdate("maxLikes", v)} />
              </div>
              <div className="capture-inbox-advanced-pair">
                <NumberInput label="Min comments" placeholder="No limit" value={draft.minComments} onChange={(v) => onUpdate("minComments", v)} />
                <NumberInput label="Max comments" placeholder="No limit" value={draft.maxComments} onChange={(v) => onUpdate("maxComments", v)} />
              </div>
              <div className="capture-inbox-advanced-pair">
                <NumberInput label="Min shares" placeholder="No limit" value={draft.minShares} onChange={(v) => onUpdate("minShares", v)} />
                <NumberInput label="Max shares" placeholder="No limit" value={draft.maxShares} onChange={(v) => onUpdate("maxShares", v)} />
              </div>
              <div className="capture-inbox-advanced-pair">
                <NumberInput label="Min engagement score" placeholder="No limit" value={draft.minEngagementScore} onChange={(v) => onUpdate("minEngagementScore", v)} />
                <NumberInput label="Max engagement score" placeholder="No limit" value={draft.maxEngagementScore} onChange={(v) => onUpdate("maxEngagementScore", v)} />
              </div>
              <div className="capture-inbox-advanced-pair">
                <NumberInput label="Min engagement rate %" placeholder="No limit" value={draft.minEngagementRate} onChange={(v) => onUpdate("minEngagementRate", v)} />
                <NumberInput label="Max engagement rate %" placeholder="No limit" value={draft.maxEngagementRate} onChange={(v) => onUpdate("maxEngagementRate", v)} />
              </div>
            </div>
          </section>
          <p className="capture-inbox-advanced-risk-disclosure"><strong>Risk filters</strong> Not available yet. Unsupported risk, speech, text-density, copyright, and complexity filters are not available yet and are not active filters.</p>
        </div>
      ) : null}
    </section>
  );
}

function NumberInput({ label, onChange, placeholder, value }: { label: string; onChange: (value: string) => void; placeholder?: string; value: string }) {
  return (
    <label className="field capture-inbox-advanced-field">
      <span>{label}</span>
      <input className="capture-inbox-advanced-input" inputMode="numeric" onChange={(event) => onChange(event.target.value)} placeholder={placeholder} type="text" value={value} />
    </label>
  );
}

function AdvancedToggle({ checked, label, onChange }: { checked: boolean; label: string; onChange: (value: boolean) => void }) {
  return (
    <label className={`capture-inbox-advanced-toggle ${checked ? "is-active" : ""}`}>
      <input checked={checked} onChange={(event) => onChange(event.target.checked)} type="checkbox" />
      <span className="capture-inbox-advanced-toggle-copy"><strong>{label}</strong></span>
    </label>
  );
}

function SessionRibbon({
  latestSessionId,
  loading,
  loadingMore,
  onDelete,
  onLoadMore,
  onSelect,
  selectedSessionId,
  sessions,
  sessionsTotalCount,
  working
}: {
  latestSessionId: string | null;
  loading: boolean;
  loadingMore: boolean;
  onDelete: (session: CaptureSession) => void;
  onLoadMore: () => void;
  onSelect: (sessionId: string) => void;
  selectedSessionId: string | null;
  sessions: CaptureSession[];
  sessionsTotalCount: number;
  working: CaptureInboxAction | "delete_session" | "refresh" | null;
}) {
  return (
    <div className="capture-inbox-command-deck-sessions capture-inbox-session-ribbon-shell-wrap" aria-label="Session Ribbon">
      <div className="capture-inbox-command-deck-sessions-head capture-inbox-session-ribbon-heading">
        <span className="capture-inbox-command-deck-sessions-kicker">Sessions</span>
        <span className="capture-inbox-command-deck-sessions-meta">
          {loading
            ? "Loading…"
            : sessionsTotalCount > 0
              ? `${sessions.length.toLocaleString("en-US")} of ${sessionsTotalCount.toLocaleString("en-US")} available`
              : `${sessions.length} available`}
        </span>
      </div>
      <div className={`capture-inbox-session-rail-shell ${sessions.length ? "" : "empty"}`.trim()}>
        <div className="capture-inbox-session-ribbon" aria-label="Session Ribbon">
        {sessions.map((session) => {
          const selected = selectedSessionId === session.id;
          const isDeleting = working === "delete_session" && selected;
          const isLatest = latestSessionId != null && session.id === latestSessionId;
          const profileUrl = resolveSessionProfileUrl(session);
          const sessionLabel = shortSessionLabel(session);
          return (
            <article className={`capture-inbox-session-row ${selected ? "selected is-active" : ""}`} data-session-current={selected ? "true" : "false"} key={session.id}>
              <div className="capture-inbox-session-top">
                <span className="capture-inbox-session-meta">
                  <span className="capture-inbox-session-status-group">
                    {selected ? <span aria-hidden="true" className="capture-inbox-session-current-dot" /> : null}
                    <span className={`status-badge ${sessionStatusTone(session.status)}`} title={session.status}>{formatCaptureSessionStatusLabel(session.status)}</span>
                    {isLatest ? <span className="capture-inbox-session-latest-badge">Latest</span> : null}
                  </span>
                  <span className="capture-inbox-session-time">{formatDateTime(session.created_at)}</span>
                </span>
                <span className="capture-inbox-session-actions" aria-label={`Session actions for ${sessionLabel}`}>
                  <button aria-current={selected ? "true" : undefined} aria-pressed={selected} className="capture-inbox-session-action-btn capture-inbox-session-open" disabled={working !== null} onClick={() => onSelect(session.id)} type="button">
                    Open
                  </button>
                  <button className="capture-inbox-session-action-btn is-danger capture-inbox-session-delete" disabled={working !== null} onClick={() => onDelete(session)} type="button">
                    {isDeleting ? "…" : "Delete"}
                  </button>
                </span>
              </div>
              <div className="capture-inbox-session-body">
                {profileUrl ? (
                  <a
                    className="capture-inbox-session-profile-link capture-inbox-session-title"
                    href={profileUrl}
                    rel="noopener noreferrer"
                    target="_blank"
                    title={profileUrl}
                  >
                    {sessionLabel}
                  </a>
                ) : (
                  <span className="capture-inbox-session-title">{sessionLabel}</span>
                )}
                <button aria-current={selected ? "true" : undefined} aria-pressed={selected} className="capture-inbox-session-main" disabled={working !== null} onClick={() => onSelect(session.id)} type="button">
                  <span className="capture-inbox-session-counts" aria-label="Session item counts">
                    <span className={`capture-inbox-session-summary-chip${selected ? " is-current" : ""}`}>
                      <strong>{formatNumber(session.captured_item_count, "0")}</strong>
                      <span>items</span>
                    </span>
                    <span className="capture-inbox-session-summary-chip is-ready">
                      <strong>{formatNumber(session.ready_item_count, "0")}</strong>
                      <span>ready</span>
                    </span>
                  </span>
                </button>
              </div>
            </article>
          );
        })}
          {!sessions.length ? <OpsEmptyState detail="Capture a Douyin page with the extension to start triaging items here." title="No capture session yet" /> : null}
        </div>
        {sessions.length > 0 || sessionsTotalCount > 0 ? (
          <OffsetLoadMoreFooter
            disabled={working !== null}
            loadedCount={sessions.length}
            loadingMore={loadingMore}
            noun="sessions"
            onLoadMore={onLoadMore}
            pageSize={SESSION_PAGE_SIZE}
            totalCount={sessionsTotalCount}
          />
        ) : null}
      </div>
    </div>
  );
}

function MediaTileGallery({
  activeItemId,
  hasMoreItems,
  items,
  itemsTotalCount,
  loadingMoreItems,
  onAction,
  onFocusItem,
  onLoadMore,
  onToggleItem,
  selectedItemIds,
  working
}: {
  activeItemId: string | null;
  hasMoreItems: boolean;
  items: CapturedItem[];
  itemsTotalCount: number;
  loadingMoreItems: boolean;
  onAction: (item: CapturedItem, action: CaptureInboxAction) => void;
  onFocusItem: (itemId: string) => void;
  onLoadMore: () => void;
  onToggleItem: (itemId: string) => void;
  selectedItemIds: string[];
  working: CaptureInboxAction | "delete_session" | "refresh" | null;
}) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const [columnCount, setColumnCount] = useState(3);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(720);

  useEffect(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return;
    const updateLayout = () => {
      const width = scrollElement.clientWidth;
      const nextColumnCount = Math.max(1, Math.floor((width + 12) / (CAPTURE_INBOX_VIRTUAL_MIN_COLUMN_WIDTH + 12)));
      setColumnCount(nextColumnCount);
      setViewportHeight(scrollElement.clientHeight);
    };
    updateLayout();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(updateLayout) : null;
    observer?.observe(scrollElement);
    return () => observer?.disconnect();
  }, []);

  useEffect(() => {
    const sentinel = loadMoreRef.current;
    const root = scrollRef.current;
    if (!sentinel || !root || !hasMoreItems) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting) && !loadingMoreItems) {
          onLoadMore();
        }
      },
      { root, rootMargin: "240px 0px" }
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMoreItems, items.length, loadingMoreItems, onLoadMore]);

  if (!items.length) return <OpsEmptyState detail="No media tiles match the current studio filters." title="No media tiles match" />;

  const rowCount = Math.ceil(items.length / columnCount);
  const startRow = Math.max(0, Math.floor(scrollTop / CAPTURE_INBOX_VIRTUAL_ROW_HEIGHT) - CAPTURE_INBOX_VIRTUAL_OVERSCAN_ROWS);
  const endRow = Math.min(
    rowCount,
    Math.ceil((scrollTop + viewportHeight) / CAPTURE_INBOX_VIRTUAL_ROW_HEIGHT) + CAPTURE_INBOX_VIRTUAL_OVERSCAN_ROWS
  );
  const startIndex = startRow * columnCount;
  const endIndex = Math.min(items.length, endRow * columnCount);
  const visibleSlice = items.slice(startIndex, endIndex);
  const visibleRows: CapturedItem[][] = [];
  for (let index = 0; index < visibleSlice.length; index += columnCount) {
    visibleRows.push(visibleSlice.slice(index, index + columnCount));
  }

  return (
    <section className="operator-panel capture-inbox-media-gallery" aria-label="Media-first Tile Gallery">
      <div className="capture-inbox-media-gallery-heading">
        <div>
          <p className="eyebrow">Media-first Triage Studio</p>
          <h2>Tile Gallery</h2>
        </div>
        <span>{items.length.toLocaleString()} tile(s) shown · {itemsTotalCount.toLocaleString()} total</span>
      </div>
      <div
        className="capture-inbox-virtual-scroll"
        onScroll={(event) => {
          const element = event.currentTarget;
          setScrollTop(element.scrollTop);
          if (
            hasMoreItems
            && !loadingMoreItems
            && element.scrollTop + element.clientHeight >= element.scrollHeight - CAPTURE_INBOX_VIRTUAL_ROW_HEIGHT
          ) {
            onLoadMore();
          }
        }}
        ref={scrollRef}
      >
        <div className="capture-inbox-virtual-spacer" style={{ height: rowCount * CAPTURE_INBOX_VIRTUAL_ROW_HEIGHT }}>
          <div className="capture-inbox-virtual-window" style={{ transform: `translateY(${startRow * CAPTURE_INBOX_VIRTUAL_ROW_HEIGHT}px)` }}>
            {visibleRows.map((row, rowOffset) => (
              <div
                className="capture-inbox-virtual-row"
                key={`${startRow + rowOffset}-${row[0]?.id ?? "empty"}`}
                style={{ ["--capture-inbox-virtual-columns" as string]: String(columnCount) }}
              >
                {row.map((item) => (
                  <MediaTile
                    focused={activeItemId === item.id}
                    item={item}
                    key={item.id}
                    onAction={onAction}
                    onFocusItem={onFocusItem}
                    onToggleItem={onToggleItem}
                    selected={selectedItemIds.includes(item.id)}
                    working={working}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
        {hasMoreItems ? (
          <div className="capture-inbox-load-more-sentinel" ref={loadMoreRef}>
            {loadingMoreItems ? "Loading more items..." : "Scroll to load more items"}
          </div>
        ) : null}
      </div>
    </section>
  );
}

function MediaTile({ focused, item, onAction, onFocusItem, onToggleItem, selected, working }: { focused: boolean; item: CapturedItem; onAction: (item: CapturedItem, action: CaptureInboxAction) => void; onFocusItem: (itemId: string) => void; onToggleItem: (itemId: string) => void; selected: boolean; working: CaptureInboxAction | "delete_session" | "refresh" | null }) {
  const ready = isReadyItem(item);
  const thumbnailUrl = resolveThumbnailDisplayUrl(item);
  const cardModel = compactCardModelForItem(item);
  const reupScore = getReupScoreForCaptureItem(item);
  const scoreLevel = reupScoreBadgeLevelForCaptureItem(reupScore.reup_score, getDouyinMetadataCompletenessForItem(item));
  const showTileMetrics = shouldShowCaptureInboxTileMetrics(item);

  useEffect(() => {
    logCaptureInboxThumbnailResolution(item, thumbnailUrl);
  }, [item, thumbnailUrl]);

  return (
    <article className={`capture-inbox-media-tile capture-inbox-compact-card ${showTileMetrics ? "" : "is-metrics-collapsed"} ${focused ? "selected" : ""}`}>
      <div className="capture-inbox-media-frame">
        <button className="capture-inbox-media-thumbnail" onClick={() => onFocusItem(item.id)} type="button">
          {thumbnailUrl ? (
            <>
              <span aria-hidden="true" className="capture-inbox-media-thumbnail-backdrop" style={{ backgroundImage: `url(${thumbnailUrl})` }} />
              <img alt="Captured video thumbnail" src={thumbnailUrl} />
            </>
          ) : <span className="capture-inbox-thumbnail-placeholder"><strong>Thumbnail not captured</strong><small>{resolvePreviewStatus(item)}</small></span>}
        </button>
        <div className="capture-inbox-media-overlay capture-inbox-tile-overlay-toolbar" aria-label="Tile overlay controls">
          <div className="capture-inbox-media-overlay-scrim capture-inbox-tile-overlay-scrim" aria-hidden="true" />
          <div className="capture-inbox-tile-overlay-row">
            <div className="capture-inbox-tile-overlay-left">
              <label
                className={`capture-inbox-tile-select-toggle ${selected ? "is-selected" : ""}`}
                title={selected ? "Deselect item" : "Select item"}
              >
                <input
                  aria-label={selected ? "Deselect item" : "Select item"}
                  checked={selected}
                  onChange={() => onToggleItem(item.id)}
                  type="checkbox"
                />
                <span aria-hidden="true" className="capture-inbox-tile-select-visual" />
              </label>
              <span className={`capture-inbox-tile-status-chip is-${itemStatusTone(item.status)} ${ready ? "is-ready" : ""}`}>
                {operatorStatusLabel(item.status)}
              </span>
            </div>
            <span
              className={`capture-inbox-reup-score-badge is-${scoreLevel} ${reupScore.reup_score == null ? "missing" : "ready"}`}
              title={reupScoreDetailText(reupScore)}
            >
              <strong>{formatReupScoreBadgeValue(reupScore.reup_score)}</strong>
              <small>{reupScoreBadgeTier(reupScore.reup_score)}</small>
            </span>
          </div>
        </div>
      </div>
      <div className="capture-inbox-tile-main capture-inbox-compact-main">
        <div className="capture-inbox-tile-primary-row">
          <button className="link-button capture-inbox-tile-title" onClick={() => onFocusItem(item.id)} title={titleForItem(item)} type="button">{titleForItem(item)}</button>
        </div>
        <div className="capture-inbox-tile-quick-meta" aria-label="Compact quick metadata">
          {cardModel.quickMetaChips.map((chip) => (
            <span className="capture-inbox-tile-quick-chip" key={chip.label}>
              <strong>{chip.label}</strong>
              <span>{chip.value}</span>
            </span>
          ))}
        </div>
        {cardModel.metadataGap ? (
          <div className="capture-inbox-tile-gap-note" aria-label="Metadata quality gaps">
            <strong>Missing</strong>
            <span>{cardModel.metadataGap}</span>
          </div>
        ) : null}
        {showTileMetrics ? (
          <div className="capture-inbox-tile-metrics" aria-label="Item metrics">
            {cardModel.metrics.map((metric) => (
              <div className="capture-inbox-tile-metric-cell" key={metric.label} title={metric.title}>
                <span className="capture-inbox-tile-metric-label">{metric.label}</span>
                <strong className="capture-inbox-tile-metric-value">{metric.value}</strong>
              </div>
            ))}
          </div>
        ) : null}
      </div>
      <div className="capture-inbox-tile-footer capture-inbox-compact-actions">
        <CaptureInboxTileActions
          item={item}
          mutating={working !== null}
          onAction={onAction}
          onFocusItem={onFocusItem}
          promotable={isPromotableItem(item)}
          workingAction={working}
        />
      </div>
    </article>
  );
}

function RightInspector({
  detailLoading,
  item,
  onClose,
  open,
  rawDetails,
  sourceUrls
}: {
  detailLoading: boolean;
  item: CapturedItem | null;
  onClose: () => void;
  open: boolean;
  rawDetails: Array<Record<string, unknown>>;
  sourceUrls: string[];
}) {
  const [expandedTextKeys, setExpandedTextKeys] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setExpandedTextKeys({});
  }, [item?.id]);

  function toggleText(key: string) {
    setExpandedTextKeys((current) => ({ ...current, [key]: !current[key] }));
  }

  const detailTextSections = item ? compactDetailTextSections(item) : [];
  const reupScore = item ? getReupScoreForCaptureItem(item) : null;

  return (
    <div className={`capture-inbox-right-inspector ${open ? "open" : "closed"}`} aria-hidden={!open && !item}>
      <div className="drawer-header">
        <div>
          <p className="eyebrow">Right-side sticky inspector</p>
          <h2>Item details</h2>
        </div>
        <button disabled={!item && !open} onClick={onClose} type="button">Close details</button>
      </div>
      <OpsDetailPanel emptyDetail={!item ? "Select an item to inspect details." : undefined} title="Item details">
      {item ? (
        <>
          <div className="capture-inbox-detail-hero compact">
            <div className="capture-inbox-detail-hero-topline">
              <span className={`status-badge ${itemStatusTone(item.status)}`}>{operatorStatusLabel(item.status)}</span>
              <span className="capture-inbox-session-time">{metadataSummary(item)}</span>
            </div>
            <CompactText
              expanded={Boolean(expandedTextKeys.title)}
              label="Title"
              text={titleForItem(item)}
              textKey="title"
              threshold={140}
              onToggle={toggleText}
            />
            <CompactText
              expanded={Boolean(expandedTextKeys.caption)}
              label="Caption"
              placeholder="Caption not captured"
              text={item.caption}
              textKey="caption"
              threshold={180}
              onToggle={toggleText}
            />
          </div>
          <OpsDetailSection title="Overview">
            <OpsMetadataList items={inspectorOverviewItems(item)} />
            {detailLoading ? <p className="capture-inbox-inspector-loading">Loading full item details…</p> : null}
            {detailTextSections.length ? (
              <div className="capture-inbox-compact-text-stack">
                {detailTextSections.map((section) => (
                  <CompactText
                    expanded={Boolean(expandedTextKeys[section.key])}
                    key={section.key}
                    label={section.label}
                    text={section.value}
                    textKey={section.key}
                    threshold={section.threshold}
                    onToggle={toggleText}
                  />
                ))}
              </div>
            ) : null}
          </OpsDetailSection>
          {reupScore ? (
            <OpsDetailSection title="Reup Score">
              <ReupScoreBreakdown score={reupScore} />
            </OpsDetailSection>
          ) : null}
          <OpsDetailSection title="Source / References">
            <OpsMetadataList items={[
              { label: "Video ID", value: item.source_video_external_id ?? "Not captured" },
              { label: "Source", value: item.source_url ? <a href={item.source_url} rel="noreferrer" target="_blank">Open source</a> : "Not captured" },
              { label: "Share", value: item.share_url ? <a href={item.share_url} rel="noreferrer" target="_blank">Open share link</a> : "Not captured" },
              { label: "Thumbnail", value: resolveThumbnailUrl(item) ? <a href={resolveThumbnailDisplayUrl(item) ?? "#"} rel="noreferrer" target="_blank">Open thumbnail</a> : "Not captured" }
            ]} />
          </OpsDetailSection>
          <OpsDetailSection title="Performance & engagement">
            <OpsMetadataList items={inspectorPerformanceItems(item)} />
          </OpsDetailSection>
          <OpsDetailSection title="Metadata quality">
            <OpsMetadataList items={inspectorMetadataQualityItems(item)} />
          </OpsDetailSection>
          <OpsDetailSection title="Outputs / Downstream artifacts">
            <OpsMetadataList items={[
              { label: "Promoted", value: item.promoted_video_candidate_id ?? "Not promoted" },
              { label: "Duplicate", value: item.duplicate_of_item_id ?? item.existing_source_video_id ?? "No" },
              { label: "Preview URL", value: item.preview_url ? <a href={item.preview_url} rel="noreferrer" target="_blank">Open preview</a> : resolvePreviewStatus(item) }
            ]} />
          </OpsDetailSection>
          <OpsDetailSection collapsed title="Diagnostics">
            <OpsMetadataList items={[
              { label: "Error", value: item.error_message ?? item.error_code ?? "None" },
              { label: "Excluded reason", value: item.excluded_reason ?? "Not excluded" }
            ]} />
          </OpsDetailSection>
          <OpsDetailSection collapsed title="Raw details">
            <pre>{JSON.stringify({ enrichment: item.enrichment_json, metadata: item.metadata_json, raw: item.raw_payload_json }, null, 2)}</pre>
          </OpsDetailSection>
        </>
      ) : null}
      {sourceUrls.length ? <OpsDetailSection collapsed title="Action source URLs"><ul>{sourceUrls.map((url) => <li key={url}><a href={url} rel="noreferrer" target="_blank">{url}</a></li>)}</ul></OpsDetailSection> : null}
      {rawDetails.length ? <OpsDetailSection collapsed title="Latest raw action details"><pre>{JSON.stringify(rawDetails, null, 2)}</pre></OpsDetailSection> : null}
      </OpsDetailPanel>
    </div>
  );
}

function ReupScoreBreakdown({ score }: { score: ReturnType<typeof getReupScoreForCaptureItem> }) {
  const bars = buildReupScoreBreakdownBars(score);
  return (
    <div className="capture-inbox-reup-score-breakdown" aria-label="Reup Score breakdown">
      <div className="capture-inbox-reup-score-breakdown-headline">
        <strong>{reupScoreDetailText(score)}</strong>
        <span className={`capture-inbox-reup-score-level is-${score.reup_score_level}`}>{score.reup_score_label}</span>
      </div>
      <div className="capture-inbox-reup-score-bars">
        {bars.map((bar) => {
          const widthPercent = bar.max > 0 ? Math.max(4, Math.round((bar.value / bar.max) * 100)) : 0;
          return (
            <div className="capture-inbox-reup-score-bar-row" key={bar.key}>
              <span className="capture-inbox-reup-score-bar-label">{bar.label}</span>
              <div className="capture-inbox-reup-score-bar-track" aria-hidden="true">
                <span className={`capture-inbox-reup-score-bar-fill is-${bar.tone}`} style={{ width: `${widthPercent}%` }} />
              </div>
              <strong className="capture-inbox-reup-score-bar-value">{bar.tone === "penalty" ? `-${bar.value}` : bar.value}</strong>
            </div>
          );
        })}
      </div>
      {score.reup_score_reasons.length ? (
        <p className="capture-inbox-reup-score-reasons">{score.reup_score_reasons.join(" · ")}</p>
      ) : null}
    </div>
  );
}

function mergeSessionItemDetail(items: CapturedItem[], detail: CapturedItem): CapturedItem[] {
  return items.map((item) => (item.id === detail.id ? { ...item, ...detail } : item));
}

function inspectorOverviewItems(item: CapturedItem): Array<{ label: string; value: string }> {
  return [
    { label: "Next", value: nextActionForItem(item) },
    { label: "Duration", value: resolveDuration(item) },
    { label: "Posted", value: resolvePosted(item) },
    { label: "Views", value: resolveViewCount(item) },
    { label: "Estimated views range", value: estimatedViewsSummary(item) },
    { label: "Estimated from likes", value: estimatedViewsSource(item) },
    { label: "Like-rate assumptions", value: "Low 5% · Base 3% · High 1%" },
    { label: "Likes", value: exactEngagementMetricDisplay(item.like_count, resolveLikeCount(item)) },
    { label: "Comments", value: exactEngagementMetricDisplay(item.comment_count, resolveCommentCount(item)) },
    { label: "Shares", value: exactEngagementMetricDisplay(item.share_count, resolveShareCount(item)) }
  ];
}

function CompactText({ expanded, label, onToggle, placeholder = "Not captured", text, textKey, threshold = 180 }: { expanded: boolean; label: string; onToggle: (key: string) => void; placeholder?: string; text: string | null | undefined; textKey: string; threshold?: number }) {
  const value = text?.trim() || placeholder;
  const canExpand = value.length > threshold;
  return (
    <div className="capture-inbox-compact-text" data-expanded={expanded ? "true" : "false"}>
      <span className="capture-inbox-compact-text-label">{label}</span>
      <p className={expanded || !canExpand ? "" : "clamped"}>{value}</p>
      {canExpand ? <button className="link-button" onClick={() => onToggle(textKey)} type="button">{expanded ? "Show less" : "Show more"}</button> : null}
    </div>
  );
}

function BatchActionBar({ eligibility, lastSelectedAt, onAction, onClear, onSelectVisible, selectionScope, visibleCount, working }: { eligibility: BulkActionEligibility; lastSelectedAt: string | null; onAction: (action: BulkAction) => void; onClear: () => void; onSelectVisible: () => void; selectionScope: "visible_items"; visibleCount: number; working: CaptureInboxAction | "delete_session" | "refresh" | null }) {
  if (!visibleCount) return null;
  const selectedCount = eligibility.selectedItems.length;
  const disabled = working !== null;
  const hasSelection = selectedCount > 0;
  return (
    <section
      className={`capture-inbox-command-bar capture-inbox-bulk-command-bar ${hasSelection ? "is-active" : "is-idle"}`}
      aria-label="Bulk actions"
      data-sticky="true"
      data-selection-scope={selectionScope}
    >
      <div className="capture-inbox-bulk-toolbar">
        <div className="capture-inbox-bulk-selection">
          <span aria-hidden="true" className="capture-inbox-bulk-count-badge">{selectedCount}</span>
          <div className="capture-inbox-command-bar-summary capture-inbox-bulk-selection-copy">
            <strong>{selectedCount} selected</strong>
            <p>{hasSelection ? "Bulk actions apply only to selected items." : "Select visible items or tick cards to enable bulk actions."}</p>
            {lastSelectedAt ? <small>Last selected {formatDateTime(lastSelectedAt)}</small> : null}
          </div>
        </div>
        <div className="capture-inbox-bulk-toolbar-utilities">
          <button className="capture-inbox-bulk-btn" disabled={disabled || visibleCount === 0} onClick={onSelectVisible} title="Select visible applies to the current filtered view." type="button">Select visible</button>
          <button className="capture-inbox-command-bar-clear capture-inbox-bulk-btn" disabled={disabled || selectedCount === 0} onClick={onClear} type="button">Clear selection</button>
        </div>
      </div>
      <div className="capture-inbox-bulk-action-row">
        <button className="primary" disabled={disabled || eligibility.promotableItems.length === 0} onClick={() => onAction("promote")} type="button">Promote</button>
        <button className="capture-inbox-bulk-btn" disabled={disabled || eligibility.recheckableItems.length === 0} onClick={() => onAction("recheck")} type="button">Re-check</button>
        <button className="danger" disabled={disabled || eligibility.deletableItems.length === 0} onClick={() => onAction("delete")} type="button">Delete</button>
      </div>
    </section>
  );
}

function BulkActionConfirmationDialog({ dialog, onClose, onConfirm, working }: { dialog: BulkActionDialog; onClose: () => void; onConfirm: () => void; working: CaptureInboxAction | "delete_session" | "refresh" | null }) {
  useEffect(() => {
    if (!dialog) return;
    document.body.classList.add("capture-inbox-bulk-dialog-open");
    return () => {
      document.body.classList.remove("capture-inbox-bulk-dialog-open");
    };
  }, [dialog]);

  if (!dialog || typeof document === "undefined") return null;
  const eligibleItems = bulkEligibleItemsForAction(dialog.eligibility, dialog.action);
  const blockedItems = bulkBlockedItemsForAction(dialog.eligibility, dialog.action);
  const blockedCount = blockedItems.length;
  const blockedReasons = blockedItems.map((item) => bulkBlockedReasonForAction(item, dialog.action));
  const actionLabelText = bulkActionLabel(dialog.action);
  const destructive = dialog.action === "delete";
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") onClose();
  };
  return createPortal(
    <div
      className="capture-inbox-bulk-dialog-backdrop"
      onClick={onClose}
      onKeyDown={onKeyDown}
      role="presentation"
    >
      <section
        aria-label={`${actionLabelText} selected items`}
        aria-modal="true"
        className="capture-inbox-bulk-dialog"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        tabIndex={-1}
      >
        <p className="eyebrow">Bulk action confirmation</p>
        <h2>{actionLabelText} selected items?</h2>
        <p>{eligibleItems.length} eligible item(s) will be sent. {blockedCount} selected item(s) will be skipped because they are not eligible for this action.</p>
        {destructive ? <p className="capture-inbox-bulk-dialog-danger">This hard-deletes non-promoted staged Capture Inbox rows. Promoted items are skipped and Review Board candidates are not removed.</p> : null}
        {blockedCount ? <p className="capture-inbox-bulk-dialog-muted">Blocked examples: {blockedReasons.slice(0, 3).join("; ")}</p> : null}
        <div className="capture-inbox-bulk-dialog-actions">
          <button className={destructive ? "danger" : "primary"} disabled={working !== null || eligibleItems.length === 0} onClick={onConfirm} type="button">{destructive ? "Delete selected" : actionLabelText}</button>
          <button className="capture-inbox-command-bar-clear" disabled={working !== null} onClick={onClose} type="button">Cancel</button>
        </div>
      </section>
    </div>,
    document.body
  );
}

type CaptureSummary = {
  captured: number;
  ready: number;
  duplicates: number;
  needsEnrichment: number;
  failed: number;
  promoted: number;
  intakeMatched: number;
  intakeNeedsReview: number;
  intakeFailed: number;
};

function buildSummary(session: CaptureSessionDetail | null): CaptureSummary {
  const items = session?.items ?? [];
  return buildSummaryFromItems(items);
}

function buildAuthoritativeSummary(
  session: CaptureSessionDetail | null,
  profileSummary: CaptureInboxProfileSummaryResponse | null,
  profileUrlFromQuery: string | null,
  loadedItems: CapturedItem[],
  itemsLoadScope: CaptureInboxItemsLoadScope
): CaptureSummary {
  const intakeFromLoaded = buildSummaryFromItems(loadedItems);
  if (shouldUseProfileItemsScope(profileUrlFromQuery, itemsLoadScope) && profileSummary) {
    return {
      captured: profileSummary.counts.captured,
      ready: profileSummary.counts.ready,
      duplicates: profileSummary.counts.dup,
      needsEnrichment: profileSummary.counts.needs_action ?? 0,
      failed: profileSummary.counts.fail,
      promoted: session?.promoted_item_count ?? intakeFromLoaded.promoted,
      intakeMatched: intakeFromLoaded.intakeMatched,
      intakeNeedsReview: intakeFromLoaded.intakeNeedsReview,
      intakeFailed: intakeFromLoaded.intakeFailed
    };
  }
  if (session) {
    const needsActionEstimate = Math.max(
      0,
      session.captured_item_count
        - session.ready_item_count
        - session.duplicate_item_count
        - session.failed_item_count
        - session.promoted_item_count
    );
    return {
      captured: session.captured_item_count,
      ready: session.ready_item_count,
      duplicates: session.duplicate_item_count,
      needsEnrichment: needsActionEstimate,
      failed: session.failed_item_count,
      promoted: session.promoted_item_count,
      intakeMatched: intakeFromLoaded.intakeMatched,
      intakeNeedsReview: intakeFromLoaded.intakeNeedsReview,
      intakeFailed: intakeFromLoaded.intakeFailed
    };
  }
  return buildSummaryFromItems([]);
}

function buildSummaryFromItems(items: CapturedItem[]): CaptureSummary {
  return {
    captured: items.length,
    ready: readyItems(items).length,
    duplicates: items.filter((item) => item.status === "DUPLICATE").length,
    needsEnrichment: items.filter((item) => item.status === "RAW" || item.status === "NEEDS_ENRICHMENT" || item.status === "PREVIEW_MISSING").length,
    failed: items.filter((item) => item.status === "FAILED").length,
    promoted: items.filter((item) => item.status === "PROMOTED").length,
    intakeMatched: items.filter((item) => item.matches_intake === true).length,
    intakeNeedsReview: items.filter((item) => item.intake_evaluation_status === "NOT_EVALUATED" || item.intake_evaluation_status === "MISSING_REQUIREMENTS").length,
    intakeFailed: items.filter((item) => item.intake_evaluation_status === "FILTERED_OUT" || item.intake_evaluation_status === "EVALUATION_ERROR" || item.matches_intake === false).length
  };
}

function patchSessionCounts<T extends CaptureSession>(session: T, items: CapturedItem[]): T {
  const summary = buildSummaryFromItems(items);
  const normalizedItemCount = items.filter((item) => item.status === "ENRICHED" || item.status === "READY" || item.status === "PREVIEW_MISSING" || item.status === "PROMOTED").length;
  const skippedItemCount = items.filter((item) => item.status === "EXCLUDED").length;
  const candidateCreatedCount = items.filter((item) => item.promoted_video_candidate_id !== null).length;
  const counts = {
    visible_item_count: summary.captured,
    captured_item_count: summary.captured,
    normalized_item_count: normalizedItemCount,
    duplicate_item_count: summary.duplicates,
    ready_item_count: summary.ready,
    skipped_item_count: skippedItemCount,
    promoted_item_count: summary.promoted,
    candidate_created_count: candidateCreatedCount,
    failed_item_count: summary.failed
  };
  if (hasReconciliation(session)) {
    return {
      ...session,
      ...counts,
      reconciliation: {
        ...session.reconciliation,
        ...counts
      }
    };
  }
  return {
    ...session,
    ...counts
  };
}

function hasReconciliation(session: CaptureSession): session is CaptureSessionDetail {
  return "reconciliation" in session;
}

function captureInboxSummaryCount(summary: CaptureSummary, filter: StudioItemStatusFilter): number {
  return Number(summaryValue(summary, filter)) || 0;
}

function captureInboxStatusTone(filter: StudioItemStatusFilter, count: number): "good" | "warn" | "danger" | "muted" | "neutral" {
  if (count === 0) return "muted";
  if (filter === "failed") return "danger";
  if (filter === "needs_action" || filter === "duplicate") return "warn";
  if (filter === "ready" || filter === "promoted") return "good";
  return "neutral";
}

function summaryValue(summary: CaptureSummary, filter: StudioItemStatusFilter): string {
  if (filter === "ready") return String(summary.ready);
  if (filter === "duplicate") return String(summary.duplicates);
  if (filter === "needs_action") return String(summary.needsEnrichment);
  if (filter === "failed") return String(summary.failed);
  if (filter === "promoted") return String(summary.promoted);
  return String(summary.captured);
}

function recommendedAction(summary: CaptureSummary): string {
  if (summary.ready > 0) return `${summary.ready} ready item(s). Promote them to Review Board.`;
  if (summary.intakeFailed > 0) return `${summary.intakeFailed} item(s) failed intake checks. Re-evaluate intake or keep them staged.`;
  if (summary.failed > 0) return `${summary.failed} failed item(s). Retry or exclude them.`;
  if (summary.needsEnrichment > 0) return `${summary.needsEnrichment} item(s) need enrichment or preview.`;
  if (summary.duplicates > 0) return `${summary.duplicates} duplicate item(s). Exclude them if needed.`;
  if (summary.promoted > 0) return `${summary.promoted} promoted item(s). Continue in Review Board.`;
  return "Capture a Douyin page with the extension, then return here.";
}

function matchesItemStatusFilter(item: CapturedItem, filter: StudioItemStatusFilter): boolean {
  if (filter === "ready") return isReadyItem(item) && item.matches_intake === true;
  if (filter === "duplicate") return item.status === "DUPLICATE";
  if (filter === "needs_action") return isActionableItem(item) && !isReadyItem(item) && item.status !== "PROMOTED" && item.status !== "DUPLICATE";
  if (filter === "failed") return item.status === "FAILED" || item.intake_evaluation_status === "FILTERED_OUT" || item.intake_evaluation_status === "EVALUATION_ERROR" || item.matches_intake === false;
  if (filter === "promoted") return item.status === "PROMOTED";
  return true;
}

function compareItems(left: CapturedItem, right: CapturedItem, sortMode: SortMode): number {
  if (sortMode === "ready_first") return readyPriority(left) - readyPriority(right) || recentlyCapturedFirst(left, right);
  if (sortMode === "newest_posted") return newestPostedFirst(left, right) || recentlyCapturedFirst(left, right);
  if (sortMode === "oldest_posted") return oldestPostedFirst(left, right) || recentlyCapturedFirst(left, right);
  if (sortMode === "highest_views") return numericDescending(resolveSortableViewCount(left), resolveSortableViewCount(right)) || recentlyCapturedFirst(left, right);
  if (sortMode === "highest_likes") return numericDescending(left.like_count, right.like_count) || recentlyCapturedFirst(left, right);
  if (sortMode === "highest_comments") return numericDescending(left.comment_count, right.comment_count) || recentlyCapturedFirst(left, right);
  if (sortMode === "highest_shares") return numericDescending(left.share_count, right.share_count) || recentlyCapturedFirst(left, right);
  if (sortMode === "highest_engagement") return numericDescending(left.engagement_score ?? null, right.engagement_score ?? null) || numericDescending(left.engagement_rate, right.engagement_rate) || recentlyCapturedFirst(left, right);
  if (sortMode === "highest_reup_score") return numericDescending(getReupScoreForCaptureItem(left).reup_score, getReupScoreForCaptureItem(right).reup_score) || numericDescending(left.engagement_score ?? null, right.engagement_score ?? null) || recentlyCapturedFirst(left, right);
  if (sortMode === "lowest_reup_score") return numericAscending(getReupScoreForCaptureItem(left).reup_score, getReupScoreForCaptureItem(right).reup_score) || recentlyCapturedFirst(left, right);
  if (sortMode === "shortest_duration") return numericAscending(left.duration_seconds, right.duration_seconds) || recentlyCapturedFirst(left, right);
  if (sortMode === "longest_duration") return numericDescending(left.duration_seconds, right.duration_seconds) || recentlyCapturedFirst(left, right);
  return recentlyCapturedFirst(left, right);
}

function recentlyCapturedFirst(left: CapturedItem, right: CapturedItem): number {
  return dateValue(right.created_at) - dateValue(left.created_at);
}

function newestPostedFirst(left: CapturedItem, right: CapturedItem): number {
  return numericDescending(postedSortValue(left), postedSortValue(right));
}

function oldestPostedFirst(left: CapturedItem, right: CapturedItem): number {
  return numericAscending(postedSortValue(left), postedSortValue(right));
}

function readyPriority(item: CapturedItem): number {
  if (isReadyItem(item)) return 0;
  if (item.status === "DUPLICATE") return 2;
  if (item.status === "PROMOTED") return 3;
  return 1;
}

function searchableText(item: CapturedItem): string {
  return [
    item.caption,
    item.title,
    item.source_video_external_id,
    item.aweme_id,
    item.source_url,
    item.share_url,
    item.video_url,
    item.profile_url,
    item.profile_name,
    stringMetadata(item.metadata_json, "profile_name"),
    stringMetadata(item.metadata_json, "profile_display_name"),
    stringMetadata(item.raw_payload_json, "video_url"),
    item.status,
    operatorStatusLabel(item.status),
    item.intake_evaluation_status,
    item.matches_intake === true ? "intake_matched" : item.matches_intake === false ? "intake_failed" : "intake_unknown"
  ].filter(Boolean).join(" ").toLowerCase();
}

function matchesMetadataFilter(item: CapturedItem, filter: MetadataStatusFilter): boolean {
  if (filter === "all") return true;
  if (filter === "complete") return hasCompleteMetadata(item);
  if (filter === "missing_posted") return !hasPostedMetadata(item);
  if (filter === "missing_thumbnail") return !hasUsableThumbnail(item);
  if (filter === "missing_duration") return !hasDurationMetadata(item);
  return !hasAnyMetrics(item);
}

function matchesAdvancedAppliedFilters(item: CapturedItem, filters: AdvancedAppliedFilters | null): boolean {
  if (!filters) return true;
  const metadata = getDouyinItemMetadataForFilters(item);
  const comparableViews = metadata.comparableViews;
  logAdvancedViewsFilterDiagnostics(item, filters, comparableViews);
  if (!matchesDateRange(resolvePostedDateForFilter(item), filters.postedFrom, filters.postedTo)) return false;
  if (!matchesDateRange(resolveCapturedDateForFilter(item), filters.capturedFrom, filters.capturedTo)) return false;
  if (!matchesNumberRange(metadata.durationSeconds, filters.minDurationSeconds, filters.maxDurationSeconds)) return false;
  if (!estimatedViewsRangeMatches(comparableViews, filters.minEstimatedViews, filters.maxEstimatedViews)) return false;
  if (!matchesNumberRange(metadata.likeCount, filters.minLikes, filters.maxLikes)) return false;
  if (!matchesNumberRange(metadata.commentCount, filters.minComments, filters.maxComments)) return false;
  if (!matchesNumberRange(metadata.shareCount, filters.minShares, filters.maxShares)) return false;
  if (!matchesNumberRange(metadata.engagementScore, filters.minEngagementScore, filters.maxEngagementScore)) return false;
  if (!matchesNumberRange(metadata.engagementRate, filters.minEngagementRate, filters.maxEngagementRate)) return false;
  if (!metadataHealthMatches(metadata, filters.metadataHealthFilters)) return false;
  return true;
}

function matchesDateRange(value: number | null, from: string | null, to: string | null): boolean {
  if (!from && !to) return true;
  if (value === null) return false;

  const fromValue = from ? dateInputStartValue(from) : null;
  const toValue = to ? dateInputEndValue(to) : null;

  if (fromValue !== null && value < fromValue) return false;
  if (toValue !== null && value > toValue) return false;
  return true;
}

function matchesNumberRange(value: number | null, min: number | null, max: number | null): boolean {
  if (min === null && max === null) return true;
  if (value === null || !Number.isFinite(value)) return false;
  if (min !== null && value < min) return false;
  if (max !== null && value > max) return false;
  return true;
}

function dateInputStartValue(value: string): number | null {
  const parsed = new Date(`${value}T00:00:00`).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function dateInputEndValue(value: string): number | null {
  const parsed = new Date(`${value}T23:59:59.999`).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function resolvePostedDateForFilter(item: CapturedItem): number | null {
  const postedAt = dateValue(item.posted_at);
  if (Number.isFinite(postedAt)) return postedAt;
  return parseDisplayDateForFilter(item.posted_display);
}

function resolveCapturedDateForFilter(item: CapturedItem): number | null {
  const capturedAt = dateValue(item.created_at);
  return Number.isFinite(capturedAt) ? capturedAt : null;
}

function parseDisplayDateForFilter(value: string | null | undefined): number | null {
  if (!value) return null;
  const normalized = value.trim();
  const slashMatch = normalized.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (slashMatch) {
    const [, day, month, year] = slashMatch;
    const parsed = new Date(Number(year), Number(month) - 1, Number(day)).getTime();
    return Number.isFinite(parsed) ? parsed : null;
  }
  const parsed = new Date(normalized).getTime();
  return Number.isFinite(parsed) ? parsed : null;
}

function resolveDurationSecondsForFilter(item: CapturedItem): number | null {
  if (typeof item.duration_seconds === "number" && Number.isFinite(item.duration_seconds)) return item.duration_seconds;
  return parseDurationTextForFilter(item.duration_text);
}

function parseDurationTextForFilter(value: string | null | undefined): number | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.includes(":")) return parseDurationFilterInput(trimmed);

  const secondsMatch = trimmed.match(/^(\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?$/i);
  if (secondsMatch) return Math.round(Number(secondsMatch[1]));

  const minutesMatch = trimmed.match(/^(\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?$/i);
  if (minutesMatch) return Math.round(Number(minutesMatch[1]) * 60);

  return null;
}

function buildAdvancedFilterDebug(items: CapturedItem[], filters: AdvancedAppliedFilters | null, draft: AdvancedFilterDraft) {
  const minInput = parseCompactNumberInput(draft.minEstimatedViews);
  const maxInput = parseCompactNumberInput(draft.maxEstimatedViews);
  const filterActive = Boolean(filters && (filters.minEstimatedViews !== null || filters.maxEstimatedViews !== null));
  const sourceCounts = new Map<string, number>();
  let itemsWithEstimatedViews = 0;
  let itemsMatchingEstimatedViews = 0;

  for (const item of items) {
    const estimatedViews = getEstimatedViewsForItem(item);
    sourceCounts.set(estimatedViews.source, (sourceCounts.get(estimatedViews.source) ?? 0) + 1);
    if (estimatedViews.mid !== null) itemsWithEstimatedViews += 1;
    if (filters && estimatedViewsRangeMatches(estimatedViews, filters.minEstimatedViews, filters.maxEstimatedViews)) itemsMatchingEstimatedViews += 1;
  }

  return {
    estimatedViews: {
      filterActive,
      minInputRaw: draft.minEstimatedViews,
      maxInputRaw: draft.maxEstimatedViews,
      parsedMin: filters?.minEstimatedViews ?? minInput.value,
      parsedMax: filters?.maxEstimatedViews ?? maxInput.value,
      totalItems: items.length,
      itemsWithEstimatedViews,
      itemsMatchingEstimatedViews,
      sampleSources: Array.from(sourceCounts.entries()).map(([source, count]) => ({ source, count })).slice(0, 8)
    }
  };
}

function logAdvancedViewsFilterDiagnostics(item: CapturedItem, filters: AdvancedAppliedFilters, comparableViews: ComparableEstimatedViews): void {
  if (process.env.NODE_ENV === "production") return;
  const viewsFilterActive = filters.minEstimatedViews !== null || filters.maxEstimatedViews !== null;
  const missingViewsActive = filters.metadataHealthFilters.includes("missing_views");
  if (!viewsFilterActive && !missingViewsActive) return;
  const estimatedViews = getEstimatedViewsForItem(item);
  console.debug("capture_inbox_advanced_views_filter", {
    item_id: item.id,
    aweme_id: item.aweme_id,
    views_filter_input_raw: item.estimated_views_text_raw ?? item.estimated_views_display ?? null,
    views_filter_parsed_min: filters.minEstimatedViews,
    views_filter_parsed_max: filters.maxEstimatedViews,
    estimated_views_filter_mode: "range_overlap",
    filter_adapter_used: true,
    views_source_field: comparableViews.source,
    views_source_value: comparableViews.sourceValue ?? null,
    views_comparable_value: comparableViews.value,
    item_estimated_views_min: estimatedViews.min,
    item_estimated_views_max: estimatedViews.max,
    item_estimated_views_mid: estimatedViews.mid,
    item_estimated_views_source: estimatedViews.source,
    item_estimated_views_comparable_source: comparableViews.source
  });
}

function hasMissingAnyMetadata(item: CapturedItem): boolean {
  return !getDouyinMetadataCompletenessForItem(item).hasAllCoreMetadata;
}

function numericDescending(left: number | null | undefined, right: number | null | undefined): number {
  const leftValue = typeof left === "number" && Number.isFinite(left) ? left : null;
  const rightValue = typeof right === "number" && Number.isFinite(right) ? right : null;
  if (leftValue === null && rightValue === null) return 0;
  if (leftValue === null) return 1;
  if (rightValue === null) return -1;
  return rightValue - leftValue;
}

function numericAscending(left: number | null | undefined, right: number | null | undefined): number {
  const leftValue = typeof left === "number" && Number.isFinite(left) ? left : null;
  const rightValue = typeof right === "number" && Number.isFinite(right) ? right : null;
  if (leftValue === null && rightValue === null) return 0;
  if (leftValue === null) return 1;
  if (rightValue === null) return -1;
  return leftValue - rightValue;
}

function dateValue(value: string | null | undefined): number {
  if (!value) return Number.NaN;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function postedSortValue(item: CapturedItem): number | null {
  const value = dateValue(item.posted_at);
  return Number.isFinite(value) ? value : null;
}

function resolveSortableViewCount(item: CapturedItem): number | null {
  return getEstimatedViewsForItem(item).mid;
}

function hasCompleteMetadata(item: CapturedItem): boolean {
  return getDouyinMetadataCompletenessForItem(item).hasAllCoreMetadata;
}

function hasPostedMetadata(item: CapturedItem): boolean {
  if (item.has_posted === true) return true;
  if (item.has_posted === false) return false;
  return Boolean(item.posted_at || item.posted_text || item.posted_display);
}

function hasUsableThumbnail(item: CapturedItem): boolean {
  if (item.has_thumbnail === false) return false;
  return Boolean(resolveThumbnailUrl(item));
}

function hasDurationMetadata(item: CapturedItem): boolean {
  if (item.has_duration === true) return true;
  if (item.has_duration === false) return false;
  return typeof item.duration_seconds === "number" || Boolean(item.duration_text);
}

function hasAnyMetrics(item: CapturedItem): boolean {
  if (item.has_views || item.has_likes || item.has_comments || item.has_shares) return true;
  return resolveSortableViewCount(item) !== null || typeof item.like_count === "number" || typeof item.comment_count === "number" || typeof item.share_count === "number";
}

function readyItems(items: CapturedItem[]): CapturedItem[] {
  return items.filter(isPromotableItem);
}

function isReadyItem(item: CapturedItem): boolean {
  return item.status === "READY" || item.status === "ENRICHED";
}

function isPromotableItem(item: CapturedItem): boolean {
  return isReadyItem(item) || item.status === "PREVIEW_MISSING";
}

function isRetryableItem(item: CapturedItem): boolean {
  return item.status === "RAW" || item.status === "NEEDS_ENRICHMENT" || item.status === "PREVIEW_MISSING" || item.status === "FAILED";
}

function isActionableItem(item: CapturedItem): boolean {
  return isReadyItem(item) || isRetryableItem(item) || item.status === "DUPLICATE" || item.status === "FAILED" || item.intake_evaluation_status === "FILTERED_OUT" || item.intake_evaluation_status === "EVALUATION_ERROR";
}

function getBulkActionEligibility(items: CapturedItem[], selectedIds: string[]): BulkActionEligibility {
  const selected = new Set(selectedIds);
  const selectedItems = items.filter((item) => selected.has(item.id));
  const promotableItems = selectedItems.filter(isPromotableItem);
  const recheckableItems = selectedItems.filter((item) => item.status !== "PROMOTED");
  const deletableItems = selectedItems.filter((item) => item.status !== "PROMOTED");
  const reasonsByItemId: Record<string, string> = {};

  for (const item of selectedItems) {
    const reasons: string[] = [];
    if (!isPromotableItem(item)) reasons.push("not ready to promote");
    if (item.status === "PROMOTED") reasons.push("already promoted");
    if (reasons.length) reasonsByItemId[item.id] = `${titleForItem(item)}: ${reasons.join(", ")}`;
  }

  const blockedItems = selectedItems.filter((item) => Boolean(reasonsByItemId[item.id]));
  return { selectedItems, promotableItems, recheckableItems, deletableItems, blockedItems, reasonsByItemId };
}

function bulkEligibleItemsForAction(eligibility: BulkActionEligibility, action: BulkAction): CapturedItem[] {
  if (action === "promote") return eligibility.promotableItems;
  if (action === "recheck") return eligibility.recheckableItems;
  return eligibility.deletableItems;
}

function bulkBlockedItemsForAction(eligibility: BulkActionEligibility, action: BulkAction): CapturedItem[] {
  const eligibleIds = new Set(bulkEligibleItemsForAction(eligibility, action).map((item) => item.id));
  return eligibility.selectedItems.filter((item) => !eligibleIds.has(item.id));
}

function bulkBlockedReasonForAction(item: CapturedItem, action: BulkAction): string {
  if (action === "promote" && !isPromotableItem(item)) return `${titleForItem(item)}: not ready to promote`;
  if (item.status === "PROMOTED") return `${titleForItem(item)}: already promoted`;
  return `${titleForItem(item)}: not eligible for ${bulkActionLabel(action).toLowerCase()}`;
}

function bulkActionLabel(action: BulkAction): string {
  if (action === "promote") return "Promote";
  if (action === "recheck") return "Re-check";
  return "Delete";
}

function formatBulkActionResultSummary(summary: BulkActionResultSummary): string {
  const actionText = summary.action === "promote" ? "promoted" : summary.action === "recheck" ? "re-checked" : "deleted";
  const affectedCount = summary.action === "promote" ? summary.affectedCount : summary.eligibleCount;
  return `Bulk ${actionText}: ${affectedCount} eligible item(s) sent; ${summary.skippedCount} skipped. ${summary.backendMessage}`;
}

function titleForItem(item: CapturedItem): string {
  return item.caption || item.source_video_external_id || `Captured item ${item.raw_item_index + 1}`;
}

function captionSnippet(item: CapturedItem): string {
  const value = item.caption ?? "Caption not captured";
  return value.length > 120 ? `${value.slice(0, 117)}...` : value;
}

function compactDetailTextSections(item: CapturedItem): Array<{ key: string; label: string; value: string; threshold: number }> {
  return [
    { key: "description", label: "Description", value: detailTextValue(item, "description", "desc", "video_description"), threshold: 220 },
    { key: "transcript", label: "Transcript", value: detailTextValue(item, "transcript", "transcript_text", "speech_text", "ocr_text"), threshold: 260 },
    { key: "notes", label: "Notes", value: detailTextValue(item, "notes", "note", "operator_notes"), threshold: 220 },
    { key: "raw_text", label: "Raw text", value: detailTextValue(item, "raw_text", "text", "body_text", "page_text"), threshold: 260 }
  ].filter((section) => section.value.trim().length > 0);
}

function detailTextValue(item: CapturedItem, ...keys: string[]): string {
  for (const key of keys) {
    const value = stringMetadata(item.metadata_json, key) ?? stringMetadata(item.enrichment_json, key) ?? stringMetadata(item.raw_payload_json, key);
    if (value?.trim()) return value.trim();
  }
  return "";
}

function shortSessionLabel(session: CaptureSession): string {
  const metadata = session.metadata_json;
  const preferred = stringMetadata(metadata, "display_title")
    ?? stringMetadata(metadata, "profile_display_name")
    ?? stringMetadata(metadata, "normalized_profile_identifier")
    ?? stringMetadata(metadata, "profile_sec_uid_or_path")
    ?? session.capture_id
    ?? session.id;
  const value = preferred.trim();
  return value.length > 32 ? `${value.slice(0, 29)}...` : value;
}

function resolveSessionProfileUrl(session: CaptureSession): string | null {
  const candidates = [
    session.submitted_profile_url,
    session.page_url,
    stringMetadata(session.metadata_json, "submitted_profile_url"),
    stringMetadata(session.metadata_json, "profile_url"),
    stringMetadata(session.metadata_json, "page_url")
  ];
  for (const candidate of candidates) {
    const trimmed = candidate?.trim();
    if (!trimmed || !/^https?:\/\//i.test(trimmed)) continue;
    try {
      const url = new URL(trimmed);
      if (url.hostname.includes("douyin.com")) return url.toString();
    } catch {
      continue;
    }
  }
  return null;
}

function truncateInlineLabel(value: string, maxLength = 32): string {
  const trimmed = value.trim();
  if (trimmed.length <= maxLength) return trimmed;
  return `${trimmed.slice(0, Math.max(0, maxLength - 3))}...`;
}

function formatCaptureSessionStatusLabel(status: CaptureSessionStatus): string {
  const labels: Record<CaptureSessionStatus, string> = {
    RECEIVED: "Received",
    ENRICHING: "Enriching",
    READY_FOR_REVIEW: "Ready",
    PARTIALLY_PROMOTED: "Partial",
    PROMOTED: "Promoted",
    FAILED: "Failed"
  };
  return labels[status] ?? status;
}

function shortSource(item: CapturedItem): string {
  if (item.source_video_external_id) return item.source_video_external_id;
  if (!item.source_url) return "Not captured";
  try {
    const url = new URL(item.source_url);
    return `${url.hostname}${url.pathname.slice(0, 36)}`;
  } catch {
    return item.source_url.slice(0, 48);
  }
}

function metadataSummary(item: CapturedItem): string {
  return `${resolveDuration(item)} · ${resolvePosted(item)}`;
}

function sourceLineForItem(item: CapturedItem): string {
  if (item.profile_url) return `Profile ${shortUrl(item.profile_url)}`;
  if (item.source_url) return `Source ${shortUrl(item.source_url)}`;
  return "Source Not captured";
}

function shortIdLine(item: CapturedItem): string {
  const videoId = item.source_video_external_id ?? "Not captured";
  const dedupe = item.dedupe_key ? ` · Dedupe ${item.dedupe_key.slice(0, 18)}` : "";
  return `Video ${videoId}${dedupe}`;
}

function compactCardModelForItem(item: CapturedItem): TileCardModel {
  return {
    metadataGap: formatCaptureInboxTileMetadataGap(item),
    metrics: compactMetricMetaForItem(item),
    quickMetaChips: compactQuickMetaForItem(item)
  };
}

function compactQuickMetaForItem(item: CapturedItem): TileQuickMetaChip[] {
  const values = [
    { label: "Duration", value: resolveDuration(item) },
    { label: "Posted", value: resolvePosted(item) }
  ];
  logTargetedAwemeCheckpoint5Render(item, values, null);
  return values;
}

function compactMetricMetaForItem(item: CapturedItem): TileMetricCell[] {
  const viewMetric = resolveViewMetricForCard(item);
  const values: TileMetricCell[] = [
    viewMetric,
    { label: "Likes", value: exactEngagementMetricDisplay(item.like_count, resolveLikeCount(item)) },
    { label: "Comments", value: exactEngagementMetricDisplay(item.comment_count, resolveCommentCount(item)) },
    { label: "Shares", value: exactEngagementMetricDisplay(item.share_count, resolveShareCount(item)) }
  ];
  logTargetedAwemeCheckpoint5Render(item, null, values);
  return values;
}

function resolveViewMetricForCard(item: CapturedItem): TileMetricCell {
  const trustedViewCount = resolveKnownViewCountValue(item);
  if (trustedViewCount !== null) {
    return { label: "Views", value: compactMetricValueCard(trustedViewCount) };
  }

  const estimatedViews = getEstimatedViewsForItem(item);
  if (estimatedViews.display) {
    return {
      label: "Est. Views",
      value: estimatedViews.display,
      title: estimatedViews.source === "derived_from_likes" ? "Estimated from likes using 1%-5% like-rate range." : "Estimated view range used by filters and sorting."
    };
  }

  return { label: "Views", value: "\u2014" };
}

function compactEstimatedViews(item: CapturedItem): string | null {
  return getEstimatedViewsForItem(item).display;
}

function reupScoreDetailText(score: ReturnType<typeof getReupScoreForCaptureItem>): string {
  return `Score ${formatReupScoreBadgeValue(score.reup_score)} · ${score.reup_score_label}`;
}

function estimatedViewsSummary(item: CapturedItem): string {
  const estimated = getEstimatedViewsForItem(item);
  if (estimated.mid === null) return "—";
  if (estimated.min === null || estimated.max === null || estimated.min === estimated.max) return `${formatMetricValue(estimated.mid)} (base ${formatMetricValue(estimated.mid)})`;
  return `${formatMetricValue(estimated.min)}-${formatMetricValue(estimated.max)} (base ${formatMetricValue(estimated.mid)})`;
}

function estimatedViewsSource(item: CapturedItem): string {
  const estimated = getEstimatedViewsForItem(item);
  if (estimated.source === "derived_from_likes") return "Like count estimation";
  if (estimated.source === "view_count") return "Captured view count fallback";
  if (estimated.source === "normalized") return "Normalized estimated views";
  if (estimated.source === "backend_display") return "Backend estimated views display";
  if (estimated.source === "legacy_display") return "Legacy estimated views display";
  return "—";
}

function logTargetedAwemeCheckpoint5Render(item: CapturedItem, quickValues: Array<{ label: string; value: string }> | null, metricValues: Array<{ label: string; value: string }> | null): void {
  if (typeof console === "undefined" || process.env.NODE_ENV === "production") return;
  const awemeId = item.source_video_external_id ?? item.aweme_id;
  if (!awemeId || !TARGET_DEBUG_AWEME_IDS.has(awemeId)) return;
  console.info("[targeted-aweme-checkpoint5-frontend-render]", {
    aweme_id: awemeId,
    quick_values: quickValues,
    metric_values: metricValues,
    posted_at: item.posted_at,
    posted_text: item.posted_text,
    duration_seconds: item.duration_seconds,
    duration_text: item.duration_text,
    view_count: item.view_count,
    estimated_views: getEstimatedViewsForItem(item),
    like_count: item.like_count,
    comment_count: item.comment_count,
    share_count: item.share_count,
    resolved_posted: resolvePosted(item),
    resolved_duration: resolveDuration(item),
    resolved_view_count: resolveViewCount(item),
    resolved_like_count: resolveLikeCount(item),
    resolved_comment_count: resolveCommentCount(item),
    resolved_share_count: resolveShareCount(item)
  });
}

function compactMetricValueCard(value: number | null | undefined): string {
  if (typeof value !== "number") return "\u2014";
  if (value === 0) return "0";
  return new Intl.NumberFormat("en", {
    maximumFractionDigits: value >= 100 ? 0 : 1,
    notation: "compact"
  }).format(value);
}

function formatMetricValue(value: number | null | undefined): string {
  if (typeof value !== "number") return "—";
  return value.toLocaleString();
}

function compactMetricValue(value: number | null | undefined): string {
  if (typeof value !== "number") return "\u2014";
  return value.toLocaleString();
}

function compactPercentValue(value: number | null | undefined): string {
  if (typeof value !== "number") return "\u2014";
  return `${(value * 100).toFixed(1)}%`;
}

function shortUrl(value: string): string {
  try {
    const url = new URL(value);
    return `${url.hostname}${url.pathname.slice(0, 40)}`;
  } catch {
    return value.slice(0, 56);
  }
}

function stringMetadata(payload: Record<string, unknown> | null | undefined, key: string): string | null {
  const value = payload?.[key];
  return typeof value === "string" && value.trim() ? value : null;
}

function logCaptureInboxThumbnailResolution(item: CapturedItem, thumbnailUrl: string | null): void {
  if (typeof console === "undefined" || process.env.NODE_ENV === "production") return;
  console.debug("capture_inbox_thumbnail_resolved", {
    item_id: item.id,
    source_video_external_id: item.source_video_external_id,
    aweme_id: item.aweme_id,
    thumbnail_source: item.thumbnail_source ?? stringMetadata(item.metadata_json, "thumbnail_source") ?? stringMetadata(item.raw_payload_json, "thumbnail_source"),
    posted_source: item.posted_source ?? stringMetadata(item.metadata_json, "posted_source") ?? stringMetadata(item.raw_payload_json, "posted_source"),
    network_source: stringMetadata(item.metadata_json, "network_source") ?? stringMetadata(item.raw_payload_json, "network_source"),
    has_thumbnail_url: Boolean(item.thumbnail_url),
    has_resolved_thumbnail: Boolean(thumbnailUrl),
    poster_aspect_ratio: item.poster_aspect_ratio,
    preview_status: item.preview_status,
    source_link_status: item.source_link_status,
    media_asset_status: item.media_asset_status,
    thumbnail_candidate_count: Array.isArray(item.raw_payload_json?.url_list) ? item.raw_payload_json.url_list.length : 0,
    raw_has_thumbnail_url: Boolean(item.raw_payload_json?.thumbnail_url),
    raw_has_url_list: Array.isArray(item.raw_payload_json?.url_list) && item.raw_payload_json.url_list.length > 0
  });
}

function operatorStatusLabel(status: CapturedItemStatus): OperatorBadge {
  const labels: Record<CapturedItemStatus, OperatorBadge> = {
    RAW: "Needs action",
    ENRICHED: "Ready",
    READY: "Ready",
    NEEDS_ENRICHMENT: "Needs action",
    PREVIEW_MISSING: "Preview pending",
    DUPLICATE: "Duplicate",
    EXCLUDED: "Excluded",
    PROMOTED: "Promoted",
    FAILED: "Failed"
  };
  return labels[status];
}

function itemStatusTone(status: CapturedItemStatus): "good" | "warn" | "danger" | "muted" {
  if (status === "READY" || status === "ENRICHED" || status === "PROMOTED") return "good";
  if (status === "FAILED") return "danger";
  if (status === "NEEDS_ENRICHMENT" || status === "PREVIEW_MISSING" || status === "DUPLICATE" || status === "RAW") return "warn";
  return "muted";
}

function metadataStatusLabel(status: CapturedItem["metadata_status"]): string {
  const labels: Record<CapturedItem["metadata_status"], string> = {
    complete: "Metadata complete",
    partial: "Metadata partial",
    missing: "Needs metadata",
    pending_hydration: "Needs metadata",
    failed: "Metadata failed"
  };
  return labels[status] ?? "Needs metadata";
}

function metadataStatusTone(status: CapturedItem["metadata_status"]): "good" | "warn" | "danger" | "muted" {
  if (status === "complete") return "good";
  if (status === "failed") return "danger";
  if (status === "partial" || status === "missing" || status === "pending_hydration") return "warn";
  return "muted";
}

function metadataGroupStatusWithReason(status: CapturedItem["time_status"], reason: string | null): string {
  const label = formatSourceLabel(status);
  return reason ? `${label} — ${reason}` : label;
}

function sessionStatusTone(status: CaptureSessionStatus | undefined): "good" | "warn" | "danger" | "muted" {
  if (status === "PROMOTED") return "good";
  if (status === "FAILED") return "danger";
  if (status === "READY_FOR_REVIEW" || status === "PARTIALLY_PROMOTED") return "warn";
  return "muted";
}

function nextActionForItem(item: CapturedItem): string {
  if (isReadyItem(item)) return "Promote to Review Board.";
  if (item.status === "RAW" || item.status === "NEEDS_ENRICHMENT") return "Retry enrich.";
  if (item.status === "PREVIEW_MISSING") return "Retry preview.";
  if (item.status === "DUPLICATE") return "Exclude if not needed.";
  if (item.status === "FAILED") return "Retry enrich or exclude.";
  if (item.status === "PROMOTED") return "Open in Review Board.";
  return "No action needed.";
}

function formatReasons(value: unknown[] | null): string {
  if (!value?.length) return "Not analyzed yet";
  return value.map((item) => String(item)).join(", ");
}

function formatNumber(value: number | undefined, fallback = "Pending"): string {
  return typeof value === "number" ? value.toLocaleString("en-US") : fallback;
}

function formatSourceLabel(value: string | null | undefined): string {
  if (!value) return "Not captured";
  if (value === "dom_zero_sentinel") return "DOM zero sentinel";
  return value.replaceAll("_", " ");
}

function formatTriStateBoolean(value: boolean | null | undefined): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "Unknown";
}

function formatRawEvidenceSummary(value: CapturedItem["raw_evidence_summary"]): string {
  if (!value) return "No evidence summary captured.";
  const tokens: string[] = [];
  if (value.has_network_aweme) tokens.push("network aweme");
  if (value.has_detail_aweme) tokens.push("detail aweme");
  if (value.has_dom_snapshot) tokens.push("dom snapshot");
  return tokens.length ? tokens.join(", ") : "No evidence flags set.";
}

function formatSemanticLevel(value: "low" | "medium" | "high" | null | undefined): string {
  return value ?? "Unknown";
}

function formatDateTime(value: string | null): string {
  if (!value) return "Not captured";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function buildAdvancedFilterPayload(draft: AdvancedFilterDraft): AdvancedAppliedFilters | null {
  const payload: AdvancedAppliedFilters = {
    postedFrom: draft.postedFrom || null,
    postedTo: draft.postedTo || null,
    capturedFrom: draft.capturedFrom || null,
    capturedTo: draft.capturedTo || null,
    minDurationSeconds: parseDurationFilterInput(draft.minDurationSeconds),
    maxDurationSeconds: parseDurationFilterInput(draft.maxDurationSeconds),
    minEstimatedViews: parseCompactNumber(draft.minEstimatedViews),
    maxEstimatedViews: parseCompactNumber(draft.maxEstimatedViews),
    minLikes: parseCompactNumber(draft.minLikes),
    maxLikes: parseCompactNumber(draft.maxLikes),
    minComments: parseCompactNumber(draft.minComments),
    maxComments: parseCompactNumber(draft.maxComments),
    minShares: parseCompactNumber(draft.minShares),
    maxShares: parseCompactNumber(draft.maxShares),
    minEngagementScore: parseCompactNumber(draft.minEngagementScore),
    maxEngagementScore: parseCompactNumber(draft.maxEngagementScore),
    minEngagementRate: parsePercent(draft.minEngagementRate),
    maxEngagementRate: parsePercent(draft.maxEngagementRate),
    metadataHealthFilters: [...draft.metadataHealthFilters]
  };

  const hasAny = Object.values(payload).some((value) => Array.isArray(value) ? value.length > 0 : value !== null);
  return hasAny ? payload : null;
}

function parseDurationFilterInput(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (trimmed.includes(":")) {
    const parts = trimmed.split(":").map((part) => Number(part));
    if (parts.some((part) => !Number.isFinite(part)) || parts.length < 2 || parts.length > 3) return null;
    return parts.reduce((total, part) => total * 60 + part, 0);
  }
  const minutes = Number(trimmed);
  return Number.isFinite(minutes) ? Math.round(minutes * 60) : null;
}

function parsePercent(value: string): number | null {
  const parsed = parseCompactNumber(value);
  if (parsed === null) return null;
  return parsed / 100;
}

function actionLabel(action: CaptureInboxAction): string {
  return {
    retry_enrich: "Retry enrich",
    retry_preview: "Retry preview",
    promote_now: "Promote to Review Board",
    exclude: "Exclude",
    delete_items: "Delete staged items",
    open_source: "Open source",
    view_raw_details: "View raw details",
    re_evaluate_intake: "Re-evaluate intake"
  }[action];
}

