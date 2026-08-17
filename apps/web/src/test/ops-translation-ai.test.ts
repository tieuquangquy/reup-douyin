import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { formatConnectionTestSummary, formatLlmProbeSuccess, formatProviderError } from "../lib/opsTranslationAiFormat";
import { modelListReady, canShowModel } from "../components/ops-console/OpsTranslationAiPage";

const pageSource = readFileSync("src/app/ops/translation-ai/page.tsx", "utf8");
const wrapperSource = readFileSync("src/components/ops-console/OpsTranslationAiPage.tsx", "utf8");
const sharedSource = readFileSync("src/components/ops-console/OpsLlmAiSetupsPage.tsx", "utf8");
const componentSource = wrapperSource + "\n" + sharedSource;
const apiSource = readFileSync("src/lib/api.ts", "utf8");
const navSource = readFileSync("src/lib/navigationConfig.ts", "utf8");
const opsHomeSource = readFileSync("src/components/ops-console/OpsHomePage.tsx", "utf8");
const enJson = JSON.parse(readFileSync("src/lib/i18n/en.json", "utf8")) as Record<string, Record<string, string>>;
const viJson = JSON.parse(readFileSync("src/lib/i18n/vi.json", "utf8")) as Record<string, Record<string, string>>;

assert.match(pageSource, /OpsTranslationAiPage/, "Ops route must mount Translation AI page");
assert.match(wrapperSource, /OpsLlmAiSetupsPage/, "Translation AI wrapper must delegate to shared setups page");
assert.match(wrapperSource, /variant=["']translation["']/, "Wrapper must pass translation variant to shared page");
assert.match(wrapperSource, /export\s+function\s+OpsTranslationAiPage/, "Wrapper must export OpsTranslationAiPage");
assert.match(wrapperSource, /export\s+\{[^}]*modelListReady[\s\S]*?canShowModel[^}]*\}/, "Wrapper must re-export modelListReady + canShowModel");

// Shared component must wire translation-scoped profile helpers.
assert.match(sharedSource, /fetchTranslationAi\b/, "Shared page must load translation via fetchTranslationAi when translation variant");
assert.match(sharedSource, /saveTranslationAiProfile\b/, "Shared page must save via translation profile helper");
assert.match(sharedSource, /createTranslationAiProfile\b/, "Shared page must create new setups via createTranslationAiProfile");
assert.match(sharedSource, /fetchTranslationAiProfile\b/, "Shared page must open editors via fetchTranslationAiProfile");
assert.match(sharedSource, /activateTranslationAiProfile\b/, "Shared page must activate setups via activateTranslationAiProfile");
assert.match(sharedSource, /setTranslationAiProfileEnabled\b/, "Shared page must toggle setups via setTranslationAiProfileEnabled");
assert.match(sharedSource, /renameTranslationAiProfile\b/, "Shared page must rename setups via renameTranslationAiProfile");
assert.match(sharedSource, /deleteTranslationAiProfile\b/, "Shared page must delete setups via deleteTranslationAiProfile");
assert.match(sharedSource, /testTranslationAi\b/, "Shared page must call testTranslationAi");
assert.match(sharedSource, /profile_id/, "Shared page must send profile_id when testing an existing setup");
assert.match(sharedSource, /viewMode/, "Shared page must maintain list/editor viewMode");
assert.match(sharedSource, /"list"\s*\|\s*"editor"/, "Shared page must model viewMode as list|editor");
assert.match(sharedSource, /editingProfileId/, "Shared page must track editingProfileId for editor mode");
assert.match(sharedSource, /ops-tts-list-toolbar/, "Shared page list mode must reuse TTS list toolbar CSS chrome");
assert.match(sharedSource, /ops-tts-list-header/, "Tabs + Active toolbar must share one list header row");
assert.match(sharedSource, /ops-tts-setup-table/, "Shared page must reuse TTS setup table CSS");
assert.match(sharedSource, /ops-ai-control-center is-\$\{variant\}/, "Translation and Caption lists must use the shared AI Setup Control Center surface");
assert.match(sharedSource, /ops-ai-registry-table is-llm/, "Translation setups must use the condensed semantic registry table");
assert.match(sharedSource, /runtimeCol[\s\S]*connectionCol/, "Translation registry must group related connection fields");
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
assert.match(sharedSource, /profileNew/, "Shared page must render New setup button using profileNew label");
assert.match(sharedSource, /setupName/, "Shared page editor must render a Setup name field");
assert.doesNotMatch(sharedSource, /kindLocal|kindCloud|kindHttp/, "Shared page must NOT expose TTS Kind tabs (Local/Cloud/HTTP)");
assert.doesNotMatch(sharedSource, /installTtsAiPackage|installCommand|previewTtsAiSpeech/, "Shared page must NOT include TTS Install/Preview features");
assert.doesNotMatch(sharedSource, /customProviderSlug/, "Shared page must NOT include TTS custom slug feature");

