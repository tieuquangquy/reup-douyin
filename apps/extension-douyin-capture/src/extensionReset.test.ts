import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DOUYIN_SCANNER_CALIBRATION_KEY, DOUYIN_SCANNER_STORAGE_ROOT_KEY } from "./wholeProfileHarvest/calibration.js";
import { clearLegacyState, LEGACY_STATE_KEYS } from "./legacy/legacyStateKeys.js";
import {
  FACTORY_RESET_CONFIRMATION_MESSAGE,
  factoryResetExtensionState,
  resetCalibrationState,
  resetHarvestState
} from "./extensionReset.js";
import {
  CALIBRATION_STATE_STORAGE_KEYS,
  EXTENSION_STORAGE_KEYS,
  FACTORY_RESET_LOCAL_STORAGE_KEYS,
  FACTORY_RESET_SYNC_STORAGE_KEYS,
  HARVEST_STATE_STORAGE_KEYS,
  LEGACY_HARVEST_STATE_STORAGE_KEYS
} from "./storageKeys.js";

class FakeStorageArea {
  public values = new Map<string, unknown>();
  public removed: string[] = [];

  async remove(keys: string | string[]): Promise<void> {
    const list = Array.isArray(keys) ? keys : [keys];
    this.removed.push(...list);
    for (const key of list) this.values.delete(key);
  }

  async set(items: Record<string, unknown>): Promise<void> {
    for (const [key, value] of Object.entries(items)) this.values.set(key, value);
  }
}

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf-8");
const popupCss = readFileSync(new URL("../public/popup.css", import.meta.url), "utf-8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf-8");
const contentScriptSource = readFileSync(new URL("./contentScript.ts", import.meta.url), "utf-8");

const explicitStorageKeyGroups = [
  HARVEST_STATE_STORAGE_KEYS,
  LEGACY_HARVEST_STATE_STORAGE_KEYS,
  CALIBRATION_STATE_STORAGE_KEYS,
  FACTORY_RESET_LOCAL_STORAGE_KEYS,
  FACTORY_RESET_SYNC_STORAGE_KEYS,
  LEGACY_STATE_KEYS
] as const;

const calibrationStorageKeys = [
  EXTENSION_STORAGE_KEYS.rightRailCalibration,
  EXTENSION_STORAGE_KEYS.legacyRightRailCalibration,
  DOUYIN_SCANNER_CALIBRATION_KEY,
  DOUYIN_SCANNER_STORAGE_ROOT_KEY
] as const;

assert.notEqual(DOUYIN_SCANNER_STORAGE_ROOT_KEY, DOUYIN_SCANNER_CALIBRATION_KEY, "canonical scanner storage root and calibration keys must remain distinct");

for (const calibrationKey of calibrationStorageKeys) {
  assert.equal((HARVEST_STATE_STORAGE_KEYS as readonly string[]).includes(calibrationKey), false, `Reset Harvest key group must not include calibration key ${calibrationKey}`);
  assert.equal((LEGACY_STATE_KEYS as readonly string[]).includes(calibrationKey), false, `Clear Legacy State key group must not include calibration key ${calibrationKey}`);
}

assert.equal(CALIBRATION_STATE_STORAGE_KEYS.includes(EXTENSION_STORAGE_KEYS.rightRailCalibration), true, "Reset Calibration includes canonical right rail calibration");
assert.equal(CALIBRATION_STATE_STORAGE_KEYS.includes(EXTENSION_STORAGE_KEYS.legacyRightRailCalibration), true, "Reset Calibration includes legacy right rail calibration alias");
assert.equal(CALIBRATION_STATE_STORAGE_KEYS.includes(DOUYIN_SCANNER_CALIBRATION_KEY), true, "Reset Calibration includes canonical scanner calibration key");
assert.equal(CALIBRATION_STATE_STORAGE_KEYS.includes(DOUYIN_SCANNER_STORAGE_ROOT_KEY), true, "Reset Calibration includes canonical scanner storage root bridge");
assert.equal(CALIBRATION_STATE_STORAGE_KEYS.includes(EXTENSION_STORAGE_KEYS.lastProbeResult), true, "Reset Calibration includes the current probe result key by design");

