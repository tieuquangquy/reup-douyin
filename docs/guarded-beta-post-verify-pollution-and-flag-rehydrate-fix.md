# Round 7: Verify-Before-Write Pre-Check + idempotent_check_inconclusive Distinction

## What changed since round 6

Round 6 added an independent verify-after-write read so a `/full-modal-harvest` response that self-reports
`idempotent_success` while persisting nothing now resolves to `failed_verify_after_write_no_confirmed_record`. Round 7
closes the remaining gap on the input side of that contradiction: the action now also performs a verify-BEFORE-write
existence check, and the write status helper distinguishes a verify call that errored (inconclusive) from a verify call
that confirmed zero records (failed). Without this distinction, an `/items/verify` outage could be silently treated as a
write failure (or worse, masked by self-reported write counts).

## Round 7 minimal fix: independent verify-before-write authority + inconclusive verdict

New helper:
[`guardedHybridCollectBetaVerifyBeforeWriteConfirmedCount`](apps/extension-douyin-capture/src/popup.ts:11131). It mirrors
the verify-after-write helper exactly — same endpoint (`/douyin-extension/capture-inbox/items/verify`), same id set
(`aweme_ids` and `source_video_external_ids` derived from the production payload preview), same scope
(`capture_session_id` from the payload). It returns
`{ attempted, confirmed_count, queried_aweme_id_count, confirms_all, error }`. The action calls it BEFORE the write and
threads `verify_before_write_*` into `backendResult` alongside the existing `verify_after_write_*` fields, so the write
status helper can use either authority to confirm record existence.

In [`runGuardedHybridCollectBetaFromPopup`](apps/extension-douyin-capture/src/popup.ts:11168):
- `const verifyBeforeWrite = await guardedHybridCollectBetaVerifyBeforeWriteConfirmedCount(payloadPreview);` runs first.
- The real `/full-modal-harvest` write still proceeds. We do not skip the write on `confirms_all` because the only
  authority that should short-circuit is the union check inside `guardedHybridBackendWriteStatus`; keeping the write
  path identical avoids a second control flow that could drift from the after-write authority.
- Both verify results are merged into `backendResult` as `verify_before_write_attempted`,
  `verify_before_write_confirmed_count`, `verify_before_write_queried_count`, `verify_before_write_confirms_all`,
  `verify_before_write_error`, plus the existing verify-after-write fields.

In [`guardedHybridBackendWriteStatus`](apps/extension-douyin-capture/src/popup.ts:10566):
- `verifyBeforeWriteInconclusive = verifyBeforeWriteAttempted && verifyBeforeWriteError !== null && verifyBeforeWriteError !== "no_written_aweme_ids_in_payload"`.
- `verifyAfterWriteInconclusive` is computed the same way for the after-write helper.
- `idempotentCheckInconclusive = (verifyBeforeWriteInconclusive || verifyAfterWriteInconclusive) && !verifyAfterWriteConfirmsAll && !verifyBeforeWriteConfirmsAll`.
  This is the new failure mode: when the verify call itself errored AND nothing else independently confirms records
  exist, the write status MUST NOT manufacture a success or a definitive failure. It emits the dedicated effective
  status `idempotent_check_inconclusive` so the caller can retry.
- Confirmed-records authority is now a UNION: `confirmedExistingRecords = anyVerifyAttempted ? (verifyAfterWriteConfirmsAll || verifyBeforeWriteConfirmsAll) : selfReportedConfirmedExistingRecords`.
  Either independent verify (before or after) confirming every target id is sufficient. The diagnostic field
  `confirmed_existing_records_authority` reports `independent_verify_before_write`, `independent_verify_after_write`, or
  `backend_self_reported_counts` accordingly.
- `normalizedOk = !verifyAfterWriteVetoesSuccess && !idempotentCheckInconclusive && (backendResult.ok === true || idempotentSuccess)`.
  `idempotent_check_inconclusive` is a third veto, alongside `verifyAfterWriteVetoesSuccess`, that forces
  `normalizedOk = false` and `safe_for_post_verify = false`.
