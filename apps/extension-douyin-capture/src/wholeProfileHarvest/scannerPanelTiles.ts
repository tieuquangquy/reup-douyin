import { partialCollectTileCounts } from "./profileContext.js";
import type { WholeProfileHarvestState } from "./state.js";

export function scanDiagnosticsLargeProfileMode(state: WholeProfileHarvestState): boolean {
  const profile = state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object"
    ? state.profile_scan.diagnostics as Record<string, unknown>
    : {};
  const verify = state.verify.diagnostics && typeof state.verify.diagnostics === "object"
    ? state.verify.diagnostics as Record<string, unknown>
    : {};
  return profile.large_profile_mode === "yes" || verify.large_profile_mode === "yes";
}

/** Large-profile scans persist more rows than the visible preview window — tiles use persisted total. */
export function shouldApplyLargeProfilePersistedTileCounts(options: {
  largeProfilePersistedTotal: number | null;
  presentationBlocked: boolean;
  largeProfileMode: boolean;
  popupMetricsAuthoritative: boolean;
  persistedTotalHasNewerAuthority: boolean;
  displayedProfileCollectLimit?: number | null;
}): boolean {
  if (options.displayedProfileCollectLimit != null && options.displayedProfileCollectLimit > 0) return false;
  if (options.largeProfilePersistedTotal == null || options.presentationBlocked) return false;
  return options.largeProfileMode
    || !options.popupMetricsAuthoritative
    || options.persistedTotalHasNewerAuthority;
}

export function resolveLargeProfileTileCounts(
  persistedTotal: number,
  alreadyCollected: number,
  largeProfileMode: boolean
): { newCount: number; queueCount: number } {
  if (largeProfileMode) {
    return { newCount: persistedTotal, queueCount: persistedTotal };
  }
  return partialCollectTileCounts(persistedTotal, alreadyCollected);
}

export function applyLargeProfilePersistedScannerPanelTiles(
  viewModel: { counts: { newCount: number; queueCount: number; alreadyCollectedCount: number } },
  options: {
    largeProfilePersistedTotal: number | null;
    presentationBlocked: boolean;
    largeProfileMode: boolean;
    popupMetricsAuthoritative: boolean;
    persistedTotalHasNewerAuthority: boolean;
    displayedProfileCollectLimit?: number | null;
  }
): void {
  if (!shouldApplyLargeProfilePersistedTileCounts(options)) return;
  const tiles = resolveLargeProfileTileCounts(
    options.largeProfilePersistedTotal!,
    viewModel.counts.alreadyCollectedCount,
    options.largeProfileMode
  );
  viewModel.counts.newCount = tiles.newCount;
  viewModel.counts.queueCount = tiles.queueCount;
}
