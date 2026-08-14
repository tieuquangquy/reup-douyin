# Local Audio-Visual Temporal OCR V25

## Product boundary

The existing Final Review `Analyze OCR` button submits the durable `ANALYZE_OCR`
job with `analysis_engine=audio_visual_temporal_v1`. The API does not process the
video inline. The worker invokes the quality-localization Phase 1 subprocess and
then continues into local Phase 2 OCR.

Analyze OCR performs no network or LLM calls. Persisted transcript timing may be
used to schedule candidate windows, but missing transcript data degrades to
Visual-Only mode. Translation remains a separate downstream step and cannot
change geometry, timing, provenance, or source authority.

## Local event pipeline

1. Build conservative audio windows from current persisted transcript segments.
2. Inspect every frame through a 256-pixel FFmpeg visual-probe stream.
3. Schedule detector evidence from audio windows, visual changes, short bursts,
   and a safety heartbeat.
4. Enforce a time-based rolling detector budget. Dense rescans are capped at
   `min(12%, 3.5 / source_fps)`, so 60 FPS input does not silently double the
   expensive detector work.
5. Decode a 256-long-edge stream for the all-frame event scheduler, then ask
   FFmpeg for only the selected source frame numbers at a maximum 1280-pixel
   long edge. Selected-frame expressions are bounded to 80 frames per process
   for stable Windows FFmpeg parser memory.
6. Use the same selected-frame decoder for dense boundary and small-text passes;
   these passes must never reopen and sequentially decode every 4K source frame.
7. Perform a bounded boundary rescan and bounded dense-UI recovery.
8. Track geometry temporally, separate visual content state with local edge
   change points, and classify provenance before editor-only post-processing.
9. Treat a small locked candidate as `SOURCE_INTRINSIC_PANEL` when overlapping
   source-bound peers form a spatially diverse UI plane around it. This protects
   text inside phone screens and other photographed interfaces.
10. Preserve `SOURCE_INTRINSIC`, `SOURCE_INTRINSIC_PANEL`, and `PLATFORM_UI`
   before local recognition; fail closed on uncertain text. Symbol-dominant
   recognizer output such as `8=` is discarded as non-text noise.

The active policy is
`audio_visual_temporal_policy_v7_source_modal`. FFmpeg decodes directly
to the analysis raster for event mode, so Python never allocates and resizes
every 4K BGR frame. Proxy coordinates are
scaled back to source pixels before `master_timeline.json` is written. Phase 1
records `frame_width` and `frame_height` in `phase1_meta.json`; Phase 2 must use
those source dimensions, never the proxy keyframe raster. Keyframe inspection is
only a compatibility fallback for older artifacts.

## Official recipe lock

Policy v7 is the official frontend Analyze OCR default under the independent
`OCR-V25.1` recipe. The mutable pointer is
`docs/pipeline-recipes/analyze_ocr_recipe_current.json`; every job persists the
matching content-addressed `analyze_ocr_recipe_<sha256>.json` reference in both
`Job.payload_json.analyze_ocr_recipe_lock` and
`Job.context_json.analyze_ocr_recipe_lock`.

The worker fails closed before execution when the job requests another engine,
does not use Master Phase 1, the installed policy constant differs from the
locked policy, the recipe hash is stale, or either OCR phase permits network
calls. This lock is intentionally separate from the immutable whole-pipeline
V24.1 authority: changing the Analyze OCR scheduler must not rewrite the TTS,
render, export, or publishing contract.

The operator explicitly promoted v7 after one measured frontend validation and
waived the proposed 5–10-video frontend regression. The V25.1 recovery evidence
was then measured locally against that frontend-produced Phase 1 artifact. The
lock records this as `batch_regression=SKIPPED_BY_OPERATOR`; therefore it is the
official local default but does not claim universal-video support.

OCR-V25.1 adds a bounded recovery pass after the primary local recognition:
failed editor candidates use at most two temporally distinct frames and a
maximum of 12 prepared inputs per run. For failed `hardsub` tracks only, each
selected frame also gets one narrow, deterministic vertical-line search plus
the immutable Phase-1 box. A geometry candidate is accepted only after the
same text is supported on two distinct frames; otherwise the pass leaves the
Phase-1 geometry untouched and records `UNRESOLVED_FAIL_CLOSED`. Accepted
geometry lives only in `phase2_ocr_timeline.json` (and a QA crop under
`qa/geometry_recovery/`), never in `master_timeline.json`. Repeated short
labels at the same UI geometry are promoted to `SOURCE_INTRINSIC_PANEL`
instead of being translated.