- `effectiveStatus` precedence: `idempotent_check_inconclusive` > `failed_verify_after_write_no_confirmed_record` >
  `idempotent_success` > `updated_success` > `partial_schema_gap` > `failed`.

Effect: an `/items/verify` outage no longer masquerades as a definitive backend write failure or success. The summary
verdict surfaces `idempotent_check_inconclusive`, the production source artifact is NOT persisted, and the operator
retries instead of advancing on phantom or unverifiable data. When the verify path is healthy, behavior is identical to
round 6 — the union authority simply admits an additional confirmation source (verify-before-write) that the write
never has to invent.

## Write-vs-verify endpoint follow-up

The write endpoint (`/douyin-extension/full-modal-harvest`) and the verify endpoint
(`/douyin-extension/capture-inbox/items/verify`) remain different surfaces with potentially different write/read scope
semantics. Round 7 keeps both calls scoped by `capture_session_id` exactly as post-verify does, so a contradiction can
only come from one of:

1. The write genuinely persisted nothing (false-idempotent-skip; round 6 verdict).
2. The verify endpoint is unavailable or auth-failed (round 7 `idempotent_check_inconclusive`).
3. The write persisted under a different `capture_session_id` than what the verify lookup used (lookup-scope mismatch;
   already detected by the read-only evidence dump in round 5).

If a future operator run exposes (3) under valid auth, the fix is server-side scope alignment between the write and the
verify lookup, not another extension-side reporting layer. The evidence dump's scoped vs unscoped lookup remains the
intended diagnostic for that case.

## Tests added (round 7)

- `guardedHybridCollectBetaVerifyBeforeWriteConfirmedCount` exists and queries `/items/verify` with the written
  aweme_ids and resolved `capture_session_id` from the payload preview.
- The action calls verify-before-write and threads `verify_before_write_*` into `backendResult` BEFORE the summary is
  built.
- `idempotent_check_inconclusive` is emitted when either verify call errored and neither confirmed every target id.
- `idempotent_success` continues to require confirmed existing records (round-6 baseline preserved).

## Constraints honored

- Read-only verify reads only; no backfill; no write semantics change beyond the inconclusive veto.
- Estimated_views remains separate from view_count; full_queue_completion stays disabled; no pilot auto-rerun.
- No reporting/next_action edits beyond the new `effectiveStatus` enum value `idempotent_check_inconclusive`, which is a
  status fact rather than a recommendation/next-action change.

---

# Round 6: Verify-After-Write Fix For False-Idempotent-Skip (live verdict, valid auth)

## What changed since round 5

Token refresh fixed the 401 Bearer-token-expired blocker. Under valid auth, beta post-verify reliably returns
`beta_post_verify_failed_backend_items_not_found` with `all_backend_items_not_found_for_accepted_aweme_ids`. The
contradiction is now confirmed live: `guarded_hybrid_collect_beta_5` reports `idempotent_success` while a successful,
authenticated read of the same accepted aweme_ids on the same `/items/verify` endpoint returns ZERO records. That is
verdict **(a) false-idempotent-skip**. Verdict (b) lookup-mismatch is ruled out because the verify endpoint and id set
match what the read-only evidence dump exercises and the dump already showed unscoped lookup also returns zero.

## Why round 4 was insufficient

Round 4 tightened `idempotentSuccess` to require `matchedCount === targetCount && unchangedCount === targetCount`. That
gate still trusts the `/full-modal-harvest` write response's SELF-REPORTED counts. Live evidence shows that response is
itself the unreliable signal: it claims idempotent counts while no row was created or matched in the backend. Trusting
its own counts cannot detect this — confirmation has to come from an independent reader.

## Round 6 minimal fix: independent verify-after-write authority

In [`runGuardedHybridCollectBetaFromPopup`](apps/extension-douyin-capture/src/popup.ts:11109): immediately after the
`/full-modal-harvest` write returns, the action calls
[`guardedHybridCollectBetaVerifyAfterWriteConfirmedCount`](apps/extension-douyin-capture/src/popup.ts:11093). That helper
issues a read-only `POST` to `/douyin-extension/capture-inbox/items/verify` for the EXACT aweme_ids in the written
payload (using the `capture_session_id` resolved by the write response, the same scope post-verify uses). It returns
`{ attempted, confirmed_count, queried_aweme_id_count, error }`, which the action threads into `backendResult` as
`verify_after_write_*` fields BEFORE the summary is built.

