import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { isSetupTableInteractiveDragTarget, moveItemIndex, profileIdsOf } from "../lib/opsProfileReorder";

assert.deepEqual(moveItemIndex(["a", "b", "c"], 0, 2), ["b", "c", "a"]);
assert.deepEqual(moveItemIndex(["a", "b", "c"], 2, 0), ["c", "a", "b"]);
assert.deepEqual(moveItemIndex(["a", "b", "c"], 1, 1), ["a", "b", "c"]);
assert.deepEqual(profileIdsOf([{ id: "1" }, { id: "2" }]), ["1", "2"]);
assert.equal(isSetupTableInteractiveDragTarget(null), false);

const llm = readFileSync("src/components/ops-console/OpsLlmAiSetupsPage.tsx", "utf8");
const tts = readFileSync("src/components/ops-console/OpsTtsAiPage.tsx", "utf8");
const prompt = readFileSync("src/components/ops-console/OpsPromptSetupsPage.tsx", "utf8");
const api = readFileSync("src/lib/api.ts", "utf8");
const css = readFileSync("src/app/globals.css", "utf8");
const en = JSON.parse(readFileSync("src/lib/i18n/en.json", "utf8")) as {
  common?: Record<string, string>;
};
const vi = JSON.parse(readFileSync("src/lib/i18n/vi.json", "utf8")) as {
  common?: Record<string, string>;
};

for (const [label, source] of [
  ["LLM", llm],
  ["TTS", tts],
  ["Prompt", prompt]
] as const) {
  assert.match(source, /ops-tts-setup-table__drag-handle/, `${label} table must expose a drag affordance`);
  assert.match(source, /draggable=\{canDrag\}/, `${label} must make the whole row draggable`);
  assert.match(source, /isSetupTableInteractiveDragTarget/, `${label} must ignore drags from buttons/inputs`);
  assert.match(source, /onReorderProfiles/, `${label} must persist row reorder`);
  assert.match(source, /moveItemIndex/, `${label} must reorder locally before save`);
}

assert.match(api, /reorderTranslationAiProfiles/, "API helper must reorder translation AI setups");
assert.match(api, /reorderCaptionAiProfiles/, "API helper must reorder caption AI setups");
assert.match(api, /reorderTtsAiProfiles/, "API helper must reorder TTS setups");
assert.match(api, /reorderTranslationPromptProfiles/, "API helper must reorder translation prompts");
assert.match(api, /reorderCaptionPromptProfiles/, "API helper must reorder caption prompts");
assert.match(api, /\/profiles\/reorder/, "Reorder must hit Ops profiles/reorder endpoints");
assert.match(css, /\.ops-tts-setup-table__drag-handle/, "CSS must style drag handles");
assert.ok(en.common?.dragToReorder, "en.common.dragToReorder must exist");
assert.ok(vi.common?.dragToReorder, "vi.common.dragToReorder must exist");

console.log("ops profile reorder tests passed");
