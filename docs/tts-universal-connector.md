# Universal HTTP TTS Connector V1

This document defines the provider-neutral contract used by `/ops/tts-ai` for HTTP TTS services. The goal is to make a documented vendor API configurable without adding a Python class for every vendor, while keeping credentials, outbound requests, and generated audio inside the API/worker boundary.

The connector is not protocol inference. A Base URL and API key alone cannot reveal arbitrary endpoint names, authentication schemes, request bodies, response shapes, or asynchronous job behavior. V1 therefore combines reviewed presets and conventional auto-discovery with an explicit, versioned mapping for proprietary APIs.

## Scope and status

The existing remote foundation already provides provider-aware catalog discovery for OpenAI, OpenAI-compatible APIs, ElevenLabs, Google Cloud TTS, Azure Speech, and common HTTP shapes. It uses a bounded, server-side transport and preserves a safe catalog snapshot in the TTS profile runtime.

`options_json.http_connector` is the portable V1 configuration boundary for `http_custom` and compatible remote profiles. A connector can describe:

- an optional, non-mutating authentication check;
- Model, Voice, and Language catalog endpoints and JSON mappings;
- one synthesis request mapping;
- direct audio, base64, URL, or asynchronous-job response handling where supported by the runtime.

Support is stage-specific. A successful authentication or catalog check does not imply synthesis readiness. The UI and API must report the stages independently and must not activate a profile for durable jobs until synthesis has passed a real Preview check.

### Implementation boundary

| Capability | V1 state |
| --- | --- |
| Built-in OpenAI/compatible, ElevenLabs, Google, Azure, and common catalog probes | Implemented. |
| V1 manifest validation, separate auth check, explicit catalog mapping, and sanitized stage checks | Implemented for remote HTTP profiles. |
| `auto` conventional catalog paths and `openapi` path inference | Implemented as assisted discovery; OpenAPI inference reads documented `GET` paths only and is not a full SDK generator. |
| cURL-assisted form setup | Implemented in the browser as a non-executing parser that discards detected credentials. |
| JSON/form synthesis with binary, base64, public-HTTPS URL, and bounded asynchronous polling responses | Implemented by the generic HTTP provider when a valid `synthesis` mapping is present. |
| Encrypted secret storage and DNS-to-socket pinning against rebinding | Google Service Account JSON is encrypted with the platform credential envelope. Generic provider API keys still require the deferred dedicated secret-store hardening; the local V1 must not be described as a hardened multi-user/SaaS secret boundary. |

## Ownership and persistence

- The web app edits a typed form and sends the connector manifest to the API. It never calls a vendor endpoint directly.
- The API validates the manifest, resolves the saved or draft credential, performs short connection/catalog checks, and returns UI-safe metadata.
- The worker performs long synthesis through the provider boundary. It must not execute arbitrary shell commands or browser-supplied code.
- The non-secret manifest is stored at `tts_ai.profiles[].options_json.http_connector` in workspace settings.
- The API key remains the profile's separate `api_key` value. It must never be copied into `http_connector`, `request_template`, catalog snapshots, logs, warnings, or API responses.
- `runtime.last_probe` may retain the last sanitized catalog and status so an edit form can reopen quickly. That snapshot is evidence of an earlier probe, not live provider authority.
- Discovery returns sanitized `checks` (`passed`, `partial`, `failed`, or `skipped`) and a `config_fingerprint`. The fingerprint covers provider, Base URL, normalized public manifest, and a non-secret credential hint; it never contains the raw key.

The current local-first settings store masks generic provider keys in public TTS responses but stores those server-side profile values in `workspaces.settings_json`. Google Service Account JSON is the exception: it is validated and encrypted before persistence, and only safe metadata is public. Encryption-at-rest or a dedicated secret store remains required for generic provider keys before treating this as a hardened multi-user SaaS secret boundary.

## Three independent checks

The operator flow is deliberately split into three stages.