for (const key of HARVEST_STATE_STORAGE_KEYS) assert.equal(FACTORY_RESET_LOCAL_STORAGE_KEYS.includes(key), true, `Factory Reset local keys include harvest key ${key}`);
for (const key of CALIBRATION_STATE_STORAGE_KEYS) assert.equal(FACTORY_RESET_LOCAL_STORAGE_KEYS.includes(key), true, `Factory Reset local keys include calibration key ${key}`);
assert.equal(FACTORY_RESET_SYNC_STORAGE_KEYS.includes(EXTENSION_STORAGE_KEYS.lastCaptureSessionId), true, "Factory Reset sync keys include last capture session id");
assert.equal(FACTORY_RESET_SYNC_STORAGE_KEYS.includes(EXTENSION_STORAGE_KEYS.lastCaptureId), true, "Factory Reset sync keys include last capture id");
assert.equal(FACTORY_RESET_SYNC_STORAGE_KEYS.length, 2, "Factory Reset sync scope remains limited to capture/session ids");

for (const group of explicitStorageKeyGroups) {
  for (const key of group) assert.doesNotMatch(key, /token|authorization|cookie|password|secret/i, `storage key group must not include secret-like key ${key}`);
}

{
  const local = new FakeStorageArea();
  for (const key of LEGACY_STATE_KEYS) local.values.set(key, "legacy");
  for (const key of calibrationStorageKeys) local.values.set(key, "calibration");
  await clearLegacyState(local);
  assert.deepEqual(local.removed, [...LEGACY_STATE_KEYS], "Clear Legacy State removes only the legacy quarantine key list");
  for (const key of calibrationStorageKeys) assert.equal(local.values.get(key), "calibration", `Clear Legacy State preserves calibration key ${key}`);
}

{
  const local = new FakeStorageArea();
  local.values.set(EXTENSION_STORAGE_KEYS.apiBaseUrl, "http://127.0.0.1:8000");
  local.values.set(EXTENSION_STORAGE_KEYS.rightRailCalibration, { version: "phase13h_four_point_calibration" });
  local.values.set(DOUYIN_SCANNER_CALIBRATION_KEY, { status: "calibrated", point_count: 4 });
  local.values.set(DOUYIN_SCANNER_STORAGE_ROOT_KEY, { calibration: { status: "calibrated", point_count: 4 } });
  for (const key of HARVEST_STATE_STORAGE_KEYS) local.values.set(key, "stale");
  for (const key of LEGACY_HARVEST_STATE_STORAGE_KEYS) local.values.set(key, "stale");
  const result = await resetHarvestState({ local });
  assert.deepEqual(result.localKeysRemoved, [...HARVEST_STATE_STORAGE_KEYS, ...LEGACY_HARVEST_STATE_STORAGE_KEYS]);
  assert.equal(local.values.get(EXTENSION_STORAGE_KEYS.apiBaseUrl), "http://127.0.0.1:8000", "Reset Harvest State preserves API base URL");
  assert.equal(local.values.has(EXTENSION_STORAGE_KEYS.safeHarvestRun), true, "Reset Harvest State seeds safe harvest idle state");
  assert.deepEqual(local.values.get(EXTENSION_STORAGE_KEYS.rightRailCalibration), { version: "phase13h_four_point_calibration" }, "Reset Harvest State preserves calibration");
  assert.deepEqual(local.values.get(DOUYIN_SCANNER_CALIBRATION_KEY), { status: "calibrated", point_count: 4 }, "Reset Harvest State preserves canonical scanner calibration");
  assert.deepEqual(local.values.get(DOUYIN_SCANNER_STORAGE_ROOT_KEY), { calibration: { status: "calibrated", point_count: 4 } }, "Reset Harvest State preserves canonical scanner root calibration bridge");
  for (const key of HARVEST_STATE_STORAGE_KEYS) {
    if (key === EXTENSION_STORAGE_KEYS.safeHarvestRun) continue;
    assert.equal(local.values.has(key), false, `Reset Harvest State removes ${key}`);
  }
  for (const key of LEGACY_HARVEST_STATE_STORAGE_KEYS) assert.equal(local.values.has(key), false, `Reset Harvest State removes legacy ${key}`);
}

