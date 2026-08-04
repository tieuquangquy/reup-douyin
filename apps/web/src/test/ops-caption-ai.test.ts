import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { captionModelListReady, captionCanShowModel } from "../components/ops-console/OpsCaptionAiPage";

const pageSource = readFileSync("src/app/ops/caption-ai/page.tsx", "utf8");
const wrapperSource = readFileSync("src/components/ops-console/OpsCaptionAiPage.tsx", "utf8");
const sharedSource = readFileSync("src/components/ops-console/OpsLlmAiSetupsPage.tsx", "utf8");
const componentSource = wrapperSource + "\n" + sharedSource;
const apiSource = readFileSync("src/lib/api.ts", "utf8");
const enJson = JSON.parse(readFileSync("src/lib/i18n/en.json", "utf8")) as Record<string, Record<string, string>>;
const viJson = JSON.parse(readFileSync("src/lib/i18n/vi.json", "utf8")) as Record<string, Record<string, string>>;

assert.match(pageSource, /OpsCaptionAiPage/, "Ops route must mount Caption AI page");
assert.match(wrapperSource, /OpsLlmAiSetupsPage/, "Caption AI wrapper must delegate to shared setups page");
assert.match(wrapperSource, /variant=["']caption["']/, "Wrapper must pass caption variant to shared page");
assert.match(wrapperSource, /export\s+function\s+OpsCaptionAiPage/, "Wrapper must export OpsCaptionAiPage");
assert.match(
  wrapperSource,
  /export\s+\{[^}]*captionModelListReady[\s\S]*?captionCanShowModel[^}]*\}/,
  "Wrapper must re-export captionModelListReady + captionCanShowModel"
);

