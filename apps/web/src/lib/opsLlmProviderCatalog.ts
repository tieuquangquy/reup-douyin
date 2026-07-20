/** LLM Ops provider presets for Translation / Caption AI (UI + gate authority). */

export type LlmRuntimeMode = "gemini" | "ollama" | "openai_compatible";

export type LlmProviderOption = {
  id: string;
  label: string;
  runtime: LlmRuntimeMode;
  /** Auto-filled when Base URL is empty on provider change. */
  defaultBaseUrl?: string;
};

/**
 * Dropdown order follows common IDE provider lists.
 * Most entries run as openai_compatible; gemini/ollama stay native.
 */
export const LLM_PROVIDER_OPTIONS: readonly LlmProviderOption[] = [
  { id: "amazon_bedrock", label: "Amazon Bedrock", runtime: "openai_compatible" },
  { id: "anthropic", label: "Anthropic", runtime: "openai_compatible" },
  { id: "baseten", label: "Baseten", runtime: "openai_compatible" },
  {
    id: "deepseek",
    label: "DeepSeek",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://api.deepseek.com/v1"
  },
  {
    id: "fireworks",
    label: "Fireworks AI",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://api.fireworks.ai/inference/v1"
  },
  { id: "gcp_vertex", label: "GCP Vertex AI", runtime: "openai_compatible" },
  { id: "gemini", label: "Google Gemini", runtime: "gemini" },
  { id: "litellm", label: "LiteLLM", runtime: "openai_compatible" },
  {
    id: "lmstudio",
    label: "LM Studio",
    runtime: "openai_compatible",
    defaultBaseUrl: "http://127.0.0.1:1234/v1"
  },
  {
    id: "minimax",
    label: "MiniMax",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://api.minimax.chat/v1"
  },
  {
    id: "mistral",
    label: "Mistral",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://api.mistral.ai/v1"
  },
  {
    id: "moonshot",
    label: "Moonshot",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://api.moonshot.cn/v1"
  },
  {
    id: "ollama",
    label: "Ollama",
    runtime: "ollama",
    defaultBaseUrl: "http://127.0.0.1:11434"
  },
  {
    id: "openai",
    label: "OpenAI",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://api.openai.com/v1"
  },
  { id: "openai_chatgpt", label: "OpenAI - ChatGPT Plus/Pro", runtime: "openai_compatible" },
  { id: "openai_compatible", label: "OpenAI Compatible", runtime: "openai_compatible" },
  {
    id: "openrouter",
    label: "OpenRouter",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://openrouter.ai/api/v1"
  },
  { id: "poe", label: "Poe", runtime: "openai_compatible" },
  { id: "qwen_code", label: "Qwen Code", runtime: "openai_compatible" },
  { id: "requesty", label: "Requesty", runtime: "openai_compatible" },
  { id: "sambanova", label: "SambaNova", runtime: "openai_compatible" },
  { id: "unbound", label: "Unbound", runtime: "openai_compatible" },
  { id: "vercel_ai_gateway", label: "Vercel AI Gateway", runtime: "openai_compatible" },
  { id: "vscode_lm", label: "VS Code LM API", runtime: "openai_compatible" },
  {
    id: "xai",
    label: "xAI (Grok)",
    runtime: "openai_compatible",
    defaultBaseUrl: "https://api.x.ai/v1"
  },
  { id: "zai", label: "Z.ai", runtime: "openai_compatible" }
] as const;

const BY_ID = new Map(LLM_PROVIDER_OPTIONS.map((option) => [option.id, option]));

/** Modes that never use the OpenAI-compatible HTTP client. */
const NATIVE_MODES = new Set<string>(["gemini", "ollama", "qwen"]);

export function llmProviderOption(provider: string): LlmProviderOption | undefined {
  return BY_ID.get((provider || "").trim().toLowerCase());
}

export function llmRuntimeMode(provider: string): LlmRuntimeMode | "unsupported" {
  const id = (provider || "").trim().toLowerCase();
  if (!id || id === "auto" || id === "placeholder" || id === "off" || id === "none") {
    return "unsupported";
  }
  const known = BY_ID.get(id);
  if (known) return known.runtime;
  if (id === "qwen") return "ollama";
  // Unknown saved ids still run as OpenAI-compatible gateways.
  return "openai_compatible";
}

export function defaultBaseUrlFor(provider: string): string {
  return llmProviderOption(provider)?.defaultBaseUrl || "";
}

export function showsLlmBaseUrl(provider: string): boolean {
  const mode = llmRuntimeMode(provider);
  return mode === "openai_compatible" || mode === "ollama";
}

export function showsLlmApiKey(provider: string): boolean {
  const mode = llmRuntimeMode(provider);
  return mode === "openai_compatible" || mode === "gemini";
}

export function llmProviderLabel(provider: string): string {
  const id = (provider || "").trim();
  if (!id) return "";
  return llmProviderOption(id)?.label || id;
}

export function isNativeLlmProvider(provider: string): boolean {
  const id = (provider || "").trim().toLowerCase();
  return NATIVE_MODES.has(id) || llmRuntimeMode(id) === "gemini" || llmRuntimeMode(id) === "ollama";
}
