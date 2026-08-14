import assert from "node:assert/strict";
import {
  defaultHttpConnector,
  httpConnectorFromOptions,
  httpConnectorToOptions,
  lucylabJsonRpcPreset,
  parseTtsCurl
} from "../lib/ttsHttpConnector";

{
  assert.equal(defaultHttpConnector().catalog.languages.id_path, "code");
  const options = httpConnectorToOptions(defaultHttpConnector());
  assert.deepEqual(
    options,
    {},
    "Untouched Auto mode must not shadow the existing OpenAI-compatible catalog adapter"
  );
}

{
  const form = defaultHttpConnector();
  form.catalog.models.path = "/hidden-models";
  form.synthesisPath = "/hidden-speech";
  assert.deepEqual(
    httpConnectorToOptions(form),
    {},
    "Auto mode must not activate mappings hidden behind the Auto tab"
  );
}

{
  const form = defaultHttpConnector();
  form.authType = "none";
  form.authPrefix = "";
  const connector = httpConnectorToOptions(form).http_connector as Record<string, unknown>;
  assert.equal(connector.mode, "auto");
  assert.deepEqual(connector.catalog, {});
  assert.equal(connector.synthesis, undefined);
}

{
  const form = defaultHttpConnector();
  form.mode = "custom";
  form.synthesisPath = "/speech";
  form.synthesisBody = '{"model":"fixed-vendor-model","text":"{{text}}"}';
  const synthesis = ((httpConnectorToOptions(form).http_connector as Record<string, unknown>)
    .synthesis as Record<string, unknown>);
  assert.equal(synthesis.polling, undefined, "Direct audio responses must not emit an invalid empty polling block");
  assert.equal((synthesis.body as Record<string, unknown>).model, "fixed-vendor-model");
}

{
  const form = defaultHttpConnector();
  form.mode = "custom";
  form.authTestPath = "/me";
  form.catalog.models.path = "/models";
  form.catalog.models.items_path = "data";
  form.synthesisPath = "/audio/speech";
  form.synthesisResponseType = "async_json";
  form.synthesisAudioPath = "data.url";
  form.pollingPath = "/jobs/{{job_id}}";
  form.pollingMethod = "POST";
  form.pollingBody = '{"task_id":"{{job_id}}"}';
  form.pollingAudioPath = "data.audio_url";
  form.pollingResponseType = "json_url";
  const connector = httpConnectorToOptions(form).http_connector as Record<string, unknown>;
  const catalog = connector.catalog as Record<string, unknown>;
  const synthesis = connector.synthesis as Record<string, unknown>;
  assert.ok(catalog.models, "Configured catalog resources must be serialized");
  assert.equal(catalog.voices, undefined, "Blank catalog resources must be omitted");
  assert.equal(synthesis.path, "/audio/speech");
  assert.equal((synthesis.response as Record<string, unknown>).type, "async_json");
  assert.equal((synthesis.polling as Record<string, unknown>).poll_path, "/jobs/{{job_id}}");
  assert.equal((synthesis.polling as Record<string, unknown>).method, "POST");
  assert.deepEqual((synthesis.polling as Record<string, unknown>).body, { task_id: "{{job_id}}" });
  assert.equal((synthesis.polling as Record<string, unknown>).audio_path, "data.audio_url");
}

{
  const form = { ...defaultHttpConnector(), ...lucylabJsonRpcPreset() };
  const connector = httpConnectorToOptions(form).http_connector as Record<string, unknown>;
  const catalog = connector.catalog as Record<string, unknown>;
  const voices = catalog.voices as Record<string, unknown>;
  const synthesis = connector.synthesis as Record<string, unknown>;
  const polling = synthesis.polling as Record<string, unknown>;
  assert.equal(form.authType, "bearer");
  assert.equal(voices.method, "POST");
  assert.equal(voices.items_path, "result.items");
  assert.equal((voices.body as Record<string, unknown>).method, "getUserVoices");
  assert.equal(synthesis.path, "/json-rpc");
  assert.equal((synthesis.body as Record<string, unknown>).method, "ttsLongText");
  assert.equal(polling.method, "POST");
  assert.equal(polling.poll_path, "/json-rpc");
  assert.equal((polling.body as Record<string, unknown>).method, "getExportStatus");
  assert.equal(polling.job_id_path, "result.projectExportId");
  assert.equal(polling.status_path, "result.state");
  assert.equal(polling.audio_path, "result.url");
}

