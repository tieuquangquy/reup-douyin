import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pageSource = readFileSync("src/app/ops/translation-prompt/page.tsx", "utf8");
const componentSource = readFileSync("src/components/ops-console/OpsTranslationPromptPage.tsx", "utf8");
const apiSource = readFileSync("src/lib/api.ts", "utf8");
const navSource = readFileSync("src/lib/navigationConfig.ts", "utf8");

assert.match(pageSource, /OpsTranslationPromptPage/, "Ops route must mount translation prompt page");
assert.match(componentSource, /saveTranslationPrompt/, "UI must save prompt via API");
assert.match(componentSource, /fetchTranslationPrompt/, "UI must load prompt via API");
assert.doesNotMatch(componentSource, /OpsPageHeader/, "Must not duplicate Topbar title with OpsPageHeader");
assert.match(componentSource, /OpsTranslationSettingsTabs/, "Must expose sibling tabs to Translation AI");
assert.match(componentSource, /OpsPanel[\s\S]*actions=\{/, "Save actions belong on the panel, not a second header");
assert.match(componentSource, /ops-ai-page is-compact/, "Prompt page must use compact AI settings density");
assert.doesNotMatch(
  componentSource,
  /savedMessage \? \([\s\S]*ops-field-alert is-success/,
  "Save success must not duplicate a field-alert when toolbar chip is present"
);
assert.match(componentSource, /ops-connection-status is-ok/, "Save success must show compact chip near Save");
assert.doesNotMatch(
  componentSource,
  /inline-success[\s\S]*savedMessage|savedMessage[\s\S]*inline-success/,
  "Save success must not use full-width inline-success banner above the panel"
);
assert.match(apiSource, /\/ops\/translation-prompt/, "API helper must hit translation-prompt endpoints");
assert.match(navSource, /\/ops\/translation-prompt/, "Ops nav activePatterns must include translation-prompt route");
assert.match(navSource, /nav\.translationSettings/, "Ops nav uses shared Translation settings entry");

const opsHomeSource = readFileSync("src/components/ops-console/OpsHomePage.tsx", "utf8");
assert.match(opsHomeSource, /\/ops\/translation-ai/, "Ops home card links into Translation settings");

console.log("ops translation prompt tests passed");