{
  const local = new FakeStorageArea();
  local.values.set(EXTENSION_STORAGE_KEYS.apiBaseUrl, "http://127.0.0.1:8000");
  for (const key of CALIBRATION_STATE_STORAGE_KEYS) local.values.set(key, "stale");
  const result = await resetCalibrationState({ local });
  assert.deepEqual(result.localKeysRemoved, [...CALIBRATION_STATE_STORAGE_KEYS]);
  assert.equal(local.values.get(EXTENSION_STORAGE_KEYS.apiBaseUrl), "http://127.0.0.1:8000", "Reset Calibration preserves API base URL");
  for (const key of CALIBRATION_STATE_STORAGE_KEYS) assert.equal(local.values.has(key), false, `Reset Calibration removes ${key}`);
}

{
  const local = new FakeStorageArea();
  const sync = new FakeStorageArea();
  sync.values.set(EXTENSION_STORAGE_KEYS.apiBaseUrl, "http://127.0.0.1:8000");
  sync.values.set(EXTENSION_STORAGE_KEYS.harvestMode, "new_only");
  for (const key of FACTORY_RESET_LOCAL_STORAGE_KEYS) local.values.set(key, "stale");
  for (const key of FACTORY_RESET_SYNC_STORAGE_KEYS) sync.values.set(key, "stale");
  const result = await factoryResetExtensionState({ local, sync });
  assert.deepEqual(result.localKeysRemoved, [...FACTORY_RESET_LOCAL_STORAGE_KEYS]);
  assert.deepEqual(result.syncKeysRemoved, [...FACTORY_RESET_SYNC_STORAGE_KEYS]);
  assert.equal(sync.values.get(EXTENSION_STORAGE_KEYS.apiBaseUrl), "http://127.0.0.1:8000", "Factory Reset preserves API base URL");
  for (const key of FACTORY_RESET_LOCAL_STORAGE_KEYS) assert.equal(local.values.has(key), false, `Factory Reset removes local ${key}`);
  for (const key of FACTORY_RESET_SYNC_STORAGE_KEYS) assert.equal(sync.values.has(key), false, `Factory Reset removes sync ${key}`);
}

assert.match(popupHtml, /Advanced Details/, "popup must render Advanced Details section");
assert.match(popupHtml, /id="resetWholeProfileHarvestStateButton"/, "popup must render maintenance Reset Scanner State button");
assert.match(popupHtml, /id="clearCalibrationButton"/, "popup must render calibration reset support button");
assert.match(popupHtml, /id="clearLegacyStateButton"/, "popup must render maintenance legacy cleanup button");
assert.doesNotMatch(popupHtml, /id="resetCalibrationStateButton"/, "legacy separate reset calibration button markup must be removed");
assert.doesNotMatch(popupHtml, /id="factoryResetExtensionButton"/, "legacy factory reset button markup must be removed from popup");
assert.match(popupCss, /button\.danger/, "destructive reset actions must have danger styling");
assert.match(popupSource, /FACTORY_RESET_CONFIRMATION_MESSAGE/, "Factory Reset must require explicit confirmation");
assert.match(popupSource, /RUNNING_HARVEST_RESET_CONFIRMATION_MESSAGE/, "running harvest reset must ask confirmation");
assert.match(popupSource, /REUP_DOUYIN_RESET_SAFE_HARVEST_RUN/, "reset must clear safe harvest run state");
assert.match(contentScriptSource, /resetHarvestStateV2/, "content script must implement harvest runtime v2 reset handler");
assert.match(contentScriptSource, /HARVEST_RUNTIME_V2_KEY/, "content reset must target canonical runtime v2 key");
assert.match(popupSource, /renderHarvestProgressPanel\(null\)/, "reset removes stale Harvest paused progress panel");
assert.match(popupSource, /Calibration: "missing"/, "reset calibration normalizes popup calibration state");
assert.match(FACTORY_RESET_CONFIRMATION_MESSAGE, /Backend database will not be changed/, "Factory Reset confirmation must state backend data is preserved");

console.log("extension reset controls tests passed");
