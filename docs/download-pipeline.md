# Download Pipeline

The download pipeline starts after an operator keeps a candidate for further processing. Its job is to bring source assets into controlled storage and register them as `MediaAsset` records for OCR, STT, TTS, subtitle, and render steps. The download boundary is intentionally durable: a request only creates a `DOWNLOAD_VIDEO` job; the worker performs the transfer and can resume it after a transient failure.

## Flow

1. API receives `POST /downloads` with either `source_video_id` or `candidate_id`.
2. `DownloadService` resolves the canonical `SourceVideo`.
3. The service binds the effective Douyin account and derives a stable
   `download:{source_video_id}:{account_id}` idempotency key for normal (non-
   refresh) commands. Thus candidate and source selectors for one video share
   one durable job; an explicit `Idempotency-Key` is still honored.
4. A `DOWNLOAD_VIDEO` job is created through the job system.
5. The worker runs the job template:
   - `register_assets` (cache validation, resumable transfer, ffprobe validation,
     atomic promotion, optional thumbnail and sidecars)
   - `finalize_manifest`
6. The `register_assets` step calls `DownloadService.run_download` and emits
   `cache_validate`, `resolve_session`, `resolve_candidates`,
   `transfer_primary|bytes_done|bytes_total`, `validate_primary`,
   `atomic_promote`, `thumbnail_optional`, `persist_sidecars`, and
   `finalize_manifest` heartbeat phases.
7. The service downloads/writes assets through the downloader and storage abstractions.
8. The service registers or updates `MediaAsset` rows.
9. The manifest is assembled from DB records and returned by asset APIs.

## Cache authority and refresh semantics

`SOURCE_VIDEO_RAW` is reusable only when all of the following are true:

- the `MediaAsset` row is `AVAILABLE`, `is_current=true`, and has a positive persisted size;
- the stored file still exists;
- the current SHA-256 and size match the values persisted on the row; and
- `ffprobe` confirms a usable video stream (positive width, height, duration, and video codec).

The normal queue path uses `force_refresh=false`, so a verified current asset is a cache hit and does not open a browser or transfer bytes. A missing, corrupt, truncated, or unprobeable asset is a cache miss and is downloaded again. `force_refresh=true` is an explicit operator command: it bypasses the raw/thumbnail cache. It is not the default retry behavior. Sidecars use versioned filenames/rows; the operator-facing raw filename is not version-prefixed. When a refresh resolves to the same raw storage key, the file and row are refreshed atomically in place, so the prior bytes are not retained as a separate historical object.

The cache check is an integrity check, not merely an `exists()` check. Recent local assets also carry a file identity/mtime fingerprint and bounded probe summary; while that fingerprint is unchanged (24 hours by default), the queue can return a fast cache hit without rereading the entire blob. After the interval, after a stat change, or for legacy rows without the fingerprint, the full SHA-256 and ffprobe check runs. This prevents a partially copied file or a stale file at the same logical key from being treated as a valid source.

## Douyin resolver policy

For `balanced_processing`, the resolver uses a discovery-first path whenever
the adapter supports it. yt-dlp runs metadata-only (`--dump-single-json
--skip-download`) and the logged-in Playwright context reads the detail payload
without requesting CDN bytes. A shared scorer ranks the sanitized candidates,
then only the winning resolver performs a full transfer. If that signed URL or
format fails, the next discovered candidate is tried; legacy adapters without
`discover()` automatically use the previous resolve-first path. Signed URLs
are kept only in memory for the active transfer and never enter the selection
manifest or asset metadata.

The active quality policy is recorded with every `SOURCE_VIDEO_RAW` asset. The
default `DOUYIN_DOWNLOAD_QUALITY_PROFILE=balanced_processing` targets the
configured `DOUYIN_DOWNLOAD_TARGET_LONG_EDGE` (1920 by default), prefers clean
H.264 that is cheap for OCR/render, and includes a policy fingerprint in cache
validation. `source_master` removes the processing ceiling and keeps the
highest verified clean source returned by the resolver; it is opt-in because
larger HEVC/AV1 files increase transfer, decode and render cost.

No-logo is a provenance claim, not a pixel theorem. `bit_rate`/`play_addr`
payload evidence and yt-dlp's affirmative format metadata are authoritative;
`watermark=0` on a direct CDN URL is retained as a URL hint in metadata and is
not used to rank resolver candidates. Resolver-only strict paths fail closed
when no authoritative clean stream exists. The post-transfer QA also compares
measured dimensions/codec/FPS, duration and expected audio presence before
promotion.

