/** Move one list item from ``from`` to ``to`` (inclusive). Returns a new array. */
export function moveItemIndex<T>(items: T[], from: number, to: number): T[] {
  if (
    from === to ||
    from < 0 ||
    to < 0 ||
    from >= items.length ||
    to >= items.length
  ) {
    return items;
  }
  const next = items.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function profileIdsOf(items: Array<{ id: string }>): string[] {
  return items.map((item) => item.id);
}

/** Buttons/inputs on a setup row must not start a row drag. */
export function isSetupTableInteractiveDragTarget(target: EventTarget | null): boolean {
  if (target == null || typeof target !== "object") return false;
  const el = target as { closest?: (selectors: string) => Element | null };
  if (typeof el.closest !== "function") return false;
  return Boolean(
    el.closest(
      "button, input, a, label, select, textarea, [contenteditable='true'], [contenteditable=true]"
    )
  );
}
