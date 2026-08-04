# Phase 1 quality contract

**Status:** Closed — v58 operator PASS, 2026-07-26  
**Authority:** `MasterPhase1Extractor` → `master_timeline.json`  
**Scope:** Geometry/timing detection only. Cloud OCR, translation and render are downstream non-goals.

## Product invariants

1. Scan every source frame in the best-quality profile (`STEP=1`).
2. Keep pre-gate detection coverage in `text_frame_coverage.json`; later gates must not erase it.
3. A rejected one-hit candidate remains observable in `qa/uncertain_candidates.json`.
4. Track boundaries are verified against a multi-frame glyph template when positive/background evidence is separable. Otherwise refinement fails soft and retains the previous span.
5. Consecutive captions that share one inclusive boundary frame are not duplicate fragments. Fragment purge requires substantial temporal overlap.
6. Final hardsub geometry may use multi-frame neutral-glyph consensus. A color-only proposal cannot replace most DBNet evidence unless it is a wide, centered line proving an extreme empty side pad.
7. Geometry-stable tracks are segmented by normalized local-OCR fingerprints before boundary/ink refinement. A stable text change creates a new timeline row; an unsupported one-frame OCR glitch cannot create a row.
8. Local OCR is timing evidence only. Cloud OCR remains the downstream content authority.
9. `master_timeline.json` stays the downstream geometry SSOT. No Phase 2 per-frame geometry re-scan.
10. Raw pre-merge detector coverage is the final X authority for dense hardsubs. If final X is at least `1.8×` the median per-frame detector union over a dense span, X is reduced to that repeated detector core while ink-refined Y is preserved.
11. A coverage hit rejected by a strong local/geometry gate may explain a detector shadow only while a confirmed final hardsub is active in the same Y band. Without an active final hardsub, the raw hit remains a recall failure.
12. Screen position lock and readable OCR are not sufficient proof that a non-hardsub is editor-added. An isolated micro track needs independent editor-layout evidence (a concurrent non-compact editor-card anchor or a nearby temporal peer); otherwise it is excluded with audit reason `isolated_micro_source_text`. Hardsubs keep their separate line-geometry authority.
13. Final temporal reconciliation may trim a singleton outlier when one contiguous cluster has at least three hits and at least 70% of the evidence. It may extend a confirmed hardsub through at most four raw-coverage fade frames, but must stop before compatible evidence that continues as a new caption.
14. `frame_edge_box_review` is reserved for likely clipping inside `max(2 px, 0.25% frame width)` of the raster edge. A complete dense editor label with a safe margin is not uncertain solely because it sits in the outer 1% of the frame.
15. Latin-only OCR is source text by default. It may survive as an editor card only when a saturated solid-color panel and a non-overlapping temporal peer support the same layout locus; pure-Latin timing signatures then split changing cards.
16. A Latin-only in-scene label may survive with `semantic_role=semantic_scene_label` only when at least two stable labels coexist on the same layout axis, remain vertically separated, have dense multi-frame OCR support for at least 12 frames, and sit on coherent but visibly distinct background regions. A single watermark, labels inside one UI panel, and print attached to a moving object do not satisfy this gate.
17. Zero final tracks never become an automatic PASS. When no uncovered dense span, high-confidence rejected text, or uncertain track remains, Phase 1 creates a hash-bound `NO_TEXT` review candidate and waits for a complete-video operator decision.
18. A non-hardsub UI track may be removed as a nested detector fragment without OCR evidence only when it is fully time-contained by a same-role authority, lasts at most 35% as long, occupies at most 75% of the authority area, and at least 95% of its own box lies inside the authority box. Sequential transitions and longer-lived nested values remain separate. Every removal is audited under `nested_temporal_ui_fragment_guard`, and the scorer independently rejects stale artifacts that still contain such a pair.
19. Intro and outro risk windows run a bounded raw-frame DBNet profile (`960`, threshold `0.25`) in addition to the sensitive dual-prep profile. Its geometry is unioned before normal track confirmation and must pass the same local-text, provenance, boundary, crop and scorer gates. This recovers stylized title/endcard lines fragmented by the primary profile without introducing per-video coordinates or text exceptions.
20. Bottom-band residual coverage is reconciled after final temporal refinement. A missing track is recovered only from at least three locally recognized text frames; an unreadable fragment is classified as a shadow only while a confirmed caption host is active beside it. Every unresolved span remains explicit in `qa/before_after.json` and blocks automatic PASS.
21. Repeated dense evidence at the raster edge is recorded as `source_intrinsic_clip=true` and does not fail solely for touching the edge. Sparse edge evidence still receives `frame_edge_box_review`. Likewise, a left-aligned caption is not treated as an empty-left box unless repeated detector geometry proves substantial left padding and width inflation.
22. Perspective phone/app UI may establish provenance through a concurrent two-dimensional cohort of at least seven tracks with broad X/Y spread. This exempts supported micro UI values from the isolated-source guard; a lone appliance/package label remains rejected.
23. A text-bearing Phase 1 quality failure that is limited to geometry/provenance gates stops at `WAITING_PHASE1_GEOMETRY_OPERATOR_REVIEW`, not a generic execution failure. The review binds source, timeline, score, coverage, QA and visual evidence hashes. Operator decisions are limited to `APPROVE_GEOMETRY`, `EDIT_GEOMETRY`, `REJECT_TRACK`, and `EXPLAIN_SHADOW`; none authorizes OCR text.
24. Approved geometry is materialized in `phase1_geometry_overrides.json` without overwriting `master_timeline.json`. Phase 2 applies the effective geometry in memory, discards stale crops for edited boxes, and records the materialization reference. Any source/evidence/master hash drift returns the case to operator review.

