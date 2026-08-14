"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  collectFacebookInsightsOnce,
  discoverFacebookReels,
  enablePublicationMetricTracking,
  fetchAllPlatformAccounts,
  fetchJob,
  fetchPlatformPublications,
  fetchPublicationGrowthSummary,
  fetchPublicationMetricSchedule,
  fetchPublicationMetricSnapshots,
  fetchPublishDraftsByPlatform,
  importDiscoveredFacebookReel,
  linkPublicationDraft,
  pausePublicationMetricTracking,
  preflightFacebookInsights,
  resumePublicationMetricTracking,
} from "../../lib/api";
import { useT } from "../../lib/i18n";
import {
  OPERATOR_LIST_PAGE_SIZE_PRESETS,
  PUBLICATION_DISCOVERY_PAGE_SIZE_STORAGE_KEY,
  readOperatorListPageSize,
  writeOperatorListPageSize,
} from "../../lib/operatorListPageSize";
import type { FacebookReelDiscoveryItem, PublicationGrowthSummary, PublicationMetricSchedule, PublicationMetricSnapshot, PublicationMetricTrackingMonitorItem } from "../../types/publication-library";
import type { ContentClassificationQueueItem } from "../../types/content-intelligence";
import type { Job } from "../../types/jobs";
import type { FacebookInsightsPreflightResponse, PlatformAccount, PlatformPublication, PublishDraft } from "../../types/publish-draft";
import { OperatorStudioShell } from "../app-shell/OperatorStudioShell";
import { TopbarRefreshButton } from "../app-shell/TopbarRefreshButton";
import { PublicationTrackingMonitor } from "./PublicationTrackingMonitor";
import { PublicationClassificationPanel } from "./PublicationClassificationPanel";
import { ContentTaxonomyManager } from "./ContentTaxonomyManager";
import { ContentClassificationQueue } from "./ContentClassificationQueue";
import { AffiliateProductMatchingQueue } from "./AffiliateProductMatchingQueue";
import { AffiliateOpportunityRanking } from "./AffiliateOpportunityRanking";
import { AsyncButton } from "../shared/AsyncButton";
import { OperatorListPagination } from "../shared/OperatorListPagination";
import { WorkItemDetailsDrawer } from "../shared/WorkItemDetailsDrawer";
import { useNotice } from "../shared/NoticeCenter";
import { formatDateTime } from "../ops-console/OpsShared";

function shortText(value: string | null | undefined, length = 120): string {
  const text = String(value || "").trim();
  if (!text) return "—";
  return text.length > length ? `${text.slice(0, length)}…` : text;
}

function metric(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat().format(value);
}

