import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

Object.defineProperty(globalThis, "chrome", {
  configurable: true,
  value: {
    runtime: {
      onInstalled: { addListener() {} },
      onMessage: { addListener() {} }
    },
    storage: {
      sync: { set: async () => undefined },
      onChanged: { addListener() {} }
    }
  }
});

const { __testCountSemanticsDiagnostics22C14Q, __testDerivePostProbeProductiveGate22C11B, __testDeriveRepositoryOverDisplayedDiagnostics22C14Q, __testNormalizeDouyinProfileIdentity22C14S, __testPaginatedScanAccountingDiagnostics22C14B, __testScanHealthVerdictDiagnostics22C14R, attachCdpAndReload, handleCdpEvent, handleMessage, postToBackend, startCdpHarvest, stopCdpHarvest } = await import("./background");
const { WHOLE_PROFILE_HARVEST_STATE_KEY, createWholeProfileHarvestIdleState } = await import("./wholeProfileHarvest/state");
const { createProfileTargetRepository, profileIdentifierFromUrl, resetProfileTargetRepositoryForTests } = await import("./wholeProfileHarvest/profileTargetRepository");

function installChromeForScanTest(options: {
  probeDiagnostics: Record<string, unknown>;
  scannerResponse: Record<string, unknown> | null;
  tabUrl?: string;
  backendProfileSummary?: Record<string, unknown>;
  paginatedResponses?: Array<Record<string, unknown> | null>;
  tailReconcileCandidates?: Array<Record<string, unknown> | string>;
  domProbeOk?: boolean;
  domProbeFailAfterFirst?: boolean;
}) {
  const values: Record<string, unknown> = {
    [WHOLE_PROFILE_HARVEST_STATE_KEY]: createWholeProfileHarvestIdleState("2026-05-13T04:02:18.860Z")
  };
  const sentMessages: Array<{ type?: string; expectedProfileVideoCount?: number | null; expected_profile_video_count?: number | null }> = [];
  let domProbeCount = 0;
  const backendRequests: string[] = [];
  const tabUrl = options.tabUrl ?? "https://www.douyin.com/user/MS4wLjABCD";
  Object.defineProperty(globalThis, "chrome", {
    configurable: true,
    value: {
      ...(globalThis as typeof globalThis & { chrome: Record<string, unknown> }).chrome,
      storage: {
        sync: {
          async get(key: string) {
            if (key === "apiBaseUrl") return { apiBaseUrl: "http://127.0.0.1:8000" };
            return {};
          },
          set: async () => undefined
        },
        local: {
          async get(key: string) {
            return { [key]: values[key] };
          },
          async set(items: Record<string, unknown>) {
            Object.assign(values, items);
          }
        }
      },
      tabs: {
        async get(tabId: number) {
          return { id: tabId, url: tabUrl, status: "complete" };
        },
        async query() {
          return [{ id: 777, url: tabUrl, status: "complete" }];
        },
        async sendMessage(_tabId: number, message: { type?: string; expectedProfileVideoCount?: number | null; expected_profile_video_count?: number | null }) {
          sentMessages.push(message);
          if (message.type === "DOUYIN_SCANNER_PING") {
            return {
              ok: true,
              content_script_supported_handlers: [
                "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B",
                "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING",
                "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B",
                ...(options.paginatedResponses ? ["DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B"] : [])
              ],
              content_script_version: "22C-11B"
            };
          }
          if (message.type === "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B") {
            return { ok: true, runtime_authority_snapshot: options.probeDiagnostics, diagnostics: options.probeDiagnostics };
          }
          if (message.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING") {
            return {
              ok: true,
              handler: "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B",
              scanner_available: true,
              scanner_function: "collectActiveWorksGridTargets22C11B",
              traceVersion: "22C-11B"
            };
          }
          if (message.type === "DOUYIN_PROFILE_DOM_PROBE_22C11B") {
            domProbeCount += 1;
            if (options.domProbeOk === false || (options.domProbeFailAfterFirst === true && domProbeCount > 1)) return { ok: false, reason: "dom_probe_unavailable_for_test", diagnostics: { error: "dom_probe_unavailable_for_test" } };
            const tailReconcileCandidates = options.tailReconcileCandidates ?? [];
            const tailReconcileCandidateIds = tailReconcileCandidates.map((candidate) => typeof candidate === "string" ? candidate : String(candidate.aweme_id ?? "")).filter(Boolean);
            return {
              ok: true,
              profile_dom_probe: {
                profileGridFound: true,
                videoAnchorCount: 2,
                modalIdLinkCount: 0,
                awemeIdCount: 2,
                gridCardCandidateCount: 2,
                scrollContainerFound: true,
                emptyProfileDetected: false,
                expectedProfileVideoCount: options.probeDiagnostics.expected_profile_video_count ?? null,
                expectedProfileVideoCountRawText: options.probeDiagnostics.expected_profile_video_count_raw_text ?? null,
                expectedProfileVideoCountSelector: "button",
                tail_reconcile_candidates: tailReconcileCandidates,
                tail_reconcile_candidate_ids: tailReconcileCandidateIds,
                videoAnchors: options.probeDiagnostics.videoAnchors ?? [],
                awemeIds: options.probeDiagnostics.awemeIds ?? []
              },
              diagnostics: {
                tail_reconcile_candidates: tailReconcileCandidates,
                tail_reconcile_candidate_ids: tailReconcileCandidateIds,
                tail_reconcile_dom_candidate_count: tailReconcileCandidates.length,
                videoAnchors: options.probeDiagnostics.videoAnchors ?? [],
                awemeIds: options.probeDiagnostics.awemeIds ?? []
              }
            };
          }
          if (message.type === "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B") {
            const next = options.paginatedResponses?.shift();
            return next ?? { ok: false, reason: "paginated_response_missing", verified_targets: [], verified_target_details: [], diagnostics: { scan_job_last_error: "paginated_response_missing" } };
          }
          if (message.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B") {
            return options.scannerResponse;
          }
          return { ok: false, error: `unexpected:${String(message.type)}` };
        }
      },
      scripting: { async executeScript() { return []; } }
    }
  });
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async (url: string) => {
      backendRequests.push(url);
      if (url.includes("/douyin-extension/capture-inbox/profile-items")) {
        return {
          ok: true,
          status: 200,
          async json() {
            return options.backendProfileSummary ?? { profile_identifier: "MS4wLjABCD", normalized_profile_url: tabUrl, profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 0, counts: { captured: 0, ready: 0, dup: 0, fail: 0 }, items: [] };
          }
        };
      }
      return {
        ok: true,
        status: 200,
        async json() {
          return { ok: true };
        }
      };
    }
  });
  return { values, sentMessages, backendRequests };
}

