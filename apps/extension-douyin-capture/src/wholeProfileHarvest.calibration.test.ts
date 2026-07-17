import assert from "node:assert/strict";

import {
  DOUYIN_SCANNER_CALIBRATION_KEY,
  DOUYIN_SCANNER_STORAGE_ROOT_KEY,
  normalizeDouyinCalibration,
  syncDouyinCalibrationFromStorage
} from "./wholeProfileHarvest/calibration.js";

class MemoryStorage {
  public values: Record<string, unknown> = {};
  public setCalls = 0;

  async get(keys: string | string[]): Promise<Record<string, unknown>> {
    const list = Array.isArray(keys) ? keys : [keys];
    return Object.fromEntries(list.map((key) => [key, this.values[key]]));
  }

  async set(items: Record<string, unknown>): Promise<void> {
    this.setCalls += 1;
    this.values = { ...this.values, ...items };
  }
}

const fourPointLegacy = {
  version: "phase13h_four_point_calibration",
  viewport_width: 1920,
  viewport_height: 1080,
  points: {
    like_count: { x: 1, y: 2, x_ratio: 0.1, y_ratio: 0.2 },
    comment_count: { x: 3, y: 4, x_ratio: 0.2, y_ratio: 0.3 },
    favourite_count: { x: 5, y: 6, x_ratio: 0.3, y_ratio: 0.4 },
    share_count: { x: 7, y: 8, x_ratio: 0.4, y_ratio: 0.5 }
  },
  created_at: "2026-05-07T12:00:00.000Z",
  profile_url_host: "www.douyin.com"
};

{
  const normalized = normalizeDouyinCalibration(fourPointLegacy);
  assert.equal(normalized.ready, true);
  assert.equal(normalized.status, "calibrated");
  assert.equal(normalized.point_count, 4);
  assert.deepEqual(normalized.missing_points, []);
  assert.ok(normalized.points.favorite, "favourite/favourite_count must normalize to canonical favorite");
}

{
  const normalized = normalizeDouyinCalibration({ points: { like_count: {}, comment_count: {}, favorite_count: {} } });
  assert.equal(normalized.ready, false, "calibration cannot be ready with fewer than four points");
  assert.equal(normalized.status, "needed");
  assert.equal(normalized.point_count, 3);
  assert.deepEqual(normalized.missing_points, ["share"]);
}

{
  const storage = new MemoryStorage();
  storage.values.douyinRightRailCalibration = fourPointLegacy;
  const synced = await syncDouyinCalibrationFromStorage(storage, "2026-05-07T12:30:00.000Z");
  assert.equal(synced.ready, true);
  assert.equal(synced.status, "calibrated");
  assert.equal(synced.source, "chrome_storage");
  assert.equal(synced.migrated_from_legacy, true);
  assert.equal(synced.updated_at, "2026-05-07T12:00:00.000Z");
  assert.equal(storage.setCalls, 1, "legacy migration should persist canonical calibration once");
  assert.deepEqual(storage.values[DOUYIN_SCANNER_CALIBRATION_KEY], synced, "sync writes canonical scanner calibration key");
  assert.deepEqual(storage.values[DOUYIN_SCANNER_STORAGE_ROOT_KEY], { calibration: synced }, "sync writes canonical scanner root bridge");
}

{
  const storage = new MemoryStorage();
  const canonical = normalizeDouyinCalibration(fourPointLegacy, {
    source: "canonical",
    migrated_from_legacy: false,
    storage_keys_checked_count: 8
  });
  storage.values[DOUYIN_SCANNER_CALIBRATION_KEY] = canonical;
  storage.values[DOUYIN_SCANNER_STORAGE_ROOT_KEY] = { calibration: canonical };
  const synced = await syncDouyinCalibrationFromStorage(storage, "2026-05-07T12:30:00.000Z");
  assert.deepEqual(synced, canonical, "sync should keep canonical calibration stable when nothing changed");
  assert.equal(storage.setCalls, 0, "sync should not rewrite identical canonical calibration");
}

{
  const storage = new MemoryStorage();
  storage.values.rightRailCalibration = { points: { like_count: {}, comment_count: {}, share_count: {} } };
  const synced = await syncDouyinCalibrationFromStorage(storage, "2026-05-07T12:30:00.000Z");
  assert.equal(synced.ready, false);
  assert.equal(synced.status, "needed");
  assert.equal(synced.point_count, 3);
  assert.deepEqual(synced.missing_points, ["favorite"]);
}

console.log("whole profile calibration bridge tests passed");
