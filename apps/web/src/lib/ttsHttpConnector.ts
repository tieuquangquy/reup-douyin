/**
 * Browser-safe state and helpers for the universal HTTP TTS connector.
 *
 * This module deliberately contains no network calls and never returns API
 * key values from cURL input. The API owns the actual secret and request
 * execution; the web app only edits the connector manifest.
 */

export type HttpConnectorMode = "auto" | "openapi" | "custom";
export type HttpConnectorAuthType = "none" | "bearer" | "header" | "query";
export type HttpConnectorResponseType = "binary" | "json_base64" | "json_url" | "async_json";

export type HttpConnectorEndpoint = {
  path: string;
  method: string;
  content_type: string;
  body: string;
  items_path: string;
  id_path: string;
  label_path: string;
  languages_path: string;
  models_path: string;
  voices_path: string;
  gender_path: string;
  description_path: string;
  capabilities_path: string;
};

export type HttpConnectorFormState = {
  version: 1;
  mode: HttpConnectorMode;
  openapiUrl: string;
  authType: HttpConnectorAuthType;
  authHeader: string;
  authPrefix: string;
  authQueryName: string;
  authTestPath: string;
  authTestMethod: string;
  catalog: {
    models: HttpConnectorEndpoint;
    voices: HttpConnectorEndpoint;
    languages: HttpConnectorEndpoint;
  };
  synthesisPath: string;
  synthesisMethod: string;
  synthesisContentType: string;
  synthesisBody: string;
  synthesisResponseType: HttpConnectorResponseType;
  synthesisAudioPath: string;
  synthesisMimeType: string;
  synthesisMimeTypePath: string;
  synthesisDurationPath: string;
  synthesisFileExtension: string;
  pollingJobIdPath: string;
  pollingPath: string;
  pollingMethod: string;
  pollingContentType: string;
  pollingBody: string;
  pollingStatusPath: string;
  pollingSuccessValues: string;
  pollingFailureValues: string;
  pollingIntervalSeconds: string;
  pollingMaxAttempts: string;
  pollingResponseType: Exclude<HttpConnectorResponseType, "async_json">;
  pollingAudioPath: string;
  pollingMimeTypePath: string;
  pollingDurationPath: string;
};

export type CurlConnectorImport = {
  baseUrl: string;
  method: string;
  synthesisPath: string;
  contentType: string;
  body: string;
  authType: HttpConnectorAuthType;
  authHeader: string;
  authPrefix: string;
  authQueryName: string;
  keyDetected: boolean;
  warning?: string;
};

/** Declarative mapping for Lucylab's two-step JSON-RPC TTS API. */
export function lucylabJsonRpcPreset(): Partial<HttpConnectorFormState> {
  const voices = emptyHttpConnectorEndpoint();
  voices.path = "/json-rpc";
  voices.method = "POST";
  voices.content_type = "application/json";
  voices.body = JSON.stringify({
    method: "getUserVoices",
    input: { limit: 10, page: 1 }
  }, null, 2);
  voices.items_path = "result.items";
  voices.id_path = "id";
  voices.label_path = "name";
  return {
    mode: "custom",
    authType: "bearer",
    authHeader: "Authorization",
    authPrefix: "Bearer ",
    authQueryName: "",
    authTestPath: "",
    authTestMethod: "GET",
    catalog: {
      models: emptyHttpConnectorEndpoint(),
      voices,
      languages: emptyHttpConnectorEndpoint("code")
    },
    synthesisPath: "/json-rpc",
    synthesisMethod: "POST",
    synthesisContentType: "application/json",
    synthesisBody: JSON.stringify({
      method: "ttsLongText",
      input: {
        text: "{{text}}",
        userVoiceId: "{{voice_id}}",
        speed: "{{speaking_rate}}"
      }
    }, null, 2),
    synthesisResponseType: "async_json",
    synthesisAudioPath: "",
    synthesisMimeType: "audio/mpeg",
    synthesisMimeTypePath: "",
    synthesisDurationPath: "",
    synthesisFileExtension: "mp3",
    pollingJobIdPath: "result.projectExportId",
    pollingPath: "/json-rpc",
    pollingMethod: "POST",
    pollingContentType: "application/json",
    pollingBody: JSON.stringify({
      method: "getExportStatus",
      input: { projectExportId: "{{job_id}}" }
    }, null, 2),
    pollingStatusPath: "result.state",
    pollingSuccessValues: "completed, succeeded, success, done, finished",
    pollingFailureValues: "failed, error, cancelled, canceled",
    pollingIntervalSeconds: "2",
    pollingMaxAttempts: "60",
    pollingResponseType: "json_url",
    pollingAudioPath: "result.url",
    pollingMimeTypePath: "",
    pollingDurationPath: ""
  };
}

