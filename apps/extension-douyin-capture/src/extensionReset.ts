import { createSmartState } from "./popupWorkflow.js";
import {
  CALIBRATION_STATE_STORAGE_KEYS,
  FACTORY_RESET_LOCAL_STORAGE_KEYS,
  FACTORY_RESET_SYNC_STORAGE_KEYS,
  HARVEST_STATE_STORAGE_KEYS,
  LEGACY_HARVEST_STATE_STORAGE_KEYS
} from "./storageKeys.js";
import type { SafeHarvestRunState, SmartCaptureHarvestState } from "./types.js";

export const FACTORY_RESET_CONFIRMATION_MESSAGE = "Factory reset will clear calibration, harvest progress, pending queue, and cached capture state. Backend database will not be changed. Continue?";
export const RUNNING_HARVEST_RESET_CONFIRMATION_MESSAGE = "Harvest is running. Stop and reset harvest state?";
export const RUNNING_HARVEST_CALIBRATION_RESET_MESSAGE = "Harvest is running. Stop harvest before resetting calibration.";

export type ExtensionStorageArea = {
  remove(keys: string | string[]): Promise<void>;
  set?(items: Record<string, unknown>): Promise<void>;
};

export type ExtensionResetRuntime = {
  local: ExtensionStorageArea;
  sync?: ExtensionStorageArea;
};

export type ExtensionResetResult = {
  localKeysRemoved: string[];
  syncKeysRemoved: string[];
  normalizedSmartState?: SmartCaptureHarvestState | null;
};

export async function resetHarvestState(runtime: ExtensionResetRuntime, options?: { preserveSmartShell?: boolean }): Promise<ExtensionResetResult> {
  await runtime.local.remove([...HARVEST_STATE_STORAGE_KEYS, ...LEGACY_HARVEST_STATE_STORAGE_KEYS]);
  const normalizedSmartState = options?.preserveSmartShell ? createSmartState({ current_state: "idle", next_required_action: "Run Capture current page", last_probe_status: "none", last_error: null }) : null;
  const safeHarvestIdleState: SafeHarvestRunState = {
    schema_version: "phase17c_safe_runner",
    run_id: null,
    status: "idle",
    phase: "idle",
    stop_reason: null,
    profile_url: null,
    capture_session_id: null,
    capture_id: null,
    target_aweme_ids: [],
    target_status: {},
    current_target_index: 0,
    current_aweme_id: null,
    previous_aweme_id: null,
    counts: {
      target: 0,
      updated: 0,
      failed: 0,
      skipped: 0,
      pending_flush: 0,
      flushed: 0,
      duplicates: 0,
      integrity_mismatch: 0
    },
    last_metrics: null,
    recent_items: [],
    started_at: null,
    updated_at: new Date().toISOString(),
    heartbeat_at: null,
    last_error: null
  };
  if (runtime.local.set) {
    await runtime.local.set({
      douyinSafeHarvestRun: safeHarvestIdleState,
      ...(normalizedSmartState ? { douyinSmartHarvestState: normalizedSmartState } : {})
    });
  }
  return {
    localKeysRemoved: [...HARVEST_STATE_STORAGE_KEYS, ...LEGACY_HARVEST_STATE_STORAGE_KEYS],
    syncKeysRemoved: [],
    normalizedSmartState
  };
}

export async function resetCalibrationState(runtime: ExtensionResetRuntime): Promise<ExtensionResetResult> {
  await runtime.local.remove([...CALIBRATION_STATE_STORAGE_KEYS]);
  return {
    localKeysRemoved: [...CALIBRATION_STATE_STORAGE_KEYS],
    syncKeysRemoved: []
  };
}

export async function factoryResetExtensionState(runtime: ExtensionResetRuntime): Promise<ExtensionResetResult> {
  await runtime.local.remove([...FACTORY_RESET_LOCAL_STORAGE_KEYS]);
  if (runtime.sync) await runtime.sync.remove([...FACTORY_RESET_SYNC_STORAGE_KEYS]);
  return {
    localKeysRemoved: [...FACTORY_RESET_LOCAL_STORAGE_KEYS],
    syncKeysRemoved: runtime.sync ? [...FACTORY_RESET_SYNC_STORAGE_KEYS] : []
  };
}
