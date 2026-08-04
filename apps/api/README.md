# apps/api

FastAPI service for the HTTP boundary of `reup-douyin`.

## Responsibility

- Own API contracts consumed by `apps/web`.
- Coordinate validation, persistence, auth when introduced, and future job submission.
- Expose job state and workflow state without leaking internal infrastructure details.

## Boundaries

- Do not run long-running crawl, video processing, rendering, or publishing jobs inline in request handlers.
- Do not place frontend UI logic here.
- Do not hardcode local-only assumptions that would block future SaaS deployment.

## Database Foundation

The API now owns the first PostgreSQL data model foundation:

- SQLAlchemy 2.0 declarative models in `src/models`.
- Central enums in `src/enums`.
- Database base/session/bootstrap helpers in `src/db`.
- Alembic migration setup in `alembic`.
- Initial schema migration: `alembic/versions/0001_initial_domain_schema.py`.

The models cover workspace foundation, source ingestion, candidate review, media assets, render outputs, durable jobs, editable AI artifacts, OCR detections, publish drafts, and risk warning/decision records.

## Job API Foundation

The API exposes the first job orchestration endpoints:

- `POST /jobs`
- `GET /jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/retry`
- `POST /jobs/{job_id}/cancel`
- `POST /jobs/{job_id}/resume`

The service layer owns state transitions, progress calculation, retry/cancel/resume behavior, and step template generation. Business handlers are placeholders only.

## Source Ingest Foundation

The API also exposes the first source metadata ingest endpoints:

- `POST /source-profiles/ingest`
- `GET /crawl-sessions`
- `GET /crawl-sessions/{crawl_session_id}`
- `GET /source-profiles`
- `GET /source-profiles/{profile_id}/videos`

The ingest layer uses source adapters. The current adapter is `DouyinProfileAdapter`, which validates/normalizes Douyin profile URLs and maps injected/mock payloads into canonical profile, video, and metric snapshot records. A real Douyin network fetch client is intentionally not bundled yet.

## Candidate Filter And Score Foundation

The API exposes candidate filtering and Reup Score endpoints:

- `POST /candidates/filter/preview`
- `POST /candidates/filter/apply`
- `GET /candidates`
- `GET /candidates/{candidate_id}`
- `GET /filter-presets`

Filtering and scoring are separate service-layer concerns. `REUP_SCORE_V1` is deterministic and stores an explainable breakdown when candidates are applied.

## Media Download And Storage Foundation

The API exposes the first media asset endpoints:

- `POST /downloads`
- `GET /source-videos/{source_video_id}/assets`
- `GET /source-videos/{source_video_id}/asset-manifest`
- `POST /source-videos/{source_video_id}/assets/refresh`

Download orchestration creates `DOWNLOAD_VIDEO` jobs, stores files through the storage abstraction, registers `MediaAsset` records, and returns an assembled asset manifest. Phase 1 uses local disk via `LOCAL_STORAGE_ROOT`; service code should not hardcode filesystem paths.

## Audio Analysis Foundation

The API exposes audio-analysis endpoints for downloaded videos:

- `POST /audio-analysis`
- `GET /source-videos/{source_video_id}/transcript`
- `GET /source-videos/{source_video_id}/translation-draft`
- `GET /source-videos/{source_video_id}/audio-analysis-summary`

The pipeline resolves media assets through the storage layer, builds current `TranscriptSegment` and `TranslationSegment` rows, and writes JSON artifacts back as `MediaAsset` records. Default providers are placeholders/fallbacks so real separation, STT, and translation providers can be swapped in later.

## TTS Subtitle And Render-Prep Foundation

The API exposes render-prep endpoints:

- `POST /tts`
- `GET /source-videos/{source_video_id}/subtitle`
- `GET /source-videos/{source_video_id}/tts-summary`
- `GET /source-videos/{source_video_id}/render-prep-manifest`

