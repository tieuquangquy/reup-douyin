import assert from "node:assert/strict";
import {
  defaultProviderForKind,
  getLocalInstallRecipe,
  getTtsFieldCapabilities,
  looksLikeEdgeVoiceId,
  OMNIVOICE_CURATED_MODELS,
  OMNIVOICE_CURATED_VOICES,
  resolveProviderSlugFromInstall,
  resolveTtsProviderKind,
  showsTtsBaseUrl,
  TTS_PROVIDERS_BY_KIND
} from "../lib/opsTtsProviderCatalog";

assert.deepEqual([...TTS_PROVIDERS_BY_KIND.local], ["edge", "vieneu", "cli", "custom"]);
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
const omniRecipe = getLocalInstallRecipe("OmniVoice-Studio");
assert.ok(omniRecipe);
assert.equal(omniRecipe.defaultModel, "omnivoice");
assert.equal(omniRecipe.defaultVoice, "auto");
assert.equal(omniRecipe.defaultLanguage, "vi");
assert.ok(OMNIVOICE_CURATED_MODELS.length >= 12);
assert.ok(OMNIVOICE_CURATED_VOICES.length >= 10);
assert.equal(OMNIVOICE_CURATED_VOICES[0].id, "auto");

const overridden = getTtsFieldCapabilities("edge", "auto", { model: true });
assert.equal(overridden.model, true);
assert.equal(overridden.voice, true);

console.log("ops-tts-provider-catalog tests passed");
