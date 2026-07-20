import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pageSource = readFileSync("src/app/ops/translation-prompt/page.tsx", "utf8");
const wrapperSource = readFileSync(
  "src/components/ops-console/OpsTranslationPromptPage.tsx",
  "utf8"
);
const sharedSource = readFileSync(
  "src/components/ops-console/OpsPromptSetupsPage.tsx",
  "utf8"
);
const apiSource = readFileSync("src/lib/api.ts", "utf8");
const navSource = readFileSync("src/lib/navigationConfig.ts", "utf8");
const cssSource = readFileSync("src/app/globals.css", "utf8");
const enSource = readFileSync("src/lib/i18n/en.json", "utf8");
const viSource = readFileSync("src/lib/i18n/vi.json", "utf8");

assert.match(pageSource, /OpsTranslationPromptPage/, "Ops route must mount translation prompt page");

assert.match(
  wrapperSource,
  /OpsPromptSetupsPage/,
  "Wrapper must delegate to shared OpsPromptSetupsPage"
);
assert.match(
  wrapperSource,
  /variant="translation"/,
  "Wrapper must select the translation variant"
);

assert.match(
  sharedSource,
  /export function OpsPromptSetupsPage/,
  "Shared component must be exported as OpsPromptSetupsPage"
);
assert.match(
  sharedSource,
  /viewMode.*"list".*"editor"|"list" \| "editor"/s,
  "Shared component must switch between list and editor view modes"
);
assert.match(sharedSource, /createTranslationPromptProfile/, "Editor must be able to create a new translation prompt profile");
assert.match(sharedSource, /activateTranslationPromptProfile/, "Active switch must activate translation prompt profile");
assert.match(sharedSource, /saveTranslationPromptProfile/, "Editor must save prompt via profile API");
assert.match(sharedSource, /setupName/, "Editor must expose setup name field");
assert.match(
  sharedSource,
  /function applyEditorResponse[\s\S]*?focus_profile_id[\s\S]*?setEditingProfileId/,
  "After Save, editor must stay on focus_profile_id (not jump to active prompt)"
);
assert.match(
  sharedSource,
  /ops-tts-setup-table--prompt/,
  "Prompt setups table must use --prompt modifier so Actions sits on the right"
);
assert.match(
  cssSource,
  /\.ops-tts-setup-table--prompt[\s\S]*?text-align:\s*right/,
  "Prompt table CSS must right-align the Actions column"
);
assert.match(sharedSource, /ops-tts-list-toolbar/, "List toolbar must reuse ops-tts-list-toolbar CSS");
assert.match(sharedSource, /ops-tts-list-header/, "Tabs + Active toolbar must share one list header row");
assert.match(sharedSource, /OpsTranslationSettingsTabs/, "Must expose sibling tabs to Translation AI");
assert.match(sharedSource, /OpsConsoleShell/, "Shared component must wrap itself in OpsConsoleShell");
assert.doesNotMatch(sharedSource, /testConnection|onTest\(|actionTest/, "Prompt setups must not expose a Test button");
assert.doesNotMatch(sharedSource, /Setup renamed|profileRenamed/, "Do not show a rename toast on rename");
assert.match(sharedSource, /ops-ai-page is-compact/, "Prompt page must keep compact AI settings density");

assert.match(apiSource, /\/ops\/translation-prompt/, "API helper must hit translation-prompt endpoints");
assert.match(apiSource, /createTranslationPromptProfile/, "API helper must expose profile create");
assert.match(navSource, /\/ops\/translation-prompt/, "Ops nav activePatterns must include translation-prompt route");

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
  const enBlock = enSource.split('"opsTranslationPrompt"')[1] || "";
  const viBlock = viSource.split('"opsTranslationPrompt"')[1] || "";
  assert.match(enBlock, new RegExp(`"${key}"`), `en.json opsTranslationPrompt must define ${key}`);
  assert.match(viBlock, new RegExp(`"${key}"`), `vi.json opsTranslationPrompt must define ${key}`);
}

console.log("ops translation prompt tests passed");