## Boundary evidence

Each timeline row includes `boundary_evidence`:

- `status`: `confirmed` or `uncertain`
- `reasons`: review reasons, never silent drops
- observed first/last hit frame
- hit density and maximum internal gap
- normalized box width/height
- confidence

Template refinement is audited under:

```text
qa/before_after.json → boundary_refinement
qa/summary.json → finalize.boundary_refinement
```

The verifier uses confirmed hit frames to build a high-frequency glyph template. Frames just outside the prior padded span calibrate the local background. It only changes onset/offset when positive and negative similarity are sufficiently separated.

## Content-aware timing evidence

Local recognition runs in batches over every frame inside each surviving geometry track. Its normalized CJK/digit signature is clustered with these fail-soft rules:

- a cluster needs support from at least two frames;
- one-frame substitutions/blanks do not create a segment;
- reliable clusters must be temporally ordered and non-overlapping;
- a single cluster can trim detector-only edge frames only with dense recognition and a clear blank edge;
- each accepted segment rebuilds its box/keyframe from detector evidence inside that content span.

Audit paths:

```text
qa/before_after.json → content_segmentation
qa/summary.json → finalize.content_segmentation
```

## Geometry evidence

Hardsub geometry remains recall-first:

1. DBNet stable seed.
2. Stroke/edge extend and trim.
3. Near-neutral bright glyph components with character-like shape.
4. Consensus across at least two frames.
5. Fail-soft gate against clipping valid DBNet evidence.

The neutral-glyph pass targets white/dark-outline editor captions and rejects saturated wood/food texture. It is an optional final refinement, not a universal text detector.

## QA artifacts

| Artifact | Purpose |
|----------|---------|
| `master_timeline.json` | Final geometry/timing authority |
| `text_frame_coverage.json` | Every pre-gate frame with a plausible text hit |
| `qa/uncertain_candidates.json` | One-hit candidates retained for review |
| `qa/quality_report.json` | Confirmed/uncertain counts and per-track evidence |
| `qa/before_after.json` | Split, gate, purge and boundary audit |
| `qa/overlays/*.jpg` | One visual keyframe per final track |
| `qa/boundaries/*.jpg` | Full-frame start−1/start/end/end+1 review strip |
| `qa/boundary_crops/*.jpg` | Zoomed start−1/start/end/end+1 box strip |

Additional gate artifacts are `phase1_score.json` (durable atomic scorer output), `phase1_no_text_review.json` (self-hashed zero-track review candidate), and `phase1_no_text_approval.json` (a separate self-hashed operator decision that automation never creates). Text-bearing geometry exceptions use `phase1_geometry_review.json`, `phase1_geometry_approval.json`, and `phase1_geometry_overrides.json`; automation may prepare the review but never writes the approval decision.

## V22.1 remediation boundary

The approved `PHASE1_REMEDIATION_PROPOSAL_APPROVED_V22_1` change set adds residual-caption recovery, role-drift reconciliation, evidence-aware edge/left alignment handling, perspective-UI provenance, and the durable geometry operator gate. It does not change the locked `v58_candidate`, `STEP=1`, `PAD=1`, local-OCR default, or `authority_v3_6_full_duration=false` recipe. V22 becomes a development set after this implementation; a new untouched V23 corpus is required for the next generalization claim.

`qa/overlays` is track-centric; it is not proof of every boundary frame. Exact onset/end review should use the boundary audit and neighboring frames.

## Closed Random-5 baseline

```text
apps/api/tmp_phase1_random5_final_v58/  # rerun video 750... after recall correction
apps/api/tmp_phase1_random5_final_v55/  # provenance rerun video 747...
apps/api/tmp_phase1_random5_final_v54/  # unchanged videos 760..., 754..., 763...
```

