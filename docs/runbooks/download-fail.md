# Download Fail Runbook

This runbook covers a failed or apparently stalled `DOWNLOAD_VIDEO` durable job.
Do not delete the source row or authoritative `MediaAsset` while diagnosing; the
managed staging directory is the only temporary area used by the downloader.
The managed directory is `.douyin_profiles/download_staging_v2` unless
`DOUYIN_DOWNLOAD_STAGING_DIR` is set. The old flat
`.douyin_profiles/download_staging` directory is not a valid retry location and
is intentionally excluded from automatic cleanup because regression fixtures may
still reference it.

## First classify the state

Inspect the job and the source manifest before clicking Retry:

```text
GET /jobs/{job_id}
GET /source-videos/{source_video_id}/asset-manifest
GET /source-videos/{source_video_id}/assets
```

In the job step named `register_assets`, read `metadata_json`:

- `download_phase` — current subphase;
- `download_phase_current` / `download_phase_total` — byte counters while
  `download_phase=transfer_primary`;
- `error_code` / `error_message` — the stable failure boundary.

The queue endpoint exposes the same values as `job_phase`,
`job_phase_current`, and `job_phase_total`. A percentage that does not move while
`transfer_primary` byte counters increase is normal; a phase and byte counter that
do not change beyond the configured stale threshold needs investigation.

## Common causes and action

### 1. Cache miss, corrupt file, or stale sidecar

Symptoms: `cache_validate` followed by a new resolve, or a log entry such as
`download_asset_cache_miss` with `missing_expected_checksum`, `size_mismatch`,
`checksum_mismatch`, `invalid_video_stream`, or `media_probe_unavailable`.

Checks:

- Confirm the current `SOURCE_VIDEO_RAW` row is `AVAILABLE` and `is_current=true`.
- Compare its `size_bytes` and `checksum_sha256` with the file reported by the
  manifest.
- Run `ffprobe` on the absolute path and verify a video stream, dimensions,
  duration, and codec.

Action: repair the local storage/ffprobe installation and retry normally. Use
explicit `force_refresh` only when the source itself must be fetched again. A
normal retry is allowed to reuse a verified cache.

### 2. Authentication/session failure

Symptoms: `RESOLVE_FAILED`/`DOWNLOAD_FAILED` with `login required`, `cookies
missing`, `session expired`, `no usable Douyin download cookies`, or a message
asking to refresh the download session.

Action:

1. Open the app-managed Douyin Chromium account and log in once.
2. Wait for the cookie store flush, then close the browser if the worker is meant
   to use the headless yt-dlp path.
3. Retry Start processing. Do not repeatedly force-refresh while the session is
   invalid; it only burns retry attempts.

### 3. Transient CDN/browser/network failure

Symptoms: timeout, HTTP 403/429/5xx, connection reset, `TargetClosed`, or
`browser_context_lost`. `yt-dlp no media bytes received` means the first-byte
watchdog escalated a resolver that stayed alive without producing media;
`transfer stalled` means byte progress stopped before completion.

Action: allow the durable retry/backoff policy to run. If it is safe to retry
manually, use normal Retry first. The HTTP path keeps an identity-validated
`.part` file and uses `Range` with `ETag`/`Last-Modified` (`If-Range`); yt-dlp
keeps its `--part` file. If a CDN returns a mismatched range or validator, the
downloader discards only that partial transfer and restarts it safely.

### 4. Strict no-logo or unsupported media rejection

Symptoms: `strict no-logo ... rejected`, `watermark-free ... not verified`,
`HLS/DASH manifest requires yt-dlp/ffmpeg`, `photo/slideshow`, or `no usable video
stream`.

Action: inspect the resolver metadata (`download_resolver`, `download_format`,
`watermark_free`, dimensions) and the source type. A watermark-only stream is
intentionally terminal under the default policy. Do not enable
`DOUYIN_DOWNLOAD_ALLOW_WATERMARKED_FALLBACK` merely to make the job green unless
the operator explicitly accepts a logo. HLS/DASH is handed to yt-dlp/ffmpeg
assembly; photo/live content still needs a dedicated media adapter. Raw manifest
bytes must never be registered as `SOURCE_VIDEO_RAW`.

### 5. Storage, disk, or validation failure

Symptoms: `storage_resolution_failed`, `write_failed`, `ffprobe is unavailable`,
`non-video content type`, empty/truncated payload, or a disk-full error.

Checks:

- Verify `LOCAL_STORAGE_ROOT` is writable and on the expected volume.
- Check free disk space against `MIN_FREE_DISK_GB` before retrying.
- Confirm `ffmpeg`/`ffprobe` are both on `PATH` and that the worker sees the same
  environment as the API.
- Inspect `.douyin_profiles/download_staging_v2/{workspace}/{account}/{aweme}/{transfer}`
  for a `.part`/`.ytdl` file; do not inspect or remove arbitrary paths.

Action: fix the environment, then retry. Validation failures remove the invalid
managed staging file; interrupted transfers are retained for Range/`--continue`
resume and are removed by the TTL sweep when expired.

### 6. Operator cancellation

Symptoms: the job has error code `cancelled`, or the operator intentionally
stopped it while `transfer_primary` was active. This is not a resolver failure.
The worker terminates the local transfer and leaves an identity-checked partial
file only when a retry can safely resume it; otherwise the partial is expired by
the managed TTL sweep. Retry is explicit after the operator confirms the source
and session are still valid.

## Resolver and cookie diagnostics

For a failed run, capture the following non-secret fields from logs or job
metadata:

- `download_resolver` / resolver error text (`yt_dlp`, `yt_dlp_browser`,
  `playwright_browser`, or `http_direct`; the current Playwright metadata does
  not distinguish direct registry use from the API bridge);
- `cookie_source` (`browser_live`, `browser_store`, `playwright_browser`, or an
  explicit session cookie indicator);
- `download_source_url` (never log cookie headers or auth tokens);
- `download_format`, `download_height`, `download_width`, and `watermark_free`;
- `media_probe` summary and transfer byte counters.

If the resolver repeatedly falls back to Playwright, check that yt-dlp is on the
worker `PATH`, `DOUYIN_YT_DLP_ENABLED=true`, and the shared browser cookie store
is readable by both API and worker. If Playwright is unavailable, verify the
account's persistent browser profile and the loopback API bridge.

## Retry decision

| Situation | Action |
| --- | --- |
| Verified cache hit expected | No retry; continue to the next pipeline stage |
| Cache miss/corrupt asset | Normal Retry; use force refresh only to intentionally replace source |
| Auth/session markers | Refresh login/session, then Retry |
| Timeout/CDN/browser transient | Wait for durable backoff, then Retry if needed |
| Strict no-logo/unsupported media | Fix source/resolver or explicitly approve watermark fallback |
| Missing URL, deleted source, bad DB binding | Mark `needs_fix`/reject; Retry will not change source data |
| Storage/disk/ffprobe environment | Fix host, verify with ffprobe, then Retry |

The job is idempotent at the `MediaAsset`/manifest boundary. A successful retry
must leave one current valid raw asset and explain optional thumbnail failures in
the manifest. Never treat a completed staging file as a deliverable until ffprobe
and atomic promotion have succeeded.
