# Local Completeness-First OCR V27.1

## Runtime boundary

The frontend `Analyze OCR` action submits the durable `ANALYZE_OCR` job and is
bound to the immutable `OCR-V27.1` recipe. Detection, recognition and provenance
remain local-only. Translation is a separate downstream authority.

The engine remains `audio_visual_temporal_v1`; the installed policy is
`audio_visual_temporal_policy_v10_cjk_single_frame_consensus`. Authority V3.6
full-duration remains disabled.

## Completeness-first discovery

1. FFmpeg decodes a 512-pixel proxy for every source frame.
2. Audio timing, scene changes, edge changes and absolute bright/dark stroke
   evidence schedule the high-resolution detector. They prioritize work but do
   not suppress persistent text candidates.
3. Local DBNet runs both CLAHE and stroke preparations at source-aware analysis
   resolution. Cheap candidate scheduling is not retention authority: a
   one-frame DBNet hit survives only after local CJK recognition, while a
   multi-frame track requires temporal consensus.
4. Dense boundary rescan and the expanded small-text budget recover short and
   compact occurrences.
5. A 384-pixel all-frame closure resolves frame-exact presence and geometry for
   every seed track while recording line-like stroke regions that belong to no
   active track.
6. Those unassigned frames receive a bounded second high-resolution DBNet pass.
   Newly confirmed tracks are appended before provenance and a second all-frame
   closure regenerates final coverage.
7. Source/editor provenance is evaluated after discovery. Source panels and
   uncertain tracks remain fail-closed and preserve source pixels.
8. Blank-recognizer hardsub fallback requires high ink and balanced horizontal/
   vertical glyph energy on the same frame, preventing fabric/hair texture from
   borrowing unrelated evidence across frames.

## Encoded-output gate

`phase1_candidate_windows_v1.json` carries strong textness, completeness and
coverage-unassigned frame evidence into Phase 4 Output QA. Local full-frame CJK
OCR checks every isolated strong boundary and representative frames from
persistent candidates, including pixels outside known render tracks. A remaining
single-frame CJK detection blocks release unless hash-bound source evidence proves
it is intrinsic.

## Cost boundary

The 512/384 proxy passes inspect every frame. Expensive DBNet work remains
adaptive and bounded: normal candidate cadence is approximately 6 fps, residual
discovery is capped by duration, and encoded-output completeness QA has a fixed
memory-safe frame cap. Cache, checkpoint and source/recipe hashes preserve retry
and resume behavior.

## Artifacts

- `phase1_candidate_windows_v1.json`
- `phase1_track_coverage_v2.json`
- `phase1_event_metrics.json`
- `phase1_provenance_v3.json`
- `phase2_ocr_timeline.json`

`master_timeline.json` remains a compatibility projection and is never
overwritten by Phase 2.

## Validation boundary

The synthetic one-frame CJK and seedless-closure regressions pass. On the local
8.126-second smoke source, V27.1 completed in 24.41 seconds, ran the expensive
detector on 72/243 frames, reduced 129 noisy V27 tracks to one fail-closed
`UNCERTAIN` one-frame candidate, and emitted no automatic editor-removal track.
This is a smoke/contract result, not a claim of universal video support; the
frontend operator regression remains pending.