1. **Authentication** sends the configured authentication header to a safe, documented test endpoint. A `2xx` response proves only that this endpoint accepted the credential.
2. **Catalog** loads each configured Model, Voice, and Language resource. Missing catalog endpoints are allowed; the operator can enter the IDs manually.
3. **Synthesis** sends a short Preview phrase and verifies that usable audio is returned. This is the readiness authority for Preview and, after the same adapter is wired into the worker, durable TTS jobs.

The stages should use distinct statuses such as `not_configured`, `checking`, `ready`, `partial`, and `failed`. Do not collapse “catalog unavailable” into “authentication failed”: a proprietary provider can accept the key and have no list endpoint at all.

## V1 manifest contract

The manifest lives under `options_json` so unrelated provider options remain available:

```json
{
  "http_connector": {
    "version": 1,
    "mode": "custom",
    "openapi": {"url": ""},
    "auth": {
      "type": "bearer",
      "header_name": "Authorization",
      "prefix": "Bearer ",
      "query_name": "",
      "test_path": "/account",
      "test_method": "GET"
    },
    "catalog": {
      "models": {
        "path": "/models",
        "method": "GET",
        "content_type": "application/json",
        "body": {},
        "items_path": "data",
        "id_path": "id",
        "label_path": "name"
      },
      "voices": {
        "path": "/voices",
        "method": "GET",
        "items_path": "voices",
        "id_path": "voice_id",
        "label_path": "name"
      },
      "languages": {
        "path": "/languages",
        "method": "GET",
        "items_path": "languages",
        "id_path": "code",
        "label_path": "name"
      }
    },
    "synthesis": {
      "path": "/text-to-speech",
      "method": "POST",
      "content_type": "application/json",
      "body": {
        "text": "{{text}}",
        "model": "{{model_id}}",
        "voice": "{{voice_id}}",
        "language": "{{language_code}}",
        "speed": "{{speaking_rate}}"
      },
      "request_template": "{\n  \"text\": \"{{text}}\",\n  \"model\": \"{{model_id}}\"\n}",
      "response": {
        "type": "binary",
        "audio_path": "",
        "mime_type": "audio/mpeg",
        "mime_type_path": "",
        "duration_path": "",
        "file_extension": "mp3"
      },
      "polling": {
        "job_id_path": "",
        "poll_path": "",
        "method": "GET",
        "content_type": "application/json",
        "body": {},
        "status_path": "",
        "success_values": [],
        "failure_values": [],
        "interval_seconds": 2,
        "max_attempts": 30
      }
    }
  }
}
```

### Top-level fields

| Field | Required | Meaning |
| --- | --- | --- |
| `version` | Yes | Contract version. V1 accepts only `1`; unknown versions fail closed. |
| `mode` | Yes | `auto`, `custom`, or `openapi`. `auto` tries known/common HTTP shapes; `custom` uses explicit mappings; `openapi` uses a bounded same-origin specification when runtime support is available. |
| `openapi.url` | For `openapi` | Public HTTPS URL for the provider specification. It must be same-origin with Base URL. It is never a general-purpose URL fetcher. `openapi_url` is accepted only as a rolling-upgrade alias. |
| `auth` | No | Authentication header and optional test endpoint. Omit only for an unauthenticated service. |
| `catalog` | No | Zero to three resource mappings. Omitted resources remain manual. `discovery` is accepted only as a rolling-upgrade alias. |
| `synthesis` | For generated audio | Request and response mapping used by Preview and the remote provider adapter. |

### Authentication mapping

| Field | Meaning |
| --- | --- |
| `type` | `bearer`, `header`, `query`, or `none`. Query authentication is a compatibility escape hatch and is discouraged because URLs can be logged. |
| `header_name` | HTTP header name. `Authorization` is the normal value for `bearer`; proprietary APIs may use a documented key header. |
| `prefix` | Text placed before the raw profile key, commonly `Bearer `. It is configuration, not part of the key input. |
| `query_name` | Used only by the deliberately opt-in `query` mode; defaults to `api_key` when omitted. |
| `test_path` | Relative, same-origin path for a documented, non-mutating endpoint. |
| `test_method` | Safe method supported by the runtime, normally `GET` or `HEAD`. |

