import { strict as assert } from "node:assert";
import {
  capHarvestUpdatedToBackendAuthority,
  resolveBackendCollectAuthorityFromState,
  resolveBackendCapturedCountFromState,
  resolveHybridBackendAlignedGapFromState,
  resolveCaptureInboxSummaryCollectGap,
  resolveBackendPriorAlreadyForLiveCollect,
  resolveOperatorSkipQueueAuthority,
  resolveScannedTotalFromState
} from "./wholeProfileHarvest/backendCollectAuthority.js";
import { resolveHybridProfileCollectRemaining } from "./wholeProfileHarvest/controller.js";
import { createWholeProfileHarvestIdleState } from "./wholeProfileHarvest/state.js";

const base = createWholeProfileHarvestIdleState(new Date().toISOString());
const state = {
  ...base,
  post_scan_counter_snapshot: {
    status: "applied" as const,
    source: "backend_capture_inbox_profile_summary" as const,
    profile_identifier: "test",
    scanned_total: 734,
    backend_captured: 500,
    backend_ready: 500,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 500,
    incomplete: 0,
    need_retry: 0,
    new: 234,
    queue: 234,
    backend_captured_aweme_ids: [],
    applied_at: new Date().toISOString()
  },
  harvest: { ...base.harvest, updated: 734, planned_total: 734 },
  scan_job: { ...base.scan_job, total_persisted: 734 }
};

assert.equal(resolveBackendCapturedCountFromState(state), 500);
assert.equal(resolveBackendPriorAlreadyForLiveCollect(state), 500);
assert.equal(capHarvestUpdatedToBackendAuthority(734, resolveBackendCollectAuthorityFromState(state)), 500);
const authority = resolveBackendCollectAuthorityFromState(state);
assert.equal(authority.remaining, 234);
assert.equal(authority.scannedTotal, 734);

const inflatedQueueState = {
  ...state,
  post_scan_counter_snapshot: {
    ...state.post_scan_counter_snapshot!,
    new: 237,
    queue: 734
  },
  harvest: { ...state.harvest, pending: 237 }
};
assert.equal(resolveOperatorSkipQueueAuthority(inflatedQueueState), 237);

const tailInflatedNewState = {
  ...state,
  post_scan_counter_snapshot: {
    ...state.post_scan_counter_snapshot!,
    scanned_total: 1000,
    backend_captured: 998,
    already_collected: 998,
    new: 6,
    queue: 6
  }
};
assert.equal(resolveHybridProfileCollectRemaining(tailInflatedNewState, 0), 2, "remaining must follow backend gap, not inflated snapshot.new");

const tailStaleQueueNewState = {
  ...state,
  classification: {
    ...base.classification,
    status: "success" as const,
    total_candidates: 739
  },
  profile_scan: {
    ...base.profile_scan,
    accepted_target_count: 739,
    target_details: Array.from({ length: 739 }, (_, index) => ({
      aweme_id: `7330000000000${String(index).padStart(3, "0")}`,
      source_url: `https://www.douyin.com/video/7330000000000${String(index).padStart(3, "0")}`,
      thumbnail_url: null,
      caption: null,
      capture_status: "new" as const,
      backend_item: null
    }))
  },
  post_scan_counter_snapshot: {
    ...state.post_scan_counter_snapshot!,
    scanned_total: 735,
    backend_captured: 736,
    already_collected: 736,
    new: 236,
    queue: 236
  }
};
assert.equal(
  resolveHybridProfileCollectRemaining(tailStaleQueueNewState, 236),
  3,
  "tail gap must trust scan authority minus backend captured, not stale snapshot.new queue"
);

const staleBackendCapturedState = {
  ...tailStaleQueueNewState,
  post_scan_counter_snapshot: {
    ...tailStaleQueueNewState.post_scan_counter_snapshot!,
    status: "fallback" as const,
    backend_captured: 500,
    already_collected: 736,
    new: 236,
    queue: 236
  }
};
assert.equal(resolveBackendCapturedCountFromState(staleBackendCapturedState), 736, "fallback snapshot must still expose backend captured");
assert.equal(resolveHybridBackendAlignedGapFromState(staleBackendCapturedState), 3);
assert.equal(resolveHybridProfileCollectRemaining(staleBackendCapturedState, 236), 3);

