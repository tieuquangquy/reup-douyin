# Douyin Zero Videos Hard Fix Architecture

## Problem Statement

The canonical Douyin intake path was treating an empty HTML shell response as a successful fetch with zero videos:

```text
/intake
  -> IntakeDiscoveryService.discover()
  -> DouyinAccountService.build_douyin_adapter()
  -> DouyinLiveFetchClient.fetch_html()
  -> extract_profile_payload_from_html()
  -> DouyinProfileAdapter.normalize_fetch_payload()
  -> SourceIngestService.ingest_profile()
  -> CandidateEvaluationService.apply()
```

When the HTTP response contained no embedded payload, the adapter still returned a `SourceFetchResult` with:

- `profile` present
- `videos = []`

This caused the fetch stage to be recorded as successful and the operator saw an ambiguous no-candidate result instead of a fetch-stage problem.

## Exact Root Cause

The failing stage is `response_classification`.

For the reproduced real profile:

- the connected account/session is selected correctly
- Douyin returns a shell/challenge bootstrap page
- the HTML parser finds zero embedded JSON documents
- zero videos are then treated as a successful parse

So the bug is not in account selection or candidate filters. It is the combination of:

1. weak HTML response classification
2. zero-video shell acceptance in the adapter
3. ingest stage events always reporting `ok`

## Canonical Fix

### 1. Strengthen response classification at fetch time

The live fetch client must distinguish:

- `success`
- `blocked_response`
- `login_required`
- `parse_failed`
- `parse_zero_videos`
- `true_zero_videos`

Zero videos may only remain a successful outcome if the response is explicitly classified as a true zero-video profile. Otherwise it is a fetch-stage issue.

### 2. Use browser probing only for diagnosis, not as a second pipeline

When HTTP fetch returns a shell with:

- zero embedded documents
- zero extracted videos

the client may use a bounded Playwright probe to determine whether the rendered page is:

- a challenge page
- a login-required page
- a rendered page with video links
- still unparseable

This probe is diagnostic support inside the same canonical live-fetch client. It does not create a second intake or persistence pipeline.

### 3. Make ingest observability reflect the real fetch stage

`SourceIngestService` must stop writing `ok` for zero-video shell outcomes. Instead:

- `response_classification` carries the real machine code/result
- `parse_payload` and `normalize_payload` show counts and warning/failure states
- `persist_entities` is warning-only when there is nothing valid to persist

### 4. Make intake result mapping explicit

`/intake` responses should distinguish:

- fetch-stage failure
- true zero videos
- filter zero candidates

This prevents operator confusion between:

- “Douyin never returned parseable videos”
- and
- “Videos were fetched, but current filters matched zero candidates”

## Final Classification Categories

The hardening for this step uses these canonical outcome categories:

- `success`
- `profile_resolution_failed`
- `login_required`
- `blocked_response`
- `parse_failed`
- `parse_zero_videos`
- `normalize_zero_videos`
- `persistence_zero_videos`
- `true_zero_videos`
- `filter_zero_candidates`

## No-Duplication Strategy

- Keep `DouyinAccountConnection` as the canonical connected-account model.
- Keep `DouyinProfileAdapter` as the canonical platform adapter.
- Keep `SourceIngestService` as the only ingest persistence path.
- Keep `CandidateEvaluationService` as the only candidate-generation path.
- Do not create a separate browser-only intake/discovery pipeline.

## Remaining External Limitations

- Douyin can still challenge or block a valid connected account/session.
- Local network path, account age, cookies, or browser fingerprinting can still affect fetch success.
- This step removes the false zero-video classification and makes failures explicit. It does not guarantee Douyin will always allow the fetch.
