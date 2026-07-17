import type { WholeProfileHarvestQueueItem, WholeProfileHarvestQueueStatus, WholeProfileHarvestTargetDetail } from "./state.js";
import { buildHybridProfileCardEvidence, evidenceIsHybridFlushReady } from "./hybridHydration.js";

export const LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE = 500;
export const PROFILE_TARGETS_DB_BACKEND = "indexeddb";
export const PROFILE_TARGETS_LOCAL_BACKEND = "local";
export const PROFILE_TARGETS_DB_NAME = "reup_douyin_profile_targets_22C14A";
export const PROFILE_TARGETS_DB_VERSION = 1;
export const PROFILE_TARGETS_STORE_NAME = "profileTargets";
export const PROFILE_TARGET_CHECKPOINTS_STORE_NAME = "profileTargetCheckpoints";

const PROFILE_TARGET_PROFILE_INDEX = "by_profile";
const PROFILE_TARGET_STATUS_INDEX = "by_profile_status_sequence";
const PROFILE_TARGET_UPDATED_INDEX = "by_profile_updated_at";

type ProfileTargetStorageBackend = typeof PROFILE_TARGETS_DB_BACKEND | typeof PROFILE_TARGETS_LOCAL_BACKEND;

type IndexedDbLike = {
  open(name: string, version?: number): IDBOpenDBRequest;
  deleteDatabase(name: string): IDBOpenDBRequest;
};

export type ProfileTargetRecord = {
  profile_identifier: string;
  aweme_id: string;
  sequence: number;
  source_url: string | null;
  status: WholeProfileHarvestQueueStatus;
  capture_status: WholeProfileHarvestQueueItem["capture_status"];
  attempts: number;
  updated_at: string;
  queue_item: WholeProfileHarvestQueueItem;
  target_detail: WholeProfileHarvestTargetDetail;
};

export type ProfileTargetUpsertResult = {
  backend: ProfileTargetStorageBackend;
  total: number;
  degraded: boolean;
  degraded_reason: string | null;
};

export type ProfileTargetWindowResult = {
  backend: ProfileTargetStorageBackend;
  total: number;
  records: ProfileTargetRecord[];
  degraded: boolean;
  degraded_reason: string | null;
};

export type ProfileTargetStatusCount = {
  status: WholeProfileHarvestQueueStatus;
  count: number;
};

export type ProfileTargetScanContinuationCheckpoint = {
  continuation_available: "yes" | "no";
  continuation_cursor: string | number | null;
  continuation_page_count: number;
  continuation_request_count: number;
  continuation_persisted_total: number;
  continuation_profile_identifier: string;
  continuation_run_id: string | null;
  continuation_checkpoint_id: string | null;
  continuation_cursor_source: "fresh_start" | "saved_continuation_checkpoint" | "replay_recovery_checkpoint" | "unknown";
  continuation_resume_strategy: "fresh_scan" | "resume_from_saved_cursor" | "replay_recovery_from_saved_cursor" | "none";
  continuation_resume_result: "not_started" | "resumed_from_saved_cursor" | "replay_recovery_resumed" | "checkpoint_unavailable" | "not_applicable";
  continuation_replay_duplicate_pages_detected: "yes" | "no";
  continuation_replay_duplicate_count: number;
  continuation_recovery_attempted: "yes" | "no";
  continuation_recovery_result: "not_attempted" | "reused_saved_cursor" | "checkpoint_unavailable" | "recovery_exhausted";
  true_source_failure: "yes" | "no" | "unknown";
  checkpoint_saved_at: string | null;
};

export type ProfileTargetCursorCheckpoint = {
  collect_cursor: number;
  last_processed_aweme_id: string | null;
  last_checkpoint_at: string | null;
  chunk_processed_count: number;
  chunk_total_count: number;
  scan_continuation?: ProfileTargetScanContinuationCheckpoint | null;
};

export const COLLECTED_REPOSITORY_STATUSES: WholeProfileHarvestQueueStatus[] = [
  "already_collected",
  "backend_verified",
  "complete",
  "extracted"
];

export type ProfileTargetResetCollectedResult = {
  backend: ProfileTargetStorageBackend;
  reset_count: number;
  degraded: boolean;
  degraded_reason: string | null;
};