async function waitForScanFinalization(values: Record<string, unknown>, timeoutMs = 3000): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt <= timeoutMs) {
    const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState> | undefined;
    const diagnostics = state?.debug?.last_response_summary;
    const result = diagnostics && typeof diagnostics === "object"
      ? (diagnostics as Record<string, unknown>).lastScannerResult
      : null;
    if (result === "success" || result === "incomplete" || result === "failed" || result === "completed_with_warning") {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

async function waitForScanJobStatus(values: Record<string, unknown>, status: string, timeoutMs = 3000): Promise<ReturnType<typeof createWholeProfileHarvestIdleState>> {
  const startedAt = Date.now();
  while (Date.now() - startedAt <= timeoutMs) {
    const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState> | undefined;
    if (state?.scan_job?.status === status) return state;
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  return values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
}

{
  assert.equal(__testDerivePostProbeProductiveGate22C11B(null, { profile_dom_probe_status: "completed", profile_grid_ready: true, aweme_id_count: 28 }).gate, "productive");
  assert.equal(__testDerivePostProbeProductiveGate22C11B(null, { profile_dom_probe_status: "completed", video_anchor_count: 28 }).gate, "productive");
  assert.equal(__testDerivePostProbeProductiveGate22C11B(null, { profile_dom_probe_status: "completed", grid_card_candidate_count: 78 }).gate, "productive");
  assert.equal(__testDerivePostProbeProductiveGate22C11B({ emptyProfileDetected: true }, {}).gate, "empty_profile");
  assert.equal(__testDerivePostProbeProductiveGate22C11B({ checkpointDetected: true }, {}).gate, "blocked");
}

{
  const fullMatchSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 996, displayedProfileCountSource: "active_works_tab_dom_text", displayedProfileCountRawText: "作品 996", apiRawCount: 996, apiUniqueCount: 996, apiHasMoreFinal: false, collectableCount: 996, persistedCount: 996, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(fullMatchSemantics.count_semantics_status, "full_match");
  assert.equal(fullMatchSemantics.count_semantics_reason, "displayed_count_matches_persisted_count");
  assert.equal(fullMatchSemantics.scan_health_verdict, "ready_full_match");
  assert.equal(fullMatchSemantics.scan_health_required_user_action, "usable_no_retry_needed_continue_to_collect");
  assert.equal(fullMatchSemantics.displayed_profile_count, 996);
  assert.equal(fullMatchSemantics.api_raw_count, 996);
  assert.equal(fullMatchSemantics.api_unique_count, 996);
  assert.equal(fullMatchSemantics.collectable_count, 996);
  assert.equal(fullMatchSemantics.persisted_count, 996);
  assert.equal(fullMatchSemantics.final_cumulative_collectable_count, 996);
  assert.equal(fullMatchSemantics.final_display_authority, "collectable_count");
  assert.equal(fullMatchSemantics.final_header_count, 996);
  assert.equal(fullMatchSemantics.final_counter_count, 996);
  assert.equal(fullMatchSemantics.header_counter_authority_match, "yes");

  const displayedMismatchSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 996, apiRawCount: 991, apiUniqueCount: 991, apiHasMoreFinal: false, collectableCount: 991, persistedCount: 991, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(displayedMismatchSemantics.count_semantics_status, "completed_with_displayed_count_mismatch");
  assert.equal(displayedMismatchSemantics.count_semantics_reason, "displayed_count_not_fully_collectable");
  assert.equal(displayedMismatchSemantics.scan_health_verdict, "ready_displayed_count_mismatch_explained");
  assert.equal(displayedMismatchSemantics.unavailable_or_unlisted_count, 5);

  const exactObservedSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 475, apiRawCount: 475, apiUniqueCount: 475, apiHasMoreFinal: false, collectableCount: 475, persistedCount: 475, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(exactObservedSemantics.count_semantics_status, "full_match");
  assert.equal(exactObservedSemantics.count_semantics_reason, "displayed_count_matches_persisted_count");
  assert.equal(exactObservedSemantics.scan_health_verdict, "ready_full_match");

  const undercountObservedSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 475, apiRawCount: 472, apiUniqueCount: 472, apiHasMoreFinal: false, collectableCount: 472, persistedCount: 472, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(undercountObservedSemantics.count_semantics_status, "completed_with_displayed_count_mismatch");
  assert.equal(undercountObservedSemantics.count_semantics_reason, "displayed_count_not_fully_collectable");
  assert.equal(undercountObservedSemantics.unavailable_or_unlisted_count, 3);

  const validatedOvercountSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 475, apiRawCount: 478, apiUniqueCount: 478, apiHasMoreFinal: false, collectableCount: 478, persistedCount: 478, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0, overDisplayedSameProfileValidated: "yes", overDisplayedExtraIdsSample: ["7634192733514501476", "7634192733514501477", "7634192733514501478"], overDisplayedExtraIdsExact: ["7634192733514501476", "7634192733514501477", "7634192733514501478"], overDisplayedExtraItemsExact: ["7634192733514501476", "7634192733514501477", "7634192733514501478"].map((aweme_id, index) => ({ aweme_id, page_index: 0, raw_index: 475 + index, accepted_index: 475 + index, source_endpoint: "/aweme/v1/web/aweme/post/", source_cursor: 0, same_profile_validated: "yes", source_profile_identifier: "MS4wLjOVERCOUNT", target_profile_identifier: "MS4wLjOVERCOUNT", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" })), overDisplayedItemizedReasonSummary: "7634192733514501476:valid_same_profile_item_hidden_from_visible_count_basis | 7634192733514501477:valid_same_profile_item_hidden_from_visible_count_basis | 7634192733514501478:valid_same_profile_item_hidden_from_visible_count_basis", overDisplayedExtraSource: "active_profile_post_api_pagination", overDisplayedExtraCount: 3, extraIdsSameProfileMatchCount: 3, extraIdsProfileMismatchCount: 0, overDisplayedValidationStatus: "validated_same_profile", overDisplayedReason: "itemized_valid_same_profile_api_items_beyond_visible_count", apiResponseProfileIdentifier: "MS4wLjOVERCOUNT", requestedProfileIdentifier: "MS4wLjOVERCOUNT", repositoryProfileIdentifier: "MS4wLjOVERCOUNT", repositoryExistingBeforeTotal: 0, repositoryExistingSameProfileTotal: 0, repositoryExistingOtherProfileTotal: 0, templateCacheProfileMatch: "yes", directApiTemplateProfileMatch: "yes" });
  assert.equal(validatedOvercountSemantics.count_semantics_status, "completed_with_api_over_displayed_count");
  assert.equal(validatedOvercountSemantics.count_semantics_reason, "itemized_valid_same_profile_api_items_beyond_visible_count");
  assert.equal(validatedOvercountSemantics.scan_health_verdict, "ready_api_over_displayed_count");
  assert.equal(validatedOvercountSemantics.over_displayed_count, 3);
  assert.equal(validatedOvercountSemantics.over_displayed_validation_status, "validated_same_profile");
  assert.deepEqual(validatedOvercountSemantics.over_displayed_extra_ids_exact, ["7634192733514501476", "7634192733514501477", "7634192733514501478"]);

  const emptyProofClaimedReadyOvercountSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 475, apiRawCount: 478, apiUniqueCount: 478, apiHasMoreFinal: false, collectableCount: 478, persistedCount: 478, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0, overDisplayedSameProfileValidated: "yes", overDisplayedExtraIdsExact: [], overDisplayedExtraItemsExact: [], overDisplayedItemizedReasonSummary: null, overDisplayedExtraCount: 3, extraIdsSameProfileMatchCount: 3, extraIdsProfileMismatchCount: 0, overDisplayedValidationStatus: "validated_same_profile", overDisplayedReason: "itemized_valid_same_profile_api_items_beyond_visible_count" });
  assert.equal(emptyProofClaimedReadyOvercountSemantics.count_semantics_status, "overcollected_needs_validation");
  assert.equal(emptyProofClaimedReadyOvercountSemantics.scan_health_verdict, "failed_or_warning_overcollection_validation_needed");
  assert.equal(emptyProofClaimedReadyOvercountSemantics.over_displayed_validation_status, "needs_validation");
  assert.equal(emptyProofClaimedReadyOvercountSemantics.over_displayed_same_profile_validated, "no");
  assert.equal(emptyProofClaimedReadyOvercountSemantics.ready_overdisplay_without_itemized_proof, "yes");

  const emptyProofClaimedReadyHealth = __testScanHealthVerdictDiagnostics22C14R({ count_semantics_status: "completed_with_api_over_displayed_count", count_semantics_reason: "itemized_valid_same_profile_api_items_beyond_visible_count", over_displayed_count: 3, over_displayed_validation_status: "needs_validation", over_displayed_same_profile_validated: "no", over_displayed_extra_ids_exact: [], over_displayed_extra_items_exact: [], over_displayed_itemized_reason_summary: null });
  assert.equal(emptyProofClaimedReadyHealth.scan_health_verdict, "failed_or_warning_overcollection_validation_needed", "scan health must not trust a ready overdisplay status without exact itemized proof");
  assert.equal(emptyProofClaimedReadyHealth.ready_overdisplay_without_itemized_proof, "yes");

  const emptyProofClaimedOutsideProfileSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 3161, apiRawCount: 3164, apiUniqueCount: 3164, apiHasMoreFinal: false, collectableCount: 3164, persistedCount: 3164, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0, overDisplayedSameProfileValidated: "no", overDisplayedExtraIdsExact: [], overDisplayedExtraItemsExact: [], overDisplayedItemizedReasonSummary: null, overDisplayedExtraSource: null, overDisplayedExtraCount: 3, extraIdsSameProfileMatchCount: 0, extraIdsProfileMismatchCount: 1, overDisplayedValidationStatus: "outside_profile_detected", overDisplayedValidationFailureReason: "over_displayed_extra_item_profile_identifier_mismatch" });
  assert.equal(emptyProofClaimedOutsideProfileSemantics.count_semantics_status, "overcollected_needs_validation", "outside-profile count semantics must be impossible without exact offending item proof");
  assert.equal(emptyProofClaimedOutsideProfileSemantics.count_semantics_reason, "over_displayed_itemized_validation_missing");
  assert.equal(emptyProofClaimedOutsideProfileSemantics.scan_health_verdict, "failed_or_warning_overcollection_validation_needed");
  assert.equal(emptyProofClaimedOutsideProfileSemantics.scan_health_verdict_reason, "over_displayed_itemized_validation_missing");
  assert.equal(emptyProofClaimedOutsideProfileSemantics.over_displayed_validation_status, "needs_validation");
  assert.deepEqual(emptyProofClaimedOutsideProfileSemantics.over_displayed_outside_profile_offending_aweme_ids, []);
  assert.match(String(emptyProofClaimedOutsideProfileSemantics.known_contradictions_to_debug), /outside_profile_verdict_without_itemized_offenders/);

  const emptyProofClaimedOutsideProfileHealth = __testScanHealthVerdictDiagnostics22C14R({ count_semantics_status: "failed_overcollection_outside_profile", count_semantics_reason: "over_displayed_extra_item_profile_identifier_mismatch", over_displayed_count: 3, over_displayed_validation_status: "outside_profile_detected", over_displayed_same_profile_validated: "no", over_displayed_extra_ids_exact: [], over_displayed_extra_items_exact: [], over_displayed_itemized_reason_summary: null, over_displayed_validation_failure_reason: "over_displayed_extra_item_profile_identifier_mismatch" });
  assert.equal(emptyProofClaimedOutsideProfileHealth.scan_health_verdict, "failed_or_warning_overcollection_validation_needed", "scan health must downgrade direct outside-profile status without exact offender proof");
  assert.equal(emptyProofClaimedOutsideProfileHealth.scan_health_verdict_reason, "over_displayed_itemized_validation_missing");
  assert.equal(emptyProofClaimedOutsideProfileHealth.outside_profile_verdict_without_itemized_offenders, "yes");

  const unvalidatedOvercountSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 475, apiRawCount: 478, apiUniqueCount: 478, apiHasMoreFinal: false, collectableCount: 478, persistedCount: 478, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0, overDisplayedSameProfileValidated: "no", repositoryExistingOtherProfileTotal: 0, templateCacheProfileMatch: "unknown", directApiTemplateProfileMatch: "unknown" });
  assert.equal(unvalidatedOvercountSemantics.count_semantics_status, "overcollected_needs_validation");
  assert.equal(unvalidatedOvercountSemantics.count_semantics_reason, "over_displayed_itemized_validation_missing");
  assert.equal(unvalidatedOvercountSemantics.scan_health_verdict, "failed_or_warning_overcollection_validation_needed");
  assert.equal(unvalidatedOvercountSemantics.over_displayed_count, 3);
  assert.equal(unvalidatedOvercountSemantics.over_displayed_validation_status, "needs_validation");

  const outsideProfileOvercountSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 475, apiRawCount: 478, apiUniqueCount: 478, apiHasMoreFinal: false, collectableCount: 478, persistedCount: 478, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0, overDisplayedSameProfileValidated: "no", overDisplayedExtraIdsExact: ["7634192733514501476", "7634192733514501477", "7634192733514501478"], overDisplayedExtraItemsExact: [{ aweme_id: "7634192733514501476", profile_identifier: "MS4wLjREQUESTED", requested_profile_identifier: "MS4wLjREQUESTED", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" }, { aweme_id: "7634192733514501477", profile_identifier: "MS4wLjOTHER", requested_profile_identifier: "MS4wLjREQUESTED", item_reason: "possible_cross_profile_contamination" }, { aweme_id: "7634192733514501478", profile_identifier: "MS4wLjREQUESTED", requested_profile_identifier: "MS4wLjREQUESTED", item_reason: "valid_same_profile_item_hidden_from_visible_count_basis" }], overDisplayedItemizedReasonSummary: "7634192733514501476:valid_same_profile_item_hidden_from_visible_count_basis | 7634192733514501477:possible_cross_profile_contamination | 7634192733514501478:valid_same_profile_item_hidden_from_visible_count_basis", overDisplayedExtraCount: 3, extraIdsSameProfileMatchCount: 2, extraIdsProfileMismatchCount: 1, overDisplayedValidationStatus: "outside_profile_detected", overDisplayedValidationFailureReason: "over_displayed_extra_item_profile_identifier_mismatch", requestedProfileIdentifier: "MS4wLjREQUESTED", apiResponseProfileIdentifier: "MS4wLjREQUESTED", templateCacheProfileMatch: "no", directApiTemplateProfileMatch: "no" });
  assert.equal(outsideProfileOvercountSemantics.count_semantics_status, "failed_overcollection_outside_profile");
  assert.equal(outsideProfileOvercountSemantics.scan_health_verdict, "failed_overcollection_outside_profile");
  assert.equal(outsideProfileOvercountSemantics.over_displayed_validation_status, "outside_profile_detected");
  assert.equal(outsideProfileOvercountSemantics.over_displayed_validation_failure_reason, "over_displayed_extra_item_profile_identifier_mismatch");
  assert.deepEqual(outsideProfileOvercountSemantics.over_displayed_extra_ids_exact, ["7634192733514501476", "7634192733514501477", "7634192733514501478"]);
  assert.deepEqual(outsideProfileOvercountSemantics.over_displayed_outside_profile_offending_aweme_ids, ["7634192733514501477"], "outside-profile verdict must list exact offending aweme IDs");

  const repositoryOvercountRecords = ["7634192733514501476", "7634192733514501477", "7634192733514501478"].map((awemeId, index) => ({
    profile_identifier: "MS4wLjOVERCOUNT",
    aweme_id: awemeId,
    sequence: 475 + index,
    source_url: `https://www.douyin.com/video/${awemeId}`,
    status: "new",
    capture_status: "pending",
    attempts: 0,
    updated_at: "2026-05-13T04:02:18.860Z",
    queue_item: { aweme_id: awemeId, status: "new", capture_status: "pending", attempts: 0, source_url: `https://www.douyin.com/video/${awemeId}`, profile_identifier: "MS4wLjOVERCOUNT" },
    target_detail: { aweme_id: awemeId, profile_identifier: "MS4wLjOVERCOUNT", profile_url: "https://www.douyin.com/user/MS4wLjOVERCOUNT", source_url: `https://www.douyin.com/video/${awemeId}` }
  }));
  const repositoryValidatedOvercount = __testDeriveRepositoryOverDisplayedDiagnostics22C14Q(repositoryOvercountRecords as never, { displayedProfileCount: 475, persistedCount: 478, requestedProfileIdentifier: "MS4wLjOVERCOUNT", apiResponseProfileIdentifier: "MS4wLjOVERCOUNT", existingDiagnostics: { api_has_more_final: false, api_raw_count: 478, api_unique_count: 478, collectable_count: 478 }, source: "profile_target_repository_ordered_final_targets" });
  assert.deepEqual(repositoryValidatedOvercount.over_displayed_extra_ids_exact, ["7634192733514501476", "7634192733514501477", "7634192733514501478"], "repository final-order overcount must return the final persisted ordered IDs");
  assert.equal(repositoryValidatedOvercount.over_displayed_extra_source, "profile_target_repository_ordered_final_targets");
  assert.equal(repositoryValidatedOvercount.over_displayed_validation_status, "needs_validation");
  assert.equal(repositoryValidatedOvercount.count_semantics_status, "overcollected_needs_validation");
  assert.equal(repositoryValidatedOvercount.count_semantics_reason, "over_displayed_itemized_validation_missing");
  assert.equal(repositoryValidatedOvercount.scan_health_verdict, "failed_or_warning_overcollection_validation_needed");

  const repositoryUnvalidatedOvercount = __testDeriveRepositoryOverDisplayedDiagnostics22C14Q(repositoryOvercountRecords.map((record) => ({ ...record, queue_item: { aweme_id: record.aweme_id, status: "new", capture_status: "pending", attempts: 0, source_url: record.source_url }, target_detail: { aweme_id: record.aweme_id, source_url: record.source_url } })) as never, { displayedProfileCount: 475, persistedCount: 478, requestedProfileIdentifier: "MS4wLjOVERCOUNT", apiResponseProfileIdentifier: "MS4wLjOVERCOUNT", existingDiagnostics: { api_has_more_final: false, api_raw_count: 478, api_unique_count: 478, collectable_count: 478 }, source: "profile_target_repository_ordered_final_targets" });
  assert.deepEqual(repositoryUnvalidatedOvercount.over_displayed_extra_ids_exact, ["7634192733514501476", "7634192733514501477", "7634192733514501478"], "missing same-profile proof must still expose exact repository IDs");
  assert.equal(repositoryUnvalidatedOvercount.over_displayed_validation_status, "needs_validation");
  assert.equal(repositoryUnvalidatedOvercount.count_semantics_status, "overcollected_needs_validation");
  assert.match(String(repositoryUnvalidatedOvercount.over_displayed_itemized_reason_summary), /profile_identity_not_proven/);

  const buildPaginatedOverDisplayAccounting = (orderedAcceptedTargets: Array<Record<string, unknown>>, includeLedger = true) => ({ rawItemsTotal: orderedAcceptedTargets.length, rawAwemeIdsTotal: orderedAcceptedTargets.length, uniqueAwemeIds: new Set(orderedAcceptedTargets.map((target) => String(target.awemeId))), uniqueAwemeIdOrder: orderedAcceptedTargets.map((target) => String(target.awemeId)), orderedAcceptedTargets, acceptedTargetLedger: includeLedger ? orderedAcceptedTargets.map((target, index) => ({ aweme_id: String(target.awemeId), accepted_index: index, page_index: Number(target.pageIndexFound ?? Math.floor(index / 20)), raw_index_in_page: Number(target.rawIndexFound ?? index % 20), source: "active_profile_post_api", endpoint_path: String(target.sourceEndpoint ?? "/aweme/v1/web/aweme/post/"), request_cursor: target.sourceCursor as string | number | null ?? null, response_cursor: target.sourceCursor as string | number | null ?? null, request_profile_identifier: "MS4wLjLIVE", request_sec_uid: "MS4wLjLIVE", api_template_profile_identifier: String(target.sourceProfileIdentifier ?? "MS4wLjLIVE"), api_template_sec_uid: String(target.sourceProfileIdentifier ?? "MS4wLjLIVE"), author_uid: target.authorId as string | null ?? null, author_sec_uid: target.authorSecUid as string | null ?? null, author_unique_id: target.authorUniqueId as string | null ?? null, raw_profile_match_evidence: target.sameProfileValidationStatus === "outside_profile_detected" || target.sameProfileValidationStatus === "outside_profile" ? ["author_sec_uid_mismatch_requested_profile_sec_uid"] : target.sameProfileValidationStatus === "missing_evidence" || target.sameProfileValidationStatus === "insufficient_evidence" ? ["author_sec_uid_missing"] : ["author_sec_uid_matches_requested_profile_sec_uid"], same_profile_validation_status: target.sameProfileValidationStatus === "outside_profile_detected" || target.sameProfileValidationStatus === "outside_profile" ? "outside_profile" : target.sameProfileValidationStatus === "missing_evidence" || target.sameProfileValidationStatus === "insufficient_evidence" ? "insufficient_evidence" : "same_profile", same_profile_validation_reason: String(target.sameProfileValidationReason ?? "author_sec_uid_matches_requested_profile_sec_uid"), same_profile_missing_evidence: Array.isArray(target.sameProfileMissingEvidence) ? target.sameProfileMissingEvidence : [] })) : undefined, sameProfileEvidenceByAwemeId: new Map(orderedAcceptedTargets.map((target) => [String(target.awemeId), target])), requestedProfileIdentifier: "MS4wLjLIVE", apiResponseProfileIdentifier: "MS4wLjLIVE", targetsReturnedToBackgroundTotal: orderedAcceptedTargets.length, backgroundTargetsReceivedTotal: orderedAcceptedTargets.length, backgroundTargetsAfterValidationTotal: orderedAcceptedTargets.length, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: 0, repositoryWriteInputCount: orderedAcceptedTargets.length, repositoryNewInsertedTotal: orderedAcceptedTargets.length, repositoryDuplicateExistingTotal: 0, repositoryWriteTotalAfter: orderedAcceptedTargets.length, perPageRawCounts: [orderedAcceptedTargets.length], perPageRawAwemeIdCounts: [orderedAcceptedTargets.length], perPageReturnedTargetCounts: [orderedAcceptedTargets.length], perPageUniqueNewCounts: [orderedAcceptedTargets.length], perPageDuplicateCounts: [0], perPageCursorValues: [null], perPageCursorPresentFlags: [false], perPageHasMoreFlags: [false], perPageStatusCodes: [200], perPageParserRoutes: ["aweme_list"], perPagePersistedTotals: [orderedAcceptedTargets.length], firstPageRawCount: orderedAcceptedTargets.length, lastPageRawCount: orderedAcceptedTargets.length, lastPageAcceptedCount: orderedAcceptedTargets.length, lastPagePersistedDelta: orderedAcceptedTargets.length, finalHasMore: false, finalCursorPresent: false, finalStatusCode: 200 });
  const liveBoundaryTargets = Array.from({ length: 3163 }, (_, index) => ({ awemeId: `76341927335145${String(index).padStart(8, "0")}`, profileUrl: "https://www.douyin.com/user/MS4wLjLIVE", profileIdentifier: "MS4wLjLIVE", pageIndexFound: Math.floor(index / 20), requestIndexFound: Math.floor(index / 20) + 1, rawIndexFound: index % 20, sourceEndpoint: "/aweme/v1/web/aweme/post/", sourceCursor: index, sourceProfileIdentifier: "MS4wLjLIVE", targetProfileIdentifier: "MS4wLjLIVE", authorId: `uid-${index}`, authorSecUid: "MS4wLjLIVE", authorUniqueId: "live_author", requestedProfileSecUid: "MS4wLjLIVE", sameProfileValidationStatus: "same_profile_validated", sameProfileMissingEvidence: [], desc: null, createTime: null, sameProfileValidated: "yes", sameProfileValidationReason: "author_sec_uid_matches_requested_profile_sec_uid", isPinnedCandidate: "unknown", isSpecialTabCandidate: "unknown", appearsInDomGrid: "unknown", appearsInVisibleProfileCountBasis: "unknown", itemReason: "valid_same_profile_item_hidden_from_visible_count_basis", acceptedIndex: index, sourceTemplateId: "template-live" }));
  const liveBoundaryDiagnostics = __testPaginatedScanAccountingDiagnostics22C14B(buildPaginatedOverDisplayAccounting(liveBoundaryTargets) as never, 3160, 3163);
  assert.equal(liveBoundaryDiagnostics.over_displayed_count, 3);
  assert.equal(liveBoundaryDiagnostics.over_displayed_extra_source, "accepted_target_ledger_boundary_tail");
  assert.deepEqual(liveBoundaryDiagnostics.over_displayed_extra_ids_exact, liveBoundaryTargets.slice(3160, 3163).map((target) => target.awemeId));
  assert.equal((liveBoundaryDiagnostics.over_displayed_extra_items_exact as Array<Record<string, unknown>>).length, 3);
  assert.equal((liveBoundaryDiagnostics.over_displayed_extra_items_exact as Array<Record<string, unknown>>)[0]?.accepted_index, 3160);
  assert.equal((liveBoundaryDiagnostics.over_displayed_extra_items_exact as Array<Record<string, unknown>>)[0]?.raw_index_in_page, 0);
  assert.equal(liveBoundaryDiagnostics.over_displayed_itemized_reason_summary, "Derived from acceptedTargetLedger.slice(displayed_profile_count, persisted_count)");
  assert.equal(liveBoundaryDiagnostics.over_displayed_validation_status, "validated_same_profile");
  assert.equal(liveBoundaryDiagnostics.scan_health_verdict, "ready_api_over_displayed_count");

  const live3161BoundaryTargets = Array.from({ length: 3164 }, (_, index) => ({ ...liveBoundaryTargets[Math.min(index, liveBoundaryTargets.length - 1)], awemeId: `76341927335146${String(index).padStart(8, "0")}`, acceptedIndex: index, pageIndexFound: Math.floor(index / 20), requestIndexFound: Math.floor(index / 20) + 1, rawIndexFound: index % 20, sourceCursor: index }));
  const live3161BoundaryDiagnostics = __testPaginatedScanAccountingDiagnostics22C14B(buildPaginatedOverDisplayAccounting(live3161BoundaryTargets) as never, 3161, 3164);
  assert.equal(live3161BoundaryDiagnostics.over_displayed_count, 3);
  assert.equal(live3161BoundaryDiagnostics.over_displayed_extra_source, "accepted_target_ledger_boundary_tail");
  assert.deepEqual(live3161BoundaryDiagnostics.over_displayed_extra_ids_exact, live3161BoundaryTargets.slice(3161, 3164).map((target) => target.awemeId));
  assert.equal((live3161BoundaryDiagnostics.over_displayed_extra_items_exact as Array<Record<string, unknown>>).length, 3);
  assert.equal((live3161BoundaryDiagnostics.over_displayed_extra_items_exact as Array<Record<string, unknown>>)[0]?.accepted_index, 3161);
  assert.equal(live3161BoundaryDiagnostics.accepted_target_ledger_present, "yes");
  assert.equal(live3161BoundaryDiagnostics.accepted_target_ledger_count, 3164);
  assert.equal(live3161BoundaryDiagnostics.accepted_target_ledger_matches_accepted_total, "yes");
  assert.deepEqual((live3161BoundaryDiagnostics.over_displayed_extra_items_exact as Array<Record<string, unknown>>).map((item) => item.accepted_index), [3161, 3162, 3163]);
  assert.equal(live3161BoundaryDiagnostics.over_displayed_itemized_reason_summary, "Derived from acceptedTargetLedger.slice(displayed_profile_count, persisted_count)");
  assert.equal((live3161BoundaryDiagnostics.accepted_target_ledger_boundary_window as Array<Record<string, unknown>>).some((item) => item.accepted_index === 3161), true);
  const live3161ForensicExport = live3161BoundaryDiagnostics.overcollection_forensic_export as Record<string, unknown>;
  assert.equal(live3161ForensicExport.purpose, "scan_profile_overcollection_forensic_export");
  assert.equal(live3161ForensicExport.displayed_profile_count, 3161);
  assert.equal(live3161ForensicExport.persisted_count, 3164);
  assert.equal(live3161ForensicExport.over_displayed_count, 3);
  assert.equal(live3161ForensicExport.ledger_present, true);
  assert.equal(live3161ForensicExport.ledger_count, 3164);
  assert.equal(live3161ForensicExport.ledger_matches_accepted_total, true);
  assert.equal(live3161ForensicExport.boundary_start_index, 3156);
  assert.equal(live3161ForensicExport.visible_boundary_index, 3161);
  assert.equal(live3161ForensicExport.boundary_end_index, 3164);
  assert.deepEqual(live3161ForensicExport.extra_ids, live3161BoundaryTargets.slice(3161, 3164).map((target) => target.awemeId));
  assert.equal((live3161ForensicExport.extra_items as Array<Record<string, unknown>>).length, 3);
  assert.deepEqual((live3161ForensicExport.extra_items as Array<Record<string, unknown>>).map((item) => item.accepted_index), [3161, 3162, 3163]);
  assert.deepEqual((live3161ForensicExport.boundary_window as Array<Record<string, unknown>>).map((item) => item.accepted_index), [3156, 3157, 3158, 3159, 3160, 3161, 3162, 3163]);
  assert.equal(live3161ForensicExport.final_verdict, "validated_same_profile");
  assert.equal(live3161ForensicExport.final_verdict_reason, "all_extra_items_validated_same_profile");

  const normalizedIdentityAccounting = __testPaginatedScanAccountingDiagnostics22C14B({
    rawItemsTotal: 3,
    rawAwemeIdsTotal: 3,
    uniqueAwemeIds: new Set(["7634192733514603161", "7634192733514603162", "7634192733514603163"]),
    uniqueAwemeIdOrder: ["7634192733514603161", "7634192733514603162", "7634192733514603163"],
    sameProfileEvidenceByAwemeId: new Map(),
    requestedProfileIdentifier: "https://www.douyin.com/user/MS4wLjABLIVE",
    apiResponseProfileIdentifier: "www.douyin.com/user/MS4wLjABLIVE",
    targetsReturnedToBackgroundTotal: 3,
    backgroundTargetsReceivedTotal: 3,
    backgroundTargetsAfterValidationTotal: 3,
    backgroundDuplicateDropTotal: 0,
    backgroundInvalidDropTotal: 0,
    otherProfileDropCount: 0,
    favoriteEndpointDropCount: 0,
    emptyOrMissingAwemeIdCount: 0,
    repositoryExistingBeforeTotal: 0,
    repositoryWriteInputCount: 3,
    repositoryNewInsertedTotal: 3,
    repositoryDuplicateExistingTotal: 0,
    repositoryWriteTotalAfter: 3,
    perPageRawCounts: [3],
    perPageRawAwemeIdCounts: [3],
    perPageReturnedTargetCounts: [3],
    perPageUniqueNewCounts: [3],
    perPageDuplicateCounts: [0],
    perPageCursorValues: [null],
    perPageCursorPresentFlags: [false],
    perPageHasMoreFlags: [false],
    perPageStatusCodes: [0],
    perPageParserRoutes: ["aweme_list"],
    acceptedTargetLedger: [0, 1, 2].map((offset) => ({
      aweme_id: `763419273351460316${offset + 1}`,
      accepted_index: 3156 + offset,
      page_index: 161,
      raw_index_in_page: offset,
      source: "active_profile_post_api",
      endpoint_path: "/aweme/v1/web/aweme/post/",
      request_url_path: "/aweme/v1/web/aweme/post/",
      request_cursor: 161,
      response_cursor: null,
      request_profile_identifier: "https://www.douyin.com/user/MS4wLjABLIVE",
      request_sec_uid: "www.douyin.com/user/MS4wLjABLIVE",
      api_template_profile_identifier: "[www.douyin.com/user/MS4wLjABLIVE](http://www.douyin.com/user/MS4wLjABLIVE)",
      api_template_sec_uid: "www.douyin.com/user/MS4wLjABLIVE",
      author_uid: `uid-${offset}`,
      author_sec_uid: "MS4wLjABLIVE",
      author_unique_id: "live_author",
      normalized_author_sec_uid: "MS4wLjABLIVE",
      normalized_request_sec_uid: "MS4wLjABLIVE",
      normalized_api_template_sec_uid: "MS4wLjABLIVE",
      normalized_request_profile_sec_uid: "MS4wLjABLIVE",
      normalized_api_template_profile_sec_uid: "MS4wLjABLIVE",
      normalized_repository_profile_sec_uid: "MS4wLjABLIVE",
      same_profile_validation_compared_fields: ["author_sec_uid:request_sec_uid", "author_sec_uid:api_template_sec_uid"],
      desc_sample: null,
      create_time: null,
      same_profile_validation_status: "same_profile",
      same_profile_validation_reason: "author_sec_uid_matches_requested_profile_sec_uid_after_normalization",
      profile_match_evidence: ["author_sec_uid_matches_requested_profile_sec_uid_after_normalization", "raw_identifier_format_mismatch_normalized_match"],
      raw_profile_match_evidence: ["author_sec_uid_matches_requested_profile_sec_uid_after_normalization", "raw_identifier_format_mismatch_normalized_match"],
      same_profile_missing_evidence: []
    }))
  } as never, 0, 3);
  assert.equal(normalizedIdentityAccounting.over_displayed_validation_status, "validated_same_profile");
  assert.equal(normalizedIdentityAccounting.scan_health_verdict, "ready_api_over_displayed_count");
  const normalizedIdentityExport = normalizedIdentityAccounting.overcollection_forensic_export as Record<string, unknown>;
  assert.equal(normalizedIdentityExport.final_verdict, "validated_same_profile");
  assert.deepEqual((normalizedIdentityExport.extra_items as Array<Record<string, unknown>>).map((item) => item.normalized_author_sec_uid), ["MS4wLjABLIVE", "MS4wLjABLIVE", "MS4wLjABLIVE"]);
  assert.deepEqual((normalizedIdentityExport.extra_items as Array<Record<string, unknown>>).map((item) => item.normalized_request_sec_uid), ["MS4wLjABLIVE", "MS4wLjABLIVE", "MS4wLjABLIVE"]);
  assert.equal((normalizedIdentityExport.extra_items as Array<Record<string, unknown>>).every((item) => item.same_profile_validation_reason === "author_sec_uid_matches_requested_profile_sec_uid_after_normalization"), true);

  const missingEvidenceTargets = liveBoundaryTargets.map((target, index) => index >= 3160 ? { ...target, profileIdentifier: null, sourceProfileIdentifier: null, authorSecUid: null, sameProfileValidationStatus: "missing_evidence", sameProfileValidated: "no", sameProfileValidationReason: "author_sec_uid_missing", sameProfileMissingEvidence: ["author_sec_uid_missing"], itemReason: "profile_identity_not_proven" } : target);
  const missingEvidenceDiagnostics = __testPaginatedScanAccountingDiagnostics22C14B(buildPaginatedOverDisplayAccounting(missingEvidenceTargets) as never, 3160, 3163);
  assert.deepEqual(missingEvidenceDiagnostics.over_displayed_extra_ids_exact, missingEvidenceTargets.slice(3160, 3163).map((target) => target.awemeId));
  assert.equal(missingEvidenceDiagnostics.over_displayed_validation_status, "needs_validation");
  assert.match(String((missingEvidenceDiagnostics.over_displayed_extra_items_exact as Array<Record<string, unknown>>)[0]?.same_profile_missing_evidence), /author_sec_uid_missing/);
  const missingEvidenceForensicExport = missingEvidenceDiagnostics.overcollection_forensic_export as Record<string, unknown>;
  assert.equal(missingEvidenceForensicExport.final_verdict, "needs_validation");
  assert.match(String(missingEvidenceForensicExport.final_verdict_reason), /insufficient_evidence_extra_items/);
  assert.equal((missingEvidenceForensicExport.extra_items as Array<Record<string, unknown>>).length, 3);

  const outsideProfileTargets = liveBoundaryTargets.map((target, index) => index === 3161 ? { ...target, profileIdentifier: "MS4wLjOTHER", sourceProfileIdentifier: "MS4wLjOTHER", authorSecUid: "MS4wLjOTHER", sameProfileValidationStatus: "outside_profile_detected", sameProfileValidated: "no", sameProfileValidationReason: "author_sec_uid_mismatch_requested_profile_sec_uid", itemReason: "possible_cross_profile_contamination" } : target);
  const outsideProfileDiagnostics = __testPaginatedScanAccountingDiagnostics22C14B(buildPaginatedOverDisplayAccounting(outsideProfileTargets) as never, 3160, 3163);
  assert.equal(outsideProfileDiagnostics.over_displayed_validation_status, "outside_profile_detected");
  assert.equal(outsideProfileDiagnostics.scan_health_verdict, "failed_overcollection_outside_profile");
  assert.deepEqual(outsideProfileDiagnostics.over_displayed_outside_profile_offending_aweme_ids, [outsideProfileTargets[3161]?.awemeId]);
  const outsideProfileForensicExport = outsideProfileDiagnostics.overcollection_forensic_export as Record<string, unknown>;
  assert.equal(outsideProfileForensicExport.final_verdict, "outside_profile_detected");
  assert.match(String(outsideProfileForensicExport.final_verdict_reason), new RegExp(String(outsideProfileTargets[3161]?.awemeId)));
  assert.deepEqual((outsideProfileForensicExport.extra_items as Array<Record<string, unknown>>).filter((item) => item.same_profile_validation_status === "outside_profile").map((item) => item.aweme_id), [outsideProfileTargets[3161]?.awemeId]);

  const noOrderedRecordDiagnostics = __testPaginatedScanAccountingDiagnostics22C14B(buildPaginatedOverDisplayAccounting([], false) as never, 3160, 3163);
  assert.equal(noOrderedRecordDiagnostics.count_semantics_status, "overcollected_forensic_ledger_missing");
  assert.equal(noOrderedRecordDiagnostics.over_displayed_validation_status, "needs_validation");
  assert.equal(noOrderedRecordDiagnostics.scan_health_verdict, "failed_or_warning_overcollection_validation_needed");
  assert.equal(noOrderedRecordDiagnostics.over_displayed_extra_items_exact, null);
  assert.equal(noOrderedRecordDiagnostics.over_displayed_extraction_error, "accepted target forensic ledger missing or incomplete");
  assert.match(String(noOrderedRecordDiagnostics.known_contradictions_to_debug), /overcollection_without_accepted_target_ledger/);
  const missingLedgerForensicExport = noOrderedRecordDiagnostics.overcollection_forensic_export as Record<string, unknown>;
  assert.equal(missingLedgerForensicExport.final_verdict, "ledger_missing");
  assert.equal(missingLedgerForensicExport.final_verdict_reason, "accepted_target_ledger_missing");
  assert.deepEqual(missingLedgerForensicExport.extra_items, []);
  assert.equal(missingLedgerForensicExport.extra_item_count, 0);

  const parserLossSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 996, apiRawCount: 996, apiUniqueCount: 996, apiHasMoreFinal: false, collectableCount: 991, persistedCount: 991, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 5, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(parserLossSemantics.count_semantics_status, "incomplete_internal_loss");
  assert.equal(parserLossSemantics.count_semantics_reason, "parser_extracted_fewer_than_raw");
  assert.equal(parserLossSemantics.scan_health_verdict, "failed_internal_accounting_loss");

  const repositoryLossSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 996, apiRawCount: 996, apiUniqueCount: 996, apiHasMoreFinal: false, collectableCount: 996, persistedCount: 991, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 5, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(repositoryLossSemantics.count_semantics_status, "incomplete_internal_loss");
  assert.equal(repositoryLossSemantics.count_semantics_reason, "repository_write_or_dedupe_loss");

  const apiNotExhaustedSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 996, apiRawCount: 991, apiUniqueCount: 991, apiHasMoreFinal: true, collectableCount: 991, persistedCount: 991, secondaryRecoveryAttempted: "not_yet_attempted", secondaryRecoveredCount: 0, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(apiNotExhaustedSemantics.count_semantics_status, "incomplete_api_not_exhausted");
  assert.equal(apiNotExhaustedSemantics.count_semantics_reason, "api_not_exhausted_or_request_chain_failed");
  assert.equal(apiNotExhaustedSemantics.scan_health_verdict, "failed_unknown");

  const secondaryFullSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 996, apiRawCount: 991, apiUniqueCount: 991, apiHasMoreFinal: false, collectableCount: 991, persistedCount: 996, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 5, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(secondaryFullSemantics.count_semantics_status, "completed_after_secondary_recovery");
  assert.equal(secondaryFullSemantics.count_semantics_reason, "secondary_recovery_reached_displayed_count");
  assert.equal(secondaryFullSemantics.scan_health_verdict, "ready_after_secondary_recovery");

  const secondaryPartialSemantics = __testCountSemanticsDiagnostics22C14Q({ displayedProfileCount: 996, apiRawCount: 991, apiUniqueCount: 991, apiHasMoreFinal: false, collectableCount: 994, persistedCount: 994, secondaryRecoveryAttempted: "yes", secondaryRecoveredCount: 3, parserExtractionDropCount: 0, validationOrProfileDropCount: 0, repositoryDropCount: 0, apiDuplicateAwemeIdsTotal: 0 });
  assert.equal(secondaryPartialSemantics.count_semantics_status, "completed_with_partial_secondary_recovery");
  assert.equal(secondaryPartialSemantics.count_semantics_reason, "displayed_count_partially_recovered_but_not_fully_collectable");
  assert.equal(secondaryPartialSemantics.scan_health_verdict, "ready_displayed_count_mismatch_explained");

  const completedContinuationSemantics = __testCountSemanticsDiagnostics22C14Q({
    displayedProfileCount: 3162,
    displayedProfileCountSource: "active_works_tab_dom_text",
    displayedProfileCountRawText: "作品 3162",
    apiRawCount: 666,
    apiUniqueCount: 666,
    apiHasMoreFinal: false,
    collectableCount: 3162,
    persistedCount: 3162,
    secondaryRecoveryAttempted: "yes",
    secondaryRecoveredCount: 0,
    parserExtractionDropCount: 0,
    validationOrProfileDropCount: 0,
    repositoryDropCount: 0,
    apiDuplicateAwemeIdsTotal: 0,
    continuationBatchNewCount: 666,
    continuationBatchRawCount: 666,
    continuationBatchAcceptedCount: 666,
    persistedTotalBeforeContinuation: 2496,
    persistedTotalAfterContinuation: 3162,
    finalCumulativeCollectableCount: 3162,
    finalDisplayAuthority: "cumulative_persisted_count",
    finalHeaderCount: 3162,
    finalCounterCount: 3162,
    headerCounterAuthorityMatch: "yes"
  });
  assert.equal(completedContinuationSemantics.count_semantics_status, "full_match");
  assert.equal(completedContinuationSemantics.collectable_count, 3162, "terminal continuation semantics must publish cumulative collectable count, not batch delta");
  assert.equal(completedContinuationSemantics.continuation_batch_new_count, 666);
  assert.equal(completedContinuationSemantics.continuation_batch_raw_count, 666);
  assert.equal(completedContinuationSemantics.continuation_batch_accepted_count, 666);
  assert.equal(completedContinuationSemantics.persisted_total_before_continuation, 2496);
  assert.equal(completedContinuationSemantics.persisted_total_after_continuation, 3162);
  assert.equal(completedContinuationSemantics.final_cumulative_collectable_count, 3162);
  assert.equal(completedContinuationSemantics.final_display_authority, "cumulative_persisted_count");
  assert.equal(completedContinuationSemantics.final_header_count, 3162);
  assert.equal(completedContinuationSemantics.final_counter_count, 3162);
  assert.equal(completedContinuationSemantics.header_counter_authority_match, "yes");

  const apiTemplateUnavailableHealth = __testScanHealthVerdictDiagnostics22C14R({ count_semantics_status: "incomplete_api_not_exhausted", count_semantics_reason: "api_not_exhausted_or_request_chain_failed", active_profile_post_fetch_stop_reason: "usable_template_unavailable", template_recovery_result: "template_unavailable_after_all_recovery" });
  assert.equal(apiTemplateUnavailableHealth.scan_health_verdict, "failed_api_template_unavailable_after_recovery");
  assert.match(String(apiTemplateUnavailableHealth.scan_health_verdict_reason), /usable_template_unavailable/);
  assert.equal(apiTemplateUnavailableHealth.scan_health_required_user_action, "retry_scan_profile_after_reload_login_or_network_check");

  const exactAccounting = __testPaginatedScanAccountingDiagnostics22C14B({ rawItemsTotal: 996, rawAwemeIdsTotal: 996, uniqueAwemeIds: new Set(Array.from({ length: 996 }, (_, index) => String(7634192733514501000n + BigInt(index)))), uniqueAwemeIdOrder: Array.from({ length: 996 }, (_, index) => String(7634192733514501000n + BigInt(index))), sameProfileEvidenceByAwemeId: new Map(Array.from({ length: 996 }, (_, index) => { const awemeId = String(7634192733514501000n + BigInt(index)); return [awemeId, { awemeId, profileUrl: "https://www.douyin.com/user/MS4wLjABEXACT", profileIdentifier: "MS4wLjABEXACT", pageIndexFound: index < 500 ? 0 : 1, requestIndexFound: index < 500 ? 1 : 2, sourceEndpoint: "/aweme/v1/web/aweme/post/", sourceCursor: index < 500 ? 0 : 1, sourceProfileIdentifier: "MS4wLjABEXACT", targetProfileIdentifier: "MS4wLjABEXACT", sameProfileValidated: "yes", sameProfileValidationReason: "source_profile_identifier_matches_requested_profile_identifier", isPinnedCandidate: "unknown", isSpecialTabCandidate: "unknown", appearsInDomGrid: "unknown", appearsInVisibleProfileCountBasis: "unknown", itemReason: "valid_same_profile_item_hidden_from_visible_count_basis" }]; })), requestedProfileIdentifier: "MS4wLjABEXACT", apiResponseProfileIdentifier: "MS4wLjABEXACT", targetsReturnedToBackgroundTotal: 996, backgroundTargetsReceivedTotal: 996, backgroundTargetsAfterValidationTotal: 996, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: 0, repositoryWriteInputCount: 996, repositoryNewInsertedTotal: 996, repositoryDuplicateExistingTotal: 0, repositoryWriteTotalAfter: 996, perPageRawCounts: [500, 496], perPageRawAwemeIdCounts: [500, 496], perPageReturnedTargetCounts: [500, 496], perPageUniqueNewCounts: [500, 496], perPageDuplicateCounts: [0, 0], perPageCursorValues: [1, null], perPageCursorPresentFlags: [true, false], perPageHasMoreFlags: [true, false], perPageStatusCodes: [0, 0], perPageParserRoutes: ["aweme_list", "aweme_list"], perPagePersistedTotals: [500, 996], firstPageRawCount: 500, lastPageRawCount: 496, lastPageAcceptedCount: 496, lastPagePersistedDelta: 496, finalHasMore: false, finalCursorPresent: false, finalStatusCode: 0 }, 996, 996);
  assert.equal(exactAccounting.final_gap_count, 0);
  assert.equal(exactAccounting.final_gap_reason, "none");
  assert.deepEqual(exactAccounting.api_pagination_per_page_raw_counts, [500, 496]);
  assert.deepEqual(exactAccounting.api_pagination_per_page_parser_routes, ["aweme_list", "aweme_list"]);

  const overcountAccounting = __testPaginatedScanAccountingDiagnostics22C14B({ rawItemsTotal: 478, rawAwemeIdsTotal: 478, uniqueAwemeIds: new Set(Array.from({ length: 478 }, (_, index) => String(7634192733514505000n + BigInt(index)))), uniqueAwemeIdOrder: Array.from({ length: 478 }, (_, index) => String(7634192733514505000n + BigInt(index))), sameProfileEvidenceByAwemeId: new Map(Array.from({ length: 478 }, (_, index) => { const awemeId = String(7634192733514505000n + BigInt(index)); return [awemeId, { awemeId, profileUrl: "https://www.douyin.com/user/MS4wLjABOVER", profileIdentifier: "MS4wLjABOVER", pageIndexFound: 0, requestIndexFound: 1, sourceEndpoint: "/aweme/v1/web/aweme/post/", sourceCursor: 0, sourceProfileIdentifier: "MS4wLjABOVER", targetProfileIdentifier: "MS4wLjABOVER", sameProfileValidated: "yes", sameProfileValidationReason: "source_profile_identifier_matches_requested_profile_identifier", isPinnedCandidate: "unknown", isSpecialTabCandidate: "unknown", appearsInDomGrid: index >= 475 ? "no" : "yes", appearsInVisibleProfileCountBasis: index >= 475 ? "no" : "yes", itemReason: "valid_same_profile_item_hidden_from_visible_count_basis" }]; })), requestedProfileIdentifier: "MS4wLjABOVER", apiResponseProfileIdentifier: "MS4wLjABOVER", targetsReturnedToBackgroundTotal: 478, backgroundTargetsReceivedTotal: 478, backgroundTargetsAfterValidationTotal: 478, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: 0, repositoryWriteInputCount: 478, repositoryNewInsertedTotal: 478, repositoryDuplicateExistingTotal: 0, repositoryWriteTotalAfter: 478, perPageRawCounts: [478], perPageRawAwemeIdCounts: [478], perPageReturnedTargetCounts: [478], perPageUniqueNewCounts: [478], perPageDuplicateCounts: [0], perPageCursorValues: [null], perPageCursorPresentFlags: [false], perPageHasMoreFlags: [false], perPageStatusCodes: [0], perPageParserRoutes: ["aweme_list"], perPagePersistedTotals: [478], firstPageRawCount: 478, lastPageRawCount: 478, lastPageAcceptedCount: 478, lastPagePersistedDelta: 478, finalHasMore: false, finalCursorPresent: false, finalStatusCode: 0 }, 475, 478);
  assert.equal(overcountAccounting.final_gap_count, 0);
  assert.equal(overcountAccounting.count_semantics_status, "overcollected_forensic_ledger_missing");
  assert.equal(overcountAccounting.count_semantics_reason, "accepted_target_forensic_ledger_missing_or_incomplete");
  assert.equal(overcountAccounting.scan_health_verdict, "failed_or_warning_overcollection_validation_needed");
  assert.equal(overcountAccounting.over_displayed_count, 3);
  assert.equal(overcountAccounting.over_displayed_validation_status, "needs_validation");
  assert.equal(overcountAccounting.over_displayed_extra_ids_exact, null);
  assert.equal(overcountAccounting.over_displayed_extra_items_exact, null);
  assert.equal(overcountAccounting.over_displayed_itemized_reason_summary, "accepted target forensic ledger missing or incomplete");
  assert.match(String(overcountAccounting.final_gap_evidence), /over_displayed_count: expected=475; persisted=478; over=3/);

  const apiShortAccounting = __testPaginatedScanAccountingDiagnostics22C14B({ rawItemsTotal: 991, rawAwemeIdsTotal: 991, uniqueAwemeIds: new Set(Array.from({ length: 991 }, (_, index) => String(7634192733514502000n + BigInt(index)))), uniqueAwemeIdOrder: Array.from({ length: 991 }, (_, index) => String(7634192733514502000n + BigInt(index))), sameProfileEvidenceByAwemeId: new Map(Array.from({ length: 991 }, (_, index) => { const awemeId = String(7634192733514502000n + BigInt(index)); return [awemeId, { awemeId, profileUrl: "https://www.douyin.com/user/MS4wLjABSHORT", profileIdentifier: "MS4wLjABSHORT", pageIndexFound: 0, requestIndexFound: 1, sourceEndpoint: "/aweme/v1/web/aweme/post/", sourceCursor: 0, sourceProfileIdentifier: "MS4wLjABSHORT", targetProfileIdentifier: "MS4wLjABSHORT", sameProfileValidated: "yes", sameProfileValidationReason: "source_profile_identifier_matches_requested_profile_identifier", isPinnedCandidate: "unknown", isSpecialTabCandidate: "unknown", appearsInDomGrid: "yes", appearsInVisibleProfileCountBasis: "yes", itemReason: "valid_same_profile_item_hidden_from_visible_count_basis" }]; })), requestedProfileIdentifier: "MS4wLjABSHORT", apiResponseProfileIdentifier: "MS4wLjABSHORT", targetsReturnedToBackgroundTotal: 991, backgroundTargetsReceivedTotal: 991, backgroundTargetsAfterValidationTotal: 991, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: 0, repositoryWriteInputCount: 991, repositoryNewInsertedTotal: 991, repositoryDuplicateExistingTotal: 0, repositoryWriteTotalAfter: 991, perPageRawCounts: [991], perPageRawAwemeIdCounts: [991], perPageReturnedTargetCounts: [991], perPageUniqueNewCounts: [991], perPageDuplicateCounts: [0], perPageCursorValues: [null], perPageCursorPresentFlags: [false], perPageHasMoreFlags: [false], perPageStatusCodes: [0], perPageParserRoutes: ["aweme_list"], perPagePersistedTotals: [991], firstPageRawCount: 991, lastPageRawCount: 991, lastPageAcceptedCount: 991, lastPagePersistedDelta: 991, finalHasMore: false, finalCursorPresent: false, finalStatusCode: 0 }, 996, 991);
  assert.equal(apiShortAccounting.final_gap_reason, "api_exhausted_below_expected");
  assert.equal(apiShortAccounting.count_semantics_status, "completed_with_displayed_count_mismatch");
  assert.equal(apiShortAccounting.count_semantics_reason, "displayed_count_not_fully_collectable");
  assert.equal(apiShortAccounting.api_raw_count, 991);

  const budgetResumableAccounting = __testPaginatedScanAccountingDiagnostics22C14B({ rawItemsTotal: 991, rawAwemeIdsTotal: 991, uniqueAwemeIds: new Set(Array.from({ length: 991 }, (_, index) => String(7634192733514502500n + BigInt(index)))), uniqueAwemeIdOrder: Array.from({ length: 991 }, (_, index) => String(7634192733514502500n + BigInt(index))), sameProfileEvidenceByAwemeId: new Map(Array.from({ length: 991 }, (_, index) => { const awemeId = String(7634192733514502500n + BigInt(index)); return [awemeId, { awemeId, profileUrl: "https://www.douyin.com/user/MS4wLjABBUDGET", profileIdentifier: "MS4wLjABBUDGET", pageIndexFound: Math.floor(index / 8), requestIndexFound: Math.floor(index / 8) + 1, sourceEndpoint: "/aweme/v1/web/aweme/post/", sourceCursor: Math.floor(index / 8), sourceProfileIdentifier: "MS4wLjABBUDGET", targetProfileIdentifier: "MS4wLjABBUDGET", sameProfileValidated: "yes", sameProfileValidationReason: "source_profile_identifier_matches_requested_profile_identifier", isPinnedCandidate: "unknown", isSpecialTabCandidate: "unknown", appearsInDomGrid: "yes", appearsInVisibleProfileCountBasis: "yes", itemReason: "valid_same_profile_item_hidden_from_visible_count_basis" }]; })), requestedProfileIdentifier: "MS4wLjABBUDGET", apiResponseProfileIdentifier: "MS4wLjABBUDGET", targetsReturnedToBackgroundTotal: 991, backgroundTargetsReceivedTotal: 991, backgroundTargetsAfterValidationTotal: 991, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: 0, repositoryWriteInputCount: 991, repositoryNewInsertedTotal: 991, repositoryDuplicateExistingTotal: 0, repositoryWriteTotalAfter: 991, perPageRawCounts: Array.from({ length: 128 }, () => 8), perPageRawAwemeIdCounts: Array.from({ length: 128 }, () => 8), perPageReturnedTargetCounts: Array.from({ length: 128 }, () => 8), perPageUniqueNewCounts: Array.from({ length: 128 }, () => 8), perPageDuplicateCounts: Array.from({ length: 128 }, () => 0), perPageCursorValues: Array.from({ length: 128 }, (_, index) => index), perPageCursorPresentFlags: Array.from({ length: 128 }, () => true), perPageHasMoreFlags: Array.from({ length: 128 }, () => true), perPageStatusCodes: Array.from({ length: 128 }, () => 0), perPageParserRoutes: Array.from({ length: 128 }, () => "aweme_list"), perPagePersistedTotals: Array.from({ length: 128 }, (_, index) => Math.min((index + 1) * 8, 991)), firstPageRawCount: 8, lastPageRawCount: 8, lastPageAcceptedCount: 8, lastPagePersistedDelta: 7, finalHasMore: true, finalCursorPresent: true, finalStatusCode: 0 }, 996, 991);
  assert.equal(budgetResumableAccounting.final_gap_reason, "api_budget_exhausted_before_has_more_false");
  assert.equal(budgetResumableAccounting.final_gap_classification, "resumable_api_budget_exhausted");
  assert.equal(budgetResumableAccounting.page_budget_exhausted, "yes");
  assert.equal(budgetResumableAccounting.continuation_available, "yes");
  assert.equal(budgetResumableAccounting.partial_scan_resumable, "yes");
  assert.equal(budgetResumableAccounting.source_failure, "no");
  assert.equal(apiShortAccounting.collectable_count, 991);
  assert.equal(apiShortAccounting.persisted_count, 991);
  assert.equal(apiShortAccounting.unavailable_or_unlisted_count, 5);
  assert.match(String(apiShortAccounting.final_gap_evidence), /raw=991/);

  const parserDropAccounting = __testPaginatedScanAccountingDiagnostics22C14B({ rawItemsTotal: 996, rawAwemeIdsTotal: 996, uniqueAwemeIds: new Set(Array.from({ length: 991 }, (_, index) => String(7634192733514503000n + BigInt(index)))), uniqueAwemeIdOrder: Array.from({ length: 991 }, (_, index) => String(7634192733514503000n + BigInt(index))), sameProfileEvidenceByAwemeId: new Map(Array.from({ length: 991 }, (_, index) => { const awemeId = String(7634192733514503000n + BigInt(index)); return [awemeId, { awemeId, profileUrl: "https://www.douyin.com/user/MS4wLjABPARSER", profileIdentifier: "MS4wLjABPARSER", pageIndexFound: 0, requestIndexFound: 1, sourceEndpoint: "/aweme/v1/web/aweme/post/", sourceCursor: 0, sourceProfileIdentifier: "MS4wLjABPARSER", targetProfileIdentifier: "MS4wLjABPARSER", sameProfileValidated: "yes", sameProfileValidationReason: "source_profile_identifier_matches_requested_profile_identifier", isPinnedCandidate: "unknown", isSpecialTabCandidate: "unknown", appearsInDomGrid: "yes", appearsInVisibleProfileCountBasis: "yes", itemReason: "valid_same_profile_item_hidden_from_visible_count_basis" }]; })), requestedProfileIdentifier: "MS4wLjABPARSER", apiResponseProfileIdentifier: "MS4wLjABPARSER", targetsReturnedToBackgroundTotal: 991, backgroundTargetsReceivedTotal: 991, backgroundTargetsAfterValidationTotal: 991, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: 0, repositoryWriteInputCount: 991, repositoryNewInsertedTotal: 991, repositoryDuplicateExistingTotal: 0, repositoryWriteTotalAfter: 991, perPageRawCounts: [996], perPageRawAwemeIdCounts: [996], perPageReturnedTargetCounts: [991], perPageUniqueNewCounts: [991], perPageDuplicateCounts: [5], perPageCursorValues: [null], perPageCursorPresentFlags: [false], perPageHasMoreFlags: [false], perPageStatusCodes: [0], perPageParserRoutes: ["aweme_list"], perPagePersistedTotals: [991], firstPageRawCount: 996, lastPageRawCount: 996, lastPageAcceptedCount: 991, lastPagePersistedDelta: 991, finalHasMore: false, finalCursorPresent: false, finalStatusCode: 0 }, 996, 991);
  assert.equal(parserDropAccounting.final_gap_reason, "parser_extracted_fewer_than_raw");
  assert.equal(parserDropAccounting.count_semantics_status, "incomplete_internal_loss");

  const repositoryDedupeAccounting = __testPaginatedScanAccountingDiagnostics22C14B({ rawItemsTotal: 996, rawAwemeIdsTotal: 996, uniqueAwemeIds: new Set(Array.from({ length: 996 }, (_, index) => String(7634192733514504000n + BigInt(index)))), uniqueAwemeIdOrder: Array.from({ length: 996 }, (_, index) => String(7634192733514504000n + BigInt(index))), sameProfileEvidenceByAwemeId: new Map(Array.from({ length: 996 }, (_, index) => { const awemeId = String(7634192733514504000n + BigInt(index)); return [awemeId, { awemeId, profileUrl: "https://www.douyin.com/user/MS4wLjABREPO", profileIdentifier: "MS4wLjABREPO", pageIndexFound: 0, requestIndexFound: 1, sourceEndpoint: "/aweme/v1/web/aweme/post/", sourceCursor: 0, sourceProfileIdentifier: "MS4wLjABREPO", targetProfileIdentifier: "MS4wLjABREPO", sameProfileValidated: "yes", sameProfileValidationReason: "source_profile_identifier_matches_requested_profile_identifier", isPinnedCandidate: "unknown", isSpecialTabCandidate: "unknown", appearsInDomGrid: "yes", appearsInVisibleProfileCountBasis: "yes", itemReason: "valid_same_profile_item_hidden_from_visible_count_basis" }]; })), requestedProfileIdentifier: "MS4wLjABREPO", apiResponseProfileIdentifier: "MS4wLjABREPO", targetsReturnedToBackgroundTotal: 996, backgroundTargetsReceivedTotal: 996, backgroundTargetsAfterValidationTotal: 996, backgroundDuplicateDropTotal: 0, backgroundInvalidDropTotal: 0, otherProfileDropCount: 0, favoriteEndpointDropCount: 0, emptyOrMissingAwemeIdCount: 0, repositoryExistingBeforeTotal: 0, repositoryWriteInputCount: 996, repositoryNewInsertedTotal: 991, repositoryDuplicateExistingTotal: 5, repositoryWriteTotalAfter: 991, perPageRawCounts: [996], perPageRawAwemeIdCounts: [996], perPageReturnedTargetCounts: [996], perPageUniqueNewCounts: [996], perPageDuplicateCounts: [0], perPageCursorValues: [null], perPageCursorPresentFlags: [false], perPageHasMoreFlags: [false], perPageStatusCodes: [0], perPageParserRoutes: ["aweme_list"], perPagePersistedTotals: [991], firstPageRawCount: 996, lastPageRawCount: 996, lastPageAcceptedCount: 996, lastPagePersistedDelta: 991, finalHasMore: false, finalCursorPresent: false, finalStatusCode: 0 }, 996, 991);
  assert.equal(repositoryDedupeAccounting.final_gap_reason, "repository_dedupe_or_write_loss");
  assert.equal(repositoryDedupeAccounting.count_semantics_status, "incomplete_internal_loss");
  assert.equal(repositoryDedupeAccounting.repository_duplicate_existing_total, 5);
}

{
  const { values, sentMessages, backendRequests } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 2, expected_profile_video_count_raw_text: "作品 2" },
    scannerResponse: null,
    paginatedResponses: [
      { ok: false, reason: "active_profile_post_response_status_non_zero", verified_targets: [], verified_target_details: [], diagnostics: { active_profile_post_page_fetch_last_status_code_22C14B: 5, scan_job_has_more_state: true, scan_job_cursor: 0 } },
      { ok: true, verified_targets: ["7634192733514501001", "7634192733514501002"], verified_target_details: [{ aweme_id: "7634192733514501001", source_url: "https://www.douyin.com/video/7634192733514501001", profile_url: "https://www.douyin.com/user/MS4wLjABCD" }, { aweme_id: "7634192733514501002", source_url: "https://www.douyin.com/video/7634192733514501002", profile_url: "https://www.douyin.com/user/MS4wLjABCD" }], scan_rounds: 1, stop_reason: "network_post_has_more_false", total_candidates: 2, rejected_count: 0, diagnostics: { scan_job_has_more_state: false, active_profile_post_page_fetch_has_more_state_22C14B: false, expected_profile_video_count: 2, expected_profile_video_count_semantics_verified: "yes", network_collection_stop_reason: "network_post_has_more_false" } }
    ],
    backendProfileSummary: { profile_identifier: "MS4wLjABCD", normalized_profile_url: "https://www.douyin.com/user/MS4wLjABCD", profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 2, counts: { captured: 2, ready: 2, dup: 0, fail: 0 }, items: [] }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  const retryState = await waitForScanJobStatus(values, "retry_wait", 5000);
  assert.equal(retryState.status, "verifying");
  assert.equal(retryState.scan_job.last_error, "active_profile_post_response_status_non_zero_retryable");
  await waitForScanFinalization(values, 5000);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(sentMessages.filter((message) => message.type === "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B").length, 2);
  assert.equal(state.scan_job.status, "completed");
  assert.equal(backendRequests.some((url) => url.includes("/douyin-extension/capture-inbox/profile-items?profile_url=https%3A%2F%2Fwww.douyin.com%2Fuser%2FMS4wLjABCD&limit=1000")), true, "paginated background scan finalization must call Capture Inbox profile summary after usable scan");
}

{
  const apiIds = ["7634192733514502001", "7634192733514502002"];
  const recoveredId = "7634192733514502003";
  const { values, sentMessages } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 3, expected_profile_video_count_raw_text: "作品 3", expected_profile_video_count_semantics_verified: "yes" },
    scannerResponse: null,
    tabUrl: "https://www.douyin.com/user/MS4wLjSECONDARYA",
    paginatedResponses: [{ ok: true, verified_targets: apiIds, verified_target_details: apiIds.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjSECONDARYA" })), diagnostics: { scan_job_has_more_state: false, active_profile_post_page_fetch_has_more_state_22C14B: false, active_profile_post_page_fetch_raw_item_count_22C14B: 2, active_profile_post_page_fetch_raw_aweme_id_count_22C14B: 2, active_profile_post_page_fetch_last_status_code_22C14B: 0, expected_profile_video_count: 3, expected_profile_video_count_source: "active_works_tab_dom_text", expected_profile_video_count_raw_text: "作品 3", expected_profile_video_count_semantics_verified: "yes" } }],
    tailReconcileCandidates: [{ aweme_id: recoveredId, source_url: `https://www.douyin.com/video/${recoveredId}`, profile_url: "https://www.douyin.com/user/MS4wLjSECONDARYA" }],
    backendProfileSummary: { profile_identifier: "MS4wLjSECONDARYA", normalized_profile_url: "https://www.douyin.com/user/MS4wLjSECONDARYA", profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 3, counts: { captured: 3, ready: 3, dup: 0, fail: 0 }, items: [] }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjSECONDARYA" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values, 5000);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(sentMessages.some((message) => message.type === "DOUYIN_PROFILE_DOM_PROBE_22C11B"), true);
  assert.equal(state.scan_job.total_persisted, 3);
  assert.equal(diagnostics.secondary_gap_probe_attempted, "yes");
  assert.equal(diagnostics.secondary_dom_candidate_count, 1);
  assert.equal(diagnostics.secondary_dom_new_candidate_count, 1);
  assert.equal(diagnostics.secondary_recovered_count, 1);
  assert.equal(diagnostics.final_gap_count_before_secondary_probe, 1);
  assert.equal(diagnostics.final_gap_count_after_secondary_probe, 0);
  assert.equal(diagnostics.final_gap_reason, "none");
  assert.equal(diagnostics.count_semantics_status, "completed_after_secondary_recovery");
  assert.equal(diagnostics.count_semantics_reason, "secondary_recovery_reached_displayed_count");
  assert.equal(diagnostics.lastScannerResult, "success");
}

{
  const apiIds = ["7634192733514503001", "7634192733514503002"];
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 3, expected_profile_video_count_raw_text: "作品 3", expected_profile_video_count_semantics_verified: "yes" },
    scannerResponse: null,
    tabUrl: "https://www.douyin.com/user/MS4wLjSECONDARYB",
    paginatedResponses: [{ ok: true, verified_targets: apiIds, verified_target_details: apiIds.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjSECONDARYB" })), diagnostics: { scan_job_has_more_state: false, active_profile_post_page_fetch_has_more_state_22C14B: false, active_profile_post_page_fetch_raw_item_count_22C14B: 2, active_profile_post_page_fetch_raw_aweme_id_count_22C14B: 2, active_profile_post_page_fetch_last_status_code_22C14B: 0, expected_profile_video_count: 3, expected_profile_video_count_source: "active_works_tab_dom_text", expected_profile_video_count_raw_text: "作品 3", expected_profile_video_count_semantics_verified: "yes" } }],
    tailReconcileCandidates: [],
    backendProfileSummary: { profile_identifier: "MS4wLjSECONDARYB", normalized_profile_url: "https://www.douyin.com/user/MS4wLjSECONDARYB", profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 2, counts: { captured: 2, ready: 2, dup: 0, fail: 0 }, items: [] }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjSECONDARYB" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values, 5000);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(state.scan_job.total_persisted, 2);
  assert.equal(diagnostics.secondary_gap_probe_attempted, "yes");
  assert.equal(diagnostics.secondary_recovered_count, 0);
  assert.equal(diagnostics.final_gap_count_after_secondary_probe, 1);
  assert.equal(diagnostics.final_gap_reason, "displayed_count_not_fully_collectable");
  assert.equal(diagnostics.count_semantics_status, "completed_with_displayed_count_mismatch");
  assert.equal(diagnostics.count_semantics_reason, "displayed_count_not_fully_collectable");
  assert.equal(diagnostics.unavailable_or_unlisted_count, 1);
  assert.match(String(diagnostics.final_gap_evidence), /secondary_recovered=0/);
}

{
  const apiIds = ["7634192733514504001", "7634192733514504002"];
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 3, expected_profile_video_count_raw_text: "作品 3", expected_profile_video_count_semantics_verified: "yes" },
    scannerResponse: null,
    tabUrl: "https://www.douyin.com/user/MS4wLjSECONDARYC",
    paginatedResponses: [{ ok: true, verified_targets: apiIds, verified_target_details: apiIds.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjSECONDARYC" })), diagnostics: { scan_job_has_more_state: false, active_profile_post_page_fetch_has_more_state_22C14B: false, active_profile_post_page_fetch_raw_item_count_22C14B: 2, active_profile_post_page_fetch_raw_aweme_id_count_22C14B: 2, active_profile_post_page_fetch_last_status_code_22C14B: 0, expected_profile_video_count: 3, expected_profile_video_count_source: "active_works_tab_dom_text", expected_profile_video_count_raw_text: "作品 3", expected_profile_video_count_semantics_verified: "yes" } }],
    domProbeFailAfterFirst: true,
    backendProfileSummary: { profile_identifier: "MS4wLjSECONDARYC", normalized_profile_url: "https://www.douyin.com/user/MS4wLjSECONDARYC", profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 2, counts: { captured: 2, ready: 2, dup: 0, fail: 0 }, items: [] }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjSECONDARYC" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values, 5000);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(state.scan_job.total_persisted, 2);
  assert.equal(diagnostics.secondary_gap_probe_attempted, "no");
  assert.equal(diagnostics.secondary_gap_probe_unavailable_reason, "dom_probe_unavailable_for_test");
  assert.equal(diagnostics.final_gap_count_after_secondary_probe, 1);
  assert.equal(diagnostics.final_gap_reason, "displayed_count_not_fully_collectable");
  assert.equal(diagnostics.count_semantics_status, "completed_with_displayed_count_mismatch");
  assert.equal(diagnostics.count_semantics_reason, "displayed_count_not_fully_collectable");
  assert.equal(diagnostics.unavailable_or_unlisted_count, 1);
}

{
  const persistedIds = Array.from({ length: 991 }, (_, index) => `763419273351452${String(index).padStart(3, "0")}`);
  const duplicatedIds = persistedIds.slice(0, 5);
  const totalPages = 128 * 4;
  const idsByPage = Array.from({ length: totalPages }, (_, pageIndex) => {
    const start = Math.floor((pageIndex * persistedIds.length) / totalPages);
    const end = Math.floor(((pageIndex + 1) * persistedIds.length) / totalPages);
    const pageIds = persistedIds.slice(start, end);
    return pageIndex === totalPages - 1 ? [...pageIds, ...duplicatedIds] : pageIds;
  });
  const paginatedResponses = idsByPage.map((pageIds, index) => ({
    ok: true,
    verified_targets: pageIds,
    verified_target_details: pageIds.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjPAGEBUDGET" })),
    diagnostics: {
      scan_job_has_more_state: true,
      active_profile_post_page_fetch_has_more_state_22C14B: true,
      scan_job_cursor: index + 1,
      active_profile_post_page_fetch_next_cursor_22C14B: index + 1,
      active_profile_post_page_fetch_raw_item_count_22C14B: pageIds.length,
      active_profile_post_page_fetch_raw_aweme_id_count_22C14B: pageIds.length,
      active_profile_post_page_fetch_empty_or_missing_aweme_id_count_22C14B: 0,
      active_profile_post_page_fetch_last_status_code_22C14B: 0,
      expected_profile_video_count: 996,
      expected_profile_video_count_semantics_verified: "yes"
    }
  }));
  const { values, sentMessages } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 996, expected_profile_video_count_raw_text: "作品 996", expected_profile_video_count_semantics_verified: "yes" },
    scannerResponse: null,
    tabUrl: "https://www.douyin.com/user/MS4wLjPAGEBUDGET",
    backendProfileSummary: { profile_identifier: "MS4wLjPAGEBUDGET", normalized_profile_url: "https://www.douyin.com/user/MS4wLjPAGEBUDGET", profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 991, counts: { captured: 991, ready: 991, dup: 0, fail: 0 }, items: [] },
    paginatedResponses
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjPAGEBUDGET" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values, 20000);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  const authorityDiagnostics = state.profile_scan.diagnostics as Record<string, unknown>;
  assert.equal(sentMessages.filter((message) => message.type === "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B").length, totalPages);
  assert.equal(state.scan_job.status, "completed");
  assert.equal(diagnostics.lastScannerResult, "completed_with_warning");
  assert.equal(diagnostics.scan_finalization_result, "completed_with_warning");
  assert.equal(diagnostics.scan_job_total_persisted, 991);
  assert.equal(diagnostics.scan_job_total_discovered, 996);
  assert.equal(diagnostics.scan_job_duplicate_or_existing_count, 5);
  assert.equal(diagnostics.scan_progress_discovered, 991);
  assert.equal(diagnostics.scan_progress_expected, 996);
  assert.equal(diagnostics.scan_progress_remaining, 5);
  assert.equal(diagnostics.profile_queue_total_count, 991);
  assert.equal(diagnostics.scan_job_page_budget, 128);
  assert.equal(diagnostics.scan_job_stop_reason, "auto_continuation_limit_reached");
  assert.equal(diagnostics.scan_job_has_more_at_stop, true);
  assert.equal(diagnostics.api_pagination_attempted, "yes");
  assert.equal(diagnostics.api_pagination_page_count, totalPages);
  assert.equal(diagnostics.api_pagination_request_count, totalPages);
  assert.equal(diagnostics.api_pagination_total_raw_targets, 996);
  assert.equal(diagnostics.api_pagination_total_accepted_targets, 991);
  assert.equal(diagnostics.api_pagination_duplicate_or_existing_count, 5);
  assert.equal(diagnostics.api_pagination_raw_items_total, 996, "real raw item accounting must come from each DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B page response");
  assert.equal(diagnostics.api_pagination_raw_aweme_ids_total, 996);
  assert.equal(diagnostics.api_pagination_accepted_targets_total, 996);
  assert.equal(diagnostics.api_pagination_persisted_targets_total, 991);
  assert.equal(diagnostics.api_pagination_duplicate_drop_count, 5);
  assert.equal(diagnostics.api_pagination_invalid_drop_count, 0);
  assert.equal(diagnostics.api_pagination_empty_or_missing_aweme_id_count, 0);
  assert.equal(diagnostics.api_pagination_repository_write_input_count, 996);
  assert.equal(diagnostics.api_pagination_repository_write_total_after, 991);
  assert.equal(diagnostics.api_pagination_first_page_raw_count, idsByPage[0]?.length);
  assert.equal(diagnostics.api_pagination_last_page_raw_count, idsByPage.at(-1)?.length);
  assert.equal(diagnostics.api_pagination_last_page_accepted_count, idsByPage.at(-1)?.length);
  assert.deepEqual(diagnostics.api_pagination_per_page_raw_counts, idsByPage.map((page) => page.length));
  assert.deepEqual(diagnostics.api_pagination_per_page_accepted_counts, idsByPage.map((page) => page.length));
  assert.deepEqual(diagnostics.api_pagination_per_page_raw_aweme_id_counts, idsByPage.map((page) => page.length));
  assert.deepEqual(diagnostics.api_pagination_per_page_returned_target_counts, idsByPage.map((page) => page.length));
  assert.equal(diagnostics.api_pages_fetched_total, totalPages);
  assert.equal(diagnostics.api_requests_total, totalPages);
  assert.equal(diagnostics.api_raw_items_total, 996);
  assert.equal(diagnostics.api_raw_aweme_ids_total, 996);
  assert.equal(diagnostics.api_targets_returned_to_background_total, 996);
  assert.equal(diagnostics.background_targets_after_validation_total, 996);
  assert.equal(diagnostics.repository_write_input_total, 996);
  assert.equal(diagnostics.repository_new_inserted_total, 991);
  assert.equal(diagnostics.repository_duplicate_existing_total, 5);
  assert.equal(diagnostics.repository_total_after, 991);
  assert.equal(diagnostics.final_gap_count, 5);
  assert.notEqual(diagnostics.final_gap_reason, "none", "positive expected gap must explain the reason instead of reporting none");
  assert.equal(diagnostics.final_gap_classification, "resumable_api_budget_exhausted");
  assert.equal(diagnostics.final_gap_reason, "api_budget_exhausted_before_has_more_false");
  assert.match(String(diagnostics.final_gap_evidence), /has_more=true/);
  assert.equal(diagnostics.api_pagination_has_more_final, true);
  assert.equal(diagnostics.api_pagination_stop_reason, "auto_continuation_limit_reached");
  assert.equal(diagnostics.final_gap_classification, "resumable_api_budget_exhausted");
  assert.equal(diagnostics.scan_mode, "api_profile_post_pagination");
  assert.equal(diagnostics.scan_mode_visible_scroll_required, "no");
  assert.equal(state.scan_job.total_persisted, 991);
  assert.equal(state.scan_job.total_discovered, 996);
  assert.equal(state.scan_job.remaining_estimate, 5);
  assert.equal(state.scan_job.has_more_state, true);
}

{
  resetProfileTargetRepositoryForTests();
  const persistedIds = ["7634192733514599001", "7634192733514599002", "7634192733514599003"];
  const profileUrl = "https://www.douyin.com/user/MS4wLjSTALERESUME";
  const profileIdentifier = profileIdentifierFromUrl(profileUrl);
  const repository = createProfileTargetRepository();
  const persistedQueue = persistedIds.map((aweme_id, index) => ({
    index: index + 1,
    aweme_id,
    capture_status: "new" as const,
    status: "pending" as const,
    attempts: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    capture_inbox_item_id: null,
    source_url: `https://www.douyin.com/video/${aweme_id}`,
    profile_card_evidence: { profile_url: profileUrl }
  }));
  const persistedDetails = persistedIds.map((aweme_id, index) => ({
    index: index + 1,
    aweme_id,
    source_url: `https://www.douyin.com/video/${aweme_id}`,
    profile_url: profileUrl,
    thumbnail_url: null,
    title: null,
    caption: null,
    text_sample: null,
    posted_text: null,
    posted_at: null,
    duration_text: null,
    duration_seconds: null,
    view_text: null,
    view_count: null,
    candidate_validation: { status: "accepted" as const, source: "video_link" as const, reason: null, source_url: `https://www.douyin.com/video/${aweme_id}` },
    metadata_completeness: { has_profile_identity: true, has_thumbnail: false, has_title_or_caption: false, has_posted_text: false, has_duration: false, has_view_count: false, has_detail_metrics: false },
    capture_status: "new" as const,
    backend_item: null,
    extraction_source: "video_link" as const,
    profile_card_evidence: { profile_url: profileUrl }
  }));
  await repository.upsertProfileTargets(profileIdentifier, persistedQueue, persistedDetails, "2026-05-30T05:00:00.000Z");
  const duplicateOnlyResponses = Array.from({ length: 6 }, (_, index) => ({
    ok: true,
    verified_targets: persistedIds,
    verified_target_details: persistedIds.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: profileUrl })),
    diagnostics: {
      scan_job_has_more_state: true,
      active_profile_post_page_fetch_has_more_state_22C14B: true,
      scan_job_cursor: index + 1,
      active_profile_post_page_fetch_next_cursor_22C14B: index + 1,
      active_profile_post_page_fetch_raw_item_count_22C14B: persistedIds.length,
      active_profile_post_page_fetch_raw_aweme_id_count_22C14B: persistedIds.length,
      active_profile_post_page_fetch_last_status_code_22C14B: 0,
      expected_profile_video_count: 6,
      expected_profile_video_count_raw_text: "作品 6",
      expected_profile_video_count_semantics_verified: "yes"
    }
  }));
  const { values, sentMessages } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 6, expected_profile_video_count_raw_text: "作品 6", expected_profile_video_count_semantics_verified: "yes" },
    scannerResponse: null,
    tabUrl: profileUrl,
    backendProfileSummary: { profile_identifier: "MS4wLjSTALERESUME", normalized_profile_url: profileUrl, profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 3, counts: { captured: 3, ready: 3, dup: 0, fail: 0 }, items: [] },
    paginatedResponses: duplicateOnlyResponses
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: profileUrl } }, {});
  assert.equal(accepted.ok, true);
  const state = await waitForScanJobStatus(values, "failed", 20000);
  assert.equal(state.scan_job.last_error, "stale_resume_duplicate_replay_after_fresh_restart");
  assert.equal(state.scan_job.total_persisted, 3);
  assert.equal(sentMessages.filter((message) => message.type === "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B").length, 6, "stale resume should trigger one fresh restart before terminal failure");
  resetProfileTargetRepositoryForTests();
}

