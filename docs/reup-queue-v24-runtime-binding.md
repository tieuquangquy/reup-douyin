# Reup Queue V24.1 runtime binding

The Reup Queue `Start auto` action now binds the item to the immutable V24.1 recipe
before creating work. The binding is stored in `metadata_json.pipeline_recipe_lock`
as a portable `pipeline_recipe_lock_ref_v1` reference (release label, recipe hash,
artifact hash and validation boundary).

Every downstream durable stage created by the auto orchestrator copies the same
reference into both `Job.context_json` and `Job.payload_json`. A retry or resume
does not read a newly changed current pointer: it verifies the content-addressed
versioned artifact selected by the item. Missing, stale or tampered recipe evidence
fails closed to `FAILED_NEEDS_ATTENTION` with `PIPELINE_RECIPE_INVALID`.

`ANALYZE_OCR` jobs additionally bind the independent official `OCR-V34` recipe
from `docs/pipeline-recipes/analyze_ocr_recipe_current.json`. Its immutable
reference is stored as `analyze_ocr_recipe_lock` beside the V24.1 whole-pipeline
reference. The OCR lock pins
`audio_visual_temporal_v1` /
`audio_visual_temporal_policy_v12_epoch_complete_cover`,
Master Phase 1, source-raster Phase 2 geometry, and zero network calls. Existing
jobs already bound to an older whole-pipeline hash remain auditable; new OCR jobs
cannot silently fall back to a legacy scheduler. Detector candidate frames are
not retention authority; a single-frame track requires local CJK confirmation
and remains `UNCERTAIN` until provenance review.

## Operator flow

1. Open `/selection/reup-queue` and choose `Start auto` / `Full auto`.
2. The first action validates and binds the current locked recipe. The queue tile
   displays `V24.1 locked · <first 8 hash characters>` after the binding is persisted.
3. Existing durable jobs advance Download → Audio → Translate → TTS → OCR → Render,
   with the existing bounded lane, retry policy, pause/resume and Final Review gate.
   Auto-queue and manual Generate TTS both bind the single Ops TTS setup visibly
   `On`. The worker verifies the same setup/fingerprint before synthesis; switching,
   disabling or editing it while queued fails closed instead of using recipe, ENV,
   fallback or an Off setup. Provider Preview remains non-authoritative.
   Auto OCR explicitly sets `workflow_version=QUALITY_LOCALIZATION_V24_1`. A V24.1
   recipe paired with a legacy or missing quality workflow fails closed as
   `PIPELINE_RECIPE_WORKFLOW_MISMATCH`; it never falls back to legacy OCR. When the
   quality workflow needs operator input, the item parks at `quality_review`, frees
   its WIP slot, and resumes final render only after the separate visual and
   `AUDIO_MIX_APPROVED` checkpoints.
4. Continue through Final Review, then use the new **Export** rail for
   `FINAL_APPROVED` → metadata approval → source-rights/music attestation →
   `MANUAL_EXPORT_READY`. The final action persists the corresponding
   `ExportPackage` and `PublishHandoff` rows and exposes a hash-verified ZIP.
   External publishing remains disabled; no upload is marked complete.

`PIPELINE_RECIPE_LOCK_PATH` may override the current-pointer path for a controlled
local deployment. The default resolves to
`docs/pipeline-recipes/pipeline_recipe_current.json` from the repository root.

This binding makes the UI-triggered queue run auditable against V24.1. It does not
claim universal video support (`universal_video_support=false`) and does not replace
the separate fresh-holdout regression required before promoting V24.1 to production
default.

## Long-running Phase 1 execution

The locked recipe remains `v58_candidate`, `STEP=1`, `PAD=1`. Phase 1 runs in an
isolated Python subprocess so an ONNX failure or no-progress timeout cannot crash the
durable worker host. It emits frame-level progress, writes an atomic
`.phase1_scan_checkpoint.json`, and resumes the DBNet scan from that checkpoint after
a worker restart. `PHASE1_NO_PROGRESS_TIMEOUT_SECONDS` controls the scan watchdog and
defaults to 300 seconds. After the frame scan, 2K/4K sources may spend several minutes
reconciling a large detection set; this work emits explicit `phase1_postprocess_*`
heartbeats and uses the separate `PHASE1_POSTPROCESS_NO_PROGRESS_TIMEOUT_SECONDS`
ceiling (default 1200 seconds), so healthy post-processing is not mistaken for a
wedged frame scan.

DBNet keeps `CPUExecutionProvider` as the deterministic locked baseline. An operator
may explicitly select `directml` or `cuda` with `DBNET_ONNX_PROVIDER` only after the
matching ONNX Runtime is installed and the geometry regression corpus passes.
Unavailable providers fall back to CPU.

Normal frontend Analyze/Retry no longer forces a new Phase 1 workspace. It reuses the
active v58 result only when the source video, `master_timeline.json`, and
`phase1_meta.json` hashes all match. This removes the repeated 30-minute scan observed
on 2160x3840/60-fps sources without weakening the STEP=1 quality contract. Advanced
Re-analyze remains available as the explicit authority-breaking operation.
