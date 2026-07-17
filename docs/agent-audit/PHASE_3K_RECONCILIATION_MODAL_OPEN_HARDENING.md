# Phase 3K Reconciliation Modal-Open Hardening

## Scope

Phase 3K hardens the Phase 3J profile-level reconciliation and safe-batch collection paths after the reported remaining issues, including the follow-up live-log defects where the popup could re-dispatch `Start Collecting` during an active safe-batch run and `Profile already collected count` could remain at stale `0` despite backend profile counts/items proving captured videos existed:

- Reset / Refresh Profile could still need clearer proof that profile-level Capture Inbox source was used and that `modal_id` query parameters were ignored.
- A `modal_navigation_timeout` while opening a `profile_url_modal` could stop collection before backend save.
- Active collection progress copy could still look unstable between item-level checkpoints.
- Popup primary action could flicker from `Collecting videos...` back to `Start Collecting`, allowing duplicate start clicks and user-facing `Action blocked` copy while a batch runner was still active.
- `Profile already collected count` could show `0` after scan finalization even when the profile-level Capture Inbox source returned captured item counts and matched saved items.

Non-goals:

- No Scan Profile scanner/autoscroll changes.
- No backend validation loosening.
- No full-modal harvest payload schema semantic changes.
- No weakening of Phase 3E profile-safe capture-session verification.
- No queue, calibration, capture-session, or current-index clearing during recoverable item failures.
- No Resume behavior changes for normal terminal safe-batch continuation.

## Authoritative popup reconciliation

[`apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts) adds a popup-only authoritative reconciliation layer that runs before counter rendering, primary-action selection, click dispatch, and final view-model export. The exported helpers are [`deriveAuthoritativeRunnerLock()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts), [`deriveAuthoritativeProfileCounters()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts), and [`sanitizePopupViewState()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts).

[`apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/readiness.ts) delegates primary-action locking through [`sanitizeCanonicalPrimaryAction()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts). [`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts) calls [`sanitizePopupViewState()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts) immediately before exporting scanner view models. [`apps/extension-douyin-capture/src/popup.ts`](../../apps/extension-douyin-capture/src/popup.ts) uses [`deriveAuthoritativeRunnerLock()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts) in the duplicate-click guard before dispatching Start Collecting.

The lock is true only for non-terminal, non-paused collection activity and uses these fields:

- Fresh `workflow.collection.status`, including `running` and `opening_target`.
- Fresh scanner ownership fields `workflow.active_task` or `workflow.action_lock` for `collect_videos`, `start_collecting`, `run_batch`, or `batch_collect`.
- Recent safe-batch diagnostics with `batch_heartbeat_at` inside the authoritative two-minute staleness window plus `batch_collection_ui_state === "collecting_videos_locked"`, a non-empty `active_runner_target`, or a non-empty `batch_run_id`.
- Active stage diagnostics through `start_collecting_stage` values such as `clicked`, `session_verified`, `target_selected`, `opening_target`, `extracting_metadata`, `building_payload`, `guarding_payload`, `verifying_item`, `saving_item`, `batch_collecting`, and `after_checkpoint`.
- Item-level runner evidence with `one_item_status === "running"`.

Terminal states such as `batch_safe_mode_completed` are intentionally not locked, so pending terminal batches continue to show `Continue Next 10`. Real paused/interrupted states still expose `Resume`.

[`apps/extension-douyin-capture/src/popup.ts`](../../apps/extension-douyin-capture/src/popup.ts) suppresses duplicate `start_collecting` clicks before dispatching the workflow if [`deriveAuthoritativeRunnerLock()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts) is active. The popup records:

- `collection_runner_active: "yes"`
- `primary_action_locked_reason: "collection_running"`
- `primary_action_lock_source` with the exact source field.
- `duplicate_start_suppressed: "yes"`

The normal active runner primary action remains disabled with `Collecting videos...` but no longer surfaces the old duplicate-click `Collection is already running.` disabled reason as user-facing action-blocked copy.

## Reconciliation diagnostics

The extension continues to prefer the profile-level Capture Inbox source before session fallback. Phase 3K adds/strengthens diagnostics in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts):

- `backend_reconciliation_modal_id_ignored`
- `backend_reconciliation_error_code`
- `backend_reconciliation_fallback_source`

Expected source diagnostics when the profile endpoint succeeds:

