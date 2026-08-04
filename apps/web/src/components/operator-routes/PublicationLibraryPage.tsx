"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type ReactNode } from "react";
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

type PublicationLibraryIconKind = "library" | "sync" | "link" | "tracking" | "alert" | "search" | "external" | "page" | "pages";

function PublicationLibraryIcon({ kind }: { kind: PublicationLibraryIconKind }) {
  const paths: Record<PublicationLibraryIconKind, ReactNode> = {
    library: <><path d="M4 5.5h16v14H4z" /><path d="m10 9 5 3-5 3z" /></>,
    sync: <><path d="M20 7v5h-5" /><path d="M4 17v-5h5" /><path d="M6.1 9a7 7 0 0 1 11.8-2L20 9M4 15l2.1 2a7 7 0 0 0 11.8-2" /></>,
    link: <><path d="M10.5 13.5 13.5 10" /><path d="M8.8 16.2 7 18a3.5 3.5 0 0 1-5-5l3-3a3.5 3.5 0 0 1 5 0" /><path d="m15.2 7.8 1.8-1.8a3.5 3.5 0 0 1 5 5l-3 3a3.5 3.5 0 0 1-5 0" /></>,
    tracking: <><path d="M4 18V9M10 18V5M16 18v-7M22 18V3" /><path d="M2 20h22" /></>,
    alert: <><path d="m12 3 10 18H2z" /><path d="M12 9v5M12 17h.01" /></>,
    search: <><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 5 5" /></>,
    external: <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 13v7H4V6h7" /></>,
    page: <><path d="M7 4h8l4 4v12H7z" /><path d="M15 4v4h4" /><path d="M10 12h6M10 16h4" /></>,
    pages: <><path d="M8 7h9v13H8z" /><path d="M5 4h9v3" /><path d="M5 4v13h3" /></>,
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
  const [importErrors, setImportErrors] = useState<Record<string, string>>({});
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<PlatformPublication | null>(null);
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
  const [error, setError] = useState<string | null>(null);

  async function load(showNotice = false, options: LoadOptions = {}) {
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
      setAccounts(facebookAccounts);
      setDrafts(draftRows);
      setPublications(publicationPayload.publications);
      setTotal(publicationPayload.total_count);
      setAccountId(resolvedAccountId);
      setPublicationScope(resolvedScope);
      setSelected((current) => current ? publicationPayload.publications.find((item) => item.id === current.id) ?? null : null);
      setSyncSetupOpen(publicationPayload.publications.length === 0);
      if (publicationPayload.publications.length > 0) setPageSyncStatus((current) => current === "PRE_SYNC" ? "SYNCED" : current);
      if (showNotice) notify({ message: t("publicationLibrary.refreshed"), tone: "success" });
    } catch (err) {
      setError(err instanceof Error ? err.message : t("publicationLibrary.loadError"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load(false, { accountId: initialAccountId, scope: "PAGE" });
  }, [initialAccountId, t]);

  const accountById = useMemo(() => new Map(accounts.map((item) => [item.id, item])), [accounts]);
  const activeAccount = accountById.get(accountId) ?? null;
  const activeAccountAvatarUrl = publicationAccountAvatarUrl(activeAccount);
  const linked = publications.filter((item) => item.publish_draft_id).length;
  const tracked = publications.filter((item) => item.metadata_json?.last_metric_collection_at).length;
  const needsAttention = publications.filter((item) => item.status !== "PUBLISHED").length;
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
  const selectedDiscovery = useMemo(
    () => discoveredVisible.find((item) => item.reel_id === selectedDiscoveryReelId) ?? discoveredVisible[0] ?? null,
    [discoveredVisible, selectedDiscoveryReelId],
  );
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
    setAccountId(nextAccountId);
    setPublicationScope("PAGE");
    setWorkspaceMode("LIBRARY");
    setDiscovered(null);
    setPageSyncStatus("PRE_SYNC");
    setLastPageSyncAt(null);
    setDiscoveryView("PENDING");
    setSelectedDiscoveryReelId(null);
    setImportErrors({});
    setNextCursor(null);
    setSelected(null);
    await load(false, { accountId: nextAccountId, scope: "PAGE" });
  }

  async function changePublicationScope(nextScope: PublicationScope) {
    if (nextScope === publicationScope || (nextScope === "PAGE" && !accountId)) return;
    setPublicationScope(nextScope);
    setWorkspaceMode("LIBRARY");
    setSelected(null);
    await load(false, { accountId, scope: nextScope });
  }

  async function syncReels(after?: string | null) {
    if (!accountId) return;
    setBusy(after ? "load-more" : "sync");
    if (!after) setPageSyncStatus("SYNCING");
    setError(null);
    if (!after) setImportErrors({});
    try {
      const payload = await discoverFacebookReels(accountId, after);
      setDiscovered((current) => after && current ? [...current, ...payload.items] : payload.items);
      setNextCursor(payload.next_cursor);
      setLastPageSyncAt(new Date().toISOString());
      const pendingCount = payload.items.filter((item) => !item.already_imported).length;
      setPageSyncStatus(payload.next_cursor ? "HAS_MORE" : pendingCount > 0 ? "HAS_NEW" : "UP_TO_DATE");
      setDiscoveryView(pendingCount > 0 ? "PENDING" : "IMPORTED");
      setWorkspaceMode("DISCOVERED");
      setSyncSetupOpen(false);
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

  async function importReel(item: FacebookReelDiscoveryItem) {
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
      await load();
      setSelected(publication);
      notify({ message: t("publicationLibrary.imported"), tone: "success" });
    } catch (err) {
      const message = err instanceof Error ? err.message : t("publicationLibrary.importError");
      if (/already imported/i.test(message)) {
        setDiscovered((current) => current?.map((row) => row.reel_id === item.reel_id ? { ...row, already_imported: true } : row) ?? null);
        await load(false, { accountId, scope: publicationScope });
        notify({ message: t("publicationLibrary.alreadyImported"), tone: "info" });
      } else {
        setImportErrors((current) => ({ ...current, [item.reel_id]: message }));
        setError(message);
      }
    } finally {
      setBusy(null);
    }
  }

  async function openPublication(publication: PlatformPublication, nextInspectorTab: InspectorTab = "OVERVIEW") {
    setSelected(publication);
    setInspectorTab(nextInspectorTab);
    setSelectedDraftId(publication.publish_draft_id ?? "");
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
      setPreflight(await preflightFacebookInsights(selected.id, {
        operator_confirmation: "FACEBOOK_INSIGHTS_LIVE_PILOT_APPROVED",
        expected_platform_account_id: account.id,
        expected_external_account_id: account.external_account_id,
        expected_media_id: mediaId,
        required_scopes: ["read_insights", "pages_read_engagement"],
      }));
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
    if (!selected && publications[0]) void openPublication(publications[0]);
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

  return (
    <OperatorStudioShell
      actions={<TopbarRefreshButton busy={loading} disabled={loading} onClick={() => void load(true, { accountId, scope: publicationScope })} />}
      description={t("publicationLibrary.description")}
      title={t("publicationLibrary.title")}
    >
      <main className="publication-library-page is-v21">
        {error ? <div className="inline-error" role="alert">{error}</div> : null}
        <div className="publication-library-view-nav">
          <nav className="publication-library-main-tabs" aria-label={t("publicationLibrary.viewLabel")} role="tablist">
            <button aria-selected={libraryView === "PUBLICATIONS"} className={libraryView === "PUBLICATIONS" ? "is-active" : ""} onClick={() => setLibraryView("PUBLICATIONS")} role="tab" type="button">{t("publicationLibrary.publicationsTab")}</button>
            <button aria-selected={libraryView === "TRACKING"} className={libraryView === "TRACKING" ? "is-active" : ""} onClick={() => setLibraryView("TRACKING")} role="tab" type="button">{t("publicationLibrary.trackingTab")}</button>
            <button aria-selected={libraryView === "INTELLIGENCE"} className={libraryView === "INTELLIGENCE" ? "is-active" : ""} onClick={() => setLibraryView("INTELLIGENCE")} role="tab" type="button">{t("publicationLibrary.intelligenceTab")}</button>
          </nav>
          <Link className="publication-library-ai-settings-link" href="/publishing/settings/content-intelligence"><span aria-hidden="true">⚙</span>{t("publicationLibrary.configureAi")}</Link>
        </div>

        {libraryView === "TRACKING" ? (
          <PublicationTrackingMonitor accounts={accounts} onOpenPublication={openMonitorPublication} />
        ) : libraryView === "INTELLIGENCE" ? (
          <section className="publication-library-intelligence">
            <nav aria-label={t("publicationLibrary.intelligenceLabel")} className="publication-library-intelligence-nav" role="tablist">
              <button aria-selected={intelligenceLane === "CLASSIFICATION"} className={intelligenceLane === "CLASSIFICATION" ? "is-active" : ""} onClick={() => setIntelligenceLane("CLASSIFICATION")} role="tab" type="button">{t("publicationLibrary.classificationTab")}</button>
              <button aria-selected={intelligenceLane === "TAXONOMY"} className={intelligenceLane === "TAXONOMY" ? "is-active" : ""} onClick={() => setIntelligenceLane("TAXONOMY")} role="tab" type="button">{t("publicationLibrary.taxonomyTab")}</button>
              <button aria-selected={intelligenceLane === "PRODUCT_MATCHING"} className={intelligenceLane === "PRODUCT_MATCHING" ? "is-active" : ""} onClick={() => setIntelligenceLane("PRODUCT_MATCHING")} role="tab" type="button">{t("publicationLibrary.productMatchingTab")}</button>
              <button aria-selected={intelligenceLane === "OPPORTUNITIES"} className={intelligenceLane === "OPPORTUNITIES" ? "is-active" : ""} onClick={() => setIntelligenceLane("OPPORTUNITIES")} role="tab" type="button">{t("publicationLibrary.opportunityRankingTab")}</button>
            </nav>
            {intelligenceLane === "CLASSIFICATION" ? <ContentClassificationQueue accounts={accounts} onOpenPublication={openClassificationPublication} /> : null}
            {intelligenceLane === "TAXONOMY" ? <ContentTaxonomyManager /> : null}
            {intelligenceLane === "PRODUCT_MATCHING" ? <AffiliateProductMatchingQueue /> : null}
            {intelligenceLane === "OPPORTUNITIES" ? <AffiliateOpportunityRanking /> : null}
          </section>
        ) : (
          <section className={`publication-library-studio is-v21${publications.length === 0 && discovered === null ? " is-empty" : ""}`}>
            <header className="publication-library-page-bar is-v30">
              <div className="publication-library-page-bar__compact">
                <label className="publication-library-page-bar__picker">
                  <span className="publication-library-page-avatar">{activeAccountAvatarUrl ? <img alt="" src={activeAccountAvatarUrl} /> : publicationAccountAvatarLabel(activeAccount)}<i>f</i></span>
                  <span className="publication-library-page-bar__copy">
                    <span className="publication-library-page-bar__name-row">
                      <strong>{activeAccount?.display_name ?? t("publicationLibrary.selectPage")}</strong>
                      <span className="publication-library-page-bar__picker-caret" aria-hidden="true" />
                    </span>
                    <span aria-live="polite" className={`publication-library-page-sync-state is-${effectivePageSyncStatus.toLowerCase()}`} title={pageSyncTimestamp ? t("publicationLibrary.syncCheckedAt").replace("{time}", formatDateTime(pageSyncTimestamp)) : t("publicationLibrary.syncNotCheckedHint")}>{pageSyncLabel}</span>
                  </span>
                  <select
                    aria-label={t("publicationLibrary.page")}
                    className="publication-library-page-bar__picker-select"
                    disabled={busy === "sync"}
                    value={accountId}
                    onChange={(event) => void changeAccount(event.target.value)}
                  >
                    <option value="">{t("publicationLibrary.selectPage")}</option>
                    {accounts.map((account) => <option key={account.id} value={account.id}>{account.display_name}</option>)}
                  </select>
                </label>
                <div className="publication-library-page-bar__cluster">
                  <div className="publication-library-scope-tabs" role="tablist" aria-label={t("publicationLibrary.scopeLabel")}>
                    <button aria-selected={publicationScope === "PAGE"} className={publicationScope === "PAGE" ? "is-active" : ""} disabled={!accountId || loading} onClick={() => void changePublicationScope("PAGE")} role="tab" type="button"><PublicationLibraryIcon kind="page" />{t("publicationLibrary.currentPage")}</button>
                    <button aria-selected={publicationScope === "ALL"} className={publicationScope === "ALL" ? "is-active" : ""} disabled={loading} onClick={() => void changePublicationScope("ALL")} role="tab" type="button"><PublicationLibraryIcon kind="pages" />{t("publicationLibrary.allPages")}</button>
                  </div>
                  {accounts.length === 0 ? (
                    <Link className="publication-library-connect-link" href="/publishing/accounts"><PublicationLibraryIcon kind="link" />{t("publicationLibrary.connectPage")}</Link>
                  ) : (
                    <AsyncButton className="publication-library-page-bar__sync primary" disabled={!accountId} leadingIcon={<PublicationLibraryIcon kind="sync" />} pending={busy === "sync"} pendingLabel={t("publicationLibrary.syncingReels")} onClick={() => void syncReels()}>{effectivePageSyncStatus === "FAILED" ? t("publicationLibrary.retrySync") : t("publicationLibrary.syncReels")}</AsyncButton>
                  )}
                </div>
              </div>
            </header>

            <div className={`publication-library-tools is-v31${publications.length === 0 && discovered === null ? " is-empty" : ""}`}>
              {publications.length > 0 || discovered !== null ? (
                <nav aria-label={t("publicationLibrary.workspaceLabel")} className="publication-library-workspace-tabs" role="tablist">
                  <button aria-selected={workspaceMode === "LIBRARY"} className={workspaceMode === "LIBRARY" ? "is-active" : ""} onClick={showLibraryWorkspace} role="tab" type="button"><PublicationLibraryIcon kind="library" />{t("publicationLibrary.libraryMode")}<b>{publications.length}</b></button>
                  <button aria-selected={workspaceMode === "DISCOVERED"} className={workspaceMode === "DISCOVERED" ? "is-active" : ""} disabled={discovered == null} onClick={() => setWorkspaceMode("DISCOVERED")} role="tab" type="button"><PublicationLibraryIcon kind="sync" />{t("publicationLibrary.discoveredMode")}<b>{discovered?.length ?? 0}</b></button>
                </nav>
              ) : null}
              {workspaceMode === "LIBRARY" && publications.length === 0 ? (
                <p className="publication-library-tools__empty-cue">{t("publicationLibrary.emptyToolsCue")}</p>
              ) : workspaceMode === "LIBRARY" ? (
                <div className="publication-library-tools__filters">
                  <label className="publication-library-search"><PublicationLibraryIcon kind="search" /><input aria-label={t("publicationLibrary.searchPlaceholder")} onChange={(event) => setPublicationQuery(event.target.value)} placeholder={t("publicationLibrary.searchPlaceholder")} type="search" value={publicationQuery} /></label>
                  <div className="publication-library-filter-chips" role="toolbar" aria-label={t("publicationLibrary.filterLabel")}>
                    <button className={publicationFilter === "ALL" ? "is-active" : ""} onClick={() => setPublicationFilter("ALL")} type="button">{t("publicationLibrary.allFilter")}<b>{total}</b></button>
                    <button className={publicationFilter === "UNLINKED" ? "is-active" : ""} onClick={() => setPublicationFilter("UNLINKED")} type="button">{t("publicationLibrary.unlinked")}<b>{Math.max(0, total - linked)}</b></button>
                    <button className={publicationFilter === "TRACKED" ? "is-active" : ""} onClick={() => setPublicationFilter("TRACKED")} type="button">{t("publicationLibrary.tracked")}<b>{tracked}</b></button>
                    <button className={publicationFilter === "ATTENTION" ? "is-active" : ""} onClick={() => setPublicationFilter("ATTENTION")} type="button">{t("publicationLibrary.needsAttention")}<b>{needsAttention}</b></button>
                  </div>
                </div>
              ) : (
                <div className="publication-library-filter-chips" role="tablist" aria-label={t("publicationLibrary.discoveryStateLabel")}>
                  <button aria-selected={discoveryView === "PENDING"} className={discoveryView === "PENDING" ? "is-active" : ""} onClick={() => { setDiscoveryView("PENDING"); setSelectedDiscoveryReelId(discoveredNeedsImport[0]?.reel_id ?? null); }} role="tab" type="button">{t("publicationLibrary.notInLibraryTab")}<b>{discoveredNeedsImport.length}</b></button>
                  <button aria-selected={discoveryView === "IMPORTED"} className={discoveryView === "IMPORTED" ? "is-active" : ""} onClick={() => { setDiscoveryView("IMPORTED"); setSelectedDiscoveryReelId(discoveredImported[0]?.reel_id ?? null); }} role="tab" type="button">{t("publicationLibrary.inLibraryTab")}<b>{discoveredImported.length}</b></button>
                </div>
              )}
            </div>

            <div className="publication-library-desk">
              {workspaceMode === "DISCOVERED" ? (
                <>
                  <section className="publication-library-worklist" aria-label={t("publicationLibrary.discovered")}>
                    {discoveredVisible.length === 0 ? (
                      <p className="publication-library-discovery-empty">{discoveryView === "PENDING" ? t("publicationLibrary.noPendingImports") : t("publicationLibrary.noImportedReels")}</p>
                    ) : discoveredVisible.map((item) => {
                      const importState = discoveryImportState(item);
                      const isSelected = (selectedDiscovery?.reel_id ?? null) === item.reel_id;
                      return (
                        <button className={`publication-library-worklist-row is-${importState.toLowerCase()}${isSelected ? " is-selected" : ""}`} key={item.reel_id} onClick={() => setSelectedDiscoveryReelId(item.reel_id)} type="button">
                          <span className="publication-library-worklist-thumb">{item.thumbnail_url ? <img alt="" src={item.thumbnail_url} /> : <span className="publication-library-thumb-placeholder">Reel</span>}</span>
                          <span className="publication-library-worklist-copy">
                            <b>{shortText(item.description, 72)}</b>
                            <small>{item.reel_id}</small>
                            <time>{formatDateTime(item.created_time)}</time>
                          </span>
                          <span aria-live="polite" className={`publication-library-reel-status is-${importState.toLowerCase()}`}><i aria-hidden="true" />{discoveryStateLabel(importState)}</span>
                        </button>
                      );
                    })}
                    {nextCursor ? <footer className="publication-library-worklist-footer"><AsyncButton pending={busy === "load-more"} onClick={() => void syncReels(nextCursor)}>{t("publicationLibrary.loadMore")}</AsyncButton>{failedImportCount > 0 ? <em>{t("publicationLibrary.failedImportCount").replace("{count}", String(failedImportCount))}</em> : null}</footer> : null}
                  </section>
                  <aside className="publication-library-focus">
                    {!selectedDiscovery ? (
                      <div className="publication-library-empty-inspector"><span className="publication-library-empty-inspector__mark" aria-hidden="true"><PublicationLibraryIcon kind="sync" /></span><strong>{t("publicationLibrary.selectPublication")}</strong><small>{t("publicationLibrary.discoveredHint")}</small></div>
                    ) : (
                      <>
                        <header className="publication-library-focus-preview">
                          <span className="publication-library-focus-thumb">{selectedDiscovery.thumbnail_url ? <img alt="" src={selectedDiscovery.thumbnail_url} /> : <span className="publication-library-thumb-placeholder">Reel</span>}</span>
                          <div>
                            <strong>{shortText(selectedDiscovery.description, 140)}</strong>
                            <small>{selectedDiscovery.reel_id}</small>
                            <time>{formatDateTime(selectedDiscovery.created_time)}</time>
                          </div>
                          {selectedDiscovery.permalink_url ? <a href={selectedDiscovery.permalink_url} rel="noreferrer" target="_blank"><PublicationLibraryIcon kind="external" />{t("publicationLibrary.openFacebook")}</a> : null}
                        </header>
                        <div className="publication-library-focus-import">
                          <span aria-live="polite" className={`publication-library-reel-status is-${discoveryImportState(selectedDiscovery).toLowerCase()}`}><i aria-hidden="true" />{discoveryStateLabel(discoveryImportState(selectedDiscovery))}</span>
                          {importErrors[selectedDiscovery.reel_id] ? <small className="publication-library-reel-error" title={importErrors[selectedDiscovery.reel_id]}>{importErrors[selectedDiscovery.reel_id]}</small> : null}
                          <AsyncButton className="publication-library-import-action primary" disabled={selectedDiscovery.already_imported || Boolean(busy?.startsWith("import-") && busy !== `import-${selectedDiscovery.reel_id}`)} pending={busy === `import-${selectedDiscovery.reel_id}`} pendingLabel={t("publicationLibrary.importingState")} onClick={() => void importReel(selectedDiscovery)}>{selectedDiscovery.already_imported ? t("publicationLibrary.importedState") : importErrors[selectedDiscovery.reel_id] ? t("publicationLibrary.retryImport") : t("publicationLibrary.import")}</AsyncButton>
                        </div>
                      </>
                    )}
                  </aside>
                </>
              ) : publications.length === 0 ? (
                <section className="publication-library-empty-desk" aria-label={t("publicationLibrary.emptyStageTitle")}>
                  <div className="publication-library-empty-desk__guide">
                    <span className="publication-library-empty-desk__eyebrow">{t("publicationLibrary.emptyEyebrow")}</span>
                    <strong>{t("publicationLibrary.emptyStageTitle")}</strong>
                    <p>{t("publicationLibrary.emptyStageHint")}</p>
                    <ol className="publication-library-empty-desk__steps">
                      <li className={accountId ? "is-done" : "is-current"}><b>1</b><span>{t("publicationLibrary.emptyGuideStepPage")}</span></li>
                      <li className={accountId ? "is-current" : ""}><b>2</b><span>{t("publicationLibrary.emptyGuideStepSync")}</span></li>
                      <li><b>3</b><span>{t("publicationLibrary.emptyGuideStepReview")}</span></li>
                    </ol>
                  </div>
                  <div className="publication-library-empty-desk__ghost" aria-hidden="true">
                    <div className="publication-library-empty-desk__ghost-list">
                      <span className="publication-library-empty-desk__ghost-label">{t("publicationLibrary.libraryMode")}</span>
                      <div className="publication-library-empty-desk__ghost-row is-accent"><i /><span /><em /></div>
                      <div className="publication-library-empty-desk__ghost-row"><i /><span /><em /></div>
                      <div className="publication-library-empty-desk__ghost-row"><i /><span /><em /></div>
                    </div>
                    <div className="publication-library-empty-desk__ghost-focus">
                      <span className="publication-library-empty-desk__ghost-label">{t("publicationLibrary.emptyGhostFocus")}</span>
                      <div className="publication-library-empty-desk__ghost-preview" />
                      <div className="publication-library-empty-desk__ghost-lines"><span /><span /><span /></div>
                    </div>
                  </div>
                </section>
              ) : (
                <>
                  <section className="publication-library-worklist" aria-label={libraryTitle}>
                    {filteredPublications.length === 0 ? (
                      <p className="publication-library-no-results">{t("publicationLibrary.noFilterResults")}</p>
                    ) : filteredPublications.map((publication) => {
                      const publicationTracked = Boolean(publication.metadata_json?.last_metric_collection_at);
                      const thumb = publicationThumbnail(publication);
                      const isSelected = selected?.id === publication.id;
                      return (
                        <button aria-busy={busy === `inspect-${publication.id}` || undefined} className={`publication-library-worklist-row is-lean${isSelected ? " is-selected" : ""}`} key={publication.id} onClick={() => void openPublication(publication)} type="button">
                          <span className="publication-library-worklist-thumb">{thumb ? <img alt="" src={thumb} /> : <span className="publication-library-thumb-placeholder">Reel</span>}</span>
                          <span className="publication-library-worklist-copy">
                            <b>{shortText(publicationCaption(publication), 72)}</b>
                            <span className="publication-library-worklist-meta">
                              <small>{accountById.get(publication.platform_account_id)?.display_name ?? publication.platform}</small>
                              <time>{formatDateTime(publication.published_at)}</time>
                              <em className={`publication-library-origin is-${publication.origin.toLowerCase()}`}>{publication.origin.replaceAll("_", " ")}</em>
                            </span>
                          </span>
                          <span className="publication-library-worklist-status">
                            <b className={`is-${publication.status.toLowerCase()}`}>{publication.status.replaceAll("_", " ")}</b>
                            <small className={publication.publish_draft_id ? "is-linked" : "is-unlinked"}>{publication.publish_draft_id ? t("publicationLibrary.linkedState") : t("publicationLibrary.unlinkedState")}</small>
                            <small className={publicationTracked ? "is-tracked" : "is-untracked"}>{publicationTracked ? t("publicationLibrary.trackedState") : t("publicationLibrary.notTrackedState")}</small>
                          </span>
                        </button>
                      );
                    })}
                  </section>

                  <aside aria-busy={Boolean(busy?.startsWith("inspect-")) || undefined} className="publication-library-focus publication-library-inspector">
                    {insightsJob ? <div aria-live="polite" className={`publication-library-job-status is-${insightsQueueDelayed ? "delayed" : insightsJob.status.toLowerCase()}`} role="status"><i aria-hidden="true" /><div><strong>{insightsQueueDelayed ? t("publicationLibrary.collectionWorkerDelayed") : insightsJob.status === "COMPLETED" && growth?.velocity_status === "BASELINE_ONLY" ? t("publicationLibrary.baselineSaved") : t(`publicationLibrary.collectionStatus.${insightsJob.status}`)}</strong><small>{t("publicationLibrary.collectionJobProgress").replace("{id}", insightsJob.id.slice(0, 8)).replace("{progress}", String(insightsJob.progress_percent))}</small>{insightsQueueDelayed ? <small className="publication-library-job-warning">{t("publicationLibrary.collectionWorkerDelayedDetail")}</small> : null}{insightsJob.error_message ? <small className="publication-library-job-error">{insightsJob.error_message}</small> : null}</div></div> : null}
                    {!selected ? (
                      <div className="publication-library-empty-inspector"><span className="publication-library-empty-inspector__mark" aria-hidden="true"><PublicationLibraryIcon kind="library" /></span><strong>{t("publicationLibrary.selectPublication")}</strong><small>{t("publicationLibrary.selectPublicationHint")}</small></div>
                    ) : (
                      <>
                        <header className="publication-library-focus-preview publication-library-inspector-head">
                          <span className="publication-library-focus-thumb publication-library-inspector-thumb">{publicationThumbnail(selected) ? <img alt="" src={publicationThumbnail(selected) ?? ""} /> : "Reel"}</span>
                          <div><span>{selected.origin.replaceAll("_", " ")}<i className={`is-${selected.status.toLowerCase()}`}>{selected.status.replaceAll("_", " ")}</i></span><strong>{shortText(publicationCaption(selected), 140)}</strong><small>{selected.external_reel_id}</small></div>
                          {selected.external_permalink ? <a href={selected.external_permalink} rel="noreferrer" target="_blank"><PublicationLibraryIcon kind="external" />{t("publicationLibrary.openFacebook")}</a> : null}
                        </header>
                        <nav aria-label={t("publicationLibrary.inspectorTabsLabel")} className="publication-library-inspector-tabs" role="tablist">
                          <button aria-selected={inspectorTab === "OVERVIEW"} className={inspectorTab === "OVERVIEW" ? "is-active" : ""} onClick={() => setInspectorTab("OVERVIEW")} role="tab" type="button">{t("publicationLibrary.inspectorOverview")}</button>
                          <button aria-selected={inspectorTab === "INSIGHTS"} className={inspectorTab === "INSIGHTS" ? "is-active" : ""} onClick={() => setInspectorTab("INSIGHTS")} role="tab" type="button">{t("publicationLibrary.inspectorInsights")}</button>
                          <button aria-selected={inspectorTab === "TRACKING"} className={inspectorTab === "TRACKING" ? "is-active" : ""} onClick={() => setInspectorTab("TRACKING")} role="tab" type="button">{t("publicationLibrary.inspectorTracking")}</button>
                          <button aria-selected={inspectorTab === "CLASSIFY"} className={inspectorTab === "CLASSIFY" ? "is-active" : ""} onClick={() => setInspectorTab("CLASSIFY")} role="tab" type="button">{t("publicationLibrary.inspectorClassify")}</button>
                        </nav>

                        {inspectorTab === "OVERVIEW" ? (
                          <>
                            <dl className="publication-library-inspector-facts"><div><dt>{t("publicationLibrary.page")}</dt><dd>{accountById.get(selected.platform_account_id)?.display_name ?? selected.platform}</dd></div><div><dt>{t("publicationLibrary.publicationStatus")}</dt><dd className={`is-${selected.status.toLowerCase()}`}>{selected.status.replaceAll("_", " ")}</dd></div><div><dt>{t("publicationLibrary.published")}</dt><dd>{formatDateTime(selected.published_at)}</dd></div><div><dt>{t("publicationLibrary.lastSynced")}</dt><dd>{selected.last_synced_at ? formatDateTime(selected.last_synced_at) : t("publicationLibrary.neverSynced")}</dd></div><div><dt>{t("publicationLibrary.nativePlacement")}</dt><dd>{selected.native_product_placement_status.replaceAll("_", " ")}</dd></div><div><dt>{t("publicationLibrary.affiliateComment")}</dt><dd>{selected.affiliate_comment_status.replaceAll("_", " ")}</dd></div></dl>
                            <section className="publication-library-link"><div><strong>{t("publicationLibrary.draftLink")}</strong><small>{selected.publish_draft_id ? t("publicationLibrary.draftLinked") : t("publicationLibrary.draftLinkHint")}</small></div><select disabled={Boolean(selected.publish_draft_id)} value={selectedDraftId} onChange={(event) => setSelectedDraftId(event.target.value)}><option value="">{t("publicationLibrary.selectDraft")}</option>{drafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.title || draft.id.slice(0, 8)} · {draft.status}</option>)}</select><AsyncButton disabled={Boolean(selected.publish_draft_id) || !selectedDraftId} pending={busy === "link-draft"} onClick={() => void linkDraft()}>{t("publicationLibrary.linkDraft")}</AsyncButton></section>
                          </>
                        ) : null}

                        {inspectorTab === "INSIGHTS" ? (
                          <>
                            <section className="publication-library-growth"><header><div><strong>{t("publicationLibrary.insights")}</strong><small>{t("publicationLibrary.insightsHint")}</small></div><span>{growth?.trend_label ?? "NO DATA"} · {t("publicationLibrary.snapshotCount").replace("{count}", String(growth?.snapshot_count ?? snapshots.length))}</span></header><div className="publication-library-metrics"><div><span>{t("publicationLibrary.views")}</span><b>{metric(growth?.latest_view_count)}</b></div><div><span>{t("publicationLibrary.viewsPerHour")}</span><b>{metric(growth?.recent_views_per_hour)}</b></div><div><span>{t("publicationLibrary.engagement")}</span><b>{growth?.latest_engagement_rate_percent == null ? "—" : `${growth.latest_engagement_rate_percent.toFixed(2)}%`}</b></div><div><span>{t("publicationLibrary.likes")}</span><b>{metric(growth?.latest_like_count)}</b></div><div><span>{t("publicationLibrary.comments")}</span><b>{metric(growth?.latest_comment_count)}</b></div><div><span>{t("publicationLibrary.shares")}</span><b>{metric(growth?.latest_share_count)}</b></div></div><div className="publication-library-insights-actions"><AsyncButton pending={busy === "preflight"} onClick={() => void runPreflight()}>{t("publicationLibrary.checkInsights")}</AsyncButton>{preflight ? <span className={preflight.ready_for_live_job ? "is-ready" : "is-blocked"}>{preflight.ready_for_live_job ? t("publicationLibrary.insightsReady") : t("publicationLibrary.insightsBlocked")}</span> : null}</div>{preflight ? <section className={`publication-library-preflight-result ${preflight.ready_for_live_job ? "is-ready" : "is-blocked"}`}><header><span aria-hidden="true">{preflight.ready_for_live_job ? "✓" : "!"}</span><div><strong>{preflight.ready_for_live_job ? t("publicationLibrary.readinessPassedTitle") : t("publicationLibrary.readinessBlockedTitle")}</strong><small>{preflight.ready_for_live_job ? t("publicationLibrary.readinessPassedDetail") : t("publicationLibrary.readinessBlockedDetail").replace("{count}", String(failedPreflightChecks.length))}</small></div></header>{failedPreflightChecks.length > 0 ? <ul>{failedPreflightChecks.map((check) => <li key={check.code}><span aria-hidden="true">!</span><div><b>{check.code.replaceAll("_", " ")}</b><small>{check.message}</small></div></li>)}</ul> : null}</section> : null}{preflight?.ready_for_live_job ? <label className="publication-library-authorize"><input checked={authorizeNetwork} onChange={(event) => setAuthorizeNetwork(event.target.checked)} type="checkbox" /><span>{t("publicationLibrary.authorizeRead")}</span><AsyncButton className="primary" disabled={!authorizeNetwork} pending={busy === "collect"} onClick={() => void collectInsights()}>{t("publicationLibrary.collectOnce")}</AsyncButton></label> : null}</section>
                            {growth && growth.velocity_status !== "STABLE" ? <div className={`publication-library-velocity-guidance is-${growth.velocity_status.toLowerCase()}`}><strong>{t(`publicationLibrary.velocityStatus.${growth.velocity_status}`)}</strong><small>{growth.velocity_status === "NO_DATA" ? t("publicationLibrary.velocityNoDataDetail") : growth.velocity_status === "COUNTER_REGRESSION" ? t("publicationLibrary.velocityRegressionDetail") : t("publicationLibrary.velocityWaitingDetail").replace("{minutes}", String(Math.ceil(growth.minimum_velocity_interval_seconds / 60))).replace("{time}", growth.next_stable_measurement_at ? formatDateTime(growth.next_stable_measurement_at) : "—")}</small>{growth.latest_data_quality === "PARTIAL" ? <small className="publication-library-data-quality-note">{t("publicationLibrary.partialEngagementDetail")}</small> : null}</div> : null}
                          </>
                        ) : null}

                        {inspectorTab === "TRACKING" ? (
                          <section className={`publication-library-tracking is-${trackingStatus.toLowerCase()}`}>
                            <header><div><strong>{t("publicationLibrary.autoTracking")}</strong><small>{t("publicationLibrary.autoTrackingHint")}</small></div><span>{t(`publicationLibrary.trackingStatus.${trackingStatus}`)}</span></header>
                            {metricSchedule && ["ACTIVE", "PAUSED"].includes(metricSchedule.status) ? <>
                              <div className="publication-library-tracking-facts"><div><span>{t("publicationLibrary.nextCollection")}</span><b>{metricSchedule.next_collection_at ? formatDateTime(metricSchedule.next_collection_at) : "—"}</b></div><div><span>{t("publicationLibrary.lastCollection")}</span><b>{metricSchedule.last_completed_at ? formatDateTime(metricSchedule.last_completed_at) : t("publicationLibrary.notCollectedYet")}</b></div><div><span>{t("publicationLibrary.trackingEnds")}</span><b>{metricSchedule.tracking_ends_at ? formatDateTime(metricSchedule.tracking_ends_at) : "—"}</b></div></div>
                              <footer><small>{trackingDecisionReason ?? t("publicationLibrary.adaptiveCadence")}</small>{metricSchedule.status === "ACTIVE" ? <AsyncButton pending={busy === "tracking-pause"} onClick={() => void pauseTracking()}>{t("publicationLibrary.pauseTracking")}</AsyncButton> : <AsyncButton className="primary" pending={busy === "tracking-resume"} onClick={() => void resumeTracking()}>{t("publicationLibrary.resumeTracking")}</AsyncButton>}</footer>
                            </> : <>
                              {metricSchedule?.status === "BLOCKED" && trackingDecisionReason ? <div className="publication-library-tracking-warning">{trackingDecisionReason}</div> : null}
                              <label className="publication-library-tracking-consent"><input checked={authorizeTracking} onChange={(event) => setAuthorizeTracking(event.target.checked)} type="checkbox" /><span>{t("publicationLibrary.authorizeTracking")}</span></label>
                              <div className="publication-library-tracking-enable"><label><span>{t("publicationLibrary.trackingWindow")}</span><select value={trackingDurationHours} onChange={(event) => setTrackingDurationHours(Number(event.target.value))}><option value={24}>{t("publicationLibrary.tracking24h")}</option><option value={72}>{t("publicationLibrary.tracking72h")}</option><option value={168}>{t("publicationLibrary.tracking7d")}</option></select></label><AsyncButton className="primary" disabled={!preflight?.ready_for_live_job || !authorizeTracking} pending={busy === "tracking-enable"} onClick={() => void enableTracking()}>{metricSchedule ? t("publicationLibrary.restartTracking") : t("publicationLibrary.enableTracking")}</AsyncButton></div>
                              {!preflight?.ready_for_live_job ? (
                                <div className="publication-library-tracking-readiness">
                                  <small>{t("publicationLibrary.trackingReadinessRequired")}</small>
                                  <AsyncButton pending={busy === "preflight"} onClick={() => void runPreflight()}>{t("publicationLibrary.checkInsights")}</AsyncButton>
                                </div>
                              ) : null}
                            </>}
                          </section>
                        ) : null}

                        {inspectorTab === "CLASSIFY" ? <PublicationClassificationPanel publicationId={selected.id} /> : null}
                      </>
                    )}
                  </aside>
                </>
              )}
            </div>
          </section>
        )}
      </main>
    </OperatorStudioShell>
  );
}