In [`guardedHybridBackendWriteStatus`](apps/extension-douyin-capture/src/popup.ts:10566):
- `verifyAfterWriteAttempted = backendResult.verify_after_write_attempted === true`.
- `verifyAfterWriteConfirmsAll = verifyAfterWriteAttempted && targetCount > 0 && verify_after_write_confirmed_count >= targetCount`.
- `confirmedExistingRecords = verifyAfterWriteAttempted ? verifyAfterWriteConfirmsAll : selfReportedConfirmedExistingRecords`.
  When verify-after-write was attempted it OVERRIDES the backend's self-reported counts as the confirmed-records
  authority (the diagnostic field `confirmed_existing_records_authority` is `independent_verify_after_write`).
- `verifyAfterWriteVetoesSuccess = verifyAfterWriteAttempted && !verifyAfterWriteConfirmsAll` forces
  `normalizedOk = false` and sets `effectiveStatus = "failed_verify_after_write_no_confirmed_record"`. With
  `normalizedOk` false, `safe_for_post_verify` is false, the production source artifact is NOT persisted, the verdict is
  `beta_collect_backend_failed`, and post-verify is never invoked against a phantom write.

Effect: a write that the backend self-reports as idempotent but does not actually persist now resolves to
`failed_verify_after_write_no_confirmed_record`. `idempotent_success` requires both the prior structural invariants AND
an independent verify confirming every target id. `beta_5_post_verify` will only be reachable once the backend genuinely
holds the records.

Constraints honored: read-only investigation first (round 5 dump still ships); no backfill of unrelated rows;
estimated_views remains separate from view_count; full_queue_completion stays disabled; no pilot auto-rerun; no
reporting/next_action layer edits this round (only the `effectiveStatus` enum gained the dedicated
`failed_verify_after_write_no_confirmed_record` value, which is a status fact, not a recommendation/next-action change).

## Tests added
- `guardedHybridCollectBetaVerifyAfterWriteConfirmedCount` exists and queries `/items/verify` with the written aweme_ids
  and resolved `capture_session_id`.
- The action threads `verify_after_write_confirmed_count` into `backendResult` before building the summary.
- `idempotentSuccess` requires confirmed existing records; when verify-after-write was attempted, confirmation requires
  it to have found every target id.
- A failing verify-after-write vetoes `normalizedOk` so `safe_for_post_verify` cannot be true.

---

# Guarded Beta Backend Evidence Dump (round 5, read-only investigation)

## What this round added (no reporting-layer changes)

The prior rounds changed only the reporting/idempotency-normalization layer, and the live blocker
`all_backend_items_not_found_for_accepted_aweme_ids` never moved because the underlying contradiction was never
resolved with real backend data:

- `guarded_hybrid_collect_beta_5` reports `idempotent_success` (system believes items are already written, so it skipped
  the write), yet
- `guarded_hybrid_collect_beta_5_post_verify` finds ZERO backend items for the same accepted aweme_id set.

These cannot both be true. This round adds a READ-ONLY evidence dump that resolves it with data instead of guessing.

### New export: GUARDED_HYBRID_COLLECT_BETA_BACKEND_EVIDENCE_DUMP

Builder: [`buildGuardedHybridCollectBetaBackendEvidenceDump()`](apps/extension-douyin-capture/src/popup.ts:12588).
Wired to the popup "Export/Copy Beta Backend Evidence Dump" buttons. It performs NO writes (read_only: true,
storage_mutation: none, pipeline_stages_rerun: none) and does NOT rerun the pipeline. It:

1. Prints the exact accepted aweme_id set beta production used as the write target (count + literal id list), from the
   persisted source artifact (`accepted_aweme_ids` + `flushed_aweme_ids`).
2. Prints the exact aweme_id set + lookup key (`aweme_ids`) + namespace filter (`capture_session_id`) that beta
   post-verify uses, derived identically to
   [`buildGuardedHybridCollectBetaPostVerifySummary()`](apps/extension-douyin-capture/src/popup.ts) (same slice by
   `requiredBetaBatchSize`).
