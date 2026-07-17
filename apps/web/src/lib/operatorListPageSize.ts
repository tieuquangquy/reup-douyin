export const OPERATOR_LIST_PAGE_SIZE_PRESETS = [25, 50, 100] as const;

export type OperatorListPageSize = (typeof OPERATOR_LIST_PAGE_SIZE_PRESETS)[number];

export const REUP_QUEUE_PAGE_SIZE_STORAGE_KEY = "reup.queue.pageSize";
export const OPS_JOBS_PAGE_SIZE_STORAGE_KEY = "ops.jobs.pageSize";

export type OperatorListPageSizeStorage = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
};

export function resolveOperatorListPageSize(
  raw: string | null | undefined,
  presets: readonly number[],
  defaultSize: number
): number {
  if (raw == null || raw === "") return defaultSize;
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed <= 0) return defaultSize;
  return presets.includes(parsed) ? parsed : defaultSize;
}

function browserStorage(): OperatorListPageSizeStorage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function readOperatorListPageSize(
  key: string,
  presets: readonly number[],
  defaultSize: number,
  storage: OperatorListPageSizeStorage | null = browserStorage()
): number {
  if (!storage) return defaultSize;
  try {
    return resolveOperatorListPageSize(storage.getItem(key), presets, defaultSize);
  } catch {
    return defaultSize;
  }
}

export function writeOperatorListPageSize(
  key: string,
  pageSize: number,
  presets: readonly number[],
  storage: OperatorListPageSizeStorage | null = browserStorage()
): boolean {
  if (!storage || !presets.includes(pageSize)) return false;
  try {
    storage.setItem(key, String(pageSize));
    return true;
  } catch {
    return false;
  }
}
