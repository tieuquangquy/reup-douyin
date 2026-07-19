/**
 * AI Settings visual sync + compact chrome contracts.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(testDir, "..");

const translationAi = readFileSync(resolve(webSrc, "components/ops-console/OpsTranslationAiPage.tsx"), "utf8");
const captionAi = readFileSync(resolve(webSrc, "components/ops-console/OpsCaptionAiPage.tsx"), "utf8");
const ttsAi = readFileSync(resolve(webSrc, "components/ops-console/OpsTtsAiPage.tsx"), "utf8");
const translationPrompt = readFileSync(resolve(webSrc, "components/ops-console/OpsTranslationPromptPage.tsx"), "utf8");
const captionPrompt = readFileSync(resolve(webSrc, "components/ops-console/OpsCaptionPromptPage.tsx"), "utf8");
const translationTabs = readFileSync(resolve(webSrc, "components/ops-console/OpsTranslationSettingsTabs.tsx"), "utf8");
const captionTabs = readFileSync(resolve(webSrc, "components/ops-console/OpsCaptionSettingsTabs.tsx"), "utf8");
const sharedTabs = readFileSync(resolve(webSrc, "components/ops-console/OpsAiSettingsTabs.tsx"), "utf8");
const css = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

assert.match(sharedTabs, /export function OpsAiSettingsTabs/, "Shared OpsAiSettingsTabs must exist");
assert.match(translationTabs, /OpsAiSettingsTabs/, "Translation tabs must reuse OpsAiSettingsTabs");
assert.match(captionTabs, /OpsAiSettingsTabs/, "Caption tabs must reuse OpsAiSettingsTabs");

for (const [label, source] of [
  ["Translation AI", translationAi],
  ["Caption AI", captionAi],
  ["TTS AI", ttsAi]
] as const) {
  assert.match(source, /ops-ai-status|ops-tts-status/, `${label} must use shared status chip strip`);
  assert.match(source, /ops-ai-chip|ops-tts-chip/, `${label} must use status chips`);
  assert.match(source, /ops-ai-section|ops-tts-section/, `${label} must use section cards`);
  assert.match(source, /ops-header-actions/, `${label} must keep Refresh/Test/Save toolbar`);
  assert.match(source, /ops-page--settings/, `${label} must use settings page shell class`);
  assert.match(source, /is-compact/, `${label} must opt into compact settings density`);
  assert.doesNotMatch(
    source,
    /savedMessage \? \([\s\S]*ops-field-alert is-success/,
    `${label} must not duplicate Saved as a field alert when the toolbar chip already shows it`
  );
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
  assert.match(source, /OpsPanel[\s\S]*meta=\{/, `${label} must place status + authority in the panel heading meta slot`);
  assert.match(source, /ops-ai-meta/, `${label} must keep status chips + authority in one meta cluster`);
  assert.match(source, /ops-ai-toggle--flush/, `${label} must use flush authority toggle (not a section card)`);
  assert.doesNotMatch(
    source,
    /ops-ai-toggle--flush[\s\S]*?<small>/,
    `${label} must not show a multi-line disableHint under the authority toggle`
  );
  assert.match(
    source,
    /ops-ai-toggle--flush[\s\S]*title=\{t\("[^"]+\.disableHint"\)\}/,
    `${label} must keep disableHint as a title tooltip on the toggle`
  );
  assert.match(
    source,
    /ops-ai-toolbar/,
    `${label} must use a compact AI action toolbar (not loose standalone buttons)`
  );
  assert.match(
    source,
    /ops-ai-toolbar__refresh|aria-label=\{t\("common\.refresh"\)\}/,
    `${label} must keep Refresh accessible in the toolbar`
  );
}

assert.match(
  readFileSync(resolve(webSrc, "components/ops-console/OpsShared.tsx"), "utf8"),
  /meta\?: ReactNode/,
  "OpsPanel must accept an optional meta slot under the title"
);
assert.match(css, /\.ops-panel-heading__lead/, "CSS must style panel heading lead column for AI masthead");
assert.match(css, /\.ops-ai-meta/, "CSS must style left-aligned AI meta cluster (not full-width stretch)");
assert.match(css, /\.ops-ai-toolbar/, "CSS must define the compact AI action toolbar");


assert.match(ttsAi, /<details[\s\S]*ops-tts-steps|ops-ai-howto/, "TTS how-to steps must be collapsible");
assert.doesNotMatch(ttsAi, /ops-tts-lede">\{t\("opsTtsAi\.readyHint"\)\}/, "TTS must not keep readyHint as a second lede");

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
}

assert.match(css, /\.ops-ai-section\s*[,{]/, "CSS must define .ops-ai-section");
assert.match(css, /\.ops-ai-chip\s*[,{]/, "CSS must define .ops-ai-chip");
assert.match(css, /\.ops-ai-status\s*[,{]/, "CSS must define .ops-ai-status");
assert.match(css, /\.ops-ai-section[^\n]*\.ops-tts-section|\.ops-tts-section[^\n]*\.ops-ai-section/, "Shared section styles must cover both ops-ai and ops-tts");
assert.match(css, /\.ops-ai-page\.is-compact/, "CSS must define compact AI settings density");

console.log("ops-ai-settings-sync tests passed");