{
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 2, expected_profile_video_count_raw_text: "作品 2" },
    scannerResponse: null,
    paginatedResponses: Array.from({ length: 4 }, () => ({ ok: false, reason: "active_profile_post_response_status_non_zero", verified_targets: [], verified_target_details: [], diagnostics: { active_profile_post_page_fetch_last_status_code_22C14B: 5, scan_job_has_more_state: true, scan_job_cursor: 0 } }))
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  const state = await waitForScanJobStatus(values, "failed", 20000);
  assert.equal(state.scan_job.last_error, "active_profile_post_response_status_non_zero_terminal");
  assert.equal(state.status, "failed");
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  const authorityDiagnostics = state.profile_scan.diagnostics as Record<string, unknown>;
  assert.equal(state.phase, "scan_finished");
  assert.equal(state.profile_scan.status, "failed");
  assert.equal(state.verify.status, "failed");
  assert.equal(authorityDiagnostics.terminal_write_lock_active, "yes");
  assert.equal(authorityDiagnostics.terminal_write_lock_run_id, state.scan_job.scan_job_id);
  assert.equal(authorityDiagnostics.scan_finalization_result, "failed");
  assert.equal(authorityDiagnostics.active_source_terminal_policy, "degraded_fallback_attempted_before_terminal_failure");
  assert.equal(state.workflow.active_task, null);
  assert.equal(state.workflow.action_lock, null);
  assert.equal(state.workflow.scan.status, "failed");
  assert.equal(state.debug.active_task, null);
  assert.equal(state.debug.busy_source, null);
  assert.notEqual(state.profile_scan.status, "running");
  assert.equal(diagnostics.active_profile_post_response_status_code, 5);
  assert.equal(diagnostics.active_profile_post_fetch_stop_reason, "active_profile_post_response_status_non_zero");
  assert.equal(diagnostics.active_profile_post_template_found, "no");
  assert.equal(diagnostics.active_profile_post_template_required_query_keys_available, "no");
  assert.equal(diagnostics.expected_count_gate_meaningful_active_fetch, "no");
  assert.equal(diagnostics.expected_count_gate_dom_only_convergence_allowed, "no");
  assert.equal(diagnostics.active_profile_post_recovery_attempted, "yes");
  assert.equal(diagnostics.active_profile_post_recovery_result, "failed");
  assert.equal(diagnostics.active_profile_post_recovery_reason, "active_profile_post_response_status_non_zero_terminal");
  assert.equal(diagnostics.active_profile_post_non_zero_status_retryable, "yes");
  assert.equal(diagnostics.scan_stop_authoritative, "active_profile_post_response_status_non_zero");
  assert.equal(diagnostics.scan_stop_authority_source, "paginated_active_profile_post_retry_22C14B");
}

