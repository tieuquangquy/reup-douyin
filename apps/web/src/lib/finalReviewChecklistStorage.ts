import type { ChecklistState } from "../types/final-review";
import { DEFAULT_FINAL_REVIEW_CHECKLIST } from "./finalReviewState";

const STORAGE_PREFIX = "final-review-checklist:";

function isChecklistState(value: unknown): value is ChecklistState {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return (Object.keys(DEFAULT_FINAL_REVIEW_CHECKLIST) as (keyof ChecklistState)[]).every(
    (key) => typeof record[key] === "boolean"
  );
}

function getLocalStorage(): Storage | null {
  try {
    const storage = (globalThis as { localStorage?: Storage }).localStorage;
    return storage ?? null;
  } catch {
    return null;
  }
}

export function finalReviewChecklistStorageKey(renderId: string): string {
  return `${STORAGE_PREFIX}${renderId}`;
}

/** Load operator checklist for a render from localStorage (Phase 1 client persist). */
export function loadFinalReviewChecklist(renderId: string): ChecklistState | null {
  const storage = getLocalStorage();
  if (!storage || !renderId) return null;
  try {
    const raw = storage.getItem(finalReviewChecklistStorageKey(renderId));
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isChecklistState(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveFinalReviewChecklist(renderId: string, checklist: ChecklistState): void {
  const storage = getLocalStorage();
  if (!storage || !renderId) return;
  try {
    storage.setItem(finalReviewChecklistStorageKey(renderId), JSON.stringify(checklist));
  } catch {
    // Quota / private mode — ignore; checklist stays session-local.
  }
}