The geometry recovery policy is
`phase2_hardsub_geometry_recovery_v1`. It uses local Sobel/blackhat stroke
projections, a bounded vertical neighbourhood, connected horizontal stroke
runs, and the existing local OCR consensus. No external model or network call
is introduced. On the 4K/60 FPS reference artifact it recovered
`直接给我丑哭了` and `特别接近我在镜子里看到的我自己`, reduced the recovery
batch to the documented 12-input cap, and kept the two source UI `素材`
occurrences protected.

V58 remains available to legacy callers and the Phase 1 CLI, but is not the
default engine behind the frontend button. No Authority V3.6 full-duration scan
is enabled.

## Review checkpoint continuity

`ANALYZE_OCR` completion means local detection and persistence succeeded; when
review objects exist, the workflow intentionally enters `WAITING_OCR_REVIEW`.
Submitting those decisions creates an `approve_ocr` durable job. Every quality
action, including approval and replay, is forced to the engine declared by the
official OCR recipe. The legacy `OcrRequest` V58 default is ignored at this
boundary and cannot overwrite the engine used by the completed analysis.

After all OCR decisions are materialized, the workflow advances to
`WAITING_TRANSLATION_REVIEW` when editor-overlay text needs Vietnamese, or to
the next visual/render checkpoint when no translation review is needed. A
successful Analyze job alone must not be mistaken for approval, while a
successful approval job must never return to OCR review.

## Artifacts

The engine keeps `master_timeline.json` for downstream compatibility and adds:

- `phase1_candidate_windows_v1.json`
- `phase1_temporal_consensus_v1.json`
- `phase1_provenance_v3.json`
- `phase1_event_timeline_v25.json`
- `phase1_event_metrics.json`

`quality_phase1_authority.json` binds the source hash, candidate-seed hash,
timeline hash, provenance hash, engine version, and metrics hashes. A retry may
reuse Phase 1 only when every authority reference still matches.

## Observability

The OCR summary exposes the active analysis engine, candidate-window count,
detector-frame count, elapsed time, metrics, and fallback state. The Final Review
screen shows these beside the provenance counters.

The benchmark fixture `7450099336215579915.mp4` (27.13 seconds, 694 frames)
completed Phase 1 in 25.1 seconds on the local Windows DirectML runtime. It used
83 detector frames (11.96%), 83 detector preprocessing calls, zero network calls,
and produced 27 tracks. The 1920x1080 source used a 1280x720 proxy while Phase 2
correctly retained a 1920x1080 source raster. Peak cached-frame bytes fell from
about 516 MB to about 229 MB. The previous unconstrained event attempt selected
all 694 frames and exceeded 180 seconds, so the time-based budget, proxy boundary,
and bounded post-processing are mandatory correctness/performance guards.

The 4K/60 FPS regression source `3b6599c2-9beb-4fe3-8370-4c6329da429d`
(41 seconds, 2483 frames, 2160x3840) originally needed 192.9 seconds even with
proxy detector inputs because dense passes still decoded the full 4K stream.
Policy v3 completes Phase 1 in 61.1 seconds with the same 144 detector-frame
budget and 2160x3840 output geometry. This is a 68% Phase-1 reduction on the
local reference machine; Phase 2 local recognition remains a separate measured
cost.

Policy v7 additionally derives the merge gap from the 3 FPS event detector
cadence (`ceil(source_fps / 3)`). The matching finalize gap applies only to
geometry-compatible mid-frame editor cards; compact source UI keeps the strict
legacy split gap. This prevents a persistent editor card from being split into
isolated one-hit tracks without over-merging phone controls. V58 remains
unchanged.

A compact locked value that persists for at least 45 frames with at least three
observations is preserved as `SOURCE_INTRINSIC_PANEL` when it lacks editor-card
scale. This covers in-app modal values such as aperture/focus labels; preserving
ambiguous compact UI is the fail-closed action, while large outlined editor
cards remain localizable.
