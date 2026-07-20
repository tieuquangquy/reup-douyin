import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pageSource = readFileSync("src/app/ops/caption-prompt/page.tsx", "utf8");
const wrapperSource = readFileSync(
  "src/components/ops-console/OpsCaptionPromptPage.tsx",
  "utf8"
);
const sharedSource = readFileSync(
  "src/components/ops-console/OpsPromptSetupsPage.tsx",
  "utf8"
);
const apiSource = readFileSync("src/lib/api.ts", "utf8");
const enSource = readFileSync("src/lib/i18n/en.json", "utf8");
const viSource = readFileSync("src/lib/i18n/vi.json", "utf8");

assert.match(pageSource, /OpsCaptionPromptPage/, "Ops route must mount caption prompt page");

assert.match(
  wrapperSource,
  /OpsPromptSetupsPage/,
  "Wrapper must delegate to shared OpsPromptSetupsPage"
);
assert.match(
  wrapperSource,
  /variant="caption"/,
  "Wrapper must select the caption variant"
);

assert.match(sharedSource, /export function OpsPromptSetupsPage/, "Shared component must be exported");
assert.match(
  sharedSource,
  /viewMode.*"list".*"editor"|"list" \| "editor"/s,
  "Shared component must switch between list and editor view modes"
);
assert.match(sharedSource, /createCaptionPromptProfile/, "Editor must be able to create a new caption prompt profile");
assert.match(sharedSource, /activateCaptionPromptProfile/, "Active switch must activate caption prompt profile");
assert.match(sharedSource, /saveCaptionPromptProfile/, "Editor must save prompt via profile API");
assert.match(sharedSource, /setupName/, "Editor must expose setup name field");
assert.match(
  sharedSource,
  /ops-tts-setup-table--prompt/,
  "Prompt setups table must use --prompt modifier so Actions sits on the right"
);
assert.match(sharedSource, /ops-tts-list-toolbar/, "List toolbar must reuse ops-tts-list-toolbar CSS");
assert.match(sharedSource, /ops-tts-list-header/, "Tabs + Active toolbar must share one list header row");
assert.match(sharedSource, /OpsCaptionSettingsTabs/, "Must expose sibling tabs to Caption AI");
assert.doesNotMatch(sharedSource, /testConnection|onTest\(|actionTest/, "Prompt setups must not expose a Test button");
assert.doesNotMatch(sharedSource, /Setup renamed|profileRenamed/, "Do not show a rename toast on rename");

assert.match(apiSource, /\/ops\/caption-prompt/, "API helper must hit caption-prompt endpoints");
assert.match(apiSource, /createCaptionPromptProfile/, "API helper must expose caption profile create");

for (const key of [
  "setupName",
  "setupNameHint",
  "setupNamePlaceholder",
  "profileNew",
  "profileActive",
  "profileActiveHint",
  "profileSetupsCount",
  "profileNameCol",
  "profileActiveCol",
  "profileActionsCol",
  "profileEmpty",
  "profileDeleteConfirm",
  "profileLastError",
  "profileError",
  "profileDeleted",
  "sectionProfiles",
  "actionBack",
  "actionSave",
  "previewCol",
  "loadingDetail"
]) {
  const enBlock = enSource.split('"opsCaptionPrompt"')[1] || "";
  const viBlock = viSource.split('"opsCaptionPrompt"')[1] || "";
  assert.match(enBlock, new RegExp(`"${key}"`), `en.json opsCaptionPrompt must define ${key}`);
  assert.match(viBlock, new RegExp(`"${key}"`), `vi.json opsCaptionPrompt must define ${key}`);
}

console.log("ops caption prompt tests passed");
