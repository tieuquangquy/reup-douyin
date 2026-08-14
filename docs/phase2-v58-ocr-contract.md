# Phase 2 v58 OCR contract

> The detector/geometry foundation remains valid, but exact-string content
> grouping has been superseded by the Semantic Hard-sub Cue Authority. See
> [`semantic-hardsub-cue-authority.md`](./semantic-hardsub-cue-authority.md).

**Status:** OCR checkpoint approved on the local candidate; translation is next.  
**Input authority:** read-only Phase 1 `master_timeline.json` + SHA-256.  
**Geometry policy:** Phase 2 must not modify `box_coords`, `start_frame`, or `end_frame`.  
**Provider policy:** local REST OCR by default; cloud and mock are explicit operator/test choices.

## Scope

Phase 2 localizes all editor-added semantic text retained by Phase 1: titles, hardsubs, ingredient/instruction labels, endcard/nutrition labels, numeric values, and known units.

Exact numeric values are protected. Known units are deterministic (`克 -> g`, `千卡 -> kcal`, `毫升 -> ml`). Mixed label/value text is sent downstream with protected placeholders so an LLM cannot change the value.

## Run

```powershell
cd apps/api

# Default: local OCR at http://127.0.0.1:8080/predict
python -m scripts.run_phase2_only <phase1-output-copy>

# Explicit alternatives only
python -m scripts.run_phase2_only --provider cloud <phase1-output-copy>
python -m scripts.run_phase2_only --provider mock <phase1-output-copy>
```

Configuration:

```text
LOCAL_OCR_ENDPOINT_URL=http://127.0.0.1:8080/predict
LOCAL_OCR_MODEL_VERSION=ppocrv6-medium-det-rec
OCR_ENDPOINT_URL=https://.../predict       # cloud mode only
OCR_MODEL_VERSION=ppocr-cloud-v1           # cloud mode only
```

For the current 11.68 GiB Docker runtime, Phase 2 pins
`PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec` on CPU with MKLDNN disabled.
PaddleOCR-VL-1.6 remains an explicit option for hosts with at least 20 GiB RAM;
it is not the local default for this candidate.

Local failure is fail-closed: content becomes `OCR_FAILED` / `NEEDS_OCR_REVIEW`. The runner never silently switches to cloud or mock.

## Flow

```text
read master_timeline.json + SHA-256
  -> OCR Phase-1 crops (Otsu/raw variants)
  -> failed-track fallback (best/mid frame, normalized 64px raw borders)
  -> cache by exact prepared JPEG + provider/model/preprocessing namespace
  -> group identical content across one or more geometry refs
  -> deterministic unit/value policy or protected LLM input
  -> operator review/approval
  -> review-input hash freshness gate
  -> READY_FOR_PHASE3 handoff + final OCR payload
```

## Content model

One content object may reference multiple Phase-1 geometry tracks:

```json
{
  "content_id": "ocr_content_010",
  "geometry_refs": ["sub_10", "sub_13"],
  "ocr_text_raw_candidates": ["蒜末"],
  "ocr_text_candidate": "蒜末",
  "ocr_text_llm_suggested": null,
  "ocr_text_approved": null,
  "review_input_sha256": "...",
  "review_status": "OCR_CANDIDATE",
  "review_required": true,
  "localization": {
    "mode": "llm_translate",
    "protected_values": []
  }
}
```

This preserves and covers every geometry occurrence while translating the content only once.

## Review states

| State | Meaning |
|---|---|
| `OCR_CANDIDATE` | Local OCR returned text; operator must approve/edit |
| `OCR_FAILED` | No usable OCR text; operator input or retry required |
| `OCR_REVIEW_STALE` | Approval does not match the current candidate/suggestion evidence hash |
| `OCR_APPROVED` | Exact Chinese text was approved |
| `OCR_REJECTED_UI` | Operator marked non-localizable UI; geometry stays coverable |

LLM correction is suggestion-only. Write suggestions to `phase2_llm_suggestions.json`; the runner records them as `ocr_text_llm_suggested`. LLM output never overwrites raw OCR and never auto-approves content.

## Approval workflow

First run creates `phase2_approvals.json` with one row per content object:

```json
{
  "content_id": "ocr_content_001",
  "decision": "",
  "review_input_sha256": "...",
  "ocr_text_approved": "鸡蛋拌饭",
  "vi_text_approved": null,
  "reviewer": null,
  "reviewed_at": null
}
```

Allowed decisions: `APPROVE`, `EDIT`, `ACCEPT_LLM`, or `REJECT_UI`. The decision is accepted only when `review_input_sha256` matches the current Phase-1 hash, geometry refs, OCR candidate, and suggestion. After editing approvals, rerun the same command. OCR results come from `qa/ocr_cache.json`; only missing cache entries call the provider.

