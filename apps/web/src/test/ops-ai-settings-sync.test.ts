/**
 * AI Settings visual sync + compact chrome contracts.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const translationAiWrapper = readFileSync(resolve(webSrc, "components/ops-console/OpsTranslationAiPage.tsx"), "utf8");
const captionAiWrapper = readFileSync(resolve(webSrc, "components/ops-console/OpsCaptionAiPage.tsx"), "utf8");
const translationPromptWrapper = readFileSync(
  resolve(webSrc, "components/ops-console/OpsTranslationPromptPage.tsx"),
  "utf8"
);
const captionPromptWrapper = readFileSync(resolve(webSrc, "components/ops-console/OpsCaptionPromptPage.tsx"), "utf8");
const translationAi = readFileSync(resolve(webSrc, "components/ops-console/OpsLlmAiSetupsPage.tsx"), "utf8");
const captionAi = translationAi;
const ttsAi = readFileSync(resolve(webSrc, "components/ops-console/OpsTtsAiPage.tsx"), "utf8");
const translationPrompt = readFileSync(resolve(webSrc, "components/ops-console/OpsPromptSetupsPage.tsx"), "utf8");
const captionPrompt = translationPrompt;
const translationTabs = readFileSync(resolve(webSrc, "components/ops-console/OpsTranslationSettingsTabs.tsx"), "utf8");
const captionTabs = readFileSync(resolve(webSrc, "components/ops-console/OpsCaptionSettingsTabs.tsx"), "utf8");
const sharedTabs = readFileSync(resolve(webSrc, "components/ops-console/OpsAiSettingsTabs.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

assert.match(sharedTabs, /export function OpsAiSettingsTabs/, "Shared OpsAiSettingsTabs must exist");
assert.match(translationTabs, /OpsAiSettingsTabs/, "Translation tabs must reuse OpsAiSettingsTabs");
assert.match(captionTabs, /OpsAiSettingsTabs/, "Caption tabs must reuse OpsAiSettingsTabs");
assert.match(translationAiWrapper, /OpsLlmAiSetupsPage/, "Translation AI page must mount shared setups page");
assert.match(captionAiWrapper, /OpsLlmAiSetupsPage/, "Caption AI page must mount shared setups page");
assert.match(translationPromptWrapper, /OpsPromptSetupsPage/, "Translation prompt page must mount shared prompt page");
assert.match(captionPromptWrapper, /OpsPromptSetupsPage/, "Caption prompt page must mount shared prompt page");

for (const [label, source] of [
  ["Translation AI", translationAi],
  ["Caption AI", captionAi],
  ["TTS AI", ttsAi]
] as const) {
  if (label === "TTS AI") {
    assert.match(source, /ops-ai-status|ops-tts-status/, `${label} must use shared status chip strip`);
    assert.match(source, /ops-ai-chip|ops-tts-chip/, `${label} must use status chips`);
  } else {
    assert.doesNotMatch(
      source,
      /ops-ai-status|ops-tts-status/,
      `${label} editor must not show Env/key/provider status chip strip`
    );
  }
  assert.match(source, /ops-ai-section|ops-tts-section/, `${label} must use section cards`);
  assert.match(source, /ops-header-actions|ops-tts-editor-actions/, `${label} must keep Refresh/Test/Save toolbar`);
  assert.match(source, /ops-page--settings/, `${label} must use settings page shell class`);
  assert.match(source, /is-compact/, `${label} must opt into compact settings density`);
  assert.doesNotMatch(
    source,
    /savedMessage \? \([\s\S]*ops-field-alert is-success/,
    `${label} must not duplicate Saved as a field alert`
  );
  assert.doesNotMatch(
    source,
    /ops-connection-status is-ok[\s\S]{0,120}?(saved|profileDeleted)/,
    `${label} must not show Saved / Setup deleted toolbar chips`
  );
  assert.doesNotMatch(source, /\bsavedMessage\b/, `${label} must not keep savedMessage badge state`);
}

assert.match(translationAi, /ops-ai-section/, "Translation AI must use shared ops-ai-section (not TTS-only markup)");
assert.match(captionAi, /ops-ai-section/, "Caption AI must use shared ops-ai-section");
assert.match(ttsAi, /ops-tts-section/, "TTS keeps domain sections");
assert.match(ttsAi, /ops-ai-status/, "TTS status strip aliases shared chrome");

assert.match(translationAi, /sectionConnection/, "Translation AI must merge provider fields into Connection");
assert.match(captionAi, /sectionConnection/, "Caption AI must merge provider fields into Connection");
assert.match(translationAi, /sectionModelFallback/, "Translation AI must merge model + fallback");
assert.match(captionAi, /sectionModelFallback/, "Caption AI must merge model + fallback");
assert.doesNotMatch(translationAi, /ops-ai-lede/, "Translation AI must drop redundant lede under chips");
assert.doesNotMatch(captionAi, /ops-ai-lede/, "Caption AI must drop redundant lede under chips");

for (const [label, source] of [
  ["Translation AI", translationAi],
  ["Caption AI", captionAi]
] as const) {
  assert.doesNotMatch(
    source,
    /OpsPanel[\s\S]*meta=\{[\s\S]*ops-ai-meta/,
    `${label} must not show Env/key/provider/override meta chips in the editor heading`
  );
  assert.doesNotMatch(
    source,
    /ops-ai-toggle--flush/,
    `${label} must not show Workspace override toggle in the editor (list On/Off is authority)`
  );
  assert.match(
    source,
    /ops-ai-toolbar/,
    `${label} must use a compact AI action toolbar (not loose standalone buttons)`
  );
  assert.match(
    source,
    /TopbarRefreshButton|ops-ai-toolbar__refresh|aria-label=\{t\("common\.refresh"\)\}/,
    `${label} must keep Refresh accessible`
  );
}

assert.match(
  ttsAi,
  /TopbarRefreshButton|ops-ai-toolbar__refresh|aria-label=\{t\("common\.refresh"\)\}/,
  "TTS must keep Refresh accessible"
);

for (const [label, source] of [
  ["Translation Prompt", translationPrompt],
  ["Caption Prompt", captionPrompt]
] as const) {
  assert.match(source, /ops-prompt-textarea/, `${label} must keep prompt textarea`);
  assert.match(source, /OpsTranslationSettingsTabs|OpsCaptionSettingsTabs/, `${label} must keep settings tabs`);
  assert.match(source, /is-compact/, `${label} must use compact density`);
  assert.doesNotMatch(
    source,
    /ops-ai-section__head[\s\S]*panelTitle/,
    `${label} must not repeat panelTitle inside a nested section head`
  );
  assert.doesNotMatch(source, /\bsavedMessage\b/, `${label} must not keep savedMessage badge state`);
  assert.doesNotMatch(
    source,
    /sourceEmpty|sourceDb|clearHint|editorSource/,
    `${label} must not show empty/file/env/builtin source chip or clear-hint clutter`
  );
}

assert.match(css, /\.ops-ai-section\s*[,{]/, "CSS must define .ops-ai-section");
assert.match(css, /\.ops-ai-chip\s*[,{]/, "CSS must define .ops-ai-chip");
assert.match(css, /\.ops-ai-status\s*[,{]/, "CSS must define .ops-ai-status");
assert.match(
  css,
  /\.ops-ai-section[^\n]*\.ops-tts-section|\.ops-tts-section[^\n]*\.ops-ai-section/,
  "Shared section styles must cover both ops-ai and ops-tts"
);
assert.match(css, /\.ops-ai-page\.is-compact/, "CSS must define compact AI settings density");

console.log("ops-ai-settings-sync tests passed");
