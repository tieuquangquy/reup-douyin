# Douyin Zero Videos Hard Fix Log

## Step Name

Canonical Douyin profile fetch hard fix for zero-video misclassification

## Time Started

2026-04-23

## Findings

- Reproduced the failing intake run with crawl session `eaa6afc7-b28c-4b76-89f3-97cf9c6d937b`.
- The selected and resolved Douyin account were the same connected account. Account selection was not the failing stage.
- The crawl run completed with:
  - `videos_discovered_count = 0`
  - `candidates_matched_count = 0`
  - no `error_code`
- Canonical fetch observability incorrectly marked:
  - `response_classification = ok`
  - `normalize_payload = ok`
  - `persist_entities = ok`
- The persisted raw payload for the failing run contained:
  - `profile.sec_uid`
  - `videos = []`
  - metadata `source = douyin_live_html`
  - metadata `embedded_document_count = 0`
- Direct HTTP fetch with the connected account returned an HTML shell with no embedded Douyin profile/video data.
- A controlled Playwright probe with the same connected account/session reached a rendered page titled `验证码中间页`, which means the real response path is challenge/blocked, not a true zero-video profile.

## Exact Previous Failing Stage

`response_classification`

More precisely:

1. `DouyinLiveFetchClient.fetch_html()` returned a shell/challenge bootstrap page.
2. `extract_profile_payload_from_html()` produced `profile` plus zero videos and zero embedded documents.
3. `DouyinProfileAdapter.normalize_fetch_payload()` treated that as a successful zero-video payload.
4. `SourceIngestService.ingest_profile()` persisted it as a completed crawl with `ok` stage events.
5. `/intake` then surfaced the run as a no-candidate result.

## Files Inspected

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/intake_run_history_service.py`
- `apps/api/src/api/routes/intake.py`
- `apps/api/src/schemas/intake.py`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/types/intake.ts`
- `docs/douyin-live-fetch-architecture.md`
- `docs/douyin-fetch-observability-architecture.md`
- `docs/intake-500-root-cause-architecture.md`

## Chosen Fix Strategy

- Keep one canonical account-backed intake pipeline.
- Stop treating zero-video shell responses as successful fetches.
- Add explicit response classification for:
  - blocked/challenge response
  - parse-zero-videos shell response
  - true zero videos
  - filter-zero-candidates
- Preserve the same `DouyinAccountConnection -> DouyinProfileAdapter -> SourceIngestService -> CandidateEvaluationService` flow.
- Use a lightweight browser probe only as a diagnostic fallback when HTTP HTML returns a shell with no embedded payload, so the system can classify the failure correctly instead of calling it zero videos.

## Verification Notes

- Reproduced latest failing run through `/intake/runs` and `/intake/runs/{id}`.
- Queried the crawl session and confirmed the persisted raw payload and observability state.
- Ran a direct HTTP fetch and a Playwright probe with the connected account to confirm the mismatch between zero-video classification and the actual challenge page.
- Verified focused backend tests:
  - `python -m unittest tests.test_douyin_live_fetch tests.test_intake_discovery_service`
- Verified API compile sanity:
  - `python -m compileall src`
- Verified web type contracts:
  - `npm --workspace @reup-douyin/web run typecheck`
- Verified live API behavior:
  - `/intake/discover` now returns `502` with `code=parse_zero_videos` instead of completing as a zero-video/no-candidate run.
  - latest failed crawl sessions now persist `fetch_observability.stages.response_classification`.

## Files Touched

- `apps/api/src/adapters/douyin_live_fetch.py`
- `apps/api/src/adapters/douyin.py`
- `apps/api/src/services/source_ingest_service.py`
- `apps/api/src/services/intake_discovery_service.py`
- `apps/api/src/services/intake_run_history_service.py`
- `apps/api/src/schemas/intake.py`
- `apps/api/tests/test_douyin_live_fetch.py`
- `apps/api/tests/test_intake_discovery_service.py`
- `apps/web/src/components/intake/IntakePage.tsx`
- `apps/web/src/types/intake.ts`
- `apps/web/src/lib/i18n/en.json`
- `apps/web/src/lib/i18n/vi.json`
- `docs/douyin-zero-videos-hard-fix-log.md`
- `docs/douyin-zero-videos-hard-fix-resume.md`
- `docs/douyin-zero-videos-hard-fix-architecture.md`
- `docs/douyin-zero-videos-hard-fix-troubleshooting.md`

## Status

completed
