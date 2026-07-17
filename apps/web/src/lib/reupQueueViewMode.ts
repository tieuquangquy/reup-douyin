export type ReupQueueViewMode = "gallery" | "worklist";

export const REUP_QUEUE_VIEW_MODE_STORAGE_KEY = "reup.queue.viewMode";
export const REUP_QUEUE_VIEW_MODE_DEFAULT: ReupQueueViewMode = "gallery";

export const REUP_QUEUE_VIEW_MODE_LABELS: Record<ReupQueueViewMode, string> = {
  gallery: "Gallery",
  worklist: "Worklist"
};

export type ReupQueueViewModeStorage = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
};

export function resolveReupQueueViewMode(raw: string | null | undefined): ReupQueueViewMode {
  if (raw === "gallery" || raw === "worklist") return raw;
  return REUP_QUEUE_VIEW_MODE_DEFAULT;
}

function browserStorage(): ReupQueueViewModeStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readReupQueueViewMode(
  storage: ReupQueueViewModeStorage | null = browserStorage()
): ReupQueueViewMode {
  if (!storage) return REUP_QUEUE_VIEW_MODE_DEFAULT;
  try {
    return resolveReupQueueViewMode(storage.getItem(REUP_QUEUE_VIEW_MODE_STORAGE_KEY));
  } catch {
    return REUP_QUEUE_VIEW_MODE_DEFAULT;
  }
}

export function writeReupQueueViewMode(
  mode: ReupQueueViewMode,
  storage: ReupQueueViewModeStorage | null = browserStorage()
): boolean {
  if (!storage || (mode !== "gallery" && mode !== "worklist")) return false;
  try {
    storage.setItem(REUP_QUEUE_VIEW_MODE_STORAGE_KEY, mode);
    return true;
  } catch {
    return false;
  }
}
