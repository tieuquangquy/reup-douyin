import assert from "node:assert/strict";
import {
  defaultProviderForKind,
  getLocalInstallRecipe,
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

console.log("ops-tts-provider-catalog tests passed");
