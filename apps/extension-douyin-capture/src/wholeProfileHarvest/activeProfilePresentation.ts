import {
  activeProfileInboxHasActionableWork,
  activeProfileInboxSummaryIsComplete,
  activeProfileInboxSummaryIsResumeEligible,
  detectProfileContextMismatch,
  partialCollectTileCounts,
  profileContextCollectableRemaining,
  profileContextHeaderStatus,
  profileContextInboxReviewCount,
  type ActiveProfileInboxSummary
} from "./profileContext.js";
import { detectCurrentDouyinProfileIdentity } from "./profileResolver.js";
import {
  COLLECTED_REPOSITORY_STATUSES,
  profileIdentifierFromUrl,
  type ProfileTargetStatusCount
} from "./profileTargetRepository.js";
import type { WholeProfileHarvestState } from "./state.js";

const ACTIONABLE_REPOSITORY_STATUSES = [
  "new",
  "pending",
  "processing",
  "retry",
  "incomplete",
  "needs_metadata",
  "failed_recoverable"
] as const;

const FAILED_REPOSITORY_STATUSES = ["failed", "failed_permanent", "failed_recoverable"] as const;

export type ActiveProfileRepositorySnapshot = {
  profile_identifier: string;
  total_targets: number;
  scanned_total: number;
  actionable_count: number;
  collected_in_repo: number;
  failed_count: number;
  degraded: boolean;
  degraded_reason: string | null;
};

export type ActiveProfilePresentationMode = "global_aligned" | "revisit_mismatch";

export type ActiveProfilePresentationSource =
  | "global"
  | "repository+inbox"
  | "repository"
  | "inbox"
  | "session_index";

export type ActiveProfilePresentation = {
  mode: ActiveProfilePresentationMode;
  profile_identifier: string;
  canonical_profile_url: string;
  scanned_total: number;
  already_collected: number;
  new_count: number;
  queue_count: number;
  incomplete_count: number;
  failed_count: number;
  has_prior_scan: boolean;
  header_status: string;
  primary_label: string;
  primary_title: string;
  primary_description: string;
  presentation_source: ActiveProfilePresentationSource;
};

export type ProfileSessionIndexEntry = {
  profile_identifier: string;
  canonical_profile_url: string;
  last_scan_at: string | null;
  last_scan_job_id: string | null;
  scanned_total: number;
  last_presented_at: string;
};

export function profileStatusCountValue(
  counts: ProfileTargetStatusCount[],
  statuses: readonly string[]
): number {
  const statusSet = new Set(statuses);
  return counts.reduce((sum, item) => sum + (statusSet.has(item.status) ? item.count : 0), 0);
}

export function buildActiveProfileRepositorySnapshot(
  profileIdentifier: string,
  result: {
    total: number;
    counts: ProfileTargetStatusCount[];
    degraded: boolean;
    degraded_reason: string | null;
  }
): ActiveProfileRepositorySnapshot {
  const actionable = profileStatusCountValue(result.counts, ACTIONABLE_REPOSITORY_STATUSES);
  const collected = profileStatusCountValue(result.counts, COLLECTED_REPOSITORY_STATUSES);
  const failed = profileStatusCountValue(result.counts, FAILED_REPOSITORY_STATUSES);
  const total = Math.max(0, Math.round(result.total));
  return {
    profile_identifier: profileIdentifier,
    total_targets: total,
    scanned_total: total,
    actionable_count: actionable,
    collected_in_repo: collected,
    failed_count: failed,
    degraded: result.degraded,
    degraded_reason: result.degraded_reason
  };
}

export function activeProfileRevisitHasEvidence(args: {
  inbox: ActiveProfileInboxSummary | null | undefined;
  repository: ActiveProfileRepositorySnapshot | null | undefined;
  sessionEntry: ProfileSessionIndexEntry | null | undefined;
}): boolean {
  if (args.repository && args.repository.total_targets > 0) return true;
  if (args.sessionEntry && args.sessionEntry.scanned_total > 0) return true;
  if (!args.inbox?.trusted) return false;
  return args.inbox.already_collected > 0
    || args.inbox.captured_total > 0
    || activeProfileInboxHasActionableWork(args.inbox);
}

export function resolveActiveProfileCanonicalUrl(activeTabUrl: string | null | undefined): string | null {
  if (typeof activeTabUrl !== "string" || !activeTabUrl.trim()) return null;
  const identity = detectCurrentDouyinProfileIdentity(activeTabUrl.trim(), null);
  return identity.canonical_profile_url?.replace(/\/+$/, "") ?? activeTabUrl.trim().replace(/\/+$/, "");
}

export function isActiveProfileSessionAligned(
  state: WholeProfileHarvestState,
  activeTabUrl: string | null | undefined
): boolean {
  const canonical = resolveActiveProfileCanonicalUrl(activeTabUrl);
  if (!canonical) return false;
  return !detectProfileContextMismatch(state, canonical);
}

export function buildActiveProfileScannerCounts(presentation: ActiveProfilePresentation): {
  newCount: number;
  incompleteCount: number;
  alreadyCollectedCount: number;
  queueCount: number;
  collectedCount: number;
  savedCount: number;
  failedCount: number;
} {
  return {
    newCount: presentation.new_count,
    incompleteCount: presentation.incomplete_count,
    alreadyCollectedCount: presentation.already_collected,
    queueCount: presentation.queue_count,
    collectedCount: presentation.already_collected,
    savedCount: presentation.already_collected,
    failedCount: presentation.failed_count
  };
}