export function emptyHttpConnectorEndpoint(idPath = "id"): HttpConnectorEndpoint {
  return {
    path: "",
    method: "GET",
    content_type: "application/json",
    body: "",
    items_path: "",
    id_path: idPath,
    label_path: "name",
    languages_path: "",
    models_path: "",
    voices_path: "",
    gender_path: "",
    description_path: "",
    capabilities_path: ""
  };
}

export function defaultHttpConnector(): HttpConnectorFormState {
  return {
    version: 1,
    mode: "auto",
    openapiUrl: "",
    authType: "bearer",
    authHeader: "Authorization",
    authPrefix: "Bearer ",
    authQueryName: "",
    authTestPath: "",
    authTestMethod: "GET",
    catalog: {
      models: emptyHttpConnectorEndpoint(),
      voices: emptyHttpConnectorEndpoint(),
      languages: emptyHttpConnectorEndpoint("code")
    },
    synthesisPath: "",
    synthesisMethod: "POST",
    synthesisContentType: "application/json",
    synthesisBody: '{\n  "model": "{{model_id}}",\n  "voice": "{{voice_id}}",\n  "input": "{{text}}"\n}',
    synthesisResponseType: "binary",
    synthesisAudioPath: "",
    synthesisMimeType: "audio/mpeg",
    synthesisMimeTypePath: "",
    synthesisDurationPath: "",
    synthesisFileExtension: "mp3",
    pollingJobIdPath: "",
    pollingPath: "",
    pollingMethod: "GET",
    pollingContentType: "application/json",
    pollingBody: "",
    pollingStatusPath: "",
    pollingSuccessValues: "completed, succeeded, success, done",
    pollingFailureValues: "failed, error, cancelled, canceled",
    pollingIntervalSeconds: "2",
    pollingMaxAttempts: "30",
    pollingResponseType: "json_url",
    pollingAudioPath: "",
    pollingMimeTypePath: "",
    pollingDurationPath: ""
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stringValue(value: unknown, fallback = ""): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    const result = stringValue(value).trim();
    if (result) return result;
  }
  return "";
}

function stringList(value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => stringValue(item).trim()).filter(Boolean).join(", ");
  return stringValue(value);
}

function endpointFromRaw(value: unknown, defaultIdPath = "id"): HttpConnectorEndpoint {
  const source = isRecord(value) ? value : {};
  return {
    path: firstString(source.path, source.url),
    method: firstString(source.method, "GET").toUpperCase(),
    content_type: firstString(source.content_type, source.contentType, "application/json"),
    body: (() => {
      const body = source.body ?? source.body_template ?? source.request_template;
      if (typeof body === "string") return body;
      if (body === undefined) return "";
      try {
        return JSON.stringify(body, null, 2);
      } catch {
        return "";
      }
    })(),
    items_path: firstString(source.items_path, source.itemsPath),
    id_path: firstString(source.id_path, source.idPath, defaultIdPath),
    label_path: firstString(source.label_path, source.labelPath, "name"),
    languages_path: firstString(source.languages_path, source.languagesPath),
    models_path: firstString(source.models_path, source.modelsPath),
    voices_path: firstString(source.voices_path, source.voicesPath),
    gender_path: firstString(source.gender_path, source.genderPath),
    description_path: firstString(source.description_path, source.descriptionPath),
    capabilities_path: firstString(source.capabilities_path, source.capabilitiesPath)
  };
}

