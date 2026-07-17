import type { ProfileSessionIndexEntry } from "./activeProfilePresentation.js";
import { profileIdentifierFromUrl } from "./profileTargetRepository.js";
import type { WholeProfileHarvestState } from "./state.js";

export const PROFILE_SESSIONS_INDEX_STORAGE_KEY = "douyin_scanner_profile_sessions_index_v1" as const;

export type ProfileSessionIndex = Record<string, ProfileSessionIndexEntry>;

type StorageLike = {
  get(keys: string | string[]): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
};

export async function readProfileSessionIndex(storage: StorageLike): Promise<ProfileSessionIndex> {
  try {
    const raw = await storage.get(PROFILE_SESSIONS_INDEX_STORAGE_KEY);
    const index = raw[PROFILE_SESSIONS_INDEX_STORAGE_KEY];
    if (!index || typeof index !== "object" || Array.isArray(index)) return {};
    return { ...(index as ProfileSessionIndex) };
  } catch {
    return {};
  }
}

export function getProfileSessionIndexEntry(
  index: ProfileSessionIndex,
  profileIdentifier: string
): ProfileSessionIndexEntry | null {
  const entry = index[profileIdentifier];
  return entry && typeof entry === "object" ? entry : null;
}

export async function upsertProfileSessionIndexEntry(
  storage: StorageLike,
  entry: ProfileSessionIndexEntry,
  at: string
): Promise<void> {
  const index = await readProfileSessionIndex(storage);
  index[entry.profile_identifier] = {
    ...entry,
    last_presented_at: at
  };
  await storage.set({ [PROFILE_SESSIONS_INDEX_STORAGE_KEY]: index });
}

export async function touchProfileSessionIndexFromScanState(
  storage: StorageLike,
  state: WholeProfileHarvestState,
  at: string
): Promise<void> {
  const profileUrl = typeof state.profile_url === "string" ? state.profile_url.trim() : "";
  if (!profileUrl) return;
  const profileIdentifier = profileIdentifierFromUrl(profileUrl);
  if (!profileIdentifier) return;
  const scannedTotal = Math.max(
    state.scan_job.total_persisted ?? 0,
    state.profile_scan.target_details.length,
    state.classification.total_candidates ?? 0
  );
  if (scannedTotal <= 0 && state.profile_scan.status !== "success") return;
  if (state.scan_job.status !== "completed" && state.profile_scan.status !== "success") return;

  await upsertProfileSessionIndexEntry(storage, {
    profile_identifier: profileIdentifier,
    canonical_profile_url: profileUrl.replace(/\/+$/, ""),
    last_scan_at: state.scan_job.completed_at ?? state.updated_at ?? at,
    last_scan_job_id: state.scan_job.scan_job_id ?? state.run_id ?? null,
    scanned_total: scannedTotal,
    last_presented_at: at
  }, at);
}