- `backend_reconciliation_source: capture_inbox_profile_items`
- `backend_reconciliation_endpoint: /douyin-extension/capture-inbox/profile-items`
- `backend_reconciliation_current_session_only: "no"`
- `backend_reconciliation_used_capture_inbox_card_source: "yes"`

If the profile source fails, the extension records the error code and may fall back to session/session-items, but that fallback is labelled and is not reported as the authoritative Capture Inbox card source.

### Already-collected counter source

The stale `0` happened because scan finalization could render/profile-store count diagnostics that did not apply the profile-level backend reconciliation result, even though backend data already contained captured counts/items. The profile counter contract now uses backend profile matched items as the canonical already-collected counter source after reconciliation.

The active counter fields are:

- `backend_reconciliation_counter_source: "backend_profile_matched_items"`
- `backend_reconciliation_applied_to_profile_counters: "yes"`
- `backend_reconciliation_backend_profile_captured_count`
- `backend_reconciliation_backend_ready_count`
- `backend_reconciliation_backend_needs_action_count`
- `backend_reconciliation_backend_item_count`
- `backend_reconciliation_matched_count`
- `backend_reconciliation_unmatched_backend_count`
- `backend_reconciliation_unmatched_scan_count`
- `profile_already_collected_count_before_apply`
- `profile_already_collected_count_after_apply`
- `profile_already_collected_count`
- `profile_eligible_count`
- `pending_count`
- `profile_counters_overwritten_after_reconciliation`

Authoritative backend item matching normalizes these alias fields:

- `aweme_id`
- `source_video_external_id`
- `video_external_id`
- `external_id`
- `metadata_json.extracted_aweme_id`
- `metadata_json.target_aweme_id`
- `metadata_json.profile_card_evidence.aweme_id`
- `raw_payload_json.aweme_id`
- `raw_payload_json.profile_card_evidence.aweme_id`

Scan-queue matching normalizes `aweme_id`, `source_video_external_id`, `video_external_id`, `external_id`, `target_aweme_id`, `extracted_aweme_id`, and aweme IDs parsed from `source_url` video paths or `modal_id` query parameters. Current-batch-only fields such as `saved_count_after_batch`, `saved_count_after`, `batch_success_count`, and `recent_batch_item_results.length` are not used as total profile already-collected authority.

For the live-log shape of queue total `111`, backend captured `30`, and pending `81`, the expected displayed values are `Profile already collected count: 30`, `Profile eligible count: 81`, and `Pending count: 81` when the 30 backend items match scanned aweme IDs. If backend captured and matched counts differ, the matched count drives queue-safe profile counters and unmatched diagnostics explain the gap.

## Modal navigation timeout behavior

`modal_navigation_timeout` is now treated as a recoverable safe-batch item error in [`apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/controller.ts).

Behavior:

- The failed item is marked retryable/recoverable through the existing safe-batch recoverable-item path.
- Backend save is not called if modal open and payload extraction did not succeed.
- Queue, calibration, capture session, current index, active task, and action lock are preserved.
- Existing repeated-failure handling remains in place to avoid infinite loops.

Added modal-open diagnostics include:

- `modal_open_attempt_count`
- `modal_open_strategy`
- `modal_open_expected_url`
- `modal_open_actual_url`
- `modal_open_timeout_ms`
- `modal_open_retry_used`
- `modal_open_fallback_used`
- `modal_open_result`
- `modal_open_recoverable_skip`
- `target_marked_retry_due_to_modal_open_timeout`
- `collect_backend_write_attempted`

For a recoverable open timeout before extraction, expected diagnostics include:

```text
modal_open_recoverable_skip: "yes"
collect_backend_write_attempted: false
backend_item_save_called: false
modal_open_result: "timeout"
```

## Active collecting UI behavior

[`apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/viewModel.ts) now renders stable active-batch progress copy from safe-batch diagnostics:

```text
Collecting batch: {processed}/{selected_count} processed, {success_count} saved.
```

While the batch is actively running, the primary action remains non-reentrant and disabled with label:

```text
Collecting videos...
```

Terminal behavior remains unchanged:

- `batch_safe_mode_completed` with pending items shows `Continue Next 10`.
- Completed/no-pending states do not show continuation copy.
- Real paused/interrupted states still expose Resume.
- Unrecoverable failures still show failure state/action.

## Phase 3M popup display metrics authority

