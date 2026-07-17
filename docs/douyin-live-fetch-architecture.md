# Douyin Live Fetch Architecture

## Current Intake Flow

```text
/intake
  -> POST /intake/discover
  -> IntakeDiscoveryService.discover()
  -> find existing SourceProfile by normalized Douyin identity
  -> if missing: SourceIngestService.ingest_profile()
  -> CandidateEvaluationService.apply()
  -> VideoCandidate rows
  -> /review-board reads candidates
```

Before this step, `SourceIngestService` constructed `DouyinProfileAdapter()` without a fetch client, so new live profiles failed unless an existing profile or dev fixture payload already existed.

## Target Live-Fetch Flow

```text
/intake
  -> POST /intake/discover
  -> IntakeDiscoveryService.discover()
  -> SourceIngestService.ingest_profile()
  -> configured DouyinProfileAdapter(fetch_client=DouyinLiveFetchClient)
  -> fetch profile page / embedded payload
  -> normalize into SourceFetchResult
  -> upsert SourceProfile + SourceVideo
  -> create VideoMetricSnapshot
  -> CandidateEvaluationService.apply()
  -> /review-board
```

## Worker Involvement

The canonical worker job type remains `CRAWL_PROFILE`. The worker handler should call `SourceIngestService.ingest_profile()` using the same configured adapter. This makes worker crawl and `/intake` use the same adapter and persistence code.

For this step, `/intake` remains synchronous because the existing UI and service flow already expect a summary response and the local Phase 1 crawl is metadata-only. Moving `/intake` to async polling can be a later UX step if live fetch becomes slow or unstable.

## Fallback Mode

Fallback behavior is preserved:

- Existing `SourceProfile` data can be reused by `/intake` without running a new crawl.
- `/source-profiles/ingest` can still pass `adapter_payload_json` for dev/test normalization.
- If live fetch is disabled, unavailable, blocked, or returns no videos, the API returns a clear error instead of the old generic missing-client message.

## Source Of Truth Entities Reused

- `SourceProfile`: profile identity, profile URL, display name, handle, profile raw payload.
- `CrawlSession`: one crawl attempt with status, counts, raw summary, result summary, and error details.
- `SourceVideo`: canonical source-video metadata.
- `VideoMetricSnapshot`: latest observed metrics per crawl session.
- `VideoCandidate`: persisted candidate score/filter result used by review board.

## No-Duplication Strategy

- No new profile/video/candidate models.
- No separate `/intake` persistence tables.
- No duplicate score/filter implementation.
- Live transport stays inside the adapter layer; persistence stays inside `SourceIngestService`; candidate discovery stays inside `CandidateEvaluationService`.

## Live Fetch Config

Environment variables:

- `DOUYIN_ENABLE_LIVE_FETCH`: enables the live HTTP fetch client.
- `DOUYIN_USER_AGENT`: optional browser user agent for Douyin requests.
- `DOUYIN_SESSION_COOKIE`: optional session cookie; never log this value.
- `DOUYIN_PROXY_URL`: optional HTTP(S) proxy.
- `DOUYIN_FETCH_TIMEOUT_SECONDS`: request timeout.
- `DOUYIN_FETCH_MAX_VIDEOS`: max normalized videos from one embedded payload.

## Current Limitations

- The live client extracts embedded JSON from public profile HTML. It does not bypass captcha, login, anti-bot checks, or private content.
- Live fetch can return zero videos if Douyin changes payload shape or withholds profile data. That is handled as a clear adapter error unless an already-ingested profile is available.
- `/intake` remains synchronous for now. Worker `CRAWL_PROFILE` is implemented for explicit jobs, but `/intake` does not submit a background job yet.
- No video media download is part of this step; downstream download/assets still starts after review-board decisions.