{
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      expected_profile_video_count: 3,
      expected_profile_video_count_raw_text: "作品 3",
      expected_profile_video_count_semantics_verified: "yes",
      network_profile_post_targets: [
        { aweme_id: "7634192733514501101", source_url: "https://www.douyin.com/video/7634192733514501101", profile_url: "https://www.douyin.com/user/MS4wLjFALLBACK", endpoint_kind: "profile_post" },
        { aweme_id: "7634192733514501102", source_url: "https://www.douyin.com/video/7634192733514501102", profile_url: "https://www.douyin.com/user/MS4wLjFALLBACK", endpoint_kind: "profile_post" }
      ],
      videoAnchors: [{ aweme_id: "7634192733514501103", href: "https://www.douyin.com/video/7634192733514501103" }],
      awemeIds: ["7634192733514501103"]
    },
    tailReconcileCandidates: [{ aweme_id: "7634192733514501103", source_url: "https://www.douyin.com/video/7634192733514501103", profile_url: "https://www.douyin.com/user/MS4wLjFALLBACK" }],
    scannerResponse: null,
    tabUrl: "https://www.douyin.com/user/MS4wLjFALLBACK",
    backendProfileSummary: { profile_identifier: "MS4wLjFALLBACK", normalized_profile_url: "https://www.douyin.com/user/MS4wLjFALLBACK", profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 0, counts: { captured: 0, ready: 0, dup: 0, fail: 0 }, items: [] },
    paginatedResponses: Array.from({ length: 4 }, () => ({ ok: false, reason: "active_profile_post_response_status_non_zero", verified_targets: [], verified_target_details: [], diagnostics: { active_profile_post_page_fetch_last_status_code_22C14B: 5, scan_job_has_more_state: true, scan_job_cursor: 0 } }))
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjFALLBACK" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values, 20000);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(state.status, "verified");
  assert.equal(state.scan_job.status, "completed");
  assert.equal(state.workflow.active_task, null);
  assert.equal(state.workflow.action_lock, null);
  assert.equal(state.debug.active_task, null);
  assert.equal(state.debug.busy_source, null);
  assert.deepEqual(state.harvest.queue.map((item) => item.aweme_id), ["7634192733514501101", "7634192733514501102", "7634192733514501103"]);
  assert.equal(state.harvest.queue.length, 3);
  assert.equal(diagnostics.scan_fallback_used, "yes");
  assert.equal(diagnostics.scan_fallback_original_active_fetch_error, "active_profile_post_response_status_non_zero_terminal");
  assert.equal(diagnostics.scan_fallback_candidate_total_count, 3);
  assert.equal(diagnostics.active_profile_post_response_status_code, 5);
  assert.equal(diagnostics.queue_authority_fallback_used, "yes");
}

