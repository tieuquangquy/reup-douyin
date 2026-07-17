import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  LEGACY_DEBUG_BUTTON_IDS,
  PRODUCTION_BUTTON_IDS,
  SHOW_LEGACY_DEBUG_ACTIONS,
  CAPTURE_SESSION_REQUIRED_MESSAGE,
  CONTENT_SCRIPT_VIEWPORT_RETRY_MESSAGE,
  CONTENT_SCRIPT_VIEWPORT_UNAVAILABLE,
  MODAL_REQUIRED_MESSAGE,
  classifyDouyinPopupPage,
  computeCurrentBlockingReason,
  createSmartState,
  describeHarvestState,
  displayProbeStatus,
  isFreshModalProbe,
  nextRequiredAction,
  reconcileSmartState,
  smartHarvestStartOptions,
  smartStateFromHarvestProgress,
  startHarvestGuard,
  validateRightRailCalibration,
  viewportWarningMessage
} from "./popupWorkflow.js";
import type { DouyinPageViewport, FullModalHarvestProgress, FullModalHarvestProbeResult, RightRailCalibration } from "./types.js";

const popupHtml = readFileSync(new URL("../public/popup.html", import.meta.url), "utf-8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf-8");
const popupWorkflowSource = readFileSync(new URL("./popupWorkflow.ts", import.meta.url), "utf-8");
const extensionBackendClientSource = readFileSync(new URL("./extensionBackendClient.ts", import.meta.url), "utf-8");
const contentScriptSource = readFileSync(new URL("./contentScript.ts", import.meta.url), "utf-8");

function pageViewport(width: number, height: number, modalId = "7634"): DouyinPageViewport {
  return {
    width,
    height,
    visual_width: width,
    visual_height: height,
    device_pixel_ratio: 1,
    url: `https://www.douyin.com/user/profile?modal_id=${modalId}`,
    modal_id: modalId,
    source: "content_script"
  };
}