export interface ProfileTargetRepository {
  upsertProfileTargets(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult>;
  upsertProfileTargetPage(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult>;
  getProfileTargetsByStatus(profileIdentifier: string, statuses: WholeProfileHarvestQueueStatus[], limit: number, offset?: number): Promise<ProfileTargetWindowResult>;
  countProfileTargets(profileIdentifier: string, statuses?: WholeProfileHarvestQueueStatus[]): Promise<ProfileTargetWindowResult>;
  countProfileTargetsByStatus(profileIdentifier: string): Promise<{ backend: ProfileTargetStorageBackend; total: number; counts: ProfileTargetStatusCount[]; degraded: boolean; degraded_reason: string | null }>;
  updateTargetStatus(profileIdentifier: string, awemeId: string, patch: Partial<Pick<ProfileTargetRecord, "status" | "attempts" | "updated_at">>, checkpoint?: ProfileTargetCursorCheckpoint): Promise<ProfileTargetUpsertResult>;
  resetCollectedTargetsToPending(profileIdentifier: string, at: string): Promise<ProfileTargetResetCollectedResult>;
  getCheckpoint(profileIdentifier: string): Promise<ProfileTargetCursorCheckpoint | null>;
  setCheckpoint(profileIdentifier: string, checkpoint: ProfileTargetCursorCheckpoint): Promise<void>;
}

const memoryRecords = new Map<string, ProfileTargetRecord>();
const memoryCheckpoints = new Map<string, ProfileTargetCursorCheckpoint>();

function storageKey(profileIdentifier: string, awemeId: string): string {
  return `${profileIdentifier}::${awemeId}`;
}

function normalizeOffset(offset: number): number {
  return Math.max(0, Math.round(Number.isFinite(offset) ? offset : 0));
}

function normalizeLimit(limit: number): number {
  return Math.max(0, Math.min(500, Math.round(Number.isFinite(limit) ? limit : LARGE_PROFILE_QUEUE_PREVIEW_WINDOW_SIZE)));
}

/**
 * Merge an existing persisted profile_card_evidence with an incoming one WITHOUT
 * ever downgrading a flush-ready record to a thinner one.
 *
 * Incoming (newer) non-null fields win, existing fields backfill the gaps. Because
 * `buildHybridProfileCardEvidence` overlays only non-null overlay values, a thin
 * incoming evidence (no metrics) never wipes the rich metrics captured at scan.
 * A final guard refuses any merge that would drop hybrid flush-readiness.
 */
export function mergeProfileCardEvidencePreservingRicher(
  existing: Record<string, unknown> | null | undefined,
  incoming: Record<string, unknown> | null | undefined
): Record<string, unknown> {
  const existingObj = existing && typeof existing === "object" && Object.keys(existing).length > 0
    ? existing as Record<string, unknown>
    : null;
  const incomingObj = incoming && typeof incoming === "object" && Object.keys(incoming).length > 0
    ? incoming as Record<string, unknown>
    : null;
  if (!existingObj) return incomingObj ?? {};
  if (!incomingObj) return existingObj;
  const merged = buildHybridProfileCardEvidence(existingObj, [incomingObj]);
  if (evidenceIsHybridFlushReady(existingObj) && !evidenceIsHybridFlushReady(merged)) {
    return existingObj;
  }
  return merged;
}

function queueItemWithMergedEvidence(
  item: WholeProfileHarvestQueueItem,
  existing: ProfileTargetRecord | undefined
): WholeProfileHarvestQueueItem {
  const existingEvidence = existing?.queue_item?.profile_card_evidence;
  if (!existingEvidence || typeof existingEvidence !== "object" || Object.keys(existingEvidence).length === 0) {
    return item;
  }
  const mergedEvidence = mergeProfileCardEvidencePreservingRicher(existingEvidence, item.profile_card_evidence);
  return { ...item, profile_card_evidence: mergedEvidence };
}

function recordFromQueueItem(profileIdentifier: string, item: WholeProfileHarvestQueueItem, targetDetails: Map<string, WholeProfileHarvestTargetDetail>, at: string, index: number): ProfileTargetRecord {
  const targetDetail = targetDetails.get(item.aweme_id) ?? {
    index: item.index ?? index + 1,
    aweme_id: item.aweme_id,
    source_url: item.source_url,
    profile_url: typeof item.profile_card_evidence?.profile_url === "string" ? item.profile_card_evidence.profile_url : null,
    thumbnail_url: null,
    title: null,
    caption: null,
    text_sample: null,
    posted_text: null,
    posted_at: null,
    duration_text: null,
    duration_seconds: null,
    view_text: null,
    view_count: null,
    candidate_validation: { status: "accepted", source: "video_link", reason: "large_profile_repository_fallback_detail", source_url: item.source_url },
    metadata_completeness: { has_profile_identity: false, has_thumbnail: false, has_title_or_caption: false, has_posted_text: false, has_duration: false, has_view_count: false, has_detail_metrics: false },
    capture_status: item.capture_status,
    backend_item: null,
    extraction_source: "video_link",
    profile_card_evidence: item.profile_card_evidence ?? {}
  } satisfies WholeProfileHarvestTargetDetail;
  return {
    profile_identifier: profileIdentifier,
    aweme_id: item.aweme_id,
    sequence: item.index ?? index + 1,
    source_url: item.source_url,
    status: item.status,
    capture_status: item.capture_status,
    attempts: item.attempts ?? 0,
    updated_at: at,
    queue_item: item,
    target_detail: targetDetail
  };
}

function recordsForProfile(profileIdentifier: string, statuses?: WholeProfileHarvestQueueStatus[]): ProfileTargetRecord[] {
  const statusSet = statuses && statuses.length > 0 ? new Set(statuses) : null;
  return Array.from(memoryRecords.values())
    .filter((record) => record.profile_identifier === profileIdentifier && (!statusSet || statusSet.has(record.status)))
    .sort((a, b) => a.sequence - b.sequence || a.aweme_id.localeCompare(b.aweme_id));
}

function captureStatusForTargetStatus(status: WholeProfileHarvestQueueStatus, fallback: WholeProfileHarvestQueueItem["capture_status"]): WholeProfileHarvestQueueItem["capture_status"] {
  if (status === "already_collected" || status === "backend_verified" || status === "complete" || status === "extracted") return "complete";
  if (status === "skipped" || status === "duplicate") return "skipped";
  if (status === "failed" || status === "failed_permanent") return "failed";
  if (status === "incomplete" || status === "needs_metadata" || status === "failed_recoverable" || status === "retry") return "incomplete";
  return fallback;
}

function applyProfileTargetRecordPatch(current: ProfileTargetRecord, patch: Partial<Pick<ProfileTargetRecord, "status" | "attempts" | "updated_at">>): ProfileTargetRecord {
  const status = patch.status ?? current.status;
  const captureStatus = patch.status ? captureStatusForTargetStatus(status, current.capture_status) : current.capture_status;
  const attempts = patch.attempts ?? current.attempts;
  return {
    ...current,
    ...patch,
    status,
    capture_status: captureStatus,
    attempts,
    queue_item: {
      ...current.queue_item,
      status,
      capture_status: captureStatus,
      attempts
    },
    target_detail: {
      ...current.target_detail,
      capture_status: captureStatus
    }
  };
}

const collectedRepositoryStatusSet = new Set<WholeProfileHarvestQueueStatus>(COLLECTED_REPOSITORY_STATUSES);

function resetCollectedRecordToPending(record: ProfileTargetRecord, at: string): ProfileTargetRecord {
  return {
    ...record,
    status: "pending",
    capture_status: "new",
    updated_at: at,
    queue_item: {
      ...record.queue_item,
      status: "pending",
      capture_status: "new",
      capture_inbox_item_id: null,
      backend_item_id: null,
      extraction_result: null,
      last_error: null,
      saved_at: null,
      profile_card_evidence: {
        ...record.queue_item.profile_card_evidence,
        backend_reconciled: false,
        backend_reconciled_source: "backend_empty_repository_reset",
        backend_reconciled_at: at
      }
    },
    target_detail: {
      ...record.target_detail,
      capture_status: "new",
      backend_item: null
    }
  };
}

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("indexeddb_request_failed"));
  });
}