{
  const fallbackDetails = Array.from({ length: 10 }, (_, index) => {
    const awemeId = `763419273351451${String(index).padStart(3, "0")}`;
    return { aweme_id: awemeId, source_url: `https://www.douyin.com/video/${awemeId}`, profile_url: "https://www.douyin.com/user/MS4wLjSEVERE", endpoint_kind: "profile_post" };
  });
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      expected_profile_video_count: 100,
      expected_profile_video_count_raw_text: "作品 100",
      expected_profile_video_count_semantics_verified: "yes",
      network_profile_post_targets: fallbackDetails.slice(0, 6),
      videoAnchors: fallbackDetails.slice(6).map((item) => ({ aweme_id: item.aweme_id, href: item.source_url })),
      awemeIds: fallbackDetails.slice(6).map((item) => item.aweme_id)
    },
    scannerResponse: null,
    tabUrl: "https://www.douyin.com/user/MS4wLjSEVERE",
    backendProfileSummary: { profile_identifier: "MS4wLjSEVERE", normalized_profile_url: "https://www.douyin.com/user/MS4wLjSEVERE", profile_scope: "same_profile_only", source: "capture_inbox_profile_items", items_count: 0, counts: { captured: 0, ready: 0, dup: 0, fail: 0 }, items: [] },
    paginatedResponses: Array.from({ length: 4 }, () => ({ ok: false, reason: "active_profile_post_response_status_non_zero", verified_targets: [], verified_target_details: [], diagnostics: { active_profile_post_page_fetch_last_status_code_22C14B: 5, scan_job_has_more_state: true, scan_job_cursor: 0 } }))
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjSEVERE" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values, 20000);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  const profileDiagnostics = state.profile_scan.diagnostics as Record<string, unknown>;
  const verifyDiagnostics = state.verify.diagnostics as Record<string, unknown>;
  const finalDiagnostics = { ...diagnostics, ...profileDiagnostics, ...verifyDiagnostics };
  assert.notEqual(state.status, "verified", "severe DOM-only expected-count undercount must not verify the scan");
  assert.equal(state.scan_job.status, "failed");
  assert.equal(state.profile_scan.status, "failed");
  assert.equal(state.workflow.scan.status, "failed");
  assert.equal(state.layer.profile_scan_ready, false);
  assert.equal(state.harvest.queue.length, 10, "partial DOM/network fallback evidence should be preserved for diagnostics and retry context");
  assert.equal(finalDiagnostics.lastScannerResult, "incomplete");
  assert.equal(finalDiagnostics.scan_finalization_result, "incomplete");
  assert.equal(finalDiagnostics.scan_completeness_gate_result, "blocked");
  assert.equal(finalDiagnostics.scan_completeness_ready_blocked, "yes");
  assert.equal(finalDiagnostics.scan_completeness_dom_only_fallback, "yes");
  assert.equal(finalDiagnostics.scan_completeness_active_fetch_meaningful, "no");
  assert.equal(finalDiagnostics.scan_completeness_expected_count, 100);
  assert.equal(finalDiagnostics.scan_completeness_found_count, 10);
  assert.equal(finalDiagnostics.scan_completeness_missing_count, 90);
  assert.equal(finalDiagnostics.profileScanReady, "no");
  assert.match(
    String(finalDiagnostics.scan_completeness_gate_reason),
    /dom_only_fallback_under_expected_active_fetch_(response_status_non_zero|required_query_keys_unavailable)/
  );
}

{
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 2, expected_profile_video_count_raw_text: "作品 2" },
    scannerResponse: null,
    paginatedResponses: [{ ok: false, reason: "page_fetch_failed", verified_targets: [], verified_target_details: [], diagnostics: { scan_job_has_more_state: true, scan_job_cursor: 0 } }]
  });
  const originalDateParse = Date.parse;
  Date.parse = (() => Number.NaN) as typeof Date.parse;
  try {
    const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
    assert.equal(accepted.ok, true);
    const state = await waitForScanJobStatus(values, "failed");
    assert.equal(state.scan_job.last_error, "retry_wait_invalid_checkpoint");
  } finally {
    Date.parse = originalDateParse;
  }
}

{
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 2, expected_profile_video_count_raw_text: "作品 2" },
    scannerResponse: null,
    paginatedResponses: [{ ok: false, reason: "active_profile_post_response_status_non_zero", verified_targets: [], verified_target_details: [], diagnostics: { active_profile_post_page_fetch_last_status_code_22C14B: 5, scan_job_has_more_state: true, scan_job_cursor: 0, scan_job_retry_wait_stall_guard_triggered: "force" } }]
  });
  const originalDateNow = Date.now;
  let now = originalDateNow();
  Date.now = (() => now) as typeof Date.now;
  try {
    now += 60_000;
    const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
    assert.equal(accepted.ok, true);
    const state = await waitForScanJobStatus(values, "failed");
    assert.equal(state.scan_job.last_error, "retry_wait_stall_guard_terminal");
  } finally {
    Date.now = originalDateNow;
  }
}

{
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 2, expected_profile_video_count_raw_text: "作品 2" },
    scannerResponse: null,
    paginatedResponses: Array.from({ length: 4 }, () => ({ ok: false, reason: "active_profile_post_response_status_non_zero", verified_targets: [], verified_target_details: [], diagnostics: { active_profile_post_page_fetch_last_status_code_22C14B: 5, scan_job_has_more_state: true, scan_job_cursor: 0 } }))
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  const state = await waitForScanJobStatus(values, "failed", 20000);
  assert.notEqual(state.status, "verified");
  assert.notEqual(state.verify.status, "success");
}

