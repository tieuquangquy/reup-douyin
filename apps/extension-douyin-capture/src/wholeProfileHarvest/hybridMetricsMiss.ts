import type { WholeProfileHarvestState } from "./state.js";
import { buildProfileCollectContractFromState } from "./profileCollectContract.js";
import { HYBRID_EXACT_GAP_RECOVERY_CAP } from "./hybridBackendGapAwemeIds.js";

function numericDiagnosticValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/** True after a Hybrid collect attempt wrote 0 items because metrics were missing. */
export function hybridLastRunWasMetricsMiss(state: WholeProfileHarvestState): boolean {
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  const outcome = String(summary.hybrid_runner_outcome ?? "");
  const loopPhase = String(summary.hybrid_runner_loop_phase ?? "");
  const readyCount = numericDiagnosticValue(summary.hybrid_runner_flush_ready_count);
  const writeOk = numericDiagnosticValue(summary.hybrid_runner_write_ok_count) ?? 0;
  const pendingSoFar = numericDiagnosticValue(summary.hybrid_runner_loop_pending_so_far) ?? 0;
  const attempted = numericDiagnosticValue(summary.hybrid_runner_per_item_count)
    ?? numericDiagnosticValue(summary.hybrid_runner_pre_skip_pending)
    ?? 0;
  if (outcome.includes("metrics_miss_unrecoverable") || loopPhase === "metrics_miss_unrecoverable") {
    return true;
  }
  if (outcome.includes("partial") && writeOk > 0 && pendingSoFar > 0) {
    return true;
  }
  return outcome.includes("write_pending") && writeOk === 0 && attempted > 0 && (readyCount == null || readyCount === 0);
}

export function hybridSkippedUncollectableCount(state: WholeProfileHarvestState): number {
  const summary = state.debug.last_response_summary && typeof state.debug.last_response_summary === "object"
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
  return numericDiagnosticValue(summary.hybrid_runner_uncollectable_skipped_count)
    ?? state.harvest.queue.filter((item) => item.profile_card_evidence?.hybrid_uncollectable === true).length;
}

export function hybridMetricsMissQueueCount(state: WholeProfileHarvestState): number {
  const contract = buildProfileCollectContractFromState(state);
  return Math.max(0, contract.incomplete_count > 0 ? contract.incomplete_count : contract.pending_hydration);
}

export function shouldOfferHybridMetricsMissSkip(state: WholeProfileHarvestState, queueCount?: number): boolean {
  if (!hybridLastRunWasMetricsMiss(state)) {
    return false;
  }
  const contract = buildProfileCollectContractFromState(state);
  const metricsMissOnly = Math.max(0, contract.incomplete_count > 0 ? contract.incomplete_count : hybridMetricsMissQueueCount(state));
  const bulkRemaining = Math.max(
    0,
    contract.new_count,
    contract.pending_hydration,
    state.post_scan_counter_snapshot?.new ?? 0,
    queueCount ?? 0
  );
  if (bulkRemaining > metricsMissOnly && bulkRemaining > HYBRID_EXACT_GAP_RECOVERY_CAP) {
    return false;
  }
  return bulkRemaining > 0 || metricsMissOnly > 0;
}

export type HybridMetricsMissUi = {
  skipCount: number;
  title: string;
  description: string;
  buttonLabel: string;
  retryHint: string;
};

export type HybridPerItemFlushOutcome = {
  status: string;
  pending_reason?: string | null;
};

export function isUncollectableHybridPendingRecord(record: HybridPerItemFlushOutcome): boolean {
  return record.status === "skipped_no_finalized"
    || (record.status === "skipped_pending"
      && typeof record.pending_reason === "string"
      && (
        record.pending_reason.startsWith("missing_required_fields:")
        || record.pending_reason === "missing_valid_thumbnail"
        || record.pending_reason === "missing_posted_at"
      ));
}

/** Hybrid collect never auto-skips metrics-miss batches; operator skip only. */
export function shouldAutoSkipHybridMetricsMissBatch(_params: {
  perItemRecords: HybridPerItemFlushOutcome[];
  loopWriteOkCount: number;
  loopFinalizedCount: number;
  loopLazyDetailAttemptedCount: number;
  preLoopDetailHydrationAttempted: number;
  tabId: number | null;
  detailHydrationAvailable: boolean;
}): boolean {
  return false;
}

export function buildHybridMetricsMissUi(queueCount: number, metricsMissing?: number | null): HybridMetricsMissUi {
  const skipCount = metricsMissing != null && metricsMissing > 0
    ? Math.min(metricsMissing, queueCount)
    : queueCount;
  const noun = skipCount === 1 ? "video" : "videos";
  const fields = "likes, comments, duration, or thumbnail";
  return {
    skipCount,
    title: "Finish collection",
    description: `${skipCount} ${noun} still missing ${fields} from Douyin. Skip them to complete this profile, or scroll the profile tab and collect again.`,
    buttonLabel: skipCount === 1 ? "Skip 1 incomplete" : `Skip ${skipCount} incomplete`,
    retryHint: "Tip: Open the Douyin profile tab, scroll to load video cards, then collect again before skipping."
  };
}