The pipeline reads current edited translation rows, creates placeholder Vietnamese TTS assets, builds subtitle rows/files, and writes a render-prep manifest. A real Vietnamese TTS provider can replace the placeholder provider later.

Ops OmniVoice engine installs use reviewed backend recipes only. Set `AUDIO_TTS_ALLOW_INSTALL=false` to disable all one-click TTS installs and use `AUDIO_TTS_ENGINE_ROOT` (default `./data/tts-engines`) for managed source checkouts, isolated environments, weights, and resumable install state. Installing an engine is separate from implementing its synthesis adapter; only adapter-ready engines are exposed to Preview and durable jobs.

## Render Engine Foundation

The API exposes render endpoints:

- `POST /renders`
- `GET /source-videos/{source_video_id}/renders`
- `GET /renders/{render_id}`
- `GET /source-videos/{source_video_id}/latest-render`

The render service consumes the current render-prep manifest, resolves source video, narration, and subtitle assets, runs an export runner, validates the output, then persists `RenderOutput`, `FINAL_RENDER_VIDEO`, `RENDER_LOG`, and `RENDER_MANIFEST`.

## Publish And Operations Foundation

The API also exposes publish preparation, risk, Facebook Page/Reels publishing, reconciliation, analytics-lite, publication metric snapshots/growth summaries, routing/control-plane, and optimization endpoints. These remain local-first and operator-assist oriented:

- publish draft metadata and scheduling skeleton
- risk scan/gating helpers
- Facebook Page/Reels `PlatformAccount` and `PublishAttempt` flow
- publish reconciliation and canonical publication summary
- publish health and operator feedback summaries
- idempotent `COLLECT_PUBLICATION_METRICS` jobs and publication growth snapshots
- adaptive publication metric schedules with pause/resume and due dispatch
- fail-closed `FACEBOOK_GRAPH` Reels insights adapter with worker-only token resolution
- read-only Facebook controlled-live preflight with exact identity/scope attestation
- Meta OAuth Page discovery with operator/workspace-bound state and encrypted Page-token storage
- fail-closed Facebook Page publish capability checks, per-Page cadence budgets,
  one-active-attempt enforcement and automatic cooldown/hold reactions
- multi-account routing/control-plane APIs
- feedback-driven optimization hints

## Authority V3.6 full-duration OCR (box QA)

When `OCR_QUALITY_PROFILE=best`, hard-sub E2E Phase 2 uses `run_per_frame_position_authority` over the **full video timeline** (every frame), not Phase-1 sample fps.

Box-only QA (no blur/render):

```powershell
cd apps/api
$env:PYTHONPATH = "src;."
python -m src.media_pipeline.ocr_filtering.per_frame_position_authority `
  --video path\to\video.mp4 `
  --out tmp_ocr_v36_run\ocr-authority-v3.6.json `
  --ocr-cache tmp_ocr_v36_run\ocr-cache.json `
  --overlay-dir tmp_ocr_v36_run\overlays_full_duration `
  --overlay-all
```

Details: `docs/ocr-hardsub-pipeline.md`, `docs/hardsub-e2e-pipeline.md`.

## Running Migrations Later

After dependencies are installed and `DATABASE_URL` is configured:

```powershell
alembic -c alembic.ini upgrade head
```

Run this from `apps/api`.

## Current Status

The API foundation covers the full local Phase 1 pipeline through publish/reconciliation/analytics-lite/publication metrics/routing/optimization. Publication metric collection is a durable job with an adaptive cadence scheduler, a network-free local adapter and a fail-closed Facebook Reels insights adapter. Meta OAuth onboarding can discover Pages and store selected Page tokens in encrypted local credentials once an operator configures a Meta App. Live Meta verification, App Review, hosted vault/KMS integration and automatic scheduler activation remain deployment responsibilities. Other intentionally limited areas include Redis queue runner replacement, real Douyin crawling, production STT/TTS/OCR providers, connector platforms beyond Facebook Reels, attribution/revenue analytics, cloud object storage, multi-user auth, and legal/compliance automation.
