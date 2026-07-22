import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { buildReupScoreMemoDeps } from "../lib/useCaptureItemReupScore";
import type { CapturedItem } from "../types/capture-inbox";

const sourcePath = join(dirname(fileURLToPath(import.meta.url)), "../lib/useCaptureItemReupScore.ts");
const source = readFileSync(sourcePath, "utf8");

const minimalItem = {
  id: "capture-1",
  view_count: 100,
  estimated_views_mid: 200,
  estimated_views_min: 150,
  estimated_views_max: 250,
  like_count: 10,
  comment_count: 2,
  share_count: 1,
  favorite_count: 0,
  follower_count: null,
  duration_seconds: 30,
  posted_at: "2026-07-01T00:00:00Z",
  status: "READY",
  metadata_status: "partial",
  thumbnail_url: "https://example.com/thumb.jpg",
  duplicate_of_item_id: null,
  existing_source_video_id: null
} as CapturedItem;

const nullDeps = buildReupScoreMemoDeps(null);
const itemDeps = buildReupScoreMemoDeps(minimalItem);

assert.equal(nullDeps.length, itemDeps.length, "Reup score memo deps must keep a fixed array size when item is null");
assert.doesNotMatch(source, /item \? reupScoreMemoDeps\(item\) : \[null\]/, "Optional reup score hook must not swap memo dependency array sizes");
assert.match(source, /buildReupScoreMemoDeps\(item\)/, "Optional reup score hook must reuse the shared memo dependency builder");

console.log("useCaptureItemReupScore memo dependency tests passed");