Phase 3M adds [`deriveReconciledPopupMetrics()`](../../apps/extension-douyin-capture/src/wholeProfileHarvest/authoritativePopupState.ts) as the final popup display-metrics object computed after backend reconciliation and before rendering/export sanitization. The helper intentionally separates profile-level counters from active-runner/current-batch counters so raw collection pending values cannot overwrite profile tiles.

Profile-level display metrics are:

- `profile_total_count`
- `already_collected_count`
- `new_count`
- `eligible_count`
- `queue_count`

When backend reconciliation authority exists, `new_count`, `eligible_count`, and `queue_count` all use the same reconciled formula:

```text
max(0, profile_total_count - already_collected_count)
```

Active runner metrics remain available separately as `active_runner_remaining_count`, `active_runner_current_index`, `active_runner_saved_this_run`, `active_runner_failed_this_run`, and `active_runner_skipped_this_run`. These values may reflect raw current-run pending state, but they are labelled as active-runner state and do not drive the profile-level `New` or `Queued` tiles.

The popup metrics diagnostics include:

- `popup_metrics_reconciler_ran`
- `popup_metrics_profile_total_source`
- `popup_metrics_already_collected_source`
- `popup_metrics_new_count`
- `popup_metrics_eligible_count`
- `popup_metrics_queue_count`
- `popup_metrics_active_runner_remaining_count`
- `popup_metrics_raw_pending_count`
- `popup_metrics_raw_batch_pending_count`
- `popup_metrics_profile_tiles_authority`
- `popup_metrics_raw_pending_ignored_for_profile_tiles`

For the live-log shape where profile total is `111`, backend matched/captured count is `30`, raw pending is `109`, and raw batch pending is `111`, popup profile tiles now render `New: 81`, `Already collected: 30`, and `Queue: 81`. The raw `109` remains visible only as active-runner/raw diagnostic state.

## Tests

Focused tests were added/updated in:

- [`apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.viewModel.test.ts)
- [`apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts`](../../apps/extension-douyin-capture/src/wholeProfileHarvest.readiness.test.ts)
- [`apps/extension-douyin-capture/src/popupWorkflow.test.ts`](../../apps/extension-douyin-capture/src/popupWorkflow.test.ts)

Coverage includes:

- Recoverable `modal_navigation_timeout` does not call backend save before extraction.
- Recoverable modal timeout preserves queue/session/calibration/action lock and records requested diagnostics.
- Reconciliation records `modal_id` ignored, profile-source error code, and labelled fallback source.
- Active collecting primary action remains `Collecting videos...` and progress detail remains stable.
- Recent heartbeat/batch diagnostics lock the active runner; stale workflow/diagnostic locks do not.
- Duplicate popup `Start Collecting` clicks are suppressed before dispatch and record diagnostics.
- Backend profile reconciliation applies matched backend items to profile counters instead of stale scan summary counts.
- Alias matching covers source/video/external IDs plus nested `metadata_json`, `raw_payload_json`, and scan-queue URL IDs.
- Sanitizer coverage corrects stale upstream `start_collecting` and stale already-collected `0` before render/export diagnostics.
- Reconciled popup metrics force visible `New`/`Queued` tiles to the backend-authoritative profile remaining count while raw pending is preserved only as active-runner/internal state.
- Active collection keeps `Collecting videos...` while profile-level `New`/`Queued` remain reconciled instead of jumping to raw pending.
- Batch completion updates `New`/`Queued` from the latest backend authority and preserves `Continue Next 10` continuation behavior.
- Existing `Continue Next 10` terminal behavior remains covered by Phase 3J tests and authoritative continuation tests.

## Manual validation checklist

1. Open the target Douyin profile.
2. Reset / Refresh Profile.
3. Confirm diagnostics show the profile-level Capture Inbox source when available.
4. Confirm URLs with `modal_id` report `backend_reconciliation_modal_id_ignored: "yes"`.
5. Start safe-batch collection.
6. If a modal open timeout occurs, confirm backend save is not attempted for that item.
7. Confirm the batch remains recoverable and does not clear queue, calibration, session, or current index.
8. Confirm active UI shows `Collecting videos...` and stable batch progress copy until terminal state.
9. Confirm duplicate Start Collecting clicks during an active run do not dispatch and record `duplicate_start_suppressed: "yes"` plus `primary_action_lock_source`.
10. Confirm terminal pending state still shows `Continue Next 10` and records continuation diagnostics.
