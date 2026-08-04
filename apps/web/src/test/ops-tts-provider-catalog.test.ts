import assert from "node:assert/strict";
import {
  defaultProviderForKind,
  getLocalInstallRecipe,
  getTtsFieldCapabilities,
  isPresetLocalProvider,
  looksLikeEdgeVoiceId,
  OMNIVOICE_CURATED_MODELS,
  OMNIVOICE_CURATED_VOICES,
  OMNIVOICE_SUPPORTED_MODELS,
  resolveProviderSlugFromInstall,
  resolveTtsCatalogForProvider,
  resolveTtsProviderKind,
  showsTtsBaseUrl,
  TTS_PROVIDERS_BY_KIND
} from "../lib/opsTtsProviderCatalog";

assert.deepEqual([...TTS_PROVIDERS_BY_KIND.local], ["edge", "vieneu", "omnivoice", "cli", "custom"]);
assert.equal(defaultProviderForKind("cloud"), "google");
assert.equal(resolveTtsProviderKind("http_custom"), "http");
assert.equal(resolveTtsProviderKind("my_tts_sdk"), "local");
assert.equal(getLocalInstallRecipe("cli")?.installCommand, "");
assert.equal(getLocalInstallRecipe("google"), null);
assert.equal(getLocalInstallRecipe("custom"), null);
assert.equal(showsTtsBaseUrl("vieneu", "auto"), false);
assert.equal(showsTtsBaseUrl("vieneu", "remote"), true);

const edgeCaps = getTtsFieldCapabilities("edge");
assert.equal(edgeCaps.voice, true);
assert.equal(edgeCaps.model, false);

const vieneuCaps = getTtsFieldCapabilities("vieneu");
assert.equal(vieneuCaps.model, true);
assert.equal(vieneuCaps.styles, true);
assert.equal(vieneuCaps.local_backend, true);

const customCaps = getTtsFieldCapabilities("omnivoice");
assert.equal(customCaps.voice, true);
assert.equal(customCaps.model, true);
assert.equal(customCaps.api_key, false);

const unknownCaps = getTtsFieldCapabilities("my_tts_sdk");
assert.equal(unknownCaps.model, true);

assert.equal(looksLikeEdgeVoiceId("vi-VN-HoaiMyNeural"), true);
assert.equal(looksLikeEdgeVoiceId("Phạm Tuyên"), false);
assert.equal(looksLikeEdgeVoiceId(""), false);

assert.equal(resolveProviderSlugFromInstall("OmniVoice-Studio"), "omnivoice");
assert.equal(isPresetLocalProvider("omnivoice"), true);
const omniRecipe = getLocalInstallRecipe("OmniVoice-Studio");
assert.ok(omniRecipe);
assert.equal(omniRecipe.defaultModel, "k2-fsa/OmniVoice");
assert.equal(omniRecipe.defaultVoice, "auto");
assert.equal(omniRecipe.defaultLanguage, "vi");
assert.ok(OMNIVOICE_CURATED_MODELS.length >= 12);
assert.ok(OMNIVOICE_CURATED_VOICES.length >= 10);
assert.equal(OMNIVOICE_CURATED_VOICES[0].id, "auto");
assert.deepEqual([...OMNIVOICE_SUPPORTED_MODELS], ["k2-fsa/OmniVoice"]);

const omniFallbackCatalog = resolveTtsCatalogForProvider("omnivoice", null);
assert.ok(omniFallbackCatalog, "OmniVoice must hydrate a curated catalog when persisted probe catalog is missing");
assert.ok((omniFallbackCatalog?.voices.length ?? 0) >= 10);
assert.deepEqual(omniFallbackCatalog?.models, ["k2-fsa/OmniVoice"]);
assert.equal(omniFallbackCatalog?.default_voice_id, "auto");

const staleOmniCatalog = resolveTtsCatalogForProvider("omnivoice", {
  source: "sdk",
  voices: [],
  styles: [],
  models: ["cosyvoice", "k2-fsa/OmniVoice"],
  default_voice_id: "",
  warning: "legacy catalog"
});
assert.ok((staleOmniCatalog?.voices.length ?? 0) >= 10, "Missing persisted voices must use curated fallback");
assert.deepEqual(
  staleOmniCatalog?.models,
  ["k2-fsa/OmniVoice"],
  "Models without a wired synthesize adapter must not be selectable"
);

const persistedOmniCatalog = resolveTtsCatalogForProvider("omnivoice", {
  source: "sdk",
  voices: [{ id: "provider-voice", label: "Provider voice" }],
  styles: [],
  models: ["k2-fsa/OmniVoice"],
  default_voice_id: "provider-voice",
  warning: ""
});
assert.deepEqual(
  persistedOmniCatalog?.voices,
  [{ id: "provider-voice", label: "Provider voice" }],
  "A persisted OmniVoice catalog must take precedence over the curated voice fallback"
);

const customCatalog = {
  source: "sdk",
  voices: [{ id: "voice-a", label: "Voice A" }],
  styles: [],
  models: ["model-a"],
  default_voice_id: "voice-a",
  warning: ""
};
assert.equal(
  resolveTtsCatalogForProvider("my_tts_sdk", customCatalog),
  customCatalog,
  "Unknown custom providers must preserve their provider-owned catalog"
);

const overridden = getTtsFieldCapabilities("edge", "auto", { model: true });
assert.equal(overridden.model, true);
assert.equal(overridden.voice, true);

console.log("ops-tts-provider-catalog tests passed");