3. Reports whether the two id sets are identical and whether the lookup endpoint differs from the write endpoint
   (it does: write = `/douyin-extension/full-modal-harvest`, lookup = `/douyin-extension/capture-inbox/items/verify`).
4. Does a direct backend read for each accepted aweme_id via TWO read-only calls to the verify endpoint:
   - scoped: `{ aweme_ids, source_video_external_ids, capture_session_id }` — exactly what post-verify sends.
   - unscoped: `{ aweme_ids, source_video_external_ids }` — no `capture_session_id`.
   Per id it reports found (scoped) / found (unscoped) and which fields exist on the returned item, plus the backend's
   own `capture_session_id` on the unscoped item.
5. Emits a data-driven verdict:
   - `false_idempotent_skip_no_backend_record` — unscoped finds nothing either: the record does not exist under any
     scope, so the write was skipped as idempotent without ever persisting. (matches round-4 idempotency fix)
   - `lookup_scope_mismatch_capture_session_id` — unscoped finds the records but scoped (by `capture_session_id`)
     filters them out: post-verify queries the wrong run-scope. (the per-batch/shared-key refactor suspect)
   - `backend_records_present_post_verify_should_pass` — scoped lookup found the required records.

### Why this discriminates the two hypotheses

The single decisive signal is the difference between the scoped and unscoped lookups against the SAME id set on the SAME
endpoint. If unscoped > scoped, the records exist and the `capture_session_id` filter is the problem (lookup-mismatch).
If unscoped is also zero, the records genuinely do not exist (false-idempotent-skip). The dump prints both counts and the
per-id evidence so the verdict is verifiable, not asserted.

Note on `capture_session_id` flow (read while tracing, not changed this round): the production write payload sends
`capture_session_id: null` ([line 10295](apps/extension-douyin-capture/src/popup.ts:10295)); the source artifact takes
`capture_session_id` from the backend RESPONSE
([line 10737](apps/extension-douyin-capture/src/popup.ts:10737)); post-verify then filters the verify lookup by that
resolved `capture_session_id` ([line 10926](apps/extension-douyin-capture/src/popup.ts:10926)). If that resolved value
does not match the scope the rows were actually stored under, the lookup-mismatch verdict will fire — which is exactly
what the unscoped probe detects.

### Operator step required

This is a read-only diagnostic; the actual id sets, per-id found/fields, and the resolved verdict only materialize when
the dump is run from the loaded extension in the browser (it reads chrome.storage.local and calls the backend). Run
"Export Beta Backend Evidence Dump" and apply the verdict-specific fix:
- verdict `false_idempotent_skip_no_backend_record` -> the round-4 idempotency fix is correct; re-run guarded beta 5 so
  a real write persists the records.
- verdict `lookup_scope_mismatch_capture_session_id` -> align post-verify's lookup scope to the key/namespace beta
  production actually writes to (drop or correct the `capture_session_id` filter).

---

# Guarded Beta False-Idempotent-Skip Root Cause (round 4, supersedes the per-field diagnosis)

## TL;DR

`guarded_hybrid_collect_beta_5_post_verify` reported zero backend items for the accepted aweme_ids
(`beta_post_verify_failed_backend_items_not_found`, leading blocker
`all_backend_items_not_found_for_accepted_aweme_ids`). The five field blockers
(title/thumbnail/raw_like_count/backend_share_count/estimated_views) were a SYMPTOM: when every
`foundItems[index]` is null, all field comparisons fail at once.

Root cause = **false-idempotent-skip** in
[`guardedHybridBackendWriteStatus()`](apps/extension-douyin-capture/src/popup.ts:10561). The backend
returned the reason `accepted_payload_but_no_capture_inbox_item_created_or_updated` — it accepted the
payload but neither created a new capture-inbox row nor matched/updated an existing one (the record
does NOT exist). The previous logic used that exact reason as an escape hatch (`onlyAcceptedUnchangedReason`)
to zero out `rawFailedCount`/`rawRejectedCount`, so a write that persisted nothing was normalized to
`idempotent_success`. Beta production then persisted a "success" source artifact whose accepted
aweme_ids were never actually written, and post-verify correctly found zero backend items for them.

