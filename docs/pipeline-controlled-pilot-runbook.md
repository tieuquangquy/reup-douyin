# Controlled Pipeline Pilot Runbook

This runbook covers the locked local-first recipe from the regression corpus through canonical DB export state. It does not authorize external publishing or bypass operator checkpoints.

## Build the regression corpus

Run from `apps/api`:

```powershell
python -m scripts.build_pipeline_regression_corpus <video-directory> ..\..\docs\pipeline-regression-corpus-v1.json --ids <video-id-1> <video-id-2> <video-id-n> --phase1-root <phase1-artifact-root> --max-duration 60
```

When selected source files live in more than one real-video staging directory, repeat `--additional-input-dir <directory>`. The builder resolves each requested ID across those directories without copying or transforming the source video.

The corpus records source-relative paths, probe data, visual samples, coverage dimensions, and declared gaps. A corpus is not universal evidence when portrait, low resolution, no-audio, lighting, motion, or text-density dimensions remain uncovered.

Public gap fixtures that exist only to validate Phase 1 through visual localization must declare `regression_scope: VISUAL_LOCALIZATION_ONLY`. They become terminal only after a current, hash-bound visual approval with passing visual Output QA. They must not be counted as full end-to-end audio, export, DB-handoff, or publishing evidence. Cases without this field default to `FULL_E2E` and retain every downstream audio/final/export gate.

## Run the Phase 1 and Phase 2 regression

```powershell
python -m scripts.run_pipeline_batch_regression ..\..\docs\pipeline-regression-corpus-v1.json regression_runs\<run-id> --phase2-provider local --stop-after-phase2
python -m scripts.build_pipeline_regression_report regression_runs\<run-id>
```

The runner is resumable and keeps per-stage logs. Existing valid stage artifacts are reused; failed or incomplete stages can be rerun. Use `--stop-after-phase2` for a Phase-1/2 validation run: it persists the current gate and cannot execute Phase 3+. Omit the flag only when the requested regression explicitly includes downstream stages. A result of `PASS_TO_OPERATOR_GATES` means automated execution is healthy only through local OCR. It does not mean OCR, translation, visual, audio, final, metadata, or rights review has been approved.

The latest controlled run `pipeline_v4_20260727_720p_guard` produced:

- 10/10 Phase 1 PASS;
- 10/10 Phase 2 local OCR execution PASS;
- 336 OCR objects requiring exact operator review;
- 0/10 ready for Phase 3 because the OCR operator gate is intentionally preserved;
- real, unmodified coverage for 1080p-or-higher and 720p-or-lower landscape inputs;
- remaining real-video gaps for portrait, low/medium motion, and absent audio.

The authoritative report is `apps/api/regression_runs/pipeline_v4_20260727_720p_guard/pipeline_regression_report.json`. Its `regression_incidents.json` records the resolution-aware scorer, the post-refinement texture guard, and the correction that `unknown` text density is a missing-evidence state rather than a required representative class.

### 720p holdout status

Corpus v3 originally exposed one unresolved 1280x720 texture false positive. Corpus v4 preserves both real, unmodified holdouts and resolves the incident without a video-specific rule:

- `7429689966633979175`: 16 tracks, 14 hardsubs, zero uncertain tracks, Phase 1 PASS and Phase 2 execution PASS;
- `7473848630424702271`: the 46-track negative control remains unchanged, with Phase 1 PASS and Phase 2 execution PASS;
- the scorer reads 1280x720 from `text_frame_coverage.json` rather than assuming 1920x1080;
- a post-refinement guard acts only on sparse compact mid-label/UI candidates and requires stable detector-backed OCR consensus;
- stable OCR alone cannot override an independent low-detail saturated-texture veto;
- recognizer failure fails soft to operator review.

The guard thresholds and positive/negative-control evidence are recorded in `apps/api/regression_runs/pipeline_v4_20260727_720p_guard/visual_guard_validation.json`. The v3 failure remains immutable historical evidence; v4 is the accepted controlled-pilot evidence. This closes the 720p corpus gap, not universal video support.

### Discover remaining real-video gaps

Run the source-only scanner from `apps/api`:

```powershell
python -m scripts.discover_pipeline_gap_candidates ..\..\docs\pipeline-gap-discovery-v1.json --corpus ..\..\docs\pipeline-regression-corpus-v4.json --source-root ..\..\.douyin_profiles --source-root ..\worker\data\storage --source-root data\storage --source-root ..\..\data\storage --max-duration 60
```

