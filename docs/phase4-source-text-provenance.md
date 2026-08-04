# Phase 4 source-text provenance

## Product rule

- `EDITOR_OVERLAY_TEXT`: OCR, translate, cover and render in Vietnamese.
- `SOURCE_SCENE_TEXT`: text naturally present on a filmed phone, appliance, package or physical scene; keep source pixels untouched.
- Ambiguous evidence must remain review-required. Density, OCR confidence or screen lock alone is not proof that text was added by an editor.

## Runtime authority

Phase 4 does not overwrite `master_timeline.json` or `phase4_render_input.json`. It appends hash-bound operations to versioned visual-remediation artifacts and moves `phase4_visual_remediation_active.json` atomically.

`CLASSIFY_SOURCE_SCENE_TEXT_REGION` removes only hash-verified, non-hardsub source-plane tracks from the effective render contract. Editor hardsubs and generic caption shapes remain active. `EXTEND_SOURCE_SCENE_TEXT_REGION` can extend a previously classified scene epoch only when both the old and replacement region hashes match.

Output QA keeps all local-OCR detections in `raw_detections`. CJK inside an active source-scene region is recorded under `source_scene_protected_exclusions`; it is still blocking when it materially overlaps the source cover geometry of an active editor track. Layout safe areas are placement constraints and are not source-text cover authority.

## Dense device-plane evidence

The automatic path starts from a bounded dense UI cohort and may expand to temporally connected small scene labels. It excludes:

- explicit `kind=hardsub` tracks;
- generic editor caption shapes;
- bottom caption-shaped tracks carrying a hardsub role;
- large title-like geometry.

Provenance v3 also resolves legacy role conflicts. A small track with `source_kind=ui` and `micro_ui=true` remains source-scene text even if an older OCR/remediation step attached a `hardsub` role. Positive filmed-UI evidence takes precedence over that inherited role; otherwise a source label can be translated for part of its epoch and visibly revert to Chinese when the mistaken render track ends.

Case-specific continuation, such as a phone disappearing and reappearing later, must be recorded as a versioned region extension with an evidence frame. It must not become a global ignore rule.

## Caption residual handling

The default editor-overlay lane uses one cover style for captions, compact labels and titles: `editor_overlay_spatial_telea_full_roi_v1`. Every approved editor track is cleaned independently on each source frame with `spatial_telea_r9` over the complete approved cover ROI. The renderer does not reuse static plates, optical-flow plates or glyph-only masks in this lane. This keeps texture and edge treatment consistent when adjacent labels have different OCR roles. `SOURCE_SCENE_TEXT` remains outside the lane and its pixels are preserved.

For every editor overlay, cover and text are now one authority lane: `cover_aligned` uses the approved cover ROI as the placement anchor and never falls back to the dense responsive grid. UI typography may expand locally around the same center when Vietnamese needs more width than the Chinese source; it cannot move to another lane. The cover remains bounded by the track damage budget. Short titles keep their expanded, shadow-covering ROI but use the same spatial Telea method as every other editor overlay.

Encoded-output QA scans editor-caption epochs at a bounded 10-fps cadence in addition to transition samples. OCR detections that are mostly Latin Vietnamese with at most two CJK characters are retained as evidence but classified as an editor-caption OCR false positive only when their geometry and text similarity match the approved Vietnamese track. Caption on/off boundary frames are reported but excluded from flicker blocking; stable-frame flicker remains fail-closed.

The validated v22.64 boundary correction keeps this distinction intact: when a
top editor note crosses a scene cut, a narrow hash-bound cover-only component
may be appended for an observed residual glyph (without changing the OCR
timeline or source-scene tracks). The accepted main cover and Vietnamese safe
area stay unchanged. This avoids both a single transition-frame Chinese flash
and the visible rectangular patch caused by widening one cover across a
high-contrast scene boundary.

## Known limit

A flattened video cannot always prove source/editor provenance from pixels alone. Clean pre-edit media or layer metadata is the only general proof. Unsupported or contradictory cases must stop for review rather than auto-translate scene text.
