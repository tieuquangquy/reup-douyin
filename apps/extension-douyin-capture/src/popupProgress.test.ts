import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  buildHarvestProgressViewModel,
  formatCount,
  formatDurationSeconds,
  harvestProgressPercent,
  isHarvestDisplayRunning,
  normalizeHarvestProgressForDisplay,
  normalizeHarvestState,
  phaseView,
  recentHarvestItems
} from "./popupProgress.js";
import type { FullModalHarvestProgress } from "./types.js";

const progress: FullModalHarvestProgress = {
  running: true,
  harvest_status: "running",
  current_state: "harvesting",
  phase: "extracting_metrics",
  target_count: 52,
  current_index: 6,
  current_aweme_id: "7623445952279416107",
  current_video_url: "https://www.douyin.com/user/profile?modal_id=7623445952279416107",
  harvested_count: 5,
  processed_count: 5,
  updated_count: 5,
  pending_count: 0,
  duplicate_count: 1,
  failed_count: 0,
  flushed_count: 5,
  flush_attempt_count: 6,
  elapsed_seconds: 78,
  average_seconds_per_item: 15.6,
  eta_seconds: 733,
  last_error: null,
  stopped_reason: null,
  last_flush_status: "success",
  next_flush_in_items: 3,
  last_extracted_metrics: {
    aweme_id: "7623445952279416107",
    source_used: "calibrated_point_dom",
    exact_aweme_runtime_found: false,
    exact_aweme_source: "none",
    raw_aweme_keys: null,
    fallback_used: null,
    rejected_reason: null,
    duration_seconds: 464,
    duration_text: "07:44",
    like_count: 136,
    comment_count: 3,
    favorite_count: 33,
    share_count: 12,
    posted_text: null,
    action_blocks_found: 4,
    ready_for_full_harvest: true,
    probe_status: "PASS"
  },
  recent_items: [
    { index: 1, aweme_id: "1", duration_seconds: 8, like_count: 8, comment_count: 8, favorite_count: 8, share_count: 8, posted_text: null, extraction_warning: null, status: "ok" },
    { index: 2, aweme_id: "2", duration_seconds: 9, like_count: 9, comment_count: 9, favorite_count: 9, share_count: 9, posted_text: null, extraction_warning: null, status: "ok" },
    { index: 3, aweme_id: "3", duration_seconds: 760, like_count: 278, comment_count: 9, favorite_count: 32, share_count: 13, posted_text: null, extraction_warning: null, status: "ok" },
    { index: 4, aweme_id: "4", duration_seconds: 464, like_count: 75_000, comment_count: 3, favorite_count: 32, share_count: 12, posted_text: null, extraction_warning: null, status: "ok" },
    { index: 5, aweme_id: "5", duration_seconds: 464, like_count: 136, comment_count: 3, favorite_count: 33, share_count: 12, posted_text: null, extraction_warning: null, status: "ok" }
  ]
};

