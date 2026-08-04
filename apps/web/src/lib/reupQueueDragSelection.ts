export type SelectionPoint = {
  x: number;
  y: number;
};

export type SelectionRect = {
  bottom: number;
  left: number;
  right: number;
  top: number;
};

export type SelectionRectEntry = {
  id: string;
  rect: SelectionRect;
};

export type MarqueeSelectionMode = "replace" | "toggle";

export function normalizeSelectionRect(anchor: SelectionPoint, current: SelectionPoint): SelectionRect {
  return {
    bottom: Math.max(anchor.y, current.y),
    left: Math.min(anchor.x, current.x),
    right: Math.max(anchor.x, current.x),
    top: Math.min(anchor.y, current.y)
  };
}

export function dragDistance(anchor: SelectionPoint, current: SelectionPoint): number {
  return Math.hypot(current.x - anchor.x, current.y - anchor.y);
}

export function selectionRectsIntersect(left: SelectionRect, right: SelectionRect): boolean {
  if (left.right <= left.left || left.bottom <= left.top || right.right <= right.left || right.bottom <= right.top) return false;
  return left.left < right.right && left.right > right.left && left.top < right.bottom && left.bottom > right.top;
}

export function intersectingSelectionIds(selectionRect: SelectionRect, entries: SelectionRectEntry[]): string[] {
  return entries.filter((entry) => selectionRectsIntersect(selectionRect, entry.rect)).map((entry) => entry.id);
}

export function applyMarqueeSelection(
  selectionAtDragStart: Set<string>,
  intersectingIds: string[],
  mode: MarqueeSelectionMode
): Set<string> {
  if (mode === "replace") return new Set(intersectingIds);

  const next = new Set(selectionAtDragStart);
  for (const itemId of intersectingIds) {
    if (next.has(itemId)) next.delete(itemId);
    else next.add(itemId);
  }
  return next;
}

export function selectSelectionRange(
  currentSelection: Set<string>,
  orderedSelectableIds: string[],
  anchorId: string,
  targetId: string,
  additive: boolean
): Set<string> {
  const anchorIndex = orderedSelectableIds.indexOf(anchorId);
  const targetIndex = orderedSelectableIds.indexOf(targetId);
  if (anchorIndex < 0 || targetIndex < 0) return new Set(currentSelection);

  const start = Math.min(anchorIndex, targetIndex);
  const end = Math.max(anchorIndex, targetIndex);
  const next = additive ? new Set(currentSelection) : new Set<string>();
  for (const itemId of orderedSelectableIds.slice(start, end + 1)) next.add(itemId);
  return next;
}

export function autoScrollVelocity(pointerClientY: number, viewportHeight: number, edgeSize = 64, maxSpeed = 18): number {
  if (viewportHeight <= 0 || edgeSize <= 0 || maxSpeed <= 0) return 0;
  if (pointerClientY < edgeSize) {
    const intensity = Math.min(1, Math.max(0, (edgeSize - pointerClientY) / edgeSize));
    return -Math.max(1, Math.ceil(maxSpeed * intensity));
  }
  if (pointerClientY > viewportHeight - edgeSize) {
    const distanceFromBottom = viewportHeight - pointerClientY;
    const intensity = Math.min(1, Math.max(0, (edgeSize - distanceFromBottom) / edgeSize));
    return Math.max(1, Math.ceil(maxSpeed * intensity));
  }
  return 0;
}
