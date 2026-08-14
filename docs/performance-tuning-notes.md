# Performance Tuning Notes

Phase 1 performance work is about avoiding wasted local work, not micro-optimizing every service.

## Metrics To Watch

`GET /ops/metrics` reports:

- job counts by type and status
- failure rate by job type
- queue backlog for `QUEUED`, `RETRYABLE`, and `RUNNING`
- retry attempts
- average step duration by job type
- average processing seconds per source video
- common failure error codes
- current vs historical media assets by type
- render, publish draft, and open risk summaries

Use these numbers before tuning. If `RENDER_FINAL` dominates duration, optimize render/probe/reuse first. If `ANALYZE_AUDIO` dominates failure count, inspect audio asset resolution and provider fallback.

## Reuse Policy

- Media assets use `is_current` to distinguish current outputs from historical versions.
- Manifest-style outputs are rebuilt from canonical DB records plus current assets.
- TTS, subtitle, render-prep, and render outputs should be reused only when their current input version and asset references are unchanged.
- If input text, timing, subtitle data, narration, or source asset changes, downstream outputs should be treated as stale.

### V24.1 compute reuse

- A hash-bound `VISUAL_PREVIEW_RENDERED` + Output-QA `PASS` artifact is the visual
  authority for Final. Final reuses its encoded video packets with `-c:v copy`,
  replaces only approved narration/background audio, compares the preview/final
  video-packet SHA-256, and reuses visual QA only on an exact packet match. Any
  stale input, remediation ref, preview hash or QA mismatch falls back to the full
  adaptive renderer and full encoded-output QA.
- Dialogue translation uses bounded JSON batches (8 beats by default). Every row
  still crosses the existing CJK, duration, protected-token and review gates;
  malformed batch JSON falls back per beat, while provider/network failures keep
  the normal durable retry policy.
- Fitted TTS WAV clips are stored in a content-addressed cache keyed by text,
  duration budget, provider/model/options, recipe runtime authority, voice/rate and
  timing policy. Retry/resume reuses only an exact key + audio SHA-256 match.

### Download measurement and tuning

Download is primarily I/O- and resolver-bound. Measure the durable job rather
than timing the browser button alone. Record `created_at`, `started_at`,
`completed_at`, retry count, resolver, cache hit/miss, and the
`transfer_primary` byte counters. A local sample of 127 `DOWNLOAD_VIDEO` jobs
(126 completed) had p50 `16.65 s`, p90 `39.00 s`, and p95 `54.88 s`; one
three-retry outlier took about `2035 s`. These numbers are a machine/session
reference, not a guarantee for all Douyin posts.

The highest-impact controls are:

- keep the normal queue path cache-first (`force_refresh=false`);
- keep a warm, authenticated browser cookie store so yt-dlp can run headlessly;
- prefer the <=1920, H.264-compatible clean stream to avoid oversized transfers
  and later transcoding;
- keep HTTP transfers streaming and Range-resumable; and
- keep the first-byte/stall watchdogs enabled so a dead signed CDN attempt
  escalates before the full yt-dlp budget; and
- cap `DOWNLOAD_VIDEO_MAX_CONCURRENT_RUNNING` to the disk/network capacity (two
  is the default for the two local worker processes; Playwright browser work
  remains serialized while direct/yt-dlp transfers can overlap).

Transfer scratch space is separate from the authoritative asset tree. The v2
staging sweeper honors `DOUYIN_DOWNLOAD_STAGING_TTL_HOURS` and removes only
expired files inside the managed v2 namespace (authoritative storage is never
scanned). Do not point it at the historical flat
`.douyin_profiles/download_staging` directory: that directory contains old
regression sources and requires an explicit, reference-checked migration before
manual cleanup.

Do not infer a slow download from a flat aggregate percentage. Inspect
`download_phase`; `transfer_primary` with increasing bytes is making progress,
while an unchanged phase/byte counter beyond the download stale threshold is a
candidate for recovery. A Playwright resolver can still have little visible byte
progress while it resolves a signed URL; direct CDN transfer and the local
yt-dlp subprocess emit byte heartbeats, while the API-bridged fallback remains
bounded by its bridge timeout.

Measured local reference on 2026-08-05 (GTX 1650, Windows):

- DBNet inference for the same prepared tensors averaged `0.0346 s/call` on CPU
  and `0.0188 s/call` on DirectML, about 46% lower latency. A 10-frame
  CLAHE/stroke comparison preserved all tested boxes at IoU >= 0.95.
- Finalizing a 26.8-second approved V24 preview took `1.88 s` with stream copy,
  versus `49.94 s` for the earlier full adaptive render: 26.55x faster, or 96.23%
  less wall time for this finalization step. Preview and Final encoded-video
  packet SHA-256 were identical, and reused visual Output QA plus fresh audio QA
  returned PASS. This is a single-machine reference, not a throughput guarantee.

## Local Bottlenecks

- Download and storage are IO-bound; cache misses add session/stream resolution
  latency before bytes start moving.
- Audio analysis, TTS, and render are CPU/GPU/provider-bound depending on provider implementation.
- Render probing and manifest assembly should not be repeated inside tight UI polling loops.
- The local worker should process a small number of jobs at a time until real queue backpressure exists.
- On Windows, DBNet selects DirectML/CUDA automatically when the installed ONNX
  Runtime exposes it, with CPU retained as fallback. The dynamic DBNet model uses
  fixed-shape DirectML sessions keyed by prepared tensor shape; this avoids the
  unsupported dynamic ConvTranspose path without changing model inputs.

## What Not To Optimize Yet

- Do not add distributed scheduling before Redis/queue backend is actually introduced.
- Do not cache raw payload parsing in UI code.
- Do not bypass MediaAsset or manifest abstractions for speed.
- Do not hide provider failures behind silent placeholder outputs in alpha/pre-beta testing.
