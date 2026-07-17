import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  getLocalInstallRecipe,
  resolveTtsProviderKind,
  showsTtsApiKey,
  showsTtsBaseUrl,
  showsTtsLocalBackend
} from "../lib/opsTtsProviderCatalog";

const testDir = dirname(fileURLToPath(import.meta.url));
const pageSource = readFileSync(resolve(testDir, "../app/ops/tts-ai/page.tsx"), "utf8");
const componentSource = readFileSync(resolve(testDir, "../components/ops-console/OpsTtsAiPage.tsx"), "utf8");
const catalogSource = readFileSync(resolve(testDir, "../lib/opsTtsProviderCatalog.ts"), "utf8");
const apiSource = readFileSync(resolve(testDir, "../lib/api.ts"), "utf8");
const navSource = readFileSync(resolve(testDir, "../lib/navigationConfig.ts"), "utf8");
const cssSource = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const enSource = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");

assert.match(pageSource, /OpsTtsAiPage/, "Route must mount OpsTtsAiPage");
assert.match(componentSource, /fetchTtsAi/, "UI must load TTS AI via API");
assert.match(componentSource, /saveTtsAi/, "UI must save TTS AI via API");
assert.match(componentSource, /testTtsAi/, "UI must test TTS AI via API");
assert.match(componentSource, /ops-tts-kind-tabs/, "Must expose provider kind tabs");
assert.match(componentSource, /sectionInstall/, "Local kind must surface install section");
assert.match(componentSource, /copyInstallCommand/, "Must support copy install command");
assert.match(componentSource, /installTtsAiPackage/, "Must one-click install via API");
assert.match(componentSource, /onInstall/, "Must expose Install action");
assert.match(componentSource, /customProviderSlug/, "Must support custom Local/SDK provider name");
assert.match(componentSource, /resolveTtsReadyState/, "Must map Install+Test to ready chip");
assert.match(componentSource, /data-ready-state/, "Must expose ready state on chip");
assert.match(componentSource, /result\.catalog/, "Must apply Test catalog to Voice select");
assert.match(componentSource, /voiceFromCatalog/, "Must explain catalog-backed voices");
assert.match(componentSource, /previewTtsAiSpeech/, "Must support speech preview");
assert.match(componentSource, /sectionPreview/, "Must expose Preview speech section");
assert.match(componentSource, /ops-tts-preview-bar/, "Preview controls must sit in one bar");
assert.match(apiSource, /\/ops\/tts-ai\/preview/, "API helper must hit preview endpoint");
assert.match(componentSource, /sampleRate/, "Must show sample rate meta from catalog");
assert.match(componentSource, /EDGE_FALLBACK_VOICE_OPTIONS/, "Fallback edge voices must be selectable");
assert.match(componentSource, /styleHint/, "Must clarify reading style vs voice label");
assert.match(componentSource, /ops-form-field/, "Fields must use stacked ops-form-field layout");
assert.match(catalogSource, /TTS_PROVIDERS_BY_KIND/, "Catalog must define provider kinds");
assert.match(catalogSource, /"custom"/, "Catalog must include custom local provider");
assert.match(catalogSource, /pip install vieneu/, "Catalog must include VieNeu install recipe");
assert.match(catalogSource, /pip install edge-tts/, "Catalog must include edge install recipe");
assert.match(cssSource, /\.ops-tts-kind-tabs/, "CSS must style kind tabs");
assert.match(cssSource, /\.ops-tts-section--install/, "CSS must style install section");
assert.match(cssSource, /\.ops-tts-install-log/, "CSS must style install log");
assert.match(cssSource, /\.ops-tts-chip\.is-warn/, "CSS must style warn ready chip");
assert.match(apiSource, /\/ops\/tts-ai/, "API helper must hit /ops/tts-ai");
assert.match(apiSource, /\/ops\/tts-ai\/install/, "API helper must hit install endpoint");
assert.match(navSource, /nav\.ttsSettings/, "Nav must expose TTS settings");

const en = JSON.parse(enSource) as {
  opsTtsAi: {
    kindLocal: string;
    sectionInstall: string;
    installCommand: string;
    install: string;
    providerCustom: string;
    customProviderSlug: string;
    readyReady: string;
    readyInstalled: string;
    readyNotInstalled: string;
    readyUnchecked: string;
  };
  nav: { ttsSettings: string };
};
assert.equal(en.opsTtsAi.kindLocal, "Local / SDK");
assert.ok(en.opsTtsAi.sectionInstall.length > 0);
assert.ok(en.opsTtsAi.installCommand.length > 0);
assert.ok(en.opsTtsAi.install.length > 0);
assert.ok(en.opsTtsAi.providerCustom.length > 0);
assert.ok(en.opsTtsAi.customProviderSlug.length > 0);
assert.equal(en.opsTtsAi.readyReady, "Ready");
assert.ok(en.opsTtsAi.readyInstalled.length > 0);
assert.ok(en.opsTtsAi.readyNotInstalled.length > 0);
assert.ok(en.opsTtsAi.readyUnchecked.length > 0);
assert.ok(en.nav.ttsSettings.length > 0);

assert.equal(resolveTtsProviderKind("vieneu"), "local");
assert.equal(resolveTtsProviderKind("google"), "cloud");
assert.equal(resolveTtsProviderKind("openai_compatible"), "http");
assert.equal(resolveTtsProviderKind("auto"), "system");
assert.equal(showsTtsApiKey("google"), true);
assert.equal(showsTtsApiKey("edge"), false);
assert.equal(showsTtsBaseUrl("openai_compatible"), true);
assert.equal(showsTtsBaseUrl("vieneu"), false);
assert.equal(showsTtsBaseUrl("vieneu", "remote"), true);
assert.equal(showsTtsBaseUrl("vieneu", "auto"), false);
assert.equal(showsTtsLocalBackend("vieneu"), true);
assert.equal(getLocalInstallRecipe("vieneu")?.installCommand, "pip install vieneu");
assert.equal(getLocalInstallRecipe("edge")?.extraRequirement.includes("ffmpeg"), true);

console.log("ops-tts-ai tests passed");
