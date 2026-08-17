/**
 * Publish Handoff cargo grouping — skip stub duplicates, cluster copyable rows.
 */
import assert from "node:assert/strict";
import { buildHandoffCargo } from "../lib/handoffCargo";

const payload = {
  export_package_id: "pkg-1",
  target_platform: "FACEBOOK_REELS",
  item_count: 1,
  items: [
    {
      source_video_id: "vid-1",
      render_output_id: "rnd-1",
      reup_queue_item_id: "queue-1",
      video_candidate_id: "cand-1",
      quality_manual_export_archive: "archive.mp4",
      nested: { skip: true }
    }
  ]
};

const groups = buildHandoffCargo(payload);
const rows = groups.flatMap((group) => group.rows);

assert.equal(groups.map((group) => group.id).join(","), "media,refs", "Cargo must split media vs references");
assert.equal(
  rows.some((row) => row.key === "target_platform" || row.key.endsWith(".target_platform")),
  false,
  "Platform already on the pass stub must not repeat in cargo"
);
assert.equal(
  rows.some((row) => row.key === "export_package_id" || row.key.endsWith(".export_package_id")),
  false,
  "Package already on the pass stub must not repeat in cargo"
);
assert.ok(
  groups.find((group) => group.id === "media")?.rows.some((row) => row.key.includes("source_video_id")),
  "Media group must surface source video"
);
assert.ok(
  groups.find((group) => group.id === "media")?.rows.some((row) => row.key.includes("quality_manual_export_archive")),
  "Media group must surface the export archive"
);
assert.ok(
  groups.find((group) => group.id === "refs")?.rows.some((row) => row.key.includes("reup_queue_item_id")),
  "Reference group must keep queue/candidate ids"
);
assert.equal(
  rows.some((row) => row.key === "item_count"),
  false,
  "A single-item count must not occupy a cargo row"
);
assert.equal(
  groups.find((group) => group.id === "media")?.rows.find((row) => row.key.includes("source_video_id"))?.label,
  "Video",
  "Cargo labels must stay short"
);
assert.ok(
  buildHandoffCargo({ ...payload, item_count: 3 })
    .flatMap((group) => group.rows)
    .some((row) => row.key === "item_count" && row.value === "3"),
  "Item count must still show when more than one item"
);
assert.equal(
  rows.some((row) => row.key.includes("nested")),
  false,
  "Nested objects stay in inspect JSON, not cargo"
);
assert.deepEqual(buildHandoffCargo(null), []);

console.log("handoff-cargo tests passed");
