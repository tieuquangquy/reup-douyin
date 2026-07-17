export const MAX_COMPARE_STARS = 3;

export function clampFocusIndex(index: number, length: number): number {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(length - 1, index));
}

export function stepFocusIndex(index: number, length: number, delta: number): number {
  if (length <= 0) return 0;
  return clampFocusIndex(index + delta, length);
}

export function focusIndexAfterRemove(index: number, lengthBefore: number): number {
  const lengthAfter = Math.max(0, lengthBefore - 1);
  if (lengthAfter === 0) return 0;
  if (index >= lengthAfter) return lengthAfter - 1;
  return index;
}

export function toggleCompareStar(starred: string[], candidateId: string, max = MAX_COMPARE_STARS): string[] {
  if (starred.includes(candidateId)) return starred.filter((id) => id !== candidateId);
  if (starred.length >= max) return starred;
  return [...starred, candidateId];
}

export function canOpenCompare(starred: string[]): boolean {
  return starred.length >= 2;
}

export function removeStars(starred: string[], candidateIds: string[]): string[] {
  const remove = new Set(candidateIds);
  return starred.filter((id) => !remove.has(id));
}
