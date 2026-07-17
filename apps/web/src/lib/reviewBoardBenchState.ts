import { reviewCandidateDisplayScore } from "./reviewCandidateMetadata";
import type { Candidate } from "../types/review-board";

export const BENCH_SLOT_COUNT = 3;
export const BENCH_SLOT_LABELS = ["A", "B", "C"] as const;

export type BenchSlots = Array<string | null>;

export function createEmptyBench(): BenchSlots {
  return [null, null, null];
}

export function addCandidateToBench(slots: BenchSlots, candidateId: string, slotIndex?: number): BenchSlots {
  const next = slots.map((id) => (id === candidateId ? null : id));
  const target = slotIndex ?? next.findIndex((id) => id === null);
  if (target < 0 || target >= next.length) return slots;
  next[target] = candidateId;
  return next;
}

export function removeBenchSlot(slots: BenchSlots, slotIndex: number): BenchSlots {
  const next = [...slots];
  if (slotIndex >= 0 && slotIndex < next.length) next[slotIndex] = null;
  return next;
}

export function clearBench(): BenchSlots {
  return createEmptyBench();
}

export function benchOccupiedIds(slots: BenchSlots): string[] {
  return slots.filter((id): id is string => Boolean(id));
}

export function pickBestBenchCandidateId(candidates: Candidate[], slotIds: string[]): string | null {
  let bestId: string | null = null;
  let bestScore = Number.NEGATIVE_INFINITY;
  for (const id of slotIds) {
    const candidate = candidates.find((entry) => entry.id === id);
    if (!candidate) continue;
    const score = reviewCandidateDisplayScore(candidate) ?? Number.NEGATIVE_INFINITY;
    if (score > bestScore) {
      bestScore = score;
      bestId = id;
    }
  }
  return bestId;
}

export function poolCandidatesForBench(visible: Candidate[], benchIds: string[]): Candidate[] {
  const occupied = new Set(benchIds);
  return visible.filter((candidate) => !occupied.has(candidate.id));
}

export function pruneBenchSlots(slots: BenchSlots, loadedIds: Set<string>): BenchSlots {
  return slots.map((id) => (id && loadedIds.has(id) ? id : null));
}

export function splitApproveBestTargets(slotIds: string[], bestId: string): { approveId: string; rejectIds: string[] } {
  return {
    approveId: bestId,
    rejectIds: slotIds.filter((id) => id !== bestId)
  };
}