The API-key field always contains only the raw key. For example, if `prefix` is `Bearer `, enter `sk_...`, not `Bearer sk_...`.

For `type: "query"`, `query_name` is only the parameter name (for example `api_key`). The API appends the protected key at request time; never paste the key into Base URL, `test_path`, catalog paths, OpenAPI URLs, or synthesis paths. Operator-visible endpoint metadata records the path without the query value.

V1 does not cover OAuth authorization-code flows, token refresh, request signing such as AWS SigV4, mTLS, cookies, or multiple independent secret headers. Query-string authentication is supported only for documented providers that leave no header alternative; it should be replaced by a reviewed header-based preset whenever possible.

### Catalog mapping

Each `models`, `voices`, or `languages` mapping has the following fields:

| Field | Meaning |
| --- | --- |
| `path` | Relative or absolute API path. A full URL is accepted only when it uses the exact Base URL origin. |
| `method` | `GET`, `POST`, or `PUT`. POST/PUT supports JSON-RPC catalog calls such as `getUserVoices`. |
| `content_type` / `body` | Optional static JSON/form request for POST/PUT catalogs. Runtime placeholders and secrets are rejected. |
| `items_path` | Dot path from the JSON root to the array, such as `data`, `data.models`, or `voices`. |
| `id_path` | Dot path inside one item to the stable ID. |
| `label_path` | Optional dot path inside one item to a human-readable label. The ID is the fallback label. |
| `languages_path` | Optional related-language path inside one item. |
| `models_path` | Optional related-model path inside one item. |
| `voices_path` | Optional related-voice path inside one item. |
| `gender_path` | Optional display-only gender path for a voice. |
| `description_path` | Optional display-only description path. |
| `capabilities_path` | Optional display-only capability/modality path. |

Dot paths address object keys only; they are not JSONPath expressions and cannot execute filters, scripts, parent traversal, or arbitrary code. A missing/invalid mapping makes that resource unavailable without discarding successfully mapped resources. The existing UI retains manual Model ID, Voice ID, and Language code entry for partial and no-catalog providers.

Catalog discovery is descriptive, not authoritative. Vendors can omit a valid model from a list, scope lists by account, or return eventually consistent data. The operator-entered value therefore must not be silently replaced merely because it is absent from a partial snapshot.

### Synthesis mapping

| Field | Meaning |
| --- | --- |
| `path` | Relative same-origin synthesis endpoint. |
| `method` | `POST` or `PUT`. |
| `content_type` | `application/json` or `application/x-www-form-urlencoded`. |
| `body` | JSON-compatible body containing only literals and allowlisted runtime placeholders. |
| `request_template` | The editable JSON text retained for the form. The API normalizes/validates it into `body`; malformed or unsupported content fails closed. |
| `headers` | Optional non-secret headers. Authentication, cookies, Host, Content-Length, and secret-like headers are rejected and remain owned by `auth`. |
| `response.type` | `binary`, `json_base64`, `json_url`, or `async_json`. |
| `response.audio_path` | Dot path to base64/URL audio when the response is JSON. Empty for direct audio bytes. |
| `response.mime_type` | Expected MIME type for direct or decoded audio. |
| `response.mime_type_path` | Optional dot path to a vendor-supplied MIME type. |
| `response.duration_path` | Optional dot path to duration metadata. Measured decoded audio remains authoritative. |
| `response.file_extension` | Safe output extension for the staged audio. |
| `polling.job_id_path` | Dot path to the created job ID for asynchronous responses. |
| `polling.poll_path` | Relative path containing the allowlisted job-ID placeholder. |
| `polling.method` | `GET`, `POST`, or `PUT`. `POST` supports JSON-RPC/status APIs that reuse one endpoint. |
| `polling.content_type` / `body` | Optional polling request encoding and template. `{{job_id}}` is rendered as the raw job ID in the body while path interpolation remains URL-encoded. |
| `polling.status_path` | Dot path to the job status in a poll response. |
| `polling.success_values` | Exact terminal-success status values. |
| `polling.failure_values` | Exact terminal-failure status values. |
| `polling.interval_seconds` / `max_attempts` | Bounded polling cadence and attempt count. |
| `polling.response_type` / `audio_path` | Optional final-response mapping after an async job succeeds. |