/** Hydrate UI state from both the v1 canonical shape and the early draft aliases. */
export function httpConnectorFromOptions(options: Record<string, unknown> | undefined): HttpConnectorFormState {
  const defaults = defaultHttpConnector();
  const raw = isRecord(options?.http_connector) ? options.http_connector : {};
  const auth = isRecord(raw.auth) ? raw.auth : {};
  const openapi = isRecord(raw.openapi) ? raw.openapi : {};
  const catalog = isRecord(raw.catalog) ? raw.catalog : isRecord(raw.discovery) ? raw.discovery : {};
  const synthesis = isRecord(raw.synthesis) ? raw.synthesis : {};
  const response = isRecord(synthesis.response) ? synthesis.response : {};
  const polling = isRecord(synthesis.polling) ? synthesis.polling : {};
  const oldSynthesis = isRecord(raw.synthesis) ? raw.synthesis : {};
  const oldDiscovery = isRecord(raw.discovery) ? raw.discovery : {};
  const endpoint = (key: "models" | "voices" | "languages") =>
    endpointFromRaw(catalog[key] || oldDiscovery[key] || defaults.catalog[key], key === "languages" ? "code" : "id");
  const authType = (["none", "bearer", "header", "query"].includes(stringValue(auth.type))
    ? stringValue(auth.type)
    : defaults.authType) as HttpConnectorAuthType;
  const authDefaultHeader = authType === "header" ? "X-API-Key" : "Authorization";
  const authDefaultPrefix = authType === "bearer" ? "Bearer " : "";
  const body = synthesis.body;
  let synthesisBody = stringValue(synthesis.request_template);
  if (!synthesisBody && body !== undefined) {
    try {
      synthesisBody = JSON.stringify(body, null, 2);
    } catch {
      synthesisBody = "";
    }
  }
  return {
    ...defaults,
    mode: ["auto", "openapi", "custom"].includes(stringValue(raw.mode))
      ? (stringValue(raw.mode) as HttpConnectorMode)
      : defaults.mode,
    openapiUrl: firstString(openapi.url, raw.openapi_url),
    authType,
    authHeader: firstString(auth.header_name, auth.header, authDefaultHeader),
    authPrefix: typeof auth.prefix === "string" ? auth.prefix : authDefaultPrefix,
    authQueryName: firstString(auth.query_name, auth.queryName, authType === "query" ? "api_key" : ""),
    authTestPath: firstString(auth.test_path, auth.testPath),
    authTestMethod: firstString(auth.test_method, auth.testMethod, defaults.authTestMethod).toUpperCase(),
    catalog: {
      models: endpoint("models"),
      voices: endpoint("voices"),
      languages: endpoint("languages")
    },
    synthesisPath: firstString(synthesis.path),
    synthesisMethod: firstString(synthesis.method, defaults.synthesisMethod).toUpperCase(),
    synthesisContentType: firstString(synthesis.content_type, synthesis.contentType, defaults.synthesisContentType),
    synthesisBody: synthesisBody || defaults.synthesisBody,
    synthesisResponseType: ((): HttpConnectorResponseType => {
      const value = firstString(response.type, rawSynthesisResponse(oldSynthesis));
      if (value === "audio_binary") return "binary";
      if (["binary", "json_base64", "json_url", "async_json"].includes(value)) {
        return value as HttpConnectorResponseType;
      }
      return defaults.synthesisResponseType;
    })(),
    synthesisAudioPath: firstString(response.audio_path, synthesis.audio_path),
    synthesisMimeType: firstString(response.mime_type, synthesis.mime_type, defaults.synthesisMimeType),
    synthesisMimeTypePath: firstString(response.mime_type_path, synthesis.mime_type_path),
    synthesisDurationPath: firstString(response.duration_path, synthesis.duration_path),
    synthesisFileExtension: firstString(response.file_extension, synthesis.file_extension, defaults.synthesisFileExtension),
    pollingJobIdPath: firstString(polling.job_id_path, synthesis.job_id_path),
    pollingPath: firstString(polling.poll_path, polling.poll_path_template, synthesis.poll_path_template),
    pollingMethod: firstString(polling.method, polling.poll_method, polling.pollMethod, "GET").toUpperCase(),
    pollingContentType: firstString(polling.content_type, polling.contentType, "application/json"),
    pollingBody: (() => {
      const value = polling.body ?? polling.body_template ?? polling.request_template;
      if (typeof value === "string") return value;
      if (value === undefined) return "";
      try {
        return JSON.stringify(value, null, 2);
      } catch {
        return "";
      }
    })(),
    pollingStatusPath: firstString(polling.status_path, synthesis.status_path),
    pollingSuccessValues: stringList(polling.success_values ?? synthesis.success_values ?? defaults.pollingSuccessValues),
    pollingFailureValues: stringList(polling.failure_values ?? synthesis.failure_values ?? defaults.pollingFailureValues),
    pollingIntervalSeconds: firstString(polling.interval_seconds, defaults.pollingIntervalSeconds),
    pollingMaxAttempts: firstString(polling.max_attempts, defaults.pollingMaxAttempts),
    pollingResponseType: (["binary", "json_base64", "json_url"].includes(firstString(polling.response_type))
      ? firstString(polling.response_type)
      : defaults.pollingResponseType) as Exclude<HttpConnectorResponseType, "async_json">,
    pollingAudioPath: firstString(polling.audio_path, defaults.pollingAudioPath),
    pollingMimeTypePath: firstString(polling.mime_type_path, defaults.pollingMimeTypePath),
    pollingDurationPath: firstString(polling.duration_path, defaults.pollingDurationPath)
  };
}