Ruled out:
- NOT wrong-lookup-key. [`guardedHybridItemsByAwemeId()`](apps/extension-douyin-capture/src/popup.ts:12844)
  matches on `aweme_id`, `source_video_external_id`, `video_external_id`, `external_id`; unchanged by
  the per-batch alias/key refactor.
- NOT wrong-namespace. Post-verify queries `/douyin-extension/capture-inbox/items/verify` with the same
  accepted aweme_ids the production source recorded.

## Fix (minimal, in `guardedHybridBackendWriteStatus`)

- `confirmedExistingRecords = matchedCount === targetCount && unchangedCount === targetCount` — a genuine
  idempotent write confirms the target rows already exist (holds without any escape hatch when the
  backend truly matched existing records).
- `acceptedButNothingPersistedReason` (the no-persist reason) is now a hard DISQUALIFIER for
  `idempotent_success`.
- `idempotentSuccess` now requires `confirmedExistingRecords`, `rawFailedCount === 0`,
  `rawRejectedCount === 0`, `!acceptedButNothingPersistedReason` (escape hatch removed).
- `backendDeclaredIdempotent` (which feeds `estimatedViewsPersisted`) also requires
  `confirmedExistingRecords`.

Effect: a no-op write that persists nothing resolves to `failed`/`partial_schema_gap`, beta production
no longer persists a false-success source artifact, and `beta_5_post_verify` passes only once the
backend actually holds the accepted items. Constraints honored: no backend write semantics change
beyond removing the false idempotent-skip; no backfill; estimated_views stays separate from view_count;
full queue completion stays disabled; no pilot auto-rerun. Confirming the fix requires the operator to
re-run guarded beta 5 (a real write) so the rows are actually created.

---

# Guarded Pipeline: next_action Foundational-Gate Fix, Beta Pilot-Contamination Guard, and Flag Rehydrate

## Update (round 3): milestone consistency + per-field beta read-back trace

Two follow-up items.

### A. highest_passed_milestone consistency (fixed)

The compact status gated `highest_passed_milestone` to `none` while a foundational gate was blocked, but the per-batch
diagnostic computed its own ungated value, so the two disagreed and `diagnostic_and_compact_status_consistent` was false.

Decision (single shared definition): a later pilot/queue milestone is reported as the highest passed milestone ONLY when
all foundational gates pass. While any foundational gate is blocked, `highest_passed_milestone` is `none` in BOTH outputs.
The compact status owns the foundational-gate authority; `buildPerBatchMilestoneAuthorityDiagnostic` now reads
`compactStatus.foundational_gate.all_foundational_gates_passed` and applies the same gate to its own
`highestPassedMilestone` (`rawHighestPassedMilestone` gated to `none` when a foundational gate is blocked). It also emits
`highest_passed_milestone_suppressed_by_foundational_gate`, `foundational_gates_passed`, `first_failing_foundational_step`,
and a `highest_passed_milestone_definition` string. Result: `diagnostic_and_compact_status_consistent = true`.

### B. Per-field beta read-back root-cause table

I traced each field through the beta production write path
([`hybridCollectBetaProductionSourceFromSummary`](apps/extension-douyin-capture/src/popup.ts:10704),
[`persistHybridCollectBetaProductionSourceFromSummary`](apps/extension-douyin-capture/src/popup.ts:10769)) and the
post-verify read-back path (helpers at lines 9940-10036, comparison loop at 10937-10976).

| Field | Write (expected_* in source artifact) | Read-back (backend item key) | Root cause |
| --- | --- | --- | --- |
| title | `expected_title_by_aweme_id` / item `title` | `guardedHybridActualTitle(item.title)` vs `guardedHybridExpectedTitle` | keys consistent; not a read-key rename |
| thumbnail | `expected_thumbnail_url` / `thumbnail_url` | `guardedHybridActualThumbnail(item.thumbnail_url\|cover_url)` vs expected | keys consistent; not a read-key rename |
| raw_like_count | `raw_like_count`/`like_count` | `guardedHybridFiniteNumber(item.like_count)` vs `guardedHybridRawLikeCountExpected` | keys consistent; not a read-key rename |
| backend_share_count | `share_count` | `guardedHybridShareCountRead(item)` vs `guardedHybridShareCountExpected` | keys consistent; not a read-key rename |
| estimated_views | `estimated_views` (+ formula) | `guardedHybridFiniteNumber(item.estimated_views)` vs expected | keys consistent; not a read-key rename |