function formatRelativeTime(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback;
  const stamp = new Date(value).getTime();
  if (!Number.isFinite(stamp)) return fallback;
  const deltaSec = Math.round((stamp - Date.now()) / 1000);
  const abs = Math.abs(deltaSec);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (abs < 60) return rtf.format(deltaSec, "second");
  if (abs < 3600) return rtf.format(Math.round(deltaSec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(deltaSec / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(deltaSec / 86400), "day");
  if (abs < 86400 * 365) return rtf.format(Math.round(deltaSec / (86400 * 30)), "month");
  return rtf.format(Math.round(deltaSec / (86400 * 365)), "year");
}

function isIdleMonetizationStatus(status: string | null | undefined): boolean {
  const normalized = String(status || "").trim().toUpperCase();
  return normalized === "NOT_EVALUATED" || normalized === "NOT_PLANNED" || normalized === "";
}

type PublicationLibraryIconKind = "library" | "discover" | "sync" | "link" | "tracking" | "alert" | "search" | "external" | "page" | "pages" | "views" | "rate" | "heart" | "chat" | "share" | "check" | "clear" | "collect" | "pause" | "spark" | "settings";

function PublicationLibraryIcon({ kind }: { kind: PublicationLibraryIconKind }) {
  const paths: Record<PublicationLibraryIconKind, ReactNode> = {
    library: <><path d="M4 5.5h16v14H4z" /><path d="m10 9 5 3-5 3z" /></>,
    discover: <><circle cx="12" cy="12" r="3" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M18.4 5.6l-1.8 1.8M7.4 16.6l-1.8 1.8" /></>,
    sync: <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M6.1 9a7 7 0 0 1 11.8-2L20 9M4 15l2.1 2a7 7 0 0 0 11.8-2" /></>,
    link: <><path d="M10.5 13.5 13.5 10" /><path d="M8.8 16.2 7 18a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 5 0" /><path d="m15.2 7.8 1.8-1.8a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-5 0" /></>,
    tracking: <><path d="M4 18V9M10 18V5M16 18v-7M22 18V3" /><path d="M2 20h22" /></>,
    alert: <><path d="m12 3 10 18H2z" /><path d="M12 9v5M12 17h.01" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 5 5" /></>,
    external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v7H4V6h7" /></>,
    page: <><path d="M7 4h8l4 4v12H7z" /><path d="M15 4v4h4" /><path d="M10 12h6M10 16h4" /></>,
    pages: <><path d="M8 7h9v13H8z" /><path d="M5 4h9v3" /><path d="M5 4v13h3" /></>,
    views: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6z" /><circle cx="12" cy="12" r="2.5" /></>,
    rate: <><path d="M4 16 V10 M9 16 V7 M14 16 V11 M19 16 V5" /></>,
    heart: <><path d="M12 19.5s-7-4.2-7-9a3.8 3.8 0 0 1 7-2 3.8 3.8 0 0 1 7 2c0 4.8-7 9-7 9z" /></>,
    chat: <><path d="M5 6.5h14v9H9l-4 3.2z" /></>,
    share: <><circle cx="18" cy="5.5" r="2.2" /><circle cx="6" cy="12" r="2.2" /><circle cx="18" cy="18.5" r="2.2" /><path d="m8 11 8-4.5M8 13l8 4.5" /></>,
    check: <><circle cx="12" cy="12" r="8.5" /><path d="m8.2 12.2 2.5 2.5 5.2-5.4" /></>,
    clear: <><path d="M7.5 7.5 16.5 16.5M16.5 7.5 7.5 16.5" /></>,
    collect: <><path d="M12 4v10" /><path d="m8 10 4 4 4-4" /><path d="M5 18h14" /></>,
    pause: <><path d="M9 6.5v11M15 6.5v11" /></>,
    spark: <><path d="M12 3.5 13.1 8.8 18.5 10 13.1 11.2 12 16.5 10.9 11.2 5.5 10 10.9 8.8z" /><path d="M18.2 14.8 18.8 17.2 21.2 17.8 18.8 18.4 18.2 20.8 17.6 18.4 15.2 17.8 17.6 17.2z" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M12 4.2v1.8M12 18v1.8M4.2 12h1.8M18 12h1.8M6.2 6.2l1.3 1.3M16.5 16.5l1.3 1.3M17.8 6.2l-1.3 1.3M7.5 16.5l-1.3 1.3" /></>,
  };

  return <svg aria-hidden="true" className="publication-library-icon" fill="none" viewBox="0 0 24 24"><g stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8">{paths[kind]}</g></svg>;
}

function publicationThumbnail(publication: PlatformPublication): string | null {
  const value = publication.metadata_json?.thumbnail_url;
  return typeof value === "string" && value ? value : null;
}

function publicationCaption(publication: PlatformPublication): string | null {
  const value = publication.metadata_json?.external_caption;
  return typeof value === "string" && value ? value : null;
}

/** Peel a trailing hashtag run so the splash lede can show an editorial headline + quieter tags line. */
function splitPublicationCaption(raw: string | null | undefined): { lede: string; tags: string | null } {
  const text = typeof raw === "string" ? raw.trim() : "";
  if (!text) return { lede: "—", tags: null };
  const match = text.match(/^(.*?)(?:\s+)((?:#[\p{L}\p{N}_]+(?:\s+|$))+)$/u);
  if (!match) return { lede: text, tags: null };
  const lede = match[1]?.trim() ?? "";
  const tags = match[2]?.trim() ?? "";
  if (!lede || !tags) return { lede: text, tags: null };
  return { lede, tags };
}

function publicationAccountAvatarUrl(account: PlatformAccount | null): string | null {
  if (!account?.metadata_json) return null;
  for (const key of ["facebook_page_picture_url", "page_picture_url", "avatar_url"]) {
    const value = account.metadata_json[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function publicationAccountAvatarLabel(account: PlatformAccount | null): string {
  const words = String(account?.display_name ?? "Facebook Page").trim().split(/\s+/).filter(Boolean);
  return words.slice(0, 2).map((word) => word[0]?.toUpperCase() ?? "").join("") || "FB";
}

type PublicationScope = "PAGE" | "ALL";
type LibraryView = "PUBLICATIONS" | "TRACKING" | "INTELLIGENCE";
type IntelligenceLane = "CLASSIFICATION" | "TAXONOMY" | "PRODUCT_MATCHING" | "OPPORTUNITIES";
type InspectorTab = "OVERVIEW" | "INSIGHTS" | "TRACKING" | "CLASSIFY";
type ReelImportState = "READY" | "IMPORTING" | "IMPORTED" | "FAILED";
type PublicationListFilter = "ALL" | "UNLINKED" | "TRACKED" | "ATTENTION";
type PublicationWorkspaceMode = "LIBRARY" | "DISCOVERED";
type PageSyncStatus = "PRE_SYNC" | "SYNCING" | "SYNCED" | "HAS_NEW" | "UP_TO_DATE" | "HAS_MORE" | "FAILED";
type DiscoveryView = "PENDING" | "IMPORTED";

function mergeAccountSyncAt(
  current: Record<string, string>,
  publications: PlatformPublication[],
  extras?: Record<string, string>
): Record<string, string> {
  const next = { ...current, ...(extras ?? {}) };
  for (const publication of publications) {
    const id = publication.platform_account_id;
    if (!id) continue;
    const stamp = publication.last_synced_at ?? publication.published_at ?? "1970-01-01T00:00:00.000Z";
    if (!next[id] || new Date(stamp).getTime() > new Date(next[id]).getTime()) {
      next[id] = stamp;
    }
  }
  return next;
}

type LoadOptions = {
  accountId?: string;
  scope?: PublicationScope;
};

export function PublicationLibraryPage({ initialAccountId = "" }: { initialAccountId?: string }) {
  const t = useT();
  const { notify } = useNotice();
  const [accounts, setAccounts] = useState<PlatformAccount[]>([]);
  const [drafts, setDrafts] = useState<PublishDraft[]>([]);
  const [publications, setPublications] = useState<PlatformPublication[]>([]);
  const [total, setTotal] = useState(0);
  const [accountId, setAccountId] = useState("");
  const [publicationScope, setPublicationScope] = useState<PublicationScope>("PAGE");
  const [libraryView, setLibraryView] = useState<LibraryView>("PUBLICATIONS");
  const [intelligenceLane, setIntelligenceLane] = useState<IntelligenceLane>("CLASSIFICATION");
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("OVERVIEW");
  const [workspaceMode, setWorkspaceMode] = useState<PublicationWorkspaceMode>("LIBRARY");
  const [, setSyncSetupOpen] = useState(true);
  const [publicationQuery, setPublicationQuery] = useState("");
  const [publicationFilter, setPublicationFilter] = useState<PublicationListFilter>("ALL");
  const [discovered, setDiscovered] = useState<FacebookReelDiscoveryItem[] | null>(null);
  const [pageSyncStatus, setPageSyncStatus] = useState<PageSyncStatus>("PRE_SYNC");
  const [lastPageSyncAt, setLastPageSyncAt] = useState<string | null>(null);
  const [discoveryView, setDiscoveryView] = useState<DiscoveryView>("PENDING");
  const [selectedDiscoveryReelId, setSelectedDiscoveryReelId] = useState<string | null>(null);
  const [discoveryInspectorOpen, setDiscoveryInspectorOpen] = useState(false);
  const [discoveryPage, setDiscoveryPage] = useState(1);
  const [discoveryPageSize, setDiscoveryPageSize] = useState(() =>
    readOperatorListPageSize(PUBLICATION_DISCOVERY_PAGE_SIZE_STORAGE_KEY, OPERATOR_LIST_PAGE_SIZE_PRESETS, 25)
  );
  const [importErrors, setImportErrors] = useState<Record<string, string>>({});
  const [discoverySelectedIds, setDiscoverySelectedIds] = useState<Set<string>>(() => new Set());
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<PlatformPublication | null>(null);
  const [libraryInspectorOpen, setLibraryInspectorOpen] = useState(false);
  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [growth, setGrowth] = useState<PublicationGrowthSummary | null>(null);
  const [snapshots, setSnapshots] = useState<PublicationMetricSnapshot[]>([]);
  const [metricSchedule, setMetricSchedule] = useState<PublicationMetricSchedule | null>(null);
  const [preflight, setPreflight] = useState<FacebookInsightsPreflightResponse | null>(null);
  const [authorizeNetwork, setAuthorizeNetwork] = useState(false);
  const [authorizeTracking, setAuthorizeTracking] = useState(false);
  const [trackingDurationHours, setTrackingDurationHours] = useState(72);
  const [insightsJob, setInsightsJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootstrapReady, setBootstrapReady] = useState(false);
  const [pageDataReady, setPageDataReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pageMenuOpen, setPageMenuOpen] = useState(false);
  const [accountSyncAtById, setAccountSyncAtById] = useState<Record<string, string>>({});
  const bootstrapReadyRef = useRef(false);
  const loadRequestIdRef = useRef(0);
  const pageMenuRef = useRef<HTMLDivElement>(null);
  const [draftMenuOpen, setDraftMenuOpen] = useState(false);
  const draftMenuRef = useRef<HTMLDivElement>(null);
  const [captionExpanded, setCaptionExpanded] = useState(false);

  async function load(showNotice = false, options: LoadOptions = {}) {
    const requestId = ++loadRequestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const [accountRows, draftRows] = await Promise.all([
        fetchAllPlatformAccounts(),
        fetchPublishDraftsByPlatform("FACEBOOK_REELS"),
      ]);
      const facebookAccounts = accountRows.filter((item) => item.platform === "FACEBOOK_REELS");
      const requestedAccountId = options.accountId ?? accountId ?? initialAccountId;
      const resolvedAccountId = facebookAccounts.some((item) => item.id === requestedAccountId)
        ? requestedAccountId
        : facebookAccounts[0]?.id ?? "";
      const resolvedScope = options.scope ?? publicationScope;
      const publicationPayload = resolvedScope === "PAGE" && !resolvedAccountId
        ? { publications: [], total_count: 0, limit: 100, offset: 0 }
        : await fetchPlatformPublications({
          platformAccountId: resolvedScope === "PAGE" ? resolvedAccountId : undefined,
          limit: 100,
        });
      if (requestId !== loadRequestIdRef.current) return;
      setAccounts(facebookAccounts);
      setDrafts(draftRows);
      setPublications(publicationPayload.publications);
      setAccountSyncAtById((current) => mergeAccountSyncAt(current, publicationPayload.publications));
      setTotal(publicationPayload.total_count);
      setAccountId(resolvedAccountId);
      setPublicationScope(resolvedScope);
      setSelected((current) => current ? publicationPayload.publications.find((item) => item.id === current.id) ?? null : null);
      setSyncSetupOpen(publicationPayload.publications.length === 0);
      if (publicationPayload.publications.length > 0) setPageSyncStatus((current) => current === "PRE_SYNC" ? "SYNCED" : current);
      if (!bootstrapReadyRef.current) {
        bootstrapReadyRef.current = true;
        setBootstrapReady(true);
      }
      setPageDataReady(true);
      if (showNotice) notify({ message: t("publicationLibrary.refreshed"), tone: "success" });
    } catch (err) {
      if (requestId === loadRequestIdRef.current) {
        setError(err instanceof Error ? err.message : t("publicationLibrary.loadError"));
      }
    } finally {
      if (requestId === loadRequestIdRef.current) setLoading(false);
    }
  }

  useEffect(() => {
    void load(false, { accountId: initialAccountId, scope: "PAGE" });
  }, [initialAccountId, t]);

  useEffect(() => {
    if (!pageMenuOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (!pageMenuRef.current?.contains(event.target as Node)) setPageMenuOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setPageMenuOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    const scrollFrame = window.requestAnimationFrame(() => {
      const menuList = pageMenuRef.current?.querySelector<HTMLElement>(".publication-library-page-menu__list");
      const selectedOption = menuList?.querySelector<HTMLElement>('[role="option"][aria-selected="true"]');
      if (!menuList || !selectedOption) return;
      const listRect = menuList.getBoundingClientRect();
      const selectedRect = selectedOption.getBoundingClientRect();
      const edgePadding = 6;
      if (selectedRect.top < listRect.top + edgePadding) {
        menuList.scrollTop -= listRect.top + edgePadding - selectedRect.top;
      } else if (selectedRect.bottom > listRect.bottom - edgePadding) {
        menuList.scrollTop += selectedRect.bottom - (listRect.bottom - edgePadding);
      }
    });
    return () => {
      window.cancelAnimationFrame(scrollFrame);
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [accountSyncAtById, pageMenuOpen]);

  useEffect(() => {
    if (!pageMenuOpen) return;
    let cancelled = false;
    void (async () => {
      try {
        const payload = await fetchPlatformPublications({ limit: 100 });
        if (cancelled) return;
        setAccountSyncAtById((current) => mergeAccountSyncAt(current, payload.publications));
      } catch {
        /* Menu stays usable even if sync roster probe fails. */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pageMenuOpen]);

  useEffect(() => {
    if (!draftMenuOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (!draftMenuRef.current?.contains(event.target as Node)) setDraftMenuOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setDraftMenuOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [draftMenuOpen]);

  const accountById = useMemo(() => new Map(accounts.map((item) => [item.id, item])), [accounts]);
  const syncedAccounts = useMemo(
    () => accounts.filter((account) => Boolean(accountSyncAtById[account.id])),
    [accountSyncAtById, accounts]
  );
  const neverSyncedAccounts = useMemo(
    () => accounts.filter((account) => !accountSyncAtById[account.id]),
    [accountSyncAtById, accounts]
  );
  const activeAccount = accountById.get(accountId) ?? null;
  const activeAccountAvatarUrl = publicationAccountAvatarUrl(activeAccount);
  const activeDraftChoice = useMemo(() => {
    const draftId = selected?.publish_draft_id || selectedDraftId;
    return drafts.find((draft) => draft.id === draftId) ?? null;
  }, [drafts, selected?.publish_draft_id, selectedDraftId]);
  const draftPickerLabel = activeDraftChoice
    ? `${shortText(activeDraftChoice.title || activeDraftChoice.id.slice(0, 8), 48)} · ${activeDraftChoice.status}`
    : t("publicationLibrary.selectDraft");
  const linked = publications.filter((item) => item.publish_draft_id).length;
  const tracked = publications.filter((item) => item.metadata_json?.last_metric_collection_at).length;
  const needsAttention = publications.filter((item) => item.status !== "PUBLISHED").length;
  const unlinkedCount = Math.max(0, total - linked);
  const metricChartMax = Math.max(total, unlinkedCount, tracked, needsAttention, 1);
  const metricLinkedPct = total > 0 ? (linked / total) * 100 : 0;
  const lastLibrarySyncAt = publications.reduce<string | null>((latest, item) => {
    if (!item.last_synced_at) return latest;
    return !latest || new Date(item.last_synced_at).getTime() > new Date(latest).getTime() ? item.last_synced_at : latest;
  }, null);
  const filteredPublications = useMemo(() => {
    const query = publicationQuery.trim().toLowerCase();
    return publications.filter((publication) => {
      const isTracked = Boolean(publication.metadata_json?.last_metric_collection_at);
      const matchesFilter = publicationFilter === "ALL"
        || (publicationFilter === "UNLINKED" && !publication.publish_draft_id)
        || (publicationFilter === "TRACKED" && isTracked)
        || (publicationFilter === "ATTENTION" && publication.status !== "PUBLISHED");
      if (!matchesFilter) return false;
      if (!query) return true;
      const accountName = accountById.get(publication.platform_account_id)?.display_name ?? "";
      return [publicationCaption(publication), publication.external_reel_id, publication.external_publish_id, accountName]
        .some((value) => String(value ?? "").toLowerCase().includes(query));
    });
  }, [accountById, publicationFilter, publicationQuery, publications]);
  const discoveredNeedsImport = useMemo(() => discovered?.filter((item) => !item.already_imported) ?? [], [discovered]);
  const discoveredImported = useMemo(() => discovered?.filter((item) => item.already_imported) ?? [], [discovered]);
  const discoveredVisible = discoveryView === "PENDING" ? discoveredNeedsImport : discoveredImported;
  const discoveryTotalPages = Math.max(1, Math.ceil(discoveredVisible.length / discoveryPageSize));
  const discoverySafePage = Math.min(discoveryPage, discoveryTotalPages);
  const discoveredPaged = useMemo(() => {
    const start = (discoverySafePage - 1) * discoveryPageSize;
    return discoveredVisible.slice(start, start + discoveryPageSize);
  }, [discoveredVisible, discoveryPageSize, discoverySafePage]);
  const selectedDiscovery = useMemo(
    () => discoveredVisible.find((item) => item.reel_id === selectedDiscoveryReelId) ?? discoveredVisible[0] ?? null,
    [discoveredVisible, selectedDiscoveryReelId],
  );
  const discoveryBulkSelectedCount = useMemo(
    () => discoveredNeedsImport.filter((item) => discoverySelectedIds.has(item.reel_id)).length,
    [discoveredNeedsImport, discoverySelectedIds],
  );
  function toggleDiscoverySelected(reelId: string) {
    setDiscoverySelectedIds((current) => {
      const next = new Set(current);
      if (next.has(reelId)) next.delete(reelId);
      else next.add(reelId);
      return next;
    });
  }

  function selectDiscoveryPage() {
    setDiscoverySelectedIds((current) => {
      const next = new Set(current);
      for (const item of discoveredPaged) {
        if (!item.already_imported) next.add(item.reel_id);
      }
      return next;
    });
  }

  function clearDiscoverySelection() {
    setDiscoverySelectedIds(new Set());
  }

    const failedImportCount = Object.keys(importErrors).length;
  const effectivePageSyncStatus: PageSyncStatus = pageSyncStatus === "PRE_SYNC" && lastLibrarySyncAt ? "SYNCED" : pageSyncStatus;
  const pageSyncLabel = t(`publicationLibrary.pageSyncStatus.${effectivePageSyncStatus}`);
  const pageSyncTimestamp = lastPageSyncAt ?? lastLibrarySyncAt;
  const failedPreflightChecks = preflight?.checks.filter((check) => !check.passed) ?? [];
  const insightsJobActive = insightsJob != null && ["QUEUED", "RUNNING", "RETRYABLE"].includes(insightsJob.status);
  const insightsQueueDelayed = insightsJob?.status === "QUEUED"
    && Date.now() - new Date(insightsJob.created_at).getTime() >= 30_000;
  const trackingStatus = metricSchedule?.status ?? "OFF";
  const trackingDecisionReason = typeof metricSchedule?.last_decision_json?.reason === "string"
    ? metricSchedule.last_decision_json.reason.replaceAll("_", " ").replaceAll(":", " · ")
    : null;
  const libraryTitle = publicationScope === "ALL"
    ? t("publicationLibrary.library")
    : t("publicationLibrary.pageLibrary").replace("{page}", activeAccount?.display_name ?? t("publicationLibrary.selectPage"));
  const libraryHint = publicationScope === "ALL"
    ? t("publicationLibrary.libraryHint")
    : t("publicationLibrary.pageLibraryHint");

  async function changeAccount(nextAccountId: string) {
    setPageDataReady(false);
    setAccountId(nextAccountId);
    setPublicationScope("PAGE");
    setWorkspaceMode("LIBRARY");
    setLibraryInspectorOpen(false);
    setDiscovered(null);
    setPageSyncStatus("PRE_SYNC");
    setLastPageSyncAt(null);
    setDiscoveryView("PENDING");
    setDiscoveryPage(1);
    setSelectedDiscoveryReelId(null);
    setDiscoverySelectedIds(new Set());
    setImportErrors({});
    setNextCursor(null);
    setSelected(null);
    await load(false, { accountId: nextAccountId, scope: "PAGE" });
  }

  async function changePublicationScope(nextScope: PublicationScope) {
    if (nextScope === publicationScope || (nextScope === "PAGE" && !accountId)) return;
    setPageDataReady(false);
    setPublicationScope(nextScope);
    setWorkspaceMode("LIBRARY");
    setLibraryInspectorOpen(false);
    setSelected(null);
    await load(false, { accountId, scope: nextScope });
  }

  async function syncReels(after?: string | null) {
    if (!accountId || loading || !pageDataReady) return;
    setLibraryInspectorOpen(false);
    setBusy(after ? "load-more" : "sync");
    if (!after) setPageSyncStatus("SYNCING");
    setError(null);
    if (!after) setImportErrors({});
    try {
      const payload = await discoverFacebookReels(accountId, after);
      setDiscovered((current) => after && current ? [...current, ...payload.items] : payload.items);
      setNextCursor(payload.next_cursor);
      const syncedAt = new Date().toISOString();
      setLastPageSyncAt(syncedAt);
      setAccountSyncAtById((current) => ({ ...current, [accountId]: syncedAt }));
      const pendingCount = payload.items.filter((item) => !item.already_imported).length;
      setPageSyncStatus(payload.next_cursor ? "HAS_MORE" : pendingCount > 0 ? "HAS_NEW" : "UP_TO_DATE");
      setDiscoveryView(pendingCount > 0 ? "PENDING" : "IMPORTED");
      setWorkspaceMode("DISCOVERED");
      setSyncSetupOpen(false);
      setDiscoveryInspectorOpen(false);
      if (!after) setDiscoveryPage(1);
      const firstId = (after ? undefined : payload.items.find((item) => !item.already_imported)?.reel_id)
        ?? payload.items[0]?.reel_id
        ?? null;
      if (!after && firstId) setSelectedDiscoveryReelId(firstId);
      notify({ message: t("publicationLibrary.syncComplete").replace("{count}", String(payload.items.length)), tone: "success" });
    } catch (err) {
      if (!after) setPageSyncStatus("FAILED");
      setError(err instanceof Error ? err.message : t("publicationLibrary.syncError"));
    } finally {
      setBusy(null);
    }
  }

  async function importReel(item: FacebookReelDiscoveryItem, options: { quiet?: boolean } = {}): Promise<"ok" | "already" | "failed"> {
    setBusy(`import-${item.reel_id}`);
    setError(null);
    setImportErrors((current) => {
      const next = { ...current };
      delete next[item.reel_id];
      return next;
    });
    try {
      const publication = await importDiscoveredFacebookReel({
        platform_account_id: accountId,
        reel_id: item.reel_id,
        description: item.description,
        created_time: item.created_time,
        permalink_url: item.permalink_url,
        thumbnail_url: item.thumbnail_url,
      });
      setDiscovered((current) => current?.map((row) => row.reel_id === item.reel_id ? { ...row, already_imported: true, platform_publication_id: publication.id } : row) ?? null);
      if (!options.quiet) {
        await load();
        setSelected(publication);
        notify({ message: t("publicationLibrary.imported"), tone: "success" });
      }
      return "ok";
    } catch (err) {
      const message = err instanceof Error ? err.message : t("publicationLibrary.importError");
      if (/already imported/i.test(message)) {
        setDiscovered((current) => current?.map((row) => row.reel_id === item.reel_id ? { ...row, already_imported: true } : row) ?? null);
        if (!options.quiet) {
          await load(false, { accountId, scope: publicationScope });
          notify({ message: t("publicationLibrary.alreadyImported"), tone: "info" });
        }
        return "already";
      }
      setImportErrors((current) => ({ ...current, [item.reel_id]: message }));
      if (!options.quiet) setError(message);
      return "failed";
    } finally {
      if (!options.quiet) setBusy(null);
    }
  }

  async function importSelectedDiscoveries() {
    const queue = discoveredNeedsImport.filter((item) => discoverySelectedIds.has(item.reel_id));
    if (queue.length === 0) {
      notify({ message: t("publicationLibrary.bulkImportEmpty"), tone: "info" });
      return;
    }
    setBusy("bulk-import");
    setError(null);
    let ok = 0;
    let failed = 0;
    const remaining = new Set(discoverySelectedIds);
    try {
      for (const item of queue) {
        const result = await importReel(item, { quiet: true });
        if (result === "failed") failed += 1;
        else {
          ok += 1;
          remaining.delete(item.reel_id);
        }
      }
      await load(false, { accountId, scope: publicationScope });
      setDiscoverySelectedIds(remaining);
      if (failed > 0) {
        notify({
          message: t("publicationLibrary.bulkImportPartial")
            .replace("{ok}", String(ok))
            .replace("{total}", String(queue.length))
            .replace("{failed}", String(failed)),
          tone: "warning",
        });
      } else {
        notify({
          message: t("publicationLibrary.bulkImportSummary")
            .replace("{ok}", String(ok))
            .replace("{total}", String(queue.length)),
          tone: "success",
        });
      }
    } finally {
      setBusy(null);
    }
  }

  async function openPublication(publication: PlatformPublication, nextInspectorTab: InspectorTab = "OVERVIEW") {
    setSelected(publication);
    setLibraryInspectorOpen(true);
    setInspectorTab(nextInspectorTab);
    setSelectedDraftId(publication.publish_draft_id ?? "");
    setDraftMenuOpen(false);
    setCaptionExpanded(false);
    setGrowth(null);
    setSnapshots([]);
    setMetricSchedule(null);
    setPreflight(null);
    setAuthorizeNetwork(false);
    setInsightsJob(null);
    setBusy(`inspect-${publication.id}`);
    try {
      const [growthPayload, snapshotPayload, schedulePayload] = await Promise.all([
        fetchPublicationGrowthSummary(publication.id),
        fetchPublicationMetricSnapshots(publication.id),
        fetchPublicationMetricSchedule(publication.id),
      ]);
      setGrowth(growthPayload);
      setSnapshots(snapshotPayload.snapshots);
      setMetricSchedule(schedulePayload);
    } catch {
      // A publication with no snapshots is still valid and inspectable.
    } finally {
      setBusy(null);
    }
  }

  async function copyReelId(reelId: string | null | undefined) {
    if (!reelId) return;
    try {
      await navigator.clipboard.writeText(reelId);
      notify({ message: t("publicationLibrary.reelIdCopied"), tone: "success" });
    } catch {
      notify({ message: t("publicationLibrary.reelIdCopyFailed"), tone: "warning" });
    }
  }

  async function linkDraft() {
    if (!selected || !selectedDraftId) return;
    setBusy("link-draft");
    try {
      const publication = await linkPublicationDraft(selected.id, selectedDraftId);
      setSelected(publication);
      await load();
      notify({ message: t("publicationLibrary.linkSuccess"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.linkError"));
    } finally {
      setBusy(null);
    }
  }

  async function runPreflight() {
    if (!selected) return;
    const account = accountById.get(selected.platform_account_id);
    const mediaId = selected.external_reel_id || selected.external_media_id || selected.external_publish_id;
    if (!account || !mediaId) return;
    setBusy("preflight");
    try {
      const result = await preflightFacebookInsights(selected.id, {
        operator_confirmation: "FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED",
        expected_platform_account_id: account.id,
        expected_external_account_id: account.external_account_id,
        expected_media_id: mediaId,
        required_scopes: ["read_insights", "pages_read_engagement"],
      });
      setPreflight(result);
      if (!result.ready_for_live_job) {
        setAuthorizeTracking(false);
        setAuthorizeNetwork(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.preflightError"));
    } finally {
      setBusy(null);
    }
  }

  async function collectInsights() {
    if (!selected || !preflight?.ready_for_live_job || !authorizeNetwork || insightsJobActive) return;
    setError(null);
    setInsightsJob(null);
    setBusy("collect");
    try {
      const job = await collectFacebookInsightsOnce(selected.id);
      setInsightsJob(job);
      notify({ message: t("publicationLibrary.collectionQueued").replace("{id}", job.id.slice(0, 8)), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.collectionError"));
      setBusy(null);
    }
  }

  async function enableTracking() {
    if (!selected || !preflight?.ready_for_live_job || !authorizeTracking) return;
    setBusy("tracking-enable");
    setError(null);
    try {
      const schedule = await enablePublicationMetricTracking(selected.id, trackingDurationHours);
      setMetricSchedule(schedule);
      setAuthorizeTracking(false);
      notify({ message: t("publicationLibrary.trackingEnabled"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.trackingEnableError"));
    } finally {
      setBusy(null);
    }
  }

  async function pauseTracking() {
    if (!metricSchedule) return;
    setBusy("tracking-pause");
    setError(null);
    try {
      setMetricSchedule(await pausePublicationMetricTracking(metricSchedule.id));
      notify({ message: t("publicationLibrary.trackingPaused"), tone: "info" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.trackingPauseError"));
    } finally {
      setBusy(null);
    }
  }

  async function resumeTracking() {
    if (!metricSchedule) return;
    setBusy("tracking-resume");
    setError(null);
    try {
      setMetricSchedule(await resumePublicationMetricTracking(metricSchedule.id));
      notify({ message: t("publicationLibrary.trackingResumed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.trackingResumeError"));
    } finally {
      setBusy(null);
    }
  }

  async function openPublicationByContext(
    platformPublicationId: string,
    platformAccountId: string,
    nextInspectorTab: InspectorTab = "OVERVIEW",
  ) {
    setLibraryView("PUBLICATIONS");
    setWorkspaceMode("LIBRARY");
    setSyncSetupOpen(false);
    setSelected(null);
    setError(null);
    setBusy(`context-open-${platformPublicationId}`);
    try {
      const payload = await fetchPlatformPublications({
        platformAccountId,
        limit: 100,
      });
      setPublications(payload.publications);
      setTotal(payload.total_count);
      setAccountId(platformAccountId);
      setPublicationScope("PAGE");
      const publication = payload.publications.find((row) => row.id === platformPublicationId);
      if (!publication) {
        setError(t("trackingMonitor.publicationNotFound"));
        return;
      }
      await openPublication(publication, nextInspectorTab);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.loadError"));
    } finally {
      setBusy(null);
    }
  }

  async function openMonitorPublication(item: PublicationMetricTrackingMonitorItem) {
    await openPublicationByContext(item.schedule.platform_publication_id, item.platform_account_id, "TRACKING");
  }

  async function openClassificationPublication(item: ContentClassificationQueueItem) {
    await openPublicationByContext(item.platform_publication_id, item.platform_account_id, "CLASSIFY");
  }

  useEffect(() => {
    const jobId = insightsJob?.id;
    const publicationId = selected?.id;
    if (!jobId || !publicationId || !insightsJobActive) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const schedule = (delay: number) => {
      timer = setTimeout(() => void poll(), delay);
    };
    const poll = async () => {
      try {
        const updated = await fetchJob(jobId);
        if (cancelled) return;
        setInsightsJob(updated);
        if (updated.status === "COMPLETED") {
          const [growthPayload, snapshotPayload, schedulePayload] = await Promise.all([
            fetchPublicationGrowthSummary(publicationId),
            fetchPublicationMetricSnapshots(publicationId),
            fetchPublicationMetricSchedule(publicationId),
          ]);
          if (cancelled) return;
          setGrowth(growthPayload);
          setSnapshots(snapshotPayload.snapshots);
          setMetricSchedule(schedulePayload);
          setError(null);
          setBusy(null);
          notify({
            message: growthPayload.velocity_status === "BASELINE_ONLY"
              ? t("publicationLibrary.baselineSaved")
              : t("publicationLibrary.collectionCompleted"),
            tone: "success",
          });
          return;
        }
        if (updated.status === "FAILED" || updated.status === "CANCELLED") {
          setError(updated.error_message || t("publicationLibrary.collectionFailed"));
          setBusy(null);
          return;
        }
        schedule(updated.status === "RETRYABLE" ? 5000 : 1200);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : t("publicationLibrary.collectionStatusError"));
        schedule(5000);
      }
    };

    schedule(600);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [insightsJob?.id, selected?.id]);

  useEffect(() => {
    const publicationId = selected?.id;
    const scheduleId = metricSchedule?.id;
    if (!publicationId || !scheduleId || metricSchedule?.status !== "ACTIVE") return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const knownSnapshotId = metricSchedule.last_metric_snapshot_id;
    const poll = async () => {
      try {
        const updated = await fetchPublicationMetricSchedule(publicationId);
        if (cancelled || !updated) return;
        setMetricSchedule(updated);
        if (updated.last_metric_snapshot_id && updated.last_metric_snapshot_id !== knownSnapshotId) {
          const [growthPayload, snapshotPayload] = await Promise.all([
            fetchPublicationGrowthSummary(publicationId),
            fetchPublicationMetricSnapshots(publicationId),
          ]);
          if (cancelled) return;
          setGrowth(growthPayload);
          setSnapshots(snapshotPayload.snapshots);
          notify({ message: t("publicationLibrary.trackingSnapshotUpdated"), tone: "success" });
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : t("publicationLibrary.trackingStatusError"));
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 15_000);
    };

    timer = setTimeout(() => void poll(), 5_000);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [metricSchedule?.id, metricSchedule?.status, metricSchedule?.last_metric_snapshot_id, selected?.id]);

  function showLibraryWorkspace() {
    setWorkspaceMode("LIBRARY");
    setDiscoveryInspectorOpen(false);
    setLibraryInspectorOpen(false);
  }

  function showAllPagesLibrary() {
    if (publicationScope === "ALL") {
      showLibraryWorkspace();
      return;
    }
    void changePublicationScope("ALL");
  }

  function openDiscoveredInLibrary(item: FacebookReelDiscoveryItem) {
    setDiscoveryInspectorOpen(false);
    setSelectedDiscoveryReelId(null);
    setWorkspaceMode("LIBRARY");
    const match =
      publications.find((publication) => publication.id === item.platform_publication_id)
      ?? publications.find((publication) => publication.external_reel_id === item.reel_id)
      ?? null;
    if (match) void openPublication(match);
    else if (filteredPublications[0]) void openPublication(filteredPublications[0]);
    else if (publications[0]) void openPublication(publications[0]);
  }

  function openDiscoveryInspector(item: FacebookReelDiscoveryItem) {
    setSelectedDiscoveryReelId(item.reel_id);
    setDiscoveryInspectorOpen(true);
  }

  function closeDiscoveryInspector() {
    setDiscoveryInspectorOpen(false);
    setSelectedDiscoveryReelId(null);
  }

  useEffect(() => {
    if (libraryView !== "PUBLICATIONS" || workspaceMode !== "LIBRARY" || loading) return;
    if (filteredPublications.length === 0 || (selected && !filteredPublications.some((item) => item.id === selected.id))) {
      if (selected) setSelected(null);
      if (libraryInspectorOpen) setLibraryInspectorOpen(false);
      return;
    }
  }, [filteredPublications, libraryInspectorOpen, libraryView, loading, selected, workspaceMode]);

  useEffect(() => {
    if (discoveryPage !== discoverySafePage) setDiscoveryPage(discoverySafePage);
  }, [discoveryPage, discoverySafePage]);

  function handleDiscoveryPageSizeChange(nextPageSize: number) {
    if (nextPageSize === discoveryPageSize) return;
    setDiscoveryPageSize(nextPageSize);
    setDiscoveryPage(1);
    writeOperatorListPageSize(PUBLICATION_DISCOVERY_PAGE_SIZE_STORAGE_KEY, nextPageSize, OPERATOR_LIST_PAGE_SIZE_PRESETS);
  }

  function discoveryImportState(item: FacebookReelDiscoveryItem): ReelImportState {
    const itemBusy = busy === `import-${item.reel_id}`;
    const itemError = importErrors[item.reel_id] ?? null;
    return item.already_imported ? "IMPORTED" : itemBusy ? "IMPORTING" : itemError ? "FAILED" : "READY";
  }

  function discoveryStateLabel(state: ReelImportState): string {
    return state === "IMPORTED"
      ? t("publicationLibrary.importedState")
      : state === "IMPORTING"
        ? t("publicationLibrary.importingState")
        : state === "FAILED"
          ? t("publicationLibrary.importFailedState")
          : t("publicationLibrary.readyToImportState");
  }

  const isPageTransitionLoading = bootstrapReady && !pageDataReady;
  const showConnectPage = bootstrapReady && accounts.length === 0;
  const isSheetEmpty = bootstrapReady && publications.length === 0 && discovered === null;
  const isPostSyncEmpty = bootstrapReady && workspaceMode === "DISCOVERED" && discovered !== null && discovered.length === 0;
  const pageIdentitySubline = isSheetEmpty
    ? (activeAccount?.external_account_id ?? pageSyncLabel)
    : isPostSyncEmpty
      ? (activeAccount?.external_account_id ?? pageSyncLabel)
      : pageSyncLabel;

  const pagePicker = (
    <div className={`publication-library-page-bar__picker${pageMenuOpen ? " is-open" : ""}`} ref={pageMenuRef}>
              <button
                aria-expanded={pageMenuOpen}
                aria-haspopup="listbox"
                aria-label={t("publicationLibrary.page")}
                className="publication-library-page-bar__picker-trigger"
                disabled={busy === "sync" || loading || !pageDataReady}
                type="button"
                onClick={() => setPageMenuOpen((open) => !open)}
              >
                <span className="publication-library-page-avatar"><span aria-hidden="true" className="publication-library-page-avatar__fallback">{publicationAccountAvatarLabel(activeAccount)}</span>{activeAccountAvatarUrl ? <img alt="" src={activeAccountAvatarUrl} onError={(event) => { event.currentTarget.hidden = true; }} /> : null}<i>f</i></span>
                <span className="publication-library-page-bar__copy">
                  <span className="publication-library-page-bar__name-row">
                    <strong>{activeAccount?.display_name ?? t("publicationLibrary.selectPage")}</strong>
                    <span className={`publication-library-page-bar__picker-caret${pageMenuOpen ? " is-open" : ""}`} aria-hidden="true" />
                    {bootstrapReady && !isSheetEmpty && !isPostSyncEmpty && activeAccount?.external_account_id ? <code className="publication-library-page-external-id" title={activeAccount.external_account_id}>ID {activeAccount.external_account_id}</code> : null}
                  </span>
                  <span aria-live="polite" className={`publication-library-page-sync-state is-${effectivePageSyncStatus.toLowerCase()}${(isSheetEmpty || isPostSyncEmpty) && activeAccount?.external_account_id ? " is-page-id" : ""}`} title={(isSheetEmpty || isPostSyncEmpty) && activeAccount?.external_account_id ? activeAccount.external_account_id : pageSyncTimestamp ? t("publicationLibrary.syncCheckedAt").replace("{time}", formatDateTime(pageSyncTimestamp)) : t("publicationLibrary.syncNotCheckedHint")}>{(isSheetEmpty || isPostSyncEmpty) && activeAccount?.external_account_id ? <><b aria-hidden="true">ID</b><span>{pageIdentitySubline}</span></> : pageIdentitySubline}</span>
                </span>
              </button>
              {pageMenuOpen ? (
                <div className="publication-library-page-menu is-v300" role="listbox" aria-label={t("publicationLibrary.selectPage")}>
                  <div className="publication-library-page-menu__list">
                    <button
                      aria-selected={!accountId}
                      className={`publication-library-page-menu__item is-clear${!accountId ? " is-selected" : ""}`}
                      role="option"
                      type="button"
                      onClick={() => {
                        setPageMenuOpen(false);
                        void changeAccount("");
                      }}
                    >
                      <span className="publication-library-page-menu__label">{t("publicationLibrary.clearPageAction")}</span>
                      {!accountId ? <span className="publication-library-page-menu__check" aria-hidden="true" /> : null}
                    </button>
                    {syncedAccounts.length > 0 ? (
                      <div className="publication-library-page-menu__group" role="group" aria-label={t("publicationLibrary.pageMenuSyncedGroup")}>
                        <div className="publication-library-page-menu__group-label">{t("publicationLibrary.pageMenuSyncedGroup")}</div>
                        {syncedAccounts.map((account) => {
                          const avatarUrl = publicationAccountAvatarUrl(account);
                          const selected = account.id === accountId;
                          return (
                            <button
                              key={account.id}
                              aria-selected={selected}
                              className={`publication-library-page-menu__item is-synced${selected ? " is-selected" : ""}`}
                              role="option"
                              title={account.display_name}
                              type="button"
                              onClick={() => {
                                setPageMenuOpen(false);
                                void changeAccount(account.id);
                              }}
                            >
                              <span className="publication-library-page-avatar"><span aria-hidden="true" className="publication-library-page-avatar__fallback">{publicationAccountAvatarLabel(account)}</span>{avatarUrl ? <img alt="" src={avatarUrl} onError={(event) => { event.currentTarget.hidden = true; }} /> : null}</span>
                              <span className="publication-library-page-menu__copy">
                                <span className="publication-library-page-menu__label">{account.display_name}</span>
                                <span className="publication-library-page-menu__meta">{account.external_account_id}</span>
                              </span>
                              {selected ? <span className="publication-library-page-menu__check" aria-hidden="true" /> : null}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                    {neverSyncedAccounts.length > 0 ? (
                      <div className="publication-library-page-menu__group" role="group" aria-label={t("publicationLibrary.pageMenuNeverSyncedGroup")}>
                        <div className="publication-library-page-menu__group-label">{t("publicationLibrary.pageMenuNeverSyncedGroup")}</div>
                        {neverSyncedAccounts.map((account) => {
                          const avatarUrl = publicationAccountAvatarUrl(account);
                          const selected = account.id === accountId;
                          return (
                            <button
                              key={account.id}
                              aria-selected={selected}
                              className={`publication-library-page-menu__item is-never-synced${selected ? " is-selected" : ""}`}
                              role="option"
                              title={account.display_name}
                              type="button"
                              onClick={() => {
                                setPageMenuOpen(false);
                                void changeAccount(account.id);
                              }}
                            >
                              <span className="publication-library-page-avatar"><span aria-hidden="true" className="publication-library-page-avatar__fallback">{publicationAccountAvatarLabel(account)}</span>{avatarUrl ? <img alt="" src={avatarUrl} onError={(event) => { event.currentTarget.hidden = true; }} /> : null}</span>
                              <span className="publication-library-page-menu__copy">
                                <span className="publication-library-page-menu__label">{account.display_name}</span>
                                <span className="publication-library-page-menu__meta">{account.external_account_id}</span>
                              </span>
                              {selected ? <span className="publication-library-page-menu__check" aria-hidden="true" /> : null}
                            </button>
                          );
                        })}
                      </div>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>
  );

  return (
    <OperatorStudioShell
      actions={<TopbarRefreshButton busy={loading} disabled={loading} onClick={() => void load(true, { accountId, scope: publicationScope })} />}
      description={t("publicationLibrary.description")}
      title={t("publicationLibrary.title")}
    >
      <main className="publication-library-page is-v140">
        {error ? <div className="inline-error" role="alert">{error}</div> : null}
        <div className={`publication-library-stageframe is-v330 is-v1500 is-v1700 is-v1800${isPostSyncEmpty ? " is-sync-zero-v2160" : ""}`}>
          <aside className={`publication-library-sidedock is-v330 is-v331 is-v332 is-v800 is-v900 is-v1210 is-v1500 is-v1700 is-v1800 is-v1810${isPostSyncEmpty ? " is-sync-zero-v2160" : ""}`} aria-label={t("publicationLibrary.viewLabel")}>
            <nav className="publication-library-sidedock__views" role="tablist">
              <button aria-selected={libraryView === "PUBLICATIONS"} className={libraryView === "PUBLICATIONS" ? "is-active" : ""} onClick={() => setLibraryView("PUBLICATIONS")} role="tab" type="button" title={t("publicationLibrary.publicationsTab")}><PublicationLibraryIcon kind="library" /><span>{t("publicationLibrary.publicationsTab")}</span></button>
              <button aria-selected={libraryView === "TRACKING"} className={libraryView === "TRACKING" ? "is-active" : ""} onClick={() => setLibraryView("TRACKING")} role="tab" type="button" title={t("publicationLibrary.trackingTab")}><PublicationLibraryIcon kind="tracking" /><span>{t("publicationLibrary.trackingTab")}</span></button>
              <button aria-selected={libraryView === "INTELLIGENCE"} className={libraryView === "INTELLIGENCE" ? "is-active" : ""} onClick={() => setLibraryView("INTELLIGENCE")} role="tab" type="button" title={t("publicationLibrary.intelligenceTab")}><PublicationLibraryIcon kind="spark" /><span>{t("publicationLibrary.intelligenceTab")}</span></button>
            </nav>
            <Link className="publication-library-ai-settings-link publication-library-sidedock__ai" href="/publishing/settings/content-intelligence" title={t("publicationLibrary.configureAi")}><PublicationLibraryIcon kind="spark" /><span>{t("publicationLibrary.configureAi")}</span></Link>
          </aside>
          <div className="publication-library-op-surface">

        {!bootstrapReady ? (
          <section aria-busy="true" aria-label={t("publicationLibrary.title")} className="publication-library-bootstrap" role="status">
            <div className="publication-library-bootstrap__toolbar">
              <span className="publication-library-bootstrap__ghost is-avatar" />
              <span className="publication-library-bootstrap__ghost is-title" />
              <span className="publication-library-bootstrap__ghost is-action" />
            </div>
            <div className="publication-library-bootstrap__body">
              <div className="publication-library-bootstrap__lead">
                <span className="publication-library-bootstrap__ghost is-kicker" />
                <span className="publication-library-bootstrap__ghost is-heading" />
                <span className="publication-library-bootstrap__ghost is-copy" />
              </div>
              <div className="publication-library-bootstrap__cards" aria-hidden="true">
                <span /><span /><span />
              </div>
            </div>
          </section>
        ) : isPageTransitionLoading ? (
          <section aria-busy="true" aria-label={t("publicationLibrary.loadingPageLibrary")} className="publication-library-page-transition" role="status">
            <header className="publication-library-page-transition__head">
              <span className="publication-library-page-avatar publication-library-page-transition__avatar">
                <span aria-hidden="true" className="publication-library-page-avatar__fallback">{publicationAccountAvatarLabel(activeAccount)}</span>
                {activeAccountAvatarUrl ? <img alt="" src={activeAccountAvatarUrl} onError={(event) => { event.currentTarget.hidden = true; }} /> : null}
              </span>
              <div>
                <small>{t("publicationLibrary.loadingPageLibrary")}</small>
                <strong>{activeAccount?.display_name ?? t("publicationLibrary.selectPage")}</strong>
                <p>{t("publicationLibrary.loadingPageLibraryHint").replace("{page}", activeAccount?.display_name ?? t("publicationLibrary.selectPage"))}</p>
              </div>
              <span aria-hidden="true" className="publication-library-page-transition__pulse"><PublicationLibraryIcon kind="sync" /></span>
            </header>
            <div aria-hidden="true" className="publication-library-page-transition__tools">
              <span className="publication-library-page-transition__ghost is-scope" />
              <span className="publication-library-page-transition__ghost is-mode" />
              <span className="publication-library-page-transition__ghost is-search" />
              <span className="publication-library-page-transition__ghost is-filter" />
            </div>
            <div aria-hidden="true" className="publication-library-page-transition__sheet">
              <div className="publication-library-page-transition__sheet-head"><span /><span /><span /><span /><span /></div>
              <div className="publication-library-page-transition__row"><i /><span /><span /><span /><span /></div>
              <div className="publication-library-page-transition__row"><i /><span /><span /><span /><span /></div>
            </div>
          </section>
        ) : libraryView === "TRACKING" ? (
          <PublicationTrackingMonitor accounts={accounts} onOpenPublication={openMonitorPublication} />
        ) : libraryView === "INTELLIGENCE" ? (
          <section className="publication-library-intelligence is-v10 is-v11 is-v19 is-v20 is-v21 is-v22 is-v23 is-v24 is-v25 is-v26" aria-label={t("publicationLibrary.intelligenceLabel")}>
            <header className="publication-library-intelligence__head">
              <div className="publication-library-intelligence__intro">
                <span className="publication-library-intelligence__kicker">{t("publicationLibrary.intelligenceTab")}</span>
                <h2>
                  {intelligenceLane === "TAXONOMY"
                    ? t("publicationLibrary.taxonomyTab")
                    : intelligenceLane === "PRODUCT_MATCHING"
                      ? t("publicationLibrary.productMatchingTab")
                      : intelligenceLane === "OPPORTUNITIES"
                        ? t("publicationLibrary.opportunityRankingTab")
                        : t("publicationLibrary.classificationTab")}
                </h2>
                <p>{t("publicationLibrary.emptyLaneIntelligenceHint")}</p>
              </div>
              <Link className="publication-library-intelligence__settings" href="/publishing/settings/content-intelligence" title={t("publicationLibrary.configureAi")}>
                <PublicationLibraryIcon kind="settings" />
                <span>{t("publicationLibrary.configureAi")}</span>
              </Link>
              <nav aria-label={t("publicationLibrary.intelligenceLabel")} className="publication-library-intelligence-nav is-v10 is-v19 is-v20 is-v21 is-v22 is-v23 is-v24 is-v25 is-v26" role="tablist">
                <button aria-selected={intelligenceLane === "CLASSIFICATION"} className={intelligenceLane === "CLASSIFICATION" ? "is-active" : ""} onClick={() => setIntelligenceLane("CLASSIFICATION")} role="tab" type="button">{t("publicationLibrary.classificationTab")}</button>
                <button aria-selected={intelligenceLane === "TAXONOMY"} className={intelligenceLane === "TAXONOMY" ? "is-active" : ""} onClick={() => setIntelligenceLane("TAXONOMY")} role="tab" type="button">{t("publicationLibrary.taxonomyTab")}</button>
                <button aria-selected={intelligenceLane === "PRODUCT_MATCHING"} className={intelligenceLane === "PRODUCT_MATCHING" ? "is-active" : ""} onClick={() => setIntelligenceLane("PRODUCT_MATCHING")} role="tab" type="button">{t("publicationLibrary.productMatchingTab")}</button>
                <button aria-selected={intelligenceLane === "OPPORTUNITIES"} className={intelligenceLane === "OPPORTUNITIES" ? "is-active" : ""} onClick={() => setIntelligenceLane("OPPORTUNITIES")} role="tab" type="button">{t("publicationLibrary.opportunityRankingTab")}</button>
              </nav>
            </header>
            <div className="publication-library-intelligence__stage">
              {intelligenceLane === "CLASSIFICATION" ? <ContentClassificationQueue accounts={accounts} onOpenPublication={openClassificationPublication} /> : null}
              {intelligenceLane === "TAXONOMY" ? <ContentTaxonomyManager /> : null}
              {intelligenceLane === "PRODUCT_MATCHING" ? <AffiliateProductMatchingQueue /> : null}
              {intelligenceLane === "OPPORTUNITIES" ? <AffiliateOpportunityRanking /> : null}
            </div>
          </section>
        ) : isSheetEmpty ? (
          <section className={`publication-library-commanddeck is-v1800 is-v1870${pageMenuOpen ? " is-page-menu-open" : ""}`} aria-label={t("publicationLibrary.presyncWorkspaceTitle")}>
            <aside className="publication-library-commanddeck__source" aria-label={t("publicationLibrary.activePage")}>
              <header>
                <span className="publication-library-commanddeck__source-kicker"><PublicationLibraryIcon kind="page" />{t("publicationLibrary.facebookCatalog")}</span>
                <h2>{t("publicationLibrary.presyncWorkspaceTitle")}</h2>
                <p>{t("publicationLibrary.presyncWorkspaceDescription")}</p>
              </header>

              <div className="publication-library-commanddeck__source-console is-v1820 is-v1840 is-v1860">
                <div className="publication-library-commanddeck__page is-v1820">
                  <div className="publication-library-commanddeck__page-label is-v1820">
                    <span>{t("publicationLibrary.activePage")}</span>
                    <small aria-live="polite" className={`is-${effectivePageSyncStatus.toLowerCase()}`} title={pageSyncTimestamp ? t("publicationLibrary.syncCheckedAt").replace("{time}", formatDateTime(pageSyncTimestamp)) : t("publicationLibrary.syncNotCheckedHint")}><i aria-hidden="true" />{pageSyncLabel}</small>
                  </div>
                  <div className={`publication-library-commanddeck__source-controls is-v1830 is-v1840 is-v1850${showConnectPage ? " is-connect" : ""}`}>
                    <div className="publication-library-commanddeck__picker">{pagePicker}</div>
                    <div className="publication-library-commanddeck__action is-v1820">
                      {showConnectPage ? (
                        <Link className="publication-library-commanddeck__sync is-v1820 publication-library-connect-link" href="/publishing/accounts" title={t("publicationLibrary.connectPage")}><PublicationLibraryIcon kind="link" /><span>{t("publicationLibrary.connectPage")}</span></Link>
                      ) : (
                        <AsyncButton className="publication-library-commanddeck__sync is-v1820 primary" disabled={!accountId || loading || !pageDataReady} leadingIcon={<PublicationLibraryIcon kind="sync" />} pending={busy === "sync"} pendingLabel={t("publicationLibrary.syncingReels")} title={effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")} onClick={() => void syncReels()}>{effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")}</AsyncButton>
                      )}
                    </div>
                  </div>
                </div>

                <p className="publication-library-commanddeck__safety is-v1820" title={t("publicationLibrary.launchSafety")}><PublicationLibraryIcon kind="check" />{t("publicationLibrary.readOnlySync")}</p>
              </div>
            </aside>

            <div className="publication-library-commanddeck__canvas">
              <header className="publication-library-commanddeck__canvas-head">
                <span className="publication-library-commanddeck__ready"><i aria-hidden="true" />{t("publicationLibrary.presyncReadyTitle")}</span>
                <time>{t("publicationLibrary.presyncLastSync").replace("{time}", pageSyncTimestamp ? formatDateTime(pageSyncTimestamp) : t("publicationLibrary.neverSynced"))}</time>
              </header>

              <section className="publication-library-commanddeck__zero is-v1810" aria-label={t("publicationLibrary.presyncReadyTitle")}>
                <div className="publication-library-commanddeck__zero-copy is-v1810">
                  <span className="publication-library-commanddeck__zero-eyebrow"><i aria-hidden="true" />{t("publicationLibrary.firstSyncTitle")}</span>
                  <h3>{t("publicationLibrary.presyncReadyTitle")}</h3>
                  <p>{t("publicationLibrary.presyncReadyHint")}</p>
                </div>
                <div className="publication-library-commanddeck__route is-v1810" aria-hidden="true">
                  <span className="is-source"><i className="is-media" /><i /><i /></span>
                  <span className="is-transfer"><i className="is-media" /><i /><i /></span>
                  <span className="is-library"><span className="publication-library-commanddeck__reel-mark"><PublicationLibraryIcon kind="library" /></span><i className="is-media" /><i /><i /></span>
                </div>
              </section>

              <ol className="publication-library-commanddeck__outcomes is-v1870">
                <li><b aria-hidden="true">01</b><PublicationLibraryIcon kind="library" /><div><strong>{t("publicationLibrary.presyncBuildTitle")}</strong><small>{t("publicationLibrary.presyncBuildHint")}</small></div></li>
                <li><b aria-hidden="true">02</b><PublicationLibraryIcon kind="link" /><div><strong>{t("publicationLibrary.presyncLinkTitle")}</strong><small>{t("publicationLibrary.presyncLinkHint")}</small></div></li>
                <li><b aria-hidden="true">03</b><PublicationLibraryIcon kind="tracking" /><div><strong>{t("publicationLibrary.presyncTrackTitle")}</strong><small>{t("publicationLibrary.presyncTrackHint")}</small></div></li>
              </ol>
            </div>
          </section>
        ) : (
          <section className={`publication-library-studio is-opdesk is-v600 is-v700 is-v800 is-v900${isPostSyncEmpty ? " is-sync-zero-v2000" : ""}`}>
            {isPostSyncEmpty ? null : (
              <header className="publication-library-briefing is-v2500 is-v2510 is-v2520 is-v2530 is-v2540 is-v2550 is-v2560 is-v2570 is-v2580 is-v2590 is-v2600 is-v2610 is-v2620 is-v2630">
                <div aria-hidden="true" className="publication-library-briefing__spine">
                  <span>LIB</span>
                  <i />
                  <strong>01</strong>
                  <span>PAGE</span>
                </div>

                <div className="publication-library-briefing__body">
                  <div className="publication-library-briefing__topline">
                    <div className="publication-library-briefing__title">
                      <span><PublicationLibraryIcon kind="library" />{t("publicationLibrary.overview")}</span>
                      <h2>{t("publicationLibrary.publications")}</h2>
                      <p>{libraryHint}</p>
                    </div>
                    <div className="publication-library-briefing__status">
                      <span className="is-scope"><i aria-hidden="true" />{publicationScope === "ALL" ? t("publicationLibrary.allPages") : t("publicationLibrary.currentPage")}</span>
                      <span><PublicationLibraryIcon kind="check" />{t("publicationLibrary.readOnlySync")}</span>
                    </div>
                  </div>

                  <div className="publication-library-briefing__dock">
                    <section className="publication-library-briefing__page" aria-label={t("publicationLibrary.activePage")}>
                      <span className="publication-library-briefing__label"><PublicationLibraryIcon kind="page" />{t("publicationLibrary.activePage")}</span>
                      {pagePicker}
                    </section>

                    <dl className="publication-library-briefing__metrics is-chart is-pulse" aria-label={t("publicationLibrary.overview")}>
                      <div className="is-hero" style={{ ["--metric-pct" as string]: `${metricLinkedPct}%` }}>
                        <dt>{t("publicationLibrary.publications")}</dt>
                        <dd>
                          <span aria-hidden="true" className="publication-library-briefing__metric-ring"><i /></span>
                          <strong>{total}</strong>
                        </dd>
                      </div>
                      <div className={unlinkedCount > 0 ? "is-warning" : ""} style={{ ["--metric-pct" as string]: `${(unlinkedCount / metricChartMax) * 100}%` }}>
                        <dt>{t("publicationLibrary.unlinked")}</dt>
                        <dd>
                          <span aria-hidden="true" className="publication-library-briefing__metric-track"><i /></span>
                          <strong>{unlinkedCount}</strong>
                        </dd>
                      </div>
                      <div className={tracked > 0 ? "is-positive" : ""} style={{ ["--metric-pct" as string]: `${(tracked / metricChartMax) * 100}%` }}>
                        <dt>{t("publicationLibrary.tracked")}</dt>
                        <dd>
                          <span aria-hidden="true" className="publication-library-briefing__metric-track"><i /></span>
                          <strong>{tracked}</strong>
                        </dd>
                      </div>
                      <div className={needsAttention > 0 ? "is-danger" : ""} style={{ ["--metric-pct" as string]: `${(needsAttention / metricChartMax) * 100}%` }}>
                        <dt>{t("publicationLibrary.needsAttention")}</dt>
                        <dd>
                          <span aria-hidden="true" className="publication-library-briefing__metric-track"><i /></span>
                          <strong>{needsAttention}</strong>
                        </dd>
                      </div>
                    </dl>

                    <div className="publication-library-briefing__action">
                      {showConnectPage ? (
                        <Link className="publication-library-connect-link" href="/publishing/accounts"><PublicationLibraryIcon kind="link" />{t("publicationLibrary.connectPage")}</Link>
                      ) : (
                        <AsyncButton className="primary" disabled={!accountId || loading || !pageDataReady} leadingIcon={<PublicationLibraryIcon kind="sync" />} pending={busy === "sync"} pendingLabel={t("publicationLibrary.syncingReels")} onClick={() => void syncReels()}>{effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")}</AsyncButton>
                      )}
                      <time>{pageSyncTimestamp ? t("publicationLibrary.syncCheckedAt").replace("{time}", formatDateTime(pageSyncTimestamp)) : t("publicationLibrary.neverSynced")}</time>
                    </div>
                  </div>
                </div>
              </header>
            )}

            {!isPostSyncEmpty && (publications.length > 0 || discovered !== null) ? (
            <div className={`publication-library-tools is-v31 is-stage-sticky${isPostSyncEmpty ? " is-post-sync-empty" : ""}`}>
              <div className="publication-library-tools__navigation">
                <div className="publication-library-scope-tabs is-op" role="tablist" aria-label={t("publicationLibrary.scopeLabel")}>
                  <button aria-selected={publicationScope === "PAGE"} className={publicationScope === "PAGE" ? "is-active" : ""} disabled={!accountId || loading} onClick={() => void changePublicationScope("PAGE")} role="tab" type="button"><PublicationLibraryIcon kind="page" />{t("publicationLibrary.currentPage")}</button>
                  <button aria-selected={publicationScope === "ALL"} className={publicationScope === "ALL" ? "is-active" : ""} disabled={loading} onClick={() => void changePublicationScope("ALL")} role="tab" type="button"><PublicationLibraryIcon kind="pages" />{t("publicationLibrary.allPages")}</button>
                </div>
                {isPostSyncEmpty ? null : (
                  <nav aria-label={t("publicationLibrary.workspaceLabel")} className="publication-library-workspace-tabs" role="tablist">
                    <button aria-selected={workspaceMode === "LIBRARY"} className={workspaceMode === "LIBRARY" ? "is-active" : ""} onClick={showLibraryWorkspace} role="tab" type="button"><PublicationLibraryIcon kind="library" />{t("publicationLibrary.libraryMode")}<b>{publications.length}</b></button>
                    {discovered !== null ? (
                      <button aria-selected={workspaceMode === "DISCOVERED"} className={workspaceMode === "DISCOVERED" ? "is-active" : ""} onClick={() => setWorkspaceMode("DISCOVERED")} role="tab" type="button"><PublicationLibraryIcon kind="discover" />{t("publicationLibrary.discoveredMode")}<b>{discovered.length}</b></button>
                    ) : null}
                  </nav>
                )}
              </div>
              {isPostSyncEmpty ? null : <>
              {workspaceMode === "LIBRARY" ? (
                <div className="publication-library-tools__filters">
                  <label className="publication-library-search"><PublicationLibraryIcon kind="search" /><input aria-label={t("publicationLibrary.searchPlaceholder")} onChange={(event) => setPublicationQuery(event.target.value)} placeholder={t("publicationLibrary.searchPlaceholder")} type="search" value={publicationQuery} /></label>
                  <div className="publication-library-filter-chips" role="toolbar" aria-label={t("publicationLibrary.filterLabel")}>
                    <button className={publicationFilter === "ALL" ? "is-active" : ""} onClick={() => setPublicationFilter("ALL")} type="button"><PublicationLibraryIcon kind="library" />{t("publicationLibrary.allFilter")}<b>{total}</b></button>
                    <button className={publicationFilter === "UNLINKED" ? "is-active" : ""} onClick={() => setPublicationFilter("UNLINKED")} type="button"><PublicationLibraryIcon kind="link" />{t("publicationLibrary.unlinked")}<b>{Math.max(0, total - linked)}</b></button>
                    <button className={publicationFilter === "TRACKED" ? "is-active" : ""} onClick={() => setPublicationFilter("TRACKED")} type="button"><PublicationLibraryIcon kind="tracking" />{t("publicationLibrary.tracked")}<b>{tracked}</b></button>
                    <button className={publicationFilter === "ATTENTION" ? "is-active" : ""} onClick={() => setPublicationFilter("ATTENTION")} type="button"><PublicationLibraryIcon kind="alert" />{t("publicationLibrary.needsAttention")}<b>{needsAttention}</b></button>
                  </div>
                </div>
              ) : (
                <div className="publication-library-filter-chips" role="tablist" aria-label={t("publicationLibrary.discoveryStateLabel")}>
                  <button aria-selected={discoveryView === "PENDING"} className={discoveryView === "PENDING" ? "is-active" : ""} onClick={() => { setDiscoveryView("PENDING"); setDiscoveryPage(1); setDiscoverySelectedIds(new Set()); setSelectedDiscoveryReelId(discoveredNeedsImport[0]?.reel_id ?? null); }} role="tab" type="button"><PublicationLibraryIcon kind="discover" />{t("publicationLibrary.notInLibraryTab")}<b>{discoveredNeedsImport.length}</b></button>
                  <button aria-selected={discoveryView === "IMPORTED"} className={discoveryView === "IMPORTED" ? "is-active" : ""} onClick={() => { setDiscoveryView("IMPORTED"); setDiscoveryPage(1); setDiscoverySelectedIds(new Set()); setSelectedDiscoveryReelId(discoveredImported[0]?.reel_id ?? null); }} role="tab" type="button"><PublicationLibraryIcon kind="library" />{t("publicationLibrary.inLibraryTab")}<b>{discoveredImported.length}</b></button>
                </div>
              )}
              </>}
            </div>
            ) : null}

            <div className={`publication-library-desk${isSheetEmpty ? " is-v270-atelier" : ""}${isPostSyncEmpty ? " is-post-sync-empty is-sync-zero-desk" : ""}${!isSheetEmpty && workspaceMode === "LIBRARY" && publications.length > 0 ? ` is-v90 is-sheet-desk is-v43${filteredPublications.length <= 4 ? " is-sparse-v2220" : ""}` : ""}${!isSheetEmpty && workspaceMode === "DISCOVERED" ? " is-v43 is-discovered" : ""}`}>
              {isSheetEmpty || isPostSyncEmpty ? null : (
              <div className={`publication-library-passport is-v330${isPostSyncEmpty ? " is-post-sync-empty" : ""}`}>
                <div className="publication-library-passport__page">{pagePicker}</div>
                {showConnectPage ? (
                  <Link className="publication-library-connect-link publication-library-passport__sync" href="/publishing/accounts"><PublicationLibraryIcon kind="link" />{t("publicationLibrary.connectPage")}</Link>
                ) : (
                  <AsyncButton className="publication-library-passport__sync primary" disabled={!accountId || loading || !pageDataReady} leadingIcon={<PublicationLibraryIcon kind="sync" />} pending={busy === "sync"} pendingLabel={t("publicationLibrary.syncingReels")} onClick={() => void syncReels()}>{effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")}</AsyncButton>
                )}
              </div>
              )}

              {isSheetEmpty ? (
                <section className={`publication-library-import-dock is-v270 is-v800 is-v900${pageMenuOpen ? " is-page-menu-open" : ""}`} aria-label={t("publicationLibrary.emptyImportDockTitle")}>
                  <div className="publication-library-import-dock__stage" aria-hidden="true">
                    <i className="publication-library-import-dock__orb" />
                    <i className="publication-library-import-dock__ring" />
                    <i className="publication-library-import-dock__veil" />
                  </div>
                  <div className="publication-library-import-dock__bay is-v360 is-v410 is-v450 is-v600 is-v700 is-v800 is-v900" aria-label={t("publicationLibrary.emptyImportDockTitle")}>
                    <div className="publication-library-import-dock__mark" aria-hidden="true">
                      <span />
                      <span />
                      <span />
                    </div>
                    <div className="publication-library-runway is-v600 is-v700 is-v800 is-v900">
                      <div className="publication-library-import-dock__copy">
                        <p className="publication-library-import-dock__eyebrow">{t("publicationLibrary.ledgerTitle")}</p>
                        <div className="publication-library-stage-illustration" aria-hidden="true">
                          <span><PublicationLibraryIcon kind="library" /></span>
                          <span><PublicationLibraryIcon kind="discover" /></span>
                          <span><PublicationLibraryIcon kind="tracking" /></span>
                        </div>
                        <span className="publication-library-runway__mark" aria-hidden="true"><PublicationLibraryIcon kind="discover" /></span>
                        <strong>{t("publicationLibrary.ledgerEmptyTitle")}</strong>
                        <p>{t("publicationLibrary.ledgerEmptyHint")}</p>
                      </div>
                      <div className="publication-library-first-sync-flow" aria-label={t("publicationLibrary.workflowChecklist")}>
                        <article><b>01</b><span><PublicationLibraryIcon kind="page" />{t("publicationLibrary.emptyGuideStepPage")}</span></article>
                        <article><b>02</b><span><PublicationLibraryIcon kind="sync" />{t("publicationLibrary.emptyGuideStepSync")}</span></article>
                        <article><b>03</b><span><PublicationLibraryIcon kind="library" />{t("publicationLibrary.emptyGuideStepReview")}</span></article>
                      </div>
                      <aside className="publication-library-runway__destination">
                        <span>{t("publicationLibrary.pagePulse")}</span>
                        <strong>{activeAccount?.display_name ?? t("publicationLibrary.selectPage")}</strong>
                        <p>{t("publicationLibrary.transferDestinationHint")}</p>
                        <ul>
                          <li><PublicationLibraryIcon kind="library" /><span><b>{t("publicationLibrary.emptyStoryLibrary")}</b><small>{t("publicationLibrary.emptyLaneLibraryHint")}</small></span></li>
                          <li><PublicationLibraryIcon kind="tracking" /><span><b>{t("publicationLibrary.trackingTab")}</b><small>{t("publicationLibrary.emptyLaneMonitorHint")}</small></span></li>
                          <li><PublicationLibraryIcon kind="spark" /><span><b>{t("publicationLibrary.intelligenceTab")}</b><small>{t("publicationLibrary.emptyLaneIntelligenceHint")}</small></span></li>
                        </ul>
                      </aside>
                    </div>
                    <div className="publication-library-import-dock__segment-dock is-v450 is-luxe">
                      <div className="publication-library-import-dock__page publication-library-import-dock__segment-dock__page">{pagePicker}</div>
                      <i className="publication-library-import-dock__segment-dock__divider" aria-hidden="true" />
                      {showConnectPage ? (
                        <Link className="publication-library-import-dock__cta publication-library-import-dock__segment-dock__sync publication-library-connect-link" href="/publishing/accounts">
                          <PublicationLibraryIcon kind="link" />
                          <span>{t("publicationLibrary.connectPage")}</span>
                        </Link>
                      ) : (
                        <AsyncButton
                          className="publication-library-import-dock__cta publication-library-import-dock__segment-dock__sync"
                          disabled={!accountId || loading || !pageDataReady}
                          leadingIcon={<PublicationLibraryIcon kind="sync" />}
                          pending={busy === "sync"}
                          pendingLabel={t("publicationLibrary.syncingReels")}
                          onClick={() => void syncReels()}
                        >
                          {effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")}
                        </AsyncButton>
                      )}
                    </div>
                  </div>
                </section>
              ) : isPostSyncEmpty ? (
                <section className={`publication-library-sync-zero is-v2000 is-v2100 is-v2110 is-v2120 is-v2160${pageMenuOpen ? " is-page-menu-open" : ""}`} aria-labelledby="publication-library-sync-zero-title">
                  <header className="publication-library-source-panel is-v2160">
                    <div className="publication-library-source-panel__identity">
                      <div className="publication-library-source-panel__source">
                        <span className="publication-library-source-panel__eyebrow">{t("publicationLibrary.activePage")}</span>
                        <div className="publication-library-source-panel__page">{pagePicker}</div>
                      </div>
                      <span className="publication-library-source-panel__safety"><PublicationLibraryIcon kind="check" />{t("publicationLibrary.readOnlySync")}</span>
                    </div>
                    <div className="publication-library-source-panel__actions">
                      <div className="publication-library-source-panel__health">
                        <span className="publication-library-source-panel__health-kicker">{t("publicationLibrary.lastLibrarySync")}</span>
                        <div className="publication-library-source-panel__health-value">
                          <span aria-live="polite" className={`is-${effectivePageSyncStatus.toLowerCase()}`}><i aria-hidden="true" />{pageSyncLabel}</span>
                          <time>{pageSyncTimestamp ? t("publicationLibrary.syncCheckedAt").replace("{time}", formatDateTime(pageSyncTimestamp)) : t("publicationLibrary.neverSynced")}</time>
                        </div>
                      </div>
                      <span className="publication-library-source-panel__divider" aria-hidden="true" />
                      <AsyncButton aria-label={effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")} className="primary publication-library-source-panel__sync" disabled={!accountId || loading || !pageDataReady} leadingIcon={<PublicationLibraryIcon kind="sync" />} pending={busy === "sync"} pendingLabel={t("publicationLibrary.syncingReels")} onClick={() => void syncReels()}>{effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")}</AsyncButton>
                    </div>
                  </header>
                  <div className="publication-library-sync-zero__canvas">
                    <div className="publication-library-sync-zero__message">
                      <span className="publication-library-sync-zero__mark"><PublicationLibraryIcon kind="discover" /></span>
                      <div>
                        <small>{t("publicationLibrary.noSyncDataEyebrow")}</small>
                        <h2 id="publication-library-sync-zero-title">{t("publicationLibrary.noSyncDataTitle")}</h2>
                        <p>{t("publicationLibrary.noSyncDataHint")}</p>
                      </div>
                    </div>
                    <dl className="publication-library-sync-zero__metrics" aria-label={t("publicationLibrary.reelsReturnedMetric")}>
                      <div className="is-primary"><dt>{t("publicationLibrary.reelsReturnedMetric")}</dt><dd>{discovered?.length ?? 0}</dd></div>
                      <div><dt>{t("publicationLibrary.newReelsMetric")}</dt><dd>{discoveredNeedsImport.length}</dd></div>
                      <div><dt>{t("publicationLibrary.libraryRecordsMetric")}</dt><dd>{publications.length}</dd></div>
                    </dl>
                  </div>
                  <footer className="publication-library-sync-zero__footer">
                    {accounts.length > 1 ? (
                      <button className="publication-library-sync-zero__view-all" disabled={loading} onClick={showAllPagesLibrary} type="button">
                        <PublicationLibraryIcon kind="pages" />
                        {t("publicationLibrary.viewAllPageRecords")}
                        <span aria-hidden="true">→</span>
                      </button>
                    ) : publications.length > 0 ? (
                      <button onClick={showLibraryWorkspace} type="button"><PublicationLibraryIcon kind="library" />{t("publicationLibrary.openLibraryCount").replace("{count}", String(publications.length))}</button>
                    ) : null}
                  </footer>
                </section>
              ) : workspaceMode === "DISCOVERED" ? (
                <>
                  <section className="publication-library-worklist" aria-label={t("publicationLibrary.discovered")}>
                    {discoveryView === "PENDING" && discoveryBulkSelectedCount > 0 ? (
                      <div className="publication-library-discovery-bulk is-active" data-sticky="true" role="toolbar" aria-label={t("publicationLibrary.notInLibraryTab")}>
                        <span className="publication-library-discovery-bulk__count">{t("publicationLibrary.discoverySelectedCount").replace("{count}", String(discoveryBulkSelectedCount))}</span>
                        <div className="publication-library-discovery-bulk__actions">
                          <button disabled={busy === "bulk-import" || Boolean(busy?.startsWith("import-")) || discoveredPaged.length === 0} onClick={selectDiscoveryPage} type="button"><PublicationLibraryIcon kind="check" />{t("publicationLibrary.selectDiscoveryPage")}</button>
                          <button disabled={busy === "bulk-import" || Boolean(busy?.startsWith("import-"))} onClick={clearDiscoverySelection} type="button"><PublicationLibraryIcon kind="clear" />{t("publicationLibrary.clearDiscoverySelection")}</button>
                          <AsyncButton
                            className="primary"
                            disabled={Boolean(busy?.startsWith("import-") && busy !== "bulk-import")}
                            leadingIcon={<PublicationLibraryIcon kind="library" />}
                            pending={busy === "bulk-import" || Boolean(busy?.startsWith("import-"))}
                            pendingLabel={t("publicationLibrary.importingState")}
                            onClick={() => void importSelectedDiscoveries()}
                          >
                            {t("publicationLibrary.importSelected").replace("{count}", String(discoveryBulkSelectedCount))}
                          </AsyncButton>
                        </div>
                      </div>
                    ) : null}
                    {discoveredVisible.length === 0 ? (
                      <p className="publication-library-discovery-empty">{discoveryView === "PENDING" ? t("publicationLibrary.noPendingImports") : t("publicationLibrary.noImportedReels")}</p>
                    ) : discoveredPaged.map((item) => {
                      const importState = discoveryImportState(item);
                      const isSelected = discoveryInspectorOpen && (selectedDiscovery?.reel_id ?? null) === item.reel_id;
                      const isBulkSelected = discoveryView === "PENDING" && discoverySelectedIds.has(item.reel_id);
                      return (
                        <button className={`publication-library-worklist-row is-${importState.toLowerCase()}${isSelected ? " is-selected" : ""}${isBulkSelected ? " is-bulk-selected" : ""}${discoveryView === "PENDING" ? " is-selectable" : ""}`} key={item.reel_id} onClick={() => openDiscoveryInspector(item)} type="button">
                          {discoveryView === "PENDING" ? (
                            <span
                              aria-checked={isBulkSelected}
                              className={`publication-library-worklist-check${isBulkSelected ? " is-checked" : ""}`}
                              role="checkbox"
                              tabIndex={0}
                              onClick={(event) => {
                                event.preventDefault();
                                event.stopPropagation();
                                if (busy === "bulk-import" || busy?.startsWith("import-")) return;
                                toggleDiscoverySelected(item.reel_id);
                              }}
                              onKeyDown={(event) => {
                                if (event.key !== " " && event.key !== "Enter") return;
                                event.preventDefault();
                                event.stopPropagation();
                                if (busy === "bulk-import" || busy?.startsWith("import-")) return;
                                toggleDiscoverySelected(item.reel_id);
                              }}
                            />
                          ) : null}
                          <span className="publication-library-worklist-thumb">{item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span className="publication-library-thumb-placeholder">Reel</span>}</span>
                          <span className="publication-library-worklist-copy">
                            <b>{shortText(item.description, 180)}</b>
                            <span className="publication-library-worklist-meta">
                              <time dateTime={item.created_time ?? undefined}>{formatDateTime(item.created_time)}</time>
                              {item.permalink_url ? <small className="publication-library-worklist-meta__fb">Facebook</small> : null}
                            </span>
                          </span>
                          <span className="publication-library-worklist-side">
                            {item.already_imported ? (
                              <small className="publication-library-worklist-side__chip is-in-library">{t("publicationLibrary.inLibraryTab")}</small>
                            ) : importState !== "READY" ? (
                              <span aria-live="polite" className={`publication-library-reel-status is-${importState.toLowerCase()}`}><i aria-hidden="true" />{discoveryStateLabel(importState)}</span>
                            ) : null}
                            <code className="publication-library-worklist-side__id" title={item.reel_id}>{item.reel_id.length > 10 ? `${item.reel_id.slice(0, 8)}…` : item.reel_id}</code>
                          </span>
                        </button>
                      );
                    })}
                    {(discoveredVisible.length > 0 || nextCursor || failedImportCount > 0) ? (
                      <footer className="publication-library-worklist-footer is-paginated">
                        {discoveredVisible.length > 0 && discoveryTotalPages > 1 ? (
                          <>
                            <OperatorListPagination
                              busy={busy === "sync" || busy === "load-more"}
                              currentPage={discoverySafePage}
                              labels={{
                                pagination: t("publicationLibrary.pagination"),
                                perPage: t("publicationLibrary.perPage"),
                                previous: t("publicationLibrary.previousPage"),
                                next: t("publicationLibrary.nextPage"),
                                page: t("publicationLibrary.paginationPage"),
                                noun: t("publicationLibrary.reelsNoun"),
                              }}
                              pageSize={discoveryPageSize}
                              pageSizeOptions={OPERATOR_LIST_PAGE_SIZE_PRESETS}
                              totalCount={discoveredVisible.length}
                              onPageChange={setDiscoveryPage}
                              onPageSizeChange={handleDiscoveryPageSizeChange}
                            />
                            {discoveryView === "PENDING" && nextCursor && discoverySafePage >= discoveryTotalPages ? (
                              <AsyncButton className="publication-library-worklist-footer__fetch-more" pending={busy === "load-more"} onClick={() => void syncReels(nextCursor)}>{t("publicationLibrary.fetchMoreFromFacebook")}</AsyncButton>
                            ) : null}
                          </>
                        ) : discoveredVisible.length > 0 ? (
                          <div className="publication-library-worklist-footer__pool">
                            <p className="publication-library-worklist-footer__count">{discoveryView === "PENDING" ? t("publicationLibrary.discoveryPoolCount").replace("{count}", String(discovered?.length ?? discoveredVisible.length)) : t("publicationLibrary.discoveryImportedCount").replace("{count}", String(discoveredVisible.length))}</p>
                            {discoveryView === "PENDING" && nextCursor ? (
                              <AsyncButton className="publication-library-worklist-footer__fetch-more" pending={busy === "load-more"} onClick={() => void syncReels(nextCursor)}>{t("publicationLibrary.fetchMoreFromFacebook")}</AsyncButton>
                            ) : null}
                          </div>
                        ) : discoveryView === "PENDING" && nextCursor ? (
                          <AsyncButton className="publication-library-worklist-footer__fetch-more" pending={busy === "load-more"} onClick={() => void syncReels(nextCursor)}>{t("publicationLibrary.fetchMoreFromFacebook")}</AsyncButton>
                        ) : null}
                        {failedImportCount > 0 ? <em>{t("publicationLibrary.failedImportCount").replace("{count}", String(failedImportCount))}</em> : null}
                      </footer>
                    ) : null}
                  </section>
                  <WorkItemDetailsDrawer
                    eyebrow={t("publicationLibrary.discoveryInspectorEyebrow")}
                    footer={selectedDiscovery ? (
                      <div className="publication-library-discovery-inspector__actions">
                        {selectedDiscovery.already_imported ? (
                          <button className="primary" type="button" onClick={() => openDiscoveredInLibrary(selectedDiscovery)}>
                            <PublicationLibraryIcon kind="library" />
                            {t("publicationLibrary.viewInLibrary")}
                          </button>
                        ) : (
                          <AsyncButton
                            className="primary"
                            disabled={Boolean(busy?.startsWith("import-") && busy !== `import-${selectedDiscovery.reel_id}`)}
                            pending={busy === `import-${selectedDiscovery.reel_id}`}
                            pendingLabel={t("publicationLibrary.importingState")}
                            onClick={() => void importReel(selectedDiscovery)}
                          >
                            {importErrors[selectedDiscovery.reel_id] ? t("publicationLibrary.retryImport") : t("publicationLibrary.import")}
                          </AsyncButton>
                        )}
                      </div>
                    ) : null}
                    open={discoveryInspectorOpen && Boolean(selectedDiscovery)}
                    title={t("publicationLibrary.discoveryInspectorTitle")}
                    titleId="publication-library-discovery-details-title"
                    onClose={closeDiscoveryInspector}
                  >
                    {selectedDiscovery ? (
                      <div className="publication-library-discovery-inspector">
                        <section className="publication-library-discovery-inspector__summary is-card" aria-label={t("publicationLibrary.discovered")}>
                          <div className="publication-library-discovery-inspector__media">
                            {selectedDiscovery.thumbnail_url ? <img alt="" src={selectedDiscovery.thumbnail_url} /> : <span className="publication-library-thumb-placeholder">Reel</span>}
                          </div>
                          <div className="publication-library-discovery-inspector__copy">
                            <div className="publication-library-discovery-inspector__topline">
                              <span className="publication-library-discovery-inspector__status">
                                <i className={`is-${discoveryImportState(selectedDiscovery).toLowerCase()}`}>{discoveryStateLabel(discoveryImportState(selectedDiscovery))}</i>
                              </span>
                              {selectedDiscovery.permalink_url ? (
                                <a className="publication-library-discovery-inspector__open" href={selectedDiscovery.permalink_url} rel="noreferrer" target="_blank">
                                  <PublicationLibraryIcon kind="external" />
                                  {t("publicationLibrary.openFacebook")}
                                </a>
                              ) : null}
                            </div>
                            <strong>{shortText(selectedDiscovery.description, 220)}</strong>
                          </div>
                        </section>
                        <div className="publication-library-discovery-inspector__hint">
                          <small>{t("publicationLibrary.discoveryNextAction")}</small>
                          <strong>{t("publicationLibrary.discoveredHint")}</strong>
                        </div>
                        <section className="publication-library-discovery-inspector__overview" aria-labelledby="publication-library-discovery-overview-title">
                          <header className="publication-library-discovery-inspector__overview-head">
                            <div>
                              <span>{t("publicationLibrary.discoveredMode")}</span>
                              <h3 id="publication-library-discovery-overview-title">{t("publicationLibrary.discoveryOverview")}</h3>
                            </div>
                          </header>
                          <div className="publication-library-discovery-inspector__facts" role="list">
                            <div role="listitem"><small>{t("publicationLibrary.published")}</small><strong>{formatDateTime(selectedDiscovery.created_time)}</strong></div>
                            <div role="listitem"><small>{t("publicationLibrary.reelId")}</small><strong title={selectedDiscovery.reel_id}>{selectedDiscovery.reel_id}</strong></div>
                          </div>
                        </section>
                        {importErrors[selectedDiscovery.reel_id] ? <small className="publication-library-reel-error" title={importErrors[selectedDiscovery.reel_id]}>{importErrors[selectedDiscovery.reel_id]}</small> : null}
                      </div>
                    ) : null}
                  </WorkItemDetailsDrawer>
                </>

              ) : (
                <>
                  <div className="publication-library-sheet-wrap is-sheet">
                    {filteredPublications.length === 0 ? (
                      <p className="publication-library-no-results">{t("publicationLibrary.noFilterResults")}</p>
                    ) : (
                      <table className="publication-library-sheet is-sheet" aria-label={libraryTitle}>
                        <thead>
                          <tr>
                            <th>{t("publicationLibrary.reel")}</th>
                            <th>{t("publicationLibrary.page")}</th>
                            <th>{t("publicationLibrary.status")}</th>
                            <th>{t("publicationLibrary.linkedState")}</th>
                            <th>{t("publicationLibrary.trackedState")}</th>
                            <th>{t("publicationLibrary.published")}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {filteredPublications.map((publication) => {
                            const publicationTracked = Boolean(publication.metadata_json?.last_metric_collection_at);
                            const thumb = publicationThumbnail(publication);
                            const isSelected = libraryInspectorOpen && selected?.id === publication.id;
                            return (
                              <tr
                                aria-busy={busy === `inspect-${publication.id}` || undefined}
                                className={isSelected ? "is-focused" : undefined}
                                key={publication.id}
                                onClick={() => void openPublication(publication)}
                              >
                                <td>
                                  <div className="publication-library-sheet__reel">
                                    {thumb ? <img alt="" src={thumb} /> : <span className="publication-library-thumb-placeholder">Reel</span>}
                                    <div>
                                      <b>{shortText(publicationCaption(publication), 72)}</b>
                                      <small>{publication.external_reel_id}</small>
                                    </div>
                                  </div>
                                </td>
                                <td>{accountById.get(publication.platform_account_id)?.display_name ?? publication.platform}</td>
                                <td><span className={`publication-library-sheet__badge is-${publication.status.toLowerCase()}`}>{publication.status.replaceAll("_", " ")}</span></td>
                                <td>
                                  <small className={`publication-library-sheet__status ${publication.publish_draft_id ? "is-linked" : "is-unlinked"}`}>
                                    {publication.publish_draft_id ? t("publicationLibrary.linkedState") : t("publicationLibrary.unlinkedState")}
                                  </small>
                                </td>
                                <td>
                                  <small className={`publication-library-sheet__status ${publicationTracked ? "is-tracked" : "is-untracked"}`}>
                                    {publicationTracked ? t("publicationLibrary.trackedState") : t("publicationLibrary.notTrackedState")}
                                  </small>
                                </td>
                                <td><small>{formatDateTime(publication.published_at)}</small></td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    )}
                  </div>

                  <footer className="publication-library-sheet-footer" aria-label={t("publicationLibrary.libraryFooterLabel")}>
                    <div className="publication-library-sheet-footer__summary">
                      <span className="publication-library-sheet-footer__mark"><PublicationLibraryIcon kind="check" /></span>
                      <span>
                        <strong>{t("publicationLibrary.libraryFooterSaved").replace("{count}", String(filteredPublications.length))}</strong>
                        <small>{pageSyncTimestamp ? t("publicationLibrary.syncCheckedAt").replace("{time}", formatDateTime(pageSyncTimestamp)) : t("publicationLibrary.neverSynced")}</small>
                      </span>
                    </div>
                    <p>{t("publicationLibrary.libraryFooterHint")}</p>
                  </footer>

                  <WorkItemDetailsDrawer
                    eyebrow={t("publicationLibrary.libraryMode")}
                    open={libraryInspectorOpen && Boolean(selected)}
                    title={t("publicationLibrary.inspectorTitle")}
                    titleId="publication-library-sheet-details-title"
                    onClose={() => setLibraryInspectorOpen(false)}
                  >
                    {selected ? (
                      <div className="publication-library-sheet-inspector publication-library-focus is-worklist-focus publication-library-inspector publication-library-signal is-v6000">
                        {insightsJob ? <div aria-live="polite" className={`publication-library-job-status is-${insightsQueueDelayed ? "delayed" : insightsJob.status.toLowerCase()}`} role="status"><i aria-hidden="true" /><div><strong>{insightsQueueDelayed ? t("publicationLibrary.collectionWorkerDelayed") : insightsJob.status === "COMPLETED" && growth?.velocity_status === "BASELINE_ONLY" ? t("publicationLibrary.baselineSaved") : t(`publicationLibrary.collectionStatus.${insightsJob.status}`)}</strong><small>{t("publicationLibrary.collectionJobProgress").replace("{id}", insightsJob.id.slice(0, 8)).replace("{progress}", String(insightsJob.progress_percent))}</small>{insightsQueueDelayed ? <small className="publication-library-job-warning">{t("publicationLibrary.collectionWorkerDelayedDetail")}</small> : null}{insightsJob.error_message ? <small className="publication-library-job-error">{insightsJob.error_message}</small> : null}</div></div> : null}

                        <div className="publication-library-mode-shell mode-shell">
                          <nav className="publication-library-mode-rail mode-rail" role="tablist" aria-label={t("publicationLibrary.inspectorTitle")}>
                            <button
                              aria-label={t("publicationLibrary.inspectorOverview")}
                              aria-selected={inspectorTab === "OVERVIEW"}
                              className={inspectorTab === "OVERVIEW" ? "is-active" : undefined}
                              role="tab"
                              title={t("publicationLibrary.inspectorOverview")}
                              type="button"
                              onClick={() => setInspectorTab("OVERVIEW")}
                            >
                              <PublicationLibraryIcon kind="library" />
                              <span className="mode-rail__label">{t("publicationLibrary.inspectorOverview")}</span>
                            </button>
                            <button
                              aria-label={t("publicationLibrary.inspectorInsights")}
                              aria-selected={inspectorTab === "INSIGHTS"}
                              className={inspectorTab === "INSIGHTS" ? "is-active" : undefined}
                              role="tab"
                              title={t("publicationLibrary.inspectorInsights")}
                              type="button"
                              onClick={() => setInspectorTab("INSIGHTS")}
                            >
                              <PublicationLibraryIcon kind="views" />
                              <span className="mode-rail__label">{t("publicationLibrary.inspectorInsights")}</span>
                            </button>
                            <button
                              aria-label={t("publicationLibrary.inspectorTracking")}
                              aria-selected={inspectorTab === "TRACKING"}
                              className={inspectorTab === "TRACKING" ? "is-active" : undefined}
                              role="tab"
                              title={t("publicationLibrary.inspectorTracking")}
                              type="button"
                              onClick={() => setInspectorTab("TRACKING")}
                            >
                              <PublicationLibraryIcon kind="tracking" />
                              <span className="mode-rail__label">{t("publicationLibrary.inspectorTracking")}</span>
                            </button>
                            <button
                              aria-label={t("publicationLibrary.inspectorClassify")}
                              aria-selected={inspectorTab === "CLASSIFY"}
                              className={inspectorTab === "CLASSIFY" ? "is-active" : undefined}
                              role="tab"
                              title={t("publicationLibrary.inspectorClassify")}
                              type="button"
                              onClick={() => setInspectorTab("CLASSIFY")}
                            >
                              <PublicationLibraryIcon kind="spark" />
                              <span className="mode-rail__label">{t("publicationLibrary.inspectorClassify")}</span>
                            </button>
                          </nav>
                          <div className="publication-library-mode-shell__stage mode-shell__stage">
                        <div className={`publication-library-inspector-panel is-v6000 is-${inspectorTab.toLowerCase()}`} role="tabpanel">
                        {inspectorTab === "OVERVIEW" ? (
                          <div className="publication-library-overview-dock is-v6000">
                            <article className="publication-library-workbench workbench">
                              <div className="publication-library-workbench__identity workbench__identity">
                                <div className="publication-library-workbench__media workbench__media">
                                  {publicationThumbnail(selected) ? <img alt="" src={publicationThumbnail(selected) ?? ""} /> : <span className="publication-library-thumb-placeholder">Reel</span>}
                                </div>
                                <div className="publication-library-workbench__meta workbench__meta">
                                  <small className="publication-library-canvas__page">{accountById.get(selected.platform_account_id)?.display_name ?? selected.platform}</small>
                                  <strong
                                    className="publication-library-workbench__caption workbench__caption publication-library-canvas__caption"
                                    title={publicationCaption(selected)?.trim() || undefined}
                                  >
                                    {splitPublicationCaption(publicationCaption(selected)).lede}
                                  </strong>
                                  <div className="publication-library-workbench__actions workbench__actions">
                                    <i className={`publication-library-workbench__status workbench__status is-${selected.status.toLowerCase()}`}>{t(`publicationLibrary.externalStatus.${selected.status}`)}</i>
                                    {selected.external_permalink ? (
                                      <a
                                        aria-label={t("publicationLibrary.openFacebook")}
                                        className="publication-library-canvas__open"
                                        href={selected.external_permalink}
                                        rel="noreferrer"
                                        target="_blank"
                                        title={t("publicationLibrary.openFacebook")}
                                      >
                                        <PublicationLibraryIcon kind="external" />
                                        {t("publicationLibrary.openFacebook")}
                                      </a>
                                    ) : null}
                                    {selected.external_reel_id ? (
                                      <button
                                        aria-label={t("publicationLibrary.copyReelId")}
                                        className="publication-library-canvas__copy is-id"
                                        title={`${t("publicationLibrary.copyReelId")}: ${selected.external_reel_id}`}
                                        type="button"
                                        onClick={() => void copyReelId(selected.external_reel_id)}
                                      >
                                        <small className="publication-library-inspector-tabs__id">
                                          <b>{t("publicationLibrary.reelId")}</b>
                                          <span>{selected.external_reel_id}</span>
                                        </small>
                                      </button>
                                    ) : null}
                                  </div>
                                </div>
                              </div>

                              <ol aria-label={t("publicationLibrary.overviewSignals")} className="publication-library-workbench__tiles workbench__tiles">
                                <li>
                                  <button
                                    aria-label={t("publicationLibrary.views")}
                                    className="publication-library-workbench__tile workbench__tile"
                                    type="button"
                                    onClick={() => setInspectorTab("INSIGHTS")}
                                  >
                                    <small>{t("publicationLibrary.views")}</small>
                                    <strong>{growth?.latest_view_count == null ? t("publicationLibrary.notCollectedYet") : metric(growth.latest_view_count)}</strong>
                                  </button>
                                </li>
                                <li>
                                  <button
                                    className="publication-library-workbench__tile workbench__tile publication-library-overview-dock__signal-jump"
                                    type="button"
                                    onClick={() => setInspectorTab("TRACKING")}
                                  >
                                    <small>{t("publicationLibrary.inspectorTracking")}</small>
                                    <strong>{t(`publicationLibrary.trackingStatus.${trackingStatus}`)}</strong>
                                  </button>
                                </li>
                                <li>
                                  <div className="publication-library-workbench__tile workbench__tile">
                                    <small>{t("publicationLibrary.publishedAt")}</small>
                                    <strong title={selected.published_at ? formatDateTime(selected.published_at) : undefined}>{formatRelativeTime(selected.published_at, formatDateTime(selected.published_at))}</strong>
                                  </div>
                                </li>
                                <li>
                                  <div className="publication-library-workbench__tile workbench__tile">
                                    <small>{t("publicationLibrary.lastSynced")}</small>
                                    <strong title={selected.last_synced_at ? formatDateTime(selected.last_synced_at) : undefined}>{selected.last_synced_at ? formatRelativeTime(selected.last_synced_at, formatDateTime(selected.last_synced_at)) : t("publicationLibrary.neverSynced")}</strong>
                                  </div>
                                </li>
                              </ol>

                              <section
                                aria-label={t("publicationLibrary.draftLink")}
                                className="publication-library-workbench__draft-bar workbench__draft-bar publication-library-overview-dock__linkage publication-library-dossier-connect dossier-connect"
                              >
                                <strong className="publication-library-workbench__draft-label">{t("publicationLibrary.draftLink")}</strong>
                                {selected.publish_draft_id ? (
                                  <div className="publication-library-overview-dock__linked-draft">
                                    <div>
                                      <b>{shortText(activeDraftChoice?.title || selected.publish_draft_id.slice(0, 8), 64)}</b>
                                      <small>{activeDraftChoice?.status ?? t("publicationLibrary.linkedState")}</small>
                                    </div>
                                    <Link className="publication-library-overview-dock__open-draft" href={`/publishing/drafts/${selected.publish_draft_id}`}>
                                      {t("publicationLibrary.openLinkedDraft")}
                                    </Link>
                                  </div>
                                ) : (
                                  <div className="publication-library-workbench__draft-stack workbench__draft-stack">
                                    <div className={`publication-library-draft-picker${draftMenuOpen ? " is-open" : ""}`} ref={draftMenuRef}>
                                      <button
                                        aria-expanded={draftMenuOpen}
                                        aria-haspopup="listbox"
                                        aria-label={t("publicationLibrary.selectDraft")}
                                        className="publication-library-draft-picker__trigger"
                                        disabled={Boolean(selected.publish_draft_id)}
                                        type="button"
                                        onClick={() => {
                                          if (selected.publish_draft_id) return;
                                          setPageMenuOpen(false);
                                          setDraftMenuOpen((open) => !open);
                                        }}
                                      >
                                        <span className="publication-library-draft-picker__value">{draftPickerLabel}</span>
                                        <span aria-hidden="true" className={`publication-library-draft-picker__caret${draftMenuOpen ? " is-open" : ""}`} />
                                      </button>
                                      {draftMenuOpen && !selected.publish_draft_id ? (
                                        <div className="publication-library-draft-menu" role="listbox" aria-label={t("publicationLibrary.selectDraft")}>
                                          <div className="publication-library-draft-menu__list">
                                            <button
                                              aria-selected={!selectedDraftId}
                                              className={`publication-library-draft-menu__item${!selectedDraftId ? " is-selected" : ""}`}
                                              role="option"
                                              type="button"
                                              onClick={() => {
                                                setSelectedDraftId("");
                                                setDraftMenuOpen(false);
                                              }}
                                            >
                                              <span className="publication-library-draft-menu__copy">
                                                <span className="publication-library-draft-menu__label">{t("publicationLibrary.draftPickerNone")}</span>
                                              </span>
                                              {!selectedDraftId ? <span className="publication-library-draft-menu__check" aria-hidden="true" /> : null}
                                            </button>
                                            {drafts.length === 0 ? (
                                              <div className="publication-library-draft-menu__empty" role="status">
                                                {t("publicationLibrary.noFacebookDrafts")}
                                              </div>
                                            ) : (
                                              drafts.map((draft) => {
                                                const isSelected = draft.id === selectedDraftId;
                                                return (
                                                  <button
                                                    key={draft.id}
                                                    aria-selected={isSelected}
                                                    className={`publication-library-draft-menu__item${isSelected ? " is-selected" : ""}`}
                                                    role="option"
                                                    title={`${draft.title || draft.id} · ${draft.status}`}
                                                    type="button"
                                                    onClick={() => {
                                                      setSelectedDraftId(draft.id);
                                                      setDraftMenuOpen(false);
                                                    }}
                                                  >
                                                    <span className="publication-library-draft-menu__copy">
                                                      <span className="publication-library-draft-menu__label">{shortText(draft.title || draft.id.slice(0, 8), 64)}</span>
                                                      <small>{draft.status}</small>
                                                    </span>
                                                    {isSelected ? <span className="publication-library-draft-menu__check" aria-hidden="true" /> : null}
                                                  </button>
                                                );
                                              })
                                            )}
                                          </div>
                                        </div>
                                      ) : null}
                                    </div>
                                    <AsyncButton
                                      className={selectedDraftId ? "primary" : "secondary"}
                                      disabled={Boolean(selected.publish_draft_id) || !selectedDraftId}
                                      leadingIcon={<PublicationLibraryIcon kind="link" />}
                                      pending={busy === "link-draft"}
                                      onClick={() => void linkDraft()}
                                    >
                                      {t("publicationLibrary.linkDraft")}
                                    </AsyncButton>
                                  </div>
                                )}
                                {selected.source_video_id || selected.render_output_id ? (
                                  <div className="publication-library-overview-dock__lineage">
                                    <strong>{t("publicationLibrary.lineageTitle")}</strong>
                                    {selected.source_video_id ? (
                                      <Link href={`/production/final-review/${selected.source_video_id}`}>
                                        {t("publicationLibrary.lineageSourceVideo")}
                                      </Link>
                                    ) : null}
                                    {selected.render_output_id ? <small>{t("publicationLibrary.lineageRender").replace("{id}", selected.render_output_id.slice(0, 8))}</small> : null}
                                  </div>
                                ) : null}
                              </section>
                            </article>

                            {(() => {
                              const placementIdle = isIdleMonetizationStatus(selected.native_product_placement_status);
                              const affiliateIdle = isIdleMonetizationStatus(selected.affiliate_comment_status);
                              const monetizationIdle = placementIdle && affiliateIdle;
                              return (
                                <section
                                  className={`publication-library-overview-dock__monetization dossier-note${monetizationIdle ? " is-idle" : ""}`}
                                  aria-label={t("publicationLibrary.monetizationTitle")}
                                  title={monetizationIdle ? t("publicationLibrary.monetizationIdle") : undefined}
                                >
                                  <header>
                                    <strong>{t("publicationLibrary.monetizationTitle")}</strong>
                                    {monetizationIdle ? <small>{t("publicationLibrary.monetizationIdle")}</small> : null}
                                  </header>
                                  {!monetizationIdle ? (
                                    <div className="publication-library-overview-dock__monetization-grid">
                                      <div>
                                        <small>{t("publicationLibrary.nativePlacement")}</small>
                                        <strong>{placementIdle ? t("publicationLibrary.monetizationNotEvaluated") : selected.native_product_placement_status.replaceAll("_", " ")}</strong>
                                      </div>
                                      <div>
                                        <small>{t("publicationLibrary.affiliateComment")}</small>
                                        <strong>{affiliateIdle ? t("publicationLibrary.monetizationNotPlanned") : selected.affiliate_comment_status.replaceAll("_", " ")}</strong>
                                      </div>
                                    </div>
                                  ) : null}
                                </section>
                              );
                            })()}

                            <details className="publication-library-overview-dock__details is-lean">
                              <summary>{t("publicationLibrary.overviewMoreDetails")}</summary>
                              <div className="publication-library-overview-dock__details-body">
                                <div>
                                  <small>{t("publicationLibrary.fullCaption")}</small>
                                  {(() => {
                                    const caption = publicationCaption(selected);
                                    if (!caption) return <p>—</p>;
                                    const long = caption.length > 140;
                                    return (
                                      <>
                                        <p>{captionExpanded || !long ? caption : `${caption.slice(0, 140)}…`}</p>
                                        {long ? (
                                          <button type="button" onClick={() => setCaptionExpanded((open) => !open)}>
                                            {captionExpanded ? t("publicationLibrary.showLess") : t("publicationLibrary.showMore")}
                                          </button>
                                        ) : null}
                                      </>
                                    );
                                  })()}
                                </div>
                                <dl>
                                  <div>
                                    <dt>{t("publicationLibrary.publicationId")}</dt>
                                    <dd>{selected.id}</dd>
                                  </div>
                                  <div>
                                    <dt>{t("publicationLibrary.originLabel")}</dt>
                                    <dd className="publication-library-canvas__origin">{t(`publicationLibrary.origin.${selected.origin}`)}</dd>
                                  </div>
                                  <div>
                                    <dt>{t("publicationLibrary.published")}</dt>
                                    <dd>{formatDateTime(selected.published_at)}</dd>
                                  </div>
                                  <div>
                                    <dt>{t("publicationLibrary.lastSynced")}</dt>
                                    <dd>{selected.last_synced_at ? formatDateTime(selected.last_synced_at) : t("publicationLibrary.neverSynced")}</dd>
                                  </div>
                                  <div>
                                    <dt>{t("publicationLibrary.createdAt")}</dt>
                                    <dd>{formatDateTime(selected.created_at)}</dd>
                                  </div>
                                </dl>
                                <button
                                  className="publication-library-workbench-classify-link"
                                  type="button"
                                  onClick={() => setInspectorTab("CLASSIFY")}
                                >
                                  {t("publicationLibrary.openClassify")}
                                </button>
                              </div>
                            </details>
                          </div>
                        ) : null}

                        {inspectorTab === "INSIGHTS" ? (
                          <>
                            <section className="publication-library-growth">
                              <header>
                                <strong>{t("publicationLibrary.insights")}</strong>
                                <span>
                                  {t(`publicationLibrary.trendLabel.${growth?.trend_label ?? "NO_DATA"}`)}
                                  {" · "}
                                  {t("publicationLibrary.snapshotCount").replace("{count}", String(growth?.snapshot_count ?? snapshots.length))}
                                </span>
                              </header>
                              <div className="publication-library-metrics is-sheet">
                                <div>
                                  <span><PublicationLibraryIcon kind="views" />{t("publicationLibrary.views")}</span>
                                  <b className={growth?.latest_view_count == null ? "is-empty" : undefined}>{metric(growth?.latest_view_count)}</b>
                                </div>
                                <div>
                                  <span><PublicationLibraryIcon kind="rate" />{t("publicationLibrary.viewsPerHour")}</span>
                                  <b className={growth?.recent_views_per_hour == null ? "is-empty" : undefined}>{metric(growth?.recent_views_per_hour)}</b>
                                </div>
                                <div>
                                  <span><PublicationLibraryIcon kind="tracking" />{t("publicationLibrary.engagement")}</span>
                                  <b className={growth?.latest_engagement_rate_percent == null ? "is-empty" : undefined}>
                                    {growth?.latest_engagement_rate_percent == null ? "—" : `${growth.latest_engagement_rate_percent.toFixed(2)}%`}
                                  </b>
                                </div>
                                <div>
                                  <span><PublicationLibraryIcon kind="heart" />{t("publicationLibrary.likes")}</span>
                                  <b className={growth?.latest_like_count == null ? "is-empty" : undefined}>{metric(growth?.latest_like_count)}</b>
                                </div>
                                <div>
                                  <span><PublicationLibraryIcon kind="chat" />{t("publicationLibrary.comments")}</span>
                                  <b className={growth?.latest_comment_count == null ? "is-empty" : undefined}>{metric(growth?.latest_comment_count)}</b>
                                </div>
                                <div>
                                  <span><PublicationLibraryIcon kind="share" />{t("publicationLibrary.shares")}</span>
                                  <b className={growth?.latest_share_count == null ? "is-empty" : undefined}>{metric(growth?.latest_share_count)}</b>
                                </div>
                              </div>
                              {!preflight?.ready_for_live_job ? (
                                <div className="publication-library-insights-actions">
                                  <AsyncButton leadingIcon={<PublicationLibraryIcon kind="check" />} pending={busy === "preflight"} onClick={() => void runPreflight()}>{t("publicationLibrary.checkInsights")}</AsyncButton>
                                </div>
                              ) : null}
                              {preflight?.ready_for_live_job ? (
                                <div className="publication-library-insights-gate is-ready">
                                  <p className="publication-library-insights-gate__note">
                                    <span aria-hidden="true" className="publication-library-insights-gate__mark">✓</span>
                                    <span>
                                      <strong>{t("publicationLibrary.readinessPassedTitle")}</strong>
                                      <small>{t("publicationLibrary.readinessPassedDetail")}</small>
                                    </span>
                                  </p>
                                  <label className="publication-library-authorize">
                                    <input checked={authorizeNetwork} onChange={(event) => setAuthorizeNetwork(event.target.checked)} type="checkbox" />
                                    <span>{t("publicationLibrary.authorizeRead")}</span>
                                    <AsyncButton className="primary" disabled={!authorizeNetwork} leadingIcon={<PublicationLibraryIcon kind="collect" />} pending={busy === "collect"} onClick={() => void collectInsights()}>{t("publicationLibrary.collectOnce")}</AsyncButton>
                                  </label>
                                </div>
                              ) : preflight ? (
                                <section className="publication-library-preflight-result is-blocked">
                                  <header>
                                    <span aria-hidden="true">!</span>
                                    <div>
                                      <strong>{t("publicationLibrary.readinessBlockedTitle")}</strong>
                                      <small>{t("publicationLibrary.readinessBlockedDetail").replace("{count}", String(failedPreflightChecks.length))}</small>
                                    </div>
                                  </header>
                                  {failedPreflightChecks.length > 0 ? (
                                    <ul>
                                      {failedPreflightChecks.map((check) => (
                                        <li key={check.code}>
                                          <span aria-hidden="true">!</span>
                                          <div>
                                            <b>{check.code.replaceAll("_", " ")}</b>
                                            <small>{check.message}</small>
                                          </div>
                                        </li>
                                      ))}
                                    </ul>
                                  ) : null}
                                </section>
                              ) : null}
                              {growth && growth.velocity_status !== "STABLE" ? (
                                <div className={`publication-library-velocity-guidance is-${growth.velocity_status.toLowerCase()}`}>
                                  <strong>{t(`publicationLibrary.velocityStatus.${growth.velocity_status}`)}</strong>
                                  <small>
                                    {growth.velocity_status === "NO_DATA"
                                      ? t("publicationLibrary.velocityNoDataDetail")
                                      : growth.velocity_status === "COUNTER_REGRESSION"
                                        ? t("publicationLibrary.velocityRegressionDetail")
                                        : t("publicationLibrary.velocityWaitingDetail")
                                            .replace("{minutes}", String(Math.ceil(growth.minimum_velocity_interval_seconds / 60)))
                                            .replace("{time}", growth.next_stable_measurement_at ? formatDateTime(growth.next_stable_measurement_at) : "—")}
                                  </small>
                                  {growth.latest_data_quality === "PARTIAL" ? (
                                    <small className="publication-library-data-quality-note">{t("publicationLibrary.partialEngagementDetail")}</small>
                                  ) : null}
                                </div>
                              ) : null}
                            </section>
                          </>
                        ) : null}

                        {inspectorTab === "TRACKING" ? (
                          <section className={`publication-library-tracking is-${trackingStatus.toLowerCase()}`}>
                            <header><div><strong>{t("publicationLibrary.autoTracking")}</strong><small>{t("publicationLibrary.autoTrackingHint")}</small></div><span>{t(`publicationLibrary.trackingStatus.${trackingStatus}`)}</span></header>
                            {metricSchedule && ["ACTIVE", "PAUSED"].includes(metricSchedule.status) ? <>
                              <div className="publication-library-tracking-facts is-sheet"><div><span>{t("publicationLibrary.nextCollection")}</span><b>{metricSchedule.next_collection_at ? formatDateTime(metricSchedule.next_collection_at) : "—"}</b></div><div><span>{t("publicationLibrary.lastCollection")}</span><b>{metricSchedule.last_completed_at ? formatDateTime(metricSchedule.last_completed_at) : t("publicationLibrary.notCollectedYet")}</b></div><div><span>{t("publicationLibrary.trackingEnds")}</span><b>{metricSchedule.tracking_ends_at ? formatDateTime(metricSchedule.tracking_ends_at) : "—"}</b></div></div>
                              <footer><small>{trackingDecisionReason ?? t("publicationLibrary.adaptiveCadence")}</small>{metricSchedule.status === "ACTIVE" ? <AsyncButton leadingIcon={<PublicationLibraryIcon kind="pause" />} pending={busy === "tracking-pause"} onClick={() => void pauseTracking()}>{t("publicationLibrary.pauseTracking")}</AsyncButton> : <AsyncButton className="primary" leadingIcon={<PublicationLibraryIcon kind="sync" />} pending={busy === "tracking-resume"} onClick={() => void resumeTracking()}>{t("publicationLibrary.resumeTracking")}</AsyncButton>}</footer>
                            </> : (
                              <div className="publication-library-tracking-setup">
                                {metricSchedule?.status === "BLOCKED" && trackingDecisionReason ? <div className="publication-library-tracking-warning">{trackingDecisionReason}</div> : null}
                                {!preflight?.ready_for_live_job ? (
                                  <div className="publication-library-tracking-readiness">
                                    <small>{t("publicationLibrary.trackingReadinessRequired")}</small>
                                    <AsyncButton leadingIcon={<PublicationLibraryIcon kind="check" />} pending={busy === "preflight"} onClick={() => void runPreflight()}>{t("publicationLibrary.checkInsights")}</AsyncButton>
                                  </div>
                                ) : null}
                                <label className={`publication-library-tracking-consent${!preflight?.ready_for_live_job ? " is-locked" : ""}`}><input checked={authorizeTracking} disabled={!preflight?.ready_for_live_job} onChange={(event) => setAuthorizeTracking(event.target.checked)} type="checkbox" /><span>{t("publicationLibrary.authorizeTracking")}</span></label>
                                <div className="publication-library-tracking-enable"><label><span>{t("publicationLibrary.trackingWindow")}</span><select className="publication-library-tracking-window" value={trackingDurationHours} onChange={(event) => setTrackingDurationHours(Number(event.target.value))}><option value={24}>{t("publicationLibrary.tracking24h")}</option><option value={72}>{t("publicationLibrary.tracking72h")}</option><option value={168}>{t("publicationLibrary.tracking7d")}</option></select></label><AsyncButton className="primary" disabled={!preflight?.ready_for_live_job || !authorizeTracking} leadingIcon={<PublicationLibraryIcon kind="sync" />} pending={busy === "tracking-enable"} onClick={() => void enableTracking()}>{metricSchedule ? t("publicationLibrary.restartTracking") : t("publicationLibrary.enableTracking")}</AsyncButton></div>
                              </div>
                            )}
                          </section>
                        ) : null}

                        {inspectorTab === "CLASSIFY" ? <PublicationClassificationPanel publicationId={selected.id} /> : null}
                        </div>
                          </div>
                        </div>
                      </div>
                    ) : null}
                  </WorkItemDetailsDrawer>
                </>
              )}
            </div>
          </section>
        )}
        </div>
        </div>
      </main>
    </OperatorStudioShell>
  );
}