The allowed request placeholders are `{{text}}`, `{{model_id}}`, `{{voice_id}}`, `{{language_code}}`, `{{speaking_rate}}`, and `{{target_duration_seconds}}`. `{{job_id}}` is additionally allowed in the polling path and polling body. An unknown placeholder or a secret-looking literal fails validation instead of being forwarded.

Asynchronous polling must have a bounded total deadline, attempt count, and response size. An unknown status is non-terminal only until that bound expires. A failure status must surface a sanitized provider error without returning the raw payload.

## Example: OpenAI-compatible API

For an API whose Base URL already ends in `/v1`, all connector paths are relative to that Base URL:

```json
{
  "http_connector": {
    "version": 1,
    "mode": "custom",
    "auth": {
      "type": "bearer",
      "header_name": "Authorization",
      "prefix": "Bearer ",
      "test_path": "/models",
      "test_method": "GET"
    },
    "catalog": {
      "models": {
        "path": "/models",
        "method": "GET",
        "items_path": "data",
        "id_path": "id",
        "label_path": "id"
      }
    },
    "synthesis": {
      "path": "/audio/speech",
      "method": "POST",
      "body": {
        "model": "{{model_id}}",
        "voice": "{{voice_id}}",
        "input": "{{text}}",
        "speed": "{{speaking_rate}}",
        "response_format": "mp3"
      },
      "response": {
        "type": "binary",
        "mime_type": "audio/mpeg",
        "file_extension": "mp3"
      },
      "polling": {}
    }
  }
}
```

If the service has no `/voices` or `/languages` endpoint, leave those mappings absent and enter Voice ID and Language code manually. Do not invent endpoints merely to make the catalog status “complete.”

## Example: GenMax asynchronous TTS

GenMax is a custom asynchronous HTTP provider, not an OpenAI-compatible TTS API. Its speech and catalog endpoints authenticate with the `xi-api-key` header. The separate `GET /v1/api-keys` account endpoint uses `Authorization: Bearer <user-token>` to retrieve an API key and must not be used as the connector authentication probe.

The following profile targets the GenMax ElevenLabs provider and filters the shared voice catalog for Vietnamese-compatible voices:

```json
{
  "http_connector": {
    "version": 1,
    "mode": "custom",
    "auth": {
      "type": "header",
      "header_name": "xi-api-key",
      "prefix": "",
      "test_path": "/models",
      "test_method": "GET"
    },
    "catalog": {
      "models": {
        "path": "/models",
        "method": "GET",
        "items_path": "",
        "id_path": "model_id",
        "label_path": "name",
        "description_path": "description"
      },
      "voices": {
        "path": "/shared-voices?page_size=100&required_languages=vi&sort=trending",
        "method": "GET",
        "items_path": "voices",
        "id_path": "voice_id",
        "label_path": "name",
        "gender_path": "gender",
        "description_path": "description"
      }
    },
    "synthesis": {
      "path": "/text-to-speech/{{voice_id}}",
      "method": "POST",
      "content_type": "application/json",
      "body": {
        "text": "{{text}}",
        "model_id": "{{model_id}}",
        "provider": "elevenlabs",
        "language_code": "{{language_code}}",
        "voice_settings": {
          "stability": 0.5,
          "similarity_boost": 0.75,
          "speed": "{{speaking_rate}}"
        }
      },
      "response": {
        "type": "async_json",
        "mime_type": "audio/mpeg",
        "file_extension": "mp3"
      },
      "polling": {
        "job_id_path": "id",
        "poll_path": "/history/{{job_id}}",
        "status_path": "status",
        "success_values": ["completed"],
        "failure_values": ["failed"],
        "interval_seconds": 2,
        "max_attempts": 60,
        "response_type": "json_url",
        "audio_path": "result.audio_url"
      }
    }
  }
}
```

