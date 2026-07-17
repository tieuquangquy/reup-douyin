const HYBRID_COLLECT_BATCH_CAP = 500;

/** Batch limits must stay > 0 when backend gap remains but the visible queue window is empty. */
export function resolveHybridCollectBatchLimits(
  queueLength: number,
  backendCollectRemaining: number
): { writeBatchLimit: number; preSkipScanLimit: number } {
  const safeRemaining = Math.max(0, Math.round(backendCollectRemaining));
  if (safeRemaining <= 0) {
    return { writeBatchLimit: 0, preSkipScanLimit: 0 };
  }
  const effectiveWindow = Math.max(Math.max(0, Math.round(queueLength)), safeRemaining);
  const cappedRemaining = Math.min(HYBRID_COLLECT_BATCH_CAP, safeRemaining);
  const writeBatchLimit = Math.max(1, Math.min(effectiveWindow, cappedRemaining));
  const preSkipScanLimit = Math.max(1, Math.min(HYBRID_COLLECT_BATCH_CAP, safeRemaining, effectiveWindow));
  return { writeBatchLimit, preSkipScanLimit };
}
