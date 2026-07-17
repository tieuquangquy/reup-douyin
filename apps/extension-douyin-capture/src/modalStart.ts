import type { IncrementalProfileHarvestMode, SmartCaptureHarvestState } from "./types.js";

export type ResolvedModalProfileUrl = {
  profile_url: string;
  original_modal_aweme_id: string;
  original_modal_url: string;
};

export type ModalProfileResolution = {
  profile_url_without_modal_id: string;
  current_modal_aweme_id: string | null;
  original_modal_url: string;
};

export type ModalHarvestCoverage = {
  modal_aweme_id: string | null;
  profile_url_resolved: string | null;
  capture_session_known: boolean;
  target_queue_known: boolean;
  total_profile_videos: number;
  target_mode: IncrementalProfileHarvestMode;
  target_count: number;
  current_modal_in_target_queue: boolean;
  remaining_targets_after_current: number;
  can_harvest_all: boolean;
  reason_if_no: string | null;
};

export function getProfileUrlFromModalUrl(value: string): ModalProfileResolution | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  const currentModalAwemeId = url.searchParams.get("modal_id")?.trim() || null;
  if (!currentModalAwemeId || !/^\/user\/[^/?#]+/.test(url.pathname)) return null;
  url.searchParams.delete("modal_id");
  url.hash = "";
  const search = url.searchParams.toString();
  return {
    profile_url_without_modal_id: `${url.origin}${url.pathname}${search ? `?${search}` : ""}`,
    current_modal_aweme_id: currentModalAwemeId,
    original_modal_url: value
  };
}

export function resolveProfileUrlFromModalUrl(value: string): ResolvedModalProfileUrl | null {
  const resolution = getProfileUrlFromModalUrl(value);
  if (!resolution?.current_modal_aweme_id) return null;
  return {
    profile_url: resolution.profile_url_without_modal_id,
    original_modal_aweme_id: resolution.current_modal_aweme_id,
    original_modal_url: resolution.original_modal_url
  };
}

export function hasKnownTargetQueue(state: SmartCaptureHarvestState | null | undefined): state is SmartCaptureHarvestState {
  return Boolean(Array.isArray(state?.target_aweme_ids) && state.target_aweme_ids.length > 0);
}

export function buildModalHarvestCoverage(args: {
  modalUrl: string;
  smartState: SmartCaptureHarvestState | null | undefined;
  mode: IncrementalProfileHarvestMode;
  profileResolution?: ModalProfileResolution | null;
  profileCaptureFailedReason?: string | null;
}): ModalHarvestCoverage {
  const resolution = args.profileResolution === undefined ? getProfileUrlFromModalUrl(args.modalUrl) : args.profileResolution;
  const targetQueue = args.smartState?.target_aweme_ids ?? [];
  const modalAwemeId = resolution?.current_modal_aweme_id ?? null;
  const currentIndex = modalAwemeId ? targetQueue.indexOf(modalAwemeId) : -1;
  const targetQueueKnown = targetQueue.length > 0;
  const captureSessionKnown = Boolean(args.smartState?.latest_capture_session_id);
  const totalProfileVideos = args.smartState?.scan_summary?.total_found ?? args.smartState?.captured_item_count ?? targetQueue.length;
  const reason = !resolution
    ? "Active tab is not a Douyin profile modal URL."
    : args.profileCaptureFailedReason
      ? args.profileCaptureFailedReason
      : !targetQueueKnown
        ? "Target queue missing; resolve profile queue first."
        : currentIndex < 0
          ? "Current modal is not in the target queue for the selected mode."
          : null;
  return {
    modal_aweme_id: modalAwemeId,
    profile_url_resolved: resolution?.profile_url_without_modal_id ?? null,
    capture_session_known: captureSessionKnown,
    target_queue_known: targetQueueKnown,
    total_profile_videos: totalProfileVideos,
    target_mode: args.smartState?.harvest_mode ?? args.mode,
    target_count: targetQueue.length,
    current_modal_in_target_queue: currentIndex >= 0,
    remaining_targets_after_current: currentIndex >= 0 ? Math.max(0, targetQueue.length - currentIndex - 1) : targetQueue.length,
    can_harvest_all: Boolean(resolution && targetQueueKnown && currentIndex >= 0 && !args.profileCaptureFailedReason),
    reason_if_no: reason
  };
}

export function formatModalHarvestCoverage(coverage: ModalHarvestCoverage): Record<string, string> {
  return {
    "Modal aweme": coverage.modal_aweme_id ?? "missing",
    "Profile queue": coverage.target_queue_known ? "resolved" : "missing",
    "Profile URL resolved": coverage.profile_url_resolved ?? "missing",
    "Capture session": coverage.capture_session_known ? "known" : "missing",
    "Target queue": coverage.target_queue_known ? "known" : "missing",
    "Total profile videos": String(coverage.total_profile_videos),
    "Target mode": formatHarvestMode(coverage.target_mode),
    "Target count": String(coverage.target_count),
    "Current modal in queue": coverage.current_modal_in_target_queue ? "yes" : "no",
    "Remaining after current": String(coverage.remaining_targets_after_current),
    "Can harvest all": coverage.can_harvest_all ? "yes" : "no",
    Reason: coverage.reason_if_no ?? "none"
  };
}

export function formatHarvestMode(mode: IncrementalProfileHarvestMode): string {
  if (mode === "refresh_all") return "Refresh all";
  if (mode === "new_only") return "New only";
  return "New + incomplete";
}
