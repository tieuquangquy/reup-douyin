/**
 * A clip parked by the work-in-progress cap must look queued, not stuck.
 *
 * The lane admits a bounded number of clips; the rest wait with their chosen automation
 * mode and start themselves. Without a visible label the operator sees an untouched item
 * and presses Start auto again, which is exactly the pile-up the cap exists to prevent.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import {
  isAwaitingPipelineSlot,
  pipelineStepChipLabel,
  queueTileNextStepHint
} from "../lib/reupQueueStudioState";
import type { ReupQueueItem } from "../types/reup-queue";

const here = dirname(fileURLToPath(import.meta.url));

function item(overrides: Partial<ReupQueueItem> = {}): ReupQueueItem {
  return {
    id: "item-1",
    workspace_id: "ws-1",
    video_candidate_id: "cand-1",
    source_video_id: "src-1",
    status: "READY_FOR_PROCESSING",
    bucket: "READY",
    next_action: null,
    held_at: null,
    metadata_json: {},
    created_at: "2026-07-26T09:00:00Z",
    updated_at: "2026-07-26T09:00:00Z",
    ...overrides
  } as ReupQueueItem;
}

const parked = item({
  metadata_json: { pipeline_mode: "auto_to_render", pipeline_awaiting_slot: true }
});

assert.equal(isAwaitingPipelineSlot(parked), true, "A parked clip must be recognisable");
assert.equal(
  isAwaitingPipelineSlot(item({ metadata_json: { pipeline_mode: "auto_to_render", pipeline_step: "ocr" } })),
  false,
  "A working clip is not waiting for a slot"
);
assert.equal(isAwaitingPipelineSlot(item()), false, "A plain item is not waiting for a slot");

assert.equal(
  pipelineStepChipLabel(parked),
  "Auto · Queued",
  "The tile chip must say the clip is queued, not blank or mid-step"
);

assert.equal(
  pipelineStepChipLabel(
    item({ held_at: "2026-07-26T09:10:00Z", metadata_json: { pipeline_mode: "auto_to_render", pipeline_awaiting_slot: true } })
  ),
  "Auto · Paused",
  "An explicit pause still outranks the queue label"
);

const hint = queueTileNextStepHint(parked);
assert.ok(hint, "A parked clip needs a hint explaining the wait");
assert.match(
  String(hint),
  /automatic/i,
  "The hint must promise the clip starts on its own so nobody re-presses Start auto"
);

const pageSource = readFileSync(join(here, "../components/reup-queue/ReupQueuePage.tsx"), "utf8");
assert.match(
  pageSource,
  /pipelineStepChipLabel/,
  "The queue tile keeps rendering the pipeline chip that now carries the queued state"
);

const capBlock = pageSource.slice(
  pageSource.indexOf("let preflightCapNotice"),
  pageSource.indexOf("capStartProcessingBatchIds(itemIds)")
);
assert.doesNotMatch(
  capBlock,
  /START_AUTO_PIPELINE/,
  "Start auto must send every selected clip; the lane parks the overflow instead of dropping it"
);
assert.match(
  capBlock,
  /action === "START_PROCESSING"/,
  "The manual start keeps its download-session batch cap"
);

console.log("reup-queue-slot-wait tests passed");