For a fresh Phase-1 artifact, build a read-only proposal before recording any
decision:

```powershell
python -m scripts.build_phase2_review_proposal `
  <new-phase2-root> <previous-reviewed-phase2-root> `
  --suggestions <unapproved-suggestions.json>
```

`phase2_review_proposal.json` is not an approval artifact. It separates:

- `CARRY_FORWARD_ELIGIBLE`: the target crop SHA-256 is byte-identical to a
  prior crop whose approval has `APPROVE`/`EDIT`, a reviewer, and a review
  timestamp;
- `OPERATOR_REVIEW_REQUIRED`: geometry/crop changed, no reviewed authority
  exists, or a new suggestion differs from that authority.

An `ocr_text_approved` placeholder with an empty decision or missing reviewer
metadata is never carry-forward authority. The proposal is self-hashed and
bound to the current `phase2_review_queue.json`; suggestions remain
non-authoritative until the operator explicitly materializes and applies a
complete decision set.

After the operator approves the exact proposal hash, materialization requires
that hash and reviewer identity explicitly:

```powershell
python -m scripts.materialize_phase2_review_proposal `
  <phase2-root> <phase2_review_proposal.json> `
  --approve-proposal-sha <operator-approved-sha256> `
  --reviewer <operator-id>
```

The generated decision set must still pass
`scripts.apply_phase2_operator_review`; materialization alone does not mutate
`phase2_approvals.json`.

## Artifacts

| Artifact | Purpose |
|---|---|
| `master_timeline.json` | Immutable Phase-1 geometry/timing authority |
| `phase2_ocr_timeline.json` | Versioned content contract + Phase-1 hash |
| `phase2_review_queue.json` | Unresolved content and crop/overlay review assets |
| `phase2_review_proposal.json` | Hash-bound carry-forward/manual-review proposal; never approval authority |
| `phase2_approvals.json` | Operator-editable decision input |
| `phase2_llm_suggestions.json` | Optional LLM suggestion input; never authority |
| `phase2_approved_content.json` | Approved content snapshot |
| `qa/ocr_inputs/` | Exact OCR preprocessing evidence |
| `qa/ocr_cache.json` | Namespaced resumable OCR cache |
| `phase2_handoff_preview.json` | Observable handoff preflight, including blocked reasons |
| `phase2_handoff.json` | Sole authoritative Phase-2 → Phase-3 boundary; written only when ready |
| `qa/stale/` | Quarantined generated finals/handoffs superseded by a blocked rerun |
| `phase2_ocr_payload_preview.json` | Fail-closed review preview |
| `ocr_payload.json` | Written only with a `READY_FOR_PHASE3` handoff |
| `phase2_meta.json` | Provider/model/hash/status/counts/runtime |

All Phase-2 JSON writes are atomic. `master_timeline.json` is never a write target.

## Current real-video evidence

Video `7450099336215579915`:

- 36 Phase-1 geometry tracks;
- 36/36 received local OCR text;
- grouped into 35 content objects (`蒜末` uses two geometry refs);
- pinned local model: `PP-OCRv6_medium_det` + `PP-OCRv6_medium_rec`;
- 35/35 content objects approved after delegated visual audit;
- fresh pinned-model OCR: 49.0 seconds;
- cached rerun: 0.62 seconds;
- Phase-1 SHA-256 unchanged before/after;
- final `ocr_payload.json` emitted only after approval;
- corrected `sub_21` exact text ends with `了`;
- 26 approved content objects require translation and 9 use deterministic localization;
- 36/36 geometry refs are mapped in `phase2_handoff.json`;
- mixed ASCII units in `10g` and `200g` are protected before translation.

Candidate artifacts: `apps/api/tmp_phase2_v2_final_local_7450099336215579915/`.

## PASS contract

Phase 2 is PASS only when:

1. Phase-1 SHA-256 still matches.
2. Every content object is `OCR_APPROVED` or `OCR_REJECTED_UI`.
3. No `OCR_FAILED`, `OCR_CANDIDATE`, `OCR_REVIEW_STALE`, or unresolved LLM conflict remains.
4. Protected numeric values are unchanged.
5. Deterministic units have approved render text.
6. Duplicate content is translated once and mapped to every geometry ref.
7. Operator has reviewed exact Chinese text.
8. `phase2_handoff.json` reports `READY_FOR_PHASE3` and maps every geometry ref.

## Non-goals of this implementation slice

- Web review UI;
- invoking an LLM correction provider automatically;
- Phase 2.5 Vietnamese translation;
- executing the full video render.

The handoff and deterministic pre-render contract are implemented; LLM translation and full render execution belong to the following steps.
