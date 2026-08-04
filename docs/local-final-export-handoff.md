# Local Final Export Handoff

This pilot boundary locks an adaptive Phase 4 final without pretending that a DB `RenderOutput` or Reup Queue item is publish-ready.

Run from `apps/api` after the operator confirms `FINAL_APPROVED`:

```powershell
python -m scripts.run_final_export_handoff <artifact-root> <source-video-uuid> <external-video-id> --operator <operator-id>
```

The command fails closed unless:

- render metadata is `FINAL_RENDERED` and its output SHA-256 matches the MP4;
- encoded-output QA is `PASS` with no failed checks;
- visual approval is `VISUAL_APPROVED`;
- audio approval is `AUDIO_APPROVED`;
- Phase 3 is closed;
- every required artifact is present and hashable.

Outputs:

- `final_approvals/final_<video-sha256>.json`: immutable, content-addressed final approval;
- `phase5_final_approval.json`: current pointer copy;
- `export_packages/<external-id>_<hash>/final_video.mp4`;
- `export_packages/<external-id>_<hash>/cover.jpg`;
- `export_packages/<external-id>_<hash>/publish_draft.json`;
- `export_packages/<external-id>_<hash>/manifest.json`;
- `phase5_export_handoff.json`.

The package is `READY_FOR_OPERATOR_HANDOFF`, while publish metadata remains `DRAFT_REVIEW_REQUIRED`. Target platform, title and caption are mandatory operator fields. This command never marks the source `PUBLISH_READY`, creates a publish attempt or calls an external platform.

## Complete the local publish metadata draft

Prepare a UTF-8 JSON input with the operator-assisted metadata:

```json
{
  "target_platform": "FACEBOOK_REELS",
  "title": "Operator-facing title",
  "caption": "Operator-facing caption",
  "cta_text": "Optional call to action",
  "hashtags": ["reels", "example"],
  "generation_source": "operator_assisted_local_v1"
}
```

Run from `apps/api`:

```powershell
python -m scripts.update_local_publish_draft <artifact-root> <metadata-json>
```

The updater resolves the content-addressed package through `phase5_export_handoff.json`, applies the configured platform limits, runs the existing publish-draft risk scanner, and refreshes both the publish-draft item hash and package manifest hash. A successful update moves only the local metadata state to `METADATA_DRAFT_COMPLETE_REVIEW_REQUIRED`; operator review remains `PENDING_OPERATOR_REVIEW`.

The updater does not approve metadata, schedule content, create a publish attempt, change the source or queue state, or call Facebook. The manifest deliberately retains `SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED` because retaining source music requires a separate rights check before external publishing.

## Record operator metadata approval

After the operator explicitly approves the exact local draft, run:

```powershell
python -m scripts.approve_local_publish_metadata <artifact-root> --operator <operator-id>
```

The approval command verifies the current handoff, manifest self-hash, and every package item before accepting the checkpoint. It snapshots both the reviewed and approved draft revisions under `publish_drafts/`, creates the immutable `metadata_approvals/metadata_<approved-draft-sha256>.json`, and refreshes the current approval pointer, package manifest, and handoff.

The resulting states are:

- publish metadata: `METADATA_APPROVED`;
- package and handoff: `READY_FOR_RIGHTS_REVIEW`;
- next gate: `SOURCE_RIGHTS_AND_MUSIC_REVIEW_REQUIRED`;
- external publish: `false`.

The operation is idempotent for an already approved package and fails closed if the reviewed draft or another package item no longer matches its manifest. Metadata approval is not a declaration that the source footage or retained music is licensed for external publication.

## Record source and retained-music rights attestation

Only after the operator explicitly confirms authorization for both the source video and retained music on the selected target platform, run:

```powershell
python -m scripts.approve_local_source_rights_and_music <artifact-root> --operator <operator-id>
```

The command verifies the complete package and the metadata-approval authority, then creates a versioned `rights_music_approvals/rights_<binding-sha256>.json`. The binding covers the final-video hash, metadata-approval hash, and target platform. A current pointer and a package copy are also written.

The resulting states are:

- rights and music: `SOURCE_RIGHTS_AND_MUSIC_APPROVED`;
- package and handoff: `READY_FOR_MANUAL_PUBLISH_HANDOFF`;
- next gate: `EXTERNAL_PUBLISH_AUTHORIZATION_REQUIRED`;
- publish authorization: `NOT_GRANTED`;
- external publish: `false`.