function rawSynthesisResponse(value: Record<string, unknown>): string {
  return firstString(value.response_type, value.responseType);
}

function parseCommaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseBodyTemplate(value: string): Record<string, unknown> | string {
  try {
    const parsed: unknown = JSON.parse(value);
    return isRecord(parsed) ? parsed : value;
  } catch {
    return value;
  }
}

function sanitizeBodyTemplate(value: string): string {
  if (!value.trim()) return value;
  try {
    const parsed: unknown = JSON.parse(value);
    return JSON.stringify(scrubSecretsOnly(parsed), null, 2);
  } catch {
    return value.replace(
      /(authorization|api[-_]?key|access[-_]?token|token|secret|password)\s*[:=]\s*[^,\s}]+/gi,
      "$1: \"\""
    );
  }
}

function scrubSecretsOnly(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(scrubSecretsOnly);
  if (!isRecord(value)) {
    if (
      typeof value === "string" &&
      /^(?:bearer\s+\S+|sk[-_][A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.)/i.test(value.trim())
    ) {
      return "";
    }
    return value;
  }
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (/authorization|api[-_]?key|access[-_]?token|secret|password|cookie/i.test(key)) continue;
    result[key] = scrubSecretsOnly(item);
  }
  return result;
}

function serializeEndpoint(endpoint: HttpConnectorEndpoint): Record<string, unknown> {
  const result: Record<string, unknown> = {
    path: endpoint.path.trim(),
    method: endpoint.method.trim().toUpperCase() || "GET",
    content_type: endpoint.content_type.trim() || "application/json",
    body: parseBodyTemplate(sanitizeBodyTemplate(endpoint.body)),
    items_path: endpoint.items_path.trim(),
    id_path: endpoint.id_path.trim(),
    label_path: endpoint.label_path.trim()
  };
  for (const key of [
    "languages_path",
    "models_path",
    "voices_path",
    "gender_path",
    "description_path",
    "capabilities_path"
  ] as const) {
    if (endpoint[key].trim()) result[key] = endpoint[key].trim();
  }
  return result;
}

