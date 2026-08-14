import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const component = readFileSync(resolve(testDir, "../components/ops-console/OpsTtsAiPage.tsx"), "utf8");
const helper = readFileSync(resolve(testDir, "../lib/ttsHttpConnector.ts"), "utf8");
const css = readFileSync(resolve(testDir, "../app/globals.css"), "utf8");
const en = readFileSync(resolve(testDir, "../lib/i18n/en.json"), "utf8");
const vi = readFileSync(resolve(testDir, "../lib/i18n/vi.json"), "utf8");

assert.match(component, /httpConnectorFromOptions/, "Saved connector mapping must hydrate into the editor");
assert.match(component, /httpConnectorToOptions/, "Connector mapping must be persisted with the profile");
assert.match(component, /HTTP_CONNECTOR_MODES/, "HTTP connector must expose Auto/OpenAPI/Custom modes");
assert.match(
  component,
  /\{\(isCloud \|\| isHttp\) && !isGoogle \? \(/,
  "Universal mapping must remain available for Cloud and HTTP providers except Google's fixed OAuth contract"
);
assert.match(component, /isHttp \|\| isCloud \|\| fieldCaps\.base_url/, "All Cloud/HTTP mappings must be able to set a Base URL");
assert.match(component, /genericSynthesisConfigured/, "Configured Cloud connector synthesis must bypass the legacy fallback-only preview gate");
assert.match(component, /httpModeAuto/, "Auto mode must have an explicit label");
assert.match(component, /httpAuthenticationTitle/, "Authentication must be a separate mapping section");
assert.match(component, /httpCatalogMappingTitle/, "Catalog must be a separate mapping section");
assert.match(component, /httpSynthesisMappingTitle/, "Synthesis must be a separate mapping section");
assert.match(component, /parseTtsCurl/, "The editor must offer deterministic cURL import");
assert.match(component, /httpRawKeyHint/, "The editor must explain raw-key/prefix handling");
assert.match(component, /httpConnectorSteps/, "The editor must distinguish auth/catalog/synthesis status");
assert.match(helper, /Credentials were detected but intentionally not imported/, "cURL import must never retain credentials");
assert.match(helper, /\{\{model_id\}\}/, "cURL import must normalize common model fields");
assert.match(helper, /\{\{voice_id\}\}/, "cURL import must normalize common voice fields");
assert.match(helper, /return \{\};/, "Untouched Auto mode must preserve legacy discovery");
assert.match(css, /\.ops-tts-http-connector/, "Universal connector requires a compact panel style");
assert.match(css, /\.ops-tts-http-step\.is-ok/, "Connector status steps need success color");
assert.match(css, /\.ops-tts-http-step\.is-error/, "Connector status steps need error color");
assert.match(en, /"httpConnectorTitle"/, "English connector copy must exist");
assert.match(vi, /"httpConnectorTitle"/, "Vietnamese connector copy must exist");

console.log("ops tts universal connector UI tests passed");
