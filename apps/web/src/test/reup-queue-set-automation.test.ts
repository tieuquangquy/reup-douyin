/**
 * Automation level must be switchable per item and in bulk, both directions.
 * SET_AUTOMATION carries a mode, so it must never render as a bare companion button.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  automationModeOptions,
  canChangeAutomation,
  currentAutomationMode,
  filterInspectorCompanionActions
} from "../lib/reupQueueStudioState";
import type { ReupQueueItem } from "../types/reup-queue";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");
const pageSource = readFileSync(resolve(webSrc, "components/reup-queue/ReupQueuePage.tsx"), "utf8");
const actionTypeSource = readFileSync(resolve(webSrc, "types/reup-queue.ts"), "utf8");
const batchTypeSource = readFileSync(resolve(webSrc, "types/export-handoff.ts"), "utf8");

function item(overrides: Partial<ReupQueueItem> = {}): ReupQueueItem {
  return {
    id: "item-1",
    status: "WAITING_FOR_METADATA",
    media_prep_status: "WAITING_FOR_METADATA",
    available_actions: [
      { action: "SET_AUTOMATION", label: "Change automation", description: "", requires_note: false },
      { action: "CANCEL", label: "Cancel", description: "", requires_note: true }
    ],
    metadata_json: { pipeline_mode: "auto_to_render" },
    ...overrides
  } as unknown as ReupQueueItem;
}

assert.match(actionTypeSource, /"SET_AUTOMATION"/, "Single-item action union must include SET_AUTOMATION");
assert.match(batchTypeSource, /"SET_AUTOMATION"/, "Batch action union must include SET_AUTOMATION");

assert.equal(currentAutomationMode(item()), "auto_to_render");
assert.equal(currentAutomationMode(item({ metadata_json: {} } as Partial<ReupQueueItem>)), "manual");

const modes = automationModeOptions().map((option) => option.mode);
assert.deepEqual(
  modes,
  ["auto_to_render", "auto_to_tts", "manual"],
  "Full auto is offered first because it is the default path"
);
for (const option of automationModeOptions()) {
  assert.ok(option.label.length > 0, `${option.mode} needs a label`);
  assert.ok(option.description.length > 0, `${option.mode} needs a description`);
}

assert.equal(canChangeAutomation(item()), true);
assert.equal(
  canChangeAutomation(
    item({
      available_actions: [{ action: "DISMISS", label: "Dismiss", description: "", requires_note: false }]
    } as Partial<ReupQueueItem>)
  ),
  false,
  "Items the API will not accept a mode change for must not show the picker"
);

const companions = filterInspectorCompanionActions(item(), item().available_actions);
assert.ok(
  !companions.some((entry) => entry.action === "SET_AUTOMATION"),
  "SET_AUTOMATION needs a mode, so it must be excluded from generic companion buttons"
);

assert.match(
  pageSource,
  /reup-queue-automation-picker/,
  "Inspector must render a dedicated automation picker"
);
assert.match(
  pageSource,
  /pipeline_mode:[\s\S]{0,160}SET_AUTOMATION/,
  "Single-item action call must forward the chosen automation mode"
);
assert.match(
  pageSource,
  /action === "SET_AUTOMATION"[\s\S]{0,200}options\?\.pipelineMode/,
  "Batch call must forward the chosen automation mode"
);
assert.match(
  pageSource,
  /eligibility\.setAutomation/,
  "Bulk bar must offer automation changes for the selection"
);

console.log("reup-queue-set-automation tests passed");