The scanner accepts only original-source paths containing `raw`, `download_staging`, or `regression_gap_staging`; rejects render/final/output/export trees; handles Windows extended-length paths at the I/O boundary; deduplicates exact bytes by SHA-256; and never transforms a source to manufacture a gap.

The immutable baseline `docs/pipeline-gap-discovery-v1.json` inspected 108 trusted files, reduced them to 104 unique SHA-256 sources, and found no remaining-gap candidates. Public-source intake is recorded separately in `docs/pipeline-public-regression-sources-v1.json`; these original bytes are restricted to local regression and do not authorize external reup or publishing.

`docs/pipeline-gap-discovery-v3.json` scans the staged public sources without transcoding and finds real candidates for portrait, low motion, medium motion, and absent audio, including real `portrait + low-motion + no-audio` controls. A discovery match is intake evidence only: do not remove corpus gaps until the candidate passes Phase 1, local Phase 2 OCR, and exact operator review under the same locked recipe. The stricter `portrait + medium-motion + audio-present` intake profile is still unfilled and must not be reported as covered.

### Public gap-candidate Phase 1 result

The public-source candidate regression remains non-locking:

- `pipeline_v5_public_gap_candidates_20260727` is immutable failure evidence for the former portrait caption-recall incident on `public_pd_nasa_spectra_vertical`;
- `pipeline_v8_portrait_latin_card_timing_20260727` resolves that incident with a general editor-card rule: 43/43 tracks confirmed, zero uncertain, no uncovered dense span, and Phase 1 scorer PASS;
- local Phase 2 OCR on the portrait case produced non-empty text for 34/43 objects with the explicit `ppocrv6-medium-det-8e0f56fb_rec-e5a92bcb_paddleocr-3.8.0.dev11` model identity;
- all 43 portrait objects received user-authorized delegated visual review: 30 approved unchanged, 13 corrected/filled from visible crops, and the Phase 2 handoff is `READY_FOR_PHASE3`;
- a complete 149-frame review rejects `public_pd_nasa_radio_signal_portrait` as `TEXT_PRESENT_PHASE1_REJECTED` because `Ionosphere` and `Earth` are visible throughout while Phase 1 returns zero tracks;
- a complete 217-frame review approves `public_cc0_flameless_candle` as `NO_TEXT_OPERATOR_APPROVED`;
- each no-text candidate is bound to the current timeline, score, coverage and quality-report hashes; no automated decision is permitted and stale or tampered approvals fail closed;
- the v8 validation bundle also reuses two accepted Chinese baselines, while a direct scorer replay remains 10/10 PASS across corpus v4;
- the current corpus v4 and locked recipe remain authoritative.

Evidence is stored in `apps/api/regression_runs/pipeline_v8_portrait_latin_card_timing_20260727/pipeline_regression_report.json` and `regression_incidents.json`. The targeted corpus is `docs/pipeline-regression-corpus-v7-portrait-fix-validation.json`. This run remains immutable historical failure evidence for radio semantic-label recall.

The follow-up `pipeline_v9_semantic_scene_label_20260727` resolves that incident with a general paired-label rule:

- Radio: 2/2 confirmed semantic tracks; Phase 2 exact review returns `Ionosphere` and `Earth`; handoff `READY_FOR_PHASE3`.
- Spectra: 43/43 confirmed with no editor-card regression; four graph labels carry `semantic_scene_label` and are exact-review approved.
- Candle: zero semantic candidates and `NO_TEXT_OPERATOR_APPROVED` after complete-video review.
- Ten-case corpus-v4 scorer replay: 10/10 PASS.
- Five-case targeted batch: `PASS_TO_OPERATOR_GATES`, zero failed cases, two reused Chinese baselines still waiting for their existing OCR operator gates.
- Local OCR identity: `ppocrv6-medium-det-8e0f56fb_rec-e5a92bcb_paddleocr-3.8.0.dev11-g2661c7c0e`.

The v9 corpus is `docs/pipeline-regression-corpus-v9-semantic-scene-label.json`; report and incidents are under `apps/api/regression_runs/pipeline_v9_semantic_scene_label_20260727`. The run intentionally stops after Phase 2 and does not lock a replacement recipe. Corpus v4 and the current recipe pointer remain authoritative until the full lock workflow is explicitly approved.

### UI-grid closure and replacement recipe