assert.equal(PRODUCTION_BUTTON_IDS.length, 9);
assert.doesNotMatch(popupHtml, /id="verifyProfileButton"/, "popup must not render the legacy verify button in the Action Deck shell");
assert.doesNotMatch(popupHtml, /id="runHarvestButton"/, "popup must not render the legacy extract button in the Action Deck shell");
assert.doesNotMatch(popupHtml, /id="prepareBackendSessionButton"/, "popup must not render the legacy save-session button in the Action Deck shell");
assert.doesNotMatch(popupHtml, /id="buildPayloadPreviewButton"/, "popup must not render the legacy payload-preview button in the Action Deck shell");
assert.equal(SHOW_LEGACY_DEBUG_ACTIONS, false);
assert.doesNotMatch(popupHtml, /Smart Capture & Harvest/, "popup must not expose legacy Smart Capture product action");
assert.doesNotMatch(popupHtml, /id="harvestMode"/, "popup must not expose legacy incremental harvest mode selection");
assert.doesNotMatch(popupHtml, /<select id="harvestMode"[\s\S]*value="new_and_incomplete"/, "popup must not expose legacy smart harvest mode options");
assert.doesNotMatch(popupHtml, /<select id="harvestMode"[\s\S]*value="new_only"/, "popup must not expose legacy smart harvest mode options");
assert.doesNotMatch(popupHtml, /<select id="harvestMode"[\s\S]*value="refresh_all"/, "popup must not expose legacy smart harvest mode options");
assert.doesNotMatch(popupHtml, /id="verifyModalHarvestCoverageButton"/, "popup must not expose legacy modal harvest coverage action");
assert.match(popupHtml, /id="scannerPrimaryActionButton"/, "popup must expose the scanner primary action");
assert.match(popupSource, /const wholeProfileHarvestModeSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestMode"\);/, "popup must keep the advanced mode control wiring in source");
assert.match(popupSource, /const wholeProfileHarvestBatchSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestBatch"\);/, "popup must keep the advanced batch control wiring in source");
assert.match(popupSource, /const wholeProfileHarvestSpeedSelect = document\.querySelector<HTMLSelectElement>\("#wholeProfileHarvestSpeed"\);/, "popup must keep the advanced speed control wiring in source");
assert.match(popupSource, /function setWholeProfileTabBadges\(state: WholeProfileHarvestState, readiness: ReturnType<typeof getWholeProfileHarvestReadiness>\): void \{[\s\S]*deriveAuthoritativeRunnerLock\(state\)[\s\S]*canonicalUiState === "waiting_for_active_tab" \|\| canonicalUiState === "paused_tab_inactive"[\s\S]*\? "Paused"/s, "Run tab badge must use authoritative runner-lock paused states for waiting-tab runtime");

for (const id of LEGACY_DEBUG_BUTTON_IDS) {
  assert.doesNotMatch(popupHtml, new RegExp(`id="${id}"[^>]*>`), `normal popup must not render legacy debug button ${id}`);
}

assert.doesNotMatch(popupHtml, /id="legacyDebugSection"/, "normal popup must not render legacy debug section");
assert.match(popupHtml, /aria-label="Scanner health"/, "popup must expose the scp scanner health row");
assert.match(popupHtml, /data-feature="advanced-harvest-options"/, "popup must keep harvest options in Advanced");
assert.match(popupHtml, /data-feature="calibration-details"/, "popup must keep calibration controls in Advanced");
assert.match(popupHtml, /Douyin Scanner/, "popup must expose the scanner header branding");
assert.match(popupHtml, /id="scannerOpenCaptureInboxButton"/, "popup must expose the Capture Inbox footer action");
assert.match(popupHtml, /id="scannerOpenAdvancedButton"/, "popup must expose the Advanced footer action");
assert.match(popupHtml, /id="scannerResetButton"/, "popup must expose the Reset footer action");
assert.match(popupHtml, /Results Dashboard<\/h2>/, "popup must have results section");
assert.doesNotMatch(popupHtml, /<h2>Controls<\/h2>/, "popup must remove the old standalone controls section from Run");
assert.match(popupHtml, /Advanced Details/, "popup must have Advanced Details section");
assert.match(popupHtml, /id="scannerPrimaryActionButton"/, "popup must expose a single scanner primary workflow button");
assert.match(popupHtml, /id="copyBackendErrorDetailsButton"[\s\S]*Copy Backend Error Details/, "popup must expose a backend error details copy button in Advanced details");
assert.match(popupHtml, /id="backendErrorDetailsPreview"[\s\S]*hidden/, "popup must expose a short redacted backend error details preview");
assert.match(popupHtml, /Collecting comparison test[\s\S]*validation-only dry-run[\s\S]*without backend writes or production collect state mutation/, "popup must explain the bounded dry-run collecting comparison workflow in Advanced details");
assert.match(popupHtml, /id="modalWholeProfileSampleSize"[\s\S]*value="5" selected[\s\S]*5 videos comparison[\s\S]*value="10"[\s\S]*10 videos comparison[\s\S]*value="25"[\s\S]*Hybrid Validation Dry Run \(25\)[\s\S]*value="50"[\s\S]*Hybrid Validation Dry Run \(50\)/, "popup must expose explicit 5, 10, 25, and 50 item dry-run validation sample sizes");
assert.match(popupHtml, /id="runModalWholeProfileTestButton"[\s\S]*Run Collecting Comparison Test/, "popup must expose a clearly named bounded collecting comparison entry button without pretending a fixed size in the label");
assert.match(popupHtml, /id="modalWholeProfileTestDisabledReason"/, "popup must expose a visible disabled-reason area for the collecting comparison action");
assert.match(popupHtml, /id="modalWholeProfileComparisonPanel"[\s\S]*Collecting Comparison Log/, "popup must expose a clearly named collecting comparison log panel in Advanced details");
assert.match(popupHtml, /id="modalWholeProfileComparisonPlaceholder"[\s\S]*Run the comparison test to generate a log\./, "popup must expose a visible collecting comparison placeholder before any run exists");
assert.match(popupHtml, /id="copyModalWholeProfileDecisionSummaryButton"[\s\S]*Copy Hybrid-Only Dry Run Decision Summary/, "popup must expose a dedicated hybrid-only dry-run decision summary copy button");
assert.match(popupHtml, /id="copyModalWholeProfileComparisonButton"[\s\S]*Copy Full Collecting Comparison Log/, "popup must preserve a dedicated full collecting comparison copy button");
assert.match(popupHtml, /Hybrid-Only Dry Run Decision Summary[\s\S]*id="modalWholeProfileDecisionSummaryPreview"/, "popup must expose a compact hybrid-only decision summary preview block");
assert.match(popupHtml, /Full Collecting Comparison Log[\s\S]*id="modalWholeProfileComparisonPreview"/, "popup must preserve the full modal comparison preview block");
assert.match(popupHtml, /Hybrid-only validation[\s\S]*Validation only:[\s\S]*no modal baseline[\s\S]*modal fallback only if required fields are missing[\s\S]*no backend writes/i, "popup must explain the hybrid-only dry-run is validation-only with no baseline and fallback-only modal use");
assert.match(popupHtml, /id="runHybridOnlyModalFallbackDryRun25Button"[\s\S]*Run Hybrid-Only Dry Run \(25\)/, "popup must expose a separate 25 item hybrid-only dry-run button");
assert.match(popupHtml, /id="runHybridOnlyModalFallbackDryRun50Button"[\s\S]*Run Hybrid-Only Dry Run \(50\)/, "popup must expose a separate 50 item hybrid-only dry-run button");
assert.match(popupHtml, /id="runBackendShadowEstimatedViews3Button"[\s\S]*Run Backend Shadow Test with Estimated Views \(3\)[\s\S]*id="runBackendShadowEstimatedViews5Button"[\s\S]*Run Backend Shadow Test with Estimated Views \(5\)/, "popup must expose isolated backend shadow estimated-views actions with default 3 and max 5 samples");
assert.match(popupHtml, /Backend Shadow Test Estimated Views Summary[\s\S]*id="modalWholeProfileBackendShadowSummaryPreview"[\s\S]*BACKEND_SHADOW_TEST_ESTIMATED_VIEWS_SUMMARY not run yet\./, "popup must expose the backend shadow estimated-views summary preview block");
assert.match(popupHtml, /id="hybridEstimatedViewsCollectBetaEnabled"[\s\S]*Enable Hybrid Estimated Views Collect Beta[\s\S]*id="runGuardedHybridCollectBeta3Button"[\s\S]*Run Guarded Hybrid Collect Beta \(3\)[\s\S]*id="runGuardedHybridCollectBeta5Button"[\s\S]*Run Guarded Hybrid Collect Beta \(5\)[\s\S]*id="postVerifyGuardedHybridCollectBetaButton"[\s\S]*Post-Verify Guarded Hybrid Beta/, "popup must expose separate guarded hybrid collect beta 3, beta 5, and post-verify actions only in Advanced Details developer controls");
assert.match(popupHtml, /Feature flag:[\s\S]*hybridEstimatedViewsCollectBetaEnabled[\s\S]*Current value:[\s\S]*default false[\s\S]*Staged batch limit:[\s\S]*3 \/ 5, max 5[\s\S]*beta writes to the production backend only after all guards pass/, "popup must explain the beta flag storage key, default-off value, staged 3/5 max batch limit, and production-write warning");
assert.match(popupHtml, /Hybrid Collect Beta Prerequisites[\s\S]*id="hybridCollectBetaPrerequisitesPreview"[\s\S]*HYBRID_COLLECT_BETA_PREREQUISITES not evaluated yet\./, "popup must expose the guarded beta prerequisite status preview block");
assert.match(popupHtml, /Guarded Hybrid Collect Beta Summary[\s\S]*id="guardedHybridCollectBetaSummaryPreview"[\s\S]*GUARDED_HYBRID_COLLECT_BETA_SUMMARY not run yet\./, "popup must expose the guarded hybrid collect beta diagnostic summary preview block");
assert.match(popupHtml, /Guarded Hybrid Collect Beta Post-Verify Summary[\s\S]*id="guardedHybridCollectBetaPostVerifySummaryPreview"[\s\S]*GUARDED_HYBRID_COLLECT_BETA_POST_VERIFY_SUMMARY not run yet\./, "popup must expose the guarded hybrid collect beta post-verify summary preview block");
assert.match(popupSource, /copyBackendErrorDetailsButton\?\.addEventListener\("click", \(\) => void copyBackendErrorDetailsFromPopup\(\)\);/, "popup must wire the backend error details copy button");
assert.match(popupSource, /copyModalWholeProfileDecisionSummaryButton\?\.addEventListener\("click", \(\) => void copyModalWholeProfileDecisionSummaryFromPopup\(\)\);/, "popup must wire the hybrid-only decision summary copy button");
assert.match(popupSource, /copyModalWholeProfileComparisonButton\?\.addEventListener\("click", \(\) => void copyModalWholeProfileComparisonFromPopup\(\)\);/, "popup must wire the full modal comparison copy button");
assert.match(popupSource, /hybridOnlyModalFallbackDryRun25Button\?\.addEventListener\("click", \(\) => void runHybridOnlyWithModalFallbackDryRunFromPopup\(25\)\);[\s\S]*hybridOnlyModalFallbackDryRun50Button\?\.addEventListener\("click", \(\) => void runHybridOnlyWithModalFallbackDryRunFromPopup\(50\)\);/, "popup must wire separate hybrid-only 25 and 50 dry-run buttons");
assert.match(popupSource, /backendShadowEstimatedViews3Button\?\.addEventListener\("click", \(\) => void runBackendShadowTestWithEstimatedViewsFromPopup\(3\)\);[\s\S]*backendShadowEstimatedViews5Button\?\.addEventListener\("click", \(\) => void runBackendShadowTestWithEstimatedViewsFromPopup\(5\)\);/, "popup must wire isolated backend shadow estimated-views actions without changing Start Collecting");
assert.match(popupSource, /HYBRID_ESTIMATED_VIEWS_COLLECT_BETA_STORAGE_KEY = "hybridEstimatedViewsCollectBetaEnabled"[\s\S]*HYBRID_COLLECT_BETA_LATEST_DRY_RUN_STORAGE_KEY = "hybridCollectBetaLatestDryRun"[\s\S]*HYBRID_COLLECT_BETA_LATEST_SHADOW_STORAGE_KEY = "hybridCollectBetaLatestBackendShadow"[\s\S]*HYBRID_COLLECT_BETA_LATEST_PRODUCTION_STORAGE_KEY = "hybridCollectBetaLatestProduction"[\s\S]*GUARDED_HYBRID_COLLECT_BETA_MAX_BATCH_SIZE = 5/, "guarded hybrid collect beta must use the named default-off feature flag, persisted prerequisite storage keys, latest production artifact key, and staged max batch 5");
assert.match(popupSource, /hybridEstimatedViewsCollectBetaEnabledInput\?\.addEventListener\("change", \(\) => void saveHybridEstimatedViewsCollectBetaFlag\(\)\);[\s\S]*guardedHybridCollectBeta3Button\?\.addEventListener\("click", \(\) => void runGuardedHybridCollectBetaFromPopup\(3\)\);[\s\S]*guardedHybridCollectBeta5Button\?\.addEventListener\("click", \(\) => void runGuardedHybridCollectBetaFromPopup\(5\)\);[\s\S]*postVerifyGuardedHybridCollectBetaButton\?\.addEventListener\("click", \(\) => void runGuardedHybridCollectBetaPostVerifyFromPopup\(\)\);[\s\S]*await renderHybridCollectBetaPrerequisitesPreview\(\);/, "popup must wire the beta flag, controlled 3-item and 5-item guarded beta actions, post-verify action, and prerequisite preview rendering");
assert.match(popupSource, /function hybridCollectBetaDryRunSourceFromRun\(run: ModalWholeProfileTestRun \| null\): HybridCollectBetaDryRunSource \| null \{[\s\S]*summary\.run[\s\S]*summary\.sample_completion[\s\S]*summary\.decision[\s\S]*decision\.safe_to_scale === "yes"[\s\S]*rows/, "popup must build beta dry-run source artifacts from nested HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY fields and rows");
assert.match(popupSource, /async function persistHybridCollectBetaDryRunSourceFromRun\(run: ModalWholeProfileTestRun \| null\): Promise<void> \{[\s\S]*hybridCollectBetaDryRunSourceValid\(source\)[\s\S]*HYBRID_COLLECT_BETA_LATEST_DRY_RUN_STORAGE_KEY[\s\S]*HYBRID_COLLECT_BETA_LATEST_DRY_RUN_COMPACT_STORAGE_KEY[\s\S]*guardedPipelineCompactLatestFromDryRun/, "popup must persist only valid latest Hybrid-Only Dry Run (50) prerequisite source metadata plus compact durable metadata");
assert.match(popupSource, /async function readHybridCollectBetaResolvedDryRunSource\(\): Promise<\{ source: HybridCollectBetaDryRunSource \| null; source_provenance:[\s\S]*stored_artifact[\s\S]*latest_modal_run[\s\S]*stored_modal_run[\s\S]*shadow_handoff[\s\S]*readModalWholeProfileTestRun\(\)[\s\S]*shadow\?\.source_run_id[\s\S]*HYBRID_COLLECT_BETA_LATEST_DRY_RUN_STORAGE_KEY/, "popup must resolve missing beta dry-run artifacts from live/stored modal runs and shadow source_run_id handoff");
assert.match(popupSource, /async function persistHybridCollectBetaShadowSourceFromSummary\(summary: Record<string, unknown>\): Promise<void> \{[\s\S]*hybridCollectBetaShadowSourceValid\(source\)[\s\S]*HYBRID_COLLECT_BETA_LATEST_SHADOW_STORAGE_KEY[\s\S]*HYBRID_COLLECT_BETA_LATEST_SHADOW_COMPACT_STORAGE_KEY[\s\S]*guardedPipelineCompactLatestFromShadow/, "popup must persist only valid latest Backend Shadow Test (5) prerequisite source metadata plus compact durable metadata");
assert.match(popupSource, /summary_title: "HYBRID_COLLECT_BETA_PREREQUISITES"[\s\S]*feature_flag:[\s\S]*latest_hybrid_dry_run:[\s\S]*latest_backend_shadow:[\s\S]*eligible_beta_rows:[\s\S]*overall:/, "popup must build the required beta prerequisite status summary");
assert.match(popupSource, /flagEnabled \? null : "feature_flag_disabled"[\s\S]*"latest_hybrid_dry_run_missing"[\s\S]*"latest_hybrid_dry_run_rows_missing"[\s\S]*"shadow_source_dry_run_handoff_broken"[\s\S]*"latest_backend_shadow_pass_missing"[\s\S]*"insufficient_eligible_hybrid_rows"/, "guarded beta prerequisites must distinguish missing artifacts, row-artifact handoff failures, shadow pass, and eligible-row blockers");
assert.match(popupSource, /source_available: hasDryRunArtifact \? "yes" : "no"[\s\S]*verdict: hasValidDryRun \? "ready" : "missing_or_invalid"[\s\S]*eligible_rows_complete_count: eligibleRows\.length[\s\S]*selection_note: flagEnabled \? "beta_flag_enabled_selecting_rows" : "feature_flag_disabled_rows_available_not_selected"[\s\S]*eligibility_blockers: eligibleRowsBlocker \? \[eligibleRowsBlocker\] : \[\]/, "guarded beta prerequisites must show dry-run availability and eligible rows even when the beta feature flag is disabled");
assert.match(popupSource, /inspect_production_state_and_counters_before_expanding[\s\S]*backendResult && !status\?\.normalizedOk[\s\S]*inspect_backend_errors[\s\S]*estimated_views_not_supported_by_full_modal_harvest_schema[\s\S]*add_backend_support_for_estimated_views[\s\S]*blockers\.includes\("feature_flag_disabled"\) && blockers\.length === 1[\s\S]*enable_beta_flag[\s\S]*run_guarded_hybrid_collect_beta_3/, "guarded beta recommendations must distinguish success, idempotent success, backend failure, unsupported production schema, feature flag, and rerun next steps");
assert.match(popupSource, /function buildBackendErrorDetailsForPopup\(state: WholeProfileHarvestState \| null\)/, "popup must build a scoped backend error detail export");
assert.match(popupSource, /function buildModalWholeProfileComparisonLog\(run: ModalWholeProfileTestRun \| null\): ModalWholeProfileComparisonLog \| null/, "popup must build a compact modal comparison export");
assert.match(popupSource, /const modalWholeProfileTestButton = document\.querySelector<HTMLButtonElement>\("#runModalWholeProfileTestButton"\);/, "popup must wire the real collecting comparison entry button rendered in HTML");
assert.match(popupSource, /const modalWholeProfileSampleSizeSelect = document\.querySelector<HTMLSelectElement>\("#modalWholeProfileSampleSize"\);/, "popup must wire the collecting comparison sample-size selector rendered in HTML");
assert.match(popupSource, /function selectedModalWholeProfileSampleSize\(\): 5 \| 10 \| 25 \| 50 \{[\s\S]*value === 50 \? 50 : value === 25 \? 25 : value === 10 \? 10 : 5;[\s\S]*\}/, "popup must constrain collecting comparison sample size to controlled 5, 10, 25, or 50 item dry-run tiers");
assert.match(popupSource, /const selectedSampleSize = selectedModalWholeProfileSampleSize\(\);[\s\S]*dry_run_limit: selectedSampleSize[\s\S]*comparison_requested_sample_size: selectedSampleSize[\s\S]*await startModalWholeProfileDryRun\(selectedMode, \{ specificIdsInput: "", sampleSize: selectedSampleSize \}\)/s, "collecting comparison action must pass the selected sample size into the dry-run path");
assert.match(popupSource, /async function startModalWholeProfileDryRun\(mode: ModalWholeProfileTestMode, options: \{ specificIdsInput: string; sampleSize: number \}\)[\s\S]*dry_run_limit: options\.sampleSize[\s\S]*requested_sample_size: options\.sampleSize/s, "collecting comparison dry-run must use the selected controlled item limit for reusable and scanned-profile queues");
assert.match(popupSource, /const modalWholeProfileTestDisabledReasonEl = document\.querySelector<HTMLElement>\("#modalWholeProfileTestDisabledReason"\);/, "popup must wire a visible disabled-reason helper for the collecting comparison action");
assert.match(popupSource, /setDefinitionList\(modalWholeProfileTestSummaryEl, \{ Status: "No comparison run yet", Details: "Run the comparison test to generate a log\." \}\);/, "popup must render a visible no-run placeholder summary for the collecting comparison section");
assert.match(popupSource, /const preview = comparison \? JSON\.stringify\(comparison, null, 2\) : diagnostics \? JSON\.stringify\(diagnostics, null, 2\) : "No comparison run yet\.";/, "popup must render comparison diagnostics or placeholder text in the collecting comparison log section");
assert.match(popupSource, /const decisionSummary = comparison\?\.HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY \?\? null;[\s\S]*modalWholeProfileDecisionSummaryPreviewEl\.textContent = decisionSummary \? JSON\.stringify\(decisionSummary, null, 2\) : "HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY not available yet\.";/, "popup must render a separate compact hybrid-only decision summary without replacing the full log preview");
assert.match(popupSource, /comparison_action_clicked: diagnostics\.comparison_action_clicked \?\? "no"[\s\S]*comparison_action_dispatch_started: diagnostics\.comparison_action_dispatch_started \?\? "no"[\s\S]*comparison_action_dispatch_result: diagnostics\.comparison_action_dispatch_result \?\? \(comparisonState === "idle_placeholder" \? "idle" : comparisonState\)[\s\S]*comparison_start_context_type: diagnostics\.comparison_start_context_type \?\? "invalid"[\s\S]*comparison_profile_context_ready: diagnostics\.comparison_profile_context_ready \?\? "no"[\s\S]*comparison_queue_context_ready: diagnostics\.comparison_queue_context_ready \?\? "no"[\s\S]*comparison_sample_count_available: diagnostics\.comparison_sample_count_available \?\? run\.verified_target_count \?\? run\.target_count \?\? 0[\s\S]*comparison_modal_operator_precondition_required: diagnostics\.comparison_modal_operator_precondition_required \?\? "no"[\s\S]*comparison_modal_opening_strategy: diagnostics\.comparison_modal_opening_strategy \?\? \(run\.verified_target_count > 0 \? "internal_runner" : "blocked"\)[\s\S]*comparison_state: comparisonState[\s\S]*comparison_run_id: diagnostics\.comparison_run_id \?\? run\.run_id \?\? null/s, "popup must render compact visible comparison action and profile/queue diagnostics when no comparison rows exist yet");
assert.match(popupSource, /const profileContext = await buildModalWholeProfileDryRunFromScannedProfileContext\(mode,[\s\S]*await runModalWholeProfileDryRunFromVerifiedTargets\(profileContext\.run, profileContext\.tabId, mode, options\.specificIdsInput\)/s, "collecting comparison dry-run must route scanned profile context into the internal modal runner");
assert.match(popupSource, /function comparisonProfileStartDiagnostics[\s\S]*comparison_modal_operator_precondition_required: "no"/s, "comparison diagnostics must state no operator-opened modal precondition");
assert.match(popupSource, /async function buildModalWholeProfileDryRunFromScannedProfileContext[\s\S]*modalOpeningStrategy: blockedReason \? "blocked" : "internal_runner"[\s\S]*available_queue_count: queueItems\.length \|\| null[\s\S]*eligible_queue_count: targets\.length \|\| null[\s\S]*collectable_queue_count: collectableQueue\.length \|\| targets\.length \|\| null[\s\S]*skipped_before_run_count:[\s\S]*skipped_before_run_reasons: skippedBeforeRunReasons/s, "profile-based comparison start must report internal modal opening plus queue availability and skipped-before-run diagnostics");
assert.match(popupSource, /Disabled while Collecting is active\. Pause or wait for the run to finish before starting the comparison test\./, "popup must show a visible disabled reason while collecting is active");
assert.match(popupSource, /comparison_title: "Advanced Details Comparison Log"[\s\S]*comparison_kind: isHybridOnly \? "hybrid_only_with_modal_fallback" : "modal_baseline_vs_hybrid_candidate"[\s\S]*candidate_mode: "hybrid_low_interaction"/, "modal comparison export must preserve compact identity fields while supporting hybrid-only mode");
assert.match(popupSource, /required_fields: requiredFields[\s\S]*items_with_all_required_fields: requiredFieldsCompleteCount[\s\S]*item_required_field_pass_rate: itemRequiredFieldPassRate[\s\S]*total_required_field_slots: totalRequiredFieldSlots[\s\S]*required_field_slots_present: requiredFieldSlotsPresent[\s\S]*required_field_slot_coverage_rate: requiredFieldSlotCoverageRate[\s\S]*missing_required_field_counts: missingFieldCounts as Record<string, number>[\s\S]*modal_fallback_required_count: modalFallbackRequiredCount[\s\S]*modal_fallback_used_count: modalFallbackUsedCount[\s\S]*modal_fallback_recovered_count: modalFallbackRecoveredCount[\s\S]*modal_fallback_incomplete_count: modalFallbackIncompleteCount[\s\S]*modal_fallback_safety_blocked_count: modalFallbackSafetyBlockedCount[\s\S]*hybrid_failed_without_fallback_count: hybridFailedWithoutFallbackCount[\s\S]*pass_with_modal_fallback_count: passWithModalFallbackCount[\s\S]*final_ready_count: finalReadyCount[\s\S]*final_ready_rate: finalReadyRate[\s\S]*final_missing_required_field_counts: finalMissingFieldCounts as Record<string, number>[\s\S]*extraction_failure_count: extractionFailureCount[\s\S]*anti_bot_signal_count: antiBotSignalCount[\s\S]*safe_to_scale: safeToScale[\s\S]*hybrid_viability_recommendation: hybridViabilityRecommendation[\s\S]*validation_tier: validationTier[\s\S]*requested_sample_size: requestedSampleSize[\s\S]*completed_sample_size: completedSampleSize[\s\S]*stopped_early: stoppedEarly[\s\S]*safety_stop_triggered: safetyStopTriggered[\s\S]*elapsed_ms: elapsedMs[\s\S]*duration_bucket: durationBucket[\s\S]*per_source_counts: perSourceCounts[\s\S]*next_step_recommendation: decisionNextStepRecommendation === "backend_shadow_test_with_estimated_views_available_set"[\s\S]*decisionNextStepRecommendation === "diagnose_hybrid_dry_run_early_stop"[\s\S]*backend_write_attempted: backendWriteAttempted[\s\S]*backend_write_mode: backendWriteMode[\s\S]*production_collect_state_mutated: productionCollectStateMutated[\s\S]*not_safe_to_scale_reason: notSafeToScaleReason[\s\S]*HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY: decisionSummary/s, "modal comparison export must distinguish hybrid-only, modal fallback, final combined result, anti-bot safety, larger dry-run telemetry, dry-run isolation, validation tier, next step, scale verdict, and compact hybrid-only summary export");
assert.match(popupSource, /const validationTier = requestedSampleSize <= 3 \? "sample_3" : requestedSampleSize <= 5 \? "sample_5" : requestedSampleSize <= 10 \? "sample_10" : requestedSampleSize <= 25 \? "sample_25" : requestedSampleSize <= 50 \? "sample_50" : "larger_dry_run";[\s\S]*backendWriteAttempted: "no"[\s\S]*productionCollectStateMutated: "no"[\s\S]*const backendWriteMode = "disabled_dry_run" as const;/s, "modal comparison export must identify 25/50 validation tiers and explicitly report dry-run no-backend-write isolation");
assert.match(popupSource, /validationTier === "sample_3"[\s\S]*\? "sample_too_small_for_scale"[\s\S]*validationTier === "sample_3"[\s\S]*\? "rerun_sample_5"[\s\S]*validationTier === "sample_5"[\s\S]*\? "rerun_sample_10"[\s\S]*validationTier === "sample_10"[\s\S]*\? "proceed_to_larger_dry_run"[\s\S]*: "proceed_to_backend_shadow_test"/s, "3/5/10 item comparison results must ladder into larger dry-run tiers before backend shadow testing");
assert.match(popupSource, /backendWriteAttempted === "yes" \|\| productionCollectStateMutated === "yes"[\s\S]*\? "do_not_scale_state_mutation_detected"[\s\S]*eligibleQueueCount != null && eligibleQueueCount >= requestedSampleSize[\s\S]*\? "diagnose_hybrid_dry_run_early_stop"[\s\S]*completedSampleSize !== requestedSampleSize[\s\S]*\? "repeat_larger_dry_run"/s, "larger dry-run recommendations must distinguish early-stop diagnosis from available-set partial completion and still block on state mutation");
assert.match(popupSource, /const modalFallbackResult = !modalFallbackRequired[\s\S]*\? "not_needed" as const[\s\S]*: attemptedFallback[\s\S]*: "not_attempted" as const;[\s\S]*modal_fallback_used: modalFallbackUsed[\s\S]*modal_fallback_result: modalFallbackResult[\s\S]*fallback_attempted: fallbackAttempted[\s\S]*fallback_open_modal_status: fallbackOpenModalStatus[\s\S]*fallback_failure_stage: fallbackFailureStage[\s\S]*fallback_failure_reason_safe: fallbackFailureReasonSafe/s, "missing required fields must normalize fallback row invariants and include safe fallback failure diagnostics");
assert.match(popupSource, /if \(modalFallbackResult === "incomplete"\) modalFallbackIncompleteCount \+= 1;/, "modal fallback incomplete aggregate must not count failed/not-attempted rows as incomplete");
assert.match(popupSource, /unrecoveredItemCount > 0 && modalFallbackRequiredCount > 0 && modalFallbackUsedCount === 0[\s\S]*\? "fix_modal_fallback_failure"[\s\S]*unrecoveredItemCount > 0 && modalFallbackRequiredCount > 0[\s\S]*\? "investigate_unrecovered_fallback_item"/s, "unrecovered fallback recommendations must identify operational fallback failure separately from unrecovered attempted fallback items");
assert.match(popupSource, /if \(\(result\.hybrid_missing_required_fields \?\? modalWholeProfileMissingRequiredFields\(result\)\)\.length > 0 && !fallbackSafetyBlocked\)[\s\S]*await comparisonModalFallbackDelay\(index\);[\s\S]*result = await executeModalWholeProfileComparisonFallback\(tabId, result, awemeId, targetUrl\);[\s\S]*if \(result\.modal_fallback_result === "safety_blocked"\) fallbackSafetyBlocked = true;/s, "comparison dry-run must execute modal fallback only for hybrid-missing-field items and stop further fallback after safety block");
assert.match(popupSource, /function executeModalWholeProfileComparisonFallback[\s\S]*assertModalWholeProfileDryRunNoBackendWrite\("douyinModalWholeProfileTestRun:modalFallbackReadOnly"\)[\s\S]*detectCaptchaOrCheckpoint[\s\S]*probeModalWholeProfileDryRunTarget[\s\S]*modalWholeProfileFallbackResult/s, "modal fallback execution must remain read-only, safety checked, and scoped to comparison dry-run extraction");
assert.match(popupSource, /modal_fallback_backend_write_attempted: "no"[\s\S]*modal_fallback_production_collect_state_mutated: "no"/s, "modal fallback diagnostics must explicitly state no backend writes and no production collect state mutation");
assert.match(popupSource, /async function runHybridOnlyWithModalFallbackDryRunFromPopup\(sampleSize: 25 \| 50\)[\s\S]*comparison_kind: "hybrid_only_with_modal_fallback_dry_run"[\s\S]*modal_baseline_disabled: "yes"[\s\S]*await runHybridOnlyDryRunFromVerifiedTargets\(run, profileContext\.tabId, sampleSize\)/s, "hybrid-only dry-run must be a distinct mode with modal baseline disabled");
assert.match(popupSource, /async function runHybridOnlyDryRunFromVerifiedTargets[\s\S]*buildHybridOnlyHydrationContext\(tabId, sample\.targets\)[\s\S]*modalWholeProfileHybridOnlyResultFromHydration[\s\S]*if \(missing\.length > 0 && !fallbackSafetyBlocked\)[\s\S]*await chrome\.tabs\.update\(tabId, \{ url: targetUrl \}\);[\s\S]*fallbackNavigationCount \+= 1[\s\S]*modal_baseline_navigation_count: 0[\s\S]*actual_modal_navigation_count: fallbackNavigationCount/s, "hybrid-only runner must hydrate non-modal sources first and count only fallback modal navigations");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function runHybridOnlyDryRunFromVerifiedTargets"), popupSource.indexOf("async function buildHybridOnlyHydrationContext")), /runModalWholeProfileDryRunFromVerifiedTargets/, "hybrid-only runner must not reuse the old modal-per-item comparison loop");
assert.match(popupSource, /function modalWholeProfileHybridOnlyResultFromHydration[\s\S]*source: "profile_repository"[\s\S]*source: "network_cache"[\s\S]*source: "passive_aweme"[\s\S]*source: "profile_post_api"[\s\S]*source: "calibrated_non_modal_dom"[\s\S]*mergeHydrationFields/s, "hybrid-only hydration must attempt the configured non-modal source priority chain and merge partial fields before modal fallback");
assert.match(popupSource, /comparison_kind: isHybridOnly \? "hybrid_only_with_modal_fallback" : "modal_baseline_vs_hybrid_candidate"[\s\S]*actual_modal_navigation_count: actualModalNavigationCount[\s\S]*modal_baseline_navigation_count: modalBaselineNavigationCount[\s\S]*modal_fallback_navigation_count: modalFallbackNavigationCount[\s\S]*modal_navigation_avoided_count: modalNavigationAvoidedCount[\s\S]*modal_navigation_reduction_rate: modalNavigationReductionRate/s, "comparison log must export hybrid-only modal navigation truth fields");
assert.match(popupSource, /modal_opened_for_this_item: modalOpenedForThisItem[\s\S]*modal_open_reason: modalOpenReason[\s\S]*hybrid_status: hybridStatus[\s\S]*hybrid_sources_attempted: hybridSourcesAttempted[\s\S]*hybrid_source_selected: hybridSourceSelected[\s\S]*hybrid_missing_after_all_non_modal_sources: hybridMissingAfterAllNonModalSources/s, "comparison rows must include per-item modal-open truth and hybrid source diagnostics");
assert.match(popupSource, /hybrid_source_attempted_counts: hybridSourceAttemptedCounts[\s\S]*hybrid_source_success_counts: hybridSourceSuccessCounts[\s\S]*hybrid_source_missing_required_counts: hybridSourceMissingRequiredCounts[\s\S]*hybrid_source_unavailable_counts: hybridSourceUnavailableCounts[\s\S]*modal_fallback_required_after_hybrid_count: modalFallbackRequiredAfterHybridCount/s, "comparison log must export aggregate hybrid source diagnostics");
assert.match(popupSource, /const modalAvoidanceNotWorking = isHybridOnly[\s\S]*actualModalNavigationCount >= testedVideos[\s\S]*modalNavigationAvoidedCount === 0[\s\S]*allRowsProfileCardOnlyFallback[\s\S]*!requiredNonModalSourcesAttempted[\s\S]*\? "modal_avoidance_not_working"[\s\S]*\? "fix_hybrid_non_modal_hydration"/s, "hybrid-only log must fail clearly when modal avoidance is not working or non-modal sources were not attempted");
assert.match(popupSource, /metric_values: metricValues[\s\S]*metric_value_types: metricValueTypes[\s\S]*metric_value_validity: metricValueValidity[\s\S]*metric_value_source: metricValueSource[\s\S]*thumbnail,/s, "comparison rows must include sanitized metric values, type/validity/source evidence, and thumbnail status");
assert.match(popupSource, /metric_value_present_counts: metricValuePresentCounts[\s\S]*metric_value_valid_counts: metricValueValidCounts[\s\S]*metric_value_invalid_counts: metricValueInvalidCounts[\s\S]*metric_value_source_counts: metricValueSourceCounts[\s\S]*thumbnail_coverage_count: thumbnailCoverageCount[\s\S]*thumbnail_valid_url_count: thumbnailValidUrlCount[\s\S]*thumbnail_source_counts: thumbnailSourceCounts/s, "comparison log must export aggregate metric value and thumbnail quality stats");
assert.match(popupSource, /function metricValueValidityForLogRow[\s\S]*field === "duration_seconds"[\s\S]*value > 0 \? "valid_positive_number" : "invalid_non_positive_number"[\s\S]*value >= 0 \? "valid_non_negative_number" : "invalid_negative_number"/s, "metric values must be validated with positive duration and non-negative engagement counts");
assert.match(popupSource, /const metricValuesMissingOrInvalid = isHybridOnly[\s\S]*metricValueValidCounts\[field\][\s\S]*\? "metric_values_missing_or_invalid"[\s\S]*\? "fix_metric_value_hydration"/s, "hybrid-only log must block backend shadow testing when metric values are missing or invalid");
assert.match(popupSource, /const thumbnailMissingOrInvalid = isHybridOnly[\s\S]*thumbnailCoverageCount[\s\S]*thumbnailValidUrlCount[\s\S]*\? "thumbnail_missing_or_invalid"[\s\S]*\? "fix_thumbnail_hydration"/s, "hybrid-only log must block backend shadow testing when required thumbnail evidence is missing or invalid");
assert.match(popupSource, /function thumbnailFromRecord[\s\S]*raw_network_aweme[\s\S]*raw_detail_aweme[\s\S]*video\.origin_cover[\s\S]*raw_network_aweme\.video\.origin_cover[\s\S]*return \{ present: "yes", field_used: field, source, valid_url: isSafeThumbnailUrl\(url\) \? "yes" : "no", url, url_host: safeUrlHost\(url\) \}/s, "thumbnail diagnostics must preserve canonical URL evidence from network/detail cover fields, not just hostname presence");
assert.match(popupSource, /view_count_diagnostics: viewCountDiagnostics[\s\S]*estimated_views_diagnostics: estimatedViewsDiagnostics[\s\S]*extra_values: extraValues[\s\S]*extra_value_types: extraValueTypes[\s\S]*extra_value_validity: extraValueValidity[\s\S]*extra_value_source: extraValueSource/s, "comparison rows must include posted, real view count provenance, estimated views diagnostics, and thumbnail extra value evidence with type, validity, and source diagnostics");
assert.match(popupSource, /extra_value_present_counts: extraValuePresentCounts[\s\S]*extra_value_valid_counts: extraValueValidCounts[\s\S]*extra_value_invalid_counts: extraValueInvalidCounts[\s\S]*extra_value_source_counts: extraValueSourceCounts[\s\S]*trusted_view_count_candidate_field_path_counts: trustedViewCountCandidateFieldPathCounts[\s\S]*rejected_view_count_false_positive_path_counts: rejectedViewCountFalsePositivePathCounts[\s\S]*view_count_selected_trusted_field_counts: viewCountSelectedTrustedFieldCounts[\s\S]*view_count_zero_confidence_counts: viewCountZeroConfidenceCounts[\s\S]*views_data_quality_verdict: viewsDataQualityVerdict[\s\S]*estimated_views_present_count: estimatedViewsPresentCount/s, "comparison log must export trusted view-count stats and estimated views stats");
assert.match(popupSource, /function buildViewCountDiagnosticsFromSources[\s\S]*trusted_candidates_found: markedTrusted[\s\S]*rejected_false_positive_candidates: rejectedFalsePositiveCandidates[\s\S]*selected_field_trusted[\s\S]*selected_field_semantic_reason[\s\S]*real_view_count_found/s, "hybrid-only view count hydration must only select trusted allowlisted raw candidate provenance diagnostics");
assert.match(popupSource, /function estimateViewsFromLikes\(likeCount: number\): number \{\s*if \(likeCount <= 0\) return 0;\s*return Math\.round\(likeCount \* estimatedViewsMultiplierForLikes\(likeCount\)\);\s*\}[\s\S]*function estimatedViewsMultiplierForLikes\(likeCount: number\): number \{\s*if \(likeCount < 100\) return 45;\s*if \(likeCount < 1_000\) return 35;\s*if \(likeCount < 10_000\) return 28;\s*if \(likeCount < 100_000\) return 22;\s*return 18;\s*\}/s, "estimated views must use the approved tiered_like_multiplier_v1 formula implementation");
for (const [likes, estimate] of [[0, 0], [99, 4455], [100, 3500], [999, 34965], [1000, 28000], [9999, 279972], [10000, 220000], [99999, 2199978], [100000, 1800000]] as const) {
  const multiplier = likes <= 0 ? 45 : likes < 100 ? 45 : likes < 1_000 ? 35 : likes < 10_000 ? 28 : likes < 100_000 ? 22 : 18;
  const actual = likes <= 0 ? 0 : Math.round(likes * multiplier);
  assert.equal(actual, estimate, `estimated_views formula boundary ${likes} likes must produce ${estimate}`);
}
assert.match(popupSource, /const estimatedViewsDiagnostics = item\.estimated_views_diagnostics \?\? buildEstimatedViewsDiagnostics\(item\.like_count, item\.metric_value_source\?\.like_count \?\? item\.source_used \?\? null\);[\s\S]*view_count: viewCountDiagnostics\.normalized_view_count,[\s\S]*estimated_views: estimatedViewsDiagnostics\.estimated_views/s, "comparison row fallback must keep real view_count separate from derived estimated_views");
assert.match(popupSource, /function rawLikeCountFromRecord\(record: Record<string, unknown>\): number \| null \{\s*return rawLikeCountEvidenceFromRecord\(record\)\.value;\s*\}[\s\S]*function rawLikeCountEvidenceFromRecord[\s\S]*\["statistics\.digg_count"[\s\S]*\["raw_like_count"[\s\S]*\["like_count"/s, "hybrid metric hydration must prefer raw numeric digg/statistics like counts before any generic like_count field");
assert.match(popupSource, /function buildEstimatedViewsDiagnostics[\s\S]*blocked_compact_or_display_like_count[\s\S]*estimated_views_source: "derived_from_like_count"[\s\S]*estimated_views_formula: "tiered_like_multiplier_v1"[\s\S]*confidence: likeCount >= 1_000 \? "high" : likeCount >= 100 \? "medium" : "low"[\s\S]*validity: "valid"/s, "row-level estimated_views diagnostics must block compact/display like-count sources and include source, formula, confidence, and validity for raw numeric likes");
assert.match(popupSource, /const estimatedViewsPresentCount = rows\.filter\(\(row\) => row\.estimated_views_diagnostics\.estimated_views != null\)\.length;[\s\S]*const estimatedViewsValidCount = rows\.filter\(\(row\) => row\.estimated_views_diagnostics\.validity === "valid"\)\.length;[\s\S]*const estimatedViewsDataQualityVerdict = estimatedViewsValidCount === testedVideos[\s\S]*"estimated_views_ready"/s, "comparison log must aggregate estimated_views present and valid counts with a ready verdict");
assert.match(popupSource, /const viewCountMissingOrInvalid = isHybridOnly && testedVideos > 0 && !estimatedViewsReady[\s\S]*const estimatedViewsMissingOrInvalid = isHybridOnly && testedVideos > 0 && !estimatedViewsReady[\s\S]*estimatedViewsReady[\s\S]*\? "backend_shadow_test_with_estimated_views"/s, "hybrid-only recommendations must permit backend shadow testing when estimated_views are ready without treating real view_count as overwritten");
assert.match(popupSource, /summary_title: "HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY"[\s\S]*comparison_mode:[\s\S]*requested_sample_size: requestedSampleSize[\s\S]*selected_sample_size: selectedSampleSize[\s\S]*completed_sample_size: completedSampleSize[\s\S]*sample_completion:[\s\S]*available_queue_count: availableQueueCount[\s\S]*eligible_queue_count: eligibleQueueCount[\s\S]*collectable_queue_count: collectableQueueCount[\s\S]*skipped_before_run_count: skippedBeforeRunCount[\s\S]*skipped_during_run_count: skippedDuringRunCount[\s\S]*stop_reason: sampleStopReason[\s\S]*sample_completion_verdict: sampleCompletionVerdict/s, "compact decision summary must include requested, selected, completed, queue availability, skip diagnostics, stop reason, and verdict fields for 50-row dry runs");
assert.match(popupSource, /dry_run_safety:[\s\S]*backend_write_attempted: backendWriteAttempted[\s\S]*backend_write_mode: backendWriteMode[\s\S]*production_collect_state_mutated: productionCollectStateMutated[\s\S]*production_counters_mutated: productionCountersMutated[\s\S]*collect_job_mutated: collectJobMutated[\s\S]*queue_items_marked_complete: queueItemsMarkedComplete/s, "compact decision summary must include explicit dry-run safety flags");
assert.match(popupSource, /required_field_counts:[\s\S]*duration_seconds_valid_count[\s\S]*like_count_valid_count[\s\S]*comment_count_valid_count[\s\S]*favorite_count_valid_count[\s\S]*share_count_valid_count[\s\S]*posted_valid_count[\s\S]*posted_at_valid_count[\s\S]*thumbnail_valid_count/s, "compact decision summary must include required metric, posted, posted_at, and thumbnail valid counts");
assert.match(popupSource, /real_view_count:[\s\S]*view_count_real_found_count[\s\S]*real_view_count_kept_separate_from_estimated_views: rowsWhereViewCountOverwrittenByEstimatedViews === 0 \? "yes" : "no"[\s\S]*estimated_views:[\s\S]*estimated_views_present_count: estimatedViewsPresentCount[\s\S]*estimated_views_valid_count: estimatedViewsValidCount[\s\S]*estimated_views_formula: "tiered_like_multiplier_v1"/s, "compact decision summary must keep real view_count diagnostics separate from estimated_views aggregate counts");
assert.match(popupSource, /const decisionReadyForBackendShadow = completedSampleSize === requestedSampleSize[\s\S]*const decisionReadyForAvailableEligibleSet = completedSampleSize < requestedSampleSize[\s\S]*sampleCompletionVerdict === "complete_available_eligible_set"[\s\S]*completedSampleSize >= 25[\s\S]*decisionReadyForAvailableEligibleSet[\s\S]*\? "backend_shadow_test_with_estimated_views_available_set"[\s\S]*eligibleQueueCount != null && eligibleQueueCount >= requestedSampleSize[\s\S]*\? "diagnose_hybrid_dry_run_early_stop"/s, "compact decision summary must separate full requested-sample readiness, available-set readiness, and early-stop diagnosis");
assert.match(popupSource, /decision_blockers: decisionBlockers[\s\S]*decision_notes: decisionNotes[\s\S]*failures:[\s\S]*failed_row_count: failedRows\.length[\s\S]*rows_missing_like_count[\s\S]*rows_invalid_like_count[\s\S]*rows_missing_thumbnail[\s\S]*rows_missing_posted[\s\S]*rows_where_view_count_overwritten_by_estimated_views/s, "compact decision summary must include decision blockers, decision notes, and failed/anomalous row index summaries");
assert.match(popupSource, /function compactRepresentativeRows[\s\S]*successfulRows\.slice\(0, 2\)[\s\S]*if \(selected\.size >= 5\) break;[\s\S]*successfulRows\.at\(-1\)[\s\S]*function compactRepresentativeRow[\s\S]*row_index: row\.index[\s\S]*estimated_views_diagnostics: row\.estimated_views_diagnostics/s, "compact decision summary must include bounded representative rows instead of dumping all 50 rows");
assert.match(popupSource, /function backendShadowLowConfidenceZeroOnlyRealViewCount[\s\S]*view_count_zero_confidence === "low"[\s\S]*backendShadowRowHasNonzeroEngagement/s, "backend shadow payload must detect low-confidence zero-only real views when engagement metrics are nonzero");
assert.match(popupSource, /function buildBackendShadowEstimatedViewsPayloadItem[\s\S]*const payloadTitle = guardedHybridString\(row\.extra_values\.title\)[\s\S]*title: payloadTitle,[\s\S]*expected_title: payloadTitle,[\s\S]*title_source: row\.extra_values\.title_source \?\? null,[\s\S]*title_valid_real_text: dryRunTitleWasRealText,[\s\S]*outgoing_payload_title_is_real_text: payloadTitle != null && dryRunTitleWasRealText && !payloadTitleEqualsAwemeId,[\s\S]*like_count: row\.metric_values\.like_count,[\s\S]*view_count: realViewCount,[\s\S]*estimated_views: row\.estimated_views_diagnostics\.estimated_views,[\s\S]*estimated_views_formula: "tiered_like_multiplier_v1"[\s\S]*real_view_count_overwritten: false/s, "backend shadow payload preview must carry dry-run real title, preserve exact Likes, suppress low-confidence zero-only view_count, and keep estimated_views separate");
assert.match(popupSource, /"trusted_zero_only_low_confidence"[\s\S]*"real_view_count_null_low_confidence_or_missing"/s, "backend shadow payload must not label low-confidence zero-only rows as trusted_real_view_count");
assert.match(popupSource, /payload_title_missing_from_real_dry_run_title[\s\S]*payload_title_equals_aweme_id_with_real_title_source[\s\S]*low_confidence_zero_view_count_sent_as_real[\s\S]*title_payload_real_text_count[\s\S]*payload_title_missing_from_real_dry_run_title_count[\s\S]*payload_title_equals_aweme_id_with_real_title_source_count[\s\S]*view_count_null_or_omitted_count[\s\S]*view_count_sent_as_zero_count[\s\S]*low_confidence_zero_view_count_suppressed_count[\s\S]*estimated_views_sent_count[\s\S]*rows_where_estimated_views_copied_to_view_count: estimatedViewsCopiedToViewCountCount/s, "backend shadow summary must fail dropped/ID title payloads and expose title plus view_count suppression counters");
assert.match(popupSource, /function buildBackendShadowTestEstimatedViewsSummary[\s\S]*Math\.min\(Math\.max\(requestedSampleSize, 3\), 5\)[\s\S]*const hasSafeShadowEndpoint = true;[\s\S]*backendShadowWriteAttempted = hasSafeShadowEndpoint[\s\S]*"blocked_no_shadow_endpoint"/s, "backend shadow test must cap samples at 5 and recognize the validation-only shadow endpoint while preserving blocked verdict fallback");
assert.match(popupSource, /summary_title: "BACKEND_SHADOW_TEST_ESTIMATED_VIEWS_SUMMARY"[\s\S]*run:[\s\S]*safety:[\s\S]*payload_validation:[\s\S]*backend_result:[\s\S]*decision:[\s\S]*representative_items/s, "backend shadow summary must include required top-level sections");
assert.match(popupSource, /production_collect_state_mutated: "no"[\s\S]*production_counters_mutated: "no"[\s\S]*collect_job_mutated: "no"[\s\S]*queue_items_marked_complete: "no"[\s\S]*endpoint_path: "\/douyin-extension\/capture-inbox\/shadow-items"/s, "backend shadow test must report no production mutation and target only the validation shadow endpoint");
assert.match(popupSource, /shadowTestVerdict = payloadInvalidReasons\.length > 0[\s\S]*\? "blocked_payload_invalid"[\s\S]*backendResult\?\.ok === true[\s\S]*\? "backend_shadow_ready"[\s\S]*: "blocked_no_shadow_endpoint"[\s\S]*safe_for_next_phase: shadowTestVerdict === "backend_shadow_ready" \? "yes_backend_shadow_passed_only" : "no"/s, "backend shadow decision rules must distinguish invalid payloads, shadow success, and blocked missing endpoint");
assert.match(popupSource, /sampleSize === 3 \? "run_shadow_test_5_items" : "prepare_guarded_production_integration_plan"[\s\S]*rejected_count[\s\S]*"inspect_backend_shadow_results"/s, "successful 5-item backend shadow must recommend guarded production integration planning and rejected rows must recommend inspection");
assert.match(popupSource, /summary_title: "GUARDED_HYBRID_COLLECT_BETA_SUMMARY"[\s\S]*run:[\s\S]*guards:[\s\S]*payload:[\s\S]*backend_write:[\s\S]*production_state:[\s\S]*decision:[\s\S]*representative_items/s, "guarded beta summary must include required diagnostic sections");
assert.match(popupSource, /const dryRunResolution = await readHybridCollectBetaResolvedDryRunSource\(\);[\s\S]*const dryRun = dryRunResolution\.source[\s\S]*feature_flag_enabled: flagEnabled \? "yes" : "no"[\s\S]*latest_hybrid_dry_run_exists[\s\S]*latest_backend_shadow_pass_exists[\s\S]*batch_size_lte_5[\s\S]*requested_batch_size_supported[\s\S]*eligible_rows_complete_count[\s\S]*insufficient_eligible_rows_for_requested_batch[\s\S]*blockers/s, "guarded beta must enforce feature flag, resolved dry-run source, persisted shadow pass, staged max batch 5, exact requested eligible rows, and blocker guards");
assert.match(popupSource, /diagnostic_payload_preview:[\s\S]*write_mode: "guarded_hybrid_collect_beta_diagnostic_only"[\s\S]*production_request_preview:[\s\S]*payload_schema_validation:/s, "guarded beta payload policy must split diagnostic preview from production request");
assert.match(popupSource, /const estimatedViewsSupportedByBackendSchema = "yes";[\s\S]*const viewCountPolicySupportedByBackendSchema = "yes";/s, "guarded beta payload policy must mark estimated_views and nullable view_count backend schema support as available");
assert.match(popupSource, /estimated_views_supported_by_backend_schema: estimatedViewsSupportedByBackendSchema[\s\S]*view_count_policy_supported_by_backend_schema: viewCountPolicySupportedByBackendSchema[\s\S]*backend_call_allowed: blocker == null && canBuildPayload \? "yes" : "no"/s, "guarded beta payload policy must expose local schema validation support flags and backend-call gating");
assert.match(popupSource, /function buildFinalizedMetadataFromHybridPayload\(row: ModalWholeProfileComparisonLogRow\): GuardedHybridFinalizedMetadata[\s\S]*source_url: sourceUrl[\s\S]*finalized_metadata_source: "guarded_hybrid_network_cache"[\s\S]*profile_card_evidence:[\s\S]*source_url: sourceUrl[\s\S]*data_integrity_status: "passed"/s, "guarded beta must build truthful finalized metadata from hybrid network-cache rows without faking modal source");
assert.match(popupSource, /function buildFinalizedMetadataFromHybridPayload[\s\S]*raw_dom_detail_metrics:[\s\S]*thumbnail_url: row\.thumbnail\.valid_url === "yes" \? row\.thumbnail\.url : null[\s\S]*profile_card_evidence:[\s\S]*thumbnail_url: row\.thumbnail\.valid_url === "yes" \? row\.thumbnail\.url : null[\s\S]*cover_url: row\.thumbnail\.valid_url === "yes" \? row\.thumbnail\.url : null/s, "guarded beta finalized adapter must carry the canonical hybrid thumbnail URL into raw metrics and profile card evidence for backend persistence/display");
assert.match(popupSource, /function buildFinalizedMetadataFromHybridPayload[\s\S]*view_count: viewCount,[\s\S]*real_view_count_data_quality[\s\S]*estimated_views: typeof diagnostic\.estimated_views === "number" \? diagnostic\.estimated_views : null[\s\S]*real_view_count_overwritten: false/s, "guarded beta finalized adapter must include estimated_views separately and keep nullable real view_count policy explicit");
assert.match(popupSource, /function titleEvidenceFromRecord[\s\S]*\["title", record\.title\][\s\S]*\["caption", record\.caption\][\s\S]*\["desc", record\.desc\][\s\S]*\["description", record\.description\][\s\S]*\["raw_network_aweme\.title", rawNetworkAweme\.title\][\s\S]*\["raw_network_aweme\.desc", rawNetworkAweme\.desc\][\s\S]*ids\.has\(text\)[\s\S]*source: fallback \? "aweme_id_fallback" : null[\s\S]*is_id_fallback: fallback != null[\s\S]*valid_real_text: false/s, "hybrid-only title hydration must prefer real title/caption/description text and mark aweme-id fallback explicitly");
assert.match(popupSource, /function rawLikeCountEvidenceFromRecord[\s\S]*\["statistics\.digg_count"[\s\S]*\["statistics\.like_count"[\s\S]*\["aweme_statistics\.digg_count"[\s\S]*\["aweme_statistics\.like_count"[\s\S]*\["raw_like_count"[\s\S]*\["like_count"[\s\S]*typeof raw === "number" && Number\.isFinite\(raw\)[\s\S]*exact_numeric: true[\s\S]*value_type: firstRaw == null \? "null"/s, "hybrid-only raw Likes hydration must use exact numeric trusted statistics/raw fields and expose provenance/value type");
assert.match(popupSource, /function displayLikeTextFromRecord[\s\S]*\["like_count_text", record\.like_count_text\][\s\S]*\["display_like_text", record\.display_like_text\][\s\S]*return \{ text, source \}/s, "hybrid-only display Likes text must be captured separately from raw_like_count persistence");
assert.match(popupSource, /function extraValuesFromRecord[\s\S]*title: titleEvidence\.title[\s\S]*title_source: titleEvidence\.source[\s\S]*title_is_id_fallback: titleEvidence\.is_id_fallback[\s\S]*title_valid_real_text: titleEvidence\.valid_real_text[\s\S]*raw_like_count_source: rawLikeEvidence\.source[\s\S]*raw_like_count_value_type: rawLikeEvidence\.value_type[\s\S]*raw_like_count_exact_numeric: rawLikeEvidence\.exact_numeric[\s\S]*display_like_text: displayLikeText\.text[\s\S]*rounded_like_display_rejected_for_raw: displayLikeText\.text != null && rawLikeEvidence\.exact_numeric/s, "hybrid-only extra values must expose title diagnostics and reject rounded display Likes as raw numeric Likes");
assert.match(popupSource, /function buildGuardedHybridCollectBetaDiagnosticItem[\s\S]*title: row\.extra_values\.title \?\? null[\s\S]*expected_title: row\.extra_values\.title \?\? null[\s\S]*title_source: row\.extra_values\.title_source \?\? null[\s\S]*raw_like_count: row\.metric_values\.like_count \?\? null[\s\S]*raw_like_count_source: row\.extra_values\.raw_like_count_source[\s\S]*display_like_text: row\.extra_values\.display_like_text \?\? null[\s\S]*rounded_like_display_rejected_for_raw: row\.extra_values\.rounded_like_display_rejected_for_raw === true/s, "guarded beta diagnostic payload must carry real title evidence and exact raw-like provenance while keeping display text diagnostic-only");
assert.match(popupSource, /function buildFinalizedMetadataFromHybridPayload[\s\S]*const title = guardedHybridString\(row\.extra_values\.title\)[\s\S]*raw_dom_detail_metrics:[\s\S]*title,[\s\S]*title_source: row\.extra_values\.title_source[\s\S]*raw_like_count_source: row\.extra_values\.raw_like_count_source[\s\S]*display_like_text: row\.extra_values\.display_like_text[\s\S]*profile_card_evidence:[\s\S]*title,[\s\S]*caption: title,[\s\S]*desc: title,[\s\S]*description: title/s, "guarded beta finalized adapter must persist real title fields and raw-like diagnostics into backend finalized metadata evidence");
assert.match(popupSource, /function guardedHybridCollectBetaProductionSchemaValidation[\s\S]*productionTitleDroppedFromRealDryRunCount[\s\S]*productionTitleEqualsAwemeIdWithRealTitleSourceCount[\s\S]*finalizedMetadataInvalid = canBuildPayload[\s\S]*production_title_dropped_from_real_dry_run_count[\s\S]*production_title_equals_aweme_id_with_real_title_source_count/s, "guarded beta production schema validation must reject dropped or aweme-id title payloads when dry-run title was real text");
assert.match(popupSource, /function buildGuardedHybridCollectBetaProductionRequest[\s\S]*const items: FullModalHarvestItemPayload\[\] = rows\.map\(\(row\) => buildFinalizedMetadataFromHybridPayload\(row\)\)[\s\S]*commit_policy: "finalized_only"/s, "guarded beta production request must include finalized metadata for every item and use finalized-only commit policy");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("function buildGuardedHybridCollectBetaProductionRequest"), popupSource.indexOf("function isHybridCollectBetaEligibleRow")), /write_mode|production_mutation_allowed|douyin_extension_guarded_hybrid_collect_beta_item\.v1|low_confidence_zero_real_view_count_suppressed|real_view_count_value|\bview_count_data_quality:|diagnostics:|capture_session_source|\bcaller\b/s, "guarded beta production request must exclude diagnostic-only fields, caller body fields, and local-guard-forbidden top-level keys");
assert.match(popupSource, /view_count_handling: "real_view_count_null_when_low_confidence_or_missing; estimated_views_never_copied_to_view_count"[\s\S]*finalized_metadata_built_count[\s\S]*finalized_metadata_valid_count[\s\S]*finalized_metadata_invalid_count[\s\S]*rows_where_estimated_views_copied_to_view_count/s, "guarded beta payload policy must keep estimated_views separate from real view_count and expose finalized metadata diagnostics");
assert.match(popupSource, /finalized_metadata_required[\s\S]*fix_finalized_metadata_mapping/s, "guarded beta backend finalized-metadata rejection must map to fix_finalized_metadata_mapping");
assert.match(popupSource, /beta_collect_partial_schema_gap[\s\S]*beta_collect_idempotent_success[\s\S]*beta_collect_succeeded/s, "guarded beta decision rules must distinguish accepted-but-not-persisted estimated_views, idempotent success, and full success");
assert.match(popupSource, /GUARDED_HYBRID_COLLECT_BETA_CALLER_VALUE = "whole_profile_one_item_collect_save"[\s\S]*GUARDED_HYBRID_COLLECT_BETA_FLUSH_PATH = "canonical-whole-profile-harvest-one-item"[\s\S]*GUARDED_HYBRID_COLLECT_BETA_HEADERS = \{ "X-Reup-Douyin-Flush-Path": GUARDED_HYBRID_COLLECT_BETA_FLUSH_PATH \}/s, "guarded beta must mirror canonical one-item full-modal caller through transport header metadata");
assert.match(popupSource, /callerSentAsBodyField = actualRequestBodyKeys\.includes\("caller"\)[\s\S]*callerSentAsBodyField \|\| !callerAllowed[\s\S]*\? "fix_caller_policy"[\s\S]*caller_policy: "caller_is_transport_header_metadata_not_body; mirror canonical one-item full-modal harvest"[\s\S]*caller_value: GUARDED_HYBRID_COLLECT_BETA_CALLER_VALUE[\s\S]*caller_sent_as_body_field: callerSentAsBodyField \? "yes" : "no"[\s\S]*caller_allowed: callerAllowed \? "yes" : "no"[\s\S]*actual_request_body_key_count: actualRequestBodyKeys\.length[\s\S]*actual_request_disallowed_fields: actualRequestDisallowedFields/s, "guarded beta schema validation must validate caller policy against the actual request body and expose caller diagnostics");
assert.match(popupSource, /production_request_preview_keys: productionRequestPreviewKeys[\s\S]*actual_request_body_keys_before_client: productionRequestPreviewKeys[\s\S]*actual_request_body_keys_after_client_if_available: productionRequestPreviewKeys[\s\S]*caller_source: "transport_header:X-Reup-Douyin-Flush-Path"[\s\S]*caller_sent_as_body_field: payloadSchemaValidation\.caller_sent_as_body_field[\s\S]*caller_value: GUARDED_HYBRID_COLLECT_BETA_CALLER_VALUE/s, "guarded beta summary must expose request-key and caller-source diagnostics for preview/actual alignment");
assert.match(popupSource, /backend_write: \{ \.\.\.backendWrite,[\s\S]*raw_ok[\s\S]*normalized_ok[\s\S]*beta_write_effective_status[\s\S]*backend_raw_rejected_count[\s\S]*normalized_rejected_count[\s\S]*idempotent_unchanged_count[\s\S]*safe_for_post_verify[\s\S]*finalized_metadata_received_count[\s\S]*finalized_metadata_accepted_count[\s\S]*accepted_not_persisted_fields[\s\S]*estimated_views_persisted_count[\s\S]*caller_value: GUARDED_HYBRID_COLLECT_BETA_CALLER_VALUE[\s\S]*caller_policy: "transport_header_metadata_not_body"[\s\S]*local_guard_passed:/s, "guarded beta backend summary must report normalized idempotent diagnostics, finalized metadata diagnostics, persistence gaps, caller value, caller policy, and local guard status");
assert.match(popupSource, /backendJson<Record<string, unknown>>\("POST", GUARDED_HYBRID_COLLECT_BETA_PRODUCTION_ENDPOINT, payloadPreview, \{ requestStage: "full_modal_harvest", headers: \{ \.\.\.GUARDED_HYBRID_COLLECT_BETA_HEADERS \} \}\)/s, "guarded beta backend call must send the canonical full-modal flush-path header instead of a body caller field");
assert.match(popupSource, /production_collect_state_mutated: backendStatus\?\.normalizedOk === true \? "yes_existing_backend_success_only_no_local_queue_mutation" : "no"[\s\S]*queue_items_marked_complete_count: 0[\s\S]*queue_items_marked_complete: "no_local_queue_completion_by_beta_action"[\s\S]*collect_job_mutated: "no"[\s\S]*counters_refreshed: backendStatus\?\.normalizedOk === true \? "yes_existing_backend_success_only" : "no"/s, "guarded beta must not mark queue complete, mutate collect_job, or refresh counters on schema/backend failure");
assert.match(popupSource, /payloadSchemaValidation\.backend_call_allowed !== "yes"[\s\S]*Guarded hybrid collect beta blocked by production payload schema[\s\S]*backendJson<Record<string, unknown>>\("POST", GUARDED_HYBRID_COLLECT_BETA_PRODUCTION_ENDPOINT, payloadPreview[\s\S]*safe_for_post_verify[\s\S]*Guarded hybrid collect beta backend write failed or is blocked; no local queue completion was applied/s, "guarded beta action must block before backend when schema validation fails and report no local queue completion on failure");
assert.match(popupSource, /const backendStatus = backendResult \? guardedHybridBackendWriteStatus[\s\S]*"beta_collect_partial_schema_gap"[\s\S]*"beta_collect_idempotent_success"[\s\S]*"beta_collect_succeeded"[\s\S]*"beta_collect_backend_failed"[\s\S]*"beta_collect_payload_schema_unsupported"[\s\S]*"beta_collect_payload_schema_invalid"/s, "guarded beta decision rules must distinguish backend failure, unsupported production schema, invalid schema, partial schema gap, idempotent success, and success");
assert.match(popupSource, /summary_title: "GUARDED_HYBRID_COLLECT_BETA_POST_VERIFY_SUMMARY"[\s\S]*source_artifact:[\s\S]*backend_lookup:[\s\S]*field_persistence:[\s\S]*status_semantics:[\s\S]*counter_reconciliation:[\s\S]*safety:[\s\S]*decision:[\s\S]*representative_items/s, "post-verify summary must expose source artifact, backend lookup, field persistence, status semantics, reconciliation, safety, decision, and representative items");
// Root cause of all_backend_items_not_found_for_accepted_aweme_ids: a false idempotent-skip. The backend reason
// `accepted_payload_but_no_capture_inbox_item_created_or_updated` means NO row was created or matched (the record does not
// exist), so it must DISQUALIFY idempotent_success rather than being used as an escape hatch that zeroes failed/rejected
// counts. idempotent_success must require confirmed existing records (matched === target AND unchanged === target).
assert.match(popupSource, /const acceptedButNothingPersistedReason = reasons\.some\(\(reason\) => reason === "accepted_payload_but_no_capture_inbox_item_created_or_updated"\);/s, "backend write status must detect the accepted-but-nothing-persisted reason as a disqualifier, not an escape hatch");
assert.match(popupSource, /const selfReportedConfirmedExistingRecords = matchedCount === targetCount && unchangedCount === targetCount;/s, "idempotent_success must require confirmed existing records: matched and unchanged both equal target (self-reported, used only when verify-after-write was not attempted)");
assert.match(popupSource, /const idempotentSuccess = targetCount > 0 && acceptedInvariant && matchedInvariant && unchangedInvariant && confirmedExistingRecords && updatedCount === 0 && rawFailedCount === 0 && rawRejectedCount === 0 && !acceptedButNothingPersistedReason && estimatedViewsPersisted;/s, "idempotent_success must require confirmed existing records and zero genuine failures/rejections, and must never be derived from the accepted-but-nothing-persisted reason");
assert.match(popupSource, /const backendDeclaredIdempotent = confirmedExistingRecords && \(backendResult\.beta_write_effective_status === "idempotent_success" \|\| Number\(backendResult\.idempotent_unchanged_count \?\? 0\) > 0\);/s, "a backend-declared idempotent status must only be honored when existing records are confirmed (matched and unchanged equal target)");
// Read-only beta backend evidence dump: it must mirror the EXACT post-verify id-set derivation, use the SAME verify
// endpoint, and issue two lookups (scoped by capture_session_id and unscoped by aweme_ids only) so the contradiction
// (idempotent_success vs zero items found) is resolved with real data: false-idempotent-skip vs lookup-scope-mismatch.
assert.match(popupSource, /async function buildGuardedHybridCollectBetaBackendEvidenceDump\(\): Promise<Record<string, unknown>>/s, "a read-only beta backend evidence dump builder must exist");
assert.match(popupSource, /read_only: true,[\s\S]*storage_mutation: "none",[\s\S]*pipeline_stages_rerun: "none",/s, "the evidence dump must declare itself read-only with no storage mutation and no pipeline rerun");
assert.match(popupSource, /const postVerifyAcceptedAwemeIds = guardedHybridUniqueStrings\(\[\.\.\.\(source\.accepted_aweme_ids \?\? \[\]\), \.\.\.\(source\.flushed_aweme_ids \?\? \[\]\)\]\)\.slice\(0, requiredBetaBatchSize \|\| undefined\);/s, "the evidence dump must derive the post-verify lookup id set identically to buildGuardedHybridCollectBetaPostVerifySummary");
assert.match(popupSource, /const verifyEndpoint = "\/douyin-extension\/capture-inbox\/items\/verify";/s, "the evidence dump must use the same verify endpoint post-verify uses");
assert.match(popupSource, /const idSetsIdentical = productionAcceptedAwemeIds\.length === postVerifyAcceptedAwemeIds\.length && productionAcceptedAwemeIds\.every\(\(id\) => postVerifyAcceptedAwemeIds\.includes\(id\)\);/s, "the evidence dump must compute whether the production write id set and the post-verify lookup id set are identical");
assert.match(popupSource, /aweme_ids: postVerifyAcceptedAwemeIds, source_video_external_ids: postVerifySourceVideoExternalIds, capture_session_id: captureSessionId,/s, "the evidence dump scoped lookup must filter by the source capture_session_id exactly as post-verify does");
assert.match(popupSource, /backendJson<Record<string, unknown>>\("POST", verifyEndpoint, \{ aweme_ids: postVerifyAcceptedAwemeIds, source_video_external_ids: postVerifySourceVideoExternalIds, limit:/s, "the evidence dump unscoped lookup must query by aweme_ids only (no capture_session_id) to detect a run-scope mismatch");
assert.match(popupSource, /} else if \(unscopedFoundCount === 0\) \{[\s\S]*verdict = "false_idempotent_skip_no_backend_record";/s, "if no record exists under any scope the verdict must be false_idempotent_skip_no_backend_record");
assert.match(popupSource, /} else if \(unscopedFoundCount > 0 && scopedFoundCount < unscopedFoundCount\) \{[\s\S]*verdict = "lookup_scope_mismatch_capture_session_id";/s, "if records exist unscoped but are filtered out when scoped, the verdict must be lookup_scope_mismatch_capture_session_id");
// Round 6/7: verify-before/after-write. The live verdict is false-idempotent-skip (backend returns zero items under valid
// auth while the write self-reports idempotent_success), so idempotent_success must require an INDEPENDENT confirmed backend
// record, not the write response's self-reported matched/unchanged counts. The action handler performs read-only verifies
// against /items/verify; verify-before-write can short-circuit only when every target already exists, and verify errors are
// reported as idempotent_check_inconclusive instead of success or confirmed-zero failure.
assert.match(popupSource, /async function guardedHybridCollectBetaVerifyBeforeWriteConfirmedCount\(/s, "a verify-before-write helper must independently check whether every target record already exists");
assert.match(popupSource, /async function guardedHybridCollectBetaVerifyBeforeWriteConfirmedCount[\s\S]*backendJson<Record<string, unknown>>\("POST", "\/douyin-extension\/capture-inbox\/items\/verify", \{ aweme_ids: writtenAwemeIds, source_video_external_ids: writtenAwemeIds, capture_session_id: captureSessionId,/s, "verify-before-write must query the same verify endpoint/scope as post-verify with the target aweme_ids");
assert.match(popupSource, /const verifyBeforeWrite = await guardedHybridCollectBetaVerifyBeforeWriteConfirmedCount\(payloadPreview\);[\s\S]*verify_before_write_confirmed_count: verifyBeforeWrite\.confirmed_count,[\s\S]*verify_before_write_error: verifyBeforeWrite\.error/s, "the beta collect action must run verify-before-write and thread its confirmation/error diagnostics into the backend result before summary building");
assert.match(popupSource, /async function guardedHybridCollectBetaVerifyAfterWriteConfirmedCount\(/s, "a verify-after-write helper must independently confirm the written records exist");
assert.match(popupSource, /backendJson<Record<string, unknown>>\("POST", "\/douyin-extension\/capture-inbox\/items\/verify", \{ aweme_ids: writtenAwemeIds, source_video_external_ids: writtenAwemeIds, capture_session_id: captureSessionId,/s, "verify-after-write must query the same verify endpoint/scope post-verify uses, with the written aweme_ids");
assert.match(popupSource, /const verifyAfterWrite = await guardedHybridCollectBetaVerifyAfterWriteConfirmedCount\(payloadPreview, backendResult\);[\s\S]*verify_after_write_confirmed_count: verifyAfterWrite\.confirmed_count,/s, "the beta collect action must run verify-after-write and thread the confirmed count into the backend result before building the summary");
assert.match(popupSource, /const verifyAfterWriteConfirmsAll = verifyAfterWriteAttempted && targetCount > 0 && verifyAfterWriteConfirmedCount >= targetCount;/s, "verify-after-write confirms all only when it independently found every target id");
assert.match(popupSource, /const anyVerifyAttempted = verifyBeforeWriteAttempted \|\| verifyAfterWriteAttempted;[\s\S]*const confirmedExistingRecords = anyVerifyAttempted \? \(verifyAfterWriteConfirmsAll \|\| verifyBeforeWriteConfirmsAll\) : selfReportedConfirmedExistingRecords;/s, "when either independent verify was attempted it overrides backend self-reported counts as the confirmed-records authority");
assert.match(popupSource, /const idempotentCheckInconclusive = \(verifyBeforeWriteInconclusive \|\| verifyAfterWriteInconclusive\) && !verifyAfterWriteConfirmsAll && !verifyBeforeWriteConfirmsAll;[\s\S]*const effectiveStatus = idempotentCheckInconclusive \? "idempotent_check_inconclusive"/s, "verify call errors must emit idempotent_check_inconclusive unless another independent verify confirms all target ids");
assert.match(popupSource, /const verifyAfterWriteVetoesSuccess = verifyAfterWriteAttempted && !verifyAfterWriteConfirmsAll && !verifyBeforeWriteConfirmsAll;[\s\S]*const normalizedOk = !verifyAfterWriteVetoesSuccess && !idempotentCheckInconclusive && \(backendResult\.ok === true \|\| idempotentSuccess\);/s, "a verify-after-write that did not confirm every target id must veto normalizedOk unless verify-before-write already confirmed existing records");
assert.match(popupSource, /type HybridCollectBetaProductionSource[\s\S]*expected_title_by_aweme_id\?: Record<string, unknown>[\s\S]*expected_thumbnail_url_by_aweme_id\?: Record<string, unknown>[\s\S]*expected_duration_seconds_by_aweme_id\?: Record<string, unknown>[\s\S]*expected_comment_count_by_aweme_id\?: Record<string, unknown>[\s\S]*expected_favorite_count_by_aweme_id\?: Record<string, unknown>[\s\S]*expected_share_count_by_aweme_id\?: Record<string, unknown>[\s\S]*expected_estimated_views_formula\?: string[\s\S]*expected_null_view_count_policy\?: string/s, "guarded beta source artifact type must include title, all expected post-verify maps, formula, and null view-count policy");
assert.match(popupSource, /function hybridCollectBetaProductionSourceFromSummary[\s\S]*const expectedMapItems = items\.length \? items : acceptedItems[\s\S]*accepted_items: acceptedItems[\s\S]*expected_title_by_aweme_id[\s\S]*expected_thumbnail_url_by_aweme_id[\s\S]*expected_duration_seconds_by_aweme_id[\s\S]*expected_raw_like_count_by_aweme_id[\s\S]*expected_comment_count_by_aweme_id[\s\S]*expected_favorite_count_by_aweme_id[\s\S]*expected_share_count_by_aweme_id[\s\S]*expected_estimated_views_by_aweme_id[\s\S]*expected_estimated_views_input_like_count_by_aweme_id[\s\S]*expected_estimated_views_input_source_by_aweme_id[\s\S]*expected_estimated_views_formula: "tiered_like_multiplier_v1"[\s\S]*expected_null_view_count_policy/s, "guarded beta must build a durable latest successful production source artifact with title and metric-complete expected-value maps from production request items");
assert.match(popupSource, /function guardedHybridExpectedItemsFromSource[\s\S]*source\.accepted_items[\s\S]*source\.expected_items[\s\S]*source\.representative_items[\s\S]*summary\.representative_items[\s\S]*productionRequest\.items[\s\S]*diagnosticPreview\.items[\s\S]*function guardedHybridExpectedRecordForAwemeId[\s\S]*expected_title_by_aweme_id[\s\S]*expected_thumbnail_url_by_aweme_id[\s\S]*expected_duration_seconds_by_aweme_id[\s\S]*expected_raw_like_count_by_aweme_id[\s\S]*expected_comment_count_by_aweme_id[\s\S]*expected_favorite_count_by_aweme_id[\s\S]*expected_share_count_by_aweme_id[\s\S]*expected_title: titleMap\[awemeId\][\s\S]*share_count: shareMap\[awemeId\][\s\S]*share_count_expected: shareMap\[awemeId\][\s\S]*expected_estimated_views_by_aweme_id[\s\S]*expected_estimated_views_input_like_count_by_aweme_id[\s\S]*expected_estimated_views_input_source_by_aweme_id/s, "post-verify must recover expected title and metric values, including share_count zero-safe maps, from durable maps and backward-compatible source-artifact item fallbacks");
assert.match(popupSource, /allowedVerdict = decision\.verdict === "beta_collect_succeeded" \|\| decision\.verdict === "beta_collect_idempotent_success"[\s\S]*estimatedViewsPersisted[\s\S]*source\.accepted_count > 0[\s\S]*chrome\.storage\.local\.set\(\{ \[HYBRID_COLLECT_BETA_LATEST_PRODUCTION_STORAGE_KEY\]: source \}\)/s, "guarded beta must persist the source artifact after successful accepted production writes, including idempotent accepted unchanged writes");
assert.match(popupSource, /const requiredBetaBatchSize = source\?\.beta_batch_size === 10 \? 10 : source\?\.beta_batch_size === 5 \? 5 : source\?\.beta_batch_size === 3 \? 3 : 0;[\s\S]*const acceptedAwemeIds = guardedHybridUniqueStrings\(\[\.\.\.\(source\?\.accepted_aweme_ids \?\? \[\]\), \.\.\.\(source\?\.flushed_aweme_ids \?\? \[\]\)\]\)\.slice\(0, requiredBetaBatchSize \|\| undefined\)[\s\S]*methodSelected = "aweme_id_lookup"[\s\S]*endpointOrMethod = "\/douyin-extension\/capture-inbox\/items\/verify"[\s\S]*capture_session_id: source\.capture_session_id/s, "post-verify must use accepted/flushed aweme/source IDs capped to the beta or pilot source batch size and optional capture session for backend lookup without requiring profile_url");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildGuardedHybridCollectBetaPostVerifySummary"), popupSource.indexOf("async function runGuardedHybridCollectBetaPostVerifyFromPopup")), /unavailable_profile_url_missing/, "post-verify must not fail lookup solely because profile_url is unavailable");
assert.match(popupSource, /partialExpected = true[\s\S]*partialBlocking = persisted\.some\(\(item\) => item\.metadata_status === "partial"\) && !partialExpected[\s\S]*metadata_status_partial_expected: partialExpected[\s\S]*guarded_hybrid_network_cache writes may be partial/s, "post-verify must treat guarded hybrid partial metadata as explicit expected semantics and block partial only when not expected");
assert.match(popupSource, /estimatedViewsMatchedCount = acceptedAwemeIds\.filter[\s\S]*guardedHybridEstimatedViewsMatchesExpected[\s\S]*estimatedViewsMismatchCount = acceptedAwemeIds\.filter[\s\S]*fieldPersistence\.estimated_views_mismatch_count > 0[\s\S]*estimated_views_expected[\s\S]*estimated_views_actual[\s\S]*estimated_views_match/s, "post-verify must compare expected vs actual estimated_views, report mismatches, and expose representative diagnostics");
assert.match(popupSource, /function guardedHybridNonNegativeNumber\(value: unknown\): number \| null \{\s*const numeric = typeof value === "number" \? value : typeof value === "string" && value\.trim\(\) !== "" \? Number\(value\) : Number\.NaN;\s*return Number\.isFinite\(numeric\) && numeric >= 0 \? numeric : null;\s*\}[\s\S]*function guardedHybridShareCountDiagnostics[\s\S]*share_count_expected_count: reads\.filter\(\(read\) => read\.expected != null\)\.length[\s\S]*share_count_actual_count: reads\.filter\(\(read\) => read\.actual\.value != null\)\.length[\s\S]*share_count_match_count: reads\.filter\(\(read\) => read\.expected != null && read\.actual\.value === read\.expected\)\.length[\s\S]*share_count_missing_count: reads\.filter\(\(read\) => read\.expected != null && read\.actual\.value == null\)\.length[\s\S]*share_count_read_path: primaryPath[\s\S]*share_count_write_present_count: reads\.filter\(\(read\) => read\.expected != null\)\.length/s, "post-verify must count share_count expected/actual/matches/missing with zero treated as a valid non-negative number");
assert.match(popupSource, /const expectedValuesMissing = required > 0[\s\S]*titleExpectedCount !== required[\s\S]*shareCountExpectedCount !== required[\s\S]*const persistenceMismatch = required > 0 && \(missingCount > 0[\s\S]*fieldPersistence\.title_mismatch_count > 0[\s\S]*fieldPersistence\.title_id_fallback_mismatch_count > 0[\s\S]*shareCountMissingCount > 0[\s\S]*shareCountExpectedCount === required && shareCountMatchCount !== required[\s\S]*fieldPersistence\.estimated_views_mismatch_count > 0[\s\S]*fieldPersistence\.estimated_views_persisted_count !== required[\s\S]*fieldPersistence\.view_count_null_persisted_count !== required[\s\S]*fieldPersistence\.real_view_count_data_quality_persisted_count !== required[\s\S]*beta_post_verify_inconclusive_expected_values_missing[\s\S]*beta_post_verify_failed_persistence_mismatch[\s\S]*expected_title_values_missing[\s\S]*title_missing_or_mismatched[\s\S]*expected_share_count_values_missing/s, "post-verify must distinguish missing expected title/share source values from backend persistence mismatches and block title ID fallback mismatches");
// When the backend lookup returns NO matching items, all five fields fail at once. The verdict must say so explicitly
// (backend items not found) rather than presenting a misleading per-field persistence mismatch, and a precise blocker must
// surface so the operator knows the read-back failed at the lookup, not at individual field persistence.
assert.match(popupSource, /const allBackendItemsMissing = required > 0 && persisted\.length === 0 && lookupAttempted;/s, "post-verify must detect the all-backend-items-missing case (lookup attempted but zero items returned)");
assert.match(popupSource, /allBackendItemsMissing \? "beta_post_verify_failed_backend_items_not_found" : persistenceMismatch \? "beta_post_verify_failed_persistence_mismatch"/s, "all-backend-items-missing must take verdict precedence over the generic persistence-mismatch verdict");
assert.match(popupSource, /allBackendItemsMissing \? "all_backend_items_not_found_for_accepted_aweme_ids" : null/s, "post-verify blockers must include a precise all_backend_items_not_found marker when the lookup returns nothing");
assert.match(popupSource, /!source \? "rerun_guarded_hybrid_collect_beta_3_then_verify"[\s\S]*verdict === "beta_post_verify_passed" && requiredBetaBatchSize === 3 \? "run_guarded_hybrid_collect_beta_5"[\s\S]*verdict === "beta_post_verify_passed" && requiredBetaBatchSize === 5 \? "prepare_controlled_start_collecting_integration_plan"[\s\S]*blockers\.includes\("expected_share_count_values_missing"\) \|\| blockers\.includes\("expected_values_missing_from_source_artifact"\) \? "rerun_guarded_hybrid_collect_beta_5_after_artifact_schema_fix"[\s\S]*verdict === "beta_post_verify_failed_persistence_mismatch" \? "fix_backend_persistence_before_expanding"[\s\S]*"fix_metadata_status_mapping"[\s\S]*"add_backend_lookup_for_beta_written_items"/s, "post-verify must recommend rerunning beta 5 after artifact schema fix for old missing expected source values and backend fixes only for persistence mismatches");
// Regression guard (Problem 1): the beta post-verify builder must accept an optional in-memory source override and use it
// verbatim without touching the shared beta production storage key, so a verify against pilot data can never pollute the
// shared beta production artifact (which previously caused beta_5 post-verify to read pilot data and fail with an
// all-field persistence mismatch).
assert.match(popupSource, /async function buildGuardedHybridCollectBetaPostVerifySummary\(sourceOverride\?: HybridCollectBetaProductionSource \| null\): Promise<Record<string, unknown>> \{\s*const source = sourceOverride !== undefined \? sourceOverride : await readHybridCollectBetaLatestProductionSource\(\);/s, "beta post-verify must accept a non-mutating in-memory source override and only read the shared beta production key when no override is provided");
// The pilot post-verify builder must verify via the override path and must NOT swap/restore the shared beta production key.
{
  const pilotPostVerifyBody = popupSource.slice(popupSource.indexOf("async function buildGuardedHybridStartCollectingPilotPostVerifySummary"), popupSource.indexOf("async function runGuardedHybridStartCollectingPilotPostVerifyFromPopup"));
  assert.match(pilotPostVerifyBody, /const betaSummary = await buildGuardedHybridCollectBetaPostVerifySummary\(\{ \.\.\.source, beta_batch_size: expectedBatchSize \}\);/s, "pilot post-verify must verify the pilot source through the in-memory override instead of mutating the shared beta production key");
  assert.doesNotMatch(pilotPostVerifyBody, /chrome\.storage\.local\.set\(\{ \[HYBRID_COLLECT_BETA_LATEST_PRODUCTION_STORAGE_KEY\]/s, "pilot post-verify must never write the shared beta production storage key (no destructive swap/restore)");
  assert.doesNotMatch(pilotPostVerifyBody, /\bpreviousBetaSource\b/s, "pilot post-verify must not retain the previousBetaSource swap/restore logic");
}
// Regression guard (Problem 2): the pilot and queue-completion flag checkboxes must be rehydrated from storage on popup
// open so an operator-enabled flag survives a popup reopen instead of silently reading false.
assert.match(popupSource, /async function applyHybridPilotAndQueueCompletionFlags\(\): Promise<void> \{[\s\S]*hybridEstimatedViewsStartCollectingPilotEnabledInput\.checked = pilotStored\[HYBRID_ESTIMATED_VIEWS_START_COLLECTING_PILOT_STORAGE_KEY\] === true;[\s\S]*hybridStartCollectingPilotQueueCompletionEnabledInput\.checked = queue10Stored\[HYBRID_START_COLLECTING_PILOT_QUEUE_COMPLETION_STORAGE_KEY\] === true;[\s\S]*hybridStartCollectingPilot50QueueCompletionEnabledInput\.checked = queue50Stored\[HYBRID_START_COLLECTING_PILOT_50_QUEUE_COMPLETION_STORAGE_KEY\] === true;/s, "popup must rehydrate the pilot and both queue-completion flag checkboxes from chrome.storage.local on open");
assert.match(popupSource, /await applyHybridEstimatedViewsCollectBetaFlag\(\);\s*await applyHybridPilotAndQueueCompletionFlags\(\);/s, "popup init must call the pilot/queue-completion flag rehydrate alongside the beta flag rehydrate");
// next_action must never advance past a failing foundational gate. The compact status must compute foundational gate
// state and force the search start to index 0 (the blocked foundational step) instead of fast-forwarding to a later
// milestone like queue_completion_pilot_50.
assert.match(popupSource, /const foundationalStepNames = \["hybrid_only_dry_run_50", "backend_shadow_5", "guarded_hybrid_collect_beta_5", "guarded_hybrid_collect_beta_5_post_verify"\];/s, "compact status must define the foundational gate step names");
assert.match(popupSource, /const firstFailingFoundationalIndex = steps\.findIndex\(\(step\) => foundationalStepNames\.includes\(String\(step\.name\)\) && step\.passed !== true\);[\s\S]*const foundationalGatesPassed = firstFailingFoundationalIndex < 0;/s, "compact status must detect the first failing foundational gate");
assert.match(popupSource, /const nextSearchStart = foundationalGatesPassed \? milestoneFastForwardStart : 0;/s, "compact status next_action search must restart at index 0 when a foundational gate is failing so the blocked gate is surfaced, not skipped");
assert.match(popupSource, /highestPassedMilestone = !foundationalGatesPassed \? "none"/s, "highest_passed_milestone must be none while a foundational gate is failing");
assert.match(popupSource, /foundational_gate: \{[\s\S]*all_foundational_gates_passed: foundationalGatesPassed[\s\S]*first_failing_foundational_step: foundationalGatesPassed \? null : String\(steps\[firstFailingFoundationalIndex\]\?\.name[\s\S]*milestone_fast_forward_suppressed_by_foundational_gate: !foundationalGatesPassed && \(pilot50MilestoneAuthorityPassed[\s\S]*next_action_blocked_at_foundational_gate: !foundationalGatesPassed/s, "compact status must surface a foundational_gate block showing the blocked gate suppressed any milestone fast-forward");
// Beta post-verify must detect a beta production artifact contaminated with Pilot data (from a prior build's destructive
// swap) on the storage-read path only, and report an inconclusive contamination verdict instead of a misleading all-field
// persistence mismatch. The in-memory override path (sourceOverride !== undefined) must NOT be flagged.
assert.match(popupSource, /function guardedHybridBetaSourcePilotContamination\(source: HybridCollectBetaProductionSource \| null\): \{ contaminated: boolean; markers: string\[\] \}/s, "beta post-verify must define a pilot-contamination detector for the shared beta production artifact");
assert.match(popupSource, /record\.feature_flag_name === HYBRID_ESTIMATED_VIEWS_START_COLLECTING_PILOT_STORAGE_KEY\) markers\.push\("feature_flag_name_is_pilot"\)/s, "contamination detector must treat a Pilot feature flag marker on the beta artifact as contamination");
assert.match(popupSource, /if \(sourceOverride === undefined\) \{[\s\S]*guardedHybridBetaSourcePilotContamination\(source\);[\s\S]*beta_post_verify_inconclusive_source_artifact_contaminated_by_pilot/s, "beta post-verify must only run contamination detection on the storage-read path and emit a contamination verdict");
assert.doesNotMatch(popupSource, /contaminated_artifact_auto_repaired: "yes"/s, "beta post-verify must not auto-repair or auto-rerun on contamination; recovery is an explicit operator beta rerun");
assert.match(popupSource, /backend_write_attempted: "no"[\s\S]*production_collect_state_mutated: "no"[\s\S]*collect_job_mutated: "no"[\s\S]*queue_items_marked_complete_count: 0/s, "post-verify must remain read-only and report no backend write, production collect state, local queue, or collect_job mutation");
assert.match(popupHtml, /id="runGuardedHybridStartCollectingPilot5Button"[\s\S]*Run Guarded Hybrid Start Collecting Pilot \(5\)[\s\S]*id="runGuardedHybridStartCollectingPilot10Button"[\s\S]*Run Guarded Hybrid Start Collecting Pilot \(10\)[\s\S]*id="runGuardedHybridStartCollectingPilot50Button"[\s\S]*Run Guarded Hybrid Start Collecting Pilot \(50\)[\s\S]*id="postVerifyGuardedHybridStartCollectingPilotButton"[\s\S]*Run Guarded Hybrid Start Collecting Pilot Post-Verify/, "popup must expose Pilot 5, Pilot 10, Pilot 50, and pilot post-verify actions only in Advanced Details controls");
assert.match(popupHtml, /id="hybridStartCollectingPilotQueueCompletionEnabled"[\s\S]*Enable Pilot Queue Completion[\s\S]*id="runGuardedHybridStartCollectingQueueCompletionPilotButton"[\s\S]*Complete Verified Pilot Queue Items[\s\S]*id="postVerifyGuardedHybridStartCollectingQueueCompletionPilotButton"[\s\S]*Run Queue Completion Pilot Post-Verify[\s\S]*GUARDED_HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_SUMMARY[\s\S]*GUARDED_HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_POST_VERIFY_SUMMARY/, "popup must expose the separate guarded queue-completion pilot flag, action, post-verify action, and summaries");
assert.match(popupHtml, /id="hybridStartCollectingPilot50QueueCompletionEnabled"[\s\S]*Enable Pilot 50 Queue Completion[\s\S]*id="runGuardedHybridStartCollectingQueueCompletionPilot50Button"[\s\S]*Complete Verified Pilot 50 Queue Items[\s\S]*id="postVerifyGuardedHybridStartCollectingQueueCompletionPilot50Button"[\s\S]*Run Queue Completion Pilot 50 Post-Verify[\s\S]*GUARDED_HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_SUMMARY[\s\S]*GUARDED_HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_POST_VERIFY_SUMMARY/, "popup must expose separate Pilot 50 queue-completion flag, action, post-verify action, and summaries");
assert.match(popupSource, /guardedHybridStartCollectingPilot5Button\?\.addEventListener\("click", \(\) => void runGuardedHybridStartCollectingPilotFromPopup\(5\)\);[\s\S]*guardedHybridStartCollectingPilot10Button\?\.addEventListener\("click", \(\) => void runGuardedHybridStartCollectingPilotFromPopup\(10\)\);[\s\S]*guardedHybridStartCollectingPilot50Button\?\.addEventListener\("click", \(\) => void runGuardedHybridStartCollectingPilotFromPopup\(50\)\);/, "popup must wire separate Pilot 5, Pilot 10, and Pilot 50 guarded Start Collecting pilot actions");
assert.match(popupSource, /HYBRID_START_COLLECTING_PILOT_QUEUE_COMPLETION_STORAGE_KEY = "hybridStartCollectingPilotQueueCompletionEnabled"[\s\S]*HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_LATEST_STORAGE_KEY = "hybridStartCollectingQueueCompletionPilotLatest"[\s\S]*feature_flag_default: false/, "queue-completion pilot must use a separate default-off feature flag and persist a separate latest artifact");
assert.match(popupSource, /guardedHybridStartCollectingQueueCompletionPilotButton\?\.addEventListener\("click", \(\) => void runGuardedHybridStartCollectingQueueCompletionPilot\(\)\);[\s\S]*postVerifyGuardedHybridStartCollectingQueueCompletionPilotButton\?\.addEventListener\("click", \(\) => void runGuardedHybridStartCollectingQueueCompletionPilotPostVerifyFromPopup\(\)\);/, "queue-completion pilot must be operator-triggered through separate action routes");
assert.match(popupSource, /HYBRID_START_COLLECTING_PILOT_50_QUEUE_COMPLETION_STORAGE_KEY = "hybridStartCollectingPilot50QueueCompletionEnabled"[\s\S]*HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_STORAGE_KEY = "hybridStartCollectingQueueCompletionPilot50Latest"[\s\S]*feature_flag_default: false/, "Pilot 50 queue-completion must use a separate default-off feature flag and persist a separate latest artifact");
assert.match(popupSource, /guardedHybridStartCollectingQueueCompletionPilot50Button\?\.addEventListener\("click", \(\) => void runGuardedHybridStartCollectingQueueCompletionPilot50\(\)\);[\s\S]*postVerifyGuardedHybridStartCollectingQueueCompletionPilot50Button\?\.addEventListener\("click", \(\) => void runGuardedHybridStartCollectingQueueCompletionPilot50PostVerifyFromPopup\(\)\);/, "Pilot 50 queue-completion must be operator-triggered through separate action routes");
assert.match(popupSource, /async function resolveGuardedHybridQueueCompletionPilot10Authority[\s\S]*const rebuiltPilotPostVerify = await buildGuardedHybridStartCollectingPilotPostVerifySummary\(\);[\s\S]*HYBRID_START_COLLECTING_PILOT_LATEST_POST_VERIFY_STORAGE_KEY[\s\S]*const authorityBlockers = compactGuardedPilotPostVerifyMilestoneBlockers\(storedCandidate, 10, source\);[\s\S]*readiness: \{ \.\.\.authorityReadiness, ready_to_enable_queue_completion: true, blockers: \[\] \}[\s\S]*latestPilot10PostVerifyPassed: true/s, "queue-completion pilot readiness must prefer highest valid stored Pilot 10 post-verify milestone authority over a fresh lower-stage rebuild");
assert.match(popupSource, /async function resolveGuardedHybridQueueCompletionPilot10Authority[\s\S]*lowerStageLatestAttemptFailed = rebuiltDecision\.post_verify_verdict !== "pilot_post_verify_passed" \|\| rebuiltReadinessBlockers\.length > 0[\s\S]*ignored_lower_stage_failure_reason: lowerStageLatestAttemptFailed \? "higher_passed_pilot_10_post_verify_authority" : null/s, "failed lower-stage or latest rebuilt post-verify diagnostics must be isolated when higher Pilot 10 authority is valid");
assert.match(popupSource, /async function buildGuardedHybridStartCollectingQueueCompletionPilotSummary\(applyCompletion: boolean\)[\s\S]*const pilot10Authority = await resolveGuardedHybridQueueCompletionPilot10Authority\(source\);[\s\S]*pilot10Authority\.latestPilot10PostVerifyPassed \? null : "latest_pilot_10_post_verify_not_passed"[\s\S]*readiness\.ready_to_enable_queue_completion === true[\s\S]*readinessBlockers\.length === 0[\s\S]*expectedBatchSize === 10[\s\S]*uniqueAcceptedAwemeIds\.length === 10[\s\S]*active_collect_job_running[\s\S]*scan_action_lock_active/s, "queue-completion pilot must use authoritative Pilot 10 post-verify readiness, exact 10 verified IDs, and runtime locks before local completion");
assert.match(popupSource, /function guardedHybridQueueCompletionAcceptedIds[\s\S]*source\?\.accepted_aweme_ids[\s\S]*source\?\.flushed_aweme_ids[\s\S]*source\?\.source_video_external_ids[\s\S]*latest_pilot_10_source_artifact_after_authoritative_pilot_post_verify/s, "queue-completion pilot must load verified aweme IDs from the latest Pilot 10 source artifact after authoritative post-verify");
assert.match(popupSource, /const verifiedIdSet = new Set\(uniqueAcceptedAwemeIds\);[\s\S]*queueBefore\.filter\(\(item\) => verifiedIdSet\.has\(item\.aweme_id\)\)[\s\S]*if \(!verifiedIdSet\.has\(item\.aweme_id\)\) return item;[\s\S]*match_strategy: "exact_aweme_id_intersection_only_no_count_or_index_completion"/s, "queue-completion pilot must match and complete only exact aweme ID intersections, never by count or index");
assert.match(popupSource, /backend_write_attempted: "no"[\s\S]*normal_start_collecting_run: "no"[\s\S]*local_queue_state_storage_key: WHOLE_PROFILE_HARVEST_STATE_KEY[\s\S]*collect_job_mutated: collectJobBefore === collectJobAfter \? "no" : "yes"[\s\S]*scan_state_reset: "no"[\s\S]*pending_queue_cleared_globally: "no"/s, "queue-completion pilot must remain local queue-state-only and detect collect_job mutation without backend writes, normal Start Collecting, scan reset, or global queue clearing");
assert.match(popupSource, /async function buildGuardedHybridStartCollectingQueueCompletionPilotPostVerifySummary[\s\S]*GUARDED_HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_POST_VERIFY_SUMMARY[\s\S]*complete_now_count[\s\S]*still_incomplete_aweme_ids[\s\S]*non_verified_queue_items_completed_count[\s\S]*evaluate_limited_queue_completion_enablement_or_run_pilot_20/s, "queue-completion pilot post-verify must verify completion, non-verified protection, safety, and final next recommendation");
assert.match(popupSource, /type GuardedHybridStartCollectingPilotBatchSize = 5 \| 10 \| 50;[\s\S]*const requestedBatchSize = batchSize;[\s\S]*const preselectedRows = blockers\.length === 0 \? eligibleRows\.slice\(0, requestedBatchSize\) : \[\];[\s\S]*const metricFidelity = buildHybridMetricFidelitySummary\(preselectedRows\);[\s\S]*const rows = metricFidelityBlocker == null \? preselectedRows : \[\];[\s\S]*actual_batch_size: rows\.length[\s\S]*max_pilot_batch_size: requestedBatchSize/s, "Pilot action must select exactly the requested eligible rows only after blockers and metric-fidelity guards are clear and cap max pilot batch size to the requested size");
assert.match(popupSource, /async function evaluateGuardedPilotProgressionPrerequisites\(batchSize: GuardedHybridStartCollectingPilotBatchSize, beta5PostVerifyPassed = false\)[\s\S]*if \(batchSize === 10\)[\s\S]*const pathSatisfied = beta5PostVerifyPassed \|\| legacyPilot5PostVerifyPassed[\s\S]*prerequisite_path_selected: beta5PostVerifyPassed \? "beta_5_post_verify" : legacyPilot5PostVerifyPassed \? "legacy_pilot_5_post_verify" : "none"[\s\S]*previous_pilot_requirement_satisfied: pathSatisfied[\s\S]*latest_guarded_hybrid_collect_beta_5_post_verify_pass_missing/s, "Pilot 10 progression must accept beta 5 post-verify and keep legacy Pilot 5 only as a backward-compatible alternative");
assert.doesNotMatch(popupSource, /batchSize === 10[\s\S]{0,220}latest_guarded_hybrid_start_collecting_pilot_5_post_verify_pass_missing/s, "Pilot 10 must not be blocked by missing legacy Pilot 5 post-verify");
assert.match(popupSource, /async function evaluateGuardedPilotProgressionPrerequisites[\s\S]*const pilot10PostVerifyPassed = guardedHybridPostVerifySummaryPassedForBatch\(pilotPostVerify, 10\);[\s\S]*const queueCompletionPilot10PostVerifyPassed = guardedHybridQueueCompletionPilot10PostVerifyPassed\(queueCompletionPostVerify\);[\s\S]*prerequisite_path_selected: pathB \? "pilot_10_plus_queue_completion_10_post_verify"[\s\S]*previous_pilot_requirement_satisfied: batchSize === 50 \? pathA \|\| pathB : true/s, "Pilot 50 must use the canonical progression helper that accepts Pilot 10 plus Queue Completion 10 post-verify");
assert.match(popupSource, /const pathB = pilot10PostVerifyPassed && queueCompletionPilot10PostVerifyPassed[\s\S]*previous_pilot_requirement_satisfied: batchSize === 50 \? pathA \|\| pathB : true[\s\S]*missing_pilot_10_plus_queue_completion_10_or_legacy_pilot_5_post_verify/s, "Pilot 50 must remain blocked until Pilot 10 post-verify and Queue Completion 10 post-verify pass, unless legacy Pilot 5 is intentionally available");
assert.doesNotMatch(popupSource, /batchSize === 50[\s\S]{0,160}latest_guarded_hybrid_start_collecting_pilot_5_post_verify_pass_missing/s, "Pilot 50 must not be blocked by the stale Pilot 5-only blocker");
assert.match(popupSource, /batchSize === 50 && !previousPilotRequirementSatisfied[\s\S]*previous_pilot_requirement_not_satisfied_for_pilot_50[\s\S]*previous_pilot_requirement_satisfied: previousPilotRequirementSatisfied/s, "Pilot 50 must gate on previous_pilot_requirement_satisfied, not previous_pilot_5_post_verify_passed");
assert.match(popupSource, /HYBRID_START_COLLECTING_PILOT_LATEST_BLOCKED_ATTEMPT_STORAGE_KEY[\s\S]*latest_success_artifact_preserved[\s\S]*blocked_or_failed_attempt_not_written_to_latest_production[\s\S]*not_safe_for_latest_successful_production_artifact/s, "Blocked Pilot 50 attempts must not overwrite the latest successful production artifact");
assert.match(popupSource, /async function readGuardedHybridStartCollectingPilot50PostVerifySource[\s\S]*sourceIsPilot50[\s\S]*latest_available_source_is_pilot_10_not_pilot_50[\s\S]*verifiedAwemeIds: blockers\.length === 0 \? uniqueVerifiedAwemeIds : \[\]/s, "Pilot 50 queue-completion must reject Pilot 10 sources and return no verified IDs when rejected");
assert.match(popupSource, /async function buildGuardedHybridStartCollectingQueueCompletionPilot50Summary\(applyCompletion: boolean\)[\s\S]*const verifiedIdSet = new Set\(verifiedAwemeIds\);[\s\S]*queueBefore\.filter\(\(item\) => verifiedIdSet\.has\(item\.aweme_id\)\)[\s\S]*!verifiedIdSet\.has\(item\.aweme_id\)[\s\S]*match_strategy: "exact_aweme_id_only_from_latest_passed_pilot_50_post_verify_artifact_no_count_or_index_completion"/s, "Pilot 50 queue-completion must match and complete only exact aweme ID intersections from the latest Pilot 50 post-verify artifact");
assert.match(popupSource, /summary_title: "GUARDED_HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_SUMMARY"[\s\S]*backend_write_attempted: "no"[\s\S]*normal_start_collecting_run: "no"[\s\S]*collect_job_mutated: collectJobMutated[\s\S]*full_queue_completion_enabled: false[\s\S]*estimated_views_copied_to_view_count: "no"/s, "Pilot 50 queue-completion must remain local queue-state-only without backend writes, normal Start Collecting, collect_job mutation, full queue completion, or estimated_views/view_count copying");
assert.match(popupSource, /GUARDED_HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_POST_VERIFY_SUMMARY[\s\S]*verified_items_complete_count[\s\S]*unexpected_completed_aweme_ids[\s\S]*non_verified_queue_items_completed_count[\s\S]*backend_read_only_verification: "yes"[\s\S]*prepare_controlled_full_queue_completion_enablement/s, "Pilot 50 queue-completion post-verify must verify exact 50 completion, non-verified protection, read-only safety, and the controlled full-queue enablement recommendation");
assert.match(popupHtml, /id="exportCompactGuardedPipelineStatusButton"[\s\S]*Export Compact Guarded Pipeline Status[\s\S]*id="copyCompactGuardedPipelineStatusButton"[\s\S]*Copy Compact Guarded Pipeline Status[\s\S]*id="exportGuardedPipelineStorageInventoryButton"[\s\S]*Export Guarded Pipeline Storage Inventory[\s\S]*id="copyGuardedPipelineStorageInventoryButton"[\s\S]*Copy Guarded Pipeline Storage Inventory[\s\S]*id="exportBackendShadowRowEvidenceButton"[\s\S]*Export Backend Shadow Row Evidence[\s\S]*id="copyBackendShadowRowEvidenceButton"[\s\S]*Copy Backend Shadow Row Evidence[\s\S]*id="exportBetaProductionRowEvidenceButton"[\s\S]*Export Beta Production Row Evidence[\s\S]*id="copyBetaProductionRowEvidenceButton"[\s\S]*Copy Beta Production Row Evidence[\s\S]*id="runGuardedPipelineToPilot50Button"[\s\S]*Run Guarded Pipeline To Pilot 50[\s\S]*id="compactGuardedPipelineStatusPreview"[\s\S]*COMPACT_GUARDED_PIPELINE_STATUS not exported yet\.[\s\S]*id="guardedPipelineStorageInventoryPreview"[\s\S]*GUARDED_PIPELINE_STORAGE_INVENTORY not exported yet\.[\s\S]*id="backendShadowRowEvidencePreview"[\s\S]*BACKEND_SHADOW_ROW_EVIDENCE not exported yet\.[\s\S]*id="betaProductionRowEvidencePreview"[\s\S]*BETA_PRODUCTION_ROW_EVIDENCE not exported yet\./, "popup must expose compact guarded pipeline export/copy/run controls plus read-only storage inventory, backend shadow row evidence, and beta production row evidence controls and preview blocks");
assert.match(popupSource, /GUARDED_PIPELINE_TO_PILOT_50_LATEST_COMPACT_STORAGE_KEY = "guardedPipelineToPilot50LatestCompact"[\s\S]*function buildCompactGuardedPipelineStatus[\s\S]*summary_title: "COMPACT_GUARDED_PIPELINE_STATUS"[\s\S]*artifacts: steps[\s\S]*next_action: next\?\.name === "guarded_hybrid_collect_beta_5_post_verify" && compactStringArray\(next\.blockers\)\.includes\("expected_share_count_values_missing"\)[\s\S]*"rerun_guarded_hybrid_collect_beta_5_after_artifact_schema_fix"[\s\S]*next \? `run_\$\{String\(next\.name\)\}` : "pipeline_to_pilot_50_complete"[\s\S]*blockers: next\?\.name === "queue_completion_pilot_10" && pilot10Passed \? \[\] : next\?\.name === "guarded_start_collecting_pilot_10" && pilot10RunReady \? \[\] : next \? compactStringArray\(next\.blockers, 12\) : \[\]/s, "compact guarded pipeline status must emit one compact JSON object, route old beta schema-fix reruns, and keep create-action top-level blockers empty for ready Pilot 10 and Queue Completion Pilot 10 actions");
assert.match(popupSource, /function buildCompactGuardedPipelineStatus[\s\S]*const beta5PostVerifyPassed = betaDecision\.post_verify_verdict === "beta_post_verify_passed" && betaRun\.beta_batch_size === 5;[\s\S]*const pilot10RunReady = beta5PostVerifyPassed && pilot10ProgressionDisplay\.previous_pilot_requirement_satisfied === true && pilot10Source == null;[\s\S]*next_action: next\?\.name === "guarded_hybrid_collect_beta_5_post_verify"[\s\S]*next \? `run_\$\{String\(next\.name\)\}` : "pipeline_to_pilot_50_complete",[\s\S]*blockers: next\?\.name === "queue_completion_pilot_10" && pilot10Passed \? \[\] : next\?\.name === "guarded_start_collecting_pilot_10" && pilot10RunReady \? \[\]/s, "beta post-verify passed plus missing Pilot 10 source should display run_guarded_start_collecting_pilot_10 with empty top-level blockers because the missing artifact is created by that action");
assert.match(popupSource, /function guardedHybridQueueCompletionPilot10PostVerifyPassed\(summary: Record<string, unknown> \| null\): boolean \{[\s\S]*decision\.post_verify_verdict === "queue_completion_pilot_post_verify_passed"[\s\S]*decision\.safe_for_next_phase === true[\s\S]*Number\(queueVerification\.complete_now_count \?\? 0\) === 10[\s\S]*queueVerification\.match_strategy === "exact_aweme_id_only"[\s\S]*safety\.backend_write_attempted === "no"[\s\S]*safety\.collect_job_mutated === "no"[\s\S]*Number\(safety\.non_verified_queue_items_completed_count \?\? 0\) === 0/s, "queue completion Pilot 10 post-verify must have one canonical strict pass detector covering verdict, exact-ID count, and safety invariants");
assert.match(popupSource, /async function evaluateGuardedPilotProgressionPrerequisites[\s\S]*const queueCompletionPostVerify = await readGuardedHybridQueueCompletionPilot10PostVerifySummary\(\);[\s\S]*const queueCompletionPilot10PostVerifyPassed = guardedHybridQueueCompletionPilot10PostVerifyPassed\(queueCompletionPostVerify\);[\s\S]*const pathB = pilot10PostVerifyPassed && queueCompletionPilot10PostVerifyPassed[\s\S]*latest_queue_completion_pilot_10_post_verify_pass_missing[\s\S]*previous_pilot_requirement_not_satisfied/s, "Pilot 50 prerequisite must use the canonical queue completion Pilot 10 post-verify detector instead of reading the raw queue-completion action artifact shape");
assert.match(popupSource, /async function readGuardedHybridQueueCompletionPilot10PostVerifySummary\(\): Promise<Record<string, unknown> \| null> \{\s*return buildGuardedHybridStartCollectingQueueCompletionPilotPostVerifySummary\(\);\s*\}/s, "queue completion Pilot 10 post-verify reader must rebuild the canonical post-verify summary and avoid stale/raw action artifact verdict normalization");
assert.match(popupSource, /function buildCompactGuardedPipelineStatus[\s\S]*const beta5PostVerifyPassed = betaDecision\.post_verify_verdict === "beta_post_verify_passed" && betaRun\.beta_batch_size === 5;[\s\S]*const pilot10Progression = await evaluateGuardedPilotProgressionPrerequisites\(10, beta5PostVerifyPassed\);[\s\S]*const pilot10MilestoneAuthorityPassed = pilot10SourceMilestoneBlockers\.length === 0 && pilot10PostMilestoneBlockers\.length === 0;[\s\S]*const queue10PostVerifyMilestoneAuthorityPassed = queue10MilestoneAuthorityBlockers\.length === 0;[\s\S]*prerequisite_path_selected: queue10PostVerifyMilestoneAuthorityPassed \? "pilot_10_plus_queue_completion_10_post_verify" : "pilot_10_post_verify_milestone"[\s\S]*previous_pilot_requirement_reason: queue10PostVerifyMilestoneAuthorityPassed \? "queue_completion_pilot_10_post_verify_milestone_authority" : "pilot_10_post_verify_milestone_authority"[\s\S]*previous_pilot_requirement_satisfied: pilot10ProgressionDisplay\.previous_pilot_requirement_satisfied[\s\S]*prerequisite_path_selected: pilot10ProgressionDisplay\.prerequisite_path_selected[\s\S]*previous_pilot_requirement_reason: pilot10ProgressionDisplay\.previous_pilot_requirement_reason/s, "compact guarded pipeline status must promote valid Pilot 10 and Queue Completion 10 post-verify artifacts to milestone authority when beta 5 post-verify is absent or later regresses");
assert.match(popupSource, /function compactGuardedQueueCompletionPilot10AuthorityBlockers[\s\S]*guardedHybridQueueCompletionPilot10PostVerifyPassed\(queue10PostVerify\)[\s\S]*queueBatch === 0 \|\| queueBatch === 10[\s\S]*postVerifyQueueVerification\.match_strategy === "exact_aweme_id_only"[\s\S]*"source_pilot_run_mismatch"[\s\S]*"source_run_mismatch"[\s\S]*verifiedIds\.length === 10 && pilotIds\.length === 10 && verifiedIds\.every\(\(awemeId\) => pilotIds\.includes\(awemeId\)\)/s, "Queue Completion 10 post-verify milestone authority must validate strict pass, batch 10, exact-ID evidence, source and source-pilot linkage, and exact verified IDs");
assert.match(popupSource, /function compactGuardedPilot10SourceFromQueueCompletionMilestone[\s\S]*guardedHybridQueueCompletionPilot10PostVerifyPassed\(queue10PostVerify\)[\s\S]*const sourceArtifact = \(queue10\.source_artifact as Record<string, unknown> \| undefined\) \?\? \{\};[\s\S]*sourceIds\.length !== 10[\s\S]*backend_write_summary: \{ verdict: "pilot_collect_succeeded"[\s\S]*authority_source: "queue_completion_pilot_10_post_verify_batch_specific_milestone"/s, "Pilot 10 source authority must be recoverable from the durable Queue Completion 10 milestone when shared latest Pilot aliases now point to Pilot 50");
assert.match(popupSource, /function compactGuardedPilot10PostVerifyFromQueueCompletionMilestone[\s\S]*queuePilotRunId !== sourcePilotRunId[\s\S]*post_verify_verdict: "pilot_post_verify_passed"[\s\S]*authority_source: "queue_completion_pilot_10_post_verify_batch_specific_milestone"/s, "Pilot 10 post-verify authority must be recoverable from Queue Completion 10 post-verify without reading overwritten shared latest Pilot aliases");
assert.match(popupSource, /function buildCompactGuardedPipelineStatus[\s\S]*const queue10PostVerify = await readGuardedHybridQueueCompletionPilot10PostVerifySummary\(\);[\s\S]*const pilot10SourceCandidate = pilot10BatchSource \?\? compactGuardedPilotSourceForBatch\(pilotSource, 10\) \?\? compactGuardedPilot10SourceFromQueueCompletionMilestone\(queue10, queue10PostVerify, currentSourceRunId\);[\s\S]*const pilot10PostCandidate = pilot10BatchPostVerify \?\? compactGuardedPilotPostVerifyForBatch\(pilotPostVerify, 10\) \?\? compactGuardedPilot10PostVerifyFromQueueCompletionMilestone\(queue10, queue10PostVerify, pilot10SourceCandidate\);[\s\S]*const queue10PostVerifyMilestoneAuthorityPassed = queue10MilestoneAuthorityBlockers\.length === 0;[\s\S]*const pilot50SourceChain = compactGuardedCurrentSource\(pilot50SourceCandidate, 50/s, "Compact status must preserve batch-specific Pilot 10 and Queue Completion 10 milestone authority via durable batch-scoped keys after Pilot 50 overwrites shared latest Pilot aliases while still using Pilot 50 batch-scoped artifacts for Pilot 50 rows");
assert.match(popupSource, /function buildCompactGuardedPipelineStatus[\s\S]*const currentQueue10 = queue10Chain\.artifact \?\? \(queue10PostVerifyMilestoneAuthorityPassed \? queue10 : null\);[\s\S]*const currentQueue10PostVerify = queue10PostVerifyChain\.artifact;[\s\S]*const queue10PostVerifyPassed = queue10PostVerifyMilestoneAuthorityPassed \|\| guardedHybridQueueCompletionPilot10PostVerifyPassed\(currentQueue10PostVerify\);[\s\S]*const pilot50ProgressionDisplay: GuardedHybridPilot50ProgressionPrerequisite = pilot50PrerequisitesPassed \? \{ \.\.\.progression,[\s\S]*previous_pilot_requirement_satisfied: true,[\s\S]*blockers: \[\] \} : progression;[\s\S]*const milestoneFastForwardStart = pilot50MilestoneAuthorityPassed \|\| pilot50Passed \? steps\.findIndex\(\(step\) => step\.name === "queue_completion_pilot_50"\) : queue10PostVerifyPassed \? steps\.findIndex\(\(step\) => step\.name === "guarded_start_collecting_pilot_50"\)[\s\S]*const nextSearchStart = foundationalGatesPassed \? milestoneFastForwardStart : 0;[\s\S]*next \? `run_\$\{String\(next\.name\)\}` : "pipeline_to_pilot_50_complete"/s, "Queue Completion 10 post-verify milestone authority must satisfy Pilot 50 prerequisites, and next_action must advance with the highest passed milestone (Pilot 50 superseding an unrecoverable earlier batch) only once all foundational gates pass; a failing foundational gate forces nextSearchStart back to 0");
assert.match(popupSource, /const pilot50ProgressionDisplay: GuardedHybridPilot50ProgressionPrerequisite = pilot50PrerequisitesPassed \? \{ \.\.\.progression,[\s\S]*prerequisite_path_selected: queue10PostVerifyMilestoneAuthorityPassed \? "pilot_10_plus_queue_completion_10_post_verify"[\s\S]*pilot_10_post_verify_available: progression\.pilot_10_post_verify_available \|\| pilot10PostVerify != null,[\s\S]*queue_completion_pilot_10_post_verify_passed: true,[\s\S]*previous_pilot_requirement_reason: queue10PostVerifyMilestoneAuthorityPassed \? "queue_completion_pilot_10_post_verify_milestone_authority"[\s\S]*blockers: \[\] \} : progression;/s, "Pilot 50 prerequisite authority must accept batch-specific Queue Completion 10 post-verify milestone authority without requiring the shared latest Pilot 10 post-verify alias");
assert.match(popupSource, /const pilot50SourceChain = compactGuardedCurrentSource\(pilot50SourceCandidate, 50, currentSourceRunId, pilot50ProgressionDisplay\.previous_pilot_requirement_satisfied === true \|\| pilot50MilestoneAuthorityPassed\);[\s\S]*compactStep\("guarded_start_collecting_pilot_50", pilot50Source != null, pilot50Source != null, pilot50Source == null \? \[\] : pilot50ProgressionDisplay\.blockers,[\s\S]*previous_pilot_requirement_satisfied: pilot50ProgressionDisplay\.previous_pilot_requirement_satisfied,[\s\S]*previous_pilot_requirement_reason: pilot50ProgressionDisplay\.previous_pilot_requirement_reason/s, "Pilot 50 production artifact must not be blocked by stale prerequisite blockers once Queue Completion 10 post-verify milestone authority is valid, and Pilot 50 milestone authority is independently sufficient to surface its own batch-scoped source");
assert.match(popupSource, /function buildCompactGuardedPipelineStatus[\s\S]*const queue10PreviousAttemptBlockers = compactDecisionBlockers\(queue10\);[\s\S]*const queue10RetryReady = pilot10Passed && !queue10PostVerifyMilestoneAuthorityPassed && currentQueue10 != null && queue10PreviousAttemptBlockers\.length > 0;[\s\S]*const queue10CurrentReadinessBlockers = queue10RetryReady \? \[\] : compactDecisionBlockers\(currentQueue10\);[\s\S]*const queue10PreviousAttemptDiagnostics = queue10 == null \? null : \{[\s\S]*blockers: queue10PreviousAttemptBlockers[\s\S]*compactStep\("queue_completion_pilot_10", currentQueue10 != null && !queue10RetryReady, currentQueue10 != null, queue10CurrentReadinessBlockers, \{ status: queue10RetryReady \? "retry_ready" : undefined, current_readiness_status: queue10RetryReady \? "retry_ready"[\s\S]*current_readiness_blockers: queue10CurrentReadinessBlockers[\s\S]*previous_attempt: queue10PreviousAttemptDiagnostics/s, "retryable Queue Completion Pilot 10 compact row must keep current blockers empty under valid Pilot 10 authority while preserving stale blocked attempt blockers as previous_attempt diagnostics");
assert.match(popupSource, /function compactGuardedPilotSourceForBatch[\s\S]*guardedHybridPilotSourceBatchSize\(source\) === batchSize \? source : null[\s\S]*function compactGuardedPilotPostVerifyForBatch[\s\S]*Number\(run\.pilot_batch_size \?\? run\.actual_batch_size \?\? run\.requested_batch_size \?\? 0\)[\s\S]*actualBatch === batchSize \? summary : null/s, "compact guarded pipeline pilot source and post-verify slots must filter shared latest artifacts by the requested batch size");
assert.match(popupSource, /function buildCompactGuardedPipelineStatus[\s\S]*const pilot10SourceCandidate = pilot10BatchSource \?\? compactGuardedPilotSourceForBatch\(pilotSource, 10\) \?\? compactGuardedPilot10SourceFromQueueCompletionMilestone\(queue10, queue10PostVerify, currentSourceRunId\);[\s\S]*const pilot10PostCandidate = pilot10BatchPostVerify \?\? compactGuardedPilotPostVerifyForBatch\(pilotPostVerify, 10\) \?\? compactGuardedPilot10PostVerifyFromQueueCompletionMilestone\(queue10, queue10PostVerify, pilot10SourceCandidate\);[\s\S]*const pilot10SourceChain = compactGuardedCurrentSource\(pilot10SourceCandidate, 10[\s\S]*const pilot10PostChain = compactGuardedCurrentPostVerify\(pilot10PostCandidate, 10[\s\S]*const pilot50SourceCandidate = pilot50BatchSource \?\? compactGuardedPilotSourceForBatch\(pilotSource, 50\);[\s\S]*const pilot50PostCandidate = pilot50BatchPostVerify \?\? compactGuardedPilotPostVerifyForBatch\(pilotPostVerify, 50\);[\s\S]*const pilot50SourceChain = compactGuardedCurrentSource\(pilot50SourceCandidate, 50[\s\S]*const pilot50PostChain = compactGuardedCurrentPostVerify\(pilot50PostCandidate, 50/s, "compact guarded pipeline status must discover Pilot 10 candidates before prerequisite gating and isolate Pilot 10 and Pilot 50 artifacts by durable batch-scoped keys and current chain");
assert.match(popupSource, /compactStep\("guarded_start_collecting_pilot_50", pilot50Source != null, pilot50Source != null, pilot50Source == null \? \[\] : pilot50ProgressionDisplay\.blockers[\s\S]*\.\.\.pilot50SourceDiagnostic[\s\S]*compactStep\("guarded_start_collecting_pilot_50_post_verify", pilot50Passed, pilot50PostVerify != null, compactDecisionBlockers\(pilot50PostVerify\)[\s\S]*\.\.\.pilot50PostDiagnostic/s, "Pilot 50 compact slots must ignore Pilot 10 artifacts as stale diagnostics instead of surfacing batch_size_mismatch blockers");
assert.match(popupSource, /compactStep\("guarded_start_collecting_pilot_10", pilot10Source != null \|\| earlierBatchSupersededByPilot50, pilot10SourceCandidate != null, pilot10Source == null && !earlierBatchSupersededByPilot50 \? pilot10SourceMilestoneBlockers : pilot10ProgressionDisplay\.blockers[\s\S]*batch_scoped_source_storage_key: hybridStartCollectingPilotProductionByBatchStorageKey\(10\)[\s\S]*\.\.\.pilot10SourceDiagnostic[\s\S]*\.\.\.batch10SupersededDiagnostic[\s\S]*compactStep\("guarded_start_collecting_pilot_10_post_verify", pilot10Passed \|\| earlierBatchSupersededByPilot50, pilot10PostCandidate != null, pilot10PostVerify == null && !earlierBatchSupersededByPilot50 \? pilot10PostMilestoneBlockers : compactDecisionBlockers\(pilot10PostVerify\)[\s\S]*batch_scoped_post_verify_storage_key: hybridStartCollectingPilotPostVerifyByBatchStorageKey\(10\)[\s\S]*\.\.\.pilot10PostDiagnostic[\s\S]*\.\.\.batch10SupersededDiagnostic/s, "Pilot 10 compact slots must report raw candidate availability, batch-scoped key resolution, milestone rejection blockers, and explicit superseded diagnostics (option a) instead of hiding found-but-rejected artifacts or silently regressing");
// Round 8: read-only artifact reporting alignment. When Pilot 50 + Pilot 50 post-verify pass but the earlier batch_10 alias
// artifacts are unrecoverable, the Pilot 50 artifact must NOT surface stale prerequisite blockers, the queue_completion_pilot_10
// and queue_completion_pilot_10_post_verify rows must report status="superseded" (not "blocked"), and the top-level
// next_action/blockers must reflect pipeline_to_pilot_50_complete with empty blockers. Safety invariants are unchanged.
assert.match(popupSource, /function compactSupersededStep\(name: string, artifactAvailable: boolean, supersededByMilestone: string, supersededReason: string[\s\S]*status: "superseded"[\s\S]*passed: true[\s\S]*blockers: \[\][\s\S]*superseded_by_higher_milestone: supersededByMilestone[\s\S]*superseded_reason: supersededReason/s, "Round 8: compactSupersededStep helper must emit status=\"superseded\", passed=true, empty blockers, and explicit supersede diagnostics so superseded artifact rows are clearly distinct from blocked/missing/failed without changing safety invariants");
assert.match(popupSource, /const earlierBatchSupersededByPilot50 = pilot50MilestoneAuthorityPassed && !pilot10Passed && !queue10PostVerifyMilestoneAuthorityPassed;[\s\S]*const pilot50ProgressionDisplay: GuardedHybridPilot50ProgressionPrerequisite = pilot50PrerequisitesPassed \?[\s\S]*: pilot50MilestoneAuthorityPassed \? \{ \.\.\.progression, prerequisite_path_selected: "pilot_50_milestone_authority_supersedes_prerequisites"[\s\S]*previous_pilot_requirement_satisfied: true[\s\S]*previous_pilot_requirement_reason: "pilot_50_milestone_authority_supersedes_unrecoverable_prerequisites"[\s\S]*blockers: \[\] \} : progression;/s, "Round 8: when Pilot 50 milestone authority has passed but the earlier batch_10 prerequisites are unrecoverable, pilot50ProgressionDisplay must use the supersede branch with empty blockers and an explicit supersede reason instead of surfacing stale prerequisite blockers at the Pilot 50 artifact row");
assert.match(popupSource, /earlierBatchSupersededByPilot50\s*\? compactSupersededStep\("queue_completion_pilot_10", currentQueue10 != null, "guarded_start_collecting_pilot_50_post_verify", "queue_completion_pilot_10_artifact_unrecoverable_but_higher_pilot_50_milestone_passed"[\s\S]*: compactStep\("queue_completion_pilot_10", currentQueue10 != null && !queue10RetryReady/s, "Round 8: queue_completion_pilot_10 row must use compactSupersededStep when Pilot 50 milestone authority has passed and the batch_10 artifact is unrecoverable, otherwise fall back to the regular compactStep blocked/missing/passed reporting");
assert.match(popupSource, /earlierBatchSupersededByPilot50\s*\? compactSupersededStep\("queue_completion_pilot_10_post_verify", currentQueue10PostVerify != null, "guarded_start_collecting_pilot_50_post_verify", "queue_completion_pilot_10_post_verify_artifact_unrecoverable_but_higher_pilot_50_milestone_passed"[\s\S]*: compactStep\("queue_completion_pilot_10_post_verify", queue10PostVerifyPassed/s, "Round 8: queue_completion_pilot_10_post_verify row must use compactSupersededStep when Pilot 50 milestone authority has passed and the batch_10 post-verify artifact is unrecoverable, otherwise fall back to the regular compactStep blocked/missing/passed reporting");
assert.match(popupSource, /type GuardedHybridPilotProgressionPrerequisite = \{[\s\S]*prerequisite_path_selected: "beta_5_post_verify" \| "legacy_pilot_5_post_verify" \| "pilot_10_post_verify_milestone" \| "pilot_10_plus_queue_completion_10_post_verify" \| "pilot_50_milestone_authority_supersedes_prerequisites" \| "none";[\s\S]*type GuardedHybridPilot50ProgressionPrerequisite = GuardedHybridPilotProgressionPrerequisite & \{\s*prerequisite_path_selected: "legacy_pilot_5_post_verify" \| "pilot_10_plus_queue_completion_10_post_verify" \| "pilot_50_milestone_authority_supersedes_prerequisites" \| "none";\s*\};/s, "Round 8: pilot progression prerequisite union types must include pilot_50_milestone_authority_supersedes_prerequisites so the Pilot 50 supersede branch type-checks");
assert.match(popupSource, /function compactGuardedPilotSourceMilestoneBlockers[\s\S]*actualBatch === expectedBatch \? null : "batch_size_mismatch"[\s\S]*pilotRunId \? null : "source_pilot_run_id_missing"[\s\S]*parentRunId \? null : "parent_source_run_id_missing"[\s\S]*source_run_mismatch[\s\S]*backendPassed \? null : "pilot_backend_write_not_successful"[\s\S]*`pilot_accepted_count_not_\$\{expectedBatch\}`[\s\S]*"pilot_rejected_count_not_0"/s, "Pilot 10 milestone source authority must still reject wrong batch, missing pilot or parent linkage, source mismatch, backend failure, wrong accepted count, and rejections");
assert.match(popupSource, /function compactGuardedPilotPostVerifyMilestoneBlockers[\s\S]*decision\.post_verify_verdict === "pilot_post_verify_passed"[\s\S]*`pilot_post_verify_success_count_not_\$\{expectedBatch\}`[\s\S]*"pilot_post_verify_blockers_present"[\s\S]*"queue_completion_readiness_blockers_present"[\s\S]*expectedPilotRunId && actualPilotRunId && expectedPilotRunId === actualPilotRunId \? null : "dependency_chain_mismatch"/s, "Pilot 10 milestone post-verify authority must still require pass verdict, exact success count, empty blockers, queue readiness without blockers, and source_pilot_run_id linkage");
assert.match(popupSource, /async function resolveGuardedHybridQueueCompletionPilot10Authority[\s\S]*stored_pilot_10_post_verify_available: storedCandidate != null[\s\S]*stored_pilot_10_post_verify_authority_blockers: authorityBlockers[\s\S]*"dependency_chain_mismatch"/s, "missing or source-pilot-mismatched Pilot 10 post-verify authority must still block queue completion readiness");
assert.match(popupSource, /function compactGuardedMilestoneRejectedDiagnostic[\s\S]*stale_artifact_ignored: true[\s\S]*ignored_artifact_reason: blockers\[0\]/s, "compact guarded status must mark found-but-rejected milestone candidates stale with a precise ignored_artifact_reason");
assert.match(popupSource, /const milestoneFastForwardStart = pilot50MilestoneAuthorityPassed \|\| pilot50Passed \? steps\.findIndex\(\(step\) => step\.name === "queue_completion_pilot_50"\) : queue10PostVerifyPassed \? steps\.findIndex\(\(step\) => step\.name === "guarded_start_collecting_pilot_50"\) : pilot10Passed \? steps\.findIndex\(\(step\) => step\.name === "queue_completion_pilot_10"\) : 0;[\s\S]*const nextSearchStart = foundationalGatesPassed \? milestoneFastForwardStart : 0;[\s\S]*const next = steps\.slice\(Math\.max\(nextSearchStart, 0\)\)\.find\(\(step\) => step\.passed !== true\) \?\? null/s, "compact guarded status next_action must derive from the highest passed milestone (Pilot 50 > Queue Completion 10 > Pilot 10) so it never regresses behind a milestone that already passed, but must NOT fast-forward past a still-failing foundational gate");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildCompactGuardedPipelineStatus"), popupSource.indexOf("async function runGuardedPipelineStep")), /next_action:[\s\S]{0,260}run_guarded_start_collecting_pilot_50/s, "Pilot 50 post-verify passed must not force next_action back to run_guarded_start_collecting_pilot_50");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildCompactGuardedPipelineStatus"), popupSource.indexOf("async function runGuardedPipelineStep")), /pilot50SourceBlockers|pilot10SourceBlockers|pilot50PostBlockers|pilot10PostBlockers|compactBatchMismatchBlockers\(pilotSource|compactBatchMismatchBlockers\(pilotPostVerify/s, "compact guarded pipeline status must not convert stale cross-batch Pilot artifacts into top-level slot blockers");
assert.match(popupSource, /function buildCompactGuardedPipelineStatus[\s\S]*sample_id_count: dryRun\?\.rows\?\.length \?\? 0[\s\S]*compact_alias_reader: \{ storage_namespace: "chrome\.storage\.local"[\s\S]*missing_aliases: Object\.entries\(compactAliases\)[\s\S]*reset_behavior: "reset helpers clear explicit reset key arrays only[\s\S]*safety: \{ scan_profile_changed: "no"[\s\S]*normal_start_collecting_replaced: "no"[\s\S]*full_queue_completion_enabled: false[\s\S]*queue_completion_match_strategy: "exact_aweme_id_only"[\s\S]*estimated_views_copied_to_view_count: "no"/s, "compact guarded pipeline export must expose only counts, read compact aliases, explain reset behavior, and report safety invariants without raw item IDs or huge row payloads");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildCompactGuardedPipelineStatus"), popupSource.indexOf("async function runGuardedPipelineStep")), /representative_items|production_request_preview|diagnostic_payload_preview|thumbnail_url|full_backend_response|collect_job_fingerprint|accepted_aweme_ids:|source_verified_aweme_ids:|first_3_aweme_ids|aweme_id:/s, "compact guarded pipeline status must not include raw aweme IDs, huge previews, representative rows, thumbnail URLs, raw backend bodies, collect_job fingerprints, or full aweme ID arrays");
assert.match(popupSource, /async function runGuardedPipelineToPilot50FromPopup[\s\S]*const next = steps\.find\(\(step\) => step\.passed !== true\) \?\? null;[\s\S]*await runGuardedPipelineStep\(String\(next\.name\)\)[\s\S]*if \(!passed\) break;[\s\S]*summary_title: "GUARDED_PIPELINE_TO_PILOT_50_COMPACT_SUMMARY"/s, "guarded pipeline runner must resume from the first missing or failed step and stop immediately on blockers/failures");
assert.match(popupSource, /async function runGuardedPipelineStep[\s\S]*"hybrid_only_dry_run_50"[\s\S]*"backend_shadow_5"[\s\S]*"guarded_hybrid_collect_beta_5"[\s\S]*"guarded_start_collecting_pilot_10"[\s\S]*await runGuardedHybridStartCollectingPilotFromPopup\(10\)[\s\S]*"queue_completion_pilot_50_post_verify"[\s\S]*return buildCompactGuardedPipelineStatus\(\)/s, "guarded pipeline runner must proceed from beta post-verify to Pilot 10 and cover the ordered guarded path through Pilot 50 post-verify");
assert.match(popupSource, /runGuardedPipelineToPilot50Button\?\.addEventListener\("click", \(\) => void runGuardedPipelineToPilot50FromPopup\(\)\);[\s\S]*exportCompactGuardedPipelineStatusButton\?\.addEventListener\("click", \(\) => void exportCompactGuardedPipelineStatusFromPopup\(\)\);[\s\S]*copyCompactGuardedPipelineStatusButton\?\.addEventListener\("click", \(\) => void copyCompactGuardedPipelineStatusFromPopup\(\)\);[\s\S]*exportGuardedPipelineStorageInventoryButton\?\.addEventListener\("click", \(\) => void exportGuardedPipelineStorageInventoryFromPopup\(\)\);[\s\S]*copyGuardedPipelineStorageInventoryButton\?\.addEventListener\("click", \(\) => void copyGuardedPipelineStorageInventoryFromPopup\(\)\);[\s\S]*exportBackendShadowRowEvidenceButton\?\.addEventListener\("click", \(\) => void exportBackendShadowRowEvidenceFromPopup\(\)\);[\s\S]*copyBackendShadowRowEvidenceButton\?\.addEventListener\("click", \(\) => void copyBackendShadowRowEvidenceFromPopup\(\)\);[\s\S]*exportBetaProductionRowEvidenceButton\?\.addEventListener\("click", \(\) => void exportBetaProductionRowEvidenceFromPopup\(\)\);[\s\S]*copyBetaProductionRowEvidenceButton\?\.addEventListener\("click", \(\) => void copyBetaProductionRowEvidenceFromPopup\(\)\);/, "popup must wire compact guarded pipeline run/export/copy plus read-only inventory, backend shadow row evidence, and beta production row evidence export/copy operator actions");
assert.match(popupHtml, /id="exportPerBatchMilestoneAuthorityDiagnosticButton"[\s\S]*Export Per-Batch Milestone Authority Diagnostic[\s\S]*id="copyPerBatchMilestoneAuthorityDiagnosticButton"[\s\S]*Copy Per-Batch Milestone Authority Diagnostic[\s\S]*id="perBatchMilestoneAuthorityDiagnosticPreview"[\s\S]*PER_BATCH_MILESTONE_AUTHORITY_DIAGNOSTIC not exported yet\./, "popup must expose per-batch milestone authority diagnostic export/copy controls and a preview block");
assert.match(popupSource, /exportPerBatchMilestoneAuthorityDiagnosticButton\?\.addEventListener\("click", \(\) => void exportPerBatchMilestoneAuthorityDiagnosticFromPopup\(\)\);[\s\S]*copyPerBatchMilestoneAuthorityDiagnosticButton\?\.addEventListener\("click", \(\) => void copyPerBatchMilestoneAuthorityDiagnosticFromPopup\(\)\);/, "popup must wire per-batch milestone authority diagnostic export/copy operator actions");
assert.match(popupSource, /async function buildPerBatchMilestoneAuthorityDiagnostic\(\): Promise<Record<string, unknown>> \{[\s\S]*const pilot10BatchSource = await readGuardedHybridStartCollectingPilotProductionSourceForBatch\(10, pilotSource\);[\s\S]*const pilot10DirectSource = pilot10BatchSource \?\? compactGuardedPilotSourceForBatch\(pilotSource, 10\);[\s\S]*const pilot10QueueDerivedSource = compactGuardedPilot10SourceFromQueueCompletionMilestone\(queue10, queue10PostVerify, currentSourceRunId\);[\s\S]*const pilot50DirectSource = pilot50BatchSource \?\? compactGuardedPilotSourceForBatch\(pilotSource, 50\);[\s\S]*summary_title: "PER_BATCH_MILESTONE_AUTHORITY_DIAGNOSTIC"[\s\S]*read_only: true[\s\S]*storage_mutation: "none"[\s\S]*pipeline_stages_rerun: "none"[\s\S]*milestone_authority_model: "additive_highest_passed_wins_per_batch_no_later_batch_overwrites_earlier"[\s\S]*later_batch_overwrites_earlier_milestone: "no"[\s\S]*highest_passed_milestone: highestPassedMilestone[\s\S]*diagnostic_and_compact_status_consistent:/s, "per-batch milestone authority diagnostic must be read-only, prefer batch-scoped per-batch keys for Pilot 10 and Pilot 50 source resolution, declare the additive no-overwrite milestone model and highest passed milestone, and assert consistency with the compact status");
// Item A consistency fix: the diagnostic mirrors the compact status' foundational-gate authority so highest_passed_milestone agrees in both outputs.
assert.match(popupSource, /const foundationalGate = \(compactStatus\.foundational_gate as Record<string, unknown> \| undefined\) \?\? \{\};[\s\S]*const foundationalGatesPassed = foundationalGate\.all_foundational_gates_passed === true;[\s\S]*const rawHighestPassedMilestone = pilot50MilestoneAuthorityPassed \? "guarded_start_collecting_pilot_50_post_verify" : queue10PostVerifyMilestoneAuthorityPassed \? "queue_completion_pilot_10_post_verify" : pilot10MilestoneAuthorityPassed \? "guarded_start_collecting_pilot_10_post_verify" : "none";[\s\S]*const highestPassedMilestone = foundationalGatesPassed \? rawHighestPassedMilestone : "none";/s, "per-batch diagnostic must suppress highest_passed_milestone to none while a foundational gate is blocked, mirroring the compact status, so diagnostic_and_compact_status_consistent is true");
assert.match(popupSource, /function perBatchMilestoneAuthorityResolution[\s\S]*batch_scoped_production_key: hybridStartCollectingPilotProductionByBatchStorageKey\(args\.batchSize\)[\s\S]*later_batch_can_overwrite_this_batch: false[\s\S]*resolved_from: args\.batchScopedSourceAvailable \? "batch_scoped_production_key" : args\.directSource != null \? "shared_latest_production_alias_batch_match" : args\.queueDerivedSource != null \? "queue_completion_pilot_10_post_verify_batch_specific_milestone" : "unresolved"[\s\S]*shared_alias_ignored_reason: !args\.batchScopedSourceAvailable && args\.directSource == null && sharedProductionMismatch \? "shared_latest_production_alias_points_at_different_batch" : null[\s\S]*milestone_authority_strategy: "additive_highest_passed_wins_batch_scoped"/s, "per-batch milestone resolution must prefer the durable batch-scoped key, record how each batch resolved its source, why a shared alias pointing at a different batch was ignored, assert later batches cannot overwrite this batch, and declare the additive batch-scoped strategy");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildPerBatchMilestoneAuthorityDiagnostic"), popupSource.indexOf("async function exportPerBatchMilestoneAuthorityDiagnosticFromPopup")), /chrome\.storage\.local\.set|runGuardedPipelineStep|runGuardedHybridStartCollectingPilotFromPopup|accepted_aweme_ids:|source_verified_aweme_ids:|thumbnail_url|aweme_id:/s, "per-batch milestone authority diagnostic must not mutate storage, rerun stages, or emit raw aweme IDs/thumbnails");
assert.match(popupSource, /async function buildGuardedPipelineStorageInventory\(\): Promise<Record<string, unknown>> \{[\s\S]*const namespaces: GuardedPipelineStorageNamespaceName\[\] = \["local", "session", "sync"\];[\s\S]*summary_title: "GUARDED_PIPELINE_STORAGE_INVENTORY"[\s\S]*read_only: true[\s\S]*storage_mutation: "none"[\s\S]*pipeline_stages_rerun: "none"[\s\S]*artifact_absence_conclusion_policy: "inventory_only_do_not_infer_from_compact_status"/s, "guarded pipeline inventory must be read-only, cover local/session/sync, and forbid absence conclusions from compact status alone");
assert.match(popupSource, /async function buildBackendShadowRowEvidence\(\): Promise<Record<string, unknown>> \{[\s\S]*chrome\.storage\.local\.get\(HYBRID_COLLECT_BETA_LATEST_SHADOW_STORAGE_KEY\)[\s\S]*summary_title: "BACKEND_SHADOW_ROW_EVIDENCE"[\s\S]*read_only: true[\s\S]*source_storage_key: HYBRID_COLLECT_BETA_LATEST_SHADOW_STORAGE_KEY[\s\S]*storage_mutation: "none"[\s\S]*backend_mutation: "none"[\s\S]*production_beta_run: "no"[\s\S]*accepted_count[\s\S]*rejected_count[\s\S]*title_payload_real_text_count[\s\S]*title_payload_id_fallback_count[\s\S]*raw_like_payload_exact_numeric_count[\s\S]*rounded_like_payload_rejected_count[\s\S]*production_backend_write_attempted_any[\s\S]*rows_sample: rowEvidence\.slice\(0, 5\)/s, "backend shadow row evidence export must read only the latest backend shadow artifact, expose aggregate safety, sample only first five rows, and forbid storage/backend/pipeline mutation");
assert.match(popupSource, /function backendShadowRowEvidence[\s\S]*payload_title_present[\s\S]*payload_title_length[\s\S]*payload_title_source[\s\S]*outgoing_payload_title_is_real_text[\s\S]*payload_title_equals_aweme_id[\s\S]*dry_run_title_was_real_text[\s\S]*title_dropped_between_dry_run_and_payload[\s\S]*title_is_id_fallback[\s\S]*outgoing_payload_raw_like_count_exact_numeric[\s\S]*raw_like_count[\s\S]*raw_like_count_source[\s\S]*backend_shadow_accepted[\s\S]*production_backend_write_attempted/s, "backend shadow row evidence sample must expose sanitized outgoing payload title diagnostics, raw Likes evidence, and backend shadow acceptance without raw IDs");
const guardedInventoryCandidatesSource = popupSource.slice(popupSource.indexOf("function guardedPipelineStorageInventoryCandidates"), popupSource.indexOf("function guardedPipelineStorageArea"));
for (const keyName of [
  "HYBRID_COLLECT_BETA_LATEST_DRY_RUN_STORAGE_KEY",
  "HYBRID_COLLECT_BETA_LATEST_SHADOW_STORAGE_KEY",
  "HYBRID_COLLECT_BETA_LATEST_PRODUCTION_STORAGE_KEY",
  "HYBRID_START_COLLECTING_PILOT_LATEST_PRODUCTION_STORAGE_KEY",
  "HYBRID_START_COLLECTING_PILOT_LATEST_POST_VERIFY_STORAGE_KEY",
  "HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_LATEST_STORAGE_KEY",
  "HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_STORAGE_KEY",
  "HYBRID_COLLECT_BETA_LATEST_DRY_RUN_COMPACT_STORAGE_KEY",
  "HYBRID_COLLECT_BETA_LATEST_SHADOW_COMPACT_STORAGE_KEY",
  "HYBRID_COLLECT_BETA_LATEST_PRODUCTION_COMPACT_STORAGE_KEY",
  "HYBRID_START_COLLECTING_PILOT_LATEST_PRODUCTION_COMPACT_STORAGE_KEY",
  "HYBRID_START_COLLECTING_PILOT_LATEST_POST_VERIFY_COMPACT_STORAGE_KEY",
  "HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_LATEST_COMPACT_STORAGE_KEY",
  "HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_COMPACT_STORAGE_KEY",
  "GUARDED_PIPELINE_TO_PILOT_50_LATEST_COMPACT_STORAGE_KEY"
]) {
  assert.match(guardedInventoryCandidatesSource, new RegExp(keyName), `guarded pipeline inventory must check ${keyName}`);
}
assert.match(popupSource, /type GuardedPipelineCompactLatestArtifact[\s\S]*backend_write_status: string \| null[\s\S]*backend_write_attempted: "no" \| "yes" \| null[\s\S]*required_field_validity_summary: string \| null[\s\S]*exact_id_only_strategy_evidence: string \| null[\s\S]*completion_count: number \| null[\s\S]*storage_sanitization: "compact_metadata_only_no_payloads_no_full_ids_no_thumbnails_no_backend_bodies"[\s\S]*async function persistGuardedPipelineCompactLatestAlias[\s\S]*chrome\.storage\.local\.set[\s\S]*chrome\.storage\.local\.get\(key\)[\s\S]*guarded compact latest alias write verification failed/s, "guarded compact latest aliases must be compact, local durable, write-verified, and include required compact status evidence");
assert.match(popupSource, /function guardedPipelineCompactLatestFromDryRun[\s\S]*required_field_validity_summary: source\.required_fields_valid \? "required_fields_valid" : "required_fields_invalid_or_missing"[\s\S]*function guardedPipelineCompactLatestFromProductionSource[\s\S]*source_pilot_run_id: stage === "guarded_hybrid_collect_beta_5" \? null : pilotRunId[\s\S]*pilot_run_id: stage === "guarded_hybrid_collect_beta_5" \? null : pilotRunId[\s\S]*source_beta_run_id: stage === "guarded_hybrid_collect_beta_5"[\s\S]*: null[\s\S]*backend_write_status: compactGuardedString\(backendWrite\.beta_write_effective_status\)[\s\S]*function guardedPipelineCompactLatestFromSummary[\s\S]*backend_write_attempted: productionState\.backend_write_attempted === "yes" \? "yes" : productionState\.backend_write_attempted === "no" \? "no" : null[\s\S]*exact_id_only_strategy_evidence: compactGuardedString\(queueMatching\.match_strategy\)[\s\S]*completion_count: compactGuardedNumber\(completionResult\.queue_items_marked_complete_count\)/s, "compact latest builders must include dry-run field validity, semantic pilot/source-beta fields, backend write status, exact-ID strategy evidence, backend_write_attempted, and completion counts without payload bodies");
assert.match(popupSource, /async function readGuardedPipelineCompactLatestAliases\(\): Promise<Record<string, GuardedPipelineCompactLatestArtifact \| null>>[\s\S]*HYBRID_COLLECT_BETA_LATEST_DRY_RUN_COMPACT_STORAGE_KEY[\s\S]*HYBRID_COLLECT_BETA_LATEST_SHADOW_COMPACT_STORAGE_KEY[\s\S]*HYBRID_COLLECT_BETA_LATEST_PRODUCTION_COMPACT_STORAGE_KEY[\s\S]*HYBRID_START_COLLECTING_PILOT_LATEST_PRODUCTION_COMPACT_STORAGE_KEY[\s\S]*HYBRID_START_COLLECTING_PILOT_LATEST_POST_VERIFY_COMPACT_STORAGE_KEY[\s\S]*HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_LATEST_COMPACT_STORAGE_KEY[\s\S]*HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_COMPACT_STORAGE_KEY[\s\S]*Promise\.all\(keys\.map\(\(key\) => chrome\.storage\.local\.get\(key\)\)\)/s, "compact guarded pipeline status must re-read every canonical compact alias from chrome.storage.local to simulate reload-safe durability");
assert.match(popupSource, /function compactAliasDiagnostic[\s\S]*compact_alias_key: key[\s\S]*compact_alias_available: alias != null[\s\S]*compact_alias_missing_reason: alias \? null : "compact_latest_alias_missing_from_chrome_storage_local"[\s\S]*compact_alias_required_field_validity_summary[\s\S]*compact_alias_exact_id_only_strategy_evidence[\s\S]*compact_alias_completion_count/s, "compact guarded status must expose same-alias read diagnostics and clear missing reasons");
assert.match(popupSource, /async function buildGuardedHybridStartCollectingQueueCompletionPilot50Summary\(applyCompletion: boolean\)[\s\S]*HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_STORAGE_KEY[\s\S]*HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_COMPACT_STORAGE_KEY[\s\S]*guardedPipelineCompactLatestFromSummary\("queue_completion_pilot_50"/s, "Pilot 50 queue-completion must persist both the full latest artifact and compact durable latest metadata only after successful explicit completion");
assert.match(popupSource, /function guardedPipelineStorageInventorySummary[\s\S]*top_level_keys: Object\.keys\(record\)\.sort\(\)\.slice\(0, 80\)[\s\S]*source_run_id[\s\S]*run_id[\s\S]*source_pilot_run_id[\s\S]*pilot_run_id[\s\S]*source_beta_run_id[\s\S]*item_count[\s\S]*blocker_count[\s\S]*updated_at_present/s, "guarded pipeline inventory must emit only top-level keys, compact run IDs, counts, blocker count, and timestamp presence");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildGuardedPipelineStorageInventory"), popupSource.indexOf("async function copyCompactGuardedPipelineStatusFromPopup")), /runGuardedPipelineStep|runHybridOnlyWithModalFallbackDryRunFromPopup|runBackendShadowTestWithEstimatedViewsFromPopup|runGuardedHybridCollectBetaFromPopup|runGuardedHybridStartCollectingPilotFromPopup|runGuardedHybridStartCollectingQueueCompletionPilot\(|chrome\.storage\.local\.set|backendJson|accepted_aweme_ids:|source_verified_aweme_ids:|representative_items:|production_request_preview:|diagnostic_payload_preview:|thumbnail_url:|full_backend_response|rows_sample:\s*acceptedAwemeIds/s, "guarded pipeline storage inventory, backend shadow row evidence, and beta production row evidence must not run stages, call backend, mutate storage, or output raw ID arrays/payloads/thumbnails/backend bodies");
assert.match(popupSource, /function betaProductionRowEvidencePostVerifyRows[\s\S]*guardedHybridCollectBetaPostVerifySummaryPreviewEl\?\.textContent[\s\S]*JSON\.parse[\s\S]*guardedHybridRecordItems\(parsed\.representative_items\)[\s\S]*summary_title: "BETA_PRODUCTION_ROW_EVIDENCE"[\s\S]*read_only: true[\s\S]*storage_mutation: "none"[\s\S]*backend_mutation: "none"[\s\S]*production_beta_run: "no"[\s\S]*pipeline_stages_rerun: "none"[\s\S]*backend_readback_source:[\s\S]*rows_sample: rows\.slice\(0, 5\)/s, "beta production row evidence must be read-only, use current post-verify preview for backend read-back fields, and emit a sanitized five-row sample without rerunning beta or backend calls");
assert.match(popupSource, /function betaProductionRowEvidenceRows[\s\S]*expected_title_present[\s\S]*expected_title_length[\s\S]*production_payload_title_present[\s\S]*production_payload_title_is_real_text[\s\S]*production_payload_title_equals_aweme_id[\s\S]*backend_readback_title_present[\s\S]*backend_readback_title_is_real_text[\s\S]*backend_readback_title_equals_expected[\s\S]*backend_readback_title_equals_aweme_id[\s\S]*title_mismatch_reason[\s\S]*raw_like_payload_exact_numeric[\s\S]*backend_readback_raw_like_exact_numeric[\s\S]*backend_readback_raw_like_equals_expected[\s\S]*estimated_views_persisted[\s\S]*view_count_unchanged_from_estimated_views[\s\S]*backend_write_status/s, "beta production row evidence rows must expose title persistence/read-back, mismatch reason, exact raw Likes, estimated_views persistence, and view_count separation diagnostics");
assert.match(popupSource, /title_mismatch_reason_counts: guardedHybridPostVerifyCountByString\(rows, "title_mismatch_reason"\)[\s\S]*estimated_views_persisted_count: rows\.filter\(\(row\) => row\.estimated_views_persisted === true\)\.length[\s\S]*view_count_unchanged_from_estimated_views_count: rows\.filter\(\(row\) => row\.view_count_unchanged_from_estimated_views === true\)\.length/s, "beta production row evidence summary must aggregate title mismatch reasons, estimated_views persistence, and view_count not-copied safety");
assert.match(popupSource, /const insufficientBlocker = eligibleRows\.length < requestedBatchSize \? `insufficient_eligible_rows_for_pilot_\$\{requestedBatchSize\}` : null;[\s\S]*const preselectedRows = blockers\.length === 0 \? eligibleRows\.slice\(0, requestedBatchSize\) : \[\];[\s\S]*const rows = metricFidelityBlocker == null \? preselectedRows : \[\];[\s\S]*selected_pilot_rows_count: rows\.length/s, "Pilot 10 must block with insufficient_eligible_rows_for_pilot_10 and selected_pilot_rows_count 0 when fewer than 10 eligible rows exist");
assert.match(popupSource, /view_count_handling: "real_view_count_null_when_low_confidence_or_missing; estimated_views_never_copied_to_view_count"[\s\S]*rows_where_estimated_views_copied_to_view_count[\s\S]*view_count_policy_valid: Number\(payloadSchemaValidation\.rows_where_estimated_views_copied_to_view_count \?\? 0\) === 0/s, "Pilot 10 must keep estimated_views separate from nullable real view_count policy");
assert.match(popupSource, /pilot_queue_completion_enabled: false[\s\S]*queue_completion_deferred_reason: "post_verify_first_then_enable_in_next_phase"[\s\S]*queue_items_marked_complete_count: 0[\s\S]*collect_job_mutated: "no"[\s\S]*local_queue_completed_delta: 0[\s\S]*collect_job_mutation_delta: 0/s, "Pilot 10 must not mutate collect_job or mark queue items complete");
assert.match(popupSource, /const requiredBetaBatchSize = source\?\.beta_batch_size === 10 \? 10 : source\?\.beta_batch_size === 5 \? 5 : source\?\.beta_batch_size === 3 \? 3 : 0;[\s\S]*fieldPersistence\.thumbnail_match_count !== required[\s\S]*fieldPersistence\.raw_like_count_match_count !== required[\s\S]*fieldPersistence\.estimated_views_persisted_count !== required[\s\S]*fieldPersistence\.estimated_views_mismatch_count > 0[\s\S]*backend_lookup:[\s\S]*success_count: persisted\.length[\s\S]*missing_count: missingCount/s, "Pilot 10 post-verify must verify exactly 10 backend rows and fail if thumbnail, raw-like, or estimated_views is missing or mismatched");
assert.match(popupSource, /const metricFidelity = buildHybridMetricFidelitySummary\(rows\);[\s\S]*const metricFidelityProbeRows = buildHybridMetricFidelityProbeRows\(rows\);[\s\S]*summary_title: "HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY"[\s\S]*metric_fidelity: metricFidelity[\s\S]*metric_fidelity_probe_rows: metricFidelityProbeRows/s, "dry-run summary must expose machine-checkable metric_fidelity diagnostics and probe rows proving raw numeric like-count use");
assert.match(popupSource, /function buildHybridMetricFidelitySummary[\s\S]*compact_like_text_used_as_source_count[\s\S]*estimated_views_using_display_like_count_count[\s\S]*raw_numeric_like_count_not_used_count[\s\S]*metric_fidelity_verdict/s, "metric_fidelity computation must include raw, compact-display, rounded, and raw-like-not-used counters");
assert.match(popupSource, /const metricFidelity = buildHybridMetricFidelitySummary\(preselectedRows\);[\s\S]*const thumbnailFidelity = buildHybridThumbnailFidelitySummary\(preselectedRows\);[\s\S]*metric_fidelity_not_raw_metrics_preserved[\s\S]*metric_fidelity: \{ \.\.\.metricFidelity, pilot_write_blocked_by_metric_fidelity[\s\S]*thumbnail_fidelity: thumbnailFidelity/s, "Pilot summary must compute metric_fidelity and thumbnail_fidelity and block writes when raw metric fidelity is not preserved");
assert.match(popupSource, /function buildHybridThumbnailFidelitySummary[\s\S]*thumbnail_expected_count[\s\S]*thumbnail_sent_count[\s\S]*thumbnail_missing_count[\s\S]*thumbnail_source_path_counts[\s\S]*thumbnail_url_host_counts/s, "Pilot thumbnail_fidelity must expose expected, sent, missing, source-path, and host counts");
assert.match(popupSource, /function guardedHybridDouyinCdnHostEquivalent[\s\S]*function guardedHybridUrlsEquivalent[\s\S]*a\.protocol === b\.protocol && a\.pathname === b\.pathname && guardedHybridDouyinCdnHostEquivalent\(a\.host, b\.host\)[\s\S]*thumbnail_expected_count: thumbnailExpectedCount[\s\S]*thumbnail_actual_count: thumbnailActualCount[\s\S]*thumbnail_match_count: thumbnailMatchCount[\s\S]*thumbnail_mismatch_count: thumbnailMismatchCount[\s\S]*thumbnail_expected: thumbnailExpected[\s\S]*thumbnail_actual: thumbnailActual[\s\S]*thumbnail_match: thumbnailMatch/s, "post-verify must compare expected vs actual thumbnails with query-ignoring Douyin/CDN URL equivalence and expose counts plus representative diagnostics");
assert.match(popupSource, /const lookupItemsByAwemeId = guardedHybridItemsByAwemeId\(lookupItems\)[\s\S]*const foundItems = acceptedAwemeIds\.map\(\(awemeId\) => lookupItemsByAwemeId\.get\(awemeId\) \?\? null\)/s, "post-verify must join backend read-back rows by exact aweme/source video id, not response order");
assert.match(popupSource, /function guardedHybridItemsByAwemeId[\s\S]*item\.aweme_id[\s\S]*item\.source_video_external_id[\s\S]*item\.video_external_id[\s\S]*item\.external_id/s, "shared aweme-id lookup helper must index all backend read-back id aliases");
assert.match(popupSource, /function guardedHybridActualTitleRead[\s\S]*metadata_json[\s\S]*raw_payload_json[\s\S]*metadata_json\.profile_card_evidence\.title[\s\S]*metadata_json\.raw_dom_detail_metrics\.title[\s\S]*raw_payload_json\.profile_card_evidence\.title[\s\S]*raw_payload_json\.raw_dom_detail_metrics\.title/s, "post-verify must read backend title from top-level, metadata_json, and raw_payload_json evidence paths with provenance");
assert.match(popupSource, /title_expected_count: titleExpectedCount[\s\S]*title_actual_count: titleActualCount[\s\S]*title_match_count: titleMatchCount[\s\S]*title_mismatch_count: titleMismatchCount[\s\S]*title_id_fallback_mismatch_count: titleIdFallbackMismatchCount[\s\S]*title_expected: titleExpected[\s\S]*title_actual: titleActual[\s\S]*title_actual_read_path: titleActualRead\.path[\s\S]*title_match: titleMatch[\s\S]*title_is_id_fallback_mismatch: titleIsIdFallback/s, "post-verify must compare expected vs actual title, expose title match counts and read path provenance, and flag backend title ID fallback mismatches");
assert.match(popupSource, /raw_like_count_expected_count: rawLikeCountExpectedCount[\s\S]*raw_like_count_actual_count: rawLikeCountActualCount[\s\S]*raw_like_count_match_count: rawLikeCountMatchCount[\s\S]*raw_like_count_mismatch_count: rawLikeCountMismatchCount[\s\S]*like_count_expected: rawLikeCountExpected[\s\S]*like_count_actual: rawLikeCountActual[\s\S]*raw_like_count_match: rawLikeCountMatch[\s\S]*estimated_views_input_like_count/s, "post-verify must compare expected vs actual raw like counts and expose representative raw-like and estimated-view input diagnostics");
assert.match(popupSource, /function buildGuardedHybridQueueCompletionReadiness[\s\S]*queue_completion_enabled: false[\s\S]*ready_to_enable_queue_completion[\s\S]*required_conditions[\s\S]*queue_completion_readiness: queueCompletionReadiness[\s\S]*production_state: \{ pilot_queue_completion_enabled: false[\s\S]*queue_completion_enabled: false[\s\S]*queue_items_marked_complete_count: 0[\s\S]*collect_job_mutated: "no"/s, "Pilot post-verify must report queue_completion_readiness while keeping queue completion disabled and preserving no-mutation safety");
assert.match(popupSource, /source_pilot_run_id: sourcePilotRunId[\s\S]*pilot_batch_size: requestedBatchSize[\s\S]*expected_estimated_views_by_aweme_id[\s\S]*expected_estimated_views_input_like_count_by_aweme_id[\s\S]*expected_estimated_views_input_source_by_aweme_id[\s\S]*expected_estimated_views_formula: "tiered_like_multiplier_v1"[\s\S]*expected_null_view_count_policy[\s\S]*pilot_post_verify_inconclusive_expected_values_missing[\s\S]*pilot_post_verify_failed_persistence_mismatch/s, "Pilot 10 compact summary/artifact and post-verify must preserve expected maps and distinguish inconclusive expected-value handoff from persistence mismatch");
assert.match(popupSource, /async function persistGuardedHybridStartCollectingPilotSourceFromSummary[\s\S]*source\.expected_title_by_aweme_id = guardedHybridRecordMapFromItems[\s\S]*source\.expected_estimated_views_by_aweme_id/s, "Pilot source persistence must preserve expected title maps before post-verify reuses beta verification logic");
assert.match(popupSource, /const parentSourceRunId = dryRun\?\.source_run_id \?\? null;[\s\S]*run: \{ source_run_id: parentSourceRunId, parent_source_run_id: parentSourceRunId, source_dry_run_id: parentSourceRunId, source_pilot_run_id: sourcePilotRunId[\s\S]*source_artifact_preview: \{[\s\S]*source_run_id: parentSourceRunId, parent_source_run_id: parentSourceRunId, source_dry_run_id: parentSourceRunId, pilot_run_id: sourcePilotRunId, source_pilot_run_id: sourcePilotRunId/s, "Pilot source summary must persist canonical dry-run parent source_run_id separately from pilot_run_id/source_pilot_run_id");
assert.match(popupSource, /const pilotRunId = String\(run\.source_pilot_run_id \?\? run\.pilot_run_id[\s\S]*const parentSourceRunId = compactGuardedString\(run\.parent_source_run_id\)[\s\S]*source\.pilot_run_id = pilotRunId;[\s\S]*source\.source_pilot_run_id = pilotRunId;[\s\S]*source\.source_run_id = parentSourceRunId \?\? pilotRunId;[\s\S]*source\.parent_source_run_id = parentSourceRunId;[\s\S]*source\.source_dry_run_id = parentSourceRunId;/s, "Pilot source persistence must preserve dry-run parent linkage while keeping pilot identity fields separate");
assert.match(popupSource, /async function runBackendShadowTestWithEstimatedViewsFromPopup\(sampleSize: 3 \| 5\)[\s\S]*payloadValidation\?\.payload_valid !== "yes"[\s\S]*backendJson<Record<string, unknown>>\("POST", "\/douyin-extension\/capture-inbox\/shadow-items", payloadPreview[\s\S]*production collect state was not mutated/s, "backend shadow action must call only the validation endpoint and avoid production Start Collecting behavior");
assert.match(popupSource, /view_count_sent_as: item\.view_count \?\? null[\s\S]*real_view_count_data_quality: item\.real_view_count_data_quality/s, "backend shadow representative items must expose view_count_sent_as and real view-count data quality");
assert.match(popupSource, /const trustedFieldPaths = new Set\(\["statistics\.play_count", "statistics\.view_count", "stats\.play_count", "stats\.view_count", "aweme_statistics\.play_count", "aweme_statistics\.view_count", "aweme_detail\.statistics\.play_count", "aweme_detail\.statistics\.view_count", "mix_info\.statis\.play_vv"\]\)/s, "view count diagnostics must constrain selectable candidates to the trusted Views field allowlist");
assert.match(popupSource, /function viewCountCandidateRejectionReason[\s\S]*music\.[\s\S]*status\.[\s\S]*series_play_info[\s\S]*video\.play_addr[\s\S]*review[\s\S]*preview[\s\S]*url[\s\S]*boolean[\s\S]*untrusted_play_or_view_like_path_not_allowlisted/s, "view count diagnostics must reject known false-positive play/view-like paths instead of selecting them");
assert.match(popupSource, /function viewCountCandidateField[\s\S]*raw_type[\s\S]*raw_value_sample: scalar[\s\S]*parsed_value: parsed[\s\S]*selected_for_view_count: "no"/s, "trusted view count diagnostics must log only safe scalar samples, path, type, parsed value, and selection state");
assert.match(popupSource, /function extraValuesFromRecord[\s\S]*create_time[\s\S]*publish_time[\s\S]*view_count: viewCountDiagnostics\?\.normalized_view_count \?\? null[\s\S]*thumbnail_url_present/s, "hybrid-only extra value hydration must not default missing view count to zero");
assert.match(popupSource, /function extraValueValidityForLogRow[\s\S]*postedDateFromValue[\s\S]*valid_iso_datetime[\s\S]*realViewCount[\s\S]*valid_non_negative_number[\s\S]*valid_url/s, "extra values must validate posted timestamp/date, provenance-backed non-negative views, and sanitized thumbnail URL evidence");
assert.match(popupSource, /const postedMissingOrInvalid = isHybridOnly[\s\S]*extraValueValidCounts\.posted[\s\S]*extraValueValidCounts\.posted_at[\s\S]*\? "posted_missing_or_invalid"[\s\S]*\? "fix_posted_hydration"/s, "hybrid-only log must block backend shadow testing when posted evidence is missing or invalid");
assert.match(popupSource, /const viewsDataQualityVerdict = viewCountNonzeroCount > 0[\s\S]*"trusted_nonzero_views_found"[\s\S]*"trusted_zero_only_low_confidence"[\s\S]*"views_false_positive_only"[\s\S]*"views_not_available_in_non_modal_sources"/s, "hybrid-only log must classify trusted nonzero, trusted zero-only, false-positive-only, and unavailable Views data quality");
assert.match(popupSource, /const viewCountFalsePositiveOnly = isHybridOnly[\s\S]*const trustedViewsZeroOnlyLowConfidence = isHybridOnly[\s\S]*\? "views_false_positive_only"[\s\S]*\? "trusted_views_zero_only_low_confidence"[\s\S]*\? "fix_view_count_source_discovery"[\s\S]*\? "decide_views_optional_or_modal_fallback"/s, "hybrid-only log must block backend shadow testing when Views are false-positive-only or trusted zero-only low confidence");
assert.match(popupSource, /const thumbnailMissingOrInvalid = isHybridOnly[\s\S]*extraValueValidCounts\.thumbnail[\s\S]*thumbnailCoverageCount[\s\S]*thumbnailValidUrlCount[\s\S]*\? "thumbnail_missing_or_invalid"[\s\S]*\? "fix_thumbnail_hydration"/s, "hybrid-only log must block backend shadow testing when thumbnail evidence is missing or invalid");
assert.match(popupSource, /function modalWholeProfileComparisonSignal[\s\S]*if \(text\.includes\("abnormal_traffic"\) \|\| text\.includes\("abnormal traffic"\)\) return "abnormal_traffic";[\s\S]*return "none";/s, "calibrated read failures must not become anti-bot signals without captcha/checkpoint/login/security evidence");
assert.match(popupSource, /function modalWholeProfileComparisonExtractionFailureType[\s\S]*calibrated_point_read_failed[\s\S]*return "calibrated_point_read_failure"/s, "calibrated point read failures must be classified as extraction/readiness failures");
assert.match(popupSource, /last_flush_request_summary[\s\S]*last_flush_response_summary[\s\S]*last_backend_response[\s\S]*debug_last_response_summary[\s\S]*top_failure[\s\S]*current_aweme[\s\S]*current_index/, "backend error details export must include only the requested diagnostic fields");
assert.match(extensionBackendClientSource, /http_status/, "backend error details source must preserve response summary http_status diagnostics");
assert.match(extensionBackendClientSource, /backend_code[\s\S]*backend_stage[\s\S]*backend_detail/, "backend error details source must preserve backend code/stage/detail diagnostics");
assert.match(extensionBackendClientSource, /validation_error_paths/, "backend error details source must preserve backend validation paths when present");
assert.match(popupSource, /token\|authorization\|cookie\|secret\|password\|headers\|raw_html\|raw_dom\|raw_response_text/, "backend error details export must deny secret-like and raw diagnostic keys");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("function buildBackendErrorDetailsForPopup"), popupSource.indexOf("async function runWholeProfileControllerAction")), /raw_payload|raw_response_text|raw_dom|raw_html|headers/i, "backend error details export must not directly include raw payloads, raw responses, DOM, HTML, or headers");
assert.doesNotMatch(popupHtml, /Test Current Video/, "popup must not expose probe-only action in the main operator UI");
assert.match(popupHtml, /Start Calibration/, "popup must expose calibration action");
assert.match(popupSource, /runWholeProfilePrimaryActionFromPopup/, "popup must route resume and stop behavior through the dynamic scanner primary action");
assert.match(popupSource, /suppressDuplicateStartCollectingIfActive[\s\S]*deriveAuthoritativeRunnerLock\(state\)[\s\S]*duplicate_start_suppressed: "yes"/, "popup must suppress duplicate Start Collecting clicks while a runner is already active using the authoritative lock");
assert.match(popupSource, /primary_action_locked_reason: "collection_running"/, "popup duplicate-start suppression must record the active runner lock reason");
assert.match(popupSource, /primary_action_lock_source: runnerLock\.source \?\? "unknown"/, "popup duplicate-start suppression must record the exact authoritative lock source");
assert.match(popupSource, /if \(actionKey === "start_collecting" && await suppressDuplicateStartCollectingIfActive\(label\)\) return;/, "popup primary action handler must suppress duplicate starts before dispatching Start Collecting");
assert.match(popupSource, /case "start_collecting":[\s\S]*return runWholeProfileHarvestProductFromPopup\(\);/, "Continue Next 10 must keep dispatching through the existing Start Collecting path");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("case \"start_collecting\":"), popupSource.indexOf("case \"pause\":")), /resume|handleResumeCollectingClick/, "safe batch continuation must not route Start Collecting through Resume");
assert.match(popupWorkflowSource, /Capture session missing\. Open profile and run Capture current page, or run Smart Capture from profile first\./);
assert.match(popupWorkflowSource, /Calibrate 4 Points on the modal video\./);
assert.match(popupWorkflowSource, /Test Current Video has not passed\. Click Test Current Video first\./);
assert.match(popupSource, /probeStatusMessage/);
assert.match(popupSource, /source_used/);
assert.match(popupSource, /apiResponse\.target_aweme_ids/, "smart capture must use backend target_aweme_ids");
assert.doesNotMatch(popupSource, /async function runSmartCaptureHarvest/, "legacy smart capture orchestration must be removed from popup");
assert.match(popupSource, /No new or incomplete videos found\./, "smart capture must show empty target queue message");
assert.match(popupSource, /verifyWholeProfileFromPopup/, "popup must implement canonical Whole Profile verification action");
assert.match(popupSource, /getWholeProfileHarvestReadiness\(state\)/, "popup must render whole-profile readiness from the canonical selector");
assert.match(popupSource, /getWholeProfileHarvestActionState\(state\)/, "popup must render whole-profile action gating from the canonical selector");
assert.match(popupSource, /let latestWholeProfileHarvestState: WholeProfileHarvestState \| null = null;/, "popup must keep a live local scanner state cache");
assert.match(popupSource, /function renderWholeProfileHarvestProductStateFromState\(state: WholeProfileHarvestState/, "popup must rerender from live scanner state without reopening");
assert.match(popupSource, /async function applyOptimisticScanProfilePopupState/, "Scan Profile click must apply an optimistic running state");
assert.match(popupSource, /workflow:[\s\S]*scan: \{ status: "running"[\s\S]*active_task: "scan_profile"[\s\S]*action_lock: "scan_profile"/, "optimistic Scan Profile state must mark the scan workflow running and locked");
assert.match(popupSource, /chrome\.storage\.onChanged\.addListener\(handleWholeProfileHarvestStorageChange\)/, "popup must subscribe to chrome.storage.onChanged for live scanner state");
assert.match(popupSource, /changes\[WHOLE_PROFILE_HARVEST_STATE_KEY\]/, "popup storage listener must watch the canonical scanner state key");
assert.match(popupSource, /chrome\.runtime\.onMessage\?\.addListener\(handleWholeProfileHarvestRuntimeMessage\)/, "popup must accept optional scanner state runtime progress messages");
assert.match(popupSource, /WHOLE_PROFILE_POPUP_STATE_CHANGED_MESSAGE = "douyinScanner:stateChanged"/, "popup runtime listener must use the scanner state changed message type");
assert.match(popupSource, /WHOLE_PROFILE_PROGRESS_POLL_FALLBACK_MS = 1_500/, "popup must define a storage polling fallback interval for missed live progress events");
assert.match(popupSource, /window\.setInterval\([\s\S]*readWholeProfileHarvestProductState\(\)[\s\S]*storage\.pollFallback/, "popup must poll canonical storage as a fallback when runtime or storage messages are missed");
assert.match(popupSource, /popup_progress_last_seen_seq/, "popup must expose progress sequence diagnostics");
assert.match(popupSource, /popup_progress_poll_fallback_used/, "popup must expose whether storage polling fallback rendered progress");
assert.match(popupSource, /chrome\.storage\.onChanged\.removeListener\(handleWholeProfileHarvestStorageChange\)/, "popup must clean up storage listeners on unload");
assert.match(popupSource, /chrome\.runtime\.onMessage\?\.removeListener\(handleWholeProfileHarvestRuntimeMessage\)/, "popup must clean up runtime message listeners on unload");
assert.match(popupSource, /recoverStaleWholeProfileScannerState/, "popup must recover stale running scanner locks on open or live update");
assert.match(popupSource, /last_action_result: "stale_recovered"/, "stale scan recovery must record a diagnostic result");
assert.match(popupSource, /staleRunningCollectionWithoutOwner[\s\S]*workflow\.collection\.status === "running"[\s\S]*workflow\.active_task == null[\s\S]*workflow\.action_lock == null/, "stale collection recovery must detect running collection state without an owner");
assert.match(popupSource, /staleRunningCollectionWithoutOwner[\s\S]*status: "paused"[\s\S]*pause_message: "Previous collection was interrupted\. Reload the Douyin tab after extension reload, then scan again\."/, "stale collection recovery must show a consistent interrupted state without clearing queue or calibration");
assert.match(popupSource, /wholeProfileHarvestActionInFlight/, "popup must guard Scan Profile against duplicate double-click starts");
assert.match(popupSource, /getDouyinScannerBusyState\(base\)[\s\S]*if \(busy\.isBusy && !busy\.isStale\) return null;/, "optimistic Scan Profile must not start while a non-stale scan is already busy");
const optimisticScanHelperSource = popupSource.slice(popupSource.indexOf("async function applyOptimisticScanProfilePopupState"), popupSource.indexOf("async function verifyWholeProfileFromPopup"));
assert.doesNotMatch(optimisticScanHelperSource, /postJson</, "optimistic scanner state must not call the backend");
assert.match(popupSource, /shouldHoldScanPresentationForRescan\(state\)[\s\S]*post_scan_counter_snapshot: holdPresentation \? state\.post_scan_counter_snapshot : null/s, "optimistic scan must preserve post-scan tiles during same-profile rescan");
assert.match(popupSource, /detectProfileContextMismatch\(base, activeTabUrl\)[\s\S]*clearPopupPresentationLocksOnProfileSwitch/s, "optimistic scan must clear presentation locks only on profile switch");
assert.match(popupSource, /async function renderScanOrCollectTerminalPopupState[\s\S]*maybeHydrateCollectQueueForDisplay\(state\)[\s\S]*resolveScannerControlPanelRenderContext/s, "scan terminal must hydrate queue and render immediately without debounce");

{
  const snapshot = {
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: null,
    calibration: null,
    lastProbe: null,
    harvestProgress: null,
    smartState: null,
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  } as const;
  const guard = startHarvestGuard(snapshot);
  assert.equal(guard.ok, false);
  if (!guard.ok) assert.equal(guard.message, "Calibrate 4 Points on the modal video.");
  assert.equal(nextRequiredAction(snapshot), "Calibrate 4 Points");
}

{
  const calibration: RightRailCalibration = {
    version: "calibrated_four_point_workflow",
    created_at: new Date().toISOString(),
    viewport_width: 1920,
    viewport_height: 1080,
    profile_url_host: "www.douyin.com",
    points: {
      like_count: { x: 10, y: 10, x_ratio: 0.1, y_ratio: 0.1 },
      comment_count: { x: 20, y: 20, x_ratio: 0.2, y_ratio: 0.2 },
      favorite_count: { x: 30, y: 30, x_ratio: 0.3, y_ratio: 0.3 },
      share_count: { x: 40, y: 40, x_ratio: 0.4, y_ratio: 0.4 }
    }
  };
  const probe: FullModalHarvestProbeResult = {
    aweme_id: "7634",
    duration_seconds: 671.94,
    duration_text: null,
    like_count: 684,
    comment_count: 46,
    favorite_count: 151,
    share_count: 90,
    posted_text: null,
    action_blocks_found: 0,
    ready_for_full_harvest: true,
    probe_status: "PASS",
    source_used: "calibrated_point_dom"
  };
  const guard = startHarvestGuard({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration,
    lastProbe: probe,
    harvestProgress: { running: false, target_count: 49, current_aweme_id: null, harvested_count: 0, updated_count: 0, duplicate_count: 0, failed_count: 0, flushed_count: 0, last_error: null, stopped_reason: null },
    smartState: null,
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/profile?modal_id=7634")
  });
  assert.deepEqual(guard, { ok: true });
}

{
  const smartState = createSmartState({
    latest_capture_session_id: "session-1",
    latest_capture_id: "capture-1",
    captured_item_count: 37,
    target_aweme_ids: ["7634", "7635"]
  });
  assert.deepEqual(smartHarvestStartOptions(smartState), {
    target_count: 2,
    flush_every_n_items: 5,
    delay_between_items_ms: 5000,
    per_item_timeout_ms: 15000,
    stop_on_captcha: true,
    stop_on_no_next: true,
    allow_probe_warnings: false,
    capture_session_id: "session-1",
    capture_id: "capture-1",
    target_aweme_ids: ["7634", "7635"],
    profile_card_evidence_by_aweme_id: {}
  });
}

assert.equal(describeHarvestState(null), "idle");
assert.equal(describeHarvestState({ running: true, target_count: 49, current_aweme_id: null, harvested_count: 0, updated_count: 0, duplicate_count: 0, failed_count: 0, flushed_count: 0, last_error: null, stopped_reason: null }), "running");
assert.equal(describeHarvestState({ running: false, target_count: 49, current_aweme_id: null, harvested_count: 0, updated_count: 0, duplicate_count: 0, failed_count: 0, flushed_count: 0, last_error: null, stopped_reason: "operator_stopped" }), "stopped");

assert.equal(viewportWarningMessage({ width: 1920, height: 919 }, pageViewport(1920, 919)), "none");
assert.equal(viewportWarningMessage({ width: 1920, height: 919 }, pageViewport(1500, 919)), "none");
assert.equal(viewportWarningMessage({ width: 1920, height: 919 }, { width: 375, height: 600 }), "none");

{
  const calibration: RightRailCalibration = {
    version: "phase10a",
    created_at: new Date().toISOString(),
    viewport_width: 1920,
    viewport_height: 919,
    profile_url_host: "www.douyin.com",
    points: {
      like_count: { x: 10, y: 10, x_ratio: 0.1, y_ratio: 0.1 },
      comment_count: { x: 20, y: 20, x_ratio: 0.2, y_ratio: 0.2 },
      favorite_count: { x: 30, y: 30, x_ratio: 0.3, y_ratio: 0.3 },
      share_count: { x: 40, y: 40, x_ratio: 0.4, y_ratio: 0.4 }
    }
  };
  const probe: FullModalHarvestProbeResult = {
    aweme_id: "7634",
    duration_seconds: 671.94,
    duration_text: null,
    like_count: 684,
    comment_count: 46,
    favorite_count: 151,
    share_count: 90,
    posted_text: null,
    action_blocks_found: 0,
    ready_for_full_harvest: true,
    probe_status: "PASS",
    source_used: "calibrated_point_dom",
    current_viewport: { width: 1920, height: 919 }
  };
  const reconciled = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration,
    lastProbe: probe,
    harvestProgress: null,
    smartState: createSmartState({
      current_state: "calibration_required",
      calibration_status: "calibrated",
      next_required_action: "Viewport changed significantly. Recalibrate before Smart Capture & Harvest.",
      last_probe_status: "PASS",
      latest_capture_session_id: "session-1",
      last_error: "viewport_changed_significantly"
    }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/profile?modal_id=7634"),
    currentPageViewport: pageViewport(1920, 919)
  });
  assert.ok(reconciled);
  assert.equal(reconciled?.current_state, "capture_ready");
  assert.equal(reconciled?.next_required_action, "Start harvest");
  assert.equal(reconciled?.last_error, null);
}

{
  const calibration: RightRailCalibration = {
    version: "phase10a",
    created_at: new Date().toISOString(),
    viewport_width: 1920,
    viewport_height: 919,
    profile_url_host: "www.douyin.com",
    points: {
      like_count: { x: 10, y: 10, x_ratio: 0.1, y_ratio: 0.1 },
      comment_count: { x: 20, y: 20, x_ratio: 0.2, y_ratio: 0.2 },
      favorite_count: { x: 30, y: 30, x_ratio: 0.3, y_ratio: 0.3 },
      share_count: { x: 40, y: 40, x_ratio: 0.4, y_ratio: 0.4 }
    }
  };
  const reconciled = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration,
    lastProbe: null,
    harvestProgress: {
      running: false,
      target_count: 49,
      current_aweme_id: null,
      harvested_count: 0,
      updated_count: 0,
      duplicate_count: 0,
      failed_count: 0,
      flushed_count: 0,
      last_error: null,
      stopped_reason: null,
      current_viewport: { width: 1500, height: 919 }
    },
    currentPageViewport: pageViewport(1500, 919),
    smartState: createSmartState({
      current_state: "capture_ready",
      calibration_status: "calibrated",
      latest_capture_session_id: "session-1"
    }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/profile?modal_id=7634")
  });
  assert.ok(reconciled);
  assert.equal(reconciled?.current_state, "capture_ready");
  assert.equal(reconciled?.next_required_action, "Run Capture current page");
  assert.equal(reconciled?.last_error, null);
}

{
  const staleProbe: FullModalHarvestProbeResult = {
    aweme_id: "7634",
    duration_seconds: 10,
    duration_text: null,
    like_count: 1,
    comment_count: 2,
    favorite_count: 3,
    share_count: 4,
    posted_text: null,
    action_blocks_found: 0,
    ready_for_full_harvest: true,
    probe_status: "PASS",
    source_used: "calibrated_point_dom"
  };
  assert.equal(displayProbeStatus(staleProbe, classifyDouyinPopupPage("https://www.douyin.com/user/profile?modal_id=7634")), "PASS");
  const reconciled = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration: null,
    lastProbe: staleProbe,
    harvestProgress: null,
    smartState: createSmartState({
      current_state: "capture_ready",
      latest_capture_session_id: "session-1",
      calibration_status: "missing"
    }),
    lastError: null
  });
  assert.ok(reconciled);
  assert.equal(reconciled?.current_state, "calibration_required");
  assert.equal(reconciled?.next_required_action, "Start Right Rail Calibration, click like/comment/favorite/share, then resume Smart Capture & Harvest.");
  assert.equal(reconciled?.last_probe_status, "none");
}

{
  const calibration: RightRailCalibration = {
    version: "phase10a",
    created_at: new Date().toISOString(),
    viewport_width: 1920,
    viewport_height: 919,
    profile_url_host: "www.douyin.com",
    points: {
      like_count: { x: 10, y: 10, x_ratio: 0.1, y_ratio: 0.1 },
      comment_count: { x: 20, y: 20, x_ratio: 0.2, y_ratio: 0.2 },
      favorite_count: { x: 30, y: 30, x_ratio: 0.3, y_ratio: 0.3 },
      share_count: { x: 40, y: 40, x_ratio: 0.4, y_ratio: 0.4 }
    }
  };
  const staleProbe: FullModalHarvestProbeResult = {
    aweme_id: "old-modal",
    duration_seconds: 10,
    duration_text: null,
    like_count: 1,
    comment_count: 2,
    favorite_count: 3,
    share_count: 4,
    posted_text: null,
    action_blocks_found: 0,
    ready_for_full_harvest: true,
    probe_status: "PASS",
    source_used: "calibrated_point_dom",
    current_viewport: { width: 1920, height: 919 }
  };
  const profilePage = classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAA41XPPYoeuqQyDtXDLltg7aBWchubmMBfEErR88VDm99210SJeDG1Qp1YattZ7Qnv");
  assert.equal(profilePage.kind, "profile");
  assert.equal(profilePage.modalId, null);
  assert.equal(viewportWarningMessage({ width: 1920, height: 919 }, pageViewport(1920, 919)), "none");
  assert.equal(displayProbeStatus(staleProbe, profilePage), "not applicable");
  const reconciled = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration,
    lastProbe: staleProbe,
    harvestProgress: null,
    smartState: createSmartState({
      current_state: "capture_ready",
      calibration_status: "calibrated",
      latest_capture_session_id: "session-1",
      last_probe_status: "PASS",
      last_error: "viewport_changed_significantly",
      next_required_action: "Viewport changed significantly. Recalibrate before Smart Capture & Harvest."
    }),
    lastError: null,
    pageState: profilePage,
    currentPageViewport: pageViewport(1920, 919)
  });
  assert.equal(reconciled?.current_state, "modal_required");
  assert.equal(reconciled?.next_required_action, MODAL_REQUIRED_MESSAGE);
  assert.equal(reconciled?.last_error, null);
  assert.equal(reconciled?.last_probe_status, "none");
}

{
  const modalPage = classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAA41XPPYoeuqQyDtXDLltg7aBWchubmMBfEErR88VDm99210SJeDG1Qp1YattZ7Qnv?modal_id=7634");
  const directVideoPage = classifyDouyinPopupPage("https://www.douyin.com/video/8899");
  const matchingProbe: FullModalHarvestProbeResult = {
    aweme_id: "7634",
    duration_seconds: 10,
    duration_text: null,
    like_count: 1,
    comment_count: 2,
    favorite_count: 3,
    share_count: 4,
    posted_text: null,
    action_blocks_found: 0,
    ready_for_full_harvest: true,
    probe_status: "PASS",
    source_used: "calibrated_point_ocr"
  };
  const staleSourceProbe: FullModalHarvestProbeResult = { ...matchingProbe, source_used: "combined_modal_text_fallback" };
  assert.equal(modalPage.kind, "modal");
  assert.equal(modalPage.modalId, "7634");
  assert.equal(directVideoPage.kind, "video");
  assert.equal(directVideoPage.modalId, "8899");
  assert.equal(isFreshModalProbe(matchingProbe, modalPage), true);
  assert.equal(isFreshModalProbe({ ...matchingProbe, aweme_id: "old-modal" }, modalPage), false);
  assert.equal(isFreshModalProbe(staleSourceProbe, modalPage), false);
}

{
  const calibration: RightRailCalibration = {
    version: "phase10a",
    created_at: new Date().toISOString(),
    viewport_width: 1920,
    viewport_height: 919,
    profile_url_host: "www.douyin.com",
    points: {
      like_count: { x: 10, y: 10, x_ratio: 0.1, y_ratio: 0.1 },
      comment_count: { x: 20, y: 20, x_ratio: 0.2, y_ratio: 0.2 },
      favorite_count: { x: 30, y: 30, x_ratio: 0.3, y_ratio: 0.3 },
      share_count: { x: 40, y: 40, x_ratio: 0.4, y_ratio: 0.4 }
    }
  };
  const unavailable = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration,
    lastProbe: null,
    harvestProgress: null,
    smartState: createSmartState({ current_state: "capture_ready", calibration_status: "calibrated", latest_capture_session_id: "session-1" }),
    lastError: null,
    currentPageViewport: null
  });
  assert.equal(unavailable?.last_error, CONTENT_SCRIPT_VIEWPORT_UNAVAILABLE);
  assert.equal(unavailable?.next_required_action, CONTENT_SCRIPT_VIEWPORT_RETRY_MESSAGE);

  const popupSizedViewport = { width: 375, height: 600 };
  assert.equal(viewportWarningMessage({ width: 1920, height: 919 }, popupSizedViewport), "none");
}

{
  const previous = createSmartState({ current_state: "harvesting", next_required_action: "Harvest running", target_count: 53, latest_capture_session_id: "session-1" });
  const completeProgress: FullModalHarvestProgress = {
    running: false,
    current_state: "completed",
    phase: "completed",
    target_count: 53,
    current_index: 53,
    current_aweme_id: "53",
    harvested_count: 53,
    processed_count: 53,
    updated_count: 53,
    pending_count: 0,
    duplicate_count: 0,
    failed_count: 0,
    flushed_count: 53,
    last_error: null,
    stopped_reason: null,
    can_resume: false
  };
  const completedState = smartStateFromHarvestProgress("harvesting", "Harvest running", previous, completeProgress);
  assert.equal(completedState.current_state, "completed", "impossible running state at target_index>=target_count normalizes to completed");
  assert.equal(completedState.next_required_action, "Review results");
  assert.equal(completedState.last_error, null);

  const warningState = smartStateFromHarvestProgress("harvesting", "Harvest running", previous, { ...completeProgress, current_state: "completed_with_warnings", phase: "completed_with_warnings", updated_count: 52, failed_count: 1, last_error: "Harvest completed with warnings. Updated 52/53. Failed 1." });
  assert.equal(warningState.current_state, "completed_with_warnings", "completed final progress with failed_count normalizes to completed_with_warnings");
  assert.equal(warningState.next_required_action, "Review results");
  assert.match(warningState.last_error ?? "", /Harvest completed with warnings/);

  const loadingState = smartStateFromHarvestProgress("harvesting", "Harvest running", previous, {
    ...completeProgress,
    running: true,
    current_state: "harvesting",
    phase: "loading_next_video",
    current_index: 12,
    current_aweme_id: "12",
    harvested_count: 11,
    processed_count: 11,
    updated_count: 11,
    flushed_count: 10,
    can_resume: false
  });
  assert.equal(loadingState.current_state, "loading_next_video");
  assert.equal(loadingState.next_required_action, "Harvest running");

  const waitingState = smartStateFromHarvestProgress("harvesting", null, previous, {
    ...completeProgress,
    running: true,
    current_state: "harvesting",
    phase: "waiting_modal_change",
    current_index: 12,
    current_aweme_id: "12",
    harvested_count: 11,
    processed_count: 11,
    updated_count: 11,
    flushed_count: 10,
    can_resume: false
  });
  assert.equal(waitingState.current_state, "waiting_modal_change");
  assert.equal(waitingState.next_required_action, "Show Progress");

  const flushingState = smartStateFromHarvestProgress("harvesting", null, previous, {
    ...completeProgress,
    running: true,
    current_state: "harvesting",
    phase: "flushing",
    current_index: 12,
    current_aweme_id: "12",
    harvested_count: 11,
    processed_count: 11,
    updated_count: 11,
    flushed_count: 10,
    can_resume: false,
    flush_error_message: null
  });
  assert.equal(flushingState.current_state, "flushing");
  assert.equal(flushingState.next_required_action, "Flush Pending");

  const pausedState = smartStateFromHarvestProgress("harvesting", null, previous, {
    ...completeProgress,
    running: false,
    current_state: "paused",
    phase: "paused",
    current_index: 12,
    current_aweme_id: "12",
    harvested_count: 11,
    processed_count: 11,
    updated_count: 11,
    flushed_count: 10,
    can_resume: true,
    last_error: "Return to the Douyin tab to continue collecting."
  });
  assert.equal(pausedState.current_state, "paused");
  assert.equal(pausedState.next_required_action, "Resume Harvest");
  assert.equal(pausedState.last_error, "Return to the Douyin tab to continue collecting.");
}

{
  const fourPointCalibration: RightRailCalibration = {
    version: "calibrated_four_point_workflow",
    created_at: new Date().toISOString(),
    viewport_width: 1920,
    viewport_height: 919,
    viewport_source: "content_script",
    profile_url_host: "www.douyin.com",
    points: {
      like_count: { x: 10, y: 10, x_ratio: 0.1, y_ratio: 0.1 },
      comment_count: { x: 20, y: 20, x_ratio: 0.2, y_ratio: 0.2 },
      favorite_count: { x: 30, y: 30, x_ratio: 0.3, y_ratio: 0.3 },
      share_count: { x: 40, y: 40, x_ratio: 0.4, y_ratio: 0.4 }
    }
  };
  const oldFourPointCalibration: RightRailCalibration = {
    ...fourPointCalibration,
    version: "phase10a"
  };
  const probe: FullModalHarvestProbeResult = {
    aweme_id: "7634",
    duration_seconds: 10,
    duration_text: null,
    like_count: 1,
    comment_count: 2,
    favorite_count: 3,
    share_count: 4,
    posted_text: null,
    action_blocks_found: 0,
    ready_for_full_harvest: true,
    probe_status: "PASS",
    source_used: "calibrated_point_dom"
  };
  assert.deepEqual(validateRightRailCalibration(fourPointCalibration), { status: "valid", pointCount: 4, missingPoints: [] });
  assert.deepEqual(validateRightRailCalibration(oldFourPointCalibration), { status: "valid", pointCount: 4, missingPoints: [] });
  const guard = startHarvestGuard({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration: oldFourPointCalibration,
    lastProbe: probe,
    harvestProgress: null,
    smartState: null,
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/profile?modal_id=7634")
  });
  assert.deepEqual(guard, { ok: true });
}

{
  const profileWithoutModal = classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture");
  const modalWithModalId = classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634");
  const directVideo = classifyDouyinPopupPage("https://www.douyin.com/video/8899");
  assert.equal(profileWithoutModal.kind, "profile", "profile page without modal_id must be profile");
  assert.equal(profileWithoutModal.modalId, null);
  assert.equal(modalWithModalId.kind, "modal", "profile URL with modal_id must be modal");
  assert.equal(modalWithModalId.modalId, "7634");
  assert.equal(directVideo.kind, "video", "direct video URL must be video");
  assert.equal(directVideo.modalId, "8899");
}

{
  const existingCalibration: RightRailCalibration = {
    version: "phase10a",
    created_at: new Date().toISOString(),
    viewport_width: 1920,
    viewport_height: 919,
    profile_url_host: "www.douyin.com",
    points: {
      like_count: { x: 10, y: 10, x_ratio: 0.1, y_ratio: 0.1 },
      comment_count: { x: 20, y: 20, x_ratio: 0.2, y_ratio: 0.2 },
      favorite_count: { x: 30, y: 30, x_ratio: 0.3, y_ratio: 0.3 },
      share_count: { x: 40, y: 40, x_ratio: 0.4, y_ratio: 0.4 }
    }
  };
  const detectorUnavailable = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: null,
    calibration: existingCalibration,
    lastProbe: null,
    harvestProgress: null,
    smartState: null,
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture"),
    contentScriptStatus: "ready",
    detectorStatus: "failed",
    detectorError: "detector_unavailable"
  });
  assert.equal(detectorUnavailable?.current_state, "detector_unavailable", "detector failure must not become calibration_required");
  assert.equal(detectorUnavailable?.next_required_action, "Reconnect Douyin tab");

  const profileMissingCapture = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: null,
    calibration: null,
    lastProbe: null,
    harvestProgress: null,
    smartState: null,
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  });
  assert.equal(profileMissingCapture?.current_state, "profile_capture_required");
  assert.equal(profileMissingCapture?.next_required_action, "Capture current page or Smart Capture & Harvest");

  const profileWithCapture = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration: null,
    lastProbe: null,
    harvestProgress: null,
    smartState: createSmartState({ latest_capture_session_id: "session-1", target_aweme_ids: ["7634"] }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  });
  assert.equal(profileWithCapture?.current_state, "modal_required", "profile capture with targets should ask for modal, not calibration");

  const modalMissingCalibration = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration: null,
    lastProbe: null,
    harvestProgress: null,
    smartState: createSmartState({ latest_capture_session_id: "session-1" }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  });
  assert.equal(modalMissingCalibration?.current_state, "calibration_required", "modal page may require calibration");
  const modalMissingCaptureProbe: FullModalHarvestProbeResult = {
    aweme_id: "7634",
    duration_seconds: 10,
    duration_text: null,
    like_count: 1,
    comment_count: 2,
    favorite_count: 3,
    share_count: 4,
    posted_text: null,
    action_blocks_found: 0,
    ready_for_full_harvest: true,
    probe_status: "PASS",
    source_used: "calibrated_point_dom"
  };
  const modalMissingCapture = reconcileSmartState({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: null,
    calibration: existingCalibration,
    lastProbe: modalMissingCaptureProbe,
    harvestProgress: null,
    smartState: createSmartState({ current_state: "detector_unavailable", last_error: "detector_unavailable", next_required_action: "Reconnect Douyin tab" }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  });
  assert.equal(modalMissingCapture?.current_state, "harvest_ready", "modal + capture_session missing may become harvest_ready after Test Current Video passes");
  assert.equal(modalMissingCapture?.next_required_action, "Smart Capture & Harvest / Resume Harvest");
  assert.equal(modalMissingCapture?.last_error, null, "detector-ready reconciliation must clear stale detector last_error");

  const modalMissingCaptureReason = computeCurrentBlockingReason({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: null,
    calibration: existingCalibration,
    lastProbe: modalMissingCaptureProbe,
    harvestProgress: null,
    smartState: createSmartState({ current_state: "harvest_ready", last_error: "detector_unavailable" }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  });
  assert.equal(modalMissingCaptureReason.state, "harvest_ready");
  assert.equal(modalMissingCaptureReason.message, "Ready to harvest.");

  const readyReason = computeCurrentBlockingReason({
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration: existingCalibration,
    lastProbe: modalMissingCaptureProbe,
    harvestProgress: null,
    smartState: createSmartState({ current_state: "harvest_ready", latest_capture_session_id: "session-1", last_error: "detector_unavailable" }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  });
  assert.equal(readyReason.state, "harvest_ready", "detector ready must not return detector_unavailable for stale detector errors");
  assert.equal(readyReason.message, "Ready to harvest.");

  assert.equal(computeCurrentBlockingReason({ ...readyReasonSnapshot(existingCalibration, modalMissingCaptureProbe), backendReachable: "no" }).state, "backend_unavailable");
  assert.equal(computeCurrentBlockingReason({ ...readyReasonSnapshot(existingCalibration, modalMissingCaptureProbe), supportedDouyinTab: "no" }).state, "unsupported_tab");
  assert.equal(computeCurrentBlockingReason({ ...readyReasonSnapshot(existingCalibration, modalMissingCaptureProbe), contentScriptStatus: "missing" }).state, "content_script_unavailable");
  assert.equal(computeCurrentBlockingReason({ ...readyReasonSnapshot(existingCalibration, modalMissingCaptureProbe), detectorStatus: "failed" }).state, "detector_unavailable");
  assert.equal(computeCurrentBlockingReason({ ...readyReasonSnapshot(existingCalibration, modalMissingCaptureProbe), captureSessionId: null }).state, "harvest_ready");
}

assert.match(contentScriptSource, /export function detectDouyinPageContext/, "content script must expose Phase 13D page context source of truth");
assert.match(contentScriptSource, /const CONTENT_SCRIPT_VERSION = "22C-13A"/, "content script ping must expose the active manual pagination verification capability version");
assert.match(contentScriptSource, /REUP_DOUYIN_PING[\s\S]*REUP_DOUYIN_PONG[\s\S]*ready: true[\s\S]*window\.location\.href[\s\S]*page_context[\s\S]*viewport/, "content script must return rich ping/pong diagnostics");
assert.match(contentScriptSource, /REUP_DOUYIN_DETECT_PAGE_CONTEXT[\s\S]*detector_status: "ready"[\s\S]*current_url/, "page-context detector must report ready status and current URL");
assert.match(popupSource, /function runDetectorWithReconnect/, "popup must implement ping-inject-ping detector reconnect");
assert.match(popupSource, /async function ensureDouyinContentScriptReady/, "popup must centralize content-script readiness checks");
assert.match(popupSource, /const firstPing = await withTimeout\(pingContentScript\(tabId\)[\s\S]*chrome\.scripting\.executeScript\(\{ target: \{ tabId \}, files: \["contentScript\.js"\] \}\)[\s\S]*const secondPing = await withTimeout\(pingContentScript\(tabId\)/, "reconnect must ping, inject missing content script, then ping again");
assert.match(popupSource, /if \(!tabUrl \|\| !manifestMatched\)[\s\S]*reason: "unsupported_tab"[\s\S]*manifestMatched: false/, "non-Douyin tabs must fail diagnostics without injecting");
assert.match(popupSource, /reason: "content_script_unavailable"[\s\S]*pingError:[\s\S]*injectionAttempted: true[\s\S]*injectionError[\s\S]*manifestMatched/, "failed reconnect must return precise content-script diagnostics");
assert.match(popupSource, /REUP_DOUYIN_DETECT_PAGE_CONTEXT[\s\S]*detector_status: "ready"/, "detector wrapper must use content script after reconnect and mark ready results");
assert.match(popupSource, /reason: "detector_message_failed"/, "detector message failures must be separated from injection failures");
assert.match(popupHtml, /id="reconnectDouyinButton"/, "popup must render Reconnect Douyin tab button");
assert.match(popupSource, /runDetectorWithReconnect\(true\)/, "Reconnect Douyin Tab must force a reconnect attempt");
assert.match(popupSource, /renderDetectorDiagnostics/, "popup must render reconnect diagnostics");
assert.match(popupSource, /Supported Douyin tab[\s\S]*Content script[\s\S]*Last reconnect[\s\S]*Last chrome error/, "popup summary must expose detector reconnect diagnostics");
assert.match(popupSource, /Content script unavailable\. Reload extension, then hard refresh Douyin tab\./, "failed reconnect must show the required operator guidance");
assert.match(popupSource, /Page:/, "popup summary must show page");
assert.match(popupSource, /Backend:/, "popup summary must show backend");
assert.match(popupSource, /Detector:/, "popup summary must show detector status");
assert.match(popupSource, /REUP_DOUYIN_PROBE_CURRENT_MODAL/, "popup must still support modal probe messages for calibration flows");
assert.doesNotMatch(popupSource, /async function runSmartCaptureHarvest/, "legacy Smart Capture orchestration must be removed");
assert.match(popupSource, /preflightCurrentState\("startCalibration"\)/, "Start Calibration must use current-state preflight");
assert.match(popupSource, /runModalWholeProfileVerifyPipeline[\s\S]*refreshOperationalState/, "Modal Whole Profile Test must refresh operational state before verify pipeline");
assert.match(popupSource, /sendHarvestMessage[\s\S]*runDetectorWithReconnect\(false\)[\s\S]*Content script unavailable\. Next action: Reconnect Douyin Tab/, "content-script feature entrypoints must run detector reconnect before sending messages");
assert.match(popupSource, /GET_DOUYIN_PAGE_VIEWPORT/, "popup must request page viewport from the content script");
assert.match(popupSource, /setStatusSummary\(\{[\s\S]*Page:[\s\S]*Backend:[\s\S]*Detector:[\s\S]*Session:[\s\S]*Calibration:[\s\S]*Harvest:/, "production summary must expose only simplified core fields");
assert.doesNotMatch(popupSource, /setStatusSummary\(\{[\s\S]*"Backend reachable"/, "production summary must not include legacy backend-reachable label");
assert.doesNotMatch(popupSource, /setStatusSummary\(\{[\s\S]*"Current state"/, "production summary must not include current-state detail row");
assert.doesNotMatch(popupSource, /globalThis\.window\.innerWidth/, "popup must not use its own viewport width as Douyin page viewport");
assert.doesNotMatch(popupSource, /globalThis\.window\.innerHeight/, "popup must not use its own viewport height as Douyin page viewport");
assert.doesNotMatch(popupSource, /function getCurrentViewport/, "popup viewport fallback helper must be removed");
assert.match(contentScriptSource, /export function getDouyinPageViewport/, "content script must expose the Douyin page viewport helper");
assert.match(contentScriptSource, /source: "content_script"/, "content script viewport must identify its source");
assert.match(contentScriptSource, /viewport_source: viewport\.source/, "five-click calibration must store the content-script viewport source");
assert.match(contentScriptSource, /Step \$\{index \+ 1\}\/\$\{metrics\.length\}: Click \$\{labels\[metric\]\}/, "calibration overlay must show the current five-click step");
assert.match(contentScriptSource, /x_ratio: event\.clientX \/ Math\.max\(1, viewport\.width\)/, "calibrated point ratios must use content-script page viewport width");
assert.match(popupWorkflowSource, /pageRequiresModal/, "profile URLs must transition to modal_required instead of reusing stale probe PASS");
assert.doesNotMatch(popupSource, /hasSignificantViewportChange/, "Smart Capture must not block on popup viewport size comparisons");
assert.doesNotMatch(popupWorkflowSource, /no_saved_harvest_state[\s\S]*VIEWPORT_RECALIBRATION_MESSAGE/, "no_saved_harvest_state must not become a viewport warning");

assert.match(popupSource, /REUP_DOUYIN_START_RIGHT_RAIL_CALIBRATION/, "Start Calibration must send the content-script calibration message");
assert.match(popupSource, /chrome\.storage\.local\.get\(RIGHT_RAIL_CALIBRATION_KEY\)/, "popup calibration reads must use the canonical calibration key");
assert.match(popupSource, /chrome\.storage\.local\.remove\(LAST_PROBE_RESULT_KEY\)/, "missing or invalid calibration must clear stale probe state");
assert.match(popupSource, /Calibration: calibrationValidation\.status === "valid" \? "calibrated" : calibrationValidation\.status/, "popup summary must display validated calibration status");
assert.match(popupSource, /"Point count": `\$\{validation\.pointCount\}\/4`/, "Show Calibration must display four-point count");
assert.match(popupSource, /content_script_not_ready/, "Start Calibration must report content_script_not_ready when injection is unavailable");
assert.match(popupSource, /calibration_incomplete/, "incomplete calibration must not be treated as valid");
assert.match(contentScriptSource, /await saveRightRailCalibration\(calibration\)/, "four-click sequence must save the calibration after completion");
assert.match(contentScriptSource, /\["like_count", "comment_count", "favorite_count", "share_count"\] as const/, "Phase 13H calibration steps are exactly four points");
assert.match(contentScriptSource, /document\.addEventListener\("pointerdown", handleCalibrationPointerDown, true\)/, "Phase 13H captures pointerdown in document capture phase");
assert.match(contentScriptSource, /now - lastRecordedAt < 250/, "Phase 13H debounces duplicate pointer\/mouse\/click events from one physical click");
assert.match(contentScriptSource, /version: "phase13h_four_point_calibration"/, "Phase 13H saves the canonical four-point calibration contract version");
assert.match(contentScriptSource, /showToast\("Calibration saved: 4\/4 points\."\)/, "Phase 13H confirms final save after share_count");
assert.doesNotMatch(popupSource, /Next video point missing\. Recalibrate with five points\./, "normal workflow must not show the removed next-video-point error");
assert.doesNotMatch(contentScriptSource, /next_video_button"\] as const/, "production calibration overlay must not require a fifth next-video click");
assert.match(contentScriptSource, /RIGHT_RAIL_CALIBRATION_KEY = "douyinRightRailCalibration"/, "content script must save using the canonical calibration key");

assert.match(popupSource, /function guardedHybridNonNegativeNumber\(value: unknown\): number \| null \{\s*const numeric = typeof value === "number" \? value : typeof value === "string" && value\.trim\(\) !== "" \? Number\(value\) : Number\.NaN;\s*return Number\.isFinite\(numeric\) && numeric >= 0 \? numeric : null;\s*\}/s, "share_count normalization must treat zero as a valid non-negative persisted metric");
assert.match(popupSource, /function guardedHybridShareCountRead[\s\S]*item\.share_count[\s\S]*path: "share_count"[\s\S]*raw_dom_detail_metrics[\s\S]*path: "raw_dom_detail_metrics\.share_count"[\s\S]*metrics[\s\S]*path: "metrics\.share_count"[\s\S]*missing:share_count\|raw_dom_detail_metrics\.share_count\|metrics\.share_count/s, "share_count post-verify must read top-level and nested backend shapes with explicit provenance");
assert.match(popupSource, /shareCountExpectedCount !== required[\s\S]*shareCountMissingCount > 0[\s\S]*backend_share_count_missing[\s\S]*missingFields\.push\(`backend_share_count_missing:\$\{shareCountActual\.path\}`\)[\s\S]*share_count_read_path: shareCountActual\.path/s, "share_count mismatch must block with backend_share_count_missing provenance instead of generic share_count_missing");
assert.match(popupSource, /function compactStep[\s\S]*const cleanPassed = passed === true && cleanBlockers\.length === 0;[\s\S]*passed: cleanPassed/s, "compact guarded status must prevent passed=true from coexisting with blockers");
assert.match(popupSource, /const pilot10SourceCandidate = pilot10BatchSource \?\? compactGuardedPilotSourceForBatch\(pilotSource, 10\) \?\? compactGuardedPilot10SourceFromQueueCompletionMilestone\(queue10, queue10PostVerify, currentSourceRunId\);[\s\S]*const pilot10PostCandidate = pilot10BatchPostVerify \?\? compactGuardedPilotPostVerifyForBatch\(pilotPostVerify, 10\) \?\? compactGuardedPilot10PostVerifyFromQueueCompletionMilestone\(queue10, queue10PostVerify, pilot10SourceCandidate\);[\s\S]*const pilot10SourceChain = compactGuardedCurrentSource\(pilot10SourceCandidate, 10,[\s\S]*const pilot10PostChain = compactGuardedCurrentPostVerify\(pilot10PostCandidate, 10,[\s\S]*const pilot50SourceCandidate = pilot50BatchSource \?\? compactGuardedPilotSourceForBatch\(pilotSource, 50\);[\s\S]*const pilot50SourceChain = compactGuardedCurrentSource\(pilot50SourceCandidate, 50,[\s\S]*const pilot50PostChain = compactGuardedCurrentPostVerify\(pilot50PostCandidate, 50/s, "compact guarded status must read durable batch-scoped Pilot 10/50 source and post-verify candidates before gating so a later batch cannot invalidate an earlier batch milestone");
assert.match(popupSource, /type CompactGuardedStaleReason = "source_run_mismatch" \| "batch_size_mismatch" \| "parent_artifact_missing" \| "dependency_chain_mismatch";[\s\S]*function compactGuardedStaleDiagnostic[\s\S]*stale_artifact_ignored[\s\S]*ignored_artifact_reason[\s\S]*ignored_artifact_batch_size/s, "compact guarded status must report stale artifacts with explicit ignored reasons");
assert.match(popupSource, /function compactGuardedSourceParentRunId[\s\S]*run\.parent_source_run_id[\s\S]*run\.source_dry_run_id[\s\S]*run\.source_run_id[\s\S]*productionRequest\.run_id[\s\S]*captureContext\.capture_id[\s\S]*legacySourceRunId[\s\S]*function compactGuardedCurrentSource[\s\S]*const sourceRunId = compactGuardedSourceParentRunId\(source\);[\s\S]*source_run_mismatch/s, "compact guarded status must compare current dry-run source_run_id against canonical parent linkage, not pilot_run_id/source_pilot_run_id");
assert.match(popupSource, /const parentSourceRunId = compactGuardedSourceParentRunId\(source\);[\s\S]*run: \{[\s\S]*source_run_id: parentSourceRunId, parent_source_run_id: parentSourceRunId, source_dry_run_id: parentSourceRunId, source_pilot_run_id[\s\S]*source_artifact: \{[\s\S]*source_run_id: parentSourceRunId, parent_source_run_id: parentSourceRunId, source_dry_run_id: parentSourceRunId, pilot_run_id[\s\S]*pilot_post_verify_passed/s, "Pilot post-verify must carry parent dry-run source linkage while matching the pilot artifact by source_pilot_run_id");
assert.match(popupSource, /function compactGuardedCurrentQueue10[\s\S]*!pilot10Source \|\| !pilot10PostVerify \|\| !pilot10Passed[\s\S]*parent_artifact_missing[\s\S]*queuePilotRunId[\s\S]*dependency_chain_mismatch[\s\S]*verifiedIds\.every\(\(awemeId\) => pilotIds\.includes\(awemeId\)\)/s, "Queue Completion 10 current-chain validation must still require Pilot 10 source, post-verify, matching source_pilot_run_id, and exact aweme IDs");
assert.match(popupSource, /const currentQueue10 = queue10Chain\.artifact \?\? \(queue10PostVerifyMilestoneAuthorityPassed \? queue10 : null\);[\s\S]*const queue10CurrentReadinessBlockers = queue10RetryReady \? \[\] : compactDecisionBlockers\(currentQueue10\);[\s\S]*compactStep\("queue_completion_pilot_10", currentQueue10 != null && !queue10RetryReady, currentQueue10 != null, queue10CurrentReadinessBlockers[\s\S]*previous_attempt: queue10PreviousAttemptDiagnostics[\s\S]*\.\.\.queue10Chain\.diagnostic/s, "Queue Completion 10 compact status must accept validated milestone authority while separating retry-ready current blockers from stale previous-attempt diagnostics");
assert.match(popupSource, /const currentQueue10PostVerify = queue10PostVerifyChain\.artifact;[\s\S]*const queue10PostVerifyPassed = queue10PostVerifyMilestoneAuthorityPassed \|\| guardedHybridQueueCompletionPilot10PostVerifyPassed\(currentQueue10PostVerify\)[\s\S]*compactStep\("queue_completion_pilot_10_post_verify", queue10PostVerifyPassed, currentQueue10PostVerify != null/s, "Queue Completion 10 post-verify must depend on strict current-chain validation or validated downstream milestone authority");
assert.match(popupSource, /const pilot50PrerequisitesPassed = queue10PostVerifyMilestoneAuthorityPassed \|\| \(pilot10Passed && queue10PostVerifyPassed\);[\s\S]*const pilot50ProgressionDisplay: GuardedHybridPilot50ProgressionPrerequisite = pilot50PrerequisitesPassed \? \{ \.\.\.progression,[\s\S]*previous_pilot_requirement_satisfied: true,[\s\S]*blockers: \[\] \} : progression;[\s\S]*const pilot50SourceChain = compactGuardedCurrentSource\(pilot50SourceCandidate, 50, currentSourceRunId, pilot50ProgressionDisplay\.previous_pilot_requirement_satisfied === true \|\| pilot50MilestoneAuthorityPassed\)/s, "Pilot 50 compact source must accept Queue Completion 10 post-verify milestone authority after stale-protection validation");
assert.match(popupSource, /const queue50Passed = pilot50Passed && queue50ActionDecision\.verdict === "queue_completion_pilot_50_succeeded";[\s\S]*compactStep\("queue_completion_pilot_50", queue50Passed, queue50 != null && pilot50Passed, pilot50Passed \? compactDecisionBlockers\(queue50\) : \[\]/s, "Queue Completion 50 compact status must require a successful current-chain Pilot 50 post-verify and action verdict");
assert.match(popupSource, /if \(applyCompletion && canComplete\) \{\s*await chrome\.storage\.local\.set\(\{ \[HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_STORAGE_KEY\]: summary \}\);[\s\S]*HYBRID_START_COLLECTING_QUEUE_COMPLETION_PILOT_50_LATEST_COMPACT_STORAGE_KEY[\s\S]*guardedPipelineCompactLatestFromSummary\("queue_completion_pilot_50", summary\)[\s\S]*\}/s, "Queue Completion 50 must not persist latest full or compact artifacts unless Pilot 50 post-verify and completion preconditions truly pass");

// FULL_QUEUE_COMPLETION_DRY_RUN: read-only pre-flight test before enabling full queue completion. It must be read-only,
// keep full_queue_completion disabled and the exact_aweme_id_only strategy, drive coverage from a SCALE-INDEPENDENT
// live backend verify (Pilot 50 post-verify is informational only as a one-time mechanism-validation precondition),
// report the required counts/lists, surface the Pilot 50 gap as informational, and emit a go/no-go readiness verdict
// with blockers that are independent of the per-profile size N (50, 126, 1000, ...).
assert.match(popupSource, /const FULL_QUEUE_COMPLETION_DRY_RUN_LATEST_STORAGE_KEY = "fullQueueCompletionDryRunLatest";/, "popup must declare the full queue completion dry-run latest storage key");
assert.match(popupSource, /const FULL_QUEUE_COMPLETION_CHUNK_SIZE = 500;/, "popup must declare the chunked verify chunk size constant for the live backend verify (scale-independent)");
assert.match(popupSource, /const FULL_QUEUE_COMPLETION_VERIFY_ENDPOINT = "\/douyin-extension\/capture-inbox\/items\/verify";/, "popup must declare the live backend verify endpoint constant used by the chunked coverage authority");
assert.match(popupSource, /async function liveBackendVerifyAwemeIds\(awemeIds: string\[\], captureSessionId: string \| null\): Promise<LiveBackendVerifyResult> \{[\s\S]*for \(let offset = 0; offset < uniqueIds\.length; offset \+= FULL_QUEUE_COMPLETION_CHUNK_SIZE\) \{[\s\S]*await backendJson<Record<string, unknown>>\("POST", FULL_QUEUE_COMPLETION_VERIFY_ENDPOINT, payload[\s\S]*if \(\/401\|unauthori\[sz\]ed\|auth_required\/i\.test\(message\)\) \{[\s\S]*result\.auth_required = true/s, "popup must define the chunked, auth-aware liveBackendVerifyAwemeIds helper as the scale-independent COVERAGE authority");
assert.match(popupSource, /async function buildFullQueueCompletionDryRunSummary\(\): Promise<Record<string, unknown>> \{[\s\S]*const postVerifySource = await readGuardedHybridStartCollectingPilot50PostVerifySource\(\);[\s\S]*const verifiedAwemeIds = guardedHybridUniqueStrings\(postVerifySource\.verifiedAwemeIds\);[\s\S]*const pilot50PostVerifyPassed = postVerifySource\.blockers\.length === 0 && verifiedAwemeIds\.length === 50;[\s\S]*const liveVerify = await liveBackendVerifyAwemeIds\(queueAwemeIds, captureSessionIdResolved\);[\s\S]*summary_title: "FULL_QUEUE_COMPLETION_DRY_RUN"[\s\S]*read_only: true[\s\S]*production_state_mutation: "none"[\s\S]*backend_write_attempted: "no"[\s\S]*pilots_auto_rerun: "no"[\s\S]*match_strategy: "exact_aweme_id_only"/s, "full queue completion dry-run must keep Pilot 50 post-verify only as a mechanism-validation precondition and drive coverage from a LIVE chunked backend verify of the full queue (scale-independent)");
assert.match(popupSource, /verified_authority: \{[\s\S]*source: "live_backend_verify_against_capture_inbox_items_verify_endpoint"[\s\S]*mechanism_validation_source: "latest_passed_pilot_50_post_verify_artifact"[\s\S]*pilot_50_post_verify_passed: pilot50PostVerifyPassed[\s\S]*coverage_authority: "live_backend_verify"[\s\S]*coverage_is_scale_independent: true/s, "dry-run must report the SCALE-INDEPENDENT verified_authority block: live verify is the coverage authority, Pilot 50 post-verify is informational mechanism validation only");
assert.match(popupSource, /live_backend_verify: \{[\s\S]*endpoint: liveVerify\.endpoint[\s\S]*chunk_size: liveVerify\.chunk_size[\s\S]*chunk_count: liveVerify\.chunk_count[\s\S]*total_input_count: liveVerify\.total_input_count[\s\S]*found_count: liveVerify\.found_count[\s\S]*not_found_count: liveVerify\.not_found_count[\s\S]*auth_required: liveVerify\.auth_required[\s\S]*completed: liveVerify\.completed/s, "dry-run must report the live backend verify result block (chunk size/count, found/not_found counts, auth_required, completion) as the scale-independent coverage authority");
assert.match(popupSource, /backend_backed_coverage: \{[\s\S]*queue_total: queueTotal[\s\S]*backend_backed_count: backendBackedCount[\s\S]*backend_backed_pending_count: pendingBackendBacked\.length[\s\S]*not_backend_backed_pending_count: pendingNotBackendBacked\.length[\s\S]*not_backend_backed_pending_aweme_ids_sample: pendingNotBackendBacked\.slice\(0, NOT_BACKED_PENDING_SAMPLE_CAP\)/s, "dry-run must report backend_backed_coverage with queue_total / backend_backed_count and a sample of NOT-yet-backend-backed pending aweme_ids (reported, not gated)");
// 1. total queue items that would be completed; 2. exact-match accounting; 3. items outside the verified set.
assert.match(popupSource, /full_queue_completion_projection: \{[\s\S]*full_queue_total_items: totalQueueItems[\s\S]*would_be_completed_total_if_full_enabled: pendingBackendBacked\.length[\s\S]*would_be_completed_by_exact_verified_match: pendingMatchingVerified\.length[\s\S]*would_not_be_completed_no_exact_verified_match: pendingNotMatchingVerified\.length[\s\S]*\}/s, "dry-run projection must surface that full completion only marks pending items confirmed backend-backed by the live verify (scale-independent)");
assert.match(popupSource, /exact_aweme_id_match_accounting: \{\s*match_strategy: "exact_aweme_id_only"[\s\S]*pending_items_matching_verified_set_count: pendingMatchingVerified\.length[\s\S]*pending_items_not_matching_verified_set_count: pendingNotMatchingVerified\.length/s, "dry-run must account exact_aweme_id_only matches vs non-matches");
assert.match(popupSource, /items_outside_verified_pilot_50_set: \{[\s\S]*total_outside_verified_set_count: uniqueOutsideVerifiedIds\.length[\s\S]*outside_verified_set_aweme_ids_sample: uniqueOutsideVerifiedIds\.slice\(0, OUTSIDE_SET_SAMPLE_CAP\)[\s\S]*classification: "informational_field_not_readiness_blocker"/s, "dry-run must keep items_outside_verified_pilot_50_set as an INFORMATIONAL field, not a readiness blocker, at scale");
// 4. safety confirmation that nothing was mutated and full completion stays disabled.
assert.match(popupSource, /safety: \{\s*scan_profile_changed: "no"[\s\S]*full_queue_completion_enabled: false[\s\S]*queue_completion_match_strategy: "exact_aweme_id_only"[\s\S]*estimated_views_copied_to_view_count: "no"[\s\S]*backend_write_attempted: "no"[\s\S]*collect_job_mutated: collectJobMutated[\s\S]*queue_mutated: queueMutated[\s\S]*unrelated_backend_rows_touched: "no"[\s\S]*auto_backfill_performed: "no"/s, "dry-run safety block must confirm full_queue_completion stays disabled, exact strategy kept, no backend write, and collect_job/queue not mutated");
// 5. Pilot 50 gap detail (informational only at scale; NOT a readiness blocker).
assert.match(popupSource, /pilot_50_completion_gap: \{[\s\S]*gap_count: verifiedGapAwemeIds\.length[\s\S]*gap_reason_no_exact_backend_match_count: gapNoExactMatchCount[\s\S]*gap_reason_other_count: gapOtherCount[\s\S]*gap_aweme_ids: verifiedGapAwemeIds[\s\S]*gap_detail: verifiedGapDetail[\s\S]*classification: "informational_field_not_readiness_blocker"/s, "dry-run must list per-id Pilot 50 gap detail with reason categories and explicitly classify it as informational, NOT a readiness blocker");
assert.match(popupSource, /reason_category: "no_exact_backend_match"[\s\S]*reason_category: "other"/s, "dry-run gap detail must classify each missing id as no_exact_backend_match or other");
// SCALE-INDEPENDENT readiness blockers: foundational invariants + mechanism validation + clean live verify.
// Pilot 50 gap and items-outside-Pilot-50-set MUST NOT be readiness blockers at scale (only informational).
assert.match(popupSource, /const readinessBlockers = \[[\s\S]*pilot50PostVerifyPassed \? null : "pilot_50_post_verify_milestone_not_passed_mechanism_validation"[\s\S]*liveVerify\.auth_required \? "auth_required_complete_authentication_and_re_run_dry_run" : null[\s\S]*!liveVerify\.completed && !liveVerify\.auth_required \? "live_backend_verify_errored_re_run_dry_run" : null[\s\S]*\]\.filter/s, "dry-run readiness blockers must be SCALE-INDEPENDENT: foundational invariants, Pilot 50 mechanism-validation precondition, and clean live backend verify");
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildFullQueueCompletionDryRunSummary"), popupSource.indexOf("async function runGuardedHybridStartCollectingQueueCompletionPilot50(")), /pilot_50_queue_completion_gap_unresolved_40_of_50|full_queue_contains_pending_items_outside_verified_pilot_50_set_exact_match_cannot_complete/, "dry-run must NOT use the legacy scale-dependent gap or out-of-set blockers; those are now informational fields only");
assert.match(popupSource, /readiness: \{\s*verdict: readinessVerdict,\s*go: readinessBlockers\.length === 0,\s*blockers: readinessBlockers,\s*coverage_gate: "live_backend_verify_per_run"/s, "dry-run must emit a go/no-go readiness verdict with the blocker list and the live_backend_verify_per_run coverage gate");
assert.match(popupSource, /const readinessVerdict = readinessBlockers\.length === 0 \? "go_enable_full_queue_completion" : "no_go_keep_full_queue_completion_disabled";/, "dry-run readiness verdict must be go/no-go based on whether any blocker is present");
// the dry-run must not enable full completion, run normal Start Collecting, mutate the queue, or write to the backend.
// It MAY perform authenticated READ-ONLY backend verifies (chunked) via liveBackendVerifyAwemeIds; it must not mark items complete.
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildFullQueueCompletionDryRunSummary"), popupSource.indexOf("async function runGuardedHybridStartCollectingQueueCompletionPilot50(")), /writeWholeProfileHarvestState|runStartCollectingWorkflow|postBackendJson|full_queue_completion_enabled: true|capture_status: "complete"|status: "backend_verified"/s, "full queue completion dry-run must not write state, run normal Start Collecting, enable full completion, or mark queue items complete");
// export/copy wiring, DOM elements, and HTML controls for the dry-run.
assert.match(popupSource, /runFullQueueCompletionDryRunButton\?\.addEventListener\("click", \(\) => void exportFullQueueCompletionDryRunFromPopup\(\)\);[\s\S]*copyFullQueueCompletionDryRunButton\?\.addEventListener\("click", \(\) => void copyFullQueueCompletionDryRunFromPopup\(\)\);/, "popup must wire the full queue completion dry-run run/copy operator actions");
assert.match(popupSource, /const fullQueueCompletionDryRunPreviewEl = document\.querySelector<HTMLElement>\("#fullQueueCompletionDryRunPreview"\);/, "popup must resolve the full queue completion dry-run preview element");
assert.match(popupHtml, /id="runFullQueueCompletionDryRunButton"[\s\S]*Run Full Queue Completion Dry-Run[\s\S]*id="copyFullQueueCompletionDryRunButton"[\s\S]*Copy Full Queue Completion Dry-Run[\s\S]*id="fullQueueCompletionDryRunPreview"[\s\S]*FULL_QUEUE_COMPLETION_DRY_RUN not run yet\./, "popup must expose the full queue completion dry-run run/copy controls and a preview block");

// FULL_QUEUE_COMPLETION executor (FIX 2): operator-triggered, feature-flagged, chunked, resumable, idempotent.
// It does NOT collect missing videos; it only MARKS pending queue items confirmed backend-backed by exact aweme_id
// at run time as status="backend_verified", capture_status="complete". Items without a live backend record stay
// pending. Re-running never double-marks. On 401/auth_required it pauses safely and resumes after re-auth.
assert.match(popupSource, /const FULL_QUEUE_COMPLETION_PROGRESS_STORAGE_KEY = "fullQueueCompletionProgress";/, "popup must declare the resumable executor progress storage key");
assert.match(popupSource, /const FULL_QUEUE_COMPLETION_LATEST_STORAGE_KEY = "fullQueueCompletionLatest";/, "popup must declare the latest executor summary storage key");
assert.match(popupSource, /const FULL_QUEUE_COMPLETION_FEATURE_FLAG_STORAGE_KEY = "fullQueueCompletionEnabled";/, "popup must declare the operator-controlled feature flag storage key for the executor");
assert.match(popupSource, /async function fullQueueCompletionFeatureFlagEnabled\(\): Promise<boolean>/, "popup must expose a feature-flag reader for the operator-controlled executor enablement");
assert.match(popupSource, /type FullQueueCompletionProgressRecord = \{[\s\S]*schema_version: "full_queue_completion_progress\.v1"[\s\S]*status: "running" \| "completed" \| "paused_auth_required" \| "paused_error" \| "idle"[\s\S]*processed_chunk_count: number[\s\S]*backend_backed_count: number[\s\S]*marked_complete_count: number/s, "popup must define the resumable progress record with explicit status, processed/backend_backed/marked_complete counts");
assert.match(popupSource, /async function runFullQueueCompletion\(\): Promise<Record<string, unknown>> \{[\s\S]*const flagEnabled = await fullQueueCompletionFeatureFlagEnabled\(\);[\s\S]*if \(!flagEnabled\)[\s\S]*verdict: "blocked_feature_flag_disabled"[\s\S]*const pilot50PostVerifyPassedOnce = postVerifySource\.blockers\.length === 0 && postVerifySource\.verifiedAwemeIds\.length === 50;[\s\S]*if \(!pilot50PostVerifyPassedOnce\)[\s\S]*verdict: "blocked_mechanism_validation_not_passed"/s, "executor must hard-gate on the operator feature flag and on the one-time Pilot 50 post-verify mechanism-validation precondition");
assert.match(popupSource, /async function runFullQueueCompletion[\s\S]*for \(let offset = 0; offset < allQueueAwemeIds\.length; offset \+= FULL_QUEUE_COMPLETION_CHUNK_SIZE\) \{[\s\S]*const chunkResult = await liveBackendVerifyAwemeIds\(chunk, captureSessionId\);[\s\S]*if \(chunkResult\.auth_required\) \{[\s\S]*authRequired = true;[\s\S]*break;[\s\S]*\}[\s\S]*await writeFullQueueCompletionProgress\(\{[\s\S]*processed_chunk_count: chunkIndex/s, "executor must process the queue in resumable chunks of FULL_QUEUE_COMPLETION_CHUNK_SIZE, persist progress per chunk, and stop safely on 401/auth_required");
assert.match(popupSource, /async function runFullQueueCompletion[\s\S]*const nextQueue = queue\.map\(\(item\) => \{\s*if \(guardedHybridQueueCompletionItemIsComplete\(item\)\) return item;\s*if \(!backendBackedSet\.has\(item\.aweme_id\)\) \{[\s\S]*return item;\s*\}\s*markedCompleteCount \+= 1;\s*return \{[\s\S]*status: "backend_verified" as const,\s*capture_status: "complete" as const/s, "executor must be idempotent (skip already-complete items), exact_aweme_id_only (skip non-backend-backed items), and only mark backend-backed pending items complete");
assert.match(popupSource, /async function runFullQueueCompletion[\s\S]*const stateAfter = markedCompleteCount === 0\s*\? stateBefore\s*: await writeWholeProfileHarvestState\(chrome\.storage\.local, \{[\s\S]*queue: nextQueue/s, "executor must only persist a queue write when at least one item is marked complete (idempotent re-run is a no-op)");
assert.match(popupSource, /async function runFullQueueCompletion[\s\S]*safety: \{[\s\S]*queue_completion_match_strategy: "exact_aweme_id_only"[\s\S]*estimated_views_copied_to_view_count: "no"[\s\S]*backend_write_attempted: "no"[\s\S]*idempotent_re_run_safe: "yes"/s, "executor latest summary must keep all hard invariants: exact_aweme_id_only, estimated_views never copied to view_count, no backend write, idempotent re-run safe");
assert.match(popupSource, /runFullQueueCompletionButton\?\.addEventListener\("click", \(\) => void runFullQueueCompletionFromPopup\(\)\);[\s\S]*copyFullQueueCompletionLatestButton\?\.addEventListener\("click", \(\) => void copyFullQueueCompletionLatestFromPopup\(\)\);[\s\S]*resetFullQueueCompletionProgressButton\?\.addEventListener\("click", \(\) => void resetFullQueueCompletionProgressFromPopup\(\)\);/, "popup must wire the executor run/copy/reset operator actions");
assert.match(popupSource, /fullQueueCompletionEnabledInput\?\.addEventListener\("change", \(\) => void saveFullQueueCompletionEnabledFlag\(\)\);/, "popup must wire the executor feature-flag checkbox change handler");
assert.match(popupSource, /const fullQueueCompletionLatestPreviewEl = document\.querySelector<HTMLElement>\("#fullQueueCompletionLatestPreview"\);/, "popup must resolve the executor latest preview element");
assert.match(popupSource, /const fullQueueCompletionEnabledInput = document\.querySelector<HTMLInputElement>\("#fullQueueCompletionEnabled"\);/, "popup must resolve the executor feature-flag checkbox input");
assert.match(popupHtml, /id="fullQueueCompletionEnabled"[\s\S]*Enable Full Queue Completion[\s\S]*id="runFullQueueCompletionButton"[\s\S]*Run Full Queue Completion[\s\S]*id="copyFullQueueCompletionLatestButton"[\s\S]*Copy Full Queue Completion Latest[\s\S]*id="resetFullQueueCompletionProgressButton"[\s\S]*Reset Full Queue Completion Progress[\s\S]*id="fullQueueCompletionLatestPreview"[\s\S]*FULL_QUEUE_COMPLETION_LATEST not run yet\./, "popup must expose the executor feature-flag checkbox, run/copy/reset buttons, and a latest preview block");

// GUARDED_HYBRID_PILOT_50_BACKEND_EVIDENCE_DUMP: read-only authenticated backend read for the verified Pilot 50 aweme_ids
// against the current backend. Same shape as the beta evidence dump. It must be read-only, must not rerun the pipeline or
// auto-rerun pilots, must do scoped + unscoped lookups, emit per-id found yes/no with present fields and scoped_found_count /
// required, and produce a backend_backed vs artifact_only verdict so we can tell if Pilot 50 is backend-backed right now.
assert.match(popupSource, /async function buildGuardedHybridPilot50BackendEvidenceDump\(\): Promise<Record<string, unknown>> \{[\s\S]*const postVerifySource = await readGuardedHybridStartCollectingPilot50PostVerifySource\(\);[\s\S]*const verifiedAwemeIds = guardedHybridUniqueStrings\(postVerifySource\.verifiedAwemeIds\);[\s\S]*summary_title: "GUARDED_HYBRID_PILOT_50_BACKEND_EVIDENCE_DUMP"[\s\S]*read_only: true[\s\S]*storage_mutation: "none"[\s\S]*pipeline_stages_rerun: "none"[\s\S]*pilots_auto_rerun: "no"/s, "Pilot 50 backend evidence dump must derive the verified aweme_id set from the latest passed Pilot 50 post-verify source and declare a read-only, no-rerun, no-pilot-auto-rerun artifact");
assert.match(popupSource, /async function buildGuardedHybridPilot50BackendEvidenceDump[\s\S]*const scopedResponse = await backendJson<Record<string, unknown>>\("POST", verifyEndpoint, \{ aweme_ids: verifiedAwemeIds, capture_session_id: captureSessionId[\s\S]*const unscopedResponse = await backendJson<Record<string, unknown>>\("POST", verifyEndpoint, \{ aweme_ids: verifiedAwemeIds, limit/s, "Pilot 50 backend evidence dump must issue an authenticated scoped (capture_session_id) and unscoped (aweme_id only) backend read against the current backend");
assert.match(popupSource, /async function buildGuardedHybridPilot50BackendEvidenceDump[\s\S]*const perId = verifiedAwemeIds\.map\(\(awemeId\) => \{[\s\S]*found_scoped_by_capture_session_id: scopedItem != null[\s\S]*found_unscoped_aweme_id_only: unscopedItem != null[\s\S]*found: scopedItem != null \|\| unscopedItem != null \? "yes" : "no"[\s\S]*scoped_present_fields: presentFields\(scopedItem\)[\s\S]*unscoped_present_fields: presentFields\(unscopedItem\)/s, "Pilot 50 backend evidence dump must report per-id found yes/no plus present fields for scoped and unscoped lookups");
assert.match(popupSource, /async function buildGuardedHybridPilot50BackendEvidenceDump[\s\S]*scoped_found_count: scopedFoundCount[\s\S]*unscoped_found_count: unscopedFoundCount[\s\S]*any_found_count: anyFoundCount[\s\S]*required,[\s\S]*per_id: perId/s, "Pilot 50 backend evidence dump must emit scoped_found_count / unscoped_found_count / required alongside the per_id evidence");
assert.match(popupSource, /async function buildGuardedHybridPilot50BackendEvidenceDump[\s\S]*\} else if \(anyFoundCount === 0\) \{\s*verdict = "artifact_only";\s*\} else if \(scopedFoundCount >= required && required > 0\) \{\s*verdict = "backend_backed";/s, "Pilot 50 backend evidence dump verdict must be artifact_only when no verified id is found in the current backend and backend_backed when the scoped lookup finds all required ids");
assert.match(popupSource, /async function buildGuardedHybridPilot50BackendEvidenceDump[\s\S]*pilot_50_post_verify_passed_from_artifacts: pilot50PostVerifyPassedFromArtifacts[\s\S]*safety: \{\s*backend_write_attempted: "no"[\s\S]*pipeline_rerun: "no"[\s\S]*pilot_auto_rerun: "no"[\s\S]*full_queue_completion_enabled: false[\s\S]*queue_completion_match_strategy: "exact_aweme_id_only"[\s\S]*estimated_views_copied_to_view_count: "no"/s, "Pilot 50 backend evidence dump must distinguish artifact-pass from backend-backed and keep all safety invariants (no write, no rerun, full completion disabled, exact strategy, estimated_views unchanged)");
// the dump must be read-only: it may read via backendJson but must never write to the backend, rerun pipeline stages, or run a pilot.
assert.doesNotMatch(popupSource.slice(popupSource.indexOf("async function buildGuardedHybridPilot50BackendEvidenceDump"), popupSource.indexOf("async function exportGuardedHybridPilot50BackendEvidenceDumpFromPopup")), /chrome\.storage\.local\.set|writeWholeProfileHarvestState|runGuardedPipelineStep|runGuardedHybridStartCollectingPilotFromPopup|runStartCollectingWorkflow|full_modal_harvest|GUARDED_HYBRID_COLLECT_BETA_PRODUCTION_ENDPOINT/s, "Pilot 50 backend evidence dump must not mutate storage, rerun stages, run a pilot, or call the production write endpoint");
assert.match(popupSource, /exportGuardedHybridPilot50BackendEvidenceDumpButton\?\.addEventListener\("click", \(\) => void exportGuardedHybridPilot50BackendEvidenceDumpFromPopup\(\)\);[\s\S]*copyGuardedHybridPilot50BackendEvidenceDumpButton\?\.addEventListener\("click", \(\) => void copyGuardedHybridPilot50BackendEvidenceDumpFromPopup\(\)\);/, "popup must wire the Pilot 50 backend evidence dump export/copy operator actions");
assert.match(popupSource, /const guardedHybridPilot50BackendEvidenceDumpPreviewEl = document\.querySelector<HTMLElement>\("#guardedHybridPilot50BackendEvidenceDumpPreview"\);/, "popup must resolve the Pilot 50 backend evidence dump preview element");
assert.match(popupHtml, /id="exportGuardedHybridPilot50BackendEvidenceDumpButton"[\s\S]*Export Pilot 50 Backend Evidence Dump[\s\S]*id="copyGuardedHybridPilot50BackendEvidenceDumpButton"[\s\S]*Copy Pilot 50 Backend Evidence Dump[\s\S]*id="guardedHybridPilot50BackendEvidenceDumpPreview"[\s\S]*GUARDED_HYBRID_PILOT_50_BACKEND_EVIDENCE_DUMP not exported yet\./, "popup must expose the Pilot 50 backend evidence dump export/copy controls and a preview block");

console.log("popup workflow simplification tests passed");

function readyReasonSnapshot(calibration: RightRailCalibration, probe: FullModalHarvestProbeResult) {
  return {
    backendReachable: "yes",
    supportedDouyinTab: "yes",
    captureSessionId: "session-1",
    calibration,
    lastProbe: probe,
    harvestProgress: null,
    smartState: createSmartState({ current_state: "harvest_ready", latest_capture_session_id: "session-1" }),
    lastError: null,
    pageState: classifyDouyinPopupPage("https://www.douyin.com/user/MS4wLjABAAAAfixture?modal_id=7634"),
    contentScriptStatus: "ready",
    detectorStatus: "ready"
  } as const;
}