Enter the GenMax API key as a raw value without `Bearer`. The model catalog is a root array, so `items_path` stays empty. GenMax does not provide one universal language shape across its upstream providers; for this ElevenLabs profile, enter `vi` manually as the Language code. The synthesis request returns HTTP `202` with `id` and `status`; the connector must poll `/history/{{job_id}}` until `completed`, then read the public HTTPS MP3 URL from `result.audio_url`.

Create separate profiles for MiniMax and CapCut because their model, voice, language, and `voice_settings` contracts differ. For MiniMax, use `/models?provider=minimax`, `/minimax/system-voices`, `items_path: voice_list`, `id_path: voice_id`, `label_path: voice_name`, and set `provider: minimax` in the synthesis body. Always verify the language value supported by the selected GenMax model rather than reusing `vi` blindly.

## Example: two-step JSON-RPC provider

Lucylab-style APIs create and poll jobs with two different JSON bodies sent to the same endpoint. Use the **Lucylab JSON-RPC** preset in Ops, then enter a fresh raw API key and the provider Voice ID. The equivalent polling mapping is:

```json
{
  "http_connector": {
    "version": 1,
    "mode": "custom",
    "catalog": {
      "voices": {
        "path": "/json-rpc",
        "method": "POST",
        "content_type": "application/json",
        "body": {
          "method": "getUserVoices",
          "input": { "limit": 10, "page": 1 }
        },
        "items_path": "result.items",
        "id_path": "id",
        "label_path": "name"
      }
    },
    "synthesis": {
      "path": "/json-rpc",
      "method": "POST",
      "body": {
        "method": "ttsLongText",
        "input": {
          "text": "{{text}}",
          "userVoiceId": "{{voice_id}}",
          "speed": "{{speaking_rate}}"
        }
      },
      "response": {
        "type": "async_json",
        "mime_type": "audio/mpeg",
        "file_extension": "mp3"
      },
      "polling": {
        "method": "POST",
        "content_type": "application/json",
        "body": {
          "method": "getExportStatus",
          "input": { "projectExportId": "{{job_id}}" }
        },
        "job_id_path": "result.projectExportId",
        "poll_path": "/json-rpc",
        "status_path": "result.state",
        "response_type": "json_url",
        "audio_path": "result.url"
      }
    }
  }
}
```

Lucylab exposes user voices through `getUserVoices`, but its `ttsLongText` contract does not accept a Model ID. The UI therefore loads Voice ID choices and explicitly hides Model ID for this preset. Provider response envelopes can change; never paste an API key into a path or template.

## OpenAPI mode

An OpenAPI document can reduce manual mapping only when it explicitly describes the necessary operations and schemas. Import must remain an assisted setup step:

- fetch only a bounded same-origin public HTTPS document;
- reject external `$ref` URLs and recursive/unbounded references;
- never import example API keys, `Authorization` values, cookies, or vendor secrets;
- show the inferred operations and mappings for operator review before Save;
- never run arbitrary callbacks, webhooks, code samples, or server URLs found in the document.

OpenAPI cannot reliably decide which of several speech operations, models, or voice fields the operator intends. When inference is ambiguous, preserve the draft and require explicit selection rather than choosing silently.

## cURL-assisted setup

The UI may parse a copied cURL command to prefill Base URL, method, synthesis path, content type, and a redacted body. Parsing is local and never executes the command. Detected credentials are intentionally discarded; the operator must enter the raw API key in the protected key field. Review every inferred path, body field, and auth mode before saving. A cURL command is input to the form, not permission to execute arbitrary flags, files, pipes, or shell substitutions.

## Security requirements

Every connector-controlled network call must reuse the hardened server-side transport or an equivalent policy:

- validate a public `http`/`https` Base URL and require HTTPS whenever credentials or synthesis text are sent;
- reject user-info, fragments, path traversal, localhost, `.local`, and non-global IPv4/IPv6 targets;
- revalidate every redirect and every resolved connection target; never forward credentials across origins;
- restrict connector control endpoints to relative paths or full URLs on the exact Base URL origin;
- validate header names and reject CR/LF in keys, prefixes, templates, paths, and header values;
- cap connection time, total deadline, redirects, poll attempts, JSON/audio bytes, nesting depth, and catalog items;
- accept only expected audio content types or explicitly mapped, bounded JSON;
- for JSON audio URLs, allow only a separately validated public HTTPS URL, apply a same-origin redirect rule for that media origin, and never forward the provider credential to it;
- redact the profile key and derived authorization value from errors, logs, catalog fields, runtime snapshots, and provider payloads; query authentication should be treated as sensitive URL data and never appear in logs;
- never surface raw vendor error bodies because vendors sometimes echo credentials or submitted text;
- treat the manifest as data only: no shell, Python, JavaScript, template expressions, environment lookup, or arbitrary header/body interpolation.

The current discovery transport caps a probe at 10 seconds, a response at 2 MiB, and each catalog at 500 options. Synthesis caps its total request deadline at 180 seconds and audio at 32 MiB. Polling is clamped to at most 60 attempts with an interval of at most 5 seconds; it still shares the synthesis transport deadline.

## Validation and readiness rules

A profile is safe to Save as a draft even when one stage is incomplete. Activation and durable synthesis should fail closed unless all required runtime evidence is current:

- Base URL and connector manifest passed schema/security validation;
- required credential is set;
- selected IDs are non-empty when the vendor requires them;
- a Preview produced decodable audio through the same synthesis mapping;
- the adapter used by the worker supports the mapped response mode;
- the evidence belongs to the current Base URL, connector version/content, and credential generation.

Changing Base URL, authentication configuration, connector mappings, or the API key invalidates prior probe/Preview evidence. A catalog may remain visible as “stale” context, but it must not be presented as newly verified.

## Known V1 limits

- There is no universal TTS catalog standard; manual IDs remain a first-class outcome.
- Base URL plus an API key is insufficient for arbitrary provider setup.
- OAuth, HMAC signing, mTLS, cookies, multipart uploads, streaming WebSockets, and vendor-specific voice cloning are outside V1. Query authentication is supported as a discouraged compatibility mode only when the vendor offers no header alternative.
- Authentication, OpenAPI, catalog, synthesis, and polling endpoints stay on the Base URL origin. A `json_url` response may point to a separately validated public HTTPS audio URL; the connector sends no provider credential to that media origin and confines redirects to it.
- Request-template mapping covers JSON HTTP APIs, not arbitrary code or SDK-only providers.
- Imported/inferred mappings require operator review and a Preview; they are never proof of vendor compatibility by themselves.
- A valid connector is not an installation mechanism for local SDK/GitHub engines. Local engines keep their reviewed registry and isolated install flow.

## Minimum test matrix

The connector must have focused tests for:

- schema versioning, unknown-field policy, size/depth limits, and allowed placeholders;
- Bearer/header/query/none authentication, query-key omission from recorded endpoint metadata, and rejection of header injection;
- separate authentication success, partial catalog, no-catalog, and authentication-failure states;
- dot-path extraction for arrays and nested objects, missing paths, duplicate IDs, option caps, and secret redaction;
- IPv4/IPv6/private DNS blocking, DNS rebinding resistance, redirects, HTTPS enforcement, and same-origin paths;
- direct binary, base64, URL, and asynchronous-job responses, including invalid MIME/base64, oversized audio, failed jobs, unknown status, timeout, and poll exhaustion;
- OpenAPI size/reference restrictions and ambiguous-operation handling before enabling `openapi` mode;
- stale evidence after Base URL, key, or manifest changes;
- Preview/worker parity, idempotent retry behavior, cancellation, sanitized logging, and the guarantee that no secret reaches public profile/catalog/runtime responses.
