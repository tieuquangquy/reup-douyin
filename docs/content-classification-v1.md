# Content Classification V1

## Purpose

Content Classification V1 gives each `PlatformPublication` an explainable, operator-reviewed topic before affiliate product matching is introduced. It remains local-first, with an operator-configured Hybrid AI path for uncertain results.

## Domain model

- `TopicCategory` is a workspace-scoped node in a versioned taxonomy. Stable `code` values are independent from editable display names and keywords.
- `ContentClassification` is one result for a publication, taxonomy version, classifier version, and evidence fingerprint.
- Only one result is marked `is_current` by the service. Historical results remain available for audit and future classifier comparisons.
- Operator decisions are explicit: `NEEDS_REVIEW`, `APPROVED`, or `OVERRIDDEN`.
- Overrides require a replacement topic and a reason. The authenticated subject and review timestamp are persisted.

The initial taxonomy version is `CONTENT_TAXONOMY_V1`. `LOCAL_KEYWORD_V1` remains the zero-network baseline; `HYBRID_CONTENT_V1` composes that baseline with an optional AI provider.

## Evidence authority

The classifier reads only evidence already persisted inside the workspace:

1. Persisted publication title and Facebook caption.
2. Linked publish-draft title and caption.
3. Source-video caption.
4. Current, non-rejected transcript segments.
5. Non-rejected OCR text objects.

Each retained evidence item records its source type, source id, bounded text, language/confidence when available, and matched taxonomy keywords. The input fingerprint excludes transient match output and confidence so retrying the same semantic input remains idempotent.

Imported Reels can be classified from their Facebook caption without linking a source video. When no evidence exists, enqueue fails before a durable job is created and tells the operator to add a caption or link source evidence.

## Durable job behavior

`CLASSIFY_CONTENT` uses four steps:

1. `validate_publication`
2. `collect_evidence`
3. `classify_and_persist`
4. `finalize`

The only persistence boundary is `classify_and_persist`. The job idempotency key includes publication id, taxonomy version, classifier version, and evidence fingerprint. Retrying the same input returns the existing job or classification instead of creating duplicate evidence.

Worker exceptions are converted to a bounded operator message. No raw provider payload or secret is exposed.

## Hybrid AI policy

Workspace-scoped configuration supports Gemini, OpenAI-compatible endpoints, and Ollama. API keys are encrypted with `PlatformSecretEnvelope`; browser responses expose only `api_key_set` and a masked suffix.

- `LOCAL_ONLY`: deterministic keyword classification; no network request.
- `HYBRID`: keep a local result at or above the configured confidence threshold, otherwise call AI.
- `AI_ONLY`: call AI for each run and fail before enqueue when explicit network authorization is absent.

Each network run must carry `external_network_authorized=true` and the exact operator confirmation `CONTENT_CLASSIFICATION_AI_APPROVED`. Provider errors can either fail closed or fall back to the local classifier. A fallback result records `fallback_from=AI` and remains `NEEDS_REVIEW`.

The configured prompt treats captions, transcripts, and OCR as untrusted evidence. The adapter accepts structured JSON only, rejects inactive or invented topic codes, rejects confidence outside `0..1`, and verifies every AI quote against persisted input evidence. AI never creates a taxonomy topic and never approves its own result.

Prompt profiles are versioned in workspace settings. Saving prompt text creates a new version identifier; activating an older profile is the rollback mechanism. Persisted classification metadata records provider, model, prompt version, whether network was used, and fallback provenance. Raw prompts, evidence payloads, credentials, and provider responses are not logged.

## Operator surfaces

`/publishing/publications` now includes the daily review surfaces:

- **Classification Queue**: workspace/Page KPIs, Page/status/search filters, a low-confidence filter, job state, and direct access to the affected publication.
- **Topic Taxonomy**: create topics, change hierarchy/name/keywords/order, and enable or disable a topic without deleting history.
- **Publication inspector → Content classification**: run/re-run, view confidence and evidence, approve the result, or override it with a required reason.

Workspace-level configuration lives separately at `/publishing/settings/content-intelligence` under the Operator Studio **Publishing Settings** navigation group. That page selects local/hybrid/AI-only policy, configures and tests the provider, and edits or activates versioned prompt profiles. Publication Library keeps a shortcut to the settings page but does not embed the credential form.

The queue uses a 60% threshold for review prioritization. This is an operational threshold, not an affiliate-fit score.

## API contracts

- `GET|POST /content-topics`
- `PATCH /content-topics/{topic_id}`
- `GET /content-classifications/review-queue`
- `GET /platform-publications/{publication_id}/content-classification`
- `POST /platform-publications/{publication_id}/content-classification-jobs`
- `POST /content-classifications/{classification_id}/decision`
- `GET|PUT /content-intelligence/ai-config`
- `POST /content-intelligence/ai-config/test`
- `GET|POST /content-intelligence/prompts`
- `PATCH /content-intelligence/prompts/{prompt_id}`
- `POST /content-intelligence/prompts/{prompt_id}/activate`

All reads and writes are scoped to the workspace from the authenticated principal.

## Non-goals

- No affiliate catalog or product matching.
- No Growth Score or Affiliate Fit Score changes.
- No automatic external-provider consent; every run is explicitly authorized by the operator action.
- No frame-level vision model inference beyond persisted OCR evidence.
- No automatic approval of high-confidence results.

The next product step is Affiliate Catalog and Product Matching, using only approved or explicitly overridden topic results for automated decisions.