function transactionDone(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("indexeddb_transaction_failed"));
    transaction.onabort = () => reject(transaction.error ?? new Error("indexeddb_transaction_aborted"));
  });
}

function indexedDbGlobal(): IndexedDbLike | null {
  const candidate = (globalThis as unknown as { indexedDB?: IndexedDbLike }).indexedDB;
  return candidate && typeof candidate.open === "function" ? candidate : null;
}

async function openProfileTargetsDb(indexedDB: IndexedDbLike): Promise<IDBDatabase> {
  const request = indexedDB.open(PROFILE_TARGETS_DB_NAME, PROFILE_TARGETS_DB_VERSION);
  request.onupgradeneeded = () => {
    const db = request.result;
    const targetStore = db.objectStoreNames.contains(PROFILE_TARGETS_STORE_NAME)
      ? request.transaction!.objectStore(PROFILE_TARGETS_STORE_NAME)
      : db.createObjectStore(PROFILE_TARGETS_STORE_NAME, { keyPath: ["profile_identifier", "aweme_id"] });
    if (!targetStore.indexNames.contains(PROFILE_TARGET_PROFILE_INDEX)) targetStore.createIndex(PROFILE_TARGET_PROFILE_INDEX, "profile_identifier", { unique: false });
    if (!targetStore.indexNames.contains(PROFILE_TARGET_STATUS_INDEX)) targetStore.createIndex(PROFILE_TARGET_STATUS_INDEX, ["profile_identifier", "status", "sequence"], { unique: false });
    if (!targetStore.indexNames.contains(PROFILE_TARGET_UPDATED_INDEX)) targetStore.createIndex(PROFILE_TARGET_UPDATED_INDEX, ["profile_identifier", "updated_at"], { unique: false });
    if (!db.objectStoreNames.contains(PROFILE_TARGET_CHECKPOINTS_STORE_NAME)) db.createObjectStore(PROFILE_TARGET_CHECKPOINTS_STORE_NAME, { keyPath: "profile_identifier" });
  };
  return requestToPromise(request);
}