Conclusion: for all five fields the read-back keys match the write keys; the per-batch refactor did not rename or move any
of them. None of the five is a "read-from-wrong-key" case in the extension code.

The signature of all six blockers firing simultaneously is `foundItems` being entirely null — the backend `/verify`
lookup returned no item for any accepted aweme_id (`backend_lookup.success_count = 0`, `missing_count = required`). When
every item is missing, all five per-field comparisons fail at once and the previous verdict read as a misleading all-field
persistence mismatch.

Minimal fix (no backend write semantics change, no backfill): the post-verify now computes
`allBackendItemsMissing = required > 0 && persisted.length === 0 && lookupAttempted` and, when true, emits the precise
verdict `beta_post_verify_failed_backend_items_not_found` (taking precedence over the generic persistence-mismatch verdict)
plus the blocker `all_backend_items_not_found_for_accepted_aweme_ids`. This tells the operator the read-back failed at the
backend lookup (the items were not found for these ids), not because each field was individually persisted to the wrong
key. `backend_lookup.success_count` / `missing_count` remain in the output for confirmation.

Honest scope note: this does not "restore beta_5_post_verify to passed" by itself, because passing requires the backend to
actually return the five fields for the accepted aweme_ids. If the lookup returns the items but a specific field truly
mismatches, the existing per-field blockers still fire correctly (verified by the field-comparison tests). If the lookup
returns nothing, the new verdict makes the real cause explicit and the recommended action is to re-run
`guarded_hybrid_collect_beta_5` so the backend has the items, then re-verify. No extension read-key change can make
post-verify pass while the backend returns zero items.

---

# Guarded Pipeline: next_action Foundational-Gate Fix, Beta Pilot-Contamination Guard, and Flag Rehydrate

## Update (follow-up): beta_5 post-verify still blocked + next_action skip

After the first round of fixes the operator reported:

- `guarded_hybrid_collect_beta_5_post_verify` is still `status=blocked`,
  `verdict=beta_post_verify_failed_persistence_mismatch`, with all five fields failing at once
  (title, thumbnail, raw_like_count, backend_share_count, estimated_views).
- Compact Guarded Pipeline Status reported `next_action=run_queue_completion_pilot_50` with top-level
  `blockers=[]`, advancing past the failing foundational gate.

### Root cause A (verified, my regression): next_action skipped the foundational gate

`buildCompactGuardedPipelineStatus` derived `nextSearchStart` purely from the highest passed pilot
milestone. When `pilot50MilestoneAuthorityPassed` (computed independently from durable batch-scoped Pilot
50 artifacts), the search `.slice()` started at `queue_completion_pilot_50` and the blocked foundational
step `guarded_hybrid_collect_beta_5_post_verify` (an earlier index) was never considered. So next_action
pointed past a failing foundational gate and top-level blockers were empty.

Fix: a foundational-gate guard. The foundational gates are `hybrid_only_dry_run_50`, `backend_shadow_5`,
`guarded_hybrid_collect_beta_5`, and `guarded_hybrid_collect_beta_5_post_verify`. The milestone
fast-forward (`milestoneFastForwardStart`) is now only honored when every foundational gate has passed
(`foundationalGatesPassed`). If any foundational gate is failing, `nextSearchStart` is forced to `0`, so
next_action is the blocked foundational step and its blockers are surfaced top-level.
`highest_passed_milestone` is reported as `none` while a foundational gate is failing, and a new
`foundational_gate` block in the status output makes the suppression explicit
(`milestone_fast_forward_suppressed_by_foundational_gate`, `first_failing_foundational_step`,
`next_action_blocked_at_foundational_gate`).

