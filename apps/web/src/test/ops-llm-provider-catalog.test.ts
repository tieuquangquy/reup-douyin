/**
 * LLM provider preset catalog + Ops form wiring (Translation / Caption).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  defaultBaseUrlFor,
  LLM_PROVIDER_OPTIONS,
  llmProviderCategory,
  llmRuntimeMode,
  showsLlmApiKey,
  showsLlmBaseUrl
} from "../lib/opsLlmProviderCatalog";
import { modelListReady } from "../components/ops-console/OpsLlmAiSetupsPage";

const sharedSource = readFileSync("src/components/ops-console/OpsLlmAiSetupsPage.tsx", "utf8");
const catalogSource = readFileSync("src/lib/opsLlmProviderCatalog.ts", "utf8");

assert.ok(LLM_PROVIDER_OPTIONS.length >= 20, "Catalog must include the expanded provider list");
assert.equal(llmRuntimeMode("gemini"), "gemini");
assert.equal(llmRuntimeMode("ollama"), "ollama");
assert.equal(llmRuntimeMode("openrouter"), "openai_compatible");
assert.equal(llmRuntimeMode("deepseek"), "openai_compatible");
assert.equal(llmRuntimeMode("custom_gateway"), "openai_compatible");
assert.equal(llmRuntimeMode(""), "unsupported");
assert.equal(defaultBaseUrlFor("openrouter"), "https://openrouter.ai/api/v1");
assert.equal(defaultBaseUrlFor("openai_compatible"), "");
assert.equal(defaultBaseUrlFor("ollama"), "http://127.0.0.1:11434");
assert.equal(showsLlmBaseUrl("openrouter"), true);
assert.equal(showsLlmApiKey("openrouter"), true);
assert.equal(showsLlmApiKey("ollama"), false);
assert.equal(showsLlmBaseUrl("gemini"), false);
assert.equal(llmProviderCategory("ollama"), "local");
assert.equal(llmProviderCategory("openai", "http://localhost:4000/v1"), "local");
assert.equal(llmProviderCategory("openrouter"), "gateway");
assert.equal(llmProviderCategory("gemini"), "cloud");
assert.equal(llmProviderCategory("auto"), "system");

assert.equal(modelListReady("openrouter", true, "https://openrouter.ai/api/v1"), true);
assert.equal(modelListReady("openrouter", true, ""), false);
assert.equal(modelListReady("deepseek", true, "https://api.deepseek.com/v1"), true);
assert.equal(modelListReady("gemini", true, ""), true);
assert.equal(modelListReady("openai_compatible", true, "https://api.openai.com/v1"), true);

assert.match(sharedSource, /LLM_PROVIDER_OPTIONS\.map/, "Provider select must render from catalog");
assert.match(sharedSource, /defaultBaseUrlFor\(next\)/, "Provider change must autofill default Base URL when empty");
assert.match(sharedSource, /showsApiKey\(profile\.provider\)/, "Registry must not report a missing key for keyless local runtimes");
assert.doesNotMatch(sharedSource, /hasFallbackColumn/, "Registry must not reserve a sparse fallback column");
assert.match(sharedSource, /FB:/, "Configured fallback must fold into the compact runtime cell");
assert.match(catalogSource, /OpenRouter/, "Catalog must include OpenRouter label");
assert.match(catalogSource, /Amazon Bedrock/, "Catalog must include Amazon Bedrock label");
assert.match(catalogSource, /xAI \(Grok\)/, "Catalog must include xAI label");

console.log("ops llm provider catalog tests passed");