export class InMemoryProfileTargetRepository implements ProfileTargetRepository {
  async upsertProfileTargets(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult> {
    const nextAwemeIds = new Set(queue.map((item) => item.aweme_id));
    for (const record of recordsForProfile(profileIdentifier)) {
      if (!nextAwemeIds.has(record.aweme_id)) memoryRecords.delete(storageKey(profileIdentifier, record.aweme_id));
    }
    const detailByAwemeId = new Map(targetDetails.map((target) => [target.aweme_id, target]));
    queue.forEach((item, index) => {
      const merged = queueItemWithMergedEvidence(item, memoryRecords.get(storageKey(profileIdentifier, item.aweme_id)));
      memoryRecords.set(storageKey(profileIdentifier, item.aweme_id), recordFromQueueItem(profileIdentifier, merged, detailByAwemeId, at, index));
    });
    return { backend: PROFILE_TARGETS_LOCAL_BACKEND, total: recordsForProfile(profileIdentifier).length, degraded: false, degraded_reason: null };
  }

  async upsertProfileTargetPage(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult> {
    const detailByAwemeId = new Map(targetDetails.map((target) => [target.aweme_id, target]));
    queue.forEach((item, index) => {
      const merged = queueItemWithMergedEvidence(item, memoryRecords.get(storageKey(profileIdentifier, item.aweme_id)));
      memoryRecords.set(storageKey(profileIdentifier, item.aweme_id), recordFromQueueItem(profileIdentifier, merged, detailByAwemeId, at, index));
    });
    return { backend: PROFILE_TARGETS_LOCAL_BACKEND, total: recordsForProfile(profileIdentifier).length, degraded: false, degraded_reason: null };
  }

  async getProfileTargetsByStatus(profileIdentifier: string, statuses: WholeProfileHarvestQueueStatus[], limit: number, offset = 0): Promise<ProfileTargetWindowResult> {
    const all = recordsForProfile(profileIdentifier, statuses);
    return { backend: PROFILE_TARGETS_LOCAL_BACKEND, total: all.length, records: all.slice(normalizeOffset(offset), normalizeOffset(offset) + normalizeLimit(limit)), degraded: false, degraded_reason: null };
  }

  async countProfileTargets(profileIdentifier: string, statuses?: WholeProfileHarvestQueueStatus[]): Promise<ProfileTargetWindowResult> {
    return { backend: PROFILE_TARGETS_LOCAL_BACKEND, total: recordsForProfile(profileIdentifier, statuses).length, records: [], degraded: false, degraded_reason: null };
  }

  async countProfileTargetsByStatus(profileIdentifier: string): Promise<{ backend: ProfileTargetStorageBackend; total: number; counts: ProfileTargetStatusCount[]; degraded: boolean; degraded_reason: string | null }> {
    const countsByStatus = new Map<WholeProfileHarvestQueueStatus, number>();
    for (const record of recordsForProfile(profileIdentifier)) countsByStatus.set(record.status, (countsByStatus.get(record.status) ?? 0) + 1);
    const counts = Array.from(countsByStatus.entries()).map(([status, count]) => ({ status, count }));
    return { backend: PROFILE_TARGETS_LOCAL_BACKEND, total: counts.reduce((sum, item) => sum + item.count, 0), counts, degraded: false, degraded_reason: null };
  }

  async updateTargetStatus(profileIdentifier: string, awemeId: string, patch: Partial<Pick<ProfileTargetRecord, "status" | "attempts" | "updated_at">>, checkpoint?: ProfileTargetCursorCheckpoint): Promise<ProfileTargetUpsertResult> {
    const key = storageKey(profileIdentifier, awemeId);
    const current = memoryRecords.get(key);
    if (current) memoryRecords.set(key, applyProfileTargetRecordPatch(current, patch));
    if (checkpoint) memoryCheckpoints.set(profileIdentifier, checkpoint);
    return { backend: PROFILE_TARGETS_LOCAL_BACKEND, total: recordsForProfile(profileIdentifier).length, degraded: false, degraded_reason: null };
  }

  async resetCollectedTargetsToPending(profileIdentifier: string, at: string): Promise<ProfileTargetResetCollectedResult> {
    let resetCount = 0;
    for (const record of recordsForProfile(profileIdentifier)) {
      if (!collectedRepositoryStatusSet.has(record.status)) continue;
      memoryRecords.set(storageKey(profileIdentifier, record.aweme_id), resetCollectedRecordToPending(record, at));
      resetCount += 1;
    }
    return { backend: PROFILE_TARGETS_LOCAL_BACKEND, reset_count: resetCount, degraded: false, degraded_reason: null };
  }

  async getCheckpoint(profileIdentifier: string): Promise<ProfileTargetCursorCheckpoint | null> {
    return memoryCheckpoints.get(profileIdentifier) ?? null;
  }

  async setCheckpoint(profileIdentifier: string, checkpoint: ProfileTargetCursorCheckpoint): Promise<void> {
    memoryCheckpoints.set(profileIdentifier, checkpoint);
  }
}

export class IndexedDbProfileTargetRepository implements ProfileTargetRepository {
  constructor(private readonly indexedDB: IndexedDbLike) {}

  private async db(): Promise<IDBDatabase> {
    return openProfileTargetsDb(this.indexedDB);
  }

  async upsertProfileTargets(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult> {
    const db = await this.db();
    try {
      const detailByAwemeId = new Map(targetDetails.map((target) => [target.aweme_id, target]));
      const nextAwemeIds = new Set(queue.map((item) => item.aweme_id));
      const existingTransaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readonly");
      const existingRecords = await requestToPromise(existingTransaction.objectStore(PROFILE_TARGETS_STORE_NAME).index(PROFILE_TARGET_PROFILE_INDEX).getAll(profileIdentifier)) as ProfileTargetRecord[];
      const existingByAwemeId = new Map(existingRecords.map((record) => [record.aweme_id, record]));
      const transaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readwrite");
      const store = transaction.objectStore(PROFILE_TARGETS_STORE_NAME);
      existingRecords.forEach((record) => {
        if (!nextAwemeIds.has(record.aweme_id)) store.delete([profileIdentifier, record.aweme_id]);
      });
      queue.forEach((item, index) => {
        const merged = queueItemWithMergedEvidence(item, existingByAwemeId.get(item.aweme_id));
        store.put(recordFromQueueItem(profileIdentifier, merged, detailByAwemeId, at, index));
      });
      await transactionDone(transaction);
      const count = await this.countProfileTargets(profileIdentifier);
      return { backend: PROFILE_TARGETS_DB_BACKEND, total: count.total, degraded: false, degraded_reason: null };
    } finally {
      db.close();
    }
  }

  async upsertProfileTargetPage(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult> {
    const db = await this.db();
    try {
      const detailByAwemeId = new Map(targetDetails.map((target) => [target.aweme_id, target]));
      const existingTransaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readonly");
      const existingRecords = await requestToPromise(existingTransaction.objectStore(PROFILE_TARGETS_STORE_NAME).index(PROFILE_TARGET_PROFILE_INDEX).getAll(profileIdentifier)) as ProfileTargetRecord[];
      const existingByAwemeId = new Map(existingRecords.map((record) => [record.aweme_id, record]));
      const transaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readwrite");
      const store = transaction.objectStore(PROFILE_TARGETS_STORE_NAME);
      queue.forEach((item, index) => {
        const merged = queueItemWithMergedEvidence(item, existingByAwemeId.get(item.aweme_id));
        store.put(recordFromQueueItem(profileIdentifier, merged, detailByAwemeId, at, index));
      });
      await transactionDone(transaction);
      const count = await this.countProfileTargets(profileIdentifier);
      return { backend: PROFILE_TARGETS_DB_BACKEND, total: count.total, degraded: false, degraded_reason: null };
    } finally {
      db.close();
    }
  }

  async getProfileTargetsByStatus(profileIdentifier: string, statuses: WholeProfileHarvestQueueStatus[], limit: number, offset = 0): Promise<ProfileTargetWindowResult> {
    const db = await this.db();
    try {
      const allStatuses = statuses.length > 0 ? statuses : ["new", "pending", "processing", "retry", "incomplete", "needs_metadata", "failed_recoverable"] as WholeProfileHarvestQueueStatus[];
      const records: ProfileTargetRecord[] = [];
      for (const status of allStatuses) {
        const transaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readonly");
        const index = transaction.objectStore(PROFILE_TARGETS_STORE_NAME).index(PROFILE_TARGET_STATUS_INDEX);
        const request = index.getAll(IDBKeyRange.bound([profileIdentifier, status, 0], [profileIdentifier, status, Number.MAX_SAFE_INTEGER]));
        records.push(...await requestToPromise(request) as ProfileTargetRecord[]);
      }
      const sorted = records.sort((a, b) => a.sequence - b.sequence || a.aweme_id.localeCompare(b.aweme_id));
      return { backend: PROFILE_TARGETS_DB_BACKEND, total: sorted.length, records: sorted.slice(normalizeOffset(offset), normalizeOffset(offset) + normalizeLimit(limit)), degraded: false, degraded_reason: null };
    } finally {
      db.close();
    }
  }

  async countProfileTargets(profileIdentifier: string, statuses?: WholeProfileHarvestQueueStatus[]): Promise<ProfileTargetWindowResult> {
    const db = await this.db();
    try {
      if (statuses && statuses.length > 0) {
        const window = await this.getProfileTargetsByStatus(profileIdentifier, statuses, 0, 0);
        return { ...window, records: [] };
      }
      const transaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readonly");
      const request = transaction.objectStore(PROFILE_TARGETS_STORE_NAME).index(PROFILE_TARGET_PROFILE_INDEX).count(profileIdentifier);
      const total = await requestToPromise(request);
      return { backend: PROFILE_TARGETS_DB_BACKEND, total, records: [], degraded: false, degraded_reason: null };
    } finally {
      db.close();
    }
  }

  async countProfileTargetsByStatus(profileIdentifier: string): Promise<{ backend: ProfileTargetStorageBackend; total: number; counts: ProfileTargetStatusCount[]; degraded: boolean; degraded_reason: string | null }> {
    const db = await this.db();
    try {
      const transaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readonly");
      const records = await requestToPromise(transaction.objectStore(PROFILE_TARGETS_STORE_NAME).index(PROFILE_TARGET_PROFILE_INDEX).getAll(profileIdentifier)) as ProfileTargetRecord[];
      const countsByStatus = new Map<WholeProfileHarvestQueueStatus, number>();
      records.forEach((record) => countsByStatus.set(record.status, (countsByStatus.get(record.status) ?? 0) + 1));
      return { backend: PROFILE_TARGETS_DB_BACKEND, total: records.length, counts: Array.from(countsByStatus.entries()).map(([status, count]) => ({ status, count })), degraded: false, degraded_reason: null };
    } finally {
      db.close();
    }
  }

  async updateTargetStatus(profileIdentifier: string, awemeId: string, patch: Partial<Pick<ProfileTargetRecord, "status" | "attempts" | "updated_at">>, checkpoint?: ProfileTargetCursorCheckpoint): Promise<ProfileTargetUpsertResult> {
    const db = await this.db();
    try {
      const stores = checkpoint ? [PROFILE_TARGETS_STORE_NAME, PROFILE_TARGET_CHECKPOINTS_STORE_NAME] : [PROFILE_TARGETS_STORE_NAME];
      const transaction = db.transaction(stores, "readwrite");
      const store = transaction.objectStore(PROFILE_TARGETS_STORE_NAME);
      const current = await requestToPromise(store.get([profileIdentifier, awemeId])) as ProfileTargetRecord | undefined;
      if (current) store.put(applyProfileTargetRecordPatch(current, patch));
      if (checkpoint) transaction.objectStore(PROFILE_TARGET_CHECKPOINTS_STORE_NAME).put({ profile_identifier: profileIdentifier, checkpoint });
      await transactionDone(transaction);
      const count = await this.countProfileTargets(profileIdentifier);
      return { backend: PROFILE_TARGETS_DB_BACKEND, total: count.total, degraded: false, degraded_reason: null };
    } finally {
      db.close();
    }
  }

  async resetCollectedTargetsToPending(profileIdentifier: string, at: string): Promise<ProfileTargetResetCollectedResult> {
    const db = await this.db();
    try {
      const readTransaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readonly");
      const records = await requestToPromise(
        readTransaction.objectStore(PROFILE_TARGETS_STORE_NAME).index(PROFILE_TARGET_PROFILE_INDEX).getAll(profileIdentifier)
      ) as ProfileTargetRecord[];
      const toReset = records.filter((record) => collectedRepositoryStatusSet.has(record.status));
      if (toReset.length === 0) {
        return { backend: PROFILE_TARGETS_DB_BACKEND, reset_count: 0, degraded: false, degraded_reason: null };
      }
      const writeTransaction = db.transaction(PROFILE_TARGETS_STORE_NAME, "readwrite");
      const store = writeTransaction.objectStore(PROFILE_TARGETS_STORE_NAME);
      for (const record of toReset) {
        store.put(resetCollectedRecordToPending(record, at));
      }
      await transactionDone(writeTransaction);
      return { backend: PROFILE_TARGETS_DB_BACKEND, reset_count: toReset.length, degraded: false, degraded_reason: null };
    } finally {
      db.close();
    }
  }

  async getCheckpoint(profileIdentifier: string): Promise<ProfileTargetCursorCheckpoint | null> {
    const db = await this.db();
    try {
      const transaction = db.transaction(PROFILE_TARGET_CHECKPOINTS_STORE_NAME, "readonly");
      const record = await requestToPromise(transaction.objectStore(PROFILE_TARGET_CHECKPOINTS_STORE_NAME).get(profileIdentifier)) as { checkpoint?: ProfileTargetCursorCheckpoint } | undefined;
      return record?.checkpoint ?? null;
    } finally {
      db.close();
    }
  }

  async setCheckpoint(profileIdentifier: string, checkpoint: ProfileTargetCursorCheckpoint): Promise<void> {
    const db = await this.db();
    try {
      const transaction = db.transaction(PROFILE_TARGET_CHECKPOINTS_STORE_NAME, "readwrite");
      transaction.objectStore(PROFILE_TARGET_CHECKPOINTS_STORE_NAME).put({ profile_identifier: profileIdentifier, checkpoint });
      await transactionDone(transaction);
    } finally {
      db.close();
    }
  }
}

export class FallbackProfileTargetRepository implements ProfileTargetRepository {
  constructor(private readonly primary: ProfileTargetRepository, private readonly fallback: InMemoryProfileTargetRepository = new InMemoryProfileTargetRepository()) {}

  private degraded<T extends { backend: ProfileTargetStorageBackend; degraded: boolean; degraded_reason: string | null }>(result: T, reason: string): T {
    return { ...result, degraded: true, degraded_reason: reason };
  }

  async upsertProfileTargets(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult> {
    try {
      return await this.primary.upsertProfileTargets(profileIdentifier, queue, targetDetails, at);
    } catch (error) {
      return this.degraded(await this.fallback.upsertProfileTargets(profileIdentifier, queue, targetDetails, at), error instanceof Error ? error.message : String(error));
    }
  }

  async upsertProfileTargetPage(profileIdentifier: string, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], at: string): Promise<ProfileTargetUpsertResult> {
    try {
      return await this.primary.upsertProfileTargetPage(profileIdentifier, queue, targetDetails, at);
    } catch (error) {
      return this.degraded(await this.fallback.upsertProfileTargetPage(profileIdentifier, queue, targetDetails, at), error instanceof Error ? error.message : String(error));
    }
  }

  async getProfileTargetsByStatus(profileIdentifier: string, statuses: WholeProfileHarvestQueueStatus[], limit: number, offset = 0): Promise<ProfileTargetWindowResult> {
    try {
      return await this.primary.getProfileTargetsByStatus(profileIdentifier, statuses, limit, offset);
    } catch (error) {
      return this.degraded(await this.fallback.getProfileTargetsByStatus(profileIdentifier, statuses, limit, offset), error instanceof Error ? error.message : String(error));
    }
  }

  async countProfileTargets(profileIdentifier: string, statuses?: WholeProfileHarvestQueueStatus[]): Promise<ProfileTargetWindowResult> {
    try {
      return await this.primary.countProfileTargets(profileIdentifier, statuses);
    } catch (error) {
      return this.degraded(await this.fallback.countProfileTargets(profileIdentifier, statuses), error instanceof Error ? error.message : String(error));
    }
  }

  async countProfileTargetsByStatus(profileIdentifier: string): Promise<{ backend: ProfileTargetStorageBackend; total: number; counts: ProfileTargetStatusCount[]; degraded: boolean; degraded_reason: string | null }> {
    try {
      return await this.primary.countProfileTargetsByStatus(profileIdentifier);
    } catch (error) {
      return this.degraded(await this.fallback.countProfileTargetsByStatus(profileIdentifier), error instanceof Error ? error.message : String(error));
    }
  }

  async updateTargetStatus(profileIdentifier: string, awemeId: string, patch: Partial<Pick<ProfileTargetRecord, "status" | "attempts" | "updated_at">>, checkpoint?: ProfileTargetCursorCheckpoint): Promise<ProfileTargetUpsertResult> {
    try {
      return await this.primary.updateTargetStatus(profileIdentifier, awemeId, patch, checkpoint);
    } catch (error) {
      return this.degraded(await this.fallback.updateTargetStatus(profileIdentifier, awemeId, patch, checkpoint), error instanceof Error ? error.message : String(error));
    }
  }

  async resetCollectedTargetsToPending(profileIdentifier: string, at: string): Promise<ProfileTargetResetCollectedResult> {
    try {
      return await this.primary.resetCollectedTargetsToPending(profileIdentifier, at);
    } catch (error) {
      return this.degraded(await this.fallback.resetCollectedTargetsToPending(profileIdentifier, at), error instanceof Error ? error.message : String(error));
    }
  }

  async getCheckpoint(profileIdentifier: string): Promise<ProfileTargetCursorCheckpoint | null> {
    try {
      return await this.primary.getCheckpoint(profileIdentifier);
    } catch {
      return this.fallback.getCheckpoint(profileIdentifier);
    }
  }

  async setCheckpoint(profileIdentifier: string, checkpoint: ProfileTargetCursorCheckpoint): Promise<void> {
    try {
      await this.primary.setCheckpoint(profileIdentifier, checkpoint);
    } catch {
      await this.fallback.setCheckpoint(profileIdentifier, checkpoint);
    }
  }
}

let singletonRepository: ProfileTargetRepository | null = null;
let repositoryFactoryOverride: (() => ProfileTargetRepository) | null = null;

export function createProfileTargetRepository(): ProfileTargetRepository {
  if (repositoryFactoryOverride) return repositoryFactoryOverride();
  if (!singletonRepository) {
    const indexedDB = indexedDbGlobal();
    singletonRepository = indexedDB ? new FallbackProfileTargetRepository(new IndexedDbProfileTargetRepository(indexedDB)) : new InMemoryProfileTargetRepository();
  }
  return singletonRepository;
}

export function setProfileTargetRepositoryFactoryForTests(factory: (() => ProfileTargetRepository) | null): void {
  repositoryFactoryOverride = factory;
  singletonRepository = null;
}

export function resetProfileTargetRepositoryForTests(): void {
  repositoryFactoryOverride = null;
  singletonRepository = null;
  memoryRecords.clear();
  memoryCheckpoints.clear();
}

export function profileIdentifierFromUrl(profileUrl: string | null | undefined): string {
  if (!profileUrl || !profileUrl.trim()) return "unknown_profile";
  try {
    const url = new URL(profileUrl);
    return `${url.hostname}${url.pathname}`.replace(/\/+$/, "") || profileUrl;
  } catch {
    return profileUrl.trim();
  }
}

export function buildQueueWindowFromRecords(records: ProfileTargetRecord[]): { queue: WholeProfileHarvestQueueItem[]; targetDetails: WholeProfileHarvestTargetDetail[] } {
  return {
    queue: records.map((record) => ({ ...record.queue_item, index: record.sequence })),
    targetDetails: records.map((record) => ({ ...record.target_detail, index: record.sequence }))
  };
}
