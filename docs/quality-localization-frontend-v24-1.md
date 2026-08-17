# Frontend quality localization workflow V24.1

Final Review keeps the operator-gated workflow validated by the regression corpus,
while Reup Queue `auto_to_render` may promote deterministic checkpoints through
`quality_auto_to_render_v1`. `POST /ocr` is a durable `ANALYZE_OCR` job bound to the current
immutable recipe and always runs Phase 1 v58 (STEP=1, local Phase 2 OCR). It no
longer invokes the legacy `media_e2e_v1` clean-and-render path.

The persistent workspace is kept below `quality-localization/{workspace}/{source}/{job}`.
It contains the hash-bound Phase 1/2/3 authorities and Phase 4 preview/final artifacts;
`master_timeline.json` is never overwritten.

## Operator sequence

1. **Analyze OCR** creates the Phase 1 + local OCR job. Normal Analyze/Retry reuses
   the active source-hash-bound v58 authority. Only the warned Advanced action sends
   `force_refresh=true` and creates a superseding Phase 1 run.
2. **Exact OCR review** requires a decision for every unresolved object. The evidence
   image and role labels help distinguish editor-added text from source-intrinsic UI.
   While this checkpoint is open, Final Review shows **Needs review** (never
   “In progress”) and both normal Analyze OCR entry points become **Review OCR
   below**. Starting another OCR run is available only through the explicit
   Advanced/break-glass action because it supersedes the current artifact run and
   makes its decisions stale.
3. If dialogue hard-sub geometry is ready before the Vietnamese dialogue draft is
   approved, the summary exposes `WAITING_DIALOGUE_TRANSLATION_APPROVAL` plus the
   exact blocker count. Final Review offers **Approve translation & resume**; approval
   creates a cache-first `resume_dialogue_translation` job that reuses Phase 1 and
   rebuilds only the semantic Phase-2 handoff. Repeated Analyze OCR requests are not
   a recovery mechanism for this checkpoint.
4. **Visual translation review** submits every Phase 3 object and creates a durable
   `RENDER_PREVIEW` job for the adaptive visual preview.
5. **Approve visual** records the hash-bound Phase 4 visual authority and stages a
   listenable narration + original-background preview. Final Render remains disabled.
6. Existing approved OmniVoice narration (`instruct:vi_female_north`) and the approved
   background stem are attached to the same Phase 4 root. If an older audio-analysis
   run produced hash-valid Demucs files without DB rows, final preparation recovers and
   upserts the stem rows, stages a gain-1.0 mix preview, and writes the bounded audio-mix
   authority before render. A verified no-dialogue case may use the approved source-audio
   handoff instead of a TTS asset.
6. **Approve audio & mix** is a separate hash-bound checkpoint. The operator must
   listen for complete dialogue, timing, voice and original background level. TTS
   marked `too_short`/`too_long` remains visible and cannot be silently accepted.
   An Auto Queue item parked at `quality_review` resumes only from this approval.
7. **Start/Rerender final** runs adaptive Phase 4 and persists `RenderOutput` plus
   Output QA. Late audio changes use the invariant-checked audio-only rebind; visual
   tracks and remediation operations are not regenerated. Refreshing the page reattaches
   OCR, preview, and final-render jobs.

## Retry and completion boundaries

- Preview and final artifacts are reusable only when source/input/output hashes, active
  remediation, current residual-CJK policy, and encoded Output QA all still match.
- A preflight residual-CJK failure is exposed in Final Review with its source frame.
  Corrected OCR and Vietnamese replacement produce a hash-bound delta remediation;
  only Phase 2/3 and the affected Phase 4 preview are resumed. Phase 1 is not rerun.
- Encoded residual evidence remains frame-granular for mask/boundary repair, but the
  frontend review and translation boundary uses temporal content objects. Adjacent
  detections are grouped by time, geometry and OCR consensus; source-intrinsic Phase-2
  tracks are excluded before translation. Residual translation runs in bounded batches,
  caches each completed text by model/prompt identity, and resumes only missing objects.
  The Jobs API exposes `workflow_action`, so this work is labelled **Residual Translation**
  instead of the multiplexed durable type `RENDER_PREVIEW`.
- Retrying the same run reuses the existing `media_assets.storage_key` row. It does not
  insert a duplicate version that violates the workspace storage-key constraint.
- A final artifact is not reusable unless `narration_complete=true`; even a sub-1%
  narration overrun is fitted with bounded `atempo` instead of being truncated by the
  final video duration.
- Final Review polls long enough for the lossless-intermediate render plus local OCR QA;
  browser polling timeout does not define durable job failure.
- When a later render succeeds, abandoned older `RENDERING` rows are closed as
  superseded so the operator sees one authoritative current output.

The API artifact route only serves files beneath the active quality workspace and
rejects traversal. Manual export/publish remains outside this workflow by design.

## Analyze OCR versus Visual Clean

`ANALYZE_OCR` and `RENDER_PREVIEW` are separate durable products. Analyze OCR publishes
tracks, content objects, geometry/provenance and review authority. Submitting approved
visual translations starts `RENDER_PREVIEW`, which runs Phase 3/4 and materializes the
Visual Clean preview. Final Review therefore labels an active preview job **Building
Visual Clean preview**, never **Analyzing OCR**.

The OCR summary exposes `visual_preview_status` independently of `workflow_stage`:
`READY_TO_BUILD`, active job states, `BLOCKED_REVIEW`, `FAILED`, or `READY`. A structured
preflight error is shown after refresh, while a residual-CJK gate remains an explicit
review checkpoint rather than a failed OCR run.

## Reup Queue full-auto authority

The ordinary Final Review buttons remain manual. A queue item explicitly running in
`auto_to_render` passes `auto_advance=true` to its OCR job. The worker records a
`quality_auto_decision_authority.json` artifact and can only approve unambiguous local
provenance. Its subsequent preview job carries `auto_approve=true`; visual and audio
approval still call the same hash/QA validators used by the frontend. If any validator
or deterministic policy cannot decide, the queue item stops as needs-attention rather
than silently rendering a lower-confidence product.
