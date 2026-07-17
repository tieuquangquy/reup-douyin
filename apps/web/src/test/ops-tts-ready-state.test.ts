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

console.log("ops-tts-ready-state tests passed");