`pipeline_v13_recipe_lock_candidate_20260727` is preserved as failure evidence because a whitespace-only ink split fragmented natural Latin captions. The replacement guard requires stable simultaneous peers distributed across both axes and temporal IoU `>= 0.80`; it never treats a lone sentence's spaces as sufficient grid evidence.

Final evidence is split by purpose:

- `pipeline_v14_grid_peer_guard_20260727`: five fresh source runs; spectra 45 tracks (43 prior byte-identical crops plus real labels `88`/`89`), radio 2 semantic labels, candle 0 tracks with source-hash-bound 217-frame approval, `745...` 42 tracks, and `747...` 37 tracks;
- `pipeline_v15_recipe_lock_candidate_20260727`: consolidated Phase 1/2 batch with 0 failed cases, 0 operator touches, 0 OCR review objects, and 0 open incidents;
- `pipeline_v16_legacy_ui_grid_refresh_20260727`: fresh current-code evidence for the three legacy v4 artifacts that correctly fail the new over-merge scorer;
- composite current-code scorer: 10/10 PASS, recorded in the self-hashed `docs/pipeline-phase1-composite-v16.json`, while the immutable pre-fix v4 artifacts remain unchanged as historical evidence.

The Phase-1/2 replacement recipe remains preserved at `docs/pipeline-recipes/pipeline_recipe_996324e5b5c3925fa0b5d0079ea4f96e8ae1884fb95dc385609f855083bb22a9.json`, and the V20 lock remains immutable historical evidence at `pipeline_recipe_42728388c79dd27207c2853c380ff2ac40dc5b557ab44d37d0ccb4187c06bede.json`. The V21 controlled-pilot lock remains immutable historical evidence at `pipeline_recipe_6a504e9c62f64a3f7f834429645edcd8990fc0f312ca0178e42e0ffaf8cbe8db.json`; it binds corpus `pipeline-regression-corpus-v21-e2e-expansion.json`, Phase-1/2 report SHA `8b5540b32f03f88f86e9dcca6de67048e04966bcda35b8a34e23262af990ac7a`, and scoped E2E report SHA `06e2f047606ca65c9ebfc15c35c5e03f1b79c141a1855773404d89e18f5d2678`. The lock accepts Phase 2 execution or a hash-valid operator-approved NO_TEXT bypass; it never runs OCR merely to satisfy counts on a no-text control.

V20 closes 3/3 included food-video cases through encoded final QA, metadata/rights/manual-export boundaries and retry-safe canonical DB handoff. It also locks the source-intrinsic residual-CJK v2 guard, measured Silero no-dialogue source-audio authority, and two-pass narration-only loudness with AAC true-peak headroom. This is supplementary end-to-end evidence: declared corpus gaps and `universal_video_support=false` remain unchanged.

V21 accepts all 9 corpus cases through their declared scope with zero failed cases, zero open incidents and zero remaining operator touches: 7 `FULL_E2E`/no-text-control cases plus 2 explicitly scoped `VISUAL_LOCALIZATION_ONLY` NASA gap fixtures. The scope override is recorded in the self-hashed `regression_scope_manifest.json`; the original corpus identity remains unchanged. Three included cases provide full retry-safe DB handoff evidence, while six cases are excluded from the E2E claim because they are visual-only, no-text controls, or lack canonical DB handoff. Therefore `included_cases_end_to_end_pass=true`, but `full_batch_end_to_end_pass=false` and `universal_video_support=false`. V21 also locks residual-CJK policy `source_intrinsic_cjk_v6` and monotonic legacy audio-mix reconciliation that fails closed on any input, recipe, final-render or approval hash drift.

The current V22.3 candidate advances residual-CJK QA to `source_intrinsic_cjk_v7`, which reserves encoded-output samples for post-end boundaries and keeps a source-confirmed trailing residual blocking. This remains a candidate until its recipe is explicitly locked.

V22.1 is the current controlled-pilot pointer: `pipeline_recipe_c60a27e2fc756607edfcded77c4774c05e5ebebc3c511f1181b9527630d027ac.json`. It binds fresh-holdout corpus SHA `288b085a8753b7f17962da81a33e5128affa63783d7a4f00eea19b8e2f03a368`, refreshed regression report SHA `3d15dafde98dc165475b5a507c40ab9644c36cbc0bfb61192af756ed37eb0648`, and Phase-4-preflight closeout SHA `ac819ab275bca5cf7f6f1b6196f9df0e7dad21635267d32c9606e25b7f9ec054`. All 6 cases are `READY_FOR_PHASE4` with zero blocking residual CJK, collision, overflow, clamp, open incident, proposal or remaining operator touch. This lock intentionally has no E2E report: audio authority, final render, encoded-output QA and canonical DB handoff remain the next boundary, so `full_batch_end_to_end_pass=false` and `universal_video_support=false`.

