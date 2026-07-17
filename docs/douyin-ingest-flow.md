# Douyin Ingest Flow

Step 4 introduces source-profile ingest for Douyin metadata. It does not download videos or run scoring.

## Flow

```text
POST /source-profiles/ingest
  -> SourceIngestService.ingest_profile()
  -> create CrawlSession RUNNING
  -> DouyinProfileAdapter.validate/normalize profile URL
  -> configured live fetch client or dev fixture payload normalization
  -> upsert SourceProfile
  -> upsert SourceVideo records
  -> insert VideoMetricSnapshot per video
  -> complete CrawlSession with summary counts
```

## Dedupe Strategy

- `SourceProfile`: dedupe by `source_platform + source_profile_external_id`.
- `SourceVideo`: dedupe by `source_platform + source_video_external_id`.
- `VideoMetricSnapshot`: insert one snapshot per `source_video_id + crawl_session_id`.

When a video already exists, ingest updates current normalized metadata such as URL, caption, posted time, duration, `metadata_json`, and `raw_payload_json`. Historical metrics are not overwritten; a new metric snapshot is created for the current crawl session.

## CrawlSession Trace

`crawl_sessions` records:

- submitted profile URL
- normalized profile identifier
- source platform
- status
- start/finish time
- discovered/created/updated/snapshot counts
- raw summary and result summary
- error code/message on failure

## Job Integration

The `CRAWL_PROFILE` job template now reflects the ingest steps:

```text
validate_input
resolve_profile
fetch_profile_payload
normalize_payload
upsert_profile
upsert_videos
create_metric_snapshots
finalize_session
```

The API currently runs intake ingest synchronously through the service. The worker `CRAWL_PROFILE` path also calls the same `SourceIngestService`, so worker and API ingest share one persistence path.

## Phase 1 Limits

- A minimal live Douyin HTML fetch client is available when `DOUYIN_ENABLE_LIVE_FETCH=true`. Douyin can still block or omit embedded payloads, so cookie/proxy config or already-ingested fallback data may be required.
- No video download.
- Candidate scoring/creation happens after intake through `CandidateEvaluationService`; raw ingest alone still only persists source profile/video/metric data.
- No OCR/STT/TTS/render.
- No distributed queue.