// Shared file must include caption profile helpers wired for caption variant.
assert.match(sharedSource, /fetchCaptionAi\b/, "Shared page must load caption via fetchCaptionAi when caption variant");
assert.match(sharedSource, /saveCaptionAiProfile\b/, "Shared page must save caption via caption profile helper");
assert.match(sharedSource, /createCaptionAiProfile\b/, "Shared page must create caption setups via createCaptionAiProfile");
assert.match(sharedSource, /fetchCaptionAiProfile\b/, "Shared page must open caption editors via fetchCaptionAiProfile");
assert.match(sharedSource, /activateCaptionAiProfile\b/, "Shared page must activate caption setups via activateCaptionAiProfile");
assert.match(sharedSource, /setCaptionAiProfileEnabled\b/, "Shared page must toggle caption setups via setCaptionAiProfileEnabled");
assert.match(sharedSource, /renameCaptionAiProfile\b/, "Shared page must rename caption setups via renameCaptionAiProfile");
assert.match(sharedSource, /deleteCaptionAiProfile\b/, "Shared page must delete caption setups via deleteCaptionAiProfile");
assert.match(sharedSource, /testCaptionAi\b/, "Shared page must call testCaptionAi");
assert.match(sharedSource, /listCaptionAiModels\b/, "Shared page must list caption models via listCaptionAiModels");
assert.match(sharedSource, /OpsCaptionSettingsTabs/, "Shared page must render caption settings tabs when caption variant");
assert.match(sharedSource, /profile_id/, "Shared page must send profile_id when testing an existing setup");
assert.match(sharedSource, /viewMode/, "Shared page must maintain list/editor viewMode");
assert.match(sharedSource, /"list"\s*\|\s*"editor"/, "Shared page must model viewMode as list|editor");
assert.match(sharedSource, /editingProfileId/, "Shared page must track editingProfileId for editor mode");
assert.match(sharedSource, /ops-tts-list-toolbar/, "Shared page list mode must reuse TTS list toolbar CSS chrome");
assert.match(sharedSource, /ops-tts-list-header/, "Tabs + Active toolbar must share one list header row");
assert.match(sharedSource, /ops-tts-setup-table/, "Shared page must reuse TTS setup table CSS");
assert.match(sharedSource, /ops-ai-control-center is-\$\{variant\}/, "Translation and Caption lists must use the shared AI Setup Control Center surface");
assert.match(sharedSource, /ops-ai-registry-table is-llm/, "LLM setups must use the condensed semantic registry table");
assert.match(sharedSource, /runtimeCol[\s\S]*connectionCol/, "LLM registry must group provider/model and key/base URL into scannable columns");
assert.match(sharedSource, /ops-ai-setup-identity[\s\S]*ops-ai-inline-config/, "LLM setup identity and configuration must stay on one visual line");
assert.doesNotMatch(sharedSource, /OpsAiProviderMark/, "LLM setup names must not have decorative leading icons");
assert.match(sharedSource, /ops-ai-row-actions/, "LLM row actions must be wrapped without changing table-cell display");
assert.match(sharedSource, /ops-ai-inline-config[\s\S]*ops-ai-inline-connection[\s\S]*ops-ai-inline-status/, "LLM runtime, connection and active state must use single-line groups");
assert.doesNotMatch(sharedSource, /hasFallbackColumn/, "Fallback must fold into configuration instead of creating a sparse column");
assert.match(sharedSource, /isOn \? \"is-active\"/, "On row (active+enabled) must get is-active class");
assert.match(
  sharedSource,
  /isActive && Boolean\(profile\.enabled\)/,
  "Row highlight must match switch On = active profile and enabled"
);
assert.match(
  sharedSource,
  /activeOnProfile/,
  "Toolbar Active must derive from enabled active setup (activeOnProfile)"
);
assert.match(
  sharedSource,
  /activeOnProfile \? \(/,
  "Toolbar Active badge must hide when all setups are Off"
);
assert.match(sharedSource, /setupName/, "Shared page editor must render a Setup name field");
assert.doesNotMatch(sharedSource, /kindLocal|kindCloud|kindHttp/, "Shared page must NOT expose TTS Kind tabs (Local/Cloud/HTTP)");
assert.doesNotMatch(sharedSource, /installTtsAiPackage|installCommand|previewTtsAiSpeech/, "Shared page must NOT include TTS Install/Preview features");
assert.doesNotMatch(sharedSource, /customProviderSlug/, "Shared page must NOT include TTS custom slug feature");

assert.match(componentSource, /fetchCaptionAi/, "UI must load Caption AI via API");
assert.match(componentSource, /testCaptionAi/, "UI must support Test caption connection");
assert.match(componentSource, /captionModelListReady|captionCanShowModel/, "UI must gate Model until credentials are ready");
assert.match(componentSource, /formatLlmProbeSuccess/, "Successful caption test must use LLM probe success formatter");
assert.match(componentSource, /ops-tts-test-banner is-ok/, "Successful caption test must use TTS-style result banner");
assert.match(componentSource, /testOkDraftHint/, "Unsaved caption draft must explain probe is not a finished setup");
assert.doesNotMatch(
  sharedSource,
  /ops-connection-status is-ok/,
  "Successful caption test must not use compact toolbar Connected chip"
);
assert.doesNotMatch(
  sharedSource,
  /ops-connection-status is-ok[\s\S]{0,80}?saved|profileDeleted/,
  "Save/delete must not show Saved or Setup deleted toolbar chips"
);
assert.match(componentSource, /testFailure/, "Failed caption test must use structured failure alert");
assert.match(componentSource, /ops-tts-test-banner is-error/, "Failed caption test must use TTS-style error banner");
assert.match(componentSource, /ops-field-alert__head/, "Provider alerts must use compact head + badge layout");
assert.match(componentSource, /ops-ai-setup-name/, "Setup name field must use editor setup-name chrome");
assert.match(componentSource, /ops-ai-gate-hint/, "Model gate hint must use dedicated callout style");
assert.doesNotMatch(componentSource, /OpsPageHeader/, "Must not duplicate Topbar title with OpsPageHeader");

assert.equal(captionModelListReady("openai_compatible", true, "https://api.openai.com/v1"), true);
assert.equal(captionModelListReady("openai_compatible", true, ""), false);
assert.equal(captionModelListReady("gemini", true, ""), true);
assert.equal(captionModelListReady("gemini", false, ""), false);
assert.equal(captionModelListReady("ollama", false, "http://127.0.0.1:11434"), true);
assert.equal(captionModelListReady("openrouter", true, "https://openrouter.ai/api/v1"), true);
assert.equal(captionModelListReady("placeholder", true, ""), false);
assert.equal(captionCanShowModel("gemini", true, ""), true);

assert.match(componentSource, /listCaptionAiModels\b/, "Shared page must list caption models via listCaptionAiModels");
assert.match(sharedSource, /profile_id:\s*editingProfileId/, "Caption model list must send editing profile_id for stored key");
assert.match(sharedSource, /ops-ai-model-action/, "Caption model actions must use icon+text buttons");
assert.match(sharedSource, /useLatestRequest/, "Caption model auto-load must ignore stale responses");

assert.match(apiSource, /\/ops\/caption-ai\/models/, "API helper must hit caption-ai models endpoint");
assert.match(apiSource, /\/ops\/caption-ai/, "API helper must hit caption-ai endpoints");

const requiredCaptionKeys = [
  "setupName",
  "setupNameHint",
  "setupNamePlaceholder",
  "providerSelectPlaceholder",
  "providerRequired",
  "providerRequiredTitle",
  "providerRequiredHint",
  "providerGateHint",
  "formErrorTitle",
  "testOkGeneric",
  "testOkHint",
  "testOkDraftHint"
];
for (const key of requiredCaptionKeys) {
  assert.ok(enJson.opsCaptionAi?.[key], `en.opsCaptionAi.${key} must exist`);
  assert.ok(viJson.opsCaptionAi?.[key], `vi.opsCaptionAi.${key} must exist`);
}

assert.match(
  sharedSource,
  /provider:\s*""/,
  "New setup blankForm must start with empty provider (not auto)"
);
assert.match(sharedSource, /providerSelectPlaceholder/, "Provider select must show choose-provider placeholder");
assert.match(sharedSource, /providerRequiredTitle/, "Provider-missing alert must use a titled field alert");
assert.match(sharedSource, /renderFormAlert/, "Editor validation notices must use compact form alert chrome");
assert.doesNotMatch(
  sharedSource,
  /clearApiKey|clear_api_key/,
  "LLM setups must not expose Clear stored API key — keys stay in workspace DB"
);
assert.match(sharedSource, /ops-ai-inline-connection/, "Table must show compact credential status instead of rendering key material");
assert.doesNotMatch(sharedSource, /profile\.api_key \|\| profile\.api_key_masked/, "Compact table must not render plaintext or masked key material");
assert.match(sharedSource, /apiKeyInput:\s*\(data\.api_key/, "Edit form must prefill saved api_key");
assert.match(apiSource, /api_key\?:/, "Caption AI types must include optional api_key");
assert.doesNotMatch(
  sharedSource,
  /id=\{`\$\{idPrefix\}-api-key`\}[\s\S]{0,120}?type="password"/,
  "Caption API key field must be visible text in Ops editor"
);

console.log("ops caption ai tests passed");