/** Convert form state to the backend's canonical manifest and harmless aliases. */
export function httpConnectorToOptions(form: HttpConnectorFormState): Record<string, unknown> {
  const defaults = defaultHttpConnector();
  const hasAuthOverride =
    Boolean(form.authTestPath.trim()) ||
    form.authType !== defaults.authType ||
    (form.authType === "bearer" &&
      (form.authHeader.trim() !== defaults.authHeader || form.authPrefix !== defaults.authPrefix)) ||
    form.authTestMethod.trim().toUpperCase() !== defaults.authTestMethod;
  // An untouched Auto connector must keep the existing provider adapter in
  // control (for example openai_compatible -> GET /models). A truthy but empty
  // manifest would otherwise shadow that proven discovery path.
  if (form.mode === "auto" && !hasAuthOverride) return {};
  const includeExplicitMappings = form.mode !== "auto";
  const endpointEntries = (["models", "voices", "languages"] as const).reduce<Record<string, unknown>>(
    (entries, key) => {
      const endpoint = form.catalog[key];
      if (includeExplicitMappings && endpoint.path.trim()) entries[key] = serializeEndpoint(endpoint);
      return entries;
    },
    {}
  );
  const responseType = form.synthesisResponseType;
  const response: Record<string, unknown> = {
    type: responseType,
    audio_path: form.synthesisAudioPath.trim(),
    mime_type: form.synthesisMimeType.trim(),
    mime_type_path: form.synthesisMimeTypePath.trim(),
    duration_path: form.synthesisDurationPath.trim(),
    file_extension: form.synthesisFileExtension.trim()
  };
  const polling: Record<string, unknown> = {
    job_id_path: form.pollingJobIdPath.trim(),
    poll_path: form.pollingPath.trim(),
    method: form.pollingMethod.trim().toUpperCase() || "GET",
    content_type: form.pollingContentType.trim() || "application/json",
    body: parseBodyTemplate(sanitizeBodyTemplate(form.pollingBody)),
    status_path: form.pollingStatusPath.trim(),
    success_values: parseCommaList(form.pollingSuccessValues),
    failure_values: parseCommaList(form.pollingFailureValues),
    interval_seconds: Number(form.pollingIntervalSeconds) || 2,
    max_attempts: Number(form.pollingMaxAttempts) || 30,
    response_type: form.pollingResponseType,
    audio_path: form.pollingAudioPath.trim(),
    mime_type_path: form.pollingMimeTypePath.trim(),
    duration_path: form.pollingDurationPath.trim()
  };
  const openapiUrl = form.mode === "openapi" ? form.openapiUrl.trim() : "";
  const connector: Record<string, unknown> = {
    version: 1,
    mode: form.mode,
    auth: {
      type: form.authType,
      header_name: form.authHeader.trim(),
      prefix: form.authPrefix,
      query_name: form.authQueryName.trim(),
      test_path: form.authTestPath.trim(),
      test_method: form.authTestMethod.trim().toUpperCase() || "GET"
    },
    openapi: { url: openapiUrl },
    catalog: endpointEntries,
    // Keep the early draft aliases so older API/worker builds can ignore or
    // consume the same configuration during a rolling local upgrade.
    openapi_url: openapiUrl,
    discovery: endpointEntries
  };
  if (includeExplicitMappings && form.synthesisPath.trim()) {
    const safeBodyTemplate = sanitizeBodyTemplate(form.synthesisBody);
    const synthesis: Record<string, unknown> = {
      path: form.synthesisPath.trim(),
      method: form.synthesisMethod.trim().toUpperCase() || "POST",
      content_type: form.synthesisContentType.trim() || "application/json",
      body: parseBodyTemplate(safeBodyTemplate),
      request_template: safeBodyTemplate,
      response,
      // Early draft aliases.
      response_type: responseType === "binary" ? "audio_binary" : responseType,
      audio_path: form.synthesisAudioPath.trim(),
      poll_path_template: form.pollingPath.trim(),
      job_id_path: form.pollingJobIdPath.trim(),
      status_path: form.pollingStatusPath.trim(),
      success_values: parseCommaList(form.pollingSuccessValues),
      failure_values: parseCommaList(form.pollingFailureValues)
    };
    if (responseType === "async_json") {
      synthesis.polling = polling;
      synthesis.poll_path_template = form.pollingPath.trim();
      synthesis.job_id_path = form.pollingJobIdPath.trim();
      synthesis.status_path = form.pollingStatusPath.trim();
      synthesis.success_values = parseCommaList(form.pollingSuccessValues);
      synthesis.failure_values = parseCommaList(form.pollingFailureValues);
    }
    connector.synthesis = synthesis;
  }
  return { http_connector: connector };
}