assert.match(componentSource, /fetchTranslationAi/, "UI must load Translation AI via API");
assert.match(componentSource, /testTranslationAi/, "UI must support Test connection");
assert.match(componentSource, /formatLlmProbeSuccess/, "Successful test must use LLM probe success formatter");
assert.match(componentSource, /ops-tts-test-banner is-ok/, "Successful test must use TTS-style result banner");
assert.match(componentSource, /ops-tts-test-banner__chip/, "Success banner must show provider chip");
assert.match(componentSource, /testOkDraftHint/, "Unsaved draft must explain probe is not a finished setup");
assert.doesNotMatch(
  sharedSource,
  /ops-connection-status is-ok/,
  "Successful test must not use compact toolbar Connected chip"
);
assert.doesNotMatch(
  sharedSource,
  /ops-connection-status is-ok[\s\S]{0,80}?saved|profileDeleted/,
  "Save/delete must not show Saved or Setup deleted toolbar chips"
);
assert.match(componentSource, /testFailure/, "Failed test must use structured failure alert");
assert.match(componentSource, /ops-tts-test-banner is-error/, "Failed test must use TTS-style error banner");
assert.match(componentSource, /listTranslationAiModels/, "UI must load model list after credentials");
assert.match(componentSource, /modelListReady|canShowModel/, "UI must gate Model until provider credentials are ready");
assert.doesNotMatch(componentSource, /OpsPageHeader/, "Must not duplicate Topbar title with OpsPageHeader");

assert.equal(modelListReady("openai_compatible", true, "https://api.openai.com/v1"), true);
assert.equal(modelListReady("openai_compatible", true, ""), false);
assert.equal(modelListReady("gemini", true, ""), true);
assert.equal(modelListReady("gemini", false, ""), false);
assert.equal(modelListReady("google_cloud", true, ""), true);
assert.equal(modelListReady("google_cloud", false, ""), false);
assert.equal(modelListReady("ollama", false, "http://127.0.0.1:11434"), true);
assert.equal(modelListReady("openrouter", true, "https://openrouter.ai/api/v1"), true);
assert.equal(modelListReady("placeholder", true, ""), false);
assert.equal(canShowModel("gemini", true, ""), true);

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
const probeOk = formatLlmProbeSuccess(
  { ok: true, provider: "openai_compatible", detail: "OK" },
  { passed: "Check passed", generic: "Provider probe succeeded on this machine." }
);
assert.equal(probeOk.title, "Check passed");
assert.equal(probeOk.provider, "openai_compatible");
assert.equal(probeOk.message, "Provider probe succeeded on this machine.");
assert.ok(enJson.opsTranslationAi?.testOkGeneric, "en.opsTranslationAi.testOkGeneric must exist");
assert.ok(enJson.opsTranslationAi?.testOkHint, "en.opsTranslationAi.testOkHint must exist");
assert.ok(enJson.opsTranslationAi?.testOkDraftHint, "en.opsTranslationAi.testOkDraftHint must exist");
assert.ok(viJson.opsTranslationAi?.testOkGeneric, "vi.opsTranslationAi.testOkGeneric must exist");
assert.ok(viJson.opsTranslationAi?.testOkHint, "vi.opsTranslationAi.testOkHint must exist");
assert.ok(viJson.opsTranslationAi?.testOkDraftHint, "vi.opsTranslationAi.testOkDraftHint must exist");
assert.match(componentSource, /formatProviderError/, "Model list errors must use provider error formatter");
assert.match(componentSource, /ops-field-alert/, "Model list errors must render as a field alert, not raw muted dump");
assert.match(
  sharedSource,
  /modelListError\s*&&\s*!testFailure\s*&&\s*!testing/,
  "Model list alert must hide while Test failure banner owns the error, and while a Test is in flight (avoids flicker)"
);

