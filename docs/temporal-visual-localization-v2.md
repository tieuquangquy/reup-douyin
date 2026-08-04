# Temporal Visual Localization V2

This is the production Analyze OCR path used by Final Review. It is not a
shadow/pilot workflow.

## Runtime binding

- Web: Final Review `Analyze OCR`
- API job: `ANALYZE_OCR`
- Workflow: `QUALITY_LOCALIZATION_V24_1`
- Phase 1 authority: `v58_candidate`, logical `STEP=1`, `PAD=1`
- Authority V3.6 full-duration: disabled
- Phase 2 provider: local PaddleOCR
- Default local model label: `ppocrv6-medium-det-rec`

## Temporal scan

Every decoded frame receives a 192-pixel lightweight luminance/edge probe.
Dual-prep DBNet runs on visual transitions and on a bounded periodic cadence
(three frames at normal fps, five frames at 50/60 fps; both remain below
0.1 seconds). Seed hits are collapsed into provisional temporal intervals.
Only interval boundaries, detector gaps, geometry jumps and transition
neighbours open dense `N-1/N/N+1` refinement. A 48% unique-heavy-frame guard
prevents persistent text from silently expanding the pass to the full video.

Dense UI anchors receive a separate bounded 1920-long-edge recovery pass for
small phone/app labels. This keeps logical STEP=1 timing authority while
avoiding full-duration high-resolution DBNet. The scan is checkpointed with
`temporal_visual_localization_v2_4`; checkpoints from the previous scan
policy are intentionally not reused.

## Provenance authority

Phase 1 assigns one classification to every final track:

- `EDITOR_OVERLAY`: OCR, review, translation, removal and Vietnamese overlay.
- `SOURCE_INTRINSIC`: preserve source pixels; never send to OCR/translation or
  render removal.
- `UNCERTAIN`: operator provenance decision in Final Review. The safe default is
  `PRESERVE_SOURCE`.

Detection is recall-first: readable source-scene candidates are retained until
provenance instead of being discarded by the legacy editor-only text gate.
Phone/app planes are classified as synchronized multi-row, multi-column panel
cohorts. Provenance is propagated both to compact members and to thin joined
rows/isolated control labels that overlap already-proven panel peers. Hardsub
geometry and tall editor captions are excluded from propagation, so an editor
caption over a phone screen remains localizable. Dense compact device panels,
audited scene labels and moving source-bound text are protected. A stable UI
navigation row fragmented into many short, near-identical boxes is also
protected when it is adjacent to a proven panel; a one-off subtitle cannot
inherit this rule. The output is
`visual_text_provenance_v2.json`, hash-bound to `master_timeline.json`.

After local text validation, preliminary provenance partitions source,
uncertain and editor candidates. Source and uncertain candidates keep their
detected timing/geometry and bypass editor-only content segmentation, ink
recovery and removal-boundary work. Only editor candidates pay those
post-processing costs; uncertain tracks remain fail-safe operator review.
Boundary QA strips are generated only for editor and uncertain tracks; source
tracks keep timeline/provenance evidence but do not pay the four-frame removal
boundary export cost.

`master_timeline.json` is written once by Phase 1 and is never overwritten by
Phase 2. Phase 2 writes `phase2_ocr_timeline.json` and carries protected source
tracks separately through its handoff.

## Render and QA

Phase 4 requires the exact master geometry partition:

`translated/localized + cover-only + protected source = master tracks`

Protected tracks are excluded from both cover and Vietnamese overlay authority.
Encoded-output QA performs a lightweight every-frame comparison in addition to
the existing sampled heavy OCR checks. It blocks:

- an active localization interval whose pixels were not changed (short CJK
  flash/missed edit);
- unexpected changes inside a protected source-intrinsic region.

The Final Review summary exposes provenance counts, protected-track count and
the provenance artifact path.