function shellTokens(input: string): string[] {
  const tokens: string[] = [];
  const pattern = /"((?:\\.|[^"\\])*)"|'([^']*)'|([^\s]+)/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(input))) {
    const raw = match[1] ?? match[2] ?? match[3] ?? "";
    tokens.push(raw.replace(/\\([\\"'])/g, "$1"));
  }
  return tokens;
}

function scrubBody(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(scrubBody);
  if (!isRecord(value)) return value;
  const result: Record<string, unknown> = {};
  for (const [key, item] of Object.entries(value)) {
    if (/authorization|api[-_]?key|access[-_]?token|secret|password/i.test(key)) continue;
    const normalized = key.toLowerCase().replace(/-/g, "_");
    if (["text", "input", "content", "script"].includes(normalized)) {
      result[key] = "{{text}}";
    } else if (["model", "model_id", "modelid"].includes(normalized)) {
      result[key] = "{{model_id}}";
    } else if (["voice", "voice_id", "voiceid", "speaker", "speaker_id"].includes(normalized)) {
      result[key] = "{{voice_id}}";
    } else if (["language", "language_code", "lang", "locale"].includes(normalized)) {
      result[key] = "{{language_code}}";
    } else if (["speed", "rate", "speaking_rate"].includes(normalized)) {
      result[key] = "{{speaking_rate}}";
    } else {
      result[key] = scrubBody(item);
    }
  }
  return result;
}

/** Parse a common cURL command without executing it or retaining credentials. */
export function parseTtsCurl(input: string): CurlConnectorImport | null {
  const tokens = shellTokens(input.trim());
  if (!tokens.length || !["curl", "curl.exe"].includes(tokens[0].toLowerCase())) return null;
  let urlText = "";
  let method = "GET";
  let contentType = "application/json";
  let bodyText = "";
  let authType: HttpConnectorAuthType = "none";
  let authHeader = "Authorization";
  let authPrefix = "";
  let authQueryName = "";
  let keyDetected = false;
  for (let index = 1; index < tokens.length; index += 1) {
    const token = tokens[index];
    if (!urlText && /^https?:\/\//i.test(token)) {
      urlText = token;
      continue;
    }
    if ((token === "--url" || token === "-url") && tokens[index + 1]) {
      urlText = tokens[++index];
      continue;
    }
    if ((token === "-X" || token === "--request") && tokens[index + 1]) {
      method = tokens[++index].toUpperCase();
      continue;
    }
    if ((token === "-H" || token === "--header") && tokens[index + 1]) {
      const header = tokens[++index];
      const separator = header.indexOf(":");
      if (separator < 0) continue;
      const name = header.slice(0, separator).trim();
      const value = header.slice(separator + 1).trim();
      if (name.toLowerCase() === "content-type") contentType = value || contentType;
      if (/authorization|api[-_]?key|token/i.test(name)) {
        keyDetected = true;
        if (name.toLowerCase() === "authorization" && /^bearer\s+/i.test(value)) {
          authType = "bearer";
          authHeader = "Authorization";
          authPrefix = "Bearer ";
        } else {
          authType = "header";
          authHeader = name;
          const prefixMatch = value.match(/^([^\s]{1,32})\s+/);
          authPrefix = prefixMatch ? prefixMatch[1] + " " : "";
        }
      }
      continue;
    }
    if (["-d", "--data", "--data-raw", "--data-binary"].includes(token) && tokens[index + 1]) {
      method = method === "GET" ? "POST" : method;
      bodyText = tokens[++index];
    }
  }
  if (!urlText) return null;
  if (!["POST", "PUT"].includes(method)) return null;
  let parsed: URL;
  try {
    parsed = new URL(urlText);
  } catch {
    return null;
  }
  if (parsed.username || parsed.password) return null;
  const safeQuery = new URLSearchParams();
  for (const [key, value] of parsed.searchParams.entries()) {
    if (
      /authorization|api[-_]?key|access[-_]?token|token|secret|password/i.test(key) ||
      /^(?:bearer\s+\S+|sk[-_][A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.)/i.test(value)
    ) {
      keyDetected = true;
      if (authType === "none") {
        authType = "query";
        authQueryName = key;
      }
      continue;
    }
    safeQuery.append(key, value);
  }
  const pathname = parsed.pathname || "/";
  const versionIndex = pathname.indexOf("/v1/");
  const basePath = versionIndex >= 0 ? pathname.slice(0, versionIndex + 3) : pathname.slice(0, pathname.lastIndexOf("/"));
  const rawSynthesisPath = versionIndex >= 0
    ? pathname.slice(versionIndex + 3) || "/"
    : pathname.slice(basePath.length) || "/";
  const synthesisPath = `${rawSynthesisPath.startsWith("/") ? rawSynthesisPath : `/${rawSynthesisPath}`}${safeQuery.toString() ? `?${safeQuery.toString()}` : ""}`;
  const baseUrl = `${parsed.origin}${basePath || ""}`.replace(/\/$/, "") || parsed.origin;
  let body = bodyText;
  if (bodyText) {
    try {
      const parsedBody: unknown = JSON.parse(bodyText);
      body = JSON.stringify(scrubBody(parsedBody), null, 2);
    } catch {
      body = bodyText.replace(/(authorization|api[-_]?key|token|secret|password)\s*[:=]\s*[^,\s}]+/gi, "$1: \"\"");
    }
  }
  return {
    baseUrl,
    method,
    synthesisPath,
    contentType,
    body,
    authType,
    authHeader,
    authPrefix,
    authQueryName,
    keyDetected,
    warning: keyDetected ? "Credentials were detected but intentionally not imported. Enter the API key separately." : undefined
  };
}
