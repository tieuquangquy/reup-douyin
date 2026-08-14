import assert from "node:assert/strict";
import {
  catalogFromRuntime,
  detailLooksLikeNotInstalled,
  resolveTtsReadyState,
  ttsReadyChipClass
} from "../lib/opsTtsReadyState";

assert.equal(resolveTtsReadyState({ test: null, install: null }), "unchecked");

assert.equal(
  resolveTtsReadyState({
    test: null,
    install: { ok: true, detail: "Successfully installed edge-tts" }
  }),
  "installed"
);

assert.equal(
  resolveTtsReadyState({
    test: { ok: true, detail: "vieneu import ready" },
    install: { ok: true, detail: "ok" }
  }),
  "ready"
);

assert.equal(
  resolveTtsReadyState({
    test: null,
    install: null,
    runtime: {
      last_probe: { ok: true, detail: "ready", provider: "vieneu" },
      last_install: { ok: true, detail: "ok" }
    },
    liveImportOk: true
  }),
  "ready"
);

assert.equal(
  resolveTtsReadyState({
    test: null,
    install: null,
    runtime: {
      last_probe: { ok: true, detail: "ready", provider: "vieneu" }
    },
    liveImportOk: false
  }),
  "not_installed"
);

assert.equal(
  resolveTtsReadyState({
    test: { ok: false, detail: "vieneu not installed. Run: pip install vieneu" },
    install: null
  }),
  "not_installed"
);

assert.equal(detailLooksLikeNotInstalled("edge-tts not installed. Run: pip install edge-tts"), true);
assert.equal(ttsReadyChipClass("ready"), "is-active");

const catalog = catalogFromRuntime({
  last_probe: {
    ok: true,
    catalog: {
      source: "sdk",
      voices: [{ id: "A", label: "A" }],
      styles: ["tu_nhien"],
      models: ["v3turbo"],
      default_voice_id: "A",
      warning: ""
    }
  }
});
assert.equal(catalog?.source, "sdk");
assert.equal(catalog?.voices[0]?.id, "A");

assert.equal(
  catalogFromRuntime(
    {
      last_probe: {
        ok: true,
        provider: "google",
        catalog: {
          source: "provider",
          voices: [{ id: "vi-VN-Chirp3-HD-Aoede", label: "Aoede" }],
          styles: [],
          models: [],
          default_voice_id: "vi-VN-Chirp3-HD-Aoede",
          warning: ""
        }
      }
    },
    "google_gemini"
  ),
  null,
  "A persisted catalog from another provider must never hydrate the current editor"
);

const richRemoteCatalog = catalogFromRuntime({
  last_probe: {
    ok: true,
    catalog: {
      source: "provider_api",
      voices: [],
      styles: [],
      models: [],
      model_options: [{ id: "tts-pro", label: "TTS Pro", languages: ["vi"] }],
      languages: [{ code: "vi", label: "Vietnamese" }],
      default_voice_id: "",
      default_model_id: "tts-pro",
      default_language_code: "vi",
      discovery: { status: "partial", endpoints: ["/models"], warnings: [] },
      warning: ""
    }
  }
});
assert.equal(richRemoteCatalog?.model_options?.[0]?.id, "tts-pro");
assert.equal(richRemoteCatalog?.discovery?.status, "partial");

console.log("ops-tts-ready-state tests passed");