This checkpoint records an `EXPLICIT_OPERATOR_ATTESTATION`; it does not claim that the application performed legal review or independently verified supporting licenses. The command is idempotent and fails closed if any package artifact has changed.

## Finalize a manual-only export

When the operator chooses manual upload instead of connector publishing, run:

```powershell
python -m scripts.finalize_local_manual_export <artifact-root> --operator <operator-id>
```

The command records an immutable `MANUAL_EXPORT_ONLY` decision, writes a reviewed `MANUAL_UPLOAD_CHECKLIST.md`, refreshes the package manifest, and creates an atomic ZIP under `manual_exports/`. The ZIP contains the final video, cover, publish metadata, approval records, manifest, draft history, and manual-upload checklist beneath one package directory.

The resulting states are:

- package: `READY_FOR_MANUAL_EXPORT`;
- handoff: `MANUAL_EXPORT_READY`;
- publish authorization: `MANUAL_EXPORT_ONLY`;
- next action: `OPERATOR_MANUAL_UPLOAD`;
- external publish: `false`.

The generated `phase5_manual_export_handoff.json` records the final manifest hash and ZIP SHA-256. Re-running the command verifies and returns the same archive rather than publishing or creating a second decision.

## Record and verify a manual upload

After manual upload, prepare an evidence JSON containing the Facebook Reel permalink, an offset-aware publication time, the IANA timezone name, and read-only verification observations. Then run:

```powershell
python -m scripts.record_local_manual_upload_evidence <artifact-root> <evidence-json> --operator <operator-id>
```

Completion requires all three observed conditions: the permalink is reachable, public visibility is observed, and the visible content matches the approved package. When all conditions pass, the service creates a hash-bound `MANUAL_UPLOAD_COMPLETED` checkpoint and moves the next gate to `PILOT_CLOSED`.

If the permalink resolves to unrelated or unverifiable content, the attempt is retained under `manual_upload_evidence/` as `MANUAL_UPLOAD_EVIDENCE_MISMATCH`. The package remains `MANUAL_EXPORT_READY`, no completion record is created, and the next gate becomes `CORRECT_MANUAL_UPLOAD_EVIDENCE_REQUIRED`. Operator-reported publication and system-triggered external publication remain separate facts.

## Defer manual upload

When the operator intends to publish later, preserve the archive and evidence audit with:

```powershell
python -m scripts.defer_local_manual_upload <artifact-root> --operator <operator-id> --reason operator_will_publish_later
```

The idempotent checkpoint moves the handoff to `MANUAL_UPLOAD_DEFERRED` and the next gate to `BATCH_REGRESSION_READY`. It does not delete mismatch evidence, rebuild the ZIP, publish externally, or prevent a later verified manual-upload completion.

The normal DB `ExportPackage` path remains authoritative once the queue item has a persisted approved `RenderOutput`, reaches `READY_TO_EXPORT`, and media prep reaches `READY_FOR_EXPORT`.

## Import the approved local final into canonical DB state

After the local final, metadata, and source-rights/music approvals are complete, run from `apps/api`:

```powershell
python -m scripts.import_adaptive_final_to_db `
  <artifact-root> <source-video-uuid> `
  --queue-item-id <queue-item-uuid> `
  --recipe-lock ..\..\docs\pipeline-recipes\pipeline_recipe_current.json `
  --expected-recipe-release V22.1
```

The command fails closed on a missing/tampered recipe lock, wrong expected release, absent Phase-4-preflight evidence, enabled external publishing, invalid approval self-hash, stale package manifest, changed package item, final-video hash mismatch, or failed encoded-output QA. On success it creates or reuses the canonical final `MediaAsset`, approved `RenderOutput`, and DB `ExportPackage`, then records `phase5_db_handoff.json` in the artifact root.

The import is retry-safe by the pair `(final-video SHA-256, locked recipe SHA-256)`. A retry with both identities unchanged reuses the same asset, render, and package, preserves downstream queue state, and repairs adaptive manifest metadata if a previous run stopped after package creation. The same bytes under another recipe may reuse only the media asset; render and package identity remain recipe-specific. The same portable recipe reference is stored in the asset, render settings/metadata, queue, package, package item, and handoff artifact. It does not create a `PublishHandoff` or trigger external publishing. See `docs/pipeline-controlled-pilot-runbook.md` for the regression and recipe-lock workflow that precedes this boundary.