function buildPresentationHeader(args: {
  scannedTotal: number;
  alreadyCollected: number;
  inbox: ActiveProfileInboxSummary | null;
  hasPriorScan: boolean;
}): string {
  if (args.inbox?.trusted && args.alreadyCollected > 0) {
    return profileContextHeaderStatus(args.inbox);
  }
  if (args.hasPriorScan && args.scannedTotal > 0) {
    if (args.alreadyCollected > 0) {
      const left = Math.max(0, args.scannedTotal - args.alreadyCollected);
      return left > 0
        ? `${args.alreadyCollected} collected · ${left} left`
        : `${args.alreadyCollected} collected`;
    }
    return `${args.scannedTotal} videos scanned`;
  }
  if (args.scannedTotal > 0) {
    return `${args.scannedTotal} videos scanned`;
  }
  return "Scan required";
}

export function resolveActiveProfilePresentation(args: {
  state: WholeProfileHarvestState;
  activeTabUrl: string | null | undefined;
  inbox: ActiveProfileInboxSummary | null | undefined;
  repository: ActiveProfileRepositorySnapshot | null | undefined;
  sessionEntry: ProfileSessionIndexEntry | null | undefined;
}): ActiveProfilePresentation | null {
  const canonical = resolveActiveProfileCanonicalUrl(args.activeTabUrl);
  if (!canonical) return null;
  const profileIdentifier = profileIdentifierFromUrl(canonical);
  if (!profileIdentifier) return null;

  if (isActiveProfileSessionAligned(args.state, canonical)) {
    return null;
  }

  const inbox = args.inbox?.trusted ? args.inbox : null;
  const repo = args.repository?.profile_identifier === profileIdentifier ? args.repository : null;
  const session = args.sessionEntry?.profile_identifier === profileIdentifier ? args.sessionEntry : null;
  const scannedTotal = repo && repo.total_targets > 0
    ? repo.scanned_total
    : Math.max(
      session?.scanned_total ?? 0,
      inbox?.total_count ?? 0,
      inbox ? inbox.already_collected + profileContextCollectableRemaining(inbox) : 0
    );
  const hasPriorScan = activeProfileRevisitHasEvidence({ inbox, repository: repo, sessionEntry: session })
    || scannedTotal > 0;
  const alreadyCollected = Math.max(
    inbox?.already_collected ?? 0,
    repo?.collected_in_repo ?? 0
  );
  const inboxComplete = inbox != null && activeProfileInboxSummaryIsComplete(inbox);
  const collectableRemaining = inboxComplete
    ? 0
    : repo && repo.total_targets > 0
      ? Math.max(0, repo.actionable_count)
      : inbox
        ? Math.max(
          profileContextCollectableRemaining(inbox),
          inbox.new_count + inbox.queue_count
        )
        : 0;
  const tileSplit = inboxComplete
    ? { newCount: 0, queueCount: 0 }
    : partialCollectTileCounts(collectableRemaining, alreadyCollected);
  const incompleteCount = inbox ? profileContextInboxReviewCount(inbox) : 0;
  const failedCount = Math.max(inbox?.need_retry_count ?? 0, repo?.failed_count ?? 0);

  let presentationSource: ActiveProfilePresentationSource = "session_index";
  if (repo && repo.total_targets > 0 && inbox && inbox.already_collected > 0) {
    presentationSource = "repository+inbox";
  } else if (repo && repo.total_targets > 0) {
    presentationSource = "repository";
  } else if (inbox && activeProfileInboxSummaryIsResumeEligible(inbox)) {
    presentationSource = "inbox";
  }

  const headerStatus = buildPresentationHeader({
    scannedTotal,
    alreadyCollected,
    inbox,
    hasPriorScan
  });

  let primaryLabel: string;
  let primaryTitle: string;
  let primaryDescription: string;
  if (inboxComplete) {
    primaryLabel = "Open Capture Inbox";
    primaryTitle = "Collection complete";
    primaryDescription = `${alreadyCollected} videos are ready in Capture Inbox for this creator.`;
  } else if (hasPriorScan) {
    primaryLabel = "Rescan profile";
    primaryTitle = "Rescan profile";
    primaryDescription = `Previously scanned on this creator (${scannedTotal || alreadyCollected} known). Rescan to refresh the collection plan.`;
  } else {
    primaryLabel = "Scan this profile";
    primaryTitle = "Scan this profile";
    primaryDescription = "Scan this profile to discover videos and build a collection plan.";
  }

  return {
    mode: "revisit_mismatch",
    profile_identifier: profileIdentifier,
    canonical_profile_url: canonical,
    scanned_total: scannedTotal,
    already_collected: alreadyCollected,
    new_count: tileSplit.newCount,
    queue_count: tileSplit.queueCount,
    incomplete_count: incompleteCount,
    failed_count: failedCount,
    has_prior_scan: hasPriorScan,
    header_status: headerStatus,
    primary_label: primaryLabel,
    primary_title: primaryTitle,
    primary_description: primaryDescription,
    presentation_source: presentationSource
  };
}

export function activeProfileRevisitPresentationActive(
  presentation: ActiveProfilePresentation | null | undefined
): boolean {
  if (presentation?.mode !== "revisit_mismatch") return false;
  return presentation.has_prior_scan === true || presentation.scanned_total > 0;
}