### Root cause B (beta field mismatch): not the per-batch read-back refactor

I read the full beta production write path
(`hybridCollectBetaProductionSourceFromSummary` → `persistHybridCollectBetaProductionSourceFromSummary`)
and the post-verify read-back helpers (`guardedHybridExpectedTitle`, `guardedHybridActualThumbnail`,
`guardedHybridExpectedThumbnail`, the `expected_*_by_aweme_id` maps, raw_like_count, share_count, and
estimated_views comparisons). The per-batch milestone refactor did not rename or change any of these keys
or helpers; the standalone beta builder only gained a backward-compatible optional `sourceOverride`
parameter that defaults to the original storage read. So the all-field mismatch is **not** produced by a
renamed/wrong read-back key in my code, and the beta write semantics were not changed.

The remaining way a prior build could still leave beta_5 post-verify stuck is a beta production artifact
already overwritten with Pilot data by the earlier (now-fixed) destructive swap. A Pilot artifact carries
`feature_flag_name=hybridEstimatedViewsStartCollectingPilotEnabled`, a `pilot_run_id`/`source_pilot_run_id`,
or a Pilot batch size of 10/50. Comparing such an artifact against the beta backend `/verify` items makes
every field mismatch even though the beta write itself was fine.

Fix (non-destructive, no auto-rerun, no backend write): `buildGuardedHybridCollectBetaPostVerifySummary`
now runs a contamination detector on the storage-read path only (`sourceOverride === undefined`). If the
shared beta production artifact carries Pilot markers, it returns
`verdict=beta_post_verify_inconclusive_source_artifact_contaminated_by_pilot` with explicit markers and a
recommendation to rerun `guarded_hybrid_collect_beta_5` to repopulate a clean artifact. It never repairs,
reruns, or writes anything. The in-memory override path used by Pilot post-verify is intentionally exempt
(it is expected to carry Pilot markers).

Note: a contaminated artifact whose `beta_batch_size` is 10/50 would also fail the `guarded_hybrid_collect_beta_5`
production step (which requires `beta_batch_size === 5`). If the operator's `beta_5` step is passing while
`beta_5_post_verify` fails, the contamination is via the batch-size-independent markers
(feature flag / pilot_run_id) or the verdict reflects a genuine backend persistence gap that requires a
clean beta rerun. The contamination guard surfaces this precisely instead of a misleading all-field
mismatch. Definitive confirmation requires re-running `guarded_hybrid_collect_beta_5` then
`guarded_hybrid_collect_beta_5_post_verify` against clean storage in the loaded extension.

---

# Guarded Beta Post-Verify Pollution + Pilot/Queue Flag Rehydrate Fix (first round)

This note documents two regressions introduced alongside the batch-scoped pilot milestone change and
their fixes in the Douyin capture extension
([`apps/extension-douyin-capture/src/popup.ts`](../apps/extension-douyin-capture/src/popup.ts)).

## Problem 1: `guarded_hybrid_collect_beta_5_post_verify` regressed to persistence mismatch

### Symptom

`guarded_hybrid_collect_beta_5_post_verify` reported `status=blocked`,
`verdict=beta_post_verify_failed_persistence_mismatch`, with every required field failing at once:
`title_missing_or_mismatched`, `thumbnail_missing_or_mismatched`, `raw_like_count_missing_or_mismatched`,
`backend_share_count_missing`, `estimated_views_missing_or_mismatched`,
`required_fields_or_estimated_views_not_persisted`. This milestone is the foundational gate and had
previously passed.

### Root cause (read path, not stored backend data)

The beta post-verify itself reads from the shared beta production key
(`hybridCollectBetaLatestProduction`) and performs a live backend `/verify` lookup. The verdict was
`failed_persistence_mismatch` (not `inconclusive_expected_values_missing`), so the source artifact still
had expected values; the mismatch was between expected values and the backend items being compared.

The real cause was the **pilot post-verify builder** mutating shared storage. It performed a destructive
temporary swap:

```text
set hybridCollectBetaLatestProduction = <pilot source>   // overwrite shared beta key with pilot data
rebuild beta post-verify summary                          // reads the now-polluted shared key
if (previousBetaSource) restore hybridCollectBetaLatestProduction = previousBetaSource
```