Prepare a read-only review pack from `apps/api` without writing any decision:

```powershell
python -m scripts.prepare_pipeline_operator_review regression_runs\pipeline_v8_portrait_latin_card_timing_20260727 --case-id local_public_pd_nasa_spectra_vertical --case-id local_public_pd_nasa_radio_signal_portrait --case-id local_public_cc0_flameless_candle
```

The generated `OPERATOR_REVIEW_PACK.md` links the two complete source videos and every crop/keyframe/overlay/boundary for the 43 spectra OCR objects. Its JSON companion is self-hashed. `NO_TEXT` review v2 binds the exact source-video SHA-256 in addition to Phase-1 timeline, score, coverage, and quality evidence, so replacing the source bytes makes an existing approval stale.

### V23 hardening candidate and current batch evidence

The latest hardening changes were first recorded as a non-locking candidate,
then locked after the six-case E2E boundary completed:

- Candidate: `docs/pipeline-recipes/pipeline_recipe_candidate_v23.json`;
- Candidate SHA-256: `90379f8ffa9c35cdf3f1a2ffea973715fcd65085f05cf8b6dd3f7ff5b21bb08a`;
- Final regression fixture: `docs/pipeline-final-regression-fixtures-v23.json`,
  fixture SHA `0f029a691f2eea3200b09ce5426b4362957d4b419b25647b0690b7dd31118b0a`;
- Fixture validation: 1/1 PASS, report SHA
  `702fecde44cb16be9fed110ab015a15cc1a864067eaec1146982c56c25b518fb`;
- Fresh-holdout batch: 6/6 Phase 1 execution, 6/6 Phase 2 execution, 0 failed;
  report SHA `cba94bd965ccaf9024a779c9186e9703558fe9b3e70a5888e7c05087da613374`;
- Full selected batch after DB handoff: 6/6 PASS, 6/6 retry-safe reuse,
  zero external publish calls; report SHA
  `13455c7af40dce7b8f47c379b7c13c81495e3924e0e99a5debce573cb84d4e3b`;
- Locked recipe: `pipeline_recipe_5d862cc2e5478bce54b45f996b25f40ebb029014c1128f8cd6d25a0f1ac9064e.json`.

V23 records `phase4_role_policy_v10`, source-relative dense-group layout,
semantic render deduplication, operator/hash-bound source-intrinsic moving-object
regions, and unity background-stem gain before loudness normalization. The
recipe is `LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS`: all selected-case rights and
DB boundaries are complete, but portrait/VFR/low-resolution/lighting/motion/
audio/text-density coverage gaps remain. `universal_video_support` therefore
remains false.

Prepare the remaining rights/music gate without recording a decision:

```powershell
python -m scripts.prepare_pipeline_rights_review `
  regression_runs\pipeline_v22_remediation_v22_1_20260729
