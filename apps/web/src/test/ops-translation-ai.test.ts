import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { formatConnectionTestSummary, formatProviderError } from "../lib/opsTranslationAiFormat";

const pageSource = readFileSync("src/app/ops/translation-ai/page.tsx", "utf8");
const componentSource = readFileSync("src/components/ops-console/OpsTranslationAiPage.tsx", "utf8");
const apiSource = readFileSync("src/lib/api.ts", "utf8");
const navSource = readFileSync("src/lib/navigationConfig.ts", "utf8");
const opsHomeSource = readFileSync("src/components/ops-console/OpsHomePage.tsx", "utf8");

assert.match(pageSource, /OpsTranslationAiPage/, "Ops route must mount Translation AI page");
assert.match(componentSource, /fetchTranslationAi/, "UI must load Translation AI via API");
assert.match(componentSource, /saveTranslationAi/, "UI must save Translation AI via API");
assert.match(componentSource, /testTranslationAi/, "UI must support Test connection");
assert.match(componentSource, /formatConnectionTestSummary/, "Successful test must use compact summary formatter");
assert.match(componentSource, /ops-connection-status is-ok/, "Successful test/save renders compact toolbar chip only");
assert.doesNotMatch(
  componentSource,
  /savedMessage \? \([\s\S]*ops-field-alert is-success/,
  "Save success must not use a second field alert under the panel"
);
assert.doesNotMatch(
  componentSource,
  /inline-success[\s\S]*savedMessage|savedMessage[\s\S]*inline-success/,
  "Save success must not use full-width inline-success banner above the panel"
);
assert.match(componentSource, /testFailure/, "Failed test must use structured failure alert");
assert.match(
  componentSource,
  /testResult\?\.ok[\s\S]*ops-connection-status/,
  "Failed Test connection must not use the cramped header pill"
);
assert.doesNotMatch(
  componentSource,
  /testMessage\.startsWith\(t\("opsTranslationAi\.testOk"\)\)/,
  "Must not treat test status as a full-width inline-success banner"
);
assert.match(componentSource, /listTranslationAiModels/, "UI must load model list after credentials");
assert.match(componentSource, /modelListReady|canShowModel/, "UI must gate Model until provider credentials are ready");
assert.doesNotMatch(componentSource, /OpsPageHeader/, "Must not duplicate Topbar title with OpsPageHeader");

assert.equal(
  formatConnectionTestSummary({ ok: true, provider: "openai_compatible", detail: "OK" }, { ok: "Connected", fail: "Failed" }),
  "Connected · openai_compatible",
  "Trivial OK ping reply must not duplicate status text"
);
assert.equal(
  formatConnectionTestSummary(
    { ok: false, provider: "gemini", detail: "gemini_http_429:quota" },
    { ok: "Connected", fail: "Failed" }
  ),
  "Failed · gemini — gemini_http_429:quota",
  "Failure detail must remain visible"
);
assert.match(componentSource, /formatProviderError/, "Model list errors must use provider error formatter");
assert.match(componentSource, /ops-field-alert/, "Model list errors must render as a field alert, not raw muted dump");
assert.doesNotMatch(componentSource, /ops-muted">\{modelListDetail\}/, "Must not dump raw list_models payload into muted text");

const openai401 = formatProviderError(
  'list_models_http_401:{ "error": { "message": "Incorrect API key provided: sk-9bea4***************3270. You can find your API key at https://platform.openai.com/account/api-keys.", "type": "invalid_request_error" } }',
  {
    unauthorized: "Invalid API key",
    forbidden: "Access denied",
    notFound: "Endpoint not found",
    rateLimited: "Rate limited",
    failed: "Could not load models",
    checkKey: "Check the API key and try again.",
    checkEndpoint: "Check Base URL and provider, then try again."
  }
);
assert.equal(openai401.title, "Invalid API key");
assert.equal(openai401.httpStatus, 401);
assert.match(openai401.message, /Incorrect API key/i);
assert.doesNotMatch(openai401.message, /list_models_http/);
assert.doesNotMatch(openai401.message, /"type"/);

const gemini429 = formatProviderError(
  'gemini_http_429:{ "error": { "code": 429, "message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED" } }',
  {
    unauthorized: "Invalid API key",
    forbidden: "Access denied",
    notFound: "Endpoint not found",
    rateLimited: "Rate limited",
    failed: "Could not load models",
    checkKey: "Check the API key and try again.",
    checkEndpoint: "Check Base URL and provider, then try again."
  }
);
assert.equal(gemini429.title, "Rate limited");
assert.equal(gemini429.httpStatus, 429);
assert.match(gemini429.message, /Resource exhausted|Rate limited/i);
assert.doesNotMatch(gemini429.message, /gemini_http_429/);
assert.match(componentSource, /OpsTranslationSettingsTabs/, "Must expose sibling tabs to Translation prompt");
assert.match(componentSource, /OpsPanel[\s\S]*actions=\{/, "Save/Test actions belong on the panel, not a second header");
assert.match(apiSource, /\/ops\/translation-ai\/models/, "API helper must hit translation-ai models endpoint");
assert.match(apiSource, /\/ops\/translation-ai/, "API helper must hit translation-ai endpoints");
assert.match(navSource, /nav\.translationSettings/, "Ops nav must use shared Translation settings label");
assert.match(
  navSource,
  /sectionAiSettings[\s\S]*?translationSettings[\s\S]*?captionAiSettings[\s\S]*?ttsSettings/,
  "AI Settings must list Translation, Caption, and TTS together"
);
assert.doesNotMatch(
  navSource,
  /sectionAiSettings[\s\S]*?translationAi[\s\S]*?translationPrompt/,
  "AI Settings must not list Translation AI and Translation prompt as separate sidebar items"
);
assert.match(navSource, /activePatterns: \["\/ops\/translation-ai", "\/ops\/translation-prompt"\]/, "Sidebar item active on both translation settings routes");
assert.doesNotMatch(navSource, /export const topbarQuickActions/, "Topbar quick-nav actions must stay removed");
assert.match(opsHomeSource, /nav\.translationSettings/, "Ops home must surface one Translation settings card");
assert.doesNotMatch(opsHomeSource, /nav\.translationPrompt"/, "Ops home must not list a separate Translation prompt card");

console.log("ops translation ai tests passed");
