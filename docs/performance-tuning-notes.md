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

## Local Bottlenecks

- Download and storage are IO-bound.
- Audio analysis, TTS, and render are CPU/GPU/provider-bound depending on provider implementation.
- Render probing and manifest assembly should not be repeated inside tight UI polling loops.
- The local worker should process a small number of jobs at a time until real queue backpressure exists.

## What Not To Optimize Yet

- Do not add distributed scheduling before Redis/queue backend is actually introduced.
- Do not cache raw payload parsing in UI code.
- Do not bypass MediaAsset or manifest abstractions for speed.
- Do not hide provider failures behind silent placeholder outputs in alpha/pre-beta testing.