const providerErrorLabels = {
  unauthorized: "Invalid API key",
  forbidden: "Access denied",
  notFound: "Endpoint not found",
  rateLimited: "Rate limited",
  failed: "Could not load models",
  checkKey: "Check the API key and try again.",
  checkForbidden: "The provider rejected this request. Check Base URL, key permissions, or a gateway/firewall block.",
  checkEndpoint: "Check Base URL and provider, then try again."
};

const openai401 = formatProviderError(
  'list_models_http_401:{ "error": { "message": "Incorrect API key provided: sk-9bea4***************3270. You can find your API key at https://platform.openai.com/account/api-keys.", "type": "invalid_request_error" } }',
  providerErrorLabels
);
assert.equal(openai401.title, "Invalid API key");
assert.equal(openai401.httpStatus, 401);
assert.match(openai401.message, /Incorrect API key/i);

const opaque403 = formatProviderError("openai_compatible_http_403: error code: 1010", providerErrorLabels);
assert.equal(opaque403.title, "Access denied");
assert.equal(opaque403.httpStatus, 403);
assert.match(opaque403.message, /rejected|Base URL|gateway|firewall/i);
assert.doesNotMatch(opaque403.message, /error code:\s*1010/i, "Opaque gateway codes must not be shown raw to operators");