{
  const hydrated = httpConnectorFromOptions({
    http_connector: {
      version: 1,
      mode: "custom",
      auth: { type: "header", header: "x-api-key", prefix: "" },
      discovery: {
        voices: {
          path: "/speakers",
          method: "POST",
          content_type: "application/json",
          body: { method: "listSpeakers" },
          items_path: "result.items",
          id_path: "uuid",
          label_path: "title"
        }
      },
      synthesis: {
        path: "/speech",
        request_template: '{"input":"{{text}}"}',
        response_type: "audio_binary",
        polling: {
          method: "POST",
          content_type: "application/json",
          body: { id: "{{job_id}}" }
        }
      }
    }
  });
  assert.equal(hydrated.authType, "header");
  assert.equal(hydrated.authHeader, "x-api-key");
  assert.equal(hydrated.authPrefix, "", "An explicitly empty prefix must remain empty");
  assert.equal(hydrated.catalog.voices.id_path, "uuid");
  assert.equal(hydrated.catalog.voices.method, "POST");
  assert.match(hydrated.catalog.voices.body, /listSpeakers/);
  assert.equal(hydrated.synthesisResponseType, "binary");
  assert.equal(hydrated.pollingMethod, "POST");
  assert.match(hydrated.pollingBody, /\{\{job_id\}\}/);
}

{
  const rawKey = "sk_super_secret_value";
  const imported = parseTtsCurl(
    `curl -X POST 'https://api.vendor.test/v1/text-to-speech' ` +
      `-H 'Authorization: Bearer ${rawKey}' -H 'Content-Type: application/json' ` +
      `--data-raw '{"model":"vendor-v3","voice":"demo-speaker","input":"hello","language":"vi","speed":1.1,"format":"mp3","api_key":"body-secret"}'`
  );
  assert.ok(imported);
  assert.equal(imported.baseUrl, "https://api.vendor.test/v1");
  assert.equal(imported.synthesisPath, "/text-to-speech");
  assert.equal(imported.authType, "bearer");
  assert.equal(imported.authPrefix, "Bearer ");
  assert.equal(imported.keyDetected, true);
  assert.doesNotMatch(JSON.stringify(imported), new RegExp(rawKey));
  assert.doesNotMatch(imported.body, /body-secret/);
  assert.match(imported.body, /\{\{text\}\}/);
  assert.match(imported.body, /\{\{model_id\}\}/);
  assert.match(imported.body, /\{\{voice_id\}\}/);
  assert.match(imported.body, /\{\{language_code\}\}/);
  assert.match(imported.body, /\{\{speaking_rate\}\}/);
  assert.match(imported.body, /"format": "mp3"/, "Fixed provider fields should be preserved");
}

{
  const imported = parseTtsCurl(
    "curl -X POST 'https://api.vendor.test/v1/speech?version=3&api_key=sk_query_secret_value&voice_id=long-fixed-voice-id-123456789'"
  );
  assert.ok(imported);
  assert.equal(imported.authType, "query");
  assert.equal(imported.authQueryName, "api_key");
  assert.match(imported.synthesisPath, /version=3/);
  assert.match(imported.synthesisPath, /voice_id=long-fixed-voice-id-123456789/);
  assert.doesNotMatch(imported.synthesisPath, /sk_query_secret_value/);
}

assert.equal(parseTtsCurl("not a curl command"), null);

console.log("tts http connector tests passed");
