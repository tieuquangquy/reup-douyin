export const LEGACY_STATE_KEYS = [
  "douyinSafeHarvestRun",
  "douyinHarvestRuntimeV2",
  "fullModalHarvestState",
  "douyinFullModalHarvestState",
  "smartHarvestState",
  "douyinSmartHarvestState",
  "harvestProgress",
  "modalHarvestProgress",
  "douyinModalWholeProfileTestRun",
  "captureSession",
  "lastCaptureSessionId",
  "douyinHarvestPendingFlushQueueV2",
  "douyinFullModalHarvestFlushQueue",
  "douyinPendingFlushQueue",
  "douyinTargetAwemeQueue",
  "douyinRetryQueue",
  "douyinFailedQueue",
] as const;

export type LegacyStateKey = (typeof LEGACY_STATE_KEYS)[number];

export type LegacyStateSummary = {
  present_keys: LegacyStateKey[];
  present_count: number;
  has_legacy_state: boolean;
};

type ChromeStorageLike = {
  get(keys: string | string[]): Promise<Record<string, unknown>>;
};

export async function getLegacyStateSummary(storage: ChromeStorageLike): Promise<LegacyStateSummary> {
  const stored = await storage.get([...LEGACY_STATE_KEYS]);
  const present_keys = LEGACY_STATE_KEYS.filter((key) => typeof stored[key] !== "undefined");
  return { present_keys, present_count: present_keys.length, has_legacy_state: present_keys.length > 0 };
}

export async function clearLegacyState(storage: { remove(keys: string[]): Promise<void> }): Promise<void> {
  // Phase 18A confirmation requirement: Clear Legacy State must not clear calibration.
  await storage.remove([...LEGACY_STATE_KEYS]);
}
