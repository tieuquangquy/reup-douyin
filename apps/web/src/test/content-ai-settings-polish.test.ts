/** Publishing Settings / Content AI v6: dark Intelligence stage + light worksheet. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { formatContentAiPromptVersion } from "../lib/contentAiPromptVersion";

const webSrc = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const page = readFileSync(resolve(webSrc, "components/operator-routes/ContentAiConfiguration.tsx"), "utf8");
const nav = readFileSync(resolve(webSrc, "components/operator-routes/PublishingSettingsNav.tsx"), "utf8");
const config = page;
const api = readFileSync(resolve(webSrc, "lib/api.ts"), "utf8");
const en = readFileSync(resolve(webSrc, "lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(webSrc, "lib/i18n/vi.json"), "utf8");
const cssFull = readFileSync(resolve(webSrc, "app/globals.css"), "utf8");

const v6Start = cssFull.indexOf("/* Publishing Settings Content AI v6");
assert.ok(v6Start >= 0, "v6 Content AI control-stage CSS block must exist");
const v6End = cssFull.indexOf(".affiliate-catalog-page", v6Start);
const v6 = cssFull.slice(v6Start, v6End > v6Start ? v6End : v6Start + 22000);

assert.match(page, /publishing-settings-page is-v1 is-v4/, "Settings page must keep the v4 horizontal switcher shell");
assert.match(nav, /publishing-settings-tabs is-v1 is-v4/, "Settings nav must stay a horizontal switcher");
assert.doesNotMatch(nav, /icon:\s*"AI"|icon:\s*"SKU"|icon:\s*"CMT"/, "Must keep SVG icons instead of AI/SKU/CMT text badges");
assert.match(config, /content-ai-page is-v6/, "Content AI workbench must mark is-v6");
assert.match(config, /content-ai-stage/, "v6 must use a dark Intelligence stage");
assert.match(config, /content-ai-stage__worksheet|content-ai-worksheet/, "v6 must use a light worksheet pane");
assert.match(config, /content-ai-stage__meter/, "Stage must show a mode meter");
assert.doesNotMatch(config, /content-ai-chips/, "v6 must drop the chip strip");
assert.doesNotMatch(config, /content-ai-canvas/, "v6 must drop the centered v4/v5 canvas");
assert.match(config, /content-ai-modes is-stage|is-pills/, "Mode picker remains on the worksheet");
assert.match(config, /contentAi\.connectionGroup|connectionGroup/, "Provider fields must use Connection group label");
assert.match(config, /contentAi\.tuningGroup|tuningGroup/, "Behavior fields must use Runtime tuning group label");
assert.match(config, /persistConfig|testConnection|savePrompt/, "Save / test / prompt flows must remain");

assert.match(en, /"connectionGroup":/, "en.json must include contentAi.connectionGroup");
assert.match(vi, /"connectionGroup":/, "vi.json must include contentAi.connectionGroup");
assert.match(en, /"tuningGroup":/, "en.json must include contentAi.tuningGroup");
assert.match(vi, /"tuningGroup":/, "vi.json must include contentAi.tuningGroup");

assert.match(v6, /--pl-iq-mint|--pl-iq-label-quiet|--pl-iq-label-strong/, "v6 CSS must use Intelligence tokens");
assert.match(v6, /content-ai-page\.is-v6/, "v6 CSS must scope to the workbench mark");
assert.match(v6, /content-ai-stage/, "v6 must style the dark stage");
assert.match(v6, /content-ai-worksheet|content-ai-stage__worksheet/, "v6 must style the light worksheet");
assert.match(v6, /grid-template-columns/, "v6 must split stage and worksheet");
assert.match(v6, /#102e26|#193f33|#0f2c24/, "Stage must use the Intelligence dark teal");
assert.match(v6, /minmax\([^,]+,\s*1[4-8]\.?\d*rem\)/, "Stage column must stay a narrow instrument rail, not a 32% void");
assert.match(v6, /content-ai-stage__panel[\s\S]{0,420}?text-align:\s*left/, "Stage copy must left-align, not float as a centered widget");
assert.match(v6, /content-ai-modes\.is-stage \{[\s\S]{0,180}?gap:\s*0/, "Mode picker must be one editorial band, not three floating cards");
assert.match(v6, /content-ai-enable \{[\s\S]{0,160}?background:\s*transparent/, "Enable control must drop the mint pill chrome");
assert.match(v6, /content-ai-worksheet__footer \{[\s\S]{0,280}?background:\s*transparent/, "Worksheet footer must flush to the paper, not a mint well");
assert.match(v6, /--app-content-inset-x/, "Settings stack must share the topbar horizontal inset");
assert.match(v6, /padding:\s*18px\s+var\(--app-content-inset-x\)/, "Header-to-nav padding must match .app-topbar");
assert.match(v6, /gap:\s*18px/, "Nav-to-stage gap must match the topbar padding");
assert.match(v6, /\.content-ai-stage \{[\s\S]{0,280}?border-radius:\s*12px/, "Stage card radius must match the settings nav");
assert.doesNotMatch(config, /content-ai-page is-v6">\s*\{error \? <div className="inline-error"/, "v6 must not float a bare inline-error above the stage");
assert.match(config, /content-ai-worksheet__note/, "API errors must render as a worksheet note");
assert.match(config, /content-ai-worksheet__footer[\s\S]{0,700}content-ai-worksheet__note/, "Connection errors must share the Test/Save footer slot");
assert.match(v6, /content-ai-worksheet__note/, "v6 must style the worksheet note");
assert.match(v6, /content-ai-worksheet__note[\s\S]{0,360}?(?:#f4f8f6|var\(--pl-iq-mint\))/, "Note must sit on mint paper, not a red banner");
assert.match(v6, /content-ai-worksheet__note[\s\S]{0,480}?(?:inset 2px 0 0 #2a4d41|inset 2px 0 0 var\(--pl-iq-label-strong\))/, "Note must use a strong ink spine, not danger fill");
assert.match(
  config,
  /connectionGroup[\s\S]{0,500}?contentAi\.provider[\s\S]{0,900}?contentAi\.timeout[\s\S]{0,400}?className="is-wide"[\s\S]{0,220}?contentAi\.baseUrl[\s\S]{0,400}?className="is-wide"[\s\S]{0,220}?contentAi\.apiKey[\s\S]{0,700}?className="content-ai-model-field is-wide"[\s\S]{0,280}?contentAi\.model/,
  "Connection fields must stack Provider+Timeout, then full-width URL, key, and model",
);
assert.doesNotMatch(
  config,
  /connectionGroup[\s\S]{0,500}?contentAi\.provider[\s\S]{0,400}?contentAi\.model[\s\S]{0,400}?contentAi\.baseUrl/,
  "Model must not sit on the first Connection row beside Provider",
);
assert.match(
  v6,
  /form-grid\.is-v1:not\(\.is-behavior\) \{[\s\S]{0,200}?grid-template-columns:\s*minmax\(0,\s*1\.\d+fr\)/,
  "Connection row must give Provider more width than Timeout",
);

assert.match(api, /listContentAiModels/, "Web client must expose listContentAiModels");
assert.match(
  api,
  /content-intelligence\/ai-config\/models/,
  "Model catalog must POST to Content AI models, not Ops translation-ai",
);
assert.match(config, /listContentAiModels/, "Worksheet must load models from the Content AI client");
assert.match(config, /content-ai-model-field/, "Model ID must become a picker field, not a lone text input");
assert.match(config, /contentAi\.loadModels/, "Worksheet must offer Reload models");
assert.match(config, /contentAi\.typeModelManually/, "Worksheet must keep Type manually");
assert.match(config, /contentAi\.useModelList/, "Worksheet must restore the model list after manual typing");
assert.match(
  config,
  /content-ai-model-field[\s\S]{0,900}?<select[\s\S]{0,500}?contentAi\.modelSelectPlaceholder/,
  "Loaded models must render as a select inside the model field",
);
assert.doesNotMatch(config, /fallbackProvider|setup name|Setup name/, "Topic AI must not copy the Ops LLM setup catalog");
assert.match(en, /"loadModels":/, "en.json must include contentAi.loadModels");
assert.match(vi, /"loadModels":/, "vi.json must include contentAi.loadModels");
assert.match(en, /"typeModelManually":/, "en.json must include contentAi.typeModelManually");
assert.match(vi, /"typeModelManually":/, "vi.json must include contentAi.typeModelManually");
assert.match(v6, /content-ai-model-actions/, "v6 must style Reload / Type manually under the model field");

assert.doesNotMatch(
  config,
  /contentAi\.apiKey[\s\S]{0,900}?type="password"/,
  "API key must be visible as text while typing, not a password mask",
);
assert.match(
  config,
  /contentAi\.apiKey[\s\S]{0,900}?type="text"/,
  "API key field must use a visible text input",
);
assert.match(config, /api_key_masked/, "Stored key hint must show the public masked suffix, not a blank password box");
assert.match(config, /function ContentAiActionIcon/, "Worksheet buttons must share a local action glyph");
assert.match(config, /leadingIcon=\{<ContentAiActionIcon kind="reload"/, "Reload models must have a reload glyph");
assert.match(config, /ContentAiActionIcon kind=\{manualModel \? "list" : "edit"\}/, "Model list/manual toggle must swap list and edit glyphs");
assert.match(config, /leadingIcon=\{<ContentAiActionIcon kind="test"/, "Test connection must have a probe glyph");
assert.match(config, /leadingIcon=\{<ContentAiActionIcon kind="save"/, "Save must have a save glyph");
assert.match(config, /leadingIcon=\{<ContentAiActionIcon kind="refresh"/, "Stage Refresh must have a refresh glyph");
assert.match(v6, /content-ai-action-icon/, "v6 must size action glyphs to the button label");

assert.match(config, /formatContentAiPromptVersion\(prompt\.version\)/, "Profile list must show a formatted version, not the raw CLASSIFICATION_PROMPT_ key as the title");
assert.match(config, /formatContentAiPromptVersion\(selectedPrompt\.version\)/, "Editor header must show the same formatted version");
assert.match(config, /content-ai-prompt-version/, "Version must render as a quiet instrument label");
assert.equal(formatContentAiPromptVersion("CLASSIFICATION_PROMPT_20260731144944"), "2026-07-31 · 14:49");
assert.equal(formatContentAiPromptVersion("CLASSIFICATION_PROMPT_V1_2"), "V1.2");
assert.equal(formatContentAiPromptVersion("CLASSIFICATION_PROMPT_V1"), "V1");
assert.match(
  v6,
  /content-ai-prompts-layout > aside[\s\S]{0,280}?background:\s*transparent/,
  "Prompt rail must sit on worksheet paper, not a nested mint well",
);
assert.match(
  v6,
  /content-ai-prompt-editor \{[\s\S]{0,280}?background:\s*transparent/,
  "Prompt editor must sit on worksheet paper, not a nested mint well",
);
assert.match(
  v6,
  /content-ai-prompt-row\.is-selected[\s\S]{0,220}?inset 2px 0 0 #2a4d41/,
  "Selected profile must use the strong ink spine, not a floating card",
);
assert.match(
  v6,
  /content-ai-prompt-editor > footer \{[\s\S]{0,280}?background:\s*transparent/,
  "Prompt editor footer must flush like Connection Test/Save",
);
assert.match(
  v6,
  /content-ai-prompt-row \{[\s\S]{0,280}?inset 0 -1px 0 #e4eee9/,
  "Every profile row must keep a hairline so unselected items are still list rows",
);
assert.match(
  v6,
  /prompts-layout > aside \{[\s\S]{0,360}?grid-template-rows:\s*auto minmax\(0,\s*1fr\) auto/,
  "Prompt rail must pin Create to the bottom of the stage height",
);
assert.match(
  v6,
  /aside > header strong/,
  "Section title size must not leak onto profile names",
);
assert.match(config, /content-ai-icon-btn/, "Create must be an icon-only control");
assert.match(config, /aria-label=\{t\("contentAi\.createPrompt"\)\}/, "Icon-only Create must keep an accessible name");
assert.doesNotMatch(
  config,
  /contentAi\.currentlyActive/,
  "Editor footer must drop Currently active; the list Active badge is the authority",
);
assert.match(api, /deleteContentAiPrompt/, "Web client must expose deleteContentAiPrompt");
assert.match(config, /deleteContentAiPrompt/, "Prompt rail must offer delete on a profile row");
assert.match(config, /ContentAiActionIcon kind="delete"/, "Delete must use the trash glyph");
assert.match(en, /"deletePromptConfirm":/, "en.json must include contentAi.deletePromptConfirm");
assert.match(vi, /"deletePromptConfirm":/, "vi.json must include contentAi.deletePromptConfirm");
assert.match(v6, /content-ai-icon-btn[\s\S]{0,220}?async-button__label[\s\S]{0,180}?clip:/, "Icon-only buttons must hide the visible label");

console.log("content-ai-settings-polish: PASS");
