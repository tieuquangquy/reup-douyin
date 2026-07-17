import type { BenchSlots } from "./reviewBoardBenchState";
import { addCandidateToBench } from "./reviewBoardBenchState";

export function clampGalleryIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(length - 1, index));
}

export function stepGalleryIndex(index: number, length: number, delta: number): number {
  if (length <= 0) return 0;
  return clampGalleryIndex(index + delta, length);
}

export function galleryIndexAfterRemove(index: number, lengthBefore: number): number {
  const lengthAfter = Math.max(0, lengthBefore - 1);
  if (lengthAfter === 0) return 0;
  if (index >= lengthAfter) return lengthAfter - 1;
  return index;
}

export function resolvePinSlotIndex(slots: BenchSlots, focusSlotIndex: number): number {
  if (focusSlotIndex >= 0 && focusSlotIndex < slots.length) return focusSlotIndex;
  const emptyIndex = slots.findIndex((id) => id === null);
  return emptyIndex >= 0 ? emptyIndex : 0;
}

export function pinCandidateToBench(slots: BenchSlots, candidateId: string, focusSlotIndex: number): BenchSlots {
  if (slots.includes(candidateId)) return slots;
  const target = resolvePinSlotIndex(slots, focusSlotIndex);
  return addCandidateToBench(slots, candidateId, target);
}

export function benchSlotIndexForCandidate(slots: BenchSlots, candidateId: string): number {
  return slots.findIndex((id) => id === candidateId);
}

export function canOpenCompareMode(filledCount: number): boolean {
  return filledCount >= 2;
}
