import { buildDirectModalUrl } from "./profileResolver.js";
import type { WholeProfileHarvestDryRunMode, WholeProfileHarvestDryRunResult } from "./state.js";

export type WholeProfileDryRunMetrics = {
  duration_seconds: number | null;
  duration_text: string | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  current_modal_id_before: string | null;
  current_modal_id_after: string | null;
  extracted_aweme_id: string | null;
  source_used: string | null;
};

export type WholeProfileDryRunTransport = {
  openDirectModal(tabId: number, targetUrl: string, awemeId: string): Promise<void>;
  extractModalMetrics(tabId: number, awemeId: string): Promise<WholeProfileDryRunMetrics>;
};

export function selectDryRunSample(targets: string[], mode: WholeProfileHarvestDryRunMode, sampleSize = 3, random = Math.random): { sampled_aweme_ids: string[]; sampled_indexes: number[] } {
  const size = Math.min(sampleSize, targets.length);
  if (mode === "first") return { sampled_aweme_ids: targets.slice(0, size), sampled_indexes: targets.slice(0, size).map((_, index) => index) };
  if (mode === "last") {
    const start = Math.max(0, targets.length - size);
    return { sampled_aweme_ids: targets.slice(start), sampled_indexes: targets.slice(start).map((_, index) => start + index) };
  }
  const indexes = new Set<number>();
  while (indexes.size < size) indexes.add(Math.floor(random() * targets.length));
  const sampledIndexes = [...indexes].sort((a, b) => a - b);
  return { sampled_aweme_ids: sampledIndexes.map((index) => targets[index] as string), sampled_indexes: sampledIndexes };
}

export async function runDryRunTargets(args: {
  transport: WholeProfileDryRunTransport;
  tabId: number;
  profileUrl: string;
  sampledAwemeIds: string[];
  sampledIndexes: number[];
  now?: () => string;
}): Promise<WholeProfileHarvestDryRunResult[]> {
  const now = args.now ?? (() => new Date().toISOString());
  const results: WholeProfileHarvestDryRunResult[] = [];
  for (let i = 0; i < args.sampledAwemeIds.length; i += 1) {
    const awemeId = args.sampledAwemeIds[i] as string;
    const targetUrl = buildDirectModalUrl(args.profileUrl, awemeId);
    const startedAt = now();
    try {
      await args.transport.openDirectModal(args.tabId, targetUrl, awemeId);
      const metrics = await args.transport.extractModalMetrics(args.tabId, awemeId);
      const integrityPassed = metrics.current_modal_id_before === awemeId && metrics.current_modal_id_after === awemeId && metrics.extracted_aweme_id === awemeId;
      results.push({
        index: args.sampledIndexes[i] ?? i,
        aweme_id: awemeId,
        target_url: targetUrl,
        status: integrityPassed ? "pass" : "fail",
        duration_seconds: metrics.duration_seconds,
        duration_text: metrics.duration_text,
        like_count: metrics.like_count,
        comment_count: metrics.comment_count,
        favorite_count: metrics.favorite_count,
        share_count: metrics.share_count,
        current_modal_id_before: metrics.current_modal_id_before,
        current_modal_id_after: metrics.current_modal_id_after,
        extracted_aweme_id: metrics.extracted_aweme_id,
        source_used: metrics.source_used,
        data_integrity_status: integrityPassed ? "passed" : "failed",
        error: integrityPassed ? null : "data_integrity_mismatch",
        started_at: startedAt,
        completed_at: now()
      });
    } catch (error) {
      results.push({
        index: args.sampledIndexes[i] ?? i,
        aweme_id: awemeId,
        target_url: targetUrl,
        status: "fail",
        duration_seconds: null,
        duration_text: null,
        like_count: null,
        comment_count: null,
        favorite_count: null,
        share_count: null,
        current_modal_id_before: null,
        current_modal_id_after: null,
        extracted_aweme_id: null,
        source_used: null,
        data_integrity_status: "failed",
        error: error instanceof Error ? error.message : String(error),
        started_at: startedAt,
        completed_at: now()
      });
    }
  }
  return results;
}