For a Douyin page URL or aweme id, the default policy is strict no-logo mode (`DOUYIN_DOWNLOAD_ALLOW_WATERMARKED_FALLBACK=false`):

1. A verified direct media URL may use the streaming HTTP downloader.
2. When a usable browser/session cookie is available, yt-dlp is attempted first as the low-overhead fast path (90 seconds by default, controlled by `DOUYIN_YT_DLP_FAST_PATH_TIMEOUT_SECONDS`). Its selector caps the long edge at 1920 and avoids HEVC/AV1 where possible; the `info.json` evidence must identify affirmative clean playback provenance rather than merely an unknown format id. The fast result is accepted immediately only when it is verified no-logo H.264 at the preferred 1920 long edge (and non-HDR). A clean HEVC/720p result is retained as a fallback, but Playwright is given one bounded chance (45 seconds by default via `DOUYIN_DOWNLOAD_QUALITY_ESCALATION_TIMEOUT_SECONDS`) to obtain a better candidate and both candidates are ranked by the same quality policy. A first-byte watchdog (`DOUYIN_YT_DLP_FIRST_BYTE_TIMEOUT_SECONDS`, 45 seconds by default) and a transfer-stall watchdog (`DOUYIN_YT_DLP_STALL_TIMEOUT_SECONDS`, 90 seconds) abandon dead signed-CDN attempts early; the watchdog is disabled after yt-dlp reports the byte total and enters local merge.
3. If that fails, an active Playwright browser resolver (or the API-bridged resolver) can obtain a clean `bit_rate`/`play_addr` stream. Auto-open/headless behavior is controlled by the corresponding settings. Navigation fallback uses an adaptive settle loop (`DOUYIN_PLAYWRIGHT_MEDIA_SETTLE_TIMEOUT_MS`, 2.5 seconds maximum) and exits as soon as a clean candidate is captured, instead of unconditionally sleeping the full budget.
4. If the fast path was not attempted, yt-dlp is tried as a last resolver. Every candidate is still gated by the strict no-logo check and media validation before persistence.

Candidate ranking prefers a watermark-free stream, a render-compatible H.264 stream, a long edge at or below the configured target, then the highest useful pixel/bit-rate quality. Watermarked fallback is available only when an operator explicitly enables it. Browser recovery and CDN fallback preserve the same profile and target, so a retry cannot silently select a different quality policy.

The durable queue allows two network-bound `DOWNLOAD_VIDEO` jobs per workspace by default, matching the two local worker processes. The Playwright registry still serializes browser-owned transfers; direct CDN and yt-dlp jobs can overlap without opening multiple Chromium operations against one profile. Increase the cap only together with `WORKER_COUNT` and disk/network headroom.

This policy cannot guarantee every Douyin post. Private/deleted/region-limited/challenge-protected posts, expired signed URLs, photo/slideshow/live content, and posts for which the account has no clean playback stream can still fail. HLS/DASH manifest URLs are routed to yt-dlp/ffmpeg assembly rather than persisted as raw bytes, but they still depend on an extractor that supports the manifest and its session. A watermark-only result is rejected in strict mode rather than silently accepted.

## Transfer, staging, and validation

- HTTP media is streamed in bounded chunks (default 1 MiB) to a managed staging file. If a retry finds a `.part` file, it sends an HTTP `Range` request and appends only when the server's `Content-Range`, URL fingerprint, and saved `ETag`/`Last-Modified` validator agree. When a signed CDN token rotates, a secondary path/resource fingerprint may preserve the resume only if the validator is present and matches; otherwise the partial is discarded and restarted safely. A server that ignores or mismatches the range causes a safe restart from byte zero.
- yt-dlp uses `--continue`/`--part`/`--max-filesize` in the same managed staging namespace. With a worker callback it runs a cancellable progress-aware subprocess and emits byte heartbeats. Playwright and the API bridge return a local staging path when available, avoiding an extra Python bytes copy.
- Before a response becomes authoritative `SOURCE_VIDEO_RAW`, the service rejects empty data, HTML/JSON/text responses, HLS playlists, audio-only payloads, and files that `ffprobe` cannot parse as a video. Probe metadata (dimensions, duration, codecs, and audio-stream presence) is stored as bounded sidecar metadata.
- A completed staging file is promoted to the logical storage key atomically on the same volume (`os.replace`); a cross-volume/object-storage adapter falls back to a streamed write. SHA-256 is calculated during the promotion/write and persisted with the `MediaAsset` row.
- Only the primary video is required. Thumbnail retrieval is best effort; a failed thumbnail is recorded as a failed optional asset while the usable source video and metadata mirror remain available.