- The previous v54 5/5 claim was revoked after operator evidence showed source/device text in the editor-only SSOT.
- v55 reran the provenance-affected videos. Operator then exposed two missing measured ingredient labels in `750...`; that video now uses v58. The other three v54 outputs are unchanged.
- Mixed scoreboard is 5/5 scorer PASS, all final tracks confirmed, `uncertain_tracks=0`; this is evidence, not operator sign-off.
- No dense uncovered hardsub span, no final hardsub at least `1.8×` its detector core, no duplicate pair, and no missing crop/keyframe.
- Final track counts by video: 34, 35, 50, 71, and 49.
- Video `7472735913513078057` removed three isolated source/scene candidates. Video `7503536530008722698` keeps the printed stove instruction out, restores `150g里脊肉` and `250g虾仁`, restores the repeated left-edge evidence for `三个鸡蛋`, and removes the two-hit bottom hardsub shadow.
- The raw dense-coverage guard corrected one real balloon: video `7472735913513078057`, span `196–219`, X `[438,1414] → [812.85,1113.15]`.
- Video `7503536530008722698` exposed food/pan detector shadows. They remain rejected by `not_overlay_geometry` / `local_text_reject`; the scorer now accepts them only beside an active confirmed caption in the same band.
- Full regressions pass: 79 extractor tests, 38 text-gate tests, 44 PASS-contract tests, 8 scorer tests, and 98 discovered `test_phase1_*.py` tests.
- The scorer now fails when local OCR reads at least two CJK glyphs with confidence `>=0.90` but the semantic gate rejects the track. This makes the old v55 `750...` output fail instead of silently losing two labels.
- Sequential-frame recall QA for the corrected ingredient scene is in `apps/api/tmp_phase1_random5_final_v58/7503536530008722698/qa/frame_recall_sequential/`. Do not use OpenCV random frame seek for exact boundary review on this MP4; it returned frame `N-1` while sequential decode matched pipeline indexing.

Detailed scoreboard and resume instructions: [`handoff-phase1-random5.md`](./handoff-phase1-random5.md).

This baseline is **operator PASS** and frozen for Phase 2. Future Phase 1 changes require new geometry/recall evidence and regression coverage.

## v58 closed baseline regression

The closed baseline keeps production at `STEP=1`, `PAD=1` and does not use Authority V3.6. Fresh outputs are:

```text
apps/api/tmp_phase1_random5_final_reconcile_v58/            # 747, 760, 750, 763
apps/api/tmp_phase1_random5_final_reconcile_v58_edge_fix/   # 754
apps/api/tmp_phase1_v58_final_reconcile_test_7450099336215579915/
```

- Random-5 rerun: 5/5 scorer PASS, 239/239 confirmed, 0 uncertain; track counts remain `34, 35, 50, 71, 49`.
- Four Random-5 videos required no final temporal change. Video `7503536530008722698` extends one confirmed fade tail by two frames (`1091 → 1093`); boundary review shows the next caption starts at frame 1094.
- Holdout `7450099336215579915` trims one sparse singleton outlier (`0–11 → 0–2`) and extends one fade tail (`230 → 233`), then scorer PASSes with 36/36 confirmed.
- The dense left ingredient label in `7543241784286465306` exposed an over-broad 1% frame-edge review threshold. The clipping-risk strip is now `max(2 px, 0.25% width)`; actual edge boxes remain uncertain.
- Phase 2 bridge contract tests PASS. `scripts/run_phase2_only.py --mock` now guarantees the mock OCR path and configures UTF-8 stdout for CJK previews on Windows.
- The first manual bridge diagnostic used the configured provider path before `--mock` existed; it completed artifact writes but its preview crashed on CP1252. No secret was printed. The fixed mock smoke exits 0 and does not call the provider.

## Portrait editor-card validation (non-locking)

The targeted run `pipeline_v8_portrait_latin_card_timing_20260727` validates the general Latin editor-card fix without changing the locked recipe:

- `public_pd_nasa_spectra_vertical`: 43/43 confirmed tracks, zero uncertain, scorer PASS, and no uncovered dense span;
- local OCR: 34/43 raw non-empty; exact visual review approves all 43 content objects after 13 corrections/fills, and Phase 2 is ready for Phase 3;
- `public_cc0_flameless_candle`: all 217 decoded frames reviewed and `NO_TEXT_OPERATOR_APPROVED`;
- `public_pd_nasa_radio_signal_portrait`: all 149 decoded frames reviewed and `TEXT_PRESENT_PHASE1_REJECTED` because `Ionosphere` and `Earth` are visible throughout despite a zero-track timeline;
- scorer replay on the ten-case corpus v4 baseline: 10/10 PASS, 339 total tracks;
- focused regression: 41 text-gate + 91 extractor + 12 scorer + 3 no-text contract + 5 batch runner + 2 reporter tests PASS.