```

The preserved pack validated all source/final/package hashes before the three
operator decisions were recorded. Its review-pack SHA is
`973013a69fb579c04d16f00000fab2c28e66672a98dff4ad711f3a1e423624e8`.
The pack itself remains read-only and never creates an external-publish
authorization.

### V24 fresh gap-closure corpus

`docs/pipeline-regression-corpus-v24-gap-closure.json` is a seven-source,
original-bytes corpus built with `--fresh-phase1`. Prior artifacts are used only
to classify text density; every selected video runs Phase 1 again from source.
The corpus covers landscape/portrait, 1080p/720p-or-lower, CFR/VFR,
above/below-30fps, every duration band, light/dark/mixed lighting,
low/medium/high motion, audio present/absent, and light/medium/dense text. Its
declared `real_video_gaps` is empty and corpus SHA is
`5b9685f04ebc2aa76f29798936076ab9403ea23948519bb2922b4709316c38cd`.

The fresh run is `apps/api/regression_runs/pipeline_v24_gap_closure_20260801`:

- 7/7 Phase 1 executions completed; 5 scorer PASS plus 2 hash-bound
  operator-approved NO_TEXT controls;
- 5/5 text-bearing cases completed local OCR and all 160 decisions are
  operator-approved; the two no-text controls are also approved;
- Phase 1 took `2840.28s` total, `313.05s` median and `978.93s` max;
- Phase 2 took `148.73s` total;
- no case failed and no external platform boundary was called;
- regression report SHA:
  `1d71ef352555a47b45a996645e9a52d14b27320d99d077eec8d4747f488783c1`;
- operator review-pack SHA:
  `56b2ae707702a703952934f726a6d3e5df1604670f611d749658d3673f88bddb`;
- Phase-2 proposal SHA:
  `01f9ca10b0423dfb4b22ae93d61e6ee7a3b72b050a83e6c852f6502fc0ae6b2b`.

Exact-crop comparison against V21 accepted reviews found 128/160 objects eligible
for carry-forward without fuzzy matching. The remaining fresh review surface is
32 objects: spectra 2, radio 2, 720p holdout 5, `745...` 23, and `754...` 0.
Reference proposals remain non-authoritative until the operator confirms them;
their per-case hashes are stored beside each V24 case as
`phase2_review_proposal_reference_v21.json`. The aggregate reference index SHA
is `c9d5fc7bdaeacd1bd82898a72ae63f581741257fa698c7a4a6f25d92874c7250`.
All 160 objects now have a proposed decision: 125 unchanged approvals and 35
edits. Four formerly empty local-OCR rows use explicit V21-reviewed suggestions
and remain part of the 32-row fresh operator-review surface.

Empty metadata gaps are intake coverage, not yet accepted gap closure. Do not
widen V23 claims from metadata alone. V24 now has clean Phase-1/2 acceptance,
but five Phase-3 translation proposals still require operator review.

The two NASA public fixtures are bound to `VISUAL_LOCALIZATION_ONLY` by scope
manifest SHA `fb6abdf47290886ddf96b35d2068f174e122c240ff551c956f79b0d6673f34b6`.
They cannot contribute audio, DB handoff or publish evidence. Phase 3 generated
128 translation review objects across five text-bearing cases, with zero
translation failures, 128 recommended approvals, one quality flag and batch
review SHA `1e5815ffcfbfc02c50371d1f74b669d9af30315dfabe56a6890d9e3f1db383d0`.

## Lock the recipe

Only lock after reviewing the corpus gaps and regression report:

```powershell
python -m scripts.lock_pipeline_recipe ..\..\docs\pipeline-regression-corpus-v1.json regression_runs\<run-id>\pipeline_regression_report.json ..\..\docs\pipeline-recipes --operator <operator-id>
```

When the controlled batch is also accepted through Phase 4 preflight, create a self-hashed closeout and bind it to a labeled recipe without claiming final-render E2E:

```powershell
python -m scripts.build_pipeline_regression_closeout regression_runs\<run-id>
python -m scripts.lock_pipeline_recipe `
  ..\..\docs\pipeline-regression-corpus-v22-fresh-holdout.json `
  regression_runs\<run-id>\pipeline_regression_report.json `
  ..\..\docs\pipeline-recipes `
  --phase4-closeout regression_runs\<run-id>\pipeline_regression_closeout.json `
  --release-label V22.1 `
  --operator <operator-id>
```

`docs/pipeline-recipes/pipeline_recipe_current.json` is the current V24.1 pointer. The versioned file is content-addressed by the recipe SHA-256 (`1a2b06c5b2f5c3c7c4e7434169e824a0baf99b3056ae695127d978d1aa3dd3dd`). V24.1 corrects the V24 TTS provenance defect: the lock is derived from and revalidates the hash-bound E2E `render_prep_manifest.json` artifacts, which prove `omnivoice` / `k2-fsa/OmniVoice` / `instruct:vi_female_north` for the three narration cases. A candidate or lock now fails when manifests are missing, stale, or disagree on runtime provider/model/voice/rate. Auto-queue TTS jobs also receive the immutable recipe authority and override a changed Ops voice/provider; manual Preview/Generate TTS remains Ops-profile controlled. The other controlled-pilot boundaries remain Phase 1 `v58_candidate`, `STEP=1`, `PAD=1`, `master_timeline.json`, `authority_v3_6_full_duration=false`, local Phase 2 OCR with `phase2_ocr_timeline.json`, measured TTS fitting, source-intrinsic text provenance, and bounded final-render QA. Reup Queue auto runs bind this immutable artifact before creating durable stage work; retries/resumes must reuse and revalidate that binding.

Changing an algorithm, provider/model, quality threshold, timing policy, or render policy requires a new regression run and a new recipe lock. Do not edit a versioned recipe in place.

Do not lock a recipe from a batch with any failed case, unresolved OCR object, stale NO_TEXT approval, open incident, unbound scope override, blocked Phase 4 preflight, residual CJK, collision, pending remediation proposal or pending triage decision. Corpus v3, v10, v11, and v13 remain non-locking historical evidence. V24 evidence is recorded in `apps/api/regression_runs/pipeline_v24_gap_closure_20260801`; it still has `universal_video_support=false` and remains controlled-pilot evidence rather than a universal-production claim.

For the UI runtime binding contract, see `docs/reup-queue-v24-runtime-binding.md`.

## Import an approved adaptive final into canonical DB state

After final, metadata, and source-rights/music approvals are hash-valid:

```powershell
python -m scripts.import_adaptive_final_to_db `
  <artifact-root> <source-video-uuid> `
  --queue-item-id <queue-item-uuid> `
  --recipe-lock ..\..\docs\pipeline-recipes\pipeline_recipe_current.json `
  --expected-recipe-release V22.1