The managed staging root defaults to `.douyin_profiles/download_staging_v2` and is namespaced as:

```text
download_staging_v2/
  {workspace}/
    {account_connection}/
      {aweme_id}/
        {transfer_or_job_id}/
          video.mp4 | http.mp4 | *.part | *.ytdl
```

Staging is never the authoritative asset location. A worker housekeeping sweep removes only files older than `DOUYIN_DOWNLOAD_STAGING_TTL_HOURS` (24 hours by default), then removes empty namespace directories. It does not recursively delete authoritative storage.

`DOUYIN_DOWNLOAD_STAGING_DIR` is the canonical override and must resolve to the
same directory for API and worker processes. `DOUYIN_PLAYWRIGHT_DOWNLOAD_STAGING_DIR`
is retained only as a compatibility alias; when both are set, the canonical
setting wins. Do not point either setting at `LOCAL_STORAGE_ROOT`.

### Legacy staging migration

Older pilot scripts used `.douyin_profiles/download_staging` (a flat directory)
for both completed regression inputs and temporary transfers. The v2 sweeper
deliberately does **not** scan or delete that directory: several regression
manifests may still reference its completed MP4 files, and treating every MP4 as
temporary could destroy a source corpus. New downloads never write there.

To retire the legacy directory, first inventory references from the repository
and manifests, for example:

```powershell
rg -n --hidden --glob '!node_modules/**' --glob '!*.pyc' "download_staging[\\/]" docs apps
```

Copy any referenced source into a controlled corpus or authoritative asset,
update the manifest paths, and have the operator verify the migrated files.
Only then remove the legacy files manually. A normal worker housekeeping pass
must never be used as a legacy migration command.

## Progress, cancellation, and resume

The download step emits real subphases (`cache_validate`, `resolve_session`, `resolve_candidates`, `transfer_primary`, `validate_primary`, `atomic_promote`, `thumbnail_optional`, `persist_sidecars`, `finalize_manifest`). During `transfer_primary`, the job step stores `download_phase_current` and `download_phase_total` byte counters; the queue UI can display `bytes_done/bytes_total`. Job and step percentages are clamped and monotonic, so an old job cannot jump backward when resumed.

Cancellation is checked at worker heartbeat boundaries. HTTP streaming reports each chunk and can stop promptly; the local yt-dlp subprocess is polled and terminated on cancellation/timeout; Playwright's direct CDN transfer reports chunks as well. The API bridge shares a cancellation marker in the managed staging namespace, so its transfer can stop without waiting for the full bridge timeout. A normal command persists a stable transfer namespace in the job payload, so queue Hold/Resume can reuse an identity-validated HTTP `.part` file even though the terminal job row is recreated. A retry resumes only an identity-validated HTTP `.part` file or yt-dlp `.part`; invalid media is deleted from staging, while an interrupted transfer is retained until retry or TTL cleanup.

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
- `cancelled`

Download failures also carry a structured reason for retry/observability:
`auth_expired`, `challenge_blocked`, `no_clean_stream`, `signed_url_expired`,
`extractor_drift`, `unsupported_post_type`, `media_corrupt`, or
`network_transient`.

## Downloader Boundary

Profile ingest and media download are separate concerns.

- Source adapters normalize profile/video metadata.
- Downloaders fetch bytes for known asset URLs.
- Storage backends persist bytes at logical keys.
- `MediaAsset` records connect canonical video records to stored files.

This keeps future TikTok, Kuaishou, Xiaohongshu, or cloud storage implementations from changing orchestration logic.

## Phase 1 Limits

- Douyin access still depends on a valid browser/session and a provider stream; private,
  deleted, challenge-protected, region-limited, or watermark-only posts can fail with a
  classified terminal error.
- HLS/DASH posts are handed to the yt-dlp/ffmpeg assembly path and are not silently
  persisted as manifest bytes; photo/slideshow/live posts remain outside the single-video
  recipe unless a dedicated media adapter is enabled.
- The local worker is intentionally single-host; storage and job boundaries remain
  replaceable for a future distributed queue.