{
  const { values, sentMessages, backendRequests } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 2,
      network_probe_unique_aweme_count: 3,
      network_profile_post_unique_count: 2,
      network_favorite_unique_count: 1,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: [
        { aweme_id: "7634192733514501001", source_url: "https://www.douyin.com/video/7634192733514501001", profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: "2026-05-14T05:00:00.000Z", trace_version: "22C-12A-R3" },
        { aweme_id: "7634192733514501002", source_url: "https://www.douyin.com/video/7634192733514501002", profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: "2026-05-14T05:00:01.000Z", trace_version: "22C-12A-R3" }
      ],
      network_favorite_targets: [
        { aweme_id: "7634192733514501999", source_url: "https://www.douyin.com/video/7634192733514501999", profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/favorite/", endpoint_kind: "favorite", captured_at: "2026-05-14T05:00:02.000Z", trace_version: "22C-12A-R3" }
      ],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: ["7634192733514501001", "7634192733514501002"],
      verified_target_details: [
        { aweme_id: "7634192733514501001", source_url: "https://www.douyin.com/video/7634192733514501001", profile_url: "https://www.douyin.com/user/MS4wLjABCD", caption: "one" },
        { aweme_id: "7634192733514501002", source_url: "https://www.douyin.com/video/7634192733514501002", profile_url: "https://www.douyin.com/user/MS4wLjABCD", caption: "two" }
      ],
      scan_rounds: 2,
      stop_reason: "network_post_has_more_false",
      total_candidates: 2,
      rejected_count: 1,
      diagnostics: {
        canonical_content_handler_received: "yes",
        canonical_scanner_function: "collectActiveWorksGridTargets22C11B",
        expected_profile_video_count: 2,
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_raw_text: "作品 2",
        expected_profile_video_count_semantics_verified: "yes",
        scan_engine_used: "minimal_active_works_grid_scanner_22C11B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 2,
        network_favorite_unique_count: 1,
        network_favorite_excluded_count: 1,
        network_collection_stop_reason: "network_post_has_more_false"
      }
    },
    backendProfileSummary: {
      profile_identifier: "MS4wLjABCD",
      normalized_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
      profile_scope: "same_profile_only",
      source: "capture_inbox_profile_items",
      items_count: 30,
      counts: { captured: 30, ready: 19, dup: 0, fail: 0 },
      items: Array.from({ length: 30 }, (_, index) => ({ id: `inbox-${index + 1}`, metadata_status: index < 19 ? "ready" : "needs_action" }))
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(sentMessages.some((message) => message.type === "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B"), true);
  assert.equal(sentMessages.some((message) => message.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING"), true);
  assert.equal(sentMessages.some((message) => message.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B"), true);
  assert.equal(diagnostics.scanner_runtime_version, "22C-12F");
  assert.equal(diagnostics.active_scan_profile_engine, "minimal_active_works_grid_scanner_22C11B");
  assert.equal(diagnostics.scan_queue_builder_used, "scan_queue_adapter_22C11B");
  assert.equal(diagnostics.network_profile_post_unique_count, 2);
  assert.equal(diagnostics.network_favorite_unique_count, 1);
  assert.equal(diagnostics.network_favorite_excluded_count, 1);
  assert.equal(diagnostics.lastScannerResult, "success");
  assert.equal(diagnostics.lastScannerError, "none");
  assert.equal(backendRequests.some((url) => url.includes("/douyin-extension/capture-inbox/profile-items?profile_url=https%3A%2F%2Fwww.douyin.com%2Fuser%2FMS4wLjABCD&limit=1000")), true, "background scan finalization must call Capture Inbox profile summary after scan");
  assert.equal(diagnostics.post_scan_backend_reconciliation_status, "success");
  assert.equal(diagnostics.post_scan_backend_reconciliation_endpoint, "/douyin-extension/capture-inbox/profile-items");
  assert.equal(diagnostics.post_scan_backend_reconciliation_used_capture_inbox_card_source, "yes");
  assert.equal(diagnostics.post_scan_backend_captured_count, 30);
  assert.equal(diagnostics.post_scan_backend_ready_count, 19);
  assert.equal(diagnostics.post_scan_backend_duplicate_count, 0);
  assert.equal(diagnostics.post_scan_backend_failed_count, 0);
  assert.equal(diagnostics.post_scan_backend_incomplete_count, 11);
  assert.equal(diagnostics.post_scan_new_count, 0);
  assert.equal(diagnostics.post_scan_queue_count, 0);
  assert.equal(diagnostics.post_scan_counter_snapshot_applied, "yes");
  assert.equal(diagnostics.post_scan_counter_snapshot_source, "capture_inbox_profile_card_counts");
  assert.equal(state.post_scan_counter_snapshot?.status, "applied");
  assert.equal(state.post_scan_counter_snapshot?.source, "backend_capture_inbox_profile_summary");
  assert.equal(state.post_scan_counter_snapshot?.already_collected, 30);
  assert.equal(state.post_scan_counter_snapshot?.incomplete, 11);
  assert.equal(state.post_scan_counter_snapshot?.need_retry, 0);
  assert.equal(state.post_scan_counter_snapshot?.new, 0);
  assert.equal(state.post_scan_counter_snapshot?.queue, 0);
  assert.equal(state.harvest.queue.length, 2);
  assert.deepEqual(state.harvest.queue.map((item) => item.aweme_id), ["7634192733514501001", "7634192733514501002"]);
  const scanSourceLedger = diagnostics.scan_source_ledger as Record<string, unknown>;
  assert.equal(typeof scanSourceLedger, "object");
  assert.equal(scanSourceLedger.network_profile_post_count, 2);
  assert.equal(scanSourceLedger.merged_target_count, 2);
  assert.equal(diagnostics.queue_source_dispatch_mode, undefined);
  assert.equal(diagnostics.queue_source_mode, diagnostics.queue_authority_mode);
  assert.equal(diagnostics.scan_stop_authoritative, diagnostics.scanStop);
  assert.equal(diagnostics.scan_stop_authority_source, "canonical_terminal_reconciliation");
  assert.equal(diagnostics.scan_stop_authority_version, "22C-13D");
  assert.equal(diagnostics.scan_stop_authority_migrated, "yes");
  assert.equal(diagnostics.scan_stop, diagnostics.scanStop);
  const stageHistory = Array.isArray(diagnostics.scan_stage_history) ? diagnostics.scan_stage_history as Array<Record<string, unknown>> : [];
  const stageEvents = stageHistory.map((entry) => String(entry.event ?? ""));
  assert.equal(stageEvents.includes("legacy_scanner_invocation_starting"), false);
  assert.equal(stageEvents.includes("legacy_scanner_invocation"), false);
  assert.equal(stageEvents.includes("queue_adapter"), false);
}

{
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 1,
      network_probe_unique_aweme_count: 0,
      network_profile_post_unique_count: 0,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: [],
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      cards: [
        { aweme_id: "7634192733514501777", source_url: "https://www.douyin.com/video/7634192733514501777", profile_url: "https://www.douyin.com/user/MS4wLjABCD" }
      ],
      scan_rounds: 2,
      stop_reason: "legacy_cards_only",
      total_candidates: 1,
      rejected_count: 0,
      diagnostics: {
        scan_engine_used: "minimal_active_works_grid_scanner_22C11B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B"
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "failed");
  assert.equal(diagnostics.lastScannerError, "canonical_scanner_zero_verified_targets");
  assert.equal(diagnostics.canonical_scanner_verified_target_count, 0);
  assert.equal(state.harvest.queue.length, 0);
}

{
  const underCollectedProfileUrl = "https://www.douyin.com/user/MS4wLjABUNDER33";
  const targets = Array.from({ length: 33 }, (_, index) => `76341927335145${String(index).padStart(4, "0")}`);
  const { values, sentMessages } = installChromeForScanTest({
    tabUrl: underCollectedProfileUrl,
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 2,
      network_probe_unique_aweme_count: 33,
      expected_profile_video_count: 45,
      expected_profile_video_count_raw_text: "作品 45",
      network_profile_post_unique_count: 33,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: underCollectedProfileUrl, endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:00:${String(index).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: underCollectedProfileUrl })),
      scan_rounds: 6,
      stop_reason: "stable_no_new_profile_post_ids",
      total_candidates: 33,
      rejected_count: 0,
      diagnostics: {
        expected_profile_video_count: 45,
        expected_profile_video_count_raw_text: "作品 45",
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_semantics_verified: "yes",
        scan_engine_used: "minimal_active_works_grid_scanner_22C11B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 33,
        network_collection_stop_reason: "stable_no_new_profile_post_ids"
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: underCollectedProfileUrl } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  const scanMessage = sentMessages.find((message) => message.type === "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B");
  assert.equal(scanMessage?.expectedProfileVideoCount, 45);
  assert.equal(diagnostics.lastScannerResult, "incomplete");
  assert.equal(diagnostics.lastScannerError, "canonical_under_collected_expected_count_active_profile_post_terminal_failure");
  assert.equal(diagnostics.profile_queue_total_count, 33);
  assert.equal(diagnostics.expected_profile_video_count, 45);
  assert.equal(diagnostics.missing_profile_video_count, 12);
  assert.equal(diagnostics.over_collected_count, 0);
  assert.equal(diagnostics.count_delta, -12);
  assert.equal(diagnostics.profile_scan_completion_ratio, "33/45");
  assert.equal(diagnostics.count_reconciliation_state, "under_collected");
  assert.equal(diagnostics.expected_count_gate_dom_only_convergence_allowed, "no");
  assert.equal(diagnostics.expected_count_gate_meaningful_active_fetch, "no");
  assert.equal(diagnostics.scanStop, "active_profile_post_extractor_no_targets_below_expected");
  assert.equal(diagnostics.scan_stop_authoritative, diagnostics.scanStop);
  assert.equal(diagnostics.scan_stop_authority_source, "canonical_terminal_reconciliation");
  assert.equal(diagnostics.scan_stop_authority_version, "22C-13D");
  assert.equal(diagnostics.scan_stop_authority_migrated, "yes");
  assert.equal(diagnostics.scan_stop, diagnostics.scanStop);
  assert.equal(state.layer.profile_scan_ready, false);
  assert.equal(state.status, "failed");
}

{
  const targets = Array.from({ length: 33 }, (_, index) => `76341927335145${String(index).padStart(4, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 2,
      network_probe_unique_aweme_count: 33,
      network_profile_post_unique_count: 33,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:00:${String(index).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 4,
      stop_reason: "stable_no_new_profile_post_ids",
      total_candidates: 33,
      rejected_count: 0,
      diagnostics: {
        expected_profile_video_count: null,
        expected_profile_video_count_semantics_verified: "no",
        minimal_scan_network_probe_post_exhausted_22C11B: "yes",
        minimal_scan_network_probe_post_has_more_state_22C11B: false,
        minimal_scan_active_profile_post_fetch_effective_attempted_22C13B: "yes",
        minimal_scan_active_profile_post_fetch_effective_attempt_reason_22C13B: "required_query_keys_unavailable",
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "required_query_keys_unavailable",
        minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B: "required_query_keys_unavailable",
        minimal_scan_active_profile_post_fetch_expected_count_retry_eligible_22C13B: "yes",
        minimal_scan_active_profile_post_fetch_expected_count_retry_attempted_22C13B: "yes",
        minimal_scan_active_profile_post_fetch_expected_count_retry_reason_22C13B: "none",
        minimal_scan_active_profile_post_fetch_expected_count_retry_wait_ms_22C13B: 600,
        minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_before_22C13B: 33,
        minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_after_22C13B: 33,
        minimal_scan_active_profile_post_fetch_expected_count_retry_stop_reason_22C13B: "active_profile_post_response_status_non_zero",
        minimal_scan_active_profile_post_fetch_expected_count_retry_meaningful_attempted_22C13B: "yes",
        scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 33
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "incomplete");
  assert.equal(diagnostics.lastScannerError, "canonical_expected_count_semantics_unverified_exhausted_without_strong_evidence");
  assert.equal(diagnostics.queue_source_mode, "dom_scoped_fallback_degraded");
  assert.equal(diagnostics.queue_authority_locked, "yes");
  assert.equal(diagnostics.queue_authority_mode, "dom_scoped_fallback_degraded");
  assert.equal(diagnostics.queue_authority_reason, "active_profile_post_setup_unavailable");
  assert.equal(diagnostics.queue_authority_health, "degraded");
  assert.equal(diagnostics.count_reconciliation_state, "expected_semantics_unverified");
  assert.equal(diagnostics.expected_count_finalization_gate_active_profile_post_meaningful_attempt_22C13B, "no");
  assert.equal(diagnostics.expected_count_finalization_gate_active_profile_post_effective_attempt_reason_22C13B, "required_query_keys_unavailable");
  assert.equal(diagnostics.active_profile_post_fetch_stop_reason, "required_query_keys_unavailable");
  assert.equal(diagnostics.active_profile_post_fetch_not_attempted_reason, "required_query_keys_unavailable");
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_eligible_22C13B, "yes");
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_attempted_22C13B, "yes");
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_reason_22C13B, "none");
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_wait_ms_22C13B, 600);
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_before_22C13B, 33);
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_target_count_after_22C13B, 33);
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_stop_reason_22C13B, "active_profile_post_response_status_non_zero");
  assert.equal(diagnostics.minimal_scan_active_profile_post_fetch_expected_count_retry_meaningful_attempted_22C13B, "yes");
  assert.equal(diagnostics.scanStop, "network_profile_post_exhausted_without_strong_evidence_22C13B");
  assert.equal(state.layer.profile_scan_ready, false);
  assert.equal(state.status, "failed");
}

{
  const targets = Array.from({ length: 22 }, (_, index) => `76341927335146${String(index).padStart(4, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 1,
      network_probe_unique_aweme_count: 22,
      network_profile_post_unique_count: 22,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:00:${String(index).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 5,
      stop_reason: "stable_no_new_profile_post_ids",
      total_candidates: 22,
      rejected_count: 0,
      diagnostics: {
        expected_profile_video_count: null,
        expected_profile_video_count_semantics_verified: "no",
        minimal_scan_network_probe_post_exhausted_22C11B: "no",
        minimal_scan_network_probe_post_has_more_state_22C11B: null,
        network_collection_stop_reason: "network_post_has_more_false",
        scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 22
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "incomplete");
  assert.equal(diagnostics.lastScannerError, "canonical_expected_count_semantics_unverified");
  assert.equal(diagnostics.network_post_exhausted_evidence_gate_passed_22C12B, "no");
  assert.equal(diagnostics.network_post_continuation_likely_22C13B, "no");
  assert.equal(diagnostics.network_collection_stop_reason_effective, "no + exhaustion_evidence_not_strong");
  assert.equal(diagnostics.scanStop, "network_profile_post_not_exhausted_expected_unverified_22C12B");
  assert.equal(state.layer.profile_scan_ready, false);
  assert.equal(state.status, "failed");
}

{
  const targets = Array.from({ length: 77 }, (_, index) => `76341927335147${String(index).padStart(4, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 2,
      network_probe_unique_aweme_count: 77,
      expected_profile_video_count: 95,
      expected_profile_video_count_raw_text: "作品 95",
      network_profile_post_unique_count: 77,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:01:${String(index % 60).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 7,
      stop_reason: "stable_no_new_profile_post_ids",
      total_candidates: 77,
      rejected_count: 0,
      diagnostics: {
        expected_profile_video_count: 95,
        expected_profile_video_count_raw_text: "作品 95",
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_semantics_verified: "yes",
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 5,
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_batch_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "none",
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "active_profile_post_response_status_non_zero",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_detected_22C13B: "yes",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_allowed_22C13B: "yes",
        scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 77
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.expected_count_gate_dom_only_convergence_allowed, "no");
  assert.equal(diagnostics.expected_count_gate_meaningful_active_fetch, "no");
  assert.equal(diagnostics.expected_count_gate_active_fetch_reason, "active_profile_post_response_status_non_zero");
  assert.equal(diagnostics.queue_source_mode, "dom_scoped_fallback_degraded");
  assert.equal(diagnostics.queue_authority_mode, "dom_scoped_fallback_degraded");
  assert.equal(diagnostics.queue_authority_reason, "active_profile_post_response_status_non_zero");
  assert.equal(diagnostics.queue_authority_health, "degraded");
  assert.equal(diagnostics.scanStop, "active_profile_post_response_status_non_zero_below_expected");
  assert.notEqual(diagnostics.scanStop, "scroll_converged_queue_below_expected_22C11B");
  assert.equal(state.layer.profile_scan_ready, false);
  assert.equal(state.status, "failed");
}

{
  const targets = Array.from({ length: 77 }, (_, index) => `76341927335148${String(index).padStart(4, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 2,
      network_probe_unique_aweme_count: 77,
      expected_profile_video_count: 95,
      expected_profile_video_count_raw_text: "作品 95",
      network_profile_post_unique_count: 77,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:02:${String(index % 60).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 7,
      stop_reason: "stable_no_new_profile_post_ids",
      total_candidates: 77,
      rejected_count: 0,
      diagnostics: {
        expected_profile_video_count: 95,
        expected_profile_video_count_raw_text: "作品 95",
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_semantics_verified: "yes",
        minimal_scan_active_profile_post_template_found_22C13B: "no",
        minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: "no",
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "required_query_keys_unavailable",
        minimal_scan_active_profile_post_fetch_not_attempted_reason_22C12B: "required_query_keys_unavailable",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_detected_22C13B: "yes",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_allowed_22C13B: "yes",
        scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 77
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.expected_count_gate_dom_only_convergence_allowed, "no");
  assert.equal(diagnostics.expected_count_gate_meaningful_active_fetch, "no");
  assert.equal(diagnostics.expected_count_gate_active_fetch_reason, "required_query_keys_unavailable");
  assert.equal(diagnostics.queue_source_mode, "dom_scoped_fallback_degraded");
  assert.equal(diagnostics.queue_authority_mode, "dom_scoped_fallback_degraded");
  assert.equal(diagnostics.queue_authority_reason, "active_profile_post_setup_unavailable");
  assert.equal(diagnostics.queue_authority_health, "degraded");
  assert.equal(diagnostics.scanStop, "active_profile_post_required_query_keys_unavailable_below_expected");
  assert.equal(state.layer.profile_scan_ready, false);
  assert.equal(state.status, "failed");
}

{
  const targets = Array.from({ length: 77 }, (_, index) => `76341927335149${String(index).padStart(4, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 2,
      network_probe_unique_aweme_count: 77,
      expected_profile_video_count: 95,
      expected_profile_video_count_raw_text: "作品 95",
      network_profile_post_unique_count: 77,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:03:${String(index % 60).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 7,
      stop_reason: "network_post_has_more_false",
      total_candidates: 77,
      rejected_count: 0,
      diagnostics: {
        expected_profile_video_count: 95,
        expected_profile_video_count_raw_text: "作品 95",
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_semantics_verified: "yes",
        minimal_scan_network_probe_post_exhausted_22C11B: "yes",
        minimal_scan_network_probe_post_has_more_state_22C11B: false,
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 0,
        minimal_scan_active_profile_post_fetch_response_shape_22C12B: "ok",
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 77,
        minimal_scan_active_profile_post_fetch_batch_count_22C12B: 1,
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "data.aweme_list",
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 1,
        minimal_scan_active_profile_post_fetch_has_more_state_22C12B: false,
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "network_post_has_more_false",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_detected_22C13B: "yes",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_allowed_22C13B: "yes",
        scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 77
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.expected_count_gate_dom_only_convergence_allowed, "yes");
  assert.equal(diagnostics.expected_count_gate_meaningful_active_fetch, "yes");
  assert.equal(diagnostics.expected_count_gate_active_fetch_reason, "active_profile_post_usable");
  assert.equal(diagnostics.queue_source_mode, "active_profile_post_only");
  assert.equal(diagnostics.queue_authority_mode, "active_profile_post_only");
  assert.equal(diagnostics.queue_authority_reason, "active_profile_post_usable");
  assert.equal(diagnostics.queue_authority_health, "healthy");
  assert.equal(diagnostics.queue_authority_source_mix_checked, "yes");
  assert.equal(diagnostics.queue_authority_non_active_queue_source_count, 0);
  assert.equal(diagnostics.queue_authority_non_active_target_source_count, 0);
  assert.equal(diagnostics.scanStop, "network_profile_post_exhausted_below_expected_22C12B");
  assert.equal(diagnostics.expected_gap_count, 18);
  assert.equal(diagnostics.terminal_small_gap_reclassified, "no");
  assert.equal(diagnostics.terminal_small_gap_reason, null);
  assert.equal(diagnostics.scan_stop_authoritative, diagnostics.scanStop);
  assert.equal(diagnostics.scan_stop_authority_source, "canonical_terminal_reconciliation");
  assert.equal(diagnostics.scan_stop_authority_version, "22C-13D");
  assert.equal(diagnostics.scan_stop_authority_migrated, "yes");
  assert.equal(diagnostics.scan_stop, diagnostics.scanStop);
  assert.equal(state.layer.profile_scan_ready, false);
  assert.equal(state.status, "failed");
}

{
  const targets = Array.from({ length: 983 }, (_, index) => `76341927335150${String(index).padStart(5, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 10,
      network_probe_unique_aweme_count: 983,
      expected_profile_video_count: 984,
      expected_profile_video_count_raw_text: "作品 984",
      network_profile_post_unique_count: 983,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:04:${String(index % 60).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 30,
      stop_reason: "network_post_has_more_false",
      total_candidates: 983,
      rejected_count: 0,
      diagnostics: {
        expected_profile_video_count: 984,
        expected_profile_video_count_raw_text: "作品 984",
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_semantics_verified: "yes",
        minimal_scan_network_probe_post_exhausted_22C11B: "yes",
        minimal_scan_network_probe_post_has_more_state_22C11B: false,
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 0,
        minimal_scan_active_profile_post_fetch_response_shape_22C12B: "ok",
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 983,
        minimal_scan_active_profile_post_fetch_batch_count_22C12B: 30,
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "data.aweme_list",
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 1,
        minimal_scan_active_profile_post_fetch_has_more_state_22C12B: false,
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "network_post_has_more_false",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_detected_22C13B: "yes",
        minimal_scan_expected_count_finalization_gate_dom_only_convergence_allowed_22C13B: "yes",
        scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        network_profile_post_unique_count: 983
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "completed_with_warning");
  assert.equal(diagnostics.lastScannerError, "none");
  assert.equal(diagnostics.expected_profile_video_count, 984);
  assert.equal(diagnostics.profile_queue_total_count, 983);
  assert.equal(diagnostics.expected_gap_count, 1);
  assert.equal(diagnostics.expected_gap_ratio, 1 / 984);
  assert.equal(diagnostics.expected_gap_small_threshold_count, 5);
  assert.equal(diagnostics.expected_gap_small_threshold_ratio, 0.01);
  assert.equal(diagnostics.tail_reconcile_attempted, "yes");
  assert.equal(diagnostics.tail_reconcile_added, 0);
  assert.equal(diagnostics.tail_reconcile_reason, "no_valid_missing_candidates");
  assert.equal(diagnostics.expected_gap_recovery_checked, "yes");
  assert.deepEqual(diagnostics.expected_gap_recovery_sources_checked, ["passive_profile_post_network_22C14E", "dom_profile_probe_tail_reconcile_candidates_22C14E"]);
  assert.equal(diagnostics.final_gap_reconciliation_result, "no_valid_missing_candidates");
  assert.equal(diagnostics.final_gap_passive_profile_post_count, 0);
  assert.equal(diagnostics.final_gap_terminal_has_more, "false");
  assert.equal(diagnostics.expected_gap_recovery_unrecoverable_reason, "no_reliable_same_profile_final_gap_candidates");
  assert.equal(diagnostics.terminal_small_gap_reclassified, "yes");
  assert.equal(diagnostics.terminal_small_gap_reason, "expected_gap_unresolved_after_terminal_reconcile");
  assert.equal(diagnostics.scanStop, "network_profile_post_exhausted_below_expected_small_gap_22C14C");
  assert.equal(state.layer.profile_scan_ready, true);
  assert.equal(state.status, "verified");
}

{
  const targets = Array.from({ length: 990 }, (_, index) => `76341927335151${String(index).padStart(5, "0")}`);
  const missing = Array.from({ length: 5 }, (_, index) => `76341927335152${String(index).padStart(5, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      expected_profile_video_count: 995,
      expected_profile_video_count_raw_text: "作品 995",
      network_profile_post_unique_count: 990,
      network_profile_post_targets: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post" }))
    },
    tailReconcileCandidates: missing.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", caption: "tail", thumbnail_url: null })),
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 30,
      stop_reason: "network_post_has_more_false",
      diagnostics: {
        expected_profile_video_count: 995,
        expected_profile_video_count_raw_text: "作品 995",
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_semantics_verified: "yes",
        minimal_scan_network_probe_post_exhausted_22C11B: "yes",
        minimal_scan_network_probe_post_has_more_state_22C11B: false,
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 0,
        minimal_scan_active_profile_post_fetch_response_shape_22C12B: "ok",
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 990,
        minimal_scan_active_profile_post_fetch_batch_count_22C12B: 30,
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "data.aweme_list",
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 1,
        minimal_scan_active_profile_post_fetch_has_more_state_22C12B: false,
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "network_post_has_more_false",
        scan_engine_used: "minimal_network_first_profile_post_scanner_22C12B",
        queue_discovery_source: "active_works_grid_22C11B"
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "success");
  assert.equal(diagnostics.profile_queue_total_count, 995);
  assert.equal(diagnostics.expected_gap_count, 0);
  assert.equal(diagnostics.tail_reconcile_attempted, "yes");
  assert.equal(diagnostics.tail_reconcile_candidates, 5);
  assert.equal(diagnostics.tail_reconcile_added, 5);
  assert.equal(diagnostics.tail_reconcile_rejected, 0);
  assert.equal(diagnostics.tail_reconcile_reason, "expected_gap_filled");
  assert.equal(diagnostics.final_gap_reconciliation_attempted, "yes");
  assert.equal(diagnostics.final_gap_recovered_count, 5);
  assert.equal(diagnostics.final_gap_unrecovered_count, 0);
  assert.equal(diagnostics.final_gap_dom_anchor_count, 5);
  assert.equal(diagnostics.final_gap_passive_profile_post_count, 0);
  assert.equal(diagnostics.final_gap_missing_count_before_reconcile, 5);
  assert.equal(diagnostics.final_gap_missing_count_after_reconcile, 0);
  assert.equal(state.layer.profile_scan_ready, true);
  assert.equal(state.status, "verified");
}

{
  const targets = Array.from({ length: 990 }, (_, index) => `76341927335153${String(index).padStart(5, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 995, expected_profile_video_count_raw_text: "作品 995", network_profile_post_unique_count: 990, network_profile_post_targets: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })) },
    tailReconcileCandidates: [],
    scannerResponse: { ok: true, verified_targets: targets, verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })), scan_rounds: 50, stop_reason: "network_post_has_more_false", diagnostics: { expected_profile_video_count: 995, expected_profile_video_count_raw_text: "作品 995", expected_profile_video_count_source: "active_works_tab_text", expected_profile_video_count_semantics_verified: "yes", minimal_scan_network_probe_post_exhausted_22C11B: "yes", minimal_scan_network_probe_post_has_more_state_22C11B: false, minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 0, minimal_scan_active_profile_post_fetch_response_shape_22C12B: "ok", minimal_scan_active_profile_post_fetch_target_count_22C12B: 990, minimal_scan_active_profile_post_fetch_request_count_22C12B: 50, minimal_scan_active_profile_post_fetch_batch_count_22C12B: 50, minimal_scan_active_profile_post_fetch_raw_items_total_22C14P: 995, minimal_scan_active_profile_post_fetch_raw_aweme_ids_total_22C14P: 990, minimal_scan_active_profile_post_fetch_accepted_targets_total_22C14P: 990, minimal_scan_active_profile_post_fetch_duplicate_drop_count_22C14P: 0, minimal_scan_active_profile_post_fetch_missing_aweme_id_count_22C14P: 5, minimal_scan_active_profile_post_fetch_per_page_raw_counts_22C14P: Array.from({ length: 50 }, (_, index) => index === 49 ? 15 : 20), minimal_scan_active_profile_post_fetch_per_page_aweme_id_counts_22C14P: Array.from({ length: 50 }, (_, index) => index === 49 ? 10 : 20), minimal_scan_active_profile_post_fetch_per_page_accepted_counts_22C14P: Array.from({ length: 50 }, (_, index) => index === 49 ? 10 : 20), minimal_scan_active_profile_post_fetch_per_page_has_more_22C14P: Array.from({ length: 50 }, (_, index) => index < 49), minimal_scan_active_profile_post_fetch_per_page_cursor_present_22C14P: Array.from({ length: 50 }, (_, index) => index < 49), minimal_scan_active_profile_post_fetch_per_page_status_codes_22C14P: Array.from({ length: 50 }, () => 0), minimal_scan_active_profile_post_fetch_parser_route_22C12B: "data.aweme_list", minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 1, minimal_scan_active_profile_post_fetch_has_more_state_22C12B: false, minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "network_post_has_more_false" } }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "completed_with_warning");
  assert.equal(diagnostics.tail_reconcile_attempted, "yes");
  assert.equal(diagnostics.tail_reconcile_added, 0);
  assert.equal(diagnostics.expected_gap_count, 5);
  assert.equal(diagnostics.expected_gap_recovery_checked, "yes");
  assert.equal(diagnostics.scan_job_page_count, 50, "canonical scan job page_count must come from real active profile-post diagnostics");
  assert.equal(diagnostics.scan_job_request_count, 50, "canonical scan job request_count must come from real active profile-post diagnostics");
  assert.equal(diagnostics.api_pagination_page_count, 50, "final diagnostics must preserve real API pagination page count");
  assert.equal(diagnostics.api_pagination_request_count, 50, "final diagnostics must preserve real API pagination request count");
  assert.equal(diagnostics.active_profile_post_fetch_page_count, 50, "popup-visible active fetch page count must mirror real API pagination pages");
  assert.equal(diagnostics.active_profile_post_fetch_request_count, 50, "popup-visible active fetch request count must mirror real API pagination requests");
  assert.equal(diagnostics.active_profile_post_fetch_target_count, 990, "popup-visible active fetch target count must mirror accepted API targets");
  assert.equal(diagnostics.api_pagination_raw_items_total, 995, "canonical finalizer must persist real active profile-post raw accounting");
  assert.equal(diagnostics.api_pagination_raw_aweme_ids_total, 990);
  assert.equal(diagnostics.api_pagination_accepted_targets_total, 990);
  assert.deepEqual(diagnostics.api_pagination_per_page_raw_counts, Array.from({ length: 50 }, (_, index) => index === 49 ? 15 : 20));
  assert.deepEqual(diagnostics.api_pagination_per_page_accepted_counts, Array.from({ length: 50 }, (_, index) => index === 49 ? 10 : 20));
  assert.equal((diagnostics.api_pagination_per_page_persisted_totals as unknown[]).length, 50);
  assert.equal((diagnostics.api_pagination_per_page_persisted_totals as unknown[])[49], 990);
  assert.equal(diagnostics.api_pagination_last_page_raw_count, 15);
  assert.equal(diagnostics.api_pagination_last_page_accepted_count, 10);
  assert.equal(diagnostics.api_pagination_repository_write_total_after, 990);
  assert.equal(diagnostics.final_gap_count, 5);
  assert.equal(diagnostics.final_gap_reason, "parser_extracted_fewer_than_raw", "positive final gap with missing raw aweme ids must use explicit parser-drop reason");
  assert.equal(diagnostics.final_gap_classification, "parser_drop");
  assert.match(String(diagnostics.final_gap_evidence), /page_count=50; request_count=50/, "gap evidence must include page/request accounting");
  assert.deepEqual(diagnostics.expected_gap_recovery_sources_checked, ["passive_profile_post_network_22C14E", "dom_profile_probe_tail_reconcile_candidates_22C14E"]);
  assert.equal(diagnostics.final_gap_reconciliation_result, "no_valid_missing_candidates");
  assert.equal(diagnostics.expected_gap_recovery_unrecoverable_reason, "no_reliable_same_profile_final_gap_candidates");
  assert.equal(diagnostics.terminal_small_gap_reason, "expected_gap_unresolved_after_terminal_reconcile");
  assert.equal(state.layer.profile_scan_ready, true);
}

{
  const targets = Array.from({ length: 900 }, (_, index) => `76341927335154${String(index).padStart(5, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 995, expected_profile_video_count_raw_text: "作品 995", network_profile_post_unique_count: 900, network_profile_post_targets: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })) },
    tailReconcileCandidates: [],
    scannerResponse: { ok: true, verified_targets: targets, verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })), scan_rounds: 30, stop_reason: "network_post_has_more_false", diagnostics: { expected_profile_video_count: 995, expected_profile_video_count_raw_text: "作品 995", expected_profile_video_count_source: "active_works_tab_text", expected_profile_video_count_semantics_verified: "yes", minimal_scan_network_probe_post_exhausted_22C11B: "yes", minimal_scan_network_probe_post_has_more_state_22C11B: false, minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 0, minimal_scan_active_profile_post_fetch_response_shape_22C12B: "ok", minimal_scan_active_profile_post_fetch_target_count_22C12B: 900, minimal_scan_active_profile_post_fetch_batch_count_22C12B: 30, minimal_scan_active_profile_post_fetch_parser_route_22C12B: "data.aweme_list", minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 1, minimal_scan_active_profile_post_fetch_has_more_state_22C12B: false, minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "network_post_has_more_false" } }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "incomplete");
  assert.equal(diagnostics.tail_reconcile_attempted, "yes");
  assert.equal(diagnostics.expected_gap_count, 95);
  assert.equal(diagnostics.terminal_small_gap_reclassified, "no");
  assert.equal(state.layer.profile_scan_ready, false);
}

{
  const targets = Array.from({ length: 990 }, (_, index) => `76341927335155${String(index).padStart(5, "0")}`);
  const otherProfileMissing = Array.from({ length: 5 }, (_, index) => `76341927335156${String(index).padStart(5, "0")}`);
  const { values } = installChromeForScanTest({
    probeDiagnostics: { expected_profile_video_count: 995, expected_profile_video_count_raw_text: "作品 995", network_profile_post_unique_count: 990, network_profile_post_targets: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })) },
    tailReconcileCandidates: otherProfileMissing.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/OTHERPROFILE" })),
    scannerResponse: { ok: true, verified_targets: targets, verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })), scan_rounds: 30, stop_reason: "network_post_has_more_false", diagnostics: { expected_profile_video_count: 995, expected_profile_video_count_raw_text: "作品 995", expected_profile_video_count_source: "active_works_tab_text", expected_profile_video_count_semantics_verified: "yes", minimal_scan_network_probe_post_exhausted_22C11B: "yes", minimal_scan_network_probe_post_has_more_state_22C11B: false, minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 0, minimal_scan_active_profile_post_fetch_response_shape_22C12B: "ok", minimal_scan_active_profile_post_fetch_target_count_22C12B: 990, minimal_scan_active_profile_post_fetch_batch_count_22C12B: 30, minimal_scan_active_profile_post_fetch_parser_route_22C12B: "data.aweme_list", minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 1, minimal_scan_active_profile_post_fetch_has_more_state_22C12B: false, minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "network_post_has_more_false" } }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "completed_with_warning");
  assert.equal(diagnostics.tail_reconcile_candidates, 5);
  assert.equal(diagnostics.tail_reconcile_added, 0);
  assert.equal(diagnostics.tail_reconcile_rejected, 5);
  assert.equal(diagnostics.expected_gap_recovery_unrecoverable_reason, "final_gap_candidates_not_same_profile_invalid_or_duplicate");
  assert.equal(diagnostics.final_gap_other_profile_drop_count, 5);
  assert.equal(diagnostics.profile_queue_total_count, 990);
}

{
  const targets = ["7634192733514501001", "7634192733514501002", "7634192733514501003"];
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 1,
      network_probe_unique_aweme_count: 3,
      network_profile_post_unique_count: 3,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: targets.map((aweme_id, index) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD", endpoint_path: "/aweme/v1/web/aweme/post/", endpoint_kind: "profile_post", captured_at: `2026-05-14T05:00:${String(index).padStart(2, "0")}.000Z`, trace_version: "22C-12A-R3" })),
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: {
      ok: true,
      verified_targets: targets,
      verified_target_details: targets.map((aweme_id) => ({ aweme_id, source_url: `https://www.douyin.com/video/${aweme_id}`, profile_url: "https://www.douyin.com/user/MS4wLjABCD" })),
      scan_rounds: 1,
      stop_reason: "network_post_has_more_false",
      diagnostics: {
        expected_profile_video_count: 2,
        expected_profile_video_count_raw_text: "作品 2",
        expected_profile_video_count_source: "active_works_tab_text",
        expected_profile_video_count_semantics_verified: "yes",
        scan_engine_used: "minimal_active_works_grid_scanner_22C11B",
        scan_queue_builder_used: "scan_queue_adapter_22C11B",
        queue_discovery_source: "active_works_grid_22C11B",
        minimal_scan_active_profile_post_fetch_enabled_22C12B: "yes",
        minimal_scan_active_profile_post_fetch_attempted_22C12B: "yes",
        minimal_scan_active_profile_post_fetch_request_count_22C12B: 2,
        minimal_scan_active_profile_post_fetch_batch_count_22C12B: 1,
        minimal_scan_active_profile_post_fetch_target_count_22C12B: 3,
        minimal_scan_active_profile_post_fetch_has_more_state_22C12B: false,
        minimal_scan_active_profile_post_fetch_stop_reason_22C12B: "network_post_has_more_false",
        minimal_scan_active_profile_post_only_aweme_count_22C12B: 1,
        active_profile_post_fetch_page_count: 1,
        active_profile_post_fetch_page_cap: 60,
        active_profile_post_fetch_page_cap_hit_count: 0,
        active_profile_post_fetch_page_cap_hit_while_has_more_count: 0,
        active_profile_post_fetch_runtime_timeout_ms: 12000,
        active_profile_post_fetch_runtime_timeout_hit: "no",
        active_profile_post_fetch_continuation_policy: "has_more_driven_22C13B",
        active_profile_post_fetch_fallback_cycle_eligible: "yes",
        active_profile_post_fetch_fallback_cycle_attempted: "no",
        active_profile_post_fetch_fallback_cycle_stop_reason: "none",
        active_profile_post_fetch_fallback_cycle_has_more_state: "unknown",
        active_profile_post_fetch_fallback_cycle_request_count: 0,
        active_profile_post_fetch_fallback_cycle_batch_count: 0,
        minimal_scan_active_profile_post_fetch_endpoint_variant_attempt_count_22C12B: 2,
        minimal_scan_active_profile_post_fetch_endpoint_variant_success_22C12B: "/aweme/v1/web/aweme/post/",
        minimal_scan_active_profile_post_fetch_endpoint_attempt_samples_22C12B: [
          { page: 1, endpoint_path: "/aweme/v1/web/aweme/post", result: "response_not_ok", status: 404 },
          { page: 1, endpoint_path: "/aweme/v1/web/aweme/post/", result: "batch_ok", status: 200, parser_route: "fallback:data" }
        ],
        minimal_scan_active_profile_post_fetch_parser_route_22C12B: "fallback:data",
        minimal_scan_active_profile_post_fetch_parser_routes_tried_22C12B: ["primary_payload", "fallback:data"],
        minimal_scan_active_profile_post_fetch_parser_direct_routes_tried_22C12B: ["primary_payload", "direct:data", "direct:data.aweme_list"],
        minimal_scan_active_profile_post_fetch_parser_direct_match_count_22C12B: 0,
        minimal_scan_active_profile_post_fetch_parser_fallback_attempted_22C12B: "yes",
        minimal_scan_active_profile_post_fetch_parser_fallback_match_count_22C12B: 1,
        minimal_scan_active_profile_post_fetch_parser_fallback_candidate_count_22C12B: 2,
        minimal_scan_active_profile_post_fetch_parser_fallback_visited_nodes_22C12B: 4,
        minimal_scan_active_profile_post_fetch_error_22C12B: null,
        minimal_scan_active_profile_post_fetch_response_shape_22C12B: "ok",
        minimal_scan_active_profile_post_template_found_22C13B: "yes",
        minimal_scan_active_profile_post_template_source_22C13B: "performance_resource",
        minimal_scan_active_profile_post_template_endpoint_path_22C13B: "/aweme/v1/web/aweme/post/",
        minimal_scan_active_profile_post_template_query_keys_22C13B: ["sec_user_id", "max_cursor", "count", "msToken"],
        minimal_scan_active_profile_post_template_required_query_keys_22C13B: ["sec_user_id", "count", "max_cursor"],
        minimal_scan_active_profile_post_template_required_query_keys_available_22C13B: "yes",
        minimal_scan_active_profile_post_template_missing_required_query_keys_22C13B: [],
        minimal_scan_active_profile_post_template_secret_keys_present_22C13B: "yes",
        minimal_scan_active_profile_post_template_secret_query_keys_22C13B: ["msToken"],
        minimal_scan_active_profile_post_fetch_response_status_code_22C13B: 0,
        minimal_scan_active_profile_post_fetch_response_status_msg_22C13B: "success",
        minimal_scan_active_profile_post_fetch_response_top_level_keys_22C13B: ["status_code", "status_msg", "data", "extra"],
        minimal_scan_active_profile_post_fetch_response_data_keys_22C13B: ["aweme_list", "has_more", "max_cursor", "min_cursor"],
        minimal_scan_active_profile_post_fetch_response_result_keys_22C13B: [],
        minimal_scan_active_profile_post_fetch_parser_path_counts_22C13B: {
          "data.aweme_list": 1,
          "result.aweme_list": "2",
          "invalid.value": "NaN"
        },
        minimal_scan_active_profile_post_fetch_list_sample_keys_22C13B: ["aweme_id", "desc", "author"],
        minimal_scan_active_profile_post_fetch_reject_reasons_22C13B: ["response_not_ok", "extractor_no_targets", "active_profile_post_response_status_non_zero"]
      }
    }
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "success");
  assert.equal(diagnostics.lastScannerError, "none");
  assert.equal(diagnostics.expected_count_gate_meaningful_active_fetch, "yes");
  assert.equal(diagnostics.expected_count_gate_active_fetch_reason, "active_profile_post_usable");
  assert.equal(diagnostics.profile_queue_total_count, 3);
  assert.equal(diagnostics.expected_profile_video_count, 2);
  assert.equal(diagnostics.missing_profile_video_count, 0);
  assert.equal(diagnostics.over_collected_count, 1);
  assert.equal(diagnostics.count_delta, 1);
  assert.equal(diagnostics.profile_scan_completion_ratio, "3/2");
  assert.equal(diagnostics.count_reconciliation_state, "over_collected");
  assert.equal(diagnostics.scanStop, "network_profile_post_queue_above_expected_accepted_22C12B");
  assert.equal(diagnostics.scan_stop_authoritative, diagnostics.scanStop);
  assert.equal(diagnostics.scan_stop_authority_source, "canonical_terminal_reconciliation");
  assert.equal(diagnostics.scan_stop_authority_version, "22C-13D");
  assert.equal(diagnostics.scan_stop_authority_migrated, "yes");
  assert.equal(diagnostics.scan_stop, diagnostics.scanStop);
  assert.equal(diagnostics.active_works_tab_filter_result, "accepted_overcollection");
  assert.equal(diagnostics.active_profile_post_fetch_enabled, "yes");
  assert.equal(diagnostics.active_profile_post_fetch_attempted, "yes");
  assert.equal(diagnostics.active_profile_post_fetch_stop_reason, "network_post_has_more_false");
  assert.equal(diagnostics.active_profile_post_fetch_not_attempted_reason, "none");
  assert.equal(diagnostics.active_profile_post_fetch_target_count, 3);
  assert.equal(diagnostics.active_profile_post_fetch_has_more_state, "false");
  assert.equal(diagnostics.active_profile_post_only_aweme_count, 1);
  assert.equal(diagnostics.active_profile_post_fetch_request_count, 2);
  assert.equal(diagnostics.active_profile_post_fetch_batch_count, 1);
  assert.equal(diagnostics.active_profile_post_fetch_page_count, 1);
  assert.equal(diagnostics.active_profile_post_fetch_page_cap, 60);
  assert.equal(diagnostics.active_profile_post_fetch_page_cap_hit_count, 0);
  assert.equal(diagnostics.active_profile_post_fetch_page_cap_hit_while_has_more_count, 0);
  assert.equal(diagnostics.active_profile_post_fetch_runtime_timeout_ms, 12000);
  assert.equal(diagnostics.active_profile_post_fetch_runtime_timeout_hit, "no");
  assert.equal(diagnostics.active_profile_post_fetch_continuation_policy, "has_more_driven_22C13B");
  assert.equal(diagnostics.active_profile_post_fetch_fallback_cycle_eligible, "yes");
  assert.equal(diagnostics.active_profile_post_fetch_fallback_cycle_attempted, "no");
  assert.equal(diagnostics.active_profile_post_fetch_fallback_cycle_stop_reason, "none");
  assert.equal(diagnostics.active_profile_post_fetch_fallback_cycle_has_more_state, "unknown");
  assert.equal(diagnostics.active_profile_post_fetch_fallback_cycle_request_count, 0);
  assert.equal(diagnostics.active_profile_post_fetch_fallback_cycle_batch_count, 0);
  assert.equal(diagnostics.active_profile_post_fetch_error, "none");
  assert.equal(diagnostics.active_profile_post_fetch_response_shape, "ok");
  assert.equal(diagnostics.active_profile_post_fetch_endpoint_variant_attempt_count, 2);
  assert.equal(diagnostics.active_profile_post_fetch_endpoint_variant_success, "/aweme/v1/web/aweme/post/");
  assert.deepEqual(diagnostics.active_profile_post_fetch_parser_routes_tried, ["primary_payload", "fallback:data"]);
  assert.equal(diagnostics.active_profile_post_fetch_parser_route, "fallback:data");
  assert.equal(
    Array.isArray(diagnostics.active_profile_post_fetch_parser_direct_routes_tried)
      && (diagnostics.active_profile_post_fetch_parser_direct_routes_tried as unknown[]).includes("direct:data.aweme_list"),
    true
  );
  assert.equal(diagnostics.active_profile_post_fetch_parser_direct_match_count, 0);
  assert.equal(diagnostics.active_profile_post_fetch_parser_fallback_attempted, "yes");
  assert.equal(diagnostics.active_profile_post_fetch_parser_fallback_match_count, 1);
  assert.equal(diagnostics.active_profile_post_fetch_parser_fallback_candidate_count, 2);
  assert.equal(diagnostics.active_profile_post_fetch_parser_fallback_visited_nodes, 4);
  const endpointAttemptSamples = diagnostics.active_profile_post_fetch_endpoint_attempt_samples as Record<string, unknown>[];
  assert.equal(Array.isArray(endpointAttemptSamples), true);
  assert.equal(endpointAttemptSamples.length, 2);
  assert.equal(diagnostics.active_profile_post_template_found, "yes");
  assert.equal(diagnostics.active_profile_post_template_source, "performance_resource");
  assert.equal(diagnostics.active_profile_post_template_endpoint_path, "/aweme/v1/web/aweme/post/");
  assert.deepEqual(diagnostics.active_profile_post_template_query_keys, ["sec_user_id", "max_cursor", "count", "msToken"]);
  assert.deepEqual(diagnostics.active_profile_post_template_required_query_keys, ["sec_user_id", "count", "max_cursor"]);
  assert.equal(diagnostics.active_profile_post_template_required_query_keys_available, "yes");
  assert.deepEqual(diagnostics.active_profile_post_template_missing_required_query_keys, []);
  assert.equal(diagnostics.active_profile_post_template_secret_keys_present, "yes");
  assert.deepEqual(diagnostics.active_profile_post_template_secret_query_keys, ["msToken"]);
  assert.equal(diagnostics.active_profile_post_fetch_response_status_code, 0);
  assert.equal(diagnostics.active_profile_post_fetch_response_status_msg, "success");
  assert.deepEqual(diagnostics.active_profile_post_fetch_response_top_level_keys, ["status_code", "status_msg", "data", "extra"]);
  assert.deepEqual(diagnostics.active_profile_post_fetch_response_data_keys, ["aweme_list", "has_more", "max_cursor", "min_cursor"]);
  assert.deepEqual(diagnostics.active_profile_post_fetch_response_result_keys, []);
  assert.deepEqual(diagnostics.active_profile_post_fetch_parser_path_counts, { "data.aweme_list": 1, "result.aweme_list": 2 });
  assert.deepEqual(diagnostics.active_profile_post_fetch_list_sample_keys, ["aweme_id", "desc", "author"]);
  assert.deepEqual(diagnostics.active_profile_post_fetch_reject_reasons, ["response_not_ok", "extractor_no_targets", "active_profile_post_response_status_non_zero"]);
  const activeProfilePost = diagnostics.active_profile_post as Record<string, unknown>;
  assert.equal(activeProfilePost.enabled, "yes");
  assert.equal(activeProfilePost.attempted, "yes");
  assert.equal(activeProfilePost.stop_reason, "network_post_has_more_false");
  assert.equal(activeProfilePost.not_attempted_reason, null);
  assert.equal(activeProfilePost.target_count, 3);
  assert.equal(activeProfilePost.has_more_state, "false");
  assert.equal(activeProfilePost.only_aweme_count, 1);
  assert.equal(activeProfilePost.request_count, 2);
  assert.equal(activeProfilePost.batch_count, 1);
  assert.equal(activeProfilePost.page_count, 1);
  assert.equal(activeProfilePost.page_cap, 60);
  assert.equal(activeProfilePost.page_cap_hit_count, 0);
  assert.equal(activeProfilePost.page_cap_hit_while_has_more_count, 0);
  assert.equal(activeProfilePost.runtime_timeout_ms, 12000);
  assert.equal(activeProfilePost.runtime_timeout_hit, "no");
  assert.equal(activeProfilePost.continuation_policy, "has_more_driven_22C13B");
  assert.equal(activeProfilePost.fallback_cycle_eligible, "yes");
  assert.equal(activeProfilePost.fallback_cycle_attempted, "no");
  assert.equal(activeProfilePost.fallback_cycle_stop_reason, null);
  assert.equal(activeProfilePost.fallback_cycle_has_more_state, "unknown");
  assert.equal(activeProfilePost.fallback_cycle_request_count, 0);
  assert.equal(activeProfilePost.fallback_cycle_batch_count, 0);
  assert.equal(activeProfilePost.error, null);
  assert.equal(activeProfilePost.response_shape, "ok");
  assert.equal(activeProfilePost.endpoint_variant_attempt_count, 2);
  assert.equal(activeProfilePost.endpoint_variant_success, "/aweme/v1/web/aweme/post/");
  assert.equal(activeProfilePost.parser_route, "fallback:data");
  assert.deepEqual(activeProfilePost.parser_routes_tried, ["primary_payload", "fallback:data"]);
  assert.equal(Array.isArray(activeProfilePost.parser_direct_routes_tried), true);
  assert.equal((activeProfilePost.parser_direct_routes_tried as unknown[]).includes("direct:data.aweme_list"), true);
  assert.equal(activeProfilePost.parser_direct_match_count, 0);
  assert.equal(activeProfilePost.parser_fallback_attempted, "yes");
  assert.equal(activeProfilePost.parser_fallback_match_count, 1);
  assert.equal(activeProfilePost.parser_fallback_candidate_count, 2);
  assert.equal(activeProfilePost.parser_fallback_visited_nodes, 4);
  assert.equal(Array.isArray(activeProfilePost.endpoint_attempt_samples), true);
  assert.equal(activeProfilePost.template_found, "yes");
  assert.equal(activeProfilePost.template_source, "performance_resource");
  assert.equal(activeProfilePost.template_endpoint_path, "/aweme/v1/web/aweme/post/");
  assert.deepEqual(activeProfilePost.template_query_keys, ["sec_user_id", "max_cursor", "count", "msToken"]);
  assert.deepEqual(activeProfilePost.template_required_query_keys, ["sec_user_id", "count", "max_cursor"]);
  assert.equal(activeProfilePost.template_required_query_keys_available, "yes");
  assert.deepEqual(activeProfilePost.template_missing_required_query_keys, []);
  assert.equal(activeProfilePost.template_secret_keys_present, "yes");
  assert.deepEqual(activeProfilePost.template_secret_query_keys, ["msToken"]);
  assert.equal(activeProfilePost.response_status_code, 0);
  assert.equal(activeProfilePost.response_status_msg, "success");
  assert.deepEqual(activeProfilePost.response_top_level_keys, ["status_code", "status_msg", "data", "extra"]);
  assert.deepEqual(activeProfilePost.response_data_keys, ["aweme_list", "has_more", "max_cursor", "min_cursor"]);
  assert.deepEqual(activeProfilePost.response_result_keys, []);
  assert.deepEqual(activeProfilePost.parser_path_counts, { "data.aweme_list": 1, "result.aweme_list": 2 });
  assert.deepEqual(activeProfilePost.list_sample_keys, ["aweme_id", "desc", "author"]);
  assert.deepEqual(activeProfilePost.reject_reasons, ["response_not_ok", "extractor_no_targets", "active_profile_post_response_status_non_zero"]);
  const profileScanDiagnostics = state.profile_scan.diagnostics as Record<string, unknown>;
  const verifyDiagnostics = state.verify.diagnostics as Record<string, unknown>;
  assert.equal((profileScanDiagnostics.active_profile_post as Record<string, unknown>).attempted, "yes");
  assert.equal((verifyDiagnostics.active_profile_post as Record<string, unknown>).attempted, "yes");
  assert.equal(state.layer.profile_scan_ready, true);
  assert.equal(state.status, "verified");
}

{
  const { values } = installChromeForScanTest({
    probeDiagnostics: {
      network_probe_version: "22C-12A-R3",
      network_probe_installed: "yes",
      network_probe_bridge_ready: "yes",
      network_probe_batches_seen: 0,
      network_probe_unique_aweme_count: 0,
      network_profile_post_unique_count: 0,
      network_favorite_unique_count: 0,
      network_other_aweme_unique_count: 0,
      network_profile_post_targets: [],
      network_favorite_targets: [],
      network_other_aweme_targets: []
    },
    scannerResponse: null
  });
  const accepted = await handleMessage({ type: "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B", traceVersion: "22C-11B", tabContext: { tabId: 777, url: "https://www.douyin.com/user/MS4wLjABCD" } }, {});
  assert.equal(accepted.ok, true);
  await waitForScanFinalization(values);
  const state = values[WHOLE_PROFILE_HARVEST_STATE_KEY] as ReturnType<typeof createWholeProfileHarvestIdleState>;
  const diagnostics = state.debug.last_response_summary as Record<string, unknown>;
  assert.equal(diagnostics.lastScannerResult, "failed");
  assert.equal(diagnostics.lastScannerError, "canonical_scanner_completed_without_result");
  assert.equal(diagnostics.canonical_queue_adapter_invoked, "no");
}

{
  let capturedUrl = "";
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async (url: string) => {
      capturedUrl = url;
      return {
        ok: true,
        status: 200,
        async json() {
          return { success: true, updated_count: 1 };
        }
      };
    }
  });
  const result = await postToBackend({
    base_url: "http://127.0.0.1:8000/",
    path: "/douyin-extension/capture-current-page",
    payload: { ok: true }
  });
  assert.equal(capturedUrl, "http://127.0.0.1:8000/douyin-extension/capture-current-page");
  assert.equal(result.ok, true);
}

{
  let fetchCalls = 0;
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async () => {
      fetchCalls += 1;
      throw new TypeError("Failed to fetch");
    }
  });
  const result = await postToBackend({
    base_url: "http://127.0.0.1:8000",
    path: "/douyin-extension/capture-current-page",
    payload: { ok: true }
  });
  assert.equal(result.ok, false);
  assert.equal(result.error_code, "backend_unreachable");
  assert.equal(fetchCalls, 2);
}

{
  const manifest = JSON.parse(readFileSync(new URL("../public/manifest.json", import.meta.url), "utf8"));
  assert.equal(manifest.permissions.includes("debugger"), true);
  assert.equal(manifest.permissions.includes("storage"), true);
  assert.equal(manifest.permissions.includes("activeTab"), true);
  assert.equal(manifest.permissions.includes("scripting"), true);
  assert.equal(manifest.content_scripts[0].matches.includes("https://www.douyin.com/*"), true);
  assert.equal(manifest.content_scripts[0].js.includes("contentScript.js"), true);
}

{
  const calls: string[] = [];
  Object.defineProperty(globalThis, "chrome", {
    configurable: true,
    value: {
      ...(globalThis as typeof globalThis & { chrome: Record<string, unknown> }).chrome,
      debugger: {
        attach: async (target: { tabId: number }, version: string) => {
          calls.push(`attach:${target.tabId}:${version}`);
        },
        detach: async (target: { tabId: number }) => {
          calls.push(`detach:${target.tabId}`);
        },
        sendCommand: async (target: { tabId: number }, method: string) => {
          calls.push(`send:${target.tabId}:${method}`);
          return {};
        },
        onEvent: { addListener() {} },
        onDetach: { addListener() {} }
      }
    }
  });
  const status = await startCdpHarvest(123);
  assert.equal(status.attached, true);
  assert.equal(status.tab_id, 123);
  await stopCdpHarvest(123, "test_complete");
  assert.equal(calls.includes("send:123:Network.enable"), true);
  assert.equal(calls.includes("detach:123"), true);
}

{
  const awemeBody = JSON.stringify({
    aweme_list: [
      {
        aweme_id: "7390000000000000001",
        desc: "phase7b exact cdp aweme",
        statistics: { digg_count: 11, comment_count: 22, collect_count: 33, share_count: 44 },
        video: { duration: 123000 },
        create_time: 1700000000
      }
    ]
  });
  Object.defineProperty(globalThis, "chrome", {
    configurable: true,
    value: {
      ...(globalThis as typeof globalThis & { chrome: Record<string, unknown> }).chrome,
      debugger: {
        attach: async () => undefined,
        detach: async () => undefined,
        sendCommand: async (_target: { tabId: number }, method: string) => {
          if (method === "Network.getResponseBody") return { body: awemeBody, base64Encoded: false };
          return {};
        },
        onEvent: { addListener() {} },
        onDetach: { addListener() {} }
      }
    }
  });
  await startCdpHarvest(456);
  await handleCdpEvent(456, "Network.responseReceived", { requestId: "req-1", response: { url: "https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=7390000000000000001" } });
  await handleCdpEvent(456, "Network.loadingFinished", { requestId: "req-1" });
  const afterBody = await startCdpHarvest(456);
  assert.equal(afterBody.response_count, 1);
  assert.equal(afterBody.exact_match_count, 1);
  await stopCdpHarvest(456, "test_cleanup");
}

{
  const backgroundSource = readFileSync(new URL("./background.ts", import.meta.url), "utf8");
  assert.match(backgroundSource, /function scanAuthorityWriteRejection22C14D[\s\S]*terminal_write_lock_active[\s\S]*terminal_write_rejected_source[\s\S]*terminal_write_rejected_stage[\s\S]*terminal_state_blocks_non_terminal_write[\s\S]*older_updated_at[\s\S]*lower_priority_than_terminal_stage/s, "background must reject stale same-run non-terminal writes after terminal authority state with explicit terminal lock diagnostics");
  assert.match(backgroundSource, /async function persistRuntimeDebugStaleRejection22C14D[\s\S]*last_request_summary: debug[\s\S]*last_response_summary: debug/s, "background stale rejection must write only runtime_debug_diagnostics and preserve scan authority containers");
  assert.match(backgroundSource, /const resetScanJob = \{ \.\.\.createPersistentScanJobRecord\(at\), scan_job_id: scanRunId, status: "running" as const, started_at: at, updated_at: at \}/, "scan accepted must reset scan_job from a clean persistent record for the new run");
  assert.match(backgroundSource, /post_scan_counter_snapshot: null[\s\S]*harvest: \{ \.\.\.existing\.harvest, queue: \[\], queue_preview: \[\], planned_total: 0, pending: 0/s, "scan accepted must clear previous terminal counters and queues for the new run");
  assert.match(backgroundSource, /const current = scanAuthorityDiagnostics22C14D\(state\);[\s\S]*withCanonicalActiveProfilePostDiagnostics22C12B\(\{[\s\S]*sanitizeScannerDiagnostics22C11B\(current\)/s, "canonical authority diagnostics must merge only scan_authority_diagnostics, not runtime debug summaries");
  assert.match(backgroundSource, /const previousDiagnostics = diagnosticRecordByChannel22C14C\(current\.debug\.last_request_summary, "runtime_debug_diagnostics"\)/, "paginated checkpoints must keep runtime diagnostics display-only");
  assert.match(backgroundSource, /active_source_terminal_policy[\s\S]*degraded_fallback_attempted_before_terminal_failure[\s\S]*active_source_degraded_fallback_policy[\s\S]*enabled_before_terminalization/s, "active-source terminal failure must attempt deterministic degraded fallback before terminalization");
  const canonicalPersistBody = backgroundSource.match(/async function persistCanonicalScanDiagnostics22C11B\([\s\S]*?\n\}/)?.[0] ?? "";
  const canonicalFailBody = backgroundSource.match(/async function failCanonicalScanProfile22C11B\([\s\S]*?\n\}/)?.[0] ?? "";
  assert.doesNotMatch(canonicalPersistBody, /state\.debug\.last_request_summary[\s\S]*\? state\.debug\.last_request_summary as Record<string, unknown>/s, "canonical progress diagnostics must not fall back to runtime_debug_diagnostics");
  assert.doesNotMatch(canonicalFailBody, /state\.debug\.last_request_summary[\s\S]*\? state\.debug\.last_request_summary as Record<string, unknown>/s, "canonical failure diagnostics must not fall back to runtime_debug_diagnostics");
}

{
  const backgroundSource = readFileSync(new URL("./background.ts", import.meta.url), "utf8");
  assert.match(backgroundSource, /function canonicalForensicVerdictForCurrentRun22C14Q[\s\S]*scanRunId !== currentRunId[\s\S]*finalVerdict === "validated_same_profile"[\s\S]*count_semantics_status: "completed_with_api_over_displayed_count"[\s\S]*scan_health_verdict: "ready_api_over_displayed_count"[\s\S]*profileScanReady: "yes"/s, "background terminal canonical write-through must promote same-run validated_same_profile forensic verdict into ready canonical count semantics");
  assert.match(backgroundSource, /function canonicalForensicVerdictForCurrentRun22C14Q[\s\S]*finalVerdict === "outside_profile_detected"[\s\S]*count_semantics_status: "failed_overcollection_outside_profile"[\s\S]*profileScanReady: "no"/s, "background terminal canonical write-through must keep outside-profile forensic verdict blocking");
  assert.match(backgroundSource, /function canonicalForensicVerdictForCurrentRun22C14Q[\s\S]*finalVerdict === "needs_validation" \|\| finalVerdict === "ledger_incomplete" \|\| finalVerdict === "ledger_missing"[\s\S]*count_semantics_status: "overcollected_needs_validation"[\s\S]*profileScanReady: "no"/s, "background terminal canonical write-through must preserve unresolved forensic verdict blocking");
  assert.match(backgroundSource, /const forensicExportForStorage = responseDiagnostics\.overcollection_forensic_export[\s\S]*const canonicalWithForensicWriteThrough = applyCanonicalForensicVerdictWriteThrough22C14Q\(next, forensicExportForStorage\);[\s\S]*const preparedNext = prepareWholeProfileHarvestStateForStorage22C11B\(canonicalWithForensicWriteThrough\);[\s\S]*chrome\.runtime\.sendMessage\?\.\(\{ type: "douyinScanner:stateChanged", state: preparedNext \}\)/s, "background terminal persistence must write and broadcast the forensic-patched canonical state");
}

{
  const calls: string[] = [];
  Object.defineProperty(globalThis, "chrome", {
    configurable: true,
    value: {
      ...(globalThis as typeof globalThis & { chrome: Record<string, unknown> }).chrome,
      debugger: {
        attach: async () => undefined,
        detach: async () => undefined,
        sendCommand: async (_target: { tabId: number }, method: string) => {
          calls.push(method);
          return {};
        },
        onEvent: { addListener() {} },
        onDetach: { addListener() {} }
      }
    }
  });
  const refreshed = await attachCdpAndReload(789);
  assert.equal(refreshed.attached, true);
  assert.equal(calls.includes("Page.reload"), true);
  await stopCdpHarvest(789, "test_cleanup");
}

console.log("background scan profile 22C-11B, backend post, and cdp lifecycle tests passed");