const view = buildHarvestProgressViewModel(progress);
assert.equal(view.visible, true);
assert.equal(view.title, "Runtime: Safe Runner · Harvest running");
assert.equal(view.mainProgress, "Target index 6 / 52");
assert.equal(view.counts.Flushed, "5");
assert.equal(view.counts["Flush attempts"], "6");
assert.equal(view.navigation["Pause reason"], "none");
assert.equal(phaseView("extracting_metrics").label, "Extracting target metrics...");
assert.equal(phaseView("paused", "operator_stop").label, "Paused · operator_stop");
assert.equal(harvestProgressPercent(5, 52), 10);
assert.deepEqual(view.metrics, { Duration: "07:44", Likes: "136", Comments: "3", Favorites: "33", Shares: "12" });
assert.equal(formatDurationSeconds(464), "07:44");
assert.equal(formatCount(75_000), "75K");
assert.equal(view.recentItems.length, 5);
assert.match(view.recentItems[4] ?? "", /#5 OK · aweme 5 · Likes 136 · Comments 3 · Shares 12/);

const paused = normalizeHarvestState({
  ...progress,
  running: false,
  harvest_status: "paused",
  current_state: "paused",
  phase: "paused",
  stopped_reason: "operator_stop",
  can_resume: true
});
assert.equal(paused.harvest_status, "paused");
assert.equal(paused.phase, "paused");
assert.equal(buildHarvestProgressViewModel(paused).title, "Runtime: Safe Runner · Harvest paused");
assert.match(buildHarvestProgressViewModel(paused).errorLines.join("\n"), /Pause reason: operator_stop/);

const loadingNextVideoView = buildHarvestProgressViewModel({
  ...progress,
  running: false,
  harvest_status: "idle",
  current_state: "stopped",
  phase: "loading_next_video",
  stopped_reason: null,
  can_resume: false
});
assert.equal(loadingNextVideoView.visible, true);
assert.equal(loadingNextVideoView.phase.label, "Opening target modal...");
assert.equal(isHarvestDisplayRunning(loadingNextVideoView.visible ? normalizeHarvestProgressForDisplay({
  ...progress,
  running: false,
  harvest_status: "idle",
  current_state: "stopped",
  phase: "loading_next_video",
  stopped_reason: null,
  can_resume: false
}) : null), true);

const flushingView = buildHarvestProgressViewModel({
  ...progress,
  running: false,
  harvest_status: "idle",
  current_state: "stopped",
  phase: "flushing",
  pending_count: 2,
  stopped_reason: null,
  can_resume: false
});
assert.equal(flushingView.visible, true);
assert.equal(flushingView.phase.label, "Flushing target to backend...");
assert.equal(flushingView.running, true);

const unauthorizedPause = normalizeHarvestState({
  ...progress,
  running: false,
  harvest_status: "paused",
  current_state: "paused",
  phase: "paused",
  stopped_reason: null,
  can_resume: true
});
assert.equal(unauthorizedPause.harvest_status, "running", "paused without reason must not render as paused");
assert.equal(buildHarvestProgressViewModel(unauthorizedPause).title, "Runtime: Safe Runner · Harvest running");
assert.equal(isHarvestDisplayRunning(unauthorizedPause), true);

const flushFailureView = buildHarvestProgressViewModel({
  ...progress,
  running: false,
  harvest_status: "paused",
  current_state: "paused",
  phase: "paused",
  stopped_reason: "backend_flush_failed",
  last_error: "backend_unreachable: backend health check failed before flush response",
  pending_count: 1,
  last_flush_status: "queued",
  flush_url: "http://127.0.0.1:8000/douyin-extension/full-modal-harvest",
  flush_status_code: null,
  flush_error_code: "backend_unreachable",
  flush_error_message: "backend_unreachable: backend health check failed before flush response",
  flush_retryable: true,
  flush_next_action: "Start backend, then click Retry Flush Pending."
});
assert.match(flushFailureView.errorLines.join("\n"), /Flush failed: backend_unreachable/);
assert.match(flushFailureView.errorLines.join("\n"), /Pending preserved: 1/);

const integrityPauseView = buildHarvestProgressViewModel({
  ...progress,
  running: false,
  harvest_status: "paused",
  current_state: "paused",
  phase: "paused",
  stopped_reason: "operator_stop",
  integrity_mismatch_count: 2,
  last_integrity_error: "probe_aweme_id_mismatch",
  last_integrity_expected_aweme_id: "7623445952279416107",
  last_integrity_observed_aweme_id: "7623445952279416111"
});
assert.match(integrityPauseView.errorLines.join("\n"), /Integrity mismatches: 2/);
assert.match(integrityPauseView.errorLines.join("\n"), /Last integrity error: probe_aweme_id_mismatch/);
assert.match(integrityPauseView.errorLines.join("\n"), /Expected aweme: 7623445952279416107/);
assert.match(integrityPauseView.errorLines.join("\n"), /Observed aweme: 7623445952279416111/);

const completedView = buildHarvestProgressViewModel({
  ...progress,
  running: false,
  harvest_status: "completed",
  current_state: "completed",
  phase: "completed",
  target_count: 53,
  current_index: 53,
  harvested_count: 53,
  processed_count: 53,
  updated_count: 53,
  pending_count: 0,
  failed_count: 0,
  flushed_count: 53,
  flush_attempt_count: 11,
  last_error: null
});
assert.equal(completedView.title, "Runtime: Safe Runner · Harvest completed");
assert.equal(completedView.running, false);

assert.equal(
  recentHarvestItems(
    completedView.recentItems.map((text, index) => ({ index, aweme_id: text, duration_seconds: null, like_count: null, comment_count: null, favorite_count: null, share_count: null, posted_text: null, extraction_warning: null }))
  ).length,
  5
);

const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf8");
const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf8");
assert.doesNotMatch(popupHtml, /id="showRuntimeTransitionsButton"/, "popup must not render legacy runtime transition button in Phase 18A UI");
assert.match(popupSource, /normalizeHarvestProgressForDisplay\(response\.harvest_progress\)/, "stop harvest renders display-normalized progress");
assert.match(popupSource, /renderHarvestProgressPanel\(normalizedProgress\)/, "progress panel renders normalized progress");

assert.match(popupSource, /purpose:\s*"debug_scan_profile_final_count_and_scan_mode"/, "scan freeze log must use the compact Scan Profile debug purpose");
assert.match(popupSource, /terminal_state:\s*\{[\s\S]*final_counts:\s*\{[\s\S]*scan_job:\s*\{[\s\S]*runtime_progress:/, "scan freeze log must include the compact terminal/count/job/runtime sections");
assert.match(popupSource, /progress_samples_compact:\s*\{[\s\S]*last_20:\s*scanProgressFreezeLogSamples22C14M\.slice\(-20\)\.map\(\(entry\) => compactScanProgressSample22C14M\(entry\)\)/, "scan freeze log must compact last_20 samples through the thin sample formatter");
assert.match(popupSource, /execution_mode:\s*\{[\s\S]*scan_mode:[\s\S]*visible_dom_scrolling_expected:[\s\S]*api_pagination_inferred_from_scan_job:[\s\S]*scan_source_ledger:/, "scan freeze log must include compact execution mode evidence");
assert.match(popupSource, /real_api_pagination_page_accounting:\s*\{[\s\S]*first_page_raw_count:[\s\S]*last_page_raw_count:[\s\S]*last_page_accepted_count:[\s\S]*last_page_persisted_delta:[\s\S]*per_page_raw_counts:[\s\S]*per_page_accepted_counts:[\s\S]*per_page_persisted_totals:[\s\S]*final_has_more:[\s\S]*final_status_code:[\s\S]*raw_accounting_present:[\s\S]*raw_accounting_unavailable_reason:/, "scan freeze log must include real per-page API accounting and explicit unavailable reason");
assert.match(popupSource, /preferRealApiAccounting[\s\S]*realApiPageCount[\s\S]*activeFetchPageCount = \(preferRealApiAccounting \? realApiPageCount : null\)[\s\S]*activeFetchRequestCount = \(preferRealApiAccounting \? realApiRequestCount : null\)/, "scan freeze log must prefer real API pagination page\/request counts over stale zero active-fetch diagnostics");
assert.match(popupSource, /raw_to_persisted_accounting:\s*\{[\s\S]*raw_items_total:[\s\S]*accepted_targets_total:[\s\S]*repository_write_input_count:[\s\S]*repository_write_total_after:/, "scan freeze log must include raw-to-persisted accounting without raw IDs");
assert.match(popupSource, /countSemanticsBlock = \{[\s\S]*displayed_profile_count:[\s\S]*api_raw_count:[\s\S]*api_unique_count:[\s\S]*collectable_count:[\s\S]*persisted_count:[\s\S]*unavailable_or_unlisted_count:[\s\S]*count_semantics_status:[\s\S]*count_semantics_reason:/, "scan freeze log must include count semantics diagnostics through the shared count semantics block");
assert.match(popupSource, /count_semantics:\s*countSemanticsBlock/, "scan freeze log must render count semantics from the shared stable count semantics block");
assert.match(popupSource, /countSemanticsBlock = \{[\s\S]*over_displayed_count:[\s\S]*over_displayed_reason:[\s\S]*over_displayed_validation_status:[\s\S]*over_displayed_same_profile_validated:[\s\S]*over_displayed_extra_source:[\s\S]*over_displayed_extra_ids_sample:[\s\S]*over_displayed_extra_ids_exact:[\s\S]*over_displayed_extra_items_exact:[\s\S]*over_displayed_itemized_reason_summary:[\s\S]*requested_profile_identifier:[\s\S]*api_response_profile_identifier:[\s\S]*repository_profile_identifier:/, "scan freeze log count semantics block must preserve stable over-display forensic fields including exact itemized evidence");
assert.match(popupSource, /debug_over_display_itemized_forensics_json:\s*debugOverDisplayItemizedForensicsJson/, "scan freeze log must expose a real nested JSON object for operators, not an escaped JSON string");
assert.match(popupSource, /terminal_exact_item_evidence_missing[\s\S]*needs_manual_overcollection_validation/, "scan freeze log must emit explicit exact-item fallback fields instead of empty over-display forensics when over_displayed_count is positive");
assert.match(popupSource, /const debugOverDisplayItemizedForensicsJson = \{[\s\S]*purpose:\s*"debug_over_display_itemized_forensics"[\s\S]*runtime_versions:\s*\{[\s\S]*terminal_state:\s*\{[\s\S]*popup_resolved_state_source:\s*resolvedPopupState\.source[\s\S]*popup_primary_action_source:\s*resolvedPopupState\.primaryActionSource[\s\S]*popup_terminal_state_source:\s*resolvedPopupState\.terminalStateSource[\s\S]*popup_review_card_source:\s*resolvedPopupState\.reviewCardSource[\s\S]*popup_fallback_suppressed:\s*resolvedPopupState\.fallbackSuppressed \? "yes" : "no"[\s\S]*popup_validated_same_profile_override_applied:\s*resolvedPopupState\.validatedSameProfileOverrideApplied \? "yes" : "no"[\s\S]*final_counts:\s*\{[\s\S]*scan_job:\s*\{[\s\S]*real_api_pagination_page_accounting:\s*\{[\s\S]*raw_to_persisted_accounting:\s*\{[\s\S]*count_semantics:\s*countSemanticsBlock[\s\S]*final_gap_accounting:\s*\{[\s\S]*scan_health:\s*\{[\s\S]*active_vs_inferred_api_diagnostics:\s*\{[\s\S]*review_reasons:\s*resolvedPopupState\.reviewReasons[\s\S]*known_contradictions_to_debug:\s*resolvedPopupState\.knownContradictions/, "scan freeze log forensic JSON block must preserve the full stable operator-facing schema with resolved popup authority diagnostics");
assert.match(popupSource, /if \(!state\) return \{ purpose:\s*"debug_scan_profile_final_count_and_scan_mode", state:\s*null, reason:\s*"whole_profile_state_missing", debug_over_display_itemized_forensics_json:\s*null \}/, "scan freeze log must preserve the forensic JSON field even when state is missing");
assert.match(popupSource, /expected_count_semantics:\s*\{[\s\S]*expected_count:[\s\S]*expected_vs_api_count_meaning:/, "scan freeze log must preserve legacy expected count semantics context");
assert.match(popupSource, /final_gap_accounting:\s*\{[\s\S]*gap_count:[\s\S]*gap_reason:[\s\S]*gap_classification:[\s\S]*evidence:[\s\S]*tail_reconcile_unrecovered_reason:/, "scan freeze log must include final gap diagnostics and tail reconciliation summary");
assert.match(popupSource, /active_vs_inferred_api_diagnostics:\s*\{[\s\S]*active_profile_post_fetch_attempted:[\s\S]*inferred_page_count_from_scan_job:[\s\S]*inconsistency_reason:[\s\S]*all_inconsistency_reasons:/, "scan freeze log must compare active fetch diagnostics against scan-job inference");
assert.match(popupSource, /ui_contract_status:\s*\{[\s\S]*profile_scan_ready:[\s\S]*scan_finalization_result:[\s\S]*primary_action_key:[\s\S]*popup_resolved_state_source:[\s\S]*popup_primary_action_source:[\s\S]*popup_terminal_state_source:[\s\S]*popup_review_card_source:[\s\S]*popup_fallback_suppressed:[\s\S]*popup_validated_same_profile_override_applied:[\s\S]*blocking_incomplete_tone_present:[\s\S]*completed_with_warning_non_blocking_expected:/, "scan freeze log must include resolved popup authority diagnostics in UI contract status");
assert.match(popupSource, /rawItemsTotal = popupFreezeNumber22C14M\(diagnostics\.api_pagination_raw_items_total\)[\s\S]*acceptedTargetsTotal = popupFreezeNumber22C14M\(diagnostics\.api_pagination_accepted_targets_total\)/, "scan freeze log raw item accounting must prefer persisted API diagnostics instead of silently fabricating zero while accepted targets exist");
assert.match(popupSource, /inconsistentReasons = \[[\s\S]*scan_job_implies_api_pagination_but_real_raw_accounting_missing[\s\S]*positive_gap_with_gap_reason_none[\s\S]*completed_with_warning_ready_state_should_not_render_blocking_incomplete/, "scan freeze log must emit explicit inconsistency reasons for contradictory API and UI evidence");
assert.match(popupSource, /const resolvedPopupState = resolveAuthoritativePopupState22C14S\(/, "scan freeze log must resolve one authoritative popup state before emitting terminal diagnostics");
assert.match(popupSource, /profile_scan_ready:\s*resolvedPopupState\.profileScanReady/, "scan freeze log readiness must use resolved popup authority instead of stale layer-only readiness");
assert.match(popupSource, /primary_action_key:\s*resolvedPopupState\.primaryActionKey/, "scan freeze log terminal state must include resolved popup primary action authority");
assert.match(popupSource, /popup_resolved_state_source:\s*resolvedPopupState\.source/, "scan freeze log must expose resolved popup authority source");
assert.match(popupSource, /popup_fallback_suppressed:\s*resolvedPopupState\.fallbackSuppressed \? "yes" : "no"/, "scan freeze log must expose whether validated same-profile suppressed stale fallback review state");
assert.match(popupSource, /popup_validated_same_profile_override_applied:\s*resolvedPopupState\.validatedSameProfileOverrideApplied \? "yes" : "no"/, "scan freeze log must expose whether validated same-profile override was applied");
assert.match(popupSource, /validatedSameProfile[\s\S]*over_displayed_validation_status === "validated_same_profile"[\s\S]*over_displayed_same_profile_validated === "yes"[\s\S]*scan_health_verdict === "ready_api_over_displayed_count"[\s\S]*count_semantics_status === "completed_with_api_over_displayed_count"/, "resolved popup authority must recognize validated same-profile terminal scans from same-run diagnostics");
assert.match(popupSource, /reviewFallbackRequested[\s\S]*scan_health_verdict === "failed_or_warning_overcollection_validation_needed"[\s\S]*count_semantics_reason === "over_displayed_itemized_validation_missing"/, "resolved popup authority must still detect unresolved overcollection review fallback conditions");
assert.match(popupSource, /fallbackSuppressed = validatedSameProfileOverrideApplied && reviewFallbackRequested/, "resolved popup authority must suppress stale review fallback only when validated same-profile canonical readiness wins");
assert.match(popupSource, /reviewReasons = fallbackSuppressed[\s\S]*\? \[\][\s\S]*scan_success_overcollection_validation_required/, "resolved popup authority must clear review reasons when validated same-profile suppresses stale review fallback");
assert.match(popupSource, /diagnostics\.scan_health_verdict === "failed_overcollection_outside_profile"[\s\S]*outside_profile_verdict_without_itemized_offenders/, "resolved popup authority must preserve outside-profile review contradictions");
assert.match(popupSource, /canonicalPrimaryAction\.key === "review_overcollection"[\s\S]*review_overcollection_without_warning_review_alert/, "resolved popup authority must preserve review-overcollection alert consistency checks");
assert.match(popupSource, /countSemanticsMismatchExplained[\s\S]*completed_with_displayed_count_mismatch[\s\S]*completed_with_partial_secondary_recovery[\s\S]*displayed_count_not_fully_collectable/, "scan freeze log must treat explained displayed-count mismatch as count semantics, not a contradiction");
assert.match(popupSource, /state\.scan_job\.status === "completed"[\s\S]*state\.scan_job\.remaining_estimate != null[\s\S]*state\.scan_job\.remaining_estimate > 0[\s\S]*!expectedCountSemanticsMismatchProven[\s\S]*\? "scan_job_completed_with_remaining_estimate"/, "scan freeze log must suppress remaining-estimate contradiction when count semantics explains the gap");
assert.match(popupSource, /scan_success_overcollection_validation_required/, "scan freeze log must classify overcollection validation required as expected review state instead of generic readiness contradiction");
assert.doesNotMatch(popupSource, /scan_success_but_overcollection_validation_required/, "scan freeze log must not classify expected overcollection validation review as a contradiction");
assert.match(popupSource, /known_contradictions_to_debug:\s*resolvedPopupState\.knownContradictions/, "scan freeze log must include known contradictions through resolved popup authority");
assert.doesNotMatch(popupSource, /profile_url:\s*state\.profile_url/, "scan freeze log must not emit raw profile URLs");
assert.doesNotMatch(popupSource, /id:\s*state\.scan_job\.scan_job_id/, "scan freeze log must not emit raw scan job identifiers");
assert.doesNotMatch(popupSource, /last_20:\s*scanProgressFreezeLogSamples22C14M\.slice\(-20\)\s*[,}]/, "scan freeze log must not emit full verbose last_20 sample objects");
assert.match(popupSource, /profile_url_present:\s*Boolean\(state\.profile_url\)/, "scan freeze log must represent profile URL only as a presence boolean");
assert.match(popupSource, /profile_identifier_present:\s*Boolean/, "scan freeze log must represent profile identity only as a presence boolean");
assert.match(popupHtml, /<summary>Scan Progress Freeze Log<\/summary>/, "advanced details label must remain Scan Progress Freeze Log");
assert.match(popupHtml, /compact JSON[\s\S]*without private IDs or full URLs/, "scan freeze log helper copy must describe compact sanitized JSON");

const popupProgressSource = readFileSync(new URL("./popupProgress.ts", import.meta.url), "utf8");
assert.match(popupProgressSource, /displayProgress\.phase === "loading_next_video"[\s\S]*displayProgress\.phase === "waiting_modal_change"[\s\S]*displayProgress\.phase === "flushing"/, "popup progress visibility must preserve richer running phases via phase");
assert.match(popupProgressSource, /current_state: "harvesting"[\s\S]*phase: runningPhase/, "popup progress normalization must keep coarse current_state while preserving richer running phase");
assert.match(popupProgressSource, /progress\.phase === "loading_next_video"[\s\S]*progress\.phase === "waiting_modal_change"[\s\S]*progress\.phase === "flushing"/, "popup progress canonical status must treat richer running phases as active");

assert.match(
  recentHarvestItems([{ index: 9, aweme_id: "aweme-x", duration_seconds: null, like_count: 1, comment_count: 2, favorite_count: 3, share_count: 4, posted_text: null, extraction_warning: null, status: "ok", data_integrity_status: "mismatch", data_integrity_reason: "payload_aweme_id_mismatch", duplicate_signature_warning: "duplicate_metric_signature_detected" }])[0] ?? "",
  /MISMATCH payload_aweme_id_mismatch.*duplicate_metric_signature_detected/
);

console.log("popup progress tests passed");