assert.equal(
  resolveCaptureInboxSummaryCollectGap(735, { captured: 736, totalCount: 739, needsAction: 0, failed: 0 }),
  3,
  "profile-summary totalCount must reveal tail gap when local scanned_total lags behind inbox captured"
);

const scanAuthorityWinsState = {
  ...base,
  classification: {
    ...base.classification,
    status: "success" as const,
    total_candidates: 738
  },
  profile_scan: {
    ...base.profile_scan,
    accepted_target_count: 738,
    target_details: Array.from({ length: 738 }, (_, index) => ({
      aweme_id: `id-${index}`,
      source_url: `https://www.douyin.com/video/id-${index}`,
      thumbnail_url: null,
      caption: null,
      capture_status: "new" as const,
      backend_item: null
    }))
  },
  post_scan_counter_snapshot: {
    status: "applied" as const,
    source: "backend_capture_inbox_profile_summary" as const,
    profile_identifier: "test",
    scanned_total: 735,
    backend_captured: 500,
    backend_ready: 500,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 500,
    incomplete: 0,
    need_retry: 0,
    new: 238,
    queue: 238,
    backend_captured_aweme_ids: [],
    applied_at: new Date().toISOString()
  }
};
assert.equal(resolveScannedTotalFromState(scanAuthorityWinsState), 738, "scan/classification authority must beat inbox-scanned_total 735");

const displayedProfileWinsState = {
  ...base,
  classification: {
    ...base.classification,
    status: "success" as const,
    total_candidates: 735
  },
  profile_scan: {
    ...base.profile_scan,
    status: "success" as const,
    accepted_target_count: 735,
    diagnostics: {
      displayed_profile_count: 738,
      expected_profile_video_count: 738,
      scan_profile_total_authority_peak: 738
    }
  },
  scan_job: {
    ...base.scan_job,
    expected_count: 738,
    total_persisted: 735
  },
  post_scan_counter_snapshot: {
    status: "applied" as const,
    source: "backend_capture_inbox_profile_summary" as const,
    profile_identifier: "test",
    scanned_total: 735,
    backend_captured: 50,
    backend_ready: 50,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 50,
    incomplete: 0,
    need_retry: 0,
    new: 685,
    queue: 685,
    backend_captured_aweme_ids: [],
    applied_at: new Date().toISOString()
  }
};
assert.equal(resolveScannedTotalFromState(displayedProfileWinsState), 738, "Douyin displayed profile count must beat inbox-scanned_total 735 during collect");

const stalePeakOverPersistedState = {
  ...base,
  classification: {
    ...base.classification,
    status: "success" as const,
    total_candidates: 3303
  },
  profile_scan: {
    ...base.profile_scan,
    status: "success" as const,
    accepted_target_count: 3303,
    diagnostics: {
      displayed_profile_count: 3303,
      scan_profile_total_authority_peak: 3381,
      queue_total_persisted: 3303,
      scan_job_total_persisted: 3303,
      count_semantics_status: "completed_with_api_over_displayed_count",
      over_displayed_count: 78
    }
  },
  scan_job: {
    ...base.scan_job,
    status: "completed" as const,
    expected_count: 3303,
    total_persisted: 3303
  },
  post_scan_counter_snapshot: {
    status: "applied" as const,
    source: "backend_capture_inbox_profile_summary" as const,
    profile_identifier: "test",
    scanned_total: 3303,
    backend_captured: 900,
    backend_ready: 900,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 900,
    incomplete: 0,
    need_retry: 0,
    new: 2403,
    queue: 2403,
    backend_captured_aweme_ids: [],
    applied_at: new Date().toISOString()
  }
};
assert.equal(
  resolveScannedTotalFromState(stalePeakOverPersistedState),
  3303,
  "finalized persisted queue must beat stale scan_profile_total_authority_peak for collect progress"
);

console.info("backendCollectAuthority.test.ts: PASS");
