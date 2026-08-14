# Local Coverage-First Temporal OCR V26

## Runtime boundary

The frontend `Analyze OCR` action still submits the durable `ANALYZE_OCR` job.
The API does not process video inline. OCR detection and recognition remain
local-only; translation remains a separate downstream operation.

The official engine is `audio_visual_temporal_v1` with policy
`audio_visual_temporal_policy_v8_coverage_first`. Authority V3.6 full-duration
is not enabled.

## Coverage-first pipeline

1. Decode a 256-pixel all-frame event proxy.
2. Measure scene, edge, and dark/bright textness changes.
3. A strong one-frame textness boundary bypasses the rolling detector budget.
4. Run local DBNet only on scheduled seed frames and bounded recovery frames.
5. Merge seeds into temporal tracks and classify source/editor provenance.
6. Decode one 384-pixel all-frame proxy and close each seed track using local
   stroke evidence, hysteresis, frame-exact presence ranges, and geometry
   keyframes.
7. Write `phase1_track_coverage_v2.json`, hash-bound to
   `master_timeline.json`. The master remains a compatibility projection and is
   not overwritten by Phase 2.
8. Phase 2 carries the coverage authority into `phase2_ocr_timeline.json`.
9. The local Semantic Hard-sub Cue Authority aligns OCR geometry with current
   ASR token timing, canonicalizes temporal cue variants, and reuses only an
   approved dialogue translation.
10. Phase 4 resolves presence and geometry for each encoded frame.

The semantic content layer is documented in
[`semantic-hardsub-cue-authority.md`](./semantic-hardsub-cue-authority.md).
OCR remains local-only; this step does not introduce a model or network call.

## Source/editor boundary

The provenance gate remains fail-closed. Dense or spatially diverse phone/UI
planes are protected before localization. A bounded row contained by at least
six proven source-plane peers may override a misleading hardsub-shaped box.
Uncertain tracks preserve source pixels.

## Unified concealment

All editor overlays use `coverage_safe_blur_plate_v2`:

- one cover style for all roles;
- a fully opaque core inside the glyph authority;
- feathering only in the padded edge band;
- stronger resolution-aware Gaussian low-pass;
- local background tint to remove coloured glyph ghosts;
- one adaptive retry when residual stroke energy remains too high.

The mask cache is keyed by frame-resolved cover geometry, so a moving or
expanding track cannot reuse a stale rectangle.

## Fail-closed QA

- Encoded-output QA resolves the same frame geometry as the renderer.
- Full-timeline visual authority records unchanged source-text strokes inside
  an intended cover.
- A remaining single-frame CJK decode is blocking even when adjacent frames do
  not confirm it.
- Sampling is retained for operator contact sheets, not as authority to clear a
  detected one-frame residual.

## Recipe and artifacts

The official frontend recipe is `OCR-V26`; the mutable pointer remains
`docs/pipeline-recipes/analyze_ocr_recipe_current.json`. Each job is bound to the
content-addressed immutable recipe before worker execution.

New artifact:

- `phase1_track_coverage_v2.json`
- `semantic_dialogue_authority.json`

Existing artifacts remain supported:

- `master_timeline.json`
- `phase1_candidate_windows_v1.json`
- `phase1_temporal_consensus_v1.json`
- `phase1_provenance_v3.json`
- `phase1_event_metrics.json`
- `phase2_ocr_timeline.json`

The V26 recipe explicitly reports universal-video regression as pending until
the operator completes frontend validation. It does not claim universal video
support from unit fixtures alone.