```

The importer verifies the recipe self-hash, `pipeline_recipe_lock_v3` schema, expected release, locked-pilot status, matching non-empty Phase-4-preflight evidence, and disabled external publishing. It then verifies all local package files and approval self-hashes, the final video SHA-256, and encoded-output QA before it:

- copies the video through the storage abstraction;
- creates or reuses `MediaAsset(FINAL_RENDER_VIDEO)`;
- creates or reuses `RenderOutput(APPROVED)`;
- moves the source to `PUBLISH_READY`;
- moves the queue item to `READY_TO_EXPORT`, then `EXPORT_PACKAGE_CREATED` after package creation;
- creates or reuses a DB `ExportPackage` in `READY_FOR_HANDOFF`.

`phase5_db_handoff.json` and the JSON metadata on `MediaAsset`, `RenderOutput`, `ReupQueueItem`, `ExportPackage`, and `ExportPackageItem` receive the same portable `pipeline_recipe_lock_ref_v1` snapshot. It contains the release, recipe SHA-256, lock-file SHA-256, status, validation boundary, and artifact filename; it never stores an operator-specific absolute path.

Re-running the same command must return `asset_reused=true`, `render_reused=true`, and `export_package_reused=true`. Render and package reuse require both the same final-video SHA-256 and the same locked recipe SHA-256. Identical video bytes under a different recipe may reuse the `MediaAsset`, but must create a new versioned `RenderOutput` and must not reuse the former package. A queue item already beyond export cannot be silently rebound to another render or a recipe-mismatched package; the import fails closed and requires a separately controlled queue decision. The importer never creates a `PublishHandoff`, publish attempt, or external platform call.

Use `--without-export-package` only when the intended boundary is an approved render waiting in `READY_TO_EXPORT` for a later operator action.

## Build end-to-end evidence and relock changed policies

After every included case has passing encoded-output QA, final/metadata/rights
approvals, a manual-export boundary, and a retry-safe canonical DB handoff, build
the supplementary end-to-end report:

```powershell
python -m scripts.build_pipeline_e2e_regression_report regression_runs\<e2e-run-id>
```

The report verifies final hashes, approval self-hashes, operator gates, manual
handoff state, DB `MediaAsset`/`RenderOutput`/`ExportPackage` reuse, and that no
external publish call occurred. It closes only the cases physically present in
that run root and always keeps `universal_video_support=false`.

When an algorithm or quality policy changed, bind this report to the existing
accepted Phase-1/2 corpus and report while creating a new immutable recipe:

```powershell
python -m scripts.lock_pipeline_recipe `
  ..\..\docs\pipeline-regression-corpus-v14-grid-peer-guard.json `
  regression_runs\pipeline_v15_recipe_lock_candidate_20260727\pipeline_regression_report.json `
  ..\..\docs\pipeline-recipes `
  --e2e-report regression_runs\<e2e-run-id>\pipeline_e2e_regression_report.json `
  --operator <operator-id>
```

An end-to-end report is supplementary evidence, not a replacement for the
5-10-case Phase-1/2 corpus. Recipe lock requires at least three fully passing
end-to-end cases with retry-reuse confirmed and zero external publish calls.

## Pilot interpretation

The recipe status is `LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS`, not universal support. Add representative real videos for every declared corpus gap before widening the supported input claim. Every new case must retain the same manual gates and should be added to the regression corpus rather than treated as a one-off tuning target.