const onTestStart = sharedSource.indexOf("async function onTest(");
const onTestEnd = sharedSource.indexOf("function onProviderChange(", onTestStart);
const onTestChunk = sharedSource.slice(onTestStart, onTestEnd > onTestStart ? onTestEnd : onTestStart + 2000);
assert.match(onTestChunk, /if\s*\(result\.ok\)\s*\{[\s\S]*?notify\(/, "Successful Test connection may toast");
assert.doesNotMatch(
  onTestChunk,
  /notify\(\{[\s\S]*?testFail/,
  "Failed Test connection must not toast a bare Failed notice; the form banner owns the detail"
);
assert.doesNotMatch(
  onTestChunk,
  /setTestResult\(null\)/,
  "Re-Test must not clear the previous banner mid-flight (that briefly reveals the model-list error)"
);
assert.match(sharedSource, /testErrorHintForbidden|testFailureHint/, "Failed Test banner must use status-aware next-step hints");
assert.ok(enJson.opsTranslationAi?.errorCheckForbidden, "EN must define forbidden check copy");
assert.ok(enJson.opsTranslationAi?.testErrorHintForbidden, "EN must define forbidden test hint");
assert.ok(viJson.opsTranslationAi?.errorCheckForbidden, "VI must define forbidden check copy");

const gemini429 = formatProviderError(
  'gemini_http_429:{"error": {"code": 429, "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits"}}',
  providerErrorLabels
);
assert.equal(gemini429.title, "Rate limited");
assert.equal(gemini429.httpStatus, 429);
assert.match(gemini429.message, /exceeded your current quota/i);
assert.doesNotMatch(gemini429.message, /gemini_http_429|ai\.google\.dev|\{"error"/i);

const googleCloud401 = formatProviderError(
  "google_cloud_http_401:API key not valid",
  providerErrorLabels
);
assert.equal(googleCloud401.title, "Invalid API key");
assert.equal(googleCloud401.httpStatus, 401);

const urlopenTimeout = formatProviderError(
  "<urlopen error [WinError 10060] A connection attempt failed because the connected party did not properly respond after a period of time, or established connection failed because connected host has failed to respond>",
  {
    unauthorized: "Invalid API key",
    forbidden: "Access denied",
    notFound: "Endpoint not found",
    rateLimited: "Rate limited",
    failed: "Could not load models",
    checkKey: "Check the API key and try again.",
    checkEndpoint: "Could not reach the provider. Check network, API key, and Base URL.",
    checkForbidden: "The provider rejected this request. Check Base URL, key permissions, or a gateway/firewall block."
  }
);
assert.equal(urlopenTimeout.title, "Could not load models");
assert.equal(urlopenTimeout.httpStatus, null);
assert.equal(urlopenTimeout.message, "Could not reach the provider. Check network, API key, and Base URL.");
assert.doesNotMatch(urlopenTimeout.message, /urlopen|WinError|10060/i);

assert.match(sharedSource, /profile_id:\s*editingProfileId/, "Model list must send editing profile_id for stored key");
assert.match(sharedSource, /useLatestRequest/, "Model list must ignore stale auto-load responses");
assert.match(
  sharedSource,
  /setTimeout\(\(\) => \{\s*void refreshModels\(\);\s*\}, 700\)/,
  "Model auto-load must debounce key typing (~700ms)"
);
assert.match(sharedSource, /ops-ai-model-action/, "Reload / Use model list must use icon+text action buttons");
assert.match(sharedSource, /SetupActionIcon kind=\"reload\"/, "Reload models button must show reload icon");
assert.match(sharedSource, /kind=\{manualModel \? \"list\" : \"edit\"\}/, "Toggle model list/manual must show list or edit icon");
assert.match(sharedSource, /ops-ai-model-field/, "Model section must use dedicated spacing wrapper");

assert.match(sharedSource, /ops-ai-fallback-grid/, "Fallback row must be spaced below model alert");
assert.match(sharedSource, /result\.models\.length > 0/, "UI must use model list even when live fetch fails with fallback catalog");
assert.match(sharedSource, /timeout_seconds:\s*12/, "Model list must use a short fail-fast timeout");

assert.match(componentSource, /ops-field-alert__head/, "Provider alerts must use compact head + badge layout");
assert.match(componentSource, /ops-ai-setup-name/, "Setup name field must use editor setup-name chrome");
assert.match(componentSource, /ops-ai-gate-hint/, "Model gate hint must use dedicated callout style");
assert.match(apiSource, /\/ops\/translation-ai\/models/, "API helper must hit translation-ai models endpoint");
assert.match(apiSource, /\/ops\/translation-ai/, "API helper must hit translation-ai endpoints");
assert.match(navSource, /nav\.translationSettings/, "Ops nav must use shared Translation settings label");
assert.match(
  navSource,
  /sectionAiSettings[\s\S]*?translationSettings[\s\S]*?captionAiSettings[\s\S]*?ttsSettings/,
  "AI Settings must list Translation, Caption, and TTS together"
);
assert.match(navSource, /activePatterns: \["\/ops\/translation-ai", "\/ops\/translation-prompt"\]/, "Sidebar item active on both translation settings routes");
assert.doesNotMatch(opsHomeSource, /studio-card-list/, "Ops home triage must not keep a long settings directory");

// i18n keys the shared page depends on for the list/editor chrome.
const requiredTranslationKeys = [
  "setupName",
  "setupNameHint",
  "setupNamePlaceholder",
  "providerSelectPlaceholder",
  "providerRequired",
  "providerRequiredTitle",
  "providerRequiredHint",
  "providerGateHint",
  "formErrorTitle"
];
for (const key of requiredTranslationKeys) {
  assert.ok(enJson.opsTranslationAi?.[key], `en.opsTranslationAi.${key} must exist`);
  assert.ok(viJson.opsTranslationAi?.[key], `vi.opsTranslationAi.${key} must exist`);
}

assert.match(
  sharedSource,
  /provider:\s*""/,
  "New setup blankForm must start with empty provider (not auto)"
);
assert.match(
  sharedSource,
  /providerSelectPlaceholder/,
  "Provider select must show a choose-provider placeholder on New"
);
assert.match(sharedSource, /LLM_PROVIDER_OPTIONS/, "Provider dropdown must use shared LLM catalog");
assert.match(sharedSource, /defaultBaseUrlFor/, "Provider change must autofill catalog Base URL presets");
assert.match(
  sharedSource,
  /providerRequiredTitle/,
  "Provider-missing alert must use a titled field alert"
);
assert.match(
  sharedSource,
  /providerMissing/,
  "Save/Test must gate on providerMissing instead of plain inline-error"
);
assert.match(
  sharedSource,
  /renderFormAlert/,
  "Editor validation notices must use compact form alert chrome"
);
assert.match(sharedSource, /profile\.api_key/, "Editor must read plaintext api_key from Ops response");
assert.match(sharedSource, /ops-ai-inline-connection/, "Table must show compact credential status instead of rendering key material");
assert.doesNotMatch(sharedSource, /profile\.api_key \|\| profile\.api_key_masked/, "Compact table must not render plaintext or masked key material");
assert.match(sharedSource, /apiKeyInput:\s*\(data\.api_key/, "Edit form must prefill saved api_key");
assert.match(apiSource, /api_key\?:/, "TranslationAi types must include optional api_key");
assert.doesNotMatch(
  sharedSource,
  /id=\{`\$\{idPrefix\}-api-key`\}[\s\S]{0,120}?type="password"/,
  "API key field must be visible text (not password-masked) in Ops editor"
);
assert.match(
  sharedSource,
  /providerGateHint/,
  "Model section must prompt to choose a provider when none selected"
);

console.log("ops translation ai tests passed");
