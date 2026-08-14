import assert from "node:assert/strict";
import {
  canonicalizeGeminiVoiceId,
  defaultProviderForKind,
  filterTtsCatalogLanguages,
  filterTtsCatalogModels,
  filterTtsCatalogVoices,
  getLocalInstallRecipe,
  getTtsFieldCapabilities,
  GEMINI_TTS_VOICES,
  isPresetLocalProvider,
  looksLikeEdgeVoiceId,
  OMNIVOICE_CURATED_MODELS,
  OMNIVOICE_CURATED_VOICES,
  OMNIVOICE_SUPPORTED_MODELS,
  resolveProviderSlugFromInstall,
  resolveTtsCatalogForProvider,
  resolveTtsProviderKind,
  showsTtsBaseUrl,
  ttsCatalogLanguageOptions,
  ttsCatalogModelOptions,
  TTS_PROVIDERS_BY_KIND
} from "../lib/opsTtsProviderCatalog";
import type { TtsAiCatalog } from "../lib/api";

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

const geminiCatalog = resolveTtsCatalogForProvider("google_gemini", null);
assert.ok(geminiCatalog, "Gemini must hydrate its provider-native voice catalog without a remote list endpoint");
assert.equal(geminiCatalog?.default_voice_id, "Kore");
assert.ok(GEMINI_TTS_VOICES.length >= 30);
assert.ok(geminiCatalog?.voices.some((voice) => voice.id === "Aoede"));
assert.ok(geminiCatalog?.voices.every((voice) => !voice.id.includes("Chirp3-HD")));
assert.equal(canonicalizeGeminiVoiceId("vi-VN-Chirp3-HD-Aoede"), "Aoede");
assert.equal(canonicalizeGeminiVoiceId("not-a-gemini-voice"), "");

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

const remoteCatalog = {
  source: "provider_api",
  voices: [
    { id: "vi-female", label: "Vietnamese female", languages: ["vi"], models: ["tts-pro"] },
    { id: "en-male", label: "English male", languages: ["en-US"], models: ["tts-lite"] }
  ],
  styles: [],
  // Legacy model ids remain usable beside richer metadata.
  models: ["legacy-model"],
  model_options: [
    { id: "tts-pro", label: "TTS Pro", languages: ["vi", "en-US"], voices: ["vi-female"] },
    { id: "tts-lite", label: "TTS Lite", languages: ["en-US"], voices: ["en-male"] }
  ],
  languages: [{ code: "vi", label: "Vietnamese" }],
  default_voice_id: "vi-female",
  default_model_id: "tts-pro",
  default_language_code: "vi",
  discovery: { status: "partial", endpoints: ["/models"], warnings: ["Voice endpoint unavailable"] },
  warning: ""
} satisfies TtsAiCatalog;

assert.deepEqual(
  ttsCatalogModelOptions(remoteCatalog).map((model) => model.id),
  ["tts-pro", "tts-lite", "legacy-model"],
  "Rich model options must merge with legacy string ids"
);
assert.deepEqual(
  ttsCatalogLanguageOptions(remoteCatalog).map((language) => language.code),
  ["vi", "en-US"],
  "Partial catalogs must infer missing language choices from model/voice metadata"
);
assert.deepEqual(
  filterTtsCatalogModels(remoteCatalog, { languageCode: "vi-VN", voiceId: "vi-female" }).map(
    (model) => model.id
  ),
  ["tts-pro"],
  "Model choices must respect language and voice compatibility metadata"
);
assert.deepEqual(
  filterTtsCatalogVoices(remoteCatalog, { languageCode: "en-US", modelId: "tts-lite" }).map(
    (voice) => voice.id
  ),
  ["en-male"],
  "Voice choices must respect selected model and language"
);
assert.deepEqual(
  filterTtsCatalogModels(remoteCatalog, { languageCode: "vi", voiceId: "vendor-manual-voice" }).map(
    (model) => model.id
  ),
  ["tts-pro", "legacy-model"],
  "An unknown manual voice id must not incorrectly eliminate otherwise compatible model choices"
);
assert.deepEqual(
  filterTtsCatalogLanguages(remoteCatalog, { modelId: "tts-pro", voiceId: "vi-female" }).map(
    (language) => language.code
  ),
  ["vi"],
  "Language choices must be the intersection of selected model and voice metadata"
);

console.log("ops-tts-provider-catalog tests passed");
