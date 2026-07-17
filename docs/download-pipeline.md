# Download Pipeline

The download pipeline starts after an operator keeps a candidate for further processing. Its job is to bring source assets into controlled storage and register them as `MediaAsset` records for OCR, STT, TTS, subtitle, and render steps.

## Flow

1. API receives `POST /downloads` with either `source_video_id` or `candidate_id`.
2. `DownloadService` resolves the canonical `SourceVideo`.
3. A `DOWNLOAD_VIDEO` job is created through the job system.
4. The worker runs the job template:
   - `validate_input`
   - `resolve_storage`
   - `fetch_primary_video`
   - `fetch_thumbnail`
   - `persist_metadata_mirror`
   - `register_assets`
   - `finalize_manifest`
5. The `register_assets` step calls `DownloadService.run_download`.
6. The service downloads/writes assets through the downloader and storage abstractions.
7. The service registers or updates `MediaAsset` rows.
8. The manifest is assembled from DB records and returned by asset APIs.

## Asset Types In Scope

- `SOURCE_VIDEO_RAW`
- `THUMBNAIL`
- `METADATA_JSON`
- `SOURCE_CAPTION_RAW`
- `SOURCE_VIDEO_PREVIEW` as a future-friendly type
- `SOURCE_AUDIO_EXTRACT` as a future-friendly type
- `TEMP_FILE`
- `RENDER_OUTPUT`

The pipeline does not extract audio or render previews in this step. Those asset types exist so later processing stages do not need a schema rewrite.

## Error Strategy

The source video file is required. If it cannot be fetched or written, the download run fails.

Thumbnail is optional. If thumbnail download fails, the pipeline records a `FAILED` thumbnail asset and continues with the primary video and metadata mirror. This keeps the manifest honest while avoiding unnecessary failure of an otherwise usable video.

Error codes are intentionally stable:

- `invalid_source_video`
- `missing_source_url`
- `storage_resolution_failed`
- `download_failed`
- `write_failed`
- `validation_failed`
- `manifest_update_failed`

## Downloader Boundary

Profile ingest and media download are separate concerns.

- Source adapters normalize profile/video metadata.
- Downloaders fetch bytes for known asset URLs.
- Storage backends persist bytes at logical keys.
- `MediaAsset` records connect canonical video records to stored files.

This keeps future TikTok, Kuaishou, Xiaohongshu, or cloud storage implementations from changing orchestration logic.

## Phase 1 Limits

- The default downloader is a simple HTTP byte fetcher.
- No Douyin-specific signed URL extraction is implemented.
- No video validation beyond non-empty file, existence, size, and checksum is implemented.
- No distributed queue backend is implemented; the existing worker skeleton can execute the job locally.
