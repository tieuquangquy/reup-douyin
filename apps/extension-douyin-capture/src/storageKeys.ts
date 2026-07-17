import { FULL_MODAL_HARVEST_FLUSH_QUEUE_KEY } from "./flushQueue.js";
import { HYBRID_COLLECTION_DONE_KEY } from "./wholeProfileHarvest/controller.js";
import { DOUYIN_SCANNER_CALIBRATION_KEY, DOUYIN_SCANNER_STORAGE_ROOT_KEY } from "./wholeProfileHarvest/calibration.js";
import { HARVEST_PENDING_FLUSH_QUEUE_V2_KEY, HARVEST_RUNTIME_V2_KEY, LEGACY_HARVEST_STORAGE_KEYS } from "./harvestRuntimeV2.js";
import { MODAL_WHOLE_PROFILE_TEST_RUN_KEY } from "./modalWholeProfileTest.js";
import { WHOLE_PROFILE_HARVEST_STATE_KEY } from "./wholeProfileHarvest/state.js";

export const EXTENSION_STORAGE_KEYS = {
  apiBaseUrl: "apiBaseUrl",
  webAppOrigin: "webAppOrigin",
  harvestMode: "harvestMode",
  installId: "installId",
  lastCaptureSessionId: "lastCaptureSessionId",
  lastCaptureId: "lastCaptureId",
  rightRailCalibration: "douyinRightRailCalibration",
  lastProbeResult: "douyinLastProbeResult",
  smartCaptureHarvestState: "douyinSmartHarvestState",
  modalWholeProfileTestRun: MODAL_WHOLE_PROFILE_TEST_RUN_KEY,
  safeHarvestRun: "douyinSafeHarvestRun",
  harvestRuntimeV2: HARVEST_RUNTIME_V2_KEY,
  harvestPendingFlushQueueV2: HARVEST_PENDING_FLUSH_QUEUE_V2_KEY,
  fullModalHarvestState: "douyinFullModalHarvestState",
  wholeProfileHarvest: WHOLE_PROFILE_HARVEST_STATE_KEY,
  hybridCollectionDone: HYBRID_COLLECTION_DONE_KEY,
  fullModalHarvestFlushQueue: FULL_MODAL_HARVEST_FLUSH_QUEUE_KEY,
  legacyFullModalHarvestProgress: "douyinFullModalHarvestProgress",
  legacySmartCaptureHarvestState: "douyinSmartCaptureHarvestState",
  legacyTargetQueue: "douyinTargetAwemeQueue",
  legacyPendingFlushQueue: "douyinPendingFlushQueue",
  legacyRetryQueue: "douyinRetryQueue",
  legacyFailedQueue: "douyinFailedQueue",
  legacyRightRailCalibration: "rightRailCalibration"
} as const;

export const HARVEST_STATE_STORAGE_KEYS = [
  EXTENSION_STORAGE_KEYS.safeHarvestRun,
  EXTENSION_STORAGE_KEYS.harvestRuntimeV2,
  EXTENSION_STORAGE_KEYS.harvestPendingFlushQueueV2,
  EXTENSION_STORAGE_KEYS.fullModalHarvestState,
  EXTENSION_STORAGE_KEYS.fullModalHarvestFlushQueue,
  EXTENSION_STORAGE_KEYS.smartCaptureHarvestState,
  EXTENSION_STORAGE_KEYS.lastProbeResult,
  EXTENSION_STORAGE_KEYS.legacyFullModalHarvestProgress,
  EXTENSION_STORAGE_KEYS.legacySmartCaptureHarvestState,
  EXTENSION_STORAGE_KEYS.legacyTargetQueue,
  EXTENSION_STORAGE_KEYS.legacyPendingFlushQueue,
  EXTENSION_STORAGE_KEYS.legacyRetryQueue,
  EXTENSION_STORAGE_KEYS.legacyFailedQueue,
] as const;

export const LEGACY_HARVEST_STATE_STORAGE_KEYS = [...LEGACY_HARVEST_STORAGE_KEYS] as const;

export const CALIBRATION_STATE_STORAGE_KEYS = [
  EXTENSION_STORAGE_KEYS.rightRailCalibration,
  EXTENSION_STORAGE_KEYS.lastProbeResult,
  EXTENSION_STORAGE_KEYS.legacyRightRailCalibration,
  DOUYIN_SCANNER_CALIBRATION_KEY,
  DOUYIN_SCANNER_STORAGE_ROOT_KEY
] as const;

export const FACTORY_RESET_LOCAL_STORAGE_KEYS = [
  ...HARVEST_STATE_STORAGE_KEYS,
  ...CALIBRATION_STATE_STORAGE_KEYS,
  EXTENSION_STORAGE_KEYS.wholeProfileHarvest,
  EXTENSION_STORAGE_KEYS.hybridCollectionDone
] as const;

export const FACTORY_RESET_SYNC_STORAGE_KEYS = [
  EXTENSION_STORAGE_KEYS.lastCaptureSessionId,
  EXTENSION_STORAGE_KEYS.lastCaptureId
] as const;