This resolves the spectra editor-card extraction and OCR gates, not universal portrait support. The radio semantic-label recall failure remains immutable in v8 as historical evidence. Corpus v4 and the current recipe pointer remain authoritative.

## Semantic scene-label validation (non-locking)

The targeted run `pipeline_v9_semantic_scene_label_20260727` validates a general semantic-label gate without enabling Authority V3.6 or changing `v58_candidate`, `STEP=1`, `PAD=1`:

- `public_pd_nasa_radio_signal_portrait`: 2/2 confirmed tracks, both audited as `semantic_scene_label`; exact Phase 2 review approves `Ionosphere` and `Earth`, and handoff is `READY_FOR_PHASE3`;
- `public_pd_nasa_spectra_vertical`: all 43 prior tracks remain confirmed; four real graph labels (`Continuous`, `Emission`, `Absorption`, `Wavelength`) receive the semantic role while the editor-card rule does not regress;
- `public_cc0_flameless_candle`: zero tracks and zero semantic candidates; the source-hash-bound 217-frame review remains `NO_TEXT_OPERATOR_APPROVED`;
- scorer replay remains 10/10 PASS on corpus v4;
- regression tests pass: 91 extractor, 43 text-gate, 13 scorer, 10 Phase-2 contract, 6 Phase-2 review/runner, and 8 batch-runner tests.

Phase 2 writes only `phase2_ocr_timeline.json` and downstream artifacts referencing the exact Phase-1 timeline SHA-256. It never overwrites `master_timeline.json`. The v9 batch used `--stop-after-phase2`, so no Phase 3 artifact was created. This closes `RADIO_SIGNAL_SEMANTIC_LABEL_RECALL`; it does not claim universal portrait support or replace the locked corpus-v4 recipe.

## UI-grid peer guard and controlled-pilot lock

The v10-v16 evidence closes the merged nutrition-cell incident without treating ordinary word spacing as a table boundary:

- v10 is immutable failure evidence: `441 + 脂肪` and `千卡 + 碳水化合物` remained merged;
- v11 is partial-fix evidence: the text cells split, but the standalone `441` failed the local gate;
- v12 restores the numeric child and produces 37/37 confirmed tracks for `7472735913513078057`, with exact Phase 2 review and `READY_FOR_PHASE3`;
- v13 exposed a real counter-regression: the first ink-gutter rule split English spectra captions into word fragments (52 tracks from the prior 43-track baseline);
- v14 requires at least seven dense tracks with temporal IoU `>= 0.80`, two-dimensional panel spread, and stable hit density before a blank gutter can become a UI-cell boundary. Spectra retains all 43 prior crops byte-for-byte and adds only the real atomic-number labels `88` and `89`; `745...` and `747...` retain 42 and 37 valid tracks respectively;
- v16 refreshes the three legacy nutrition-grid cases that the stricter scorer correctly rejects in immutable v4 artifacts. Fresh counts are `37`, `53`, and `51`, with unchanged hardsub counts and zero uncertain or merged-grid tracks.

The current-code composite scorer is 10/10 PASS. The five-case Phase 1/2 lock batch is `pipeline_v15_recipe_lock_candidate_20260727`: four text-bearing cases are `READY_FOR_PHASE3`, the 217-frame candle control is `NO_TEXT_OPERATOR_APPROVED`, operator review objects are zero, and open incidents are zero. Exact OCR carry-forward is allowed only for byte-identical crop SHA-256 values; every new crop requires an explicit override and a self-hashed decision set.

The controlled-pilot recipe is content-addressed as `996324e5b5c3925fa0b5d0079ea4f96e8ae1884fb95dc385609f855083bb22a9`. It keeps `v58_candidate`, `STEP=1`, `PAD=1`, local OCR, and `authority_v3_6_full_duration=false`. It does not claim universal input support.

## Known limitations

- No computer-vision-only pipeline can guarantee 100% on unseen videos without labeled ground truth.
- With only one flattened raster video, static source print and a static editor overlay can be observationally identical. A true 100% provenance guarantee requires either the clean pre-edit source/layer metadata or a fail-closed review path for ambiguous tracks; screen lock and OCR confidence alone must never be presented as proof.
- `box_coords` remains one static box per track; animated/moving text will eventually need `box_keyframes` or per-frame masks.
- Neutral-glyph refinement is intentionally conservative for non-white/stylized text.
- Local recognition fails soft when content clusters are weak or interleaved; those tracks retain their prior timing and still require QA.
- ONNX Runtime logs dynamic-output shape warnings for the current DBNet model; inference succeeds, but model metadata/export should be cleaned separately.
- Production E2E persists the timeline/keyframes; dedicated Phase 1 runs remain the full QA artifact path.