Two ways this corrupted the shared beta production artifact:

1. The restore was a plain `if`, not `try/finally`. If the rebuild (which performs a network `/verify`
   call) threw, the shared beta production key was left holding pilot data permanently.
2. The restore was skipped entirely when `previousBetaSource` was `null` (no prior beta production
   artifact), again leaving pilot data in the shared beta key.

Once the shared beta key held pilot data, the next `guarded_hybrid_collect_beta_5_post_verify` read pilot
items as if they were beta items and every expected-vs-actual comparison failed → all-field persistence
mismatch. The batch-scoped milestone change added another caller of this builder (the per-batch
diagnostic export), increasing how often the destructive swap ran.

### Fix (side-effect-free source override)

[`buildGuardedHybridCollectBetaPostVerifySummary()`](../apps/extension-douyin-capture/src/popup.ts) now
accepts an optional in-memory `sourceOverride`:

- `undefined` (default): read the shared beta production key as before.
- an explicit source (or `null`): use it verbatim and never touch storage.

The pilot post-verify builder now calls
`buildGuardedHybridCollectBetaPostVerifySummary({ ...source, beta_batch_size: expectedBatchSize })` and no
longer writes `HYBRID_COLLECT_BETA_LATEST_PRODUCTION_STORAGE_KEY` at all. The shared beta production
artifact is never mutated by pilot post-verify, so it cannot be polluted with pilot data.

Backend write semantics are unchanged: this is a read/verify path only. `estimated_views` is still never
copied into `view_count`, and no backend writes occur during verification.

## Problem 2: pilot/queue feature flags read `false` after popup reopen

### Symptom

`hybridEstimatedViewsStartCollectingPilotEnabled`,
`hybridStartCollectingPilotQueueCompletionEnabled`, and
`hybridStartCollectingPilot50QueueCompletionEnabled` were all `false` in the build despite being enabled
in earlier sessions. `next_action` recommended `run_queue_completion_pilot_50` while the flag to run it
was off.

### Root cause (missing checkbox rehydrate, accidental)

The flags persist to `chrome.storage.local` on change and the readers fall back to stored values when the
checkbox element is absent. But when the popup DOM is present, the readers return the live checkbox
`checked` state. Only the beta flag had an init-time rehydrate
(`applyHybridEstimatedViewsCollectBetaFlag()`) that restored its checkbox from storage on popup open. The
three pilot/queue flag checkboxes were never rehydrated, so after a popup reopen they defaulted to
unchecked and every reader returned `false` even though storage still held `true`.

This was an accidental gap, not an intentional disable. The flag state was never changed in code; the
checkboxes simply lost their persisted state on reopen.

### Fix (rehydrate all three flags on init)

[`applyHybridPilotAndQueueCompletionFlags()`](../apps/extension-douyin-capture/src/popup.ts) reads the
three stored flag values and restores each checkbox's `checked` state on popup init, mirroring the beta
flag behavior. It is called right after `applyHybridEstimatedViewsCollectBetaFlag()` during popup
initialization. After this, the readers reflect the operator's persisted choices across popup reopens.

The flags remain operator-default-false by design: unset storage still reads `false`. The fix only
restores values the operator previously set.

## Validation

- Extension build passes (`tsc` type check + bundling).
- `popupWorkflow.test.ts` static guards pass, including new regression assertions:
  - beta post-verify accepts a non-mutating source override and only reads the shared key without an
    override,
  - pilot post-verify uses the override and never writes the shared beta production key,
  - the three pilot/queue flags are rehydrated on popup init.
- The pre-existing, unrelated `wholeProfileHarvest.viewModel.test.ts` overcollection/calibration
  assertion failure is outside this change's scope (pilot/beta milestone code) and is not affected by
  these fixes.

## Safety Invariants (unchanged)

- No backend writes during verification; verify/lookup only.
- `estimated_views` is never copied into `view_count`.
- Full queue completion stays disabled.
- Queue completion uses exact aweme-id-only matching.
- The per-batch diagnostic remains read-only and no longer triggers shared-key mutation via pilot
  post-verify.
