import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { applyUnreachableTailGapOfferToState } from "./wholeProfileHarvest/hybridUnreachableTailGap.js";
import { assertAllowedScannerRunnerTarget, buildModalDetailUrl, buildProfileScanQueueFromCandidates22C9J, classifyProfileScanFailure, clearProfileScanState, detectDouyinSafetyBlock, dryRunFirst, extractCaptureInboxItemId, extractCaptureSessionId, flushBatchFromHarvestResults, flushOneItemFromPayloadPreview, getFirstPendingCollectTarget, getNextPendingCollectTarget, isAllowedScannerRunnerTarget, matchesCaptureInboxItemAweme, normalizeProfileDomProbeCandidates22C9J, normalizeProfileDomProbeStatus22C9K, parseCaptureInboxItemSaveResult, readWholeProfileHarvestState, recoverStalePausingLock, requestPauseCollecting, resetScannerWorkflowState, resumeHarvest, resumePendingVerifyAfterProfileNavigation, runBatchCollectNext3SafeMode, runBatchCollectNext10SafeMode, runLegacyVerifiedProfileScrollScan22C9ZNOGIT, runScanProfileWorkflow, runStartCollectingWorkflow, selectNextActionableTargets, validateExtractionContext, verifyProfile, writeWholeProfileHarvestState, type WholeProfileHarvestRuntime } from "./wholeProfileHarvest/controller.js";
import { buildCaptureInboxItemPayload, buildCleanCaptureInboxItemPayload, buildCanonicalBatchFlushQueue, buildCanonicalHarvestQueue, buildCanonicalFullModalPayloadPreview, extractDouyinPostedMetadataFromText, guardCaptureInboxPayload, guardCanonicalHarvestPayload, guardNoSecretDebugLeakage, isLikelyDouyinUiChromeImage, normalizeDouyinPostedRawText, parseDouyinPostedText, parseDouyinPostedTextToDate, resolveAwemeThumbnail, sanitizeCaptureInboxPayloadValue } from "./wholeProfileHarvest/canonicalHarvest.js";
import { getCanonicalScannerPrimaryAction, getDouyinScannerWorkflowReadiness, getWholeProfileHarvestActionState, getWholeProfileHarvestReadiness } from "./wholeProfileHarvest/readiness.js";
import { detectCurrentDouyinProfileIdentity, isDifferentProfile, isDouyinProfileModalUrl, normalizeDouyinProfileUrl, resolveTargetProfileUrlForScan, resolveWholeProfileFromCurrentUrl } from "./wholeProfileHarvest/profileResolver.js";
import { selectDryRunSample } from "./wholeProfileHarvest/dryRun.js";
import { wholeProfileProgressSummary } from "./wholeProfileHarvest/progress.js";
import { getRunTabViewModel, getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";
import { WHOLE_PROFILE_HARVEST_STATE_KEY, createWholeProfileHarvestIdleState, validateScannerState, type WholeProfileHarvestState } from "./wholeProfileHarvest/state.js";
import { DOUYIN_SCANNER_CALIBRATION_KEY, DOUYIN_SCANNER_STORAGE_ROOT_KEY } from "./wholeProfileHarvest/calibration.js";
import type { ModalWholeProfileCardScanResult } from "./modalWholeProfileTest.js";
import type { DouyinProfileVideoClassificationRequest, DouyinProfileVideoClassificationResponse } from "./wholeProfileHarvest/profileClassification.js";

const controllerSource = readFileSync(new URL("./wholeProfileHarvest/controller.ts", import.meta.url), "utf-8");
const popupSource = readFileSync(new URL("./popup.ts", import.meta.url), "utf-8");

/*
 * wholeProfileHarvest.test standards snapshot
 * - Assertion messages: MUST be present for safety-critical invariants and SHOULD use "<scope> must <invariant>".
 * - Duplicate assertions: MUST only be removed when matcher, actual, expected, and coverage are exact semantic duplicates.
 * - Helpers: SHOULD wrap repeated invariant clusters only; keep rare, scenario-specific assertions inline.
 * - Safety-critical invariants: MUST stay explicit for batch limits, queue preservation, runner ownership, backend ID-set guards, and reset lock clearing.
 * - Edit boundaries: MUST remain test-only for cleanup passes; do not touch runtime/controller code to satisfy test-maintenance work.
 * - Validation: MUST run `npm run extension:test` and `npm run extension:build` after edits.
 * - Good messages: "safe batch summary must report next_10_safe mode"; "Next 5 summary must keep effective batch limit at 5";
 *   "backend-captured filter must skip two already captured targets"; "resume runner must record running diagnostics before completion";
 *   "Fix Stuck reset must release persistent collect job lock"; "reset must preserve collect queue";
 *   "unavailable backend IDs summary must block selection"; "Start Collecting default Next 10 must enforce the route contract".
 */

class MemoryStorage {
  values: Record<string, unknown> = {};
  writes: Record<string, unknown>[] = [];

  async get(key: string): Promise<Record<string, unknown>> {
    return { [key]: this.values[key] };
  }

  async set(items: Record<string, unknown>): Promise<void> {
    this.writes.push(items);
    Object.assign(this.values, items);
  }
}

function seedLoggedInAppAuth(storage: MemoryStorage): void {
  storage.values.apiAuthToken = "test-token";
  storage.values.apiAuthRequired = false;
}


function scanResult(): ModalWholeProfileCardScanResult {
  return {
    status: "success",
    reason: null,
    cards: ["7634192733514501001", "7634192733514501002", "7634192733514501003", "7634192733514501004"].map((aweme_id) => ({
      aweme_id,
      source_url: `https://www.douyin.com/video/${aweme_id}`,
      title: null,
      caption: null,
      text_sample: null,
      thumbnail_url: null,
      posted_text: null,
      posted_at: null,
      duration_text: null,
      duration_seconds: null,
      view_text: null,
      view_count: null,
      extraction_source: "anchor_href",
      raw_profile_card: { aweme_id }
    })),
    diagnostics: {
      selector_attempts: [],
      current_url: "https://www.douyin.com/user/MS4wLjABCD",
      target_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
      page_type: "profile",
      modal_id_present: false,
      document_ready_state: "complete",
      body_text_sample: "",
      scroll_y: 0,
      viewport: { width: 1280, height: 720, device_pixel_ratio: 1 },
      candidate_card_count: 4,
      visible_link_count: 4,
      video_aweme_candidate_count: 4,
      grid_container_count: 1,
      empty_state_detected: false,
      login_or_captcha_detected: false,
      rounds: 2,
      scan_rounds: [],
      stop_reason: "stable_no_new_ids",
      scanner_invocation_mode: "content_script_message",
      selected_scroll_container: null,
      scroll_container_candidates: [],
      scroll_container_found: true,
      scroll_container_strategy: "window_fallback",
      selected_profile_tab: null,
      tab_candidates: [],
      warning: null,
      candidate_classifications: [],
      raw_candidate_count: 4,
      accepted_count: 4,
      rejected_count: 0,
      rejected_examples: [],
      candidate_sources_count: { video_link: 4, modal_link: 0, data_attr: 0, card_context_regex: 0, body_regex: 0 },
      expected_profile_video_count: null,
      expected_count_value: null,
      expected_count_source: "unavailable",
      expected_count_profile_url: "https://www.douyin.com/user/MS4wLjABCD",
      expected_count_updated_at: "2026-05-11T09:39:49.592Z",
      expected_count_scan_run_id: "test_scan_run_22C_9",
      scan_run_id: "test_scan_run_22C_9",
      final_found_count: 4,
      missing_expected_count: null,
      bottom_reached: true,
      bottom_bounce_done: true,
      stable_rounds: 3,
      final_aweme_ids: ["7634192733514501001", "7634192733514501002", "7634192733514501003", "7634192733514501004"],
      partial_scan: false,
      per_round: []
    }
  };
}

function classificationResponse(request: DouyinProfileVideoClassificationRequest): DouyinProfileVideoClassificationResponse {
  const statuses = ["new", "incomplete", "complete", "failed"] as const;
  const targets = request.candidates.map((candidate, index) => {
    const classification = statuses[index] ?? "new";
    return {
      aweme_id: candidate.aweme_id,
      classification,
      collect: classification === "new" || classification === "incomplete" || classification === "failed",
      reason: classification,
      required_missing_fields: classification === "incomplete" ? ["duration_seconds"] : [],
      existing_item_id: classification === "new" ? null : `item_${index}`,
      metadata_status: classification === "complete" ? "complete" : classification === "incomplete" ? "incomplete" : null,
      review_status: null,
      video_url: candidate.video_url,
      source_url: candidate.source_url,
      thumbnail_url: candidate.thumbnail_url,
      caption: candidate.caption
    };
  });
  return {
    schema_version: "douyin_profile_video_classification_result.v1",
    profile_url: request.profile_url,
    sec_uid: request.sec_uid,
    collection_mode: request.collection_mode,
    database_lookup_status: "ok",
    total_candidates: request.candidates.length,
    counts: { new: 1, incomplete: 1, complete: 1, failed: 1, skipped: 0, unknown: 0, collect: 3, skip: 1 },
    targets,
    collect_aweme_ids: targets.filter((target) => target.collect).map((target) => target.aweme_id),
    skip_aweme_ids: targets.filter((target) => !target.collect).map((target) => target.aweme_id),
    diagnostics: { fixture: true }
  };
}

function runtime(storage: MemoryStorage, overrides: Partial<WholeProfileHarvestRuntime> = {}): WholeProfileHarvestRuntime {
  const events: string[] = [];
  const flushedAwemeIds = new Set<string>();
  return {
    storage,
    now: () => "2026-05-05T09:00:00.000Z",
    random: () => 0.5,
    async getActiveTab() {
      events.push("getActiveTab");
      return { id: 123, url: "https://www.douyin.com/user/MS4wLjABCD" };
    },
    async ensureContentScriptReady() {
      events.push("ensureContentScriptReady");
      return { ok: true, status: "ready", detector_status: "ready" };
    },
    async getCalibration() {
      return { status: "calibrated", ready: true, layout: "profile_modal", source_url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501001", profile_url: "https://www.douyin.com/user/MS4wLjABCD", aweme_id: "7634192733514501001", points: { like: {}, comment: {}, favorite: {}, share: {} }, point_count: 4, source_key: "douyinRightRailCalibration", viewport_warning: null };
    },
    async scanProfile() {
      events.push("scanProfile");
      return scanResult();
    },
    async classifyProfileVideos(request) {
      events.push("classifyProfileVideos");
      assert.equal(request.schema_version, "douyin_profile_video_classification.v1");
      assert.equal(request.collection_mode, "new_incomplete_failed");
      assert.equal(request.include_unknown, false);
      assert.equal(request.dry_run, true);
      assert.equal(request.candidates.length, 4);
      return classificationResponse(request);
    },
    async openDirectModal(_tabId, targetUrl) {
      events.push(`openDirectModal:${targetUrl}`);
      return;
    },
    async getExtractionContext() {
      const opened = events.find((event) => event.startsWith("openDirectModal:"))?.replace("openDirectModal:", "") ?? "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501001";
      const modalId = new URL(opened).searchParams.get("modal_id");
      return { current_url: opened, page_type: "profile_modal", modal_id: modalId, modal_id_present: Boolean(modalId), metric_rail_visible: true, diagnostics: {} };
    },
    async createCanonicalHarvestSession() {
      return { ok: true, session_id: "session_1", created: true, status: 200, url: "http://127.0.0.1:8000/douyin-extension/capture-session", body: { ok: true, session_id: "session_1", created: true } };
    },
    async detectCaptchaOrCheckpoint() {
      return { detected: false, reason: null, evidence_text: "", current_url: null };
    },
    async flushCanonicalHarvestPayload(payload, _headers) {
      const awemeId = "items" in payload ? payload.items[0]?.aweme_id : payload.aweme_id;
      if (awemeId) flushedAwemeIds.add(awemeId);
      return { ok: true, item_created_or_updated: true, capture_inbox_item_id: "inbox_1", status: 200 };
    },
    async listCaptureSessionItems() {
      return {
        ok: true,
        session_id: "session_1",
        items_count: flushedAwemeIds.size,
        items: Array.from(flushedAwemeIds).map((aweme_id) => ({ aweme_id, id: "inbox_1" })),
        counts: null,
        raw: null
      };
    },
    async listCaptureInboxProfileItems(profileUrl) {
      return {
        ok: true,
        status: 200,
        profile_identifier: "MS4wLjABCD",
        normalized_profile_url: profileUrl,
        items_count: 0,
        counts: { captured: 0, ready: 0, dup: 0, fail: 0 },
        items: [],
        raw: null
      };
    },
    async listCaptureInboxProfileSummary(profileUrl) {
      return {
        ok: true,
        status: 200,
        profile_identifier: "MS4wLjABCD",
        normalized_profile_url: profileUrl,
        total_count: 0,
        counts: { captured: 0, ready: 0, dup: 0, fail: 0, needs_action: 0 },
        source: "capture_inbox_profile_summary",
        raw: null
      };
    },
    async extractModalMetrics(_tabId, awemeId) {
      return {
        duration_seconds: 12,
        duration_text: "00:12",
        like_count: 10,
        comment_count: 2,
        favorite_count: 3,
        share_count: 4,
        current_modal_id_before: awemeId,
        current_modal_id_after: awemeId,
        extracted_aweme_id: awemeId,
        source_used: "calibrated_points"
      };
    },
    ...overrides
  };
}

async function prepareVerifiedDryRunState(storage: MemoryStorage, overrides: Partial<WholeProfileHarvestRuntime> = {}): Promise<void> {
  await verifyProfile(runtime(storage, overrides));
  await dryRunFirst(runtime(storage, overrides));
}

function queuePreview(items: WholeProfileHarvestState["harvest"]["queue"]): WholeProfileHarvestState["harvest"]["queue_preview"] {
  return items.slice(0, 5).map((item, index) => ({
    index,
    aweme_id: item.aweme_id,
    capture_status: item.capture_status,
    source_url: item.source_url,
    title: typeof item.profile_card_evidence?.caption === "string" ? item.profile_card_evidence.caption : null,
    thumbnail_url: typeof item.profile_card_evidence?.thumbnail_url === "string" ? item.profile_card_evidence.thumbnail_url : null
  }));
}

function assertBatchLimit(summary: Record<string, unknown>, requested: number, effective: number, contextLabel: string): void {
  assert.equal(summary.requested_batch_limit, requested, `${contextLabel} must record requested batch limit as ${requested}`);
  assert.equal(summary.effective_batch_limit, effective, `${contextLabel} must keep effective batch limit at ${effective}`);
}

function assertBatchLoopCounts(summary: Record<string, unknown>, expectedCount: number, contextLabel: string): void {
  assert.equal(summary.batch_item_loop_entered, true, `${contextLabel} must record that the item loop entered`);
  assert.equal(summary.batch_item_loop_selected_count, expectedCount, `${contextLabel} must record selected item count as ${expectedCount}`);
  assert.equal(summary.batch_item_loop_attempted_count, expectedCount, `${contextLabel} must record one-item attempts as ${expectedCount}`);
  assert.equal(summary.batch_item_loop_returned_count, expectedCount, `${contextLabel} must record one-item returns as ${expectedCount}`);
  assert.equal(summary.batch_item_loop_result_appended_count, expectedCount, `${contextLabel} must record appended item results as ${expectedCount}`);
  assert.equal(Array.isArray(summary.recent_batch_item_results), true, `${contextLabel} must expose recent item-loop results`);
  assert.equal((summary.recent_batch_item_results as unknown[]).length, expectedCount, `${contextLabel} must keep ${expectedCount} recent item-loop results`);
}

function assertRunnerOwnership(summary: Record<string, unknown>, expectedRunnerType: string, contextLabel: string): void {
  assert.equal(summary.trace_collect_expected_runner_type, expectedRunnerType, `${contextLabel} must declare ${expectedRunnerType} as expected owning runner`);
  assert.equal(summary.trace_collect_actual_runner_type, expectedRunnerType, `${contextLabel} must declare ${expectedRunnerType} as actual owning runner`);
  assert.equal(summary.trace_collect_runner_contract_enforced, "yes", `${contextLabel} must enforce the runner contract`);
  assert.equal(summary.trace_collect_runner_contract_passed, "yes", `${contextLabel} must pass the runner contract`);
}

function assertQueuePreservation(summary: Record<string, unknown>, pendingBefore: number, pendingAfter: number, expectedSaved: number, contextLabel: string): void {
  assert.equal(summary.queue_preserved_after_batch, true, `${contextLabel} must preserve queue structure after processing`);
  assert.equal(summary.pending_count_before_batch, pendingBefore, `${contextLabel} must record pending_count_before_batch as ${pendingBefore}`);
  assert.equal(summary.pending_count_after_batch, pendingAfter, `${contextLabel} must record pending_count_after_batch as ${pendingAfter}`);
  assert.equal(summary.saved_count_after_batch, expectedSaved, `${contextLabel} must record saved_count_after_batch as ${expectedSaved}`);
}

const idle: WholeProfileHarvestState = createWholeProfileHarvestIdleState("2026-05-05T09:00:00.000Z");
assert.equal(idle.schema_version, "phase18i_a_three_layer_harvest_design");
assert.equal(idle.harvest.status, "idle");
assert.equal(extractCaptureSessionId({ session_id: "session_a" }), "session_a");
assert.equal(extractCaptureSessionId({ id: "session_b" }), "session_b");
assert.equal(extractCaptureSessionId({ capture_session_id: "session_c" }), "session_c");
assert.equal(extractCaptureSessionId({ session: { id: "session_d" } }), "session_d");
assert.equal(extractCaptureSessionId({ data: { session_id: "session_e" } }), "session_e");
assert.equal(extractCaptureInboxItemId({ capture_inbox_item_id: "item_a" }), "item_a");
assert.equal(extractCaptureInboxItemId({ item_id: "item_b" }), "item_b");
assert.equal(extractCaptureInboxItemId({ id: "item_c" }), "item_c");
assert.equal(extractCaptureInboxItemId({ item: { id: "item_d" } }), "item_d");
assert.equal(extractCaptureInboxItemId({ data: { item_id: "item_e" } }), "item_e");
assert.deepEqual(parseCaptureInboxItemSaveResult({ item_id: "item_a", created: true, source_video_external_id: "aweme_a", metadata_status: "ready", review_status: "pending_review" }), { itemId: "item_a", created: true, updated: false, sourceVideoExternalId: "aweme_a", metadataStatus: "ready", reviewStatus: "pending_review" });
assert.deepEqual(parseCaptureInboxItemSaveResult({ id: "item_b", updated: true }), { itemId: "item_b", created: false, updated: true, sourceVideoExternalId: null, metadataStatus: null, reviewStatus: null });
assert.equal(parseCaptureInboxItemSaveResult({ item: { id: "item_c", source_video_external_id: "aweme_c" } }).itemId, "item_c");
assert.equal(parseCaptureInboxItemSaveResult({ data: { item_id: "item_d" } }).itemId, "item_d");
assert.equal(parseCaptureInboxItemSaveResult({ result: { item_id: "item_e" }, created: true }).itemId, "item_e");
assert.equal(parseCaptureInboxItemSaveResult({ created: true, updated: false, source_video_external_id: "aweme_f" }).sourceVideoExternalId, "aweme_f");
assert.equal(matchesCaptureInboxItemAweme({ source_video_external_id: "7634192733514501001" }, "7634192733514501001").matchedBy, "source_video_external_id");
assert.equal(matchesCaptureInboxItemAweme({ aweme_id: "7634192733514501001" }, "7634192733514501001").matchedBy, "aweme_id");
assert.equal(matchesCaptureInboxItemAweme({ video_id: "7634192733514501001" }, "7634192733514501001").matchedBy, "video_id");
assert.equal(matchesCaptureInboxItemAweme({ source_url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501001" }, "7634192733514501001").matchedBy, "source_url");
assert.equal(matchesCaptureInboxItemAweme({ external_id: "7634192733514501001" }, "7634192733514501001").matchedBy, "external_id");
assert.equal(matchesCaptureInboxItemAweme({ source: { video_external_id: "7634192733514501001" } }, "7634192733514501001").matchedBy, "source.video_external_id");
assert.equal(matchesCaptureInboxItemAweme({ raw_payload_json: { aweme_id: "7634192733514501001" } }, "7634192733514501001").matchedBy, "raw_payload_json.aweme_id");
assert.equal(isLikelyDouyinUiChromeImage({ url: "https://p3.douyinpic.com/obj/getapp-banner.webp", source: "og_image", alt: "Get APP" }), true);
assert.equal(isLikelyDouyinUiChromeImage({ url: "https://p3.douyinpic.com/obj/logo.png", source: "modal_img", alt: "抖音 logo" }), true);
assert.equal(isLikelyDouyinUiChromeImage({ url: "https://p3.douyinpic.com/obj/avatar.jpeg", source: "modal_img", alt: "头像" }), true);
assert.equal(isLikelyDouyinUiChromeImage({ url: "https://p3.douyinpic.com/obj/video-cover.webp", source: "profile_card", width: 320, height: 568, nearAweme: true }), false);
assert.equal(resolveAwemeThumbnail({ awemeId: "7634192733514501001", target: { profile_card_evidence: { thumbnail_url: "https://p3.douyinpic.com/obj/profile-thumb.webp" } }, extracted: { thumbnail_url: "https://p3.douyinpic.com/obj/modal-thumb.webp" } }).thumbnail_url, "https://p3.douyinpic.com/obj/profile-thumb.webp");
assert.equal(resolveAwemeThumbnail({ awemeId: "7634192733514501001", target: { profile_card_evidence: {} }, candidates: [{ url: "https://p3.douyinpic.com/obj/getapp.webp", source: "og_image", alt: "Get APP", nearAweme: true }, { url: "https://p3.douyinpic.com/obj/poster.webp", source: "video_poster", width: 320, height: 568, nearAweme: true }] }).thumbnail_source, "video_poster");
assert.equal(resolveAwemeThumbnail({ awemeId: "7634192733514501001", target: { profile_card_evidence: {} }, candidates: [{ url: "https://p3.douyinpic.com/obj/app-banner.webp", source: "og_image", alt: "Get App", nearAweme: true }] }).thumbnail_url, null);
assert.deepEqual(extractDouyinPostedMetadataFromText("@地球之旅 · 12小时前").posted_text_raw, "@地球之旅 · 12小时前");
assert.equal(extractDouyinPostedMetadataFromText("发布时间：2026-05-08 06:00").posted_source, "direct_publish_time");
assert.equal(extractDouyinPostedMetadataFromText("发布时间：2026-05-08 06:00").posted_display, "08/05/2026");
assert.equal(parseDouyinPostedText("2026-05-08 06:00"), "2026-05-07T22:00:00.000Z");

const weekReferenceTime = new Date("2026-05-09T08:00:00.000Z");
assert.equal(normalizeDouyinPostedRawText("· 4月28日").raw_normalized, "4月28日");
assert.equal(normalizeDouyinPostedRawText("@地球之旅 · 4月28日").raw_normalized, "4月28日");
assert.equal(extractDouyinPostedMetadataFromText("· 4月28日", { referenceTime: weekReferenceTime }).posted_display, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("4月28日", { referenceTime: weekReferenceTime }).posted_display, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("@地球之旅 · 4月28日", { referenceTime: weekReferenceTime }).posted_text_raw, "@地球之旅 · 4月28日");
assert.equal(extractDouyinPostedMetadataFromText("@地球之旅 · 4月28日", { referenceTime: weekReferenceTime }).posted_text, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("2026年4月28日", { referenceTime: weekReferenceTime }).posted_display, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("2026年04月28日 06:00", { referenceTime: weekReferenceTime }).posted_display, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("2026-04-28 06:00", { referenceTime: weekReferenceTime }).posted_display, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("Apr 28", { referenceTime: weekReferenceTime }).posted_display, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("April 28, 2026", { referenceTime: weekReferenceTime }).posted_display, "28/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("12月31日", { referenceTime: new Date("2026-01-05T08:00:00.000Z") }).posted_display, "31/12/2025");
assert.equal(extractDouyinPostedMetadataFromText("刚刚", { referenceTime: weekReferenceTime }).posted_display, "09/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("昨天", { referenceTime: weekReferenceTime }).posted_display, "08/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("前天", { referenceTime: weekReferenceTime }).posted_display, "07/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("1天前", { referenceTime: weekReferenceTime }).posted_display, "08/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("2天前", { referenceTime: weekReferenceTime }).posted_display, "07/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("4天前", { referenceTime: weekReferenceTime }).posted_display, "05/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("1周前", { referenceTime: weekReferenceTime }).posted_display, "02/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("2周前", { referenceTime: weekReferenceTime }).posted_display, "25/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("一周前", { referenceTime: weekReferenceTime }).posted_display, "02/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("两周前", { referenceTime: weekReferenceTime }).posted_display, "25/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("1星期前", { referenceTime: weekReferenceTime }).posted_display, "02/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("1个月前", { referenceTime: weekReferenceTime }).posted_display, "09/04/2026");
assert.equal(extractDouyinPostedMetadataFromText("一年前", { referenceTime: weekReferenceTime }).posted_display, "09/05/2025");
assert.equal(extractDouyinPostedMetadataFromText("just now", { referenceTime: weekReferenceTime }).posted_display, "09/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("2 minutes ago", { referenceTime: weekReferenceTime }).posted_display, "09/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("yesterday", { referenceTime: weekReferenceTime }).posted_display, "08/05/2026");
assert.equal(extractDouyinPostedMetadataFromText("1周前", { referenceTime: weekReferenceTime }).posted_text_raw, "1周前");
assert.equal(parseDouyinPostedTextToDate({ postedText: "1周前", referenceTime: weekReferenceTime })?.toISOString(), "2026-05-02T08:00:00.000Z");
assert.equal(extractDouyinPostedMetadataFromText("no posted evidence here").posted_at, null);
assert.equal(extractDouyinPostedMetadataFromText("no posted evidence here").posted_text, null);
const first = selectDryRunSample(["7634192733514501001", "7634192733514501002", "7634192733514501003", "7634192733514501004"], "first", 3);
assert.deepEqual(first, { sampled_aweme_ids: ["7634192733514501001", "7634192733514501002", "7634192733514501003"], sampled_indexes: [0, 1, 2] });
const last = selectDryRunSample(["7634192733514501001", "7634192733514501002", "7634192733514501003", "7634192733514501004"], "last", 3);
assert.deepEqual(last, { sampled_aweme_ids: ["7634192733514501002", "7634192733514501003", "7634192733514501004"], sampled_indexes: [1, 2, 3] });
const random = selectDryRunSample(["7634192733514501001", "7634192733514501002", "7634192733514501003", "7634192733514501004"], "random", 1, () => 0.75);
assert.deepEqual(random, { sampled_aweme_ids: ["7634192733514501004"], sampled_indexes: [3] });

const sourceModalUrl = buildModalDetailUrl({ profile_url: "https://www.douyin.com/user/MS4wLjABCD?previous=1", aweme_id: "7634192733514501001", source_url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501001&from=grid" });
assert.deepEqual(sourceModalUrl, { ok: true, url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501001&from=grid", strategy: "target_source_url_modal" });
const builtModalUrl = buildModalDetailUrl({ profile_url: "https://www.douyin.com/user/MS4wLjABCD?previous=1", aweme_id: "7634192733514501002", source_url: "https://www.douyin.com/video/7634192733514501002" });
assert.deepEqual(builtModalUrl, { ok: true, url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501002", strategy: "profile_url_modal" });
assert.equal(builtModalUrl.ok && builtModalUrl.url.includes("/video/"), false, "profile-modal detail URL builder must not use direct video URLs");
const missingProfileModalUrl = buildModalDetailUrl({ profile_url: null, aweme_id: "7634192733514501002", source_url: "https://www.douyin.com/video/7634192733514501002" });
assert.deepEqual(missingProfileModalUrl, { ok: false, error: "Cannot build profile modal URL for this target." });
assert.deepEqual(validateExtractionContext({ expected_layout: "profile_modal", target_aweme_id: "7634192733514501002", current_url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501002", diagnostics: { page_type: "profile_modal", modal_id_present: true, metric_rail_visible: true } }), { ok: true, expected_layout: "profile_modal", actual_url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501002", actual_page_type: "profile_modal", modal_id_present: true, expected_aweme_id: "7634192733514501002", error: null });
assert.equal(validateExtractionContext({ expected_layout: "profile_modal", target_aweme_id: "7634192733514501002", current_url: "https://www.douyin.com/video/7634192733514501002", diagnostics: { page_type: "video", modal_id_present: false, metric_rail_visible: true } }).error, "extraction_context_mismatch");
assert.equal(validateExtractionContext({ expected_layout: "profile_modal", target_aweme_id: "7634192733514501002", current_url: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501002", diagnostics: { page_type: "profile_modal", modal_id_present: true, metric_rail_visible: false } }).ok, false, "profile-modal extraction must require visible metric rail/buttons");

const storage = new MemoryStorage();
const verified = await verifyProfile(runtime(storage));
assert.equal(verified.status, "verified");
assert.equal(verified.verify.verified_target_count, 4);
assert.equal(verified.classification.status, "success");
assert.equal(verified.classification.counts.collect, 3);
assert.deepEqual(verified.harvest.queue.map((item) => item.aweme_id), ["7634192733514501001", "7634192733514501002", "7634192733514501004"]);
assert.equal(verified.harvest.queue.some((item) => item.capture_status === "complete" || item.capture_status === "skipped"), false);
assert.equal(storage.writes.length >= 3, true, "verifyProfile must persist durable intermediate states");
assert.equal((await readWholeProfileHarvestState(storage)).verify.targets[0], "7634192733514501001");

const scannerScanStorage = new MemoryStorage();
const scannerScan = await runScanProfileWorkflow(runtime(scannerScanStorage));
const scannerScanWrites = scannerScanStorage.writes.map((write) => write.douyinWholeProfileHarvest as { phase?: string; workflow?: WholeProfileHarvestState["workflow"]; profile_scan?: WholeProfileHarvestState["profile_scan"]; classification?: WholeProfileHarvestState["classification"] });
assert.equal(scannerScan.status, "verified");
assert.equal(scannerScanWrites.some((state) => state.workflow?.scan.status === "running" && state.workflow.active_task === "scan_profile" && state.workflow.action_lock === "scan_profile"), true, "Scan Profile handler must persist the running state patch immediately");
assert.equal(scannerScanWrites.some((state) => state.phase === "waiting_profile_ready"), true, "Scan Profile workflow must emit waiting_profile_ready progress");
assert.equal(scannerScanWrites.some((state) => state.phase === "scanning_profile"), true, "Scan Profile workflow must emit scanning_profile progress");
assert.equal(scannerScanWrites.some((state) => (state.profile_scan?.scan_rounds ?? 0) > 0), true, "Scan Profile workflow must persist scan round progress");
assert.equal(scannerScanWrites.some((state) => state.workflow?.classification.status === "running"), true, "Scan Profile workflow must emit classification running progress");
assert.equal(scannerScanWrites.some((state) => state.workflow?.classification.status === "success" && (state.classification?.counts.collect ?? 0) > 0), true, "Scan Profile workflow must persist classification success and queue counts");
assert.equal(scannerScan.debug.last_action_clicked, "scan_profile");
assert.equal(scannerScan.debug.last_action_result, "success");
assert.equal(scannerScan.debug.last_action_error, null);
assert.equal(scannerScan.workflow.scan.status, "success", "Scan Profile must finish the scan workflow");
assert.equal(scannerScan.workflow.classification.status, "success", "Scan Profile must finish the classification workflow");
assert.equal(scannerScan.workflow.collection.status, "idle", "Scan Profile must not mark collection as running");
assert.equal(scannerScan.workflow.active_task, null, "Scan Profile must clear the active task lock when finished");
assert.equal(scannerScan.workflow.action_lock, null, "Scan Profile must clear the action lock when finished");
assert.equal(scannerScan.classification.status, "success", "Scan Profile must classify videos during the one-click workflow");
assert.equal(scannerScan.harvest.queue.length, 3, "Scan Profile must build the collect queue during the one-click workflow");
assert.equal(scannerScan.debug.last_action, "scan_profile.success", "Scan Profile must record the completed action code");
assert.equal((scannerScan.debug.last_request_summary as Record<string, unknown>).scan_run_id !== undefined, true, "Scan Profile must persist a scan run id");
assert.equal((scannerScan.debug.last_request_summary as Record<string, unknown>).scan_watchdog_started_at !== undefined, true, "Scan Profile must persist watchdog start diagnostics");
assert.equal((scannerScan.debug.last_request_summary as Record<string, unknown>).scan_watchdog_deadline_at !== undefined, true, "Scan Profile must persist watchdog deadline diagnostics");

const contentDiagnosticsStorage = new MemoryStorage();
const contentDiagnosticsFailure = await runScanProfileWorkflow(runtime(contentDiagnosticsStorage, {
  async ensureContentScriptReady() {
    return {
      ok: false,
      status: "missing",
      detector_status: "failed",
      page_type: "profile",
      current_url: "https://www.douyin.com/user/MS4wLjABCD",
      modal_id: null,
      error: "content_script_ping_timeout",
      diagnostics: {
        tab_resolve_strategy: "active_current_window",
        tab_resolve_result: "success",
        tab_url: "https://www.douyin.com/user/MS4wLjABCD",
        content_script_ensure_status: "failed",
        content_script_ping_result: "timeout",
        content_injection_result: "not_attempted"
      }
    };
  }
}));
const contentDiagnostics = contentDiagnosticsFailure.debug.last_request_summary as Record<string, unknown>;
assert.equal(contentDiagnosticsFailure.debug.last_action_result, "failed", "content script failure must finish Scan Profile as failed");
assert.equal(contentDiagnosticsFailure.workflow.active_task, null, "content script failure must clear active task lock");
assert.equal(contentDiagnosticsFailure.workflow.action_lock, null, "content script failure must clear action lock");
assert.equal(contentDiagnostics.content_script_ensure_status, "failed", "content script ensure status must persist to diagnostics");
assert.equal(contentDiagnostics.content_script_ping_result, "timeout", "content script ping result must persist to diagnostics");
assert.equal(contentDiagnostics.content_injection_result, "not_attempted", "content injection result must persist to diagnostics");
assert.equal(contentDiagnostics.tab_resolve_strategy, "active_current_window", "tab resolver strategy must persist to diagnostics");

assert.equal(controllerSource.includes("SCAN_PROFILE_ENSURE_CONTENT_SCRIPT_TIMEOUT_MS = 30_000"), true, "Scan Profile watchdog must use a 20-30s deadline");
assert.equal(controllerSource.includes("scan_profile_ensure_content_script_timeout"), true, "Scan Profile watchdog must use an explicit timeout error");
assert.equal(popupSource.includes("resolveActiveDouyinTabForScan"), true, "popup runtime must include the robust Douyin tab resolver");
assert.equal(popupSource.includes("lastFocusedWindow"), true, "tab resolver must query the last focused window");
assert.equal(popupSource.includes('url: "https://www.douyin.com/*"'), true, "tab resolver must enumerate www.douyin.com tabs");
assert.equal(popupSource.includes('url: "https://*.douyin.com/*"'), true, "tab resolver must enumerate subdomain Douyin tabs");
assert.equal(popupSource.includes("content_script_ping_timeout"), true, "content script ping must have an explicit timeout error");
assert.equal(popupSource.includes("scan_content_script_injection_failed"), true, "content script injection must have an explicit failure error");

const scannerScanFailure = await runScanProfileWorkflow(runtime(new MemoryStorage(), {
  async getActiveTab() { return { id: 123, url: "https://example.com/not-douyin" }; }
}));
assert.equal(scannerScanFailure.debug.last_action_clicked, "scan_profile");
assert.equal(scannerScanFailure.debug.last_action_result, "failed");
assert.equal(scannerScanFailure.debug.last_action_error, "Open a Douyin profile page first.");
assert.equal(scannerScanFailure.workflow.scan.status, "failed", "failed Scan Profile must mark the canonical scan workflow as failed");
assert.equal(scannerScanFailure.workflow.classification.status, "idle", "failed Scan Profile must not start classification");
assert.equal(scannerScanFailure.workflow.collection.status, "idle", "failed Scan Profile must not start collection");
assert.equal(scannerScanFailure.workflow.active_task, null, "failed Scan Profile must clear the active task lock");
assert.equal(scannerScanFailure.workflow.action_lock, null, "failed Scan Profile must clear the action lock");
assert.equal(scannerScanFailure.last_error, "Open a Douyin profile page first.");

const startBlockedStorage = new MemoryStorage();
const startBlocked = await runStartCollectingWorkflow(runtime(startBlockedStorage));
assert.equal(startBlocked.status, "idle", "blocked Start Collecting must not mark idle state as failed");
assert.equal(startBlocked.phase, "blocked");
assert.equal(startBlocked.debug.last_action_clicked, "start_collecting");
assert.equal(startBlocked.debug.last_action_result, "blocked");
assert.equal(startBlocked.debug.last_action_error, "No pending video is available for collection.");
assert.equal(startBlocked.workflow.collection.status, "failed", "blocked Start Collecting must leave an explicit failed collection reason visible");
assert.equal(startBlocked.workflow.active_task, null, "blocked Start Collecting must clear the active task lock");
assert.equal(startBlocked.workflow.action_lock, null, "blocked Start Collecting must clear the action lock");
assert.equal(typeof startBlocked.last_error === "object" && startBlocked.last_error?.message, "Start Collecting failed: No pending video is available for collection.");

const startAuthBlockedStorage = new MemoryStorage();
await verifyProfile(runtime(startAuthBlockedStorage));
const startAuthBlocked = await runStartCollectingWorkflow(runtime(startAuthBlockedStorage));
assert.equal(startAuthBlocked.debug.last_action_result, "blocked");
assert.equal(startAuthBlocked.debug.last_action_error, "App login required. Sign in to the Web Dashboard before collecting.");
assert.equal(startAuthBlocked.workflow.collection.status, "failed", "auth-blocked Start Collecting must keep an explicit failed reason visible");

const startCalibrationBlockedStorage = new MemoryStorage();
seedLoggedInAppAuth(startCalibrationBlockedStorage);
await verifyProfile(runtime(startCalibrationBlockedStorage));
const startCalibrationBlocked = await runStartCollectingWorkflow(runtime(startCalibrationBlockedStorage));
assert.equal(startCalibrationBlocked.debug.last_action_result, "blocked");
assert.equal(startCalibrationBlocked.debug.last_action_error, "Calibrate 4 Points first.");
assert.equal(startCalibrationBlocked.workflow.collection.status, "failed", "calibration-blocked Start Collecting must keep an explicit failed reason visible");
assert.equal(startCalibrationBlocked.workflow.active_task, null, "calibration-blocked Start Collecting must clear the active task lock");
assert.equal(startCalibrationBlocked.workflow.action_lock, null, "calibration-blocked Start Collecting must clear the action lock");
assert.equal(typeof startCalibrationBlocked.last_error === "object" && startCalibrationBlocked.last_error?.message, "Start Collecting failed: Calibrate 4 Points first.");
const startCalibrationBlockedSummary = startCalibrationBlocked.debug.last_request_summary as Record<string, unknown>;
assert.equal(startCalibrationBlockedSummary.start_collecting_clicked_at != null, true, "Start Collecting must record click time diagnostics even when blocked");
assert.equal(startCalibrationBlockedSummary.start_collecting_stage, "calibration_ready", "Start Collecting must record the calibration readiness stage when blocked on calibration readiness");
assert.equal(startCalibrationBlockedSummary.last_primary_action_key_clicked, "start_collecting", "Start Collecting controller diagnostics must preserve the strict primary action key");
assert.equal(startCalibrationBlockedSummary.last_primary_action_dispatch_target, "runStartCollectingWorkflow", "Start Collecting controller diagnostics must preserve the strict dispatch target");

{
  const unreachableOfferStorage = new MemoryStorage();
  seedLoggedInAppAuth(unreachableOfferStorage);
  unreachableOfferStorage.values.hybrid_network_cache_mode = true;
  const verified = await verifyProfile(runtime(unreachableOfferStorage));
  const at = "2026-07-10T06:00:00.000Z";
  await writeWholeProfileHarvestState(unreachableOfferStorage, applyUnreachableTailGapOfferToState({
    ...verified,
    calibration: {
      status: "calibrated",
      ready: true,
      layout: "profile_modal",
      profile_url: verified.profile_url,
      source_url: verified.profile_url,
      points: { like: { x: 1, y: 1 }, comment: { x: 2, y: 2 }, favorite: { x: 3, y: 3 }, share: { x: 4, y: 4 } },
      point_count: 4,
      source_key: "douyinRightRailCalibration",
      viewport_warning: null
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "test",
      scanned_total: 739,
      backend_captured_aweme_ids: [],
      backend_captured: 736,
      already_collected: 736,
      backend_ready: 736,
      backend_dup: 0,
      backend_fail: 0,
      incomplete: 0,
      need_retry: 0,
      new: 3,
      queue: 3,
      applied_at: at
    },
    harvest: { ...verified.harvest, queue: [], pending: 0 }
  }, at));
  const unreachableBlocked = await runStartCollectingWorkflow(runtime(unreachableOfferStorage));
  assert.equal(unreachableBlocked.debug.last_action_result, "blocked", "unreachable tail-gap offer must block Start Collecting dispatch");
  assert.match(String(unreachableBlocked.debug.last_action_error ?? ""), /Close the unreachable gap/, "blocked collect must tell operator to Close");
  const unreachableBlockedSummary = unreachableBlocked.debug.last_response_summary as Record<string, unknown>;
  assert.equal(unreachableBlockedSummary.start_collecting_blocked_reason, "unreachable_tail_gap_offer_active");
  assert.equal(unreachableBlocked.hybrid_tail_gap_presentation, "unreachable_offer");
  assert.equal(unreachableBlockedSummary.start_collecting_controller_exit_before_batch_runner, true);
}

const hybridSkipsCalibrationStorage = new MemoryStorage();
seedLoggedInAppAuth(hybridSkipsCalibrationStorage);
hybridSkipsCalibrationStorage.values.hybrid_network_cache_mode = true;
await verifyProfile(runtime(hybridSkipsCalibrationStorage, {
  async getCalibration() {
    return { status: "missing", ready: false, layout: "unknown", source_url: null, profile_url: "https://www.douyin.com/user/MS4wLjABCD", aweme_id: null, points: {}, point_count: 0, source_key: null, viewport_warning: null };
  }
}));
const hybridSkipsCalibration = await runStartCollectingWorkflow(runtime(hybridSkipsCalibrationStorage, {
  async getCalibration() {
    return { status: "missing", ready: false, layout: "unknown", source_url: null, profile_url: "https://www.douyin.com/user/MS4wLjABCD", aweme_id: null, points: {}, point_count: 0, source_key: null, viewport_warning: null };
  }
}));
const hybridSkipsCalibrationSummary = hybridSkipsCalibration.debug.last_request_summary as Record<string, unknown>;
assert.notEqual(hybridSkipsCalibrationSummary.start_collecting_stage, "calibration_ready", "hybrid storage flag must skip modal calibration gate");
assert.notEqual(hybridSkipsCalibration.debug.last_action_error, "Calibrate 4 Points first.", "hybrid storage flag must not block Start Collecting on calibration");

const calibrationModeStillActiveStorage = new MemoryStorage();
seedLoggedInAppAuth(calibrationModeStillActiveStorage);
const calibrationModeStillActiveBase = await verifyProfile(runtime(calibrationModeStillActiveStorage));
await writeWholeProfileHarvestState(calibrationModeStillActiveStorage, {
  ...calibrationModeStillActiveBase,
  calibration: {
    status: "calibrated",
    ready: true,
    layout: "profile_modal",
    profile_url: calibrationModeStillActiveBase.profile_url,
    source_url: calibrationModeStillActiveBase.profile_url,
    points: { like: {}, comment: {}, favorite: {}, share: {} },
    point_count: 4,
    source_key: "douyinRightRailCalibration",
    viewport_warning: null
  }
});
const calibrationModeStillActive = await runStartCollectingWorkflow(runtime(calibrationModeStillActiveStorage), {
  diagnostics: {
    calibration_mode_active_before_start: true,
    calibration_mode_stopped_before_start: false
  }
});
assert.equal(calibrationModeStillActive.debug.last_action_result, "blocked");
assert.equal(calibrationModeStillActive.debug.last_action_error, "Calibration mode is still active. Cancel calibration first.");
const calibrationModeStillActiveSummary = calibrationModeStillActive.debug.last_request_summary as Record<string, unknown>;
assert.equal(calibrationModeStillActiveSummary.calibration_mode_active_before_start, true, "Start Collecting diagnostics must record active calibration mode before start");
assert.equal(calibrationModeStillActiveSummary.calibration_mode_stopped_before_start, false, "Start Collecting diagnostics must record failed calibration mode cleanup before start");
assert.equal(calibrationModeStillActiveSummary.start_collecting_stage, "calibration_mode_stopped", "Start Collecting must stop before runner preflight if calibration mode remains active");
assert.equal(calibrationModeStillActiveSummary.start_collecting_blocked_reason, "Calibration mode is still active. Cancel calibration first.");
assert.equal(calibrationModeStillActiveSummary.start_collecting_controller_exit_before_batch_runner, true, "Start Collecting must mark calibration-mode cleanup as a pre-runner controller exit");
assert.equal(calibrationModeStillActiveSummary.start_collecting_controller_exit_stage, "calibration_mode_stopped", "Start Collecting must expose the calibration-mode pre-runner exit stage");
assert.equal(calibrationModeStillActiveSummary.start_collecting_controller_exit_reason, "Calibration mode is still active. Cancel calibration first.");
assert.equal(calibrationModeStillActiveSummary.collect_batch_runner_entry_hit, false, "calibration-mode block must prove the batch runner was not entered");
assert.equal(calibrationModeStillActiveSummary.batch_runner_called, false, "calibration-mode block must prove the batch runner was not called");
assert.equal(typeof calibrationModeStillActive.last_error === "object" && calibrationModeStillActive.last_error?.message, "Start Collecting failed: Calibration mode is still active. Cancel calibration first.");

const runnerDisconnectedStorage = new MemoryStorage();
seedLoggedInAppAuth(runnerDisconnectedStorage);
const runnerDisconnectedBase = await verifyProfile(runtime(runnerDisconnectedStorage));
await writeWholeProfileHarvestState(runnerDisconnectedStorage, {
  ...runnerDisconnectedBase,
  calibration: {
    status: "calibrated",
    ready: true,
    layout: "profile_modal",
    profile_url: runnerDisconnectedBase.profile_url,
    source_url: runnerDisconnectedBase.profile_url,
    points: { like: {}, comment: {}, favorite: {}, share: {} },
    point_count: 4,
    source_key: "douyinRightRailCalibration",
    viewport_warning: null
  }
});
const disconnectedRuntime = runtime(runnerDisconnectedStorage);
delete (disconnectedRuntime as Partial<WholeProfileHarvestRuntime>).openDirectModal;
delete (disconnectedRuntime as Partial<WholeProfileHarvestRuntime>).extractModalMetrics;
const runnerDisconnected = await runStartCollectingWorkflow(disconnectedRuntime);
assert.equal(runnerDisconnected.debug.last_action_result, "failed");
assert.equal(runnerDisconnected.debug.last_action_error, "One-item collector runner is not connected.");
assert.equal(runnerDisconnected.workflow.collection.status, "failed", "Start Collecting must fail visibly if the one-item runner is disconnected");
assert.equal(runnerDisconnected.workflow.active_task, null, "session handoff must clear active task");
assert.equal(runnerDisconnected.workflow.action_lock, null, "session handoff must clear action lock");
assert.equal(typeof runnerDisconnected.last_error === "object" && runnerDisconnected.last_error?.message, "Start Collecting failed: One-item collector runner is not connected.");
assert.equal(runnerDisconnected.harvest.collect_trace.length, 0, "runner-disconnected Start Collecting must not append collection trace entries");
const runnerDisconnectedSummary = runnerDisconnected.debug.last_response_summary as Record<string, unknown>;
assert.equal(runnerDisconnectedSummary.start_collecting_controller_exit_before_batch_runner, true, "runner-disconnected failure must mark a pre-runner controller exit");
assert.equal(runnerDisconnectedSummary.start_collecting_controller_exit_stage, "runner_capability_check", "runner-disconnected failure must expose the runner capability check stage");
assert.equal(runnerDisconnectedSummary.start_collecting_controller_exit_reason, "One-item collector runner is not connected.");
assert.equal(runnerDisconnectedSummary.runtime_open_direct_modal_present, false, "runner-disconnected failure must expose missing openDirectModal capability");
assert.equal(runnerDisconnectedSummary.runtime_extract_modal_metrics_present, false, "runner-disconnected failure must expose missing extractModalMetrics capability");
assert.equal(runnerDisconnectedSummary.collect_batch_runner_entry_hit, false, "runner-disconnected failure must prove the batch runner was not entered");
assert.equal(runnerDisconnectedSummary.batch_runner_called, false, "runner-disconnected failure must prove the batch runner was not called");

const emptyQueueBlockedStorage = new MemoryStorage();
const emptyQueueBase = await verifyProfile(runtime(emptyQueueBlockedStorage));
await writeWholeProfileHarvestState(emptyQueueBlockedStorage, {
  ...emptyQueueBase,
  calibration: {
    status: "calibrated",
    ready: true,
    layout: "profile_modal",
    profile_url: emptyQueueBase.profile_url,
    source_url: emptyQueueBase.profile_url,
    points: { like: {}, comment: {}, favorite: {}, share: {} },
    point_count: 4,
    source_key: "douyinRightRailCalibration",
    viewport_warning: null
  },
  classification: {
    ...emptyQueueBase.classification,
    counts: {
      ...emptyQueueBase.classification.counts,
      collect: 0,
      complete: 4,
      skipped: 0,
      unknown: 0
    },
    collect_aweme_ids: [],
    targets: []
  },
  harvest: {
    ...emptyQueueBase.harvest,
    queue: [],
    queue_preview: [],
    planned_total: 0,
    pending: 0
  }
});
const emptyQueueBlocked = await runStartCollectingWorkflow(runtime(emptyQueueBlockedStorage));
assert.equal(emptyQueueBlocked.debug.last_action_result, "blocked");
assert.equal(emptyQueueBlocked.debug.last_action_error, "No collect queue is available. Scan Profile first.");
assert.equal(emptyQueueBlocked.workflow.collection.status, "failed", "empty-queue Start Collecting must keep an explicit failed reason visible");
assert.equal(emptyQueueBlocked.workflow.active_task, null, "empty-queue Start Collecting must clear the active task lock");
assert.equal(emptyQueueBlocked.workflow.action_lock, null, "empty-queue Start Collecting must clear the action lock");
assert.equal(typeof emptyQueueBlocked.last_error === "object" && emptyQueueBlocked.last_error?.message, "Start Collecting failed: No collect queue is available. Scan Profile first.");
const emptyQueueBlockedSummary = emptyQueueBlocked.debug.last_request_summary as Record<string, unknown>;
assert.equal(emptyQueueBlockedSummary.start_collecting_controller_exit_before_batch_runner, true, "empty-queue block must mark a pre-runner controller exit");
assert.equal(emptyQueueBlockedSummary.start_collecting_controller_exit_stage, "queue_exists", "empty-queue block must expose the preflight queue stage");
assert.equal(emptyQueueBlockedSummary.start_collecting_controller_exit_reason, "No collect queue is available. Scan Profile first.");
assert.equal(emptyQueueBlockedSummary.collect_batch_runner_entry_hit, false, "empty-queue block must prove the batch runner was not entered");
assert.equal(emptyQueueBlockedSummary.batch_runner_called, false, "empty-queue block must prove the batch runner was not called");
assert.equal(Array.isArray(emptyQueueBlocked.harvest.collect_trace), true, "collect trace must always exist on harvest state");
assert.equal(emptyQueueBlocked.harvest.collect_trace.length, 0, "blocked Start Collecting must not append collect trace entries before collection starts");
assert.equal(emptyQueueBlocked.harvest.pause_diagnostics, null, "blocked Start Collecting must not create pause diagnostics");

const staleMetadataBlockedStorage = new MemoryStorage();
seedLoggedInAppAuth(staleMetadataBlockedStorage);
const staleMetadataBase = await verifyProfile(runtime(staleMetadataBlockedStorage));
const staleMetadataTargetDetails = staleMetadataBase.profile_scan.target_details.map((target, index) => ({
  ...target,
  backend_item: {
    item_id: `stale-item-${index}`,
    metadata_status: "ready" as const,
    missing_fields: [] as string[],
    existing_fields: {},
    updated_at: "2026-05-05T09:00:00.000Z"
  }
}));
await writeWholeProfileHarvestState(staleMetadataBlockedStorage, {
  ...staleMetadataBase,
  calibration: {
    status: "calibrated",
    ready: true,
    layout: "profile_modal",
    profile_url: staleMetadataBase.profile_url,
    source_url: staleMetadataBase.profile_url,
    points: { like: {}, comment: {}, favorite: {}, share: {} },
    point_count: 4,
    source_key: "douyinRightRailCalibration",
    viewport_warning: null
  },
  profile_scan: { ...staleMetadataBase.profile_scan, target_details: staleMetadataTargetDetails },
  verify: { ...staleMetadataBase.verify, target_details: staleMetadataTargetDetails },
  post_scan_counter_snapshot: {
    status: "applied",
    source: "backend_empty_disproves_snapshot",
    profile_identifier: "MS4wLjABCD",
    scanned_total: staleMetadataBase.harvest.queue.length,
    backend_captured: 0,
    backend_ready: 0,
    backend_dup: 0,
    backend_fail: 0,
    already_collected: 0,
    incomplete: 0,
    need_retry: 0,
    new: staleMetadataBase.harvest.queue.length,
    queue: staleMetadataBase.harvest.queue.length,
    applied_at: "2026-05-05T09:00:00.000Z"
  }
});
let staleMetadataRunnerDispatched = false;
const staleMetadataResult = await runStartCollectingWorkflow(runtime(staleMetadataBlockedStorage, {
  async openDirectModal(tabId, targetUrl) {
    staleMetadataRunnerDispatched = true;
    return runtime(staleMetadataBlockedStorage).openDirectModal!(tabId, targetUrl);
  }
}));
assert.notEqual(
  staleMetadataResult.debug.last_action_error,
  "No pending video is available for collection.",
  "stale scan-time backend_item must not block Start Collecting when backend is empty"
);
assert.equal(staleMetadataRunnerDispatched, true, "Start Collecting must dispatch modal runner after clearing stale metadata blockers");

const dryRun = await dryRunFirst(runtime(storage));
assert.equal(dryRun.dry_run.status, "success");
assert.equal(dryRun.dry_run.pass, 3);
assert.equal(dryRun.dry_run.results[0]?.data_integrity_status, "passed");
assert.equal(wholeProfileProgressSummary(dryRun)["Verified targets"], "4");
assert.equal(wholeProfileProgressSummary(dryRun)["Dry-run ready"], "yes");
assert.equal(wholeProfileProgressSummary(dryRun)["Safety scheduled pause"], "none");
assert.equal(wholeProfileProgressSummary(dryRun)["Harvest resume available"], "yes");

const phase22C5Captcha = detectDouyinSafetyBlock({ title: "安全验证", body: { innerText: "请完成验证 滑块 captcha" } }, "https://www.douyin.com/user/MS4wLjABCD");
assert.equal(phase22C5Captcha.detected, true, "Phase 22C-5 detector must catch captcha/security text");
assert.equal(phase22C5Captcha.safety_status, "needs_attention");
assert.equal(phase22C5Captcha.safety_user_action_required, true);

const captchaPauseStorage = new MemoryStorage();
const captchaPauseBase = await verifyProfile(runtime(captchaPauseStorage));
await writeWholeProfileHarvestState(captchaPauseStorage, {
  ...captchaPauseBase,
  status: "paused",
  phase: "harvest_paused_captcha",
  workflow: {
    ...captchaPauseBase.workflow,
    collection: {
      ...captchaPauseBase.workflow.collection,
      status: "paused",
      updated_at: "2026-05-05T09:00:00.000Z",
      completed_at: null,
      last_error: "captcha_detected: Captcha or checkpoint detected. Resolve it in Douyin, then resume."
    },
    active_task: null,
    action_lock: null
  },
  harvest: {
    ...captchaPauseBase.harvest,
    status: "paused",
    paused_reason: "captcha_detected",
    pause_message: "Captcha/checkpoint detected. Resolve manually in the active Douyin tab, then press Resume Harvest.",
    resume_available: true,
    resume_from_index: 0,
    current_index: 0,
    current_aweme_id: captchaPauseBase.harvest.queue[0]?.aweme_id ?? null
  },
  safety: {
    ...captchaPauseBase.safety,
    safety_status: "needs_attention",
    safety_reason: "login_required",
    safety_evidence: "请登录后继续",
    safety_recoverable: true,
    safety_user_action_required: true,
    safety_checkpoint: null,
    captcha_detected: true,
    captcha_reason: "login_required",
    captcha_evidence_text: "请登录后继续",
    checkpoint_detected: true,
    login_required: true
  }
});
const captchaPaused = await resumeHarvest(runtime(captchaPauseStorage));
assert.equal(captchaPaused.safety.safety_status, "needs_attention", "captcha pause must write canonical safety status");
assert.equal(captchaPaused.safety.safety_reason, "login_required");
assert.equal(captchaPaused.safety.safety_user_action_required, true);
assert.equal(captchaPaused.safety.safety_checkpoint?.schema_version, "douyin_safety_checkpoint.v1", "captcha pause must persist a safety checkpoint");
assert.equal(captchaPaused.safety.safety_checkpoint?.safety_reason, "login_required");
assert.equal(getWholeProfileHarvestReadiness(captchaPaused).resume_ready, false, "Resume must be gated while user action is required");
const captchaRunVm = getRunTabViewModel(captchaPaused, getWholeProfileHarvestReadiness(captchaPaused), getWholeProfileHarvestActionState(captchaPaused));
assert.equal(captchaRunVm.alert?.title, "Attention needed");
assert.equal(captchaRunVm.status_chips.find((chip) => chip.label === "Safety")?.value, "Check");

const staleStorage = new MemoryStorage();
const staleBase = createWholeProfileHarvestIdleState("2026-05-05T09:00:00.000Z");
await writeWholeProfileHarvestState(staleStorage, {
  ...staleBase,
  status: "harvesting",
  phase: "extracting_metadata",
  run_id: "run_stale_1",
  profile_url: "https://www.douyin.com/user/MS4wLjABCD",
  workflow: { ...staleBase.workflow, collection: { ...staleBase.workflow.collection, status: "running", updated_at: "2026-05-05T09:00:00.000Z" }, active_task: "collect_videos", action_lock: "collect_videos" },
  harvest: {
    ...staleBase.harvest,
    status: "running",
    current_index: 0,
    current_aweme_id: "7634192733514501001",
    pause_diagnostics: { batch_heartbeat_at: "2026-05-05T09:00:00.000Z", batch_heartbeat_stage: "extracting", batch_heartbeat_aweme: "7634192733514501001" }
  },
  debug: { ...staleBase.debug, last_response_summary: { batch_heartbeat_at: "2026-05-05T09:00:00.000Z", batch_heartbeat_stage: "extracting", batch_heartbeat_aweme: "7634192733514501001" } }
});
const phase22C5StaleRecovered = await recoverStalePausingLock({ storage: staleStorage, now: () => "2026-05-05T09:02:00.000Z" });
assert.equal(phase22C5StaleRecovered.status, "paused", "stale running watchdog must pause safely");
assert.equal(phase22C5StaleRecovered.workflow.action_lock, null, "stale running watchdog must clear action lock");
assert.equal(phase22C5StaleRecovered.safety.safety_status, "stale");
assert.equal(phase22C5StaleRecovered.safety.safety_checkpoint?.safety_reason, "running_heartbeat_stale");

const phase22C15LegacyQuarantine = await runLegacyVerifiedProfileScrollScan22C9ZNOGIT({ runtime: runtime(new MemoryStorage()), tabId: 1, profileUrl: "https://www.douyin.com/user/MS4wLjABCD", domProbeResult: { profile_dom_probe_status: "completed", aweme_id_count: 4 } });
assert.equal(phase22C15LegacyQuarantine.ok, false, "Phase 22C-15 legacy verified scroll scan must be quarantined instead of acting as scan authority");
assert.equal(phase22C15LegacyQuarantine.error, "legacy_verified_scroll_scan_quarantined", "Phase 22C-15 legacy verified scroll scan must expose a stable quarantine error");
assert.equal(phase22C15LegacyQuarantine.scrollDiagnostics.legacy_verified_scroll_scan_quarantined, "yes", "Phase 22C-15 legacy verified scroll scan must emit quarantine diagnostics");
assert.equal(phase22C15LegacyQuarantine.scrollDiagnostics.legacy_verified_scroll_scan_reason, "authenticated_active_profile_post_authority_required", "Phase 22C-15 legacy verified scroll scan must explain active profile-post authority");
assert.equal(phase22C15LegacyQuarantine.scrollDiagnostics.legacy_verified_scroll_scan_diagnostic_only, "yes", "Phase 22C-15 legacy verified scroll scan must be diagnostic-only");
assert.equal(phase22C15LegacyQuarantine.scan, null, "Phase 22C-15 legacy verified scroll scan must not return a canonical scan result");
assert.equal(controllerSource.includes("legacy_verified_scroll_scan_quarantined") && controllerSource.includes("authenticated_active_profile_post_authority_required"), true, "Phase 22C-15 controller must keep legacy verified scan quarantine diagnostics wired");
assert.equal(controllerSource.includes("completeProfileVerifyFromDomProbe22C9J") && controllerSource.includes("legacy_dom_finalizer_blocked"), true, "Phase 22C-15 must keep DOM Probe finalizer as diagnostic-only when active authority is unresolved");

const phase22C15DomDiagnosticOnly = await verifyProfile(runtime(new MemoryStorage(), {
  async scanProfile() {
    return {
      ...scanResult(),
      cards: [],
      diagnostics: {
        ...scanResult().diagnostics,
        rounds: 0,
        raw_candidate_count: 0,
        final_found_count: 44,
        expected_profile_video_count: 995,
        missing_expected_count: 951,
        profile_dom_probe_status: "completed",
        profile_dom_probe_completed_at: "2026-05-11T00:00:00.000Z",
        profile_grid_ready: true,
        aweme_id_count: 44,
        awemeIds: Array.from({ length: 44 }, (_, index) => String(7634192733514501000n + BigInt(index)))
      }
    };
  }
}));
const phase22C15DomDiagnostics = phase22C15DomDiagnosticOnly.profile_scan.diagnostics as Record<string, unknown>;
assert.equal(phase22C15DomDiagnosticOnly.profile_scan.status, "failed", "Phase 22C-15 DOM finalizer must not write scan success under known large expected count");
assert.equal(phase22C15DomDiagnosticOnly.verify.status, "failed", "Phase 22C-15 DOM finalizer must not write verify success under known large expected count");
assert.equal(phase22C15DomDiagnosticOnly.layer.profile_scan_ready, false, "Phase 22C-15 DOM finalizer must not unlock profile scan readiness");
assert.equal(phase22C15DomDiagnosticOnly.post_scan_counter_snapshot, null, "Phase 22C-15 DOM finalizer must not create post-scan counter snapshots for incomplete scans");
assert.equal(phase22C15DomDiagnosticOnly.harvest.queue.length, 44, "Phase 22C-15 DOM finalizer may preserve partial DOM queue as diagnostic evidence");
assert.equal(phase22C15DomDiagnostics.legacy_dom_finalizer_blocked, "yes", "Phase 22C-15 DOM finalizer must expose blocked authority diagnostics");
assert.equal(phase22C15DomDiagnostics.legacy_dom_finalizer_block_reason, "known_large_expected_count_with_unresolved_active_profile_post_source", "Phase 22C-15 DOM finalizer must explain large-count active-source block");
assert.equal(phase22C15DomDiagnostics.legacy_dom_candidate_count, 44, "Phase 22C-15 DOM finalizer must report DOM candidate count");
assert.equal(phase22C15DomDiagnostics.legacy_dom_expected_count, 995, "Phase 22C-15 DOM finalizer must report expected count");
assert.equal(phase22C15DomDiagnostics.legacy_dom_active_source_status, "failed_or_unresolved", "Phase 22C-15 DOM finalizer must report unresolved active source status");
assert.equal(phase22C15DomDiagnostics.legacy_dom_written_as_diagnostic_only, "yes", "Phase 22C-15 DOM finalizer must mark DOM queue diagnostic-only");
assert.equal(phase22C15DomDiagnostics.backend_reconciliation_skipped_for_incomplete_scan, "yes", "Phase 22C-15 DOM finalizer must skip backend reconciliation authority for incomplete scans");
assert.equal(phase22C15DomDiagnostics.post_scan_snapshot_skipped_for_incomplete_scan, "yes", "Phase 22C-15 DOM finalizer must skip counter snapshot authority for incomplete scans");
assert.equal(phase22C15DomDiagnostics.counter_authority_blocked_for_incomplete_scan, "yes", "Phase 22C-15 DOM finalizer must block counter authority for incomplete scans");

const phase22C9Z3InvariantFailure = await verifyProfile(runtime(new MemoryStorage(), {
  async scanProfile() {
    return {
      ...scanResult(),
      cards: [],
      diagnostics: {
        ...scanResult().diagnostics,
        rounds: 0,
        raw_candidate_count: 0,
        final_found_count: 0,
        profile_dom_probe_status: "completed",
        profile_dom_probe_completed_at: "2026-05-11T00:00:00.000Z",
        profile_grid_ready: true,
        aweme_id_count: 27
      }
    };
  }
}));
assert.equal(phase22C9Z3InvariantFailure.last_error, "profile_candidate_normalization_failed: Profile DOM probe candidates could not be normalized.", "Phase 22C-15 incomplete DOM evidence must fail before any canonical legacy success finalizer");
assert.notEqual(phase22C9Z3InvariantFailure.last_error, "profile_scan_no_round_started: Profile scan did not start a scan round.");

const phase22C9Z3MessageMissing = await verifyProfile(runtime(new MemoryStorage(), {
  async scanProfile() { throw Object.assign(new Error("receiving end does not exist"), { code: "legacy_scanner_message_handler_missing" }); }
}));
assert.equal(phase22C9Z3MessageMissing.last_error, "legacy_scanner_message_handler_missing: receiving end does not exist");

const phase22C9Z3Timeout = await verifyProfile(runtime(new MemoryStorage(), {
  async scanProfile() { throw Object.assign(new Error("timeout"), { code: "profile_scan_timeout" }); },
  async runPostPingProfileDomProbe22C9I() { return { ok: true, specificError: null, diagnostics: { profile_dom_probe_status: "completed", profile_dom_probe_completed_at: "2026-05-11T00:00:00.000Z", profile_grid_ready: true, aweme_id_count: 27 } }; }
}));
assert.equal(phase22C9Z3Timeout.last_error, "profile_scan_timeout: timeout");

const phase22C9Z3Thrown = await verifyProfile(runtime(new MemoryStorage(), {
  async scanProfile() { throw new Error("legacy exploded"); },
  async runPostPingProfileDomProbe22C9I() { return { ok: true, specificError: null, diagnostics: { profile_dom_probe_status: "completed", profile_dom_probe_completed_at: "2026-05-11T00:00:00.000Z", profile_grid_ready: true, aweme_id_count: 27 } }; }
}));
assert.equal(phase22C9Z3Thrown.last_error, "profile_scan_failed: Profile scan failed.");
const phase22C9Z3ThrownDiagnostics = phase22C9Z3Thrown.debug.last_response_summary as Record<string, unknown>;
assert.notEqual(phase22C9Z3ThrownDiagnostics.legacy_dom_finalizer_blocked, "no", "Phase 22C-15 failed active scanner runs must not re-enable legacy DOM finalizer authority");

assert.equal(controllerSource.includes("legacy_queue_adapter_zero_output"), true, "22C-9Z-3 must include the queue adapter zero-output specific error");
assert.equal(controllerSource.includes("legacy_verified_scroll_scan_quarantined"), true, "Phase 22C-15 must keep the legacy verified scroll route quarantined");
assert.equal(controllerSource.includes("profile_scan_no_round_started") && controllerSource.includes("illegal_final_error_prevented"), true, "22C-9Z-3 must block generic no-round finalization after a productive DOM Probe");
assert.equal(controllerSource.includes("const routeAttempted = result === \"started\" || result === \"success\" || result === \"failed\""), true, "22C-9Z-4 must preserve failed legacy scanner attempts as visible invoked routes");

const phase22C9JProbe = {
  awemeIdsSample: ["7634192733514501001"],
  videoAnchorsSample: ["https://www.douyin.com/video/7634192733514501002"],
  modalIdLinksSample: ["https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501003"],
  dataAwemeIdsSample: ["aweme_id=7634192733514501004", "bad-id", "https://www.douyin.com/video/7634192733514501002"]
};
const phase22C9JNormalized = normalizeProfileDomProbeCandidates22C9J(phase22C9JProbe, "https://www.douyin.com/user/MS4wLjABCD");
assert.deepEqual(phase22C9JNormalized.candidates.map((candidate) => candidate.aweme_id), ["7634192733514501001", "7634192733514501002", "7634192733514501003", "7634192733514501004"], "22C-9J must normalize explicit ids, /video ids, modal ids, and aweme_id fallback");
assert.equal(phase22C9JNormalized.duplicate_count, 1, "22C-9J normalization must count duplicates");
assert.equal(phase22C9JNormalized.invalid_count, 1, "22C-9J normalization must count invalid candidates");
const phase22C9JQueue = buildProfileScanQueueFromCandidates22C9J(phase22C9JNormalized.candidates, createWholeProfileHarvestIdleState("2026-05-11T00:00:00.000Z"), "2026-05-11T00:00:01.000Z");
assert.equal(phase22C9JQueue.queue.length, 4, "22C-9J must build queue entries from DOM probe candidates");
assert.equal(phase22C9JQueue.pendingCount, 4, "22C-9J queue entries must be pending");
assert.equal(phase22C9JQueue.queue.at(0)?.profile_card_evidence.discovery_source, "dom_probe_known_good_fallback_22C9K", "22C-9Z-NOGIT queue must carry known-good DOM probe fallback discovery source");
assert.equal(phase22C9JNormalized.candidates.at(0)?.source_url, "https://www.douyin.com/video/7634192733514501001", "22C-9Z-NOGIT must synthesize source_url for aweme-id-only DOM probe candidates");
const phase22C9Z_NOGITProbe = {
  awemeIds: ["7634192733514501010", "7634192733514501011"],
  videoAnchors: [{ href: "https://www.douyin.com/video/7634192733514501012", text: "caption" }],
  modalIdLinks: [{ href: "https://www.douyin.com/user/MS4wLjABCD?modal_id=7634192733514501013" }],
  gridCards: [{ aweme_id: "7634192733514501014", href: "https://www.douyin.com/video/7634192733514501014" }],
  awemeIdCount: 5,
  videoAnchorCount: 1,
  gridCardCandidateCount: 5
};
const phase22C9Z_NOGITNested = normalizeProfileDomProbeCandidates22C9J({ legacy_verified_profile_scroll_scan_22C9Z_NOGIT: { scrollDiagnostics: { dom_probe_preflight: { profile_dom_probe: phase22C9Z_NOGITProbe } } } }, "https://www.douyin.com/user/MS4wLjABCD");
assert.deepEqual(phase22C9Z_NOGITNested.candidates.map((candidate) => candidate.aweme_id), ["7634192733514501010", "7634192733514501011", "7634192733514501012", "7634192733514501013", "7634192733514501014"], "22C-9Z-NOGIT must normalize full DOM probe arrays from nested full-scroll diagnostics");
assert.equal(phase22C9Z_NOGITNested.diagnostics.normalization_input_has_aweme_ids, true, "22C-9Z-NOGIT diagnostics must expose aweme id array input");
assert.equal(phase22C9Z_NOGITNested.diagnostics.probe_aweme_ids_array_count, 2, "22C-9Z-NOGIT diagnostics must expose probe aweme id array count");
assert.equal(controllerSource.includes("completeProfileVerifyFromDomProbe22C9J"), true, "22C-9J fallback finalizer must be wired after scan runner failure/no rounds");
assert.equal(normalizeProfileDomProbeStatus22C9K({ profile_dom_probe_message: "ok", profile_dom_probe_completed_at: "2026-05-11T00:00:00.000Z" }), "completed", "22C-9Z-NOGIT must normalize ok+completed DOM probe status to completed");
assert.equal(normalizeProfileDomProbeStatus22C9K({}), "not_attempted", "22C-9Z-NOGIT must expose not_attempted when DOM probe never ran");
assert.equal(normalizeProfileDomProbeStatus22C9K({ profile_dom_probe_message: "scan_dom_probe_timeout" }), "timeout", "22C-9Z-NOGIT must preserve failure status semantics");
assert.equal(controllerSource.includes("scanner_runtime_version: SCANNER_RUNTIME_VERSION") && controllerSource.includes("const SCANNER_RUNTIME_VERSION = \"22C-12F\""), true, "22C-12F active scanner runtime version must be wired");
assert.equal(controllerSource.includes("scan_success_cleanup_version: \"22C-9Z-NOGIT-1\""), true, "22C-9Z-3 small/unknown-count fallback success cleanup diagnostics must remain stamped");
assert.equal(controllerSource.includes("scan_queue_builder_used: \"dom_probe_known_good_fallback_22C9K\""), true, "22C-9Z-NOGIT must stamp known-good fallback queue builder diagnostics");
assert.equal(controllerSource.includes("scan_fallback_reason: scanError ? \"full_scroll_normalization_zero\""), true, "22C-9Z-NOGIT must explain full-scroll normalization-zero fallback");
for (const key of ["profile_discovered_count", "profile_normalized_count", "profile_duplicate_count", "profile_invalid_count", "profile_already_collected_count", "profile_eligible_count", "profile_queue_total_count", "profile_batch_limit", "profile_batch_pending_count", "profile_batch_mode", "profile_queue_limit_reason"]) {
  assert.equal(controllerSource.includes(key), true, `22C-9Z-NOGIT count contract must include ${key}`);
}
for (const key of ["backend_reconciliation_status", "backend_reconciliation_profile_identifier", "backend_reconciliation_backend_count", "backend_reconciliation_matched_count", "backend_reconciliation_unmatched_count", "backend_reconciliation_match_key"]) {
  assert.equal(controllerSource.includes(key), true, `Phase 3H backend reconciliation diagnostics must include ${key}`);
}
for (const key of ["backend_reconciliation_source", "backend_reconciliation_session_count", "backend_reconciliation_item_count", "backend_reconciliation_unmatched_backend_count", "backend_reconciliation_unmatched_queue_count", "backend_reconciliation_profile_scope"]) {
  assert.equal(controllerSource.includes(key), true, `Phase 3I backend reconciliation diagnostics must include ${key}`);
}
assert.equal(controllerSource.includes("backendItemMatchesProfile"), true, "Phase 3I backend reconciliation must inspect unverifiable sessions using same-profile item proof");
for (const key of ["payload_sanitized_removed_disallowed_fields_count", "payload_sanitized_removed_disallowed_field_names"]) {
  assert.equal(controllerSource.includes(key), true, `Phase 3I payload sanitizer diagnostics must include ${key}`);
}
for (const key of ["collect_backend_write_attempted", "collect_backend_write_status", "collect_backend_write_success_count", "collect_backend_write_failed_count"]) {
  assert.equal(controllerSource.includes(key), true, `Phase 3H collect write diagnostics must include ${key}`);
}
assert.equal(controllerSource.includes("reconcileProfileQueueWithBackend({ runtime, profileUrl"), true, "Phase 3H completed scan paths must reconcile profile queue with backend Capture Inbox data");
assert.equal(controllerSource.includes("queueItemAlreadyCollected(item)"), true, "Phase 3H already-collected count must include reconciled backend queue items");
assert.equal(controllerSource.includes("selectNextActionableTargets(queue"), true, "22C-9Z-NOGIT queue contract must preserve canonical queue and calculate batch pending via Start Collecting selection semantics");
assert.equal(controllerSource.includes("profile_scan_ready_state_update_failed"), true, "22C-9J must protect profileScanReady finalization");

console.log("Phase 18I-E whole-profile safety scheduler and captcha pause tests passed");


