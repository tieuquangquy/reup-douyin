import assert from "node:assert/strict";

import {
  ensureHarvestQueueReadyForStartCollecting,
  evaluateCollectJobWriteGuard,
  HYBRID_COLLECTION_DONE_KEY,
  HYBRID_FLUSH_CHUNK_SIZE_DEFAULT,
  readWholeProfileHarvestState,
  runBatchCollectHybridNetworkCacheMode,
  runSkipHybridUncollectableRemainder,
  writeHybridLoopHeartbeat,
  writeWholeProfileHarvestState,
  type WholeProfileHarvestRuntime
} from "./wholeProfileHarvest/controller.js";
import { applyHybridCollectionDoneOverride, deriveAuthoritativeRunnerLock } from "./wholeProfileHarvest/authoritativePopupState.js";
import { getScannerControlPanelViewModel } from "./wholeProfileHarvest/viewModel.js";
import {
  WHOLE_PROFILE_HARVEST_STATE_KEY,
  createWholeProfileHarvestIdleState,
  type WholeProfileHarvestQueueItem,
  type WholeProfileHarvestState,
  type WholeProfileHarvestTargetDetail
} from "./wholeProfileHarvest/state.js";
import { emptyDouyinProfileVideoClassificationCounts } from "./wholeProfileHarvest/profileClassification.js";
import {
  InMemoryProfileTargetRepository,
  buildQueueWindowFromRecords,
  profileIdentifierFromUrl,
  resetProfileTargetRepositoryForTests,
  setProfileTargetRepositoryFactoryForTests
} from "./wholeProfileHarvest/profileTargetRepository.js";
import type { FullModalHarvestRequestPayload } from "./types.js";
import type { ModalWholeProfileScanDiagnostics } from "./modalWholeProfileTest.js";

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

type FlushCall = {
  payload: FullModalHarvestRequestPayload | Record<string, unknown>;
  headers: Record<string, string>;
  awemeIds: string[];
};

type FetchCall = {
  url: string;
  init: RequestInit | undefined;
  body: Record<string, unknown> | null;
};

const PROFILE_URL = "https://www.douyin.com/user/MS4wLjABAAAA-hybrid-regression";
const SESSION_ID = "11111111-1111-4111-8111-111111111111";
const BASE_NOW_MS = Date.parse("2026-01-01T00:00:00.000Z");

function iso(offsetSeconds: number): string {
  return new Date(BASE_NOW_MS + offsetSeconds * 1000).toISOString();
}

function awemeId(index: number): string {
  return `7330000000000000${String(index).padStart(2, "0")}`;
}

function evidenceFor(id: string, index: number): Record<string, unknown> {
  return {
    aweme_id: id,
    source_url: `https://www.douyin.com/video/${id}`,
    thumbnail_url: `https://p3-sign.douyinpic.com/obj/test-${id}.jpg`,
    cover_url: `https://p3-sign.douyinpic.com/obj/test-${id}.jpg`,
    caption: `hybrid regression ${index}`,
    title: `hybrid regression ${index}`,
    duration_seconds: 15 + index,
    like_count: 100 + index,
    comment_count: 10 + index,
    favorite_count: 5 + index,
    share_count: 2 + index,
    posted_at: iso(-index - 1),
    posted_text: iso(-index - 1)
  };
}

function makeScanDiagnostics(): ModalWholeProfileScanDiagnostics {
  return {
    selector_attempts: [],
    current_url: PROFILE_URL,
    target_profile_url: PROFILE_URL,
    page_type: "profile",
    modal_id_present: false,
    document_ready_state: "complete",
    body_text_sample: "",
    scroll_y: 0,
    viewport: { width: 1280, height: 720, device_pixel_ratio: 1 },
    candidate_card_count: 0,
    visible_link_count: 0,
    video_aweme_candidate_count: 0,
    grid_container_count: 0,
    empty_state_detected: false,
    login_or_captcha_detected: false,
    rounds: 0,
    scan_rounds: [],
    stop_reason: null,
    selected_scroll_container: null,
    scroll_container_candidates: [],
    scroll_container_found: true,
    scroll_container_strategy: null,
    selected_profile_tab: null,
    tab_candidates: [],
    warning: null,
    candidate_classifications: [],
    raw_candidate_count: 0,
    accepted_count: 0,
    rejected_count: 0,
    rejected_examples: [],
    candidate_sources_count: {
      video_link: 0,
      modal_link: 0,
      data_attr: 0,
      card_context_regex: 0,
      body_regex: 0
    },
    expected_profile_video_count: null,
    expected_count_value: null,
    expected_count_source: "unavailable",
    expected_count_profile_url: PROFILE_URL,
    expected_count_updated_at: iso(0),
    expected_count_scan_run_id: "hybrid_regression_scan",
    scan_run_id: "hybrid_regression_scan",
    final_found_count: 0,
    missing_expected_count: null,
    bottom_reached: false,
    bottom_bounce_done: false,
    stable_rounds: 0,
    final_aweme_ids: [],
    partial_scan: false,
    per_round: []
  };
}

function makeQueueItem(id: string, index: number): WholeProfileHarvestQueueItem {
  const evidence = evidenceFor(id, index);
  return {
    index,
    aweme_id: id,
    capture_status: "new",
    status: "pending",
    attempts: 0,
    retry_count: 0,
    checkpoint_sequence: null,
    extraction_result: null,
    last_error: null,
    last_attempt_at: null,
    saved_at: null,
    capture_inbox_item_id: null,
    backend_item_id: null,
    metadata_status: null,
    source_url: evidence.source_url as string,
    thumbnail_url: evidence.thumbnail_url as string,
    caption: evidence.caption as string,
    profile_card_evidence: evidence
  };
}

function makeTargetDetail(id: string, index: number): WholeProfileHarvestTargetDetail {
  const evidence = evidenceFor(id, index);
  return {
    index,
    aweme_id: id,
    source_url: evidence.source_url as string,
    profile_url: PROFILE_URL,
    thumbnail_url: evidence.thumbnail_url as string,
    title: evidence.title as string,
    caption: evidence.caption as string,
    text_sample: evidence.caption as string,
    posted_text: evidence.posted_text as string,
    posted_at: evidence.posted_at as string,
    duration_text: `${evidence.duration_seconds}s`,
    duration_seconds: evidence.duration_seconds as number,
    view_text: null,
    view_count: null,
    candidate_validation: { status: "accepted", source: "video_link", reason: null, source_url: evidence.source_url as string },
    metadata_completeness: {
      has_profile_identity: true,
      has_thumbnail: true,
      has_title_or_caption: true,
      has_posted_text: true,
      has_duration: true,
      has_view_count: false,
      has_detail_metrics: true
    },
    capture_status: "new",
    backend_item: null,
    extraction_source: "test_fixture",
    profile_card_evidence: evidence
  };
}

function buildState(total: number, at = iso(0)): WholeProfileHarvestState {
  const ids = Array.from({ length: total }, (_, index) => awemeId(index + 1));
  const queue = ids.map(makeQueueItem);
  const targetDetails = ids.map(makeTargetDetail);
  const counts = emptyDouyinProfileVideoClassificationCounts();
  counts.new = total;
  counts.collect = total;

  return {
    ...createWholeProfileHarvestIdleState(at),
    run_id: "hybrid_regression_run",
    status: "harvesting",
    phase: "harvest",
    profile_url: PROFILE_URL,
    source_url: PROFILE_URL,
    capture_session_id: SESSION_ID,
    workflow: {
      ...createWholeProfileHarvestIdleState(at).workflow,
      collection: {
        status: "running",
        started_at: at,
        updated_at: at,
        completed_at: null,
        last_error: null
      },
      active_task: "collect_videos",
      action_lock: "collecting"
    },
    collect_job: {
      ...createWholeProfileHarvestIdleState(at).collect_job,
      job_id: "hybrid_collect_job",
      profile_identifier: PROFILE_URL,
      normalized_profile_identifier: PROFILE_URL,
      state: "starting",
      started_at: at,
      updated_at: at,
      heartbeat_at: at,
      current_step: "starting",
      batch_limit: 10,
      selected_count: 10,
      selected_aweme_ids: ids.slice(0, 10),
      selected_indexes: Array.from({ length: Math.min(10, total) }, (_, index) => index),
      start_index: 0,
      runtime_generation: 1,
      lock_owner: "hybrid_collect_job",
      lock_acquired_at: at,
      lock_expires_at: iso(60),
      runner_ack_at: null,
      startup_deadline_at: iso(60),
      startup_timeout_ms: 60000,
      recoverable: false,
      lock_released: false,
      heartbeat_updates_count: 1
    },
    active_collect_runtime: {
      ...createWholeProfileHarvestIdleState(at).active_collect_runtime,
      job_id: "hybrid_collect_job",
      runtime_generation: 1,
      canonical_state: "starting",
      canonical_phase: "batch_collect",
      current_step: "starting",
      batch_limit: 10,
      selected_count: 10,
      lock_owner: "hybrid_collect_job",
      lock_expires_at: iso(60),
      heartbeat_at: at,
      updated_at: at
    },
    profile_scan: {
      ...createWholeProfileHarvestIdleState(at).profile_scan,
      status: "success",
      raw_candidate_count: total,
      accepted_target_count: total,
      targets: ids,
      target_details: targetDetails,
      diagnostics: { fixture: "hybrid_regression" }
    },
    verify: {
      ...createWholeProfileHarvestIdleState(at).verify,
      status: "success",
      raw_candidate_count: total,
      accepted_target_count: total,
      verified_target_count: total,
      targets: ids,
      target_details: targetDetails,
      diagnostics: { fixture: "hybrid_regression" }
    },
    target_status: { unknown: 0, new: total, incomplete: 0, complete: 0, failed: 0, skipped: 0 },
    classification: {
      status: "success",
      started_at: at,
      completed_at: at,
      last_error: null,
      profile_url: PROFILE_URL,
      sec_uid: "MS4wLjABAAAA-hybrid-regression",
      schema_version: "douyin_profile_video_classification_result.v1",
      collection_mode: "new_and_incomplete",
      database_lookup_status: "ok",
      total_candidates: total,
      counts,
      targets: ids.map((id, index) => ({
        aweme_id: id,
        classification: "new",
        collect: true,
        reason: "fixture_new",
        required_missing_fields: [],
        existing_item_id: null,
        metadata_status: null,
        review_status: null,
        video_url: `https://www.douyin.com/video/${id}`,
        source_url: `https://www.douyin.com/video/${id}`,
        thumbnail_url: `https://p3-sign.douyinpic.com/obj/test-${id}.jpg`,
        caption: `hybrid regression ${index}`
      })),
      collect_aweme_ids: ids,
      skip_aweme_ids: [],
      diagnostics: { fixture: "hybrid_regression" }
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: total,
      backend_captured_aweme_ids: [],
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 0,
      need_retry: 0,
      new: total,
      queue: total,
      applied_at: at
    },
    harvest_options: { mode: "new_and_incomplete", batch: "next_10", batch_limit: 10, speed: "safe", unattended_safe_mode: false },
    harvest: {
      ...createWholeProfileHarvestIdleState(at).harvest,
      status: "running",
      mode: "new_and_incomplete",
      batch_limit: 10,
      queue,
      queue_preview: queue.slice(0, 10).map((item) => ({
        index: item.index,
        aweme_id: item.aweme_id,
        capture_status: item.capture_status,
        source_url: item.source_url,
        title: item.caption ?? null,
        thumbnail_url: item.thumbnail_url ?? null
      })),
      planned_total: total,
      pending: total,
      processed: 0,
      resume_from_index: 0,
      capture_session_status: "ready",
      backend: {
        ...createWholeProfileHarvestIdleState(at).harvest.backend,
        capture_session: {
          ...createWholeProfileHarvestIdleState(at).harvest.backend.capture_session,
          status: "ready",
          session_id: SESSION_ID,
          created: false,
          updated_at: at
        }
      },
      started_at: at,
      updated_at: at
    },
    debug: {
      ...createWholeProfileHarvestIdleState(at).debug,
      last_response_summary: {
        batch_collection_ui_state: "collecting_videos_locked",
        batch_heartbeat_at: at
      }
    },
    started_at: at,
    updated_at: at
  };
}

function installChromeStorage(storage: MemoryStorage): void {
  (globalThis as unknown as { chrome: unknown }).chrome = {
    storage: {
      local: {
        get: async (key: string | string[] | Record<string, unknown> | null | undefined): Promise<Record<string, unknown>> => {
          if (typeof key === "string") return { [key]: storage.values[key] };
          if (Array.isArray(key)) return Object.fromEntries(key.map((entry) => [entry, storage.values[entry]]));
          if (key && typeof key === "object") {
            const out: Record<string, unknown> = {};
            for (const [entry, fallback] of Object.entries(key)) out[entry] = storage.values[entry] ?? fallback;
            return out;
          }
          return { ...storage.values };
        },
        set: async (items: Record<string, unknown>): Promise<void> => storage.set(items),
        remove: async (key: string): Promise<void> => { delete storage.values[key]; }
      }
    }
  };
}

function installVerifyFetch(existingIdsProvider: () => string[], calls: FetchCall[]): void {
  (globalThis as unknown as { fetch: unknown }).fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    let body: Record<string, unknown> | null = null;
    if (typeof init?.body === "string") {
      body = JSON.parse(init.body) as Record<string, unknown>;
    }
    calls.push({ url, init, body });
    if (url.endsWith("/douyin-extension/capture-inbox/items/verify")) {
      const requested = new Set(
        (Array.isArray(body?.aweme_ids) ? body.aweme_ids as string[] : [])
          .map((id) => id.trim())
          .filter(Boolean)
      );
      const existing = new Set(existingIdsProvider().map((id) => id.trim()).filter(Boolean));
      const matched = requested.size > 0
        ? Array.from(requested).filter((id) => existing.has(id))
        : Array.from(existing);
      return new Response(JSON.stringify({ ok: true, items: matched.map((id) => ({ aweme_id: id, item_id: `item_${id}` })) }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }
    if (url.endsWith("/openapi.json")) {
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    throw new Error(`unexpected fetch ${url}`);
  };
}

function makeRuntime(
  storage: MemoryStorage,
  flushCalls: FlushCall[],
  nowRef: { tick: number },
  profileItemsOverride: { captured: number; ids: string[] } | null = null
): WholeProfileHarvestRuntime {
  return {
    storage,
    now: () => iso(nowRef.tick++),
    random: () => 0.42,
    getBackendBaseUrl: () => "https://backend.test",
    getActiveTab: async () => ({ id: 123, url: PROFILE_URL }),
    ensureContentScriptReady: async () => ({ ok: true, status: "ready", page_type: "profile", current_url: PROFILE_URL }),
    getCalibration: async () => ({ ready: true }),
    scanProfile: async () => ({
      status: "success",
      reason: null,
      cards: [],
      raw_candidate_count: 0,
      accepted_target_count: 0,
      rejected_target_count: 0,
      targets: [],
      target_details: [],
      rejected_candidates_sample: [],
      scan_rounds: 0,
      stop_reason: null,
      scroll_container_found: true,
      diagnostics: makeScanDiagnostics()
    }),
    openDirectModal: async () => undefined,
    extractModalMetrics: async () => ({
      duration_seconds: 1,
      duration_text: "1s",
      like_count: 1,
      comment_count: 1,
      favorite_count: 1,
      share_count: 1,
      current_modal_id_before: null,
      current_modal_id_after: null,
      extracted_aweme_id: null,
      source_used: "test_fixture",
      data_integrity_status: "passed",
      error: null
    }),
    listCaptureSessions: async () => ({
      ok: true,
      total_count: 1,
      sessions: [{
        id: SESSION_ID,
        session_id: SESSION_ID,
        profile_url: PROFILE_URL,
        normalized_profile_url: PROFILE_URL,
        profile_identifier: "MS4wLjABAAAA-hybrid-regression",
        status: "ready",
        created_at: iso(0),
        updated_at: iso(0),
        captured_item_count: 0,
        ready_item_count: 0,
        needs_action_count: 0
      }]
    }),
    createCanonicalHarvestSession: async () => ({ ok: true, session_id: SESSION_ID, created: false, status: 200 }),
    listCaptureSessionItems: async () => ({ ok: true, status: 200, items: [] }),
    listCaptureInboxProfileItems: async () => {
      // Mirror Capture Inbox profile card. Optional override simulates the web
      // card being ahead of local arithmetic (the production bug: BE 20, UI 10).
      if (profileItemsOverride) {
        return {
          ok: true,
          status: 200,
          items: profileItemsOverride.ids.map((id) => ({ aweme_id: id, id: `item_${id}`, item_id: `item_${id}` })),
          items_count: profileItemsOverride.ids.length,
          counts: {
            captured: profileItemsOverride.captured,
            ready: profileItemsOverride.captured,
            dup: 0,
            fail: 0
          },
          profile_identifier: "MS4wLjABAAAA-hybrid-regression"
        };
      }
      const state = storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined;
      const snapshot = state?.post_scan_counter_snapshot;
      const snapshotIds = snapshot?.backend_captured_aweme_ids ?? [];
      const queueCompleteIds = (state?.harvest.queue ?? [])
        .filter((item) => item.status === "already_collected" || item.capture_status === "complete")
        .map((item) => item.aweme_id);
      const writtenIds = flushCalls.flatMap((call) => call.awemeIds);
      const mergedIds = Array.from(new Set([...snapshotIds, ...queueCompleteIds, ...writtenIds]));
      const captured = Math.max(snapshot?.already_collected ?? 0, snapshot?.backend_captured ?? 0, mergedIds.length);
      return {
        ok: true,
        status: 200,
        items: mergedIds.map((id) => ({ aweme_id: id, id: `item_${id}`, item_id: `item_${id}` })),
        items_count: mergedIds.length,
        counts: { captured, ready: captured, dup: 0, fail: 0 },
        profile_identifier: "MS4wLjABAAAA-hybrid-regression"
      };
    },
    listCaptureInboxProfileSummary: async () => {
      if (profileItemsOverride) {
        return {
          ok: true,
          status: 200,
          total_count: profileItemsOverride.captured,
          counts: {
            captured: profileItemsOverride.captured,
            ready: profileItemsOverride.captured,
            dup: 0,
            fail: 0,
            needs_action: 0
          },
          profile_identifier: "MS4wLjABAAAA-hybrid-regression",
          source: "capture_inbox_profile_summary"
        };
      }
      const state = storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState | undefined;
      const snapshot = state?.post_scan_counter_snapshot;
      const snapshotIds = snapshot?.backend_captured_aweme_ids ?? [];
      const queueCompleteIds = (state?.harvest.queue ?? [])
        .filter((item) => item.status === "already_collected" || item.capture_status === "complete")
        .map((item) => item.aweme_id);
      const writtenIds = flushCalls.flatMap((call) => call.awemeIds);
      const mergedIds = Array.from(new Set([...snapshotIds, ...queueCompleteIds, ...writtenIds]));
      const captured = Math.max(snapshot?.already_collected ?? 0, snapshot?.backend_captured ?? 0, mergedIds.length);
      return {
        ok: true,
        status: 200,
        total_count: captured,
        counts: { captured, ready: captured, dup: 0, fail: 0, needs_action: 0 },
        profile_identifier: "MS4wLjABAAAA-hybrid-regression",
        source: "capture_inbox_profile_summary"
      };
    },
    readNetworkCacheFromTab: async () => [],
    readPassiveProbeDiagnosticsFromTab: async () => ({}),
    flushCanonicalHarvestPayload: async (payload, headers) => {
      const items = Array.isArray((payload as Record<string, unknown>).items)
        ? (payload as Record<string, unknown>).items as Array<Record<string, unknown>>
        : [];
      flushCalls.push({ payload, headers, awemeIds: items.map((item) => String(item.aweme_id)) });
      return { ok: true, status: 200, body: { ok: true }, error_code: null, error_message: null };
    },
    sleep: async () => undefined
  };
}

async function setup(total: number): Promise<{ storage: MemoryStorage; runtime: WholeProfileHarvestRuntime; flushCalls: FlushCall[]; fetchCalls: FetchCall[]; nowRef: { tick: number } }> {
  const storage = new MemoryStorage();
  installChromeStorage(storage);
  storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = buildState(total);
  storage.values.apiAuthToken = "test-token";
  const flushCalls: FlushCall[] = [];
  const fetchCalls: FetchCall[] = [];
  installVerifyFetch(() => [], fetchCalls);
  const nowRef = { tick: 10 };
  const runtime = makeRuntime(storage, flushCalls, nowRef);
  return { storage, runtime, flushCalls, fetchCalls, nowRef };
}

function withLargeProfileWindow(state: WholeProfileHarvestState, queue: WholeProfileHarvestQueueItem[], targetDetails: WholeProfileHarvestTargetDetail[], total: number, at = state.updated_at): WholeProfileHarvestState {
  const windowIds = queue.map((item) => item.aweme_id);
  return {
    ...state,
    profile_scan: {
      ...state.profile_scan,
      raw_candidate_count: total,
      accepted_target_count: total,
      targets: windowIds,
      target_details: targetDetails,
      diagnostics: {
        ...(state.profile_scan.diagnostics && typeof state.profile_scan.diagnostics === "object" ? state.profile_scan.diagnostics as Record<string, unknown> : {}),
        large_profile_mode: "yes",
        queue_total_persisted: total,
        queue_total_visible: queue.length,
        large_profile_collect_source: "repository_cursor_status_query_22C14B"
      }
    },
    verify: {
      ...state.verify,
      raw_candidate_count: total,
      accepted_target_count: total,
      verified_target_count: total,
      targets: windowIds,
      target_details: targetDetails,
      diagnostics: {
        ...(state.verify.diagnostics && typeof state.verify.diagnostics === "object" ? state.verify.diagnostics as Record<string, unknown> : {}),
        large_profile_mode: "yes",
        queue_total_persisted: total,
        queue_total_visible: queue.length
      }
    },
    post_scan_counter_snapshot: state.post_scan_counter_snapshot
      ? {
          ...state.post_scan_counter_snapshot,
          scanned_total: total,
          new: Math.min(total, state.post_scan_counter_snapshot.new ?? total),
          queue: Math.min(total, state.post_scan_counter_snapshot.queue ?? total)
        }
      : state.post_scan_counter_snapshot,
    harvest: {
      ...state.harvest,
      queue,
      queue_preview: queue.slice(0, 10).map((item) => ({ index: item.index, aweme_id: item.aweme_id, capture_status: item.capture_status, source_url: item.source_url, title: item.caption ?? null, thumbnail_url: item.thumbnail_url ?? null })),
      planned_total: total,
      pending: queue.length > 0
        ? queue.filter((item) => item.status === "pending" || item.status === "new").length
        : Math.max(0, state.harvest.pending),
      resume_from_index: queue.length > 0 ? 0 : null,
      updated_at: at
    },
    updated_at: at
  };
}

function restartCollectingState(state: WholeProfileHarvestState, selectedIds: string[], at: string): WholeProfileHarvestState {
  return {
    ...state,
    status: "harvesting",
    phase: "harvest",
    workflow: {
      ...state.workflow,
      collection: { status: "running", started_at: at, updated_at: at, completed_at: null, last_error: null },
      active_task: "collect_videos",
      action_lock: "collecting"
    },
    collect_job: {
      ...state.collect_job,
      job_id: "hybrid_collect_job",
      state: "starting",
      started_at: at,
      updated_at: at,
      heartbeat_at: at,
      completed_at: null,
      runner_ack_at: null,
      current_step: "starting",
      batch_limit: 10,
      selected_count: selectedIds.length,
      selected_aweme_ids: selectedIds,
      selected_indexes: selectedIds.map((_, index) => index),
      start_index: 0,
      runtime_generation: (state.collect_job.runtime_generation ?? 1) + 1,
      lock_owner: "hybrid_collect_job",
      lock_acquired_at: at,
      lock_expires_at: iso(1060),
      startup_deadline_at: iso(1060),
      lock_released: false,
      recoverable: false,
      heartbeat_updates_count: state.collect_job.heartbeat_updates_count + 1
    },
    active_collect_runtime: {
      ...state.active_collect_runtime,
      job_id: "hybrid_collect_job",
      runtime_generation: state.active_collect_runtime.runtime_generation + 1,
      canonical_state: "starting",
      canonical_phase: "batch_collect",
      current_step: "starting",
      batch_limit: 10,
      selected_count: selectedIds.length,
      lock_owner: "hybrid_collect_job",
      lock_expires_at: iso(1060),
      heartbeat_at: at,
      updated_at: at
    },
    debug: { ...state.debug, last_response_summary: { ...summary(state), batch_collection_ui_state: "collecting_videos_locked", batch_heartbeat_at: at } },
    updated_at: at
  };
}

function summary(state: WholeProfileHarvestState): Record<string, unknown> {
  return (state.debug.last_response_summary && typeof state.debug.last_response_summary === "object")
    ? state.debug.last_response_summary as Record<string, unknown>
    : {};
}

function assertUnlocked(state: WholeProfileHarvestState): void {
  const s = summary(state);
  assert.equal(state.status, "completed");
  assert.equal(state.phase, "completed");
  assert.equal(state.workflow.collection.status, "idle");
  assert.equal(state.workflow.active_task, null);
  assert.equal(state.workflow.action_lock, null);
  assert.equal(state.active_collect_runtime.job_id, null);
  assert.equal(state.active_collect_runtime.canonical_state, "idle");
  assert.equal(s.hybrid_collector_completed, "yes");
  assert.equal(s.batch_collection_ui_state, "idle");
  assert.equal(s.batch_heartbeat_at, null);
}

async function testFullLoopWriteOkReconcilesQueueAndUnlocks(): Promise<void> {
  const { storage, runtime, flushCalls } = await setup(12);

  // Hybrid ignores modal-era "Next 10" and drains all remaining actionable (≤500).
  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
  const finalState = await readWholeProfileHarvestState(storage, iso(999));

  assert.equal(result.harvest.queue.filter((item) => item.status === "already_collected").length, 12);
  assert.equal(flushCalls.length, 1, "Phase 4.4e: default flush_chunk_size batches all finalized items into one request");
  assert.equal(flushCalls[0]?.awemeIds.length, 12);
  assert.deepEqual(flushCalls.flatMap((call) => call.awemeIds), Array.from({ length: 12 }, (_, index) => awemeId(index + 1)));
  assert.equal(summary(result).hybrid_runner_flush_mode, "interleaved_chunked");
  assert.equal(summary(result).hybrid_runner_flush_chunk_count, 1);
  assert.equal(summary(result).hybrid_runner_flush_chunk_limit, HYBRID_FLUSH_CHUNK_SIZE_DEFAULT);
  assert.equal(summary(result).hybrid_runner_flush_ready_count, 0);
  for (let index = 0; index < 12; index++) {
    assert.equal(finalState.harvest.queue[index]?.status, "already_collected");
    assert.equal(finalState.harvest.queue[index]?.capture_status, "complete");
    const reconciledSource = finalState.harvest.queue[index]?.profile_card_evidence.backend_reconciled_source;
    assert.ok(
      reconciledSource === "hybrid_backend_write_ok"
        || reconciledSource === "hybrid_post_run_summary"
        || reconciledSource === "hybrid_post_run_capture_inbox_card",
      `expected write_ok or post_run card reconcile source, got ${String(reconciledSource)}`
    );
  }
  assert.equal(finalState.harvest.pending, 0);
  assert.equal(finalState.harvest.resume_from_index, null);
  assert.equal(finalState.post_scan_counter_snapshot?.already_collected, 12);
  assert.equal(finalState.post_scan_counter_snapshot?.backend_captured, 12);
  assert.equal(finalState.post_scan_counter_snapshot?.queue, 0);
  assert.equal(finalState.post_scan_counter_snapshot?.new, 0);
  assertUnlocked(finalState);
  assert.equal(summary(finalState).hybrid_runner_backend_write_ok, "yes");
  assert.equal(summary(finalState).hybrid_runner_write_ok_count, 12);
  assert.equal((storage.values.hybrid_runner_fossil as Record<string, unknown>).hybrid_readback_path, "loop_complete");
}

async function testSecondRunSkipsAlreadyCollectedAndFlushesNextBatch(): Promise<void> {
  // First click drains the full queue (Hybrid ignores Next-N). Second click
  // pre-skips everything already on backend and writes nothing.
  const { storage, runtime, flushCalls } = await setup(12);

  await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
  const afterFirst = await readWholeProfileHarvestState(storage, iso(1000));
  assert.equal(afterFirst.harvest.pending, 0);
  assert.equal(afterFirst.post_scan_counter_snapshot?.already_collected, 12);

  const restarted: WholeProfileHarvestState = {
    ...afterFirst,
    status: "harvesting",
    phase: "harvest",
    workflow: {
      ...afterFirst.workflow,
      collection: { status: "running", started_at: iso(1001), updated_at: iso(1001), completed_at: null, last_error: null },
      active_task: "collect_videos",
      action_lock: "collecting"
    },
    collect_job: {
      ...afterFirst.collect_job,
      job_id: "hybrid_collect_job",
      state: "starting",
      started_at: iso(1001),
      updated_at: iso(1001),
      heartbeat_at: iso(1001),
      completed_at: null,
      runner_ack_at: null,
      current_step: "starting",
      batch_limit: 10,
      selected_count: 0,
      selected_aweme_ids: [],
      selected_indexes: [],
      start_index: 0,
      runtime_generation: (afterFirst.collect_job.runtime_generation ?? 1) + 1,
      lock_owner: "hybrid_collect_job",
      lock_acquired_at: iso(1001),
      lock_expires_at: iso(1060),
      startup_deadline_at: iso(1060),
      lock_released: false,
      recoverable: false,
      heartbeat_updates_count: afterFirst.collect_job.heartbeat_updates_count + 1
    },
    active_collect_runtime: {
      ...afterFirst.active_collect_runtime,
      job_id: "hybrid_collect_job",
      runtime_generation: afterFirst.active_collect_runtime.runtime_generation + 1,
      canonical_state: "starting",
      canonical_phase: "batch_collect",
      current_step: "starting",
      batch_limit: 10,
      selected_count: 0,
      lock_owner: "hybrid_collect_job",
      lock_expires_at: iso(1060),
      heartbeat_at: iso(1001),
      updated_at: iso(1001)
    },
    debug: {
      ...afterFirst.debug,
      last_response_summary: { ...summary(afterFirst), batch_collection_ui_state: "collecting_videos_locked", batch_heartbeat_at: iso(1001) }
    },
    updated_at: iso(1001)
  };
  await writeWholeProfileHarvestState(storage, restarted);
  flushCalls.length = 0;

  const second = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });

  assert.equal(flushCalls.length, 0, "second click must pre-skip all backend hits and write nothing");
  assert.equal(second.harvest.queue.filter((item) => item.status === "already_collected").length, 12);
  assert.equal(second.harvest.pending, 0);
  assert.equal(second.harvest.resume_from_index, null);
  assert.equal(second.post_scan_counter_snapshot?.already_collected, 12);
  assert.equal(second.post_scan_counter_snapshot?.backend_captured, 12);
  assert.equal(second.post_scan_counter_snapshot?.queue, 0);
  assert.equal(second.post_scan_counter_snapshot?.new, 0);
  assertUnlocked(second);
}

async function testPreSkipAllCollectedReconcilesQueueAndUnlocks(): Promise<void> {
  const storage = new MemoryStorage();
  installChromeStorage(storage);
  storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = buildState(10);
  storage.values.apiAuthToken = "test-token";
  const existing = Array.from({ length: 10 }, (_, index) => awemeId(index + 1));
  const fetchCalls: FetchCall[] = [];
  installVerifyFetch(() => existing, fetchCalls);
  const flushCalls: FlushCall[] = [];
  const runtime = makeRuntime(storage, flushCalls, { tick: 20 });

  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });

  assert.equal(flushCalls.length, 0);
  assert.equal(fetchCalls.filter((call) => call.url.endsWith("/douyin-extension/capture-inbox/items/verify")).length, 1);
  assert.equal(result.harvest.queue.filter((item) => item.status === "already_collected").length, 10);
  assert.equal(result.harvest.pending, 0);
  assert.equal(result.harvest.resume_from_index, null);
  assert.equal(result.post_scan_counter_snapshot?.already_collected, 10);
  assert.equal(result.post_scan_counter_snapshot?.backend_captured, 10);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  for (const item of result.harvest.queue) {
    assert.equal(item.capture_status, "complete");
    assert.equal(item.profile_card_evidence.backend_reconciled_source, "hybrid_pre_skip_backend_verify");
  }
  assertUnlocked(result);
  assert.equal(summary(result).hybrid_runner_pre_skip_total, 10);
  assert.equal(summary(result).hybrid_runner_pre_skip_already_collected, 10);
  assert.equal(summary(result).hybrid_runner_pre_skip_pending, 0);
  assert.equal(summary(result).hybrid_runner_pre_skip_source, "backend_verify_api_profile");
  assert.equal((storage.values.hybrid_runner_fossil as Record<string, unknown>).hybrid_readback_path, "pre_skip");
}

async function testLargeProfilePreSkipUpdatesRepositoryAndCountersThenFlushesNextWindow(): Promise<void> {
  resetProfileTargetRepositoryForTests();
  const repository = new InMemoryProfileTargetRepository();
  setProfileTargetRepositoryFactoryForTests(() => repository);
  try {
    const total = 138;
    const profile = profileIdentifierFromUrl(PROFILE_URL);
    const allQueue = Array.from({ length: total }, (_, index) => makeQueueItem(awemeId(index + 1), index + 1));
    const allDetails = allQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    await repository.upsertProfileTargets(profile, allQueue, allDetails, iso(0));

    const storage = new MemoryStorage();
    installChromeStorage(storage);
    storage.values.apiAuthToken = "test-token";
    const firstWindow = buildQueueWindowFromRecords((await repository.getProfileTargetsByStatus(profile, ["pending"], 10, 0)).records);
    storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = withLargeProfileWindow(buildState(total), firstWindow.queue, firstWindow.targetDetails, total);
    const existing = Array.from({ length: 10 }, (_, index) => awemeId(index + 1));
    const fetchCalls: FetchCall[] = [];
    installVerifyFetch(() => existing, fetchCalls);
    const flushCalls: FlushCall[] = [];
    const runtime = makeRuntime(storage, flushCalls, { tick: 30 });

    const first = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
    assert.equal(flushCalls.length, 0, "all first-window items already in backend should pre-skip without write");
    assert.equal(first.post_scan_counter_snapshot?.scanned_total, total);
    assert.equal(first.post_scan_counter_snapshot?.already_collected, 10);
    assert.equal(first.post_scan_counter_snapshot?.backend_captured, 10);
    assert.equal(first.post_scan_counter_snapshot?.queue, 128);
    assert.equal(first.post_scan_counter_snapshot?.new, 128);
    const afterFirstPending = await repository.getProfileTargetsByStatus(profile, ["pending"], 10, 0);
    assert.equal(afterFirstPending.records[0]?.aweme_id, awemeId(11), "repository must advance next pending window after pre-skip reconcile");
    const collectedCounts = await repository.countProfileTargetsByStatus(profile);
    assert.equal(collectedCounts.counts.find((item) => item.status === "already_collected")?.count, 10);

    const nextWindow = buildQueueWindowFromRecords(afterFirstPending.records);
    const restarted = restartCollectingState(withLargeProfileWindow(first, nextWindow.queue, nextWindow.targetDetails, total, iso(1001)), nextWindow.queue.map((item) => item.aweme_id), iso(1001));
    await writeWholeProfileHarvestState(storage, restarted);
    flushCalls.length = 0;
    installVerifyFetch(() => existing, fetchCalls);

    const second = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
    assert.deepEqual(flushCalls.flatMap((call) => call.awemeIds), Array.from({ length: 10 }, (_, index) => awemeId(index + 11)), "second run must flush the next repository window, not re-select the first 10");
    assert.equal(second.post_scan_counter_snapshot?.scanned_total, total);
    assert.equal(second.post_scan_counter_snapshot?.already_collected, 20);
    assert.equal(second.post_scan_counter_snapshot?.backend_captured, 20);
    assert.equal(second.post_scan_counter_snapshot?.queue, 118);
    assert.equal(second.post_scan_counter_snapshot?.new, 118);
    const afterSecondPending = await repository.getProfileTargetsByStatus(profile, ["pending"], 10, 0);
    assert.equal(afterSecondPending.records[0]?.aweme_id, awemeId(21));
    assertUnlocked(second);
  } finally {
    resetProfileTargetRepositoryForTests();
  }
}

async function testStaleStartingWriteCannotClobberCompleted(): Promise<void> {
  const { storage, runtime } = await setup(10);
  // Drive a pre-skip-all-collected completion so storage holds completed + done key.
  installVerifyFetch(() => Array.from({ length: 10 }, (_, index) => awemeId(index + 1)), []);
  const completed = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
  assertUnlocked(completed);
  assert.equal(completed.collect_job.state, "completed");
  assert.equal(summary(completed).hybrid_collector_completed, "yes");

  const doneSignal = storage.values[HYBRID_COLLECTION_DONE_KEY] as Record<string, unknown>;
  assert.equal(doneSignal.job_id, completed.collect_job.job_id);
  assert.equal(doneSignal.runtime_generation, completed.collect_job.runtime_generation ?? 0);

  // Simulate the popup probe-sync TOCTOU: a stale snapshot captured while the
  // job was still "starting" (same job_id + generation) tries to land after
  // completion. The chokepoint must reject and preserve completed.
  const staleStarting: WholeProfileHarvestState = {
    ...completed,
    status: "harvesting",
    phase: "harvest",
    collect_job: {
      ...completed.collect_job,
      state: "starting",
      completed_at: null,
      runner_ack_at: null,
      lock_owner: completed.collect_job.job_id,
      lock_expires_at: iso(60),
      lock_released: false,
      current_step: "starting",
      heartbeat_at: iso(1)
    },
    active_collect_runtime: {
      ...completed.active_collect_runtime,
      job_id: completed.collect_job.job_id,
      canonical_state: "starting",
      canonical_phase: "batch_collect",
      current_step: "starting",
      heartbeat_at: iso(1),
      lock_owner: completed.collect_job.job_id,
      lock_expires_at: iso(60)
    },
    workflow: {
      ...completed.workflow,
      collection: { status: "idle", started_at: null, updated_at: iso(1), completed_at: null, last_error: null },
      active_task: null,
      action_lock: null
    },
    debug: {
      ...completed.debug,
      last_response_summary: {
        active_runner_target: "wholeProfileHarvest/controller.runBatchCollectHybridNetworkCacheMode",
        hybrid_network_cache_mode_flag: "enabled"
      }
    },
    updated_at: iso(1)
  };

  const guard = evaluateCollectJobWriteGuard(completed, staleStarting, {
    job_id: String(doneSignal.job_id),
    runtime_generation: Number(doneSignal.runtime_generation ?? 0),
    completed_at: String(doneSignal.completed_at),
    outcome: String(doneSignal.outcome)
  });
  assert.equal(guard.reject, true);
  assert.equal(guard.reject ? guard.reason : null, "terminal_collect_job_revert");

  const afterClobberAttempt = await writeWholeProfileHarvestState(storage, staleStarting);
  assert.equal(afterClobberAttempt.collect_job.state, "completed", "stale starting write must not clobber completed collect_job");
  assert.equal(summary(afterClobberAttempt).hybrid_collector_completed, "yes");
  const rejectionBreadcrumb = afterClobberAttempt.debug.last_request_summary && typeof afterClobberAttempt.debug.last_request_summary === "object"
    ? afterClobberAttempt.debug.last_request_summary as Record<string, unknown>
    : {};
  assert.equal(rejectionBreadcrumb.trace_stale_state_write_rejected, "yes");
  assert.equal(rejectionBreadcrumb.trace_stale_state_write_rejected_reason, "terminal_collect_job_revert");
  assert.equal(afterClobberAttempt.active_collect_runtime.canonical_state, "idle");
  assertUnlocked(afterClobberAttempt);

  // Defense-in-depth: even if main state were clobbered, the done-key override
  // must unlock the popup lock derivation.
  const clobberedUiState: WholeProfileHarvestState = {
    ...staleStarting,
    harvest: completed.harvest
  };
  const overridden = applyHybridCollectionDoneOverride(clobberedUiState, {
    job_id: String(doneSignal.job_id),
    runtime_generation: Number(doneSignal.runtime_generation ?? 0),
    completed_at: String(doneSignal.completed_at),
    outcome: String(doneSignal.outcome)
  });
  const lock = deriveAuthoritativeRunnerLock(overridden, Date.parse(iso(2)));
  assert.equal(lock.active, false, "done-key override must release Collecting videos lock after clobber");
  assert.ok(
    lock.source === "collect_job_terminal" || lock.source === "hybrid_collector_completed_override",
    `expected terminal/hybrid unlock source, got ${lock.source}`
  );
  assert.equal(overridden.collect_job.state, "completed");
  assert.equal(summary(overridden).hybrid_collector_completed, "yes");

  // Also prove unlock when only hybrid_collector_completed is restored and
  // collect_job/runtime remain clobbered to starting (done-key partial apply).
  const partialOverride: WholeProfileHarvestState = {
    ...clobberedUiState,
    debug: {
      ...clobberedUiState.debug,
      last_response_summary: {
        ...(clobberedUiState.debug.last_response_summary as Record<string, unknown>),
        hybrid_collector_completed: "yes"
      }
    }
  };
  const partialLock = deriveAuthoritativeRunnerLock(partialOverride, Date.parse(iso(2)));
  assert.equal(partialLock.active, false, "hybrid_collector_completed alone must unlock stale starting runtime");
  assert.equal(partialLock.source, "hybrid_collector_completed_override");
}

async function testPreSkipDrainsBackendHitsThenWritesNextBatchInOneClick(): Promise<void> {
  // Operator symptom: Next 10 all already on backend → write_ok n/a, "backend not working".
  // One Start Collecting must drain every backend hit in the actionable window, then
  // write the first truly pending batch in the same run.
  const { storage, runtime, flushCalls } = await setup(20);
  const backendIds = Array.from({ length: 15 }, (_, index) => awemeId(index + 1));
  installVerifyFetch(() => backendIds, []);

  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
  assert.equal(flushCalls.length, 1, "Phase 4.4e: remaining 5 items flush in one chunk (<=500)");
  assert.deepEqual(
    flushCalls.flatMap((call) => call.awemeIds),
    Array.from({ length: 5 }, (_, index) => awemeId(index + 16))
  );
  assert.equal(result.post_scan_counter_snapshot?.already_collected, 20);
  assert.equal(result.post_scan_counter_snapshot?.backend_captured, 20);
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(result.post_scan_counter_snapshot?.scanned_total, 20);
  assertUnlocked(result);
}

async function testPreSkipDoesNotInflateAlreadyCollectedOrScannedTotal(): Promise<void> {
  // Operator symptom: Already collected 100 + New 108 > header 138, backend card 90.
  // Pre-skip must fill missing ids without adding them on top of an already-correct count,
  // and must never grow scanned_total via captured+pending.
  const { storage, runtime, flushCalls } = await setup(20);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  const backendIds = Array.from({ length: 10 }, (_, index) => awemeId(index + 1));
  const seeded: WholeProfileHarvestState = {
    ...before,
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 20,
      backend_captured_aweme_ids: backendIds,
      backend_captured: 10,
      backend_ready: 10,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 10,
      incomplete: 0,
      need_retry: 0,
      new: 10,
      queue: 10,
      applied_at: iso(0)
    },
    collect_job: {
      ...before.collect_job,
      job_id: "hybrid_collect_job",
      state: "starting",
      started_at: iso(1),
      updated_at: iso(1),
      heartbeat_at: iso(1),
      runner_ack_at: null,
      current_step: "starting",
      batch_limit: 10,
      selected_count: 10,
      runtime_generation: (before.collect_job.runtime_generation ?? 0) + 1,
      lock_owner: "hybrid_collect_job",
      lock_acquired_at: iso(1),
      lock_expires_at: iso(60),
      startup_deadline_at: iso(60),
      lock_released: false
    }
  };
  await writeWholeProfileHarvestState(storage, seeded);
  installVerifyFetch(() => backendIds, []);

  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
  assert.equal(result.post_scan_counter_snapshot?.already_collected, 20, "pre_skip must not inflate past true backend+write total");
  assert.equal(result.post_scan_counter_snapshot?.scanned_total, 20, "scanned_total must stay at profile total, not captured+pending");
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.ok((result.post_scan_counter_snapshot?.already_collected ?? 0) + (result.post_scan_counter_snapshot?.new ?? 0) <= (result.post_scan_counter_snapshot?.scanned_total ?? 0));
  assert.equal(flushCalls.length, 1, "Phase 4.4e: items 11-20 flush in one chunk after pre_skip of 1-10");
}

async function testBatch2DoesNotFalseCompleteWhenBackendGapRemains(): Promise<void> {
  // Operator symptom: backend 500/734, tile New=234, pre_skip_already_collected=468,
  // pre_skip_pending=0, zero writes. Two backend-hit windows must not masquerade as done.
  resetProfileTargetRepositoryForTests();
  const repository = new InMemoryProfileTargetRepository();
  setProfileTargetRepositoryFactoryForTests(() => repository);
  try {
    const total = 734;
    const profile = profileIdentifierFromUrl(PROFILE_URL);
    const backendIds = Array.from({ length: 500 }, (_, index) => awemeId(index + 1));
    const allQueue = Array.from({ length: total }, (_, index) => makeQueueItem(awemeId(index + 1), index + 1));
    const allDetails = allQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    await repository.upsertProfileTargets(profile, allQueue, allDetails, iso(0));
    for (const id of backendIds) {
      await repository.updateTargetStatus(profile, id, { status: "already_collected", updated_at: iso(0) });
    }

    const staleQueue = Array.from({ length: 234 }, (_, index) => makeQueueItem(awemeId(index + 267), index + 267));
    const staleDetails = staleQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));

    const storage = new MemoryStorage();
    installChromeStorage(storage);
    storage.values.apiAuthToken = "test-token";
    const seeded = withLargeProfileWindow(buildState(total), staleQueue, staleDetails, total);
    storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = {
      ...seeded,
      post_scan_counter_snapshot: {
        status: "applied",
        source: "backend_capture_inbox_profile_summary",
        profile_identifier: profile,
        scanned_total: total,
        backend_captured_aweme_ids: backendIds,
        backend_captured: 500,
        backend_ready: 500,
        backend_dup: 0,
        backend_fail: 0,
        already_collected: 500,
        incomplete: 0,
        need_retry: 0,
        new: 234,
        queue: 234,
        applied_at: iso(0)
      },
      harvest: {
        ...seeded.harvest,
        batch_limit: 234,
        queue: staleQueue,
        queue_preview: staleQueue.slice(0, 10).map((item) => ({
          index: item.index,
          aweme_id: item.aweme_id,
          capture_status: item.capture_status,
          source_url: item.source_url,
          title: item.caption ?? null,
          thumbnail_url: item.thumbnail_url ?? null
        })),
        pending: staleQueue.length
      },
      collect_job: {
        ...seeded.collect_job,
        batch_limit: 234,
        selected_count: 234
      }
    };

    const fetchCalls: FetchCall[] = [];
    installVerifyFetch(() => backendIds, fetchCalls);
    const flushCalls: FlushCall[] = [];
    const runtime = makeRuntime(storage, flushCalls, { tick: 40 }, { captured: 500, ids: backendIds });

    const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 234, mode: "new_and_incomplete" });
    const fossil = summary(result);
    const remaining = Math.max(0, (result.post_scan_counter_snapshot?.new ?? 0));
    const wroteNewItems = flushCalls.flatMap((call) => call.awemeIds).some((id) => !backendIds.includes(id));

    assert.ok(
      wroteNewItems || fossil.hybrid_runner_outcome === "phase_4_4d_loop_all_failed",
      "batch 2 must flush uncaptured ids or fail loudly — never false-complete with zero writes while gap remains"
    );
    assert.ok(
      wroteNewItems || remaining === 0,
      "when no flush happens, runner must not report success while snapshot.new > 0"
    );
    if (wroteNewItems) {
      assert.ok(flushCalls.flatMap((call) => call.awemeIds).some((id) => Number(id.slice(-3)) >= 501), "flush must target uncaptured tail ids (501+)");
      assert.ok(flushCalls.flatMap((call) => call.awemeIds).length > 0, "flush must include pending uncaptured ids");
    } else {
      assert.equal(fossil.hybrid_runner_outcome, "phase_4_4d_loop_all_failed");
    }
  } finally {
    resetProfileTargetRepositoryForTests();
  }
}

async function testPreSkipFailsWhenGapRemainsAndRepositoryCannotAdvance(): Promise<void> {
  // Force the operator failure mode: stale visible window is all on backend, but
  // snapshot still reports new=234 and repository has no further pending rows.
  resetProfileTargetRepositoryForTests();
  const repository = new InMemoryProfileTargetRepository();
  setProfileTargetRepositoryFactoryForTests(() => repository);
  try {
    const total = 734;
    const profile = profileIdentifierFromUrl(PROFILE_URL);
    const backendIds = Array.from({ length: 500 }, (_, index) => awemeId(index + 1));
    const staleQueue = Array.from({ length: 234 }, (_, index) => makeQueueItem(awemeId(index + 267), index + 267));
    const staleDetails = staleQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    await repository.upsertProfileTargets(profile, staleQueue, staleDetails, iso(0));
    for (const id of staleQueue.map((item) => item.aweme_id)) {
      await repository.updateTargetStatus(profile, id, { status: "already_collected", updated_at: iso(0) });
    }

    const storage = new MemoryStorage();
    installChromeStorage(storage);
    storage.values.apiAuthToken = "test-token";
    const seeded = withLargeProfileWindow(buildState(total), staleQueue, staleDetails, total);
    storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = {
      ...seeded,
      classification: {
        ...seeded.classification,
        total_candidates: staleQueue.length,
        counts: {
          ...seeded.classification.counts,
          new: staleQueue.length,
          collect: staleQueue.length
        },
        collect_aweme_ids: staleQueue.map((item) => item.aweme_id),
        targets: staleQueue.map((item, index) => ({
          aweme_id: item.aweme_id,
          classification: "new",
          collect: true,
          reason: "fixture_stale_window",
          required_missing_fields: [],
          existing_item_id: null,
          metadata_status: null,
          review_status: null,
          video_url: item.source_url,
          source_url: item.source_url,
          thumbnail_url: item.thumbnail_url,
          caption: item.caption
        }))
      },
      post_scan_counter_snapshot: {
        status: "applied",
        source: "backend_capture_inbox_profile_summary",
        profile_identifier: profile,
        scanned_total: total,
        backend_captured_aweme_ids: backendIds,
        backend_captured: 500,
        backend_ready: 500,
        backend_dup: 0,
        backend_fail: 0,
        already_collected: 500,
        incomplete: 0,
        need_retry: 0,
        new: 234,
        queue: 234,
        applied_at: iso(0)
      }
    };

    const fetchCalls: FetchCall[] = [];
    installVerifyFetch(() => backendIds, fetchCalls);
    const flushCalls: FlushCall[] = [];
    const runtime = makeRuntime(storage, flushCalls, { tick: 50 }, { captured: 500, ids: backendIds });

    const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 234, mode: "new_and_incomplete" });
    const fossil = summary(result);
    assert.equal(flushCalls.length, 0, "no uncaptured targets must not flush");
    assert.equal(result.collect_job.state, "failed", "gap remaining with zero pending must fail, not false-complete");
    assert.equal(fossil.hybrid_runner_outcome, "phase_4_4d_loop_all_failed");
    assert.match(
      String(fossil.trace_collect_job_failed_with_error ?? fossil.hybrid_runner_error ?? ""),
      /234 videos (to collect|still on backend gap)/
    );
  } finally {
    resetProfileTargetRepositoryForTests();
  }
}

async function testTailGapCollectRecoversMissingIdsFromBackendDiff(): Promise<void> {
  const total = 1000;
  const backendIds = Array.from({ length: 998 }, (_, index) => awemeId(index + 1));
  const staleFront = Array.from({ length: 6 }, (_, index) => makeQueueItem(awemeId(index + 1), index + 1));
  const storage = new MemoryStorage();
  installChromeStorage(storage);
  storage.values.apiAuthToken = "test-token";
  const base = buildState(total);
  storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = {
    ...base,
    post_scan_counter_snapshot: {
      ...base.post_scan_counter_snapshot!,
      scanned_total: total,
      backend_captured_aweme_ids: backendIds,
      backend_captured: 998,
      backend_ready: 998,
      already_collected: 998,
      new: 6,
      queue: 6
    },
    harvest: {
      ...base.harvest,
      batch_limit: 6,
      queue: staleFront,
      queue_preview: staleFront.slice(0, 6).map((item) => ({
        index: item.index,
        aweme_id: item.aweme_id,
        capture_status: item.capture_status,
        source_url: item.source_url,
        title: item.caption ?? null,
        thumbnail_url: item.thumbnail_url ?? null
      })),
      pending: staleFront.length,
      planned_total: staleFront.length
    },
    collect_job: {
      ...base.collect_job,
      batch_limit: 6,
      selected_count: 6
    },
    debug: {
      ...base.debug,
      last_response_summary: {
        ...(base.debug.last_response_summary && typeof base.debug.last_response_summary === "object"
          ? base.debug.last_response_summary as Record<string, unknown>
          : {}),
        hybrid_network_cache_mode_flag: "enabled"
      }
    }
  };

  const fetchCalls: FetchCall[] = [];
  installVerifyFetch(() => backendIds, fetchCalls);
  const flushCalls: FlushCall[] = [];
  const runtime = makeRuntime(storage, flushCalls, { tick: 20 }, { captured: 998, ids: backendIds });

  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 6, mode: "new_and_incomplete" });
  const fossil = summary(result);
  const flushedIds = flushCalls.flatMap((call) => call.awemeIds);
  assert.ok(flushedIds.includes(awemeId(999)), "tail gap recovery must flush missing id 999");
  assert.ok(flushedIds.includes(awemeId(1000)), "tail gap recovery must flush missing id 1000");
  assert.notEqual(result.collect_job.state, "failed", "tail gap collect must not fail when missing ids are discoverable");
  assert.ok(
    fossil.hybrid_runner_outcome === "phase_4_4d_loop_completed"
      || result.collect_job.state === "completed",
    "tail gap collect must complete successfully"
  );
}

async function testLargeProfileTailGapUsesRepositoryWhenClassificationWindowed(): Promise<void> {
  resetProfileTargetRepositoryForTests();
  const repository = new InMemoryProfileTargetRepository();
  setProfileTargetRepositoryFactoryForTests(() => repository);
  try {
    const total = 1000;
    const profile = profileIdentifierFromUrl(PROFILE_URL);
    const backendIds = Array.from({ length: 998 }, (_, index) => awemeId(index + 1));
    const allQueue = Array.from({ length: total }, (_, index) => makeQueueItem(awemeId(index + 1), index + 1));
    const allDetails = allQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    await repository.upsertProfileTargets(profile, allQueue, allDetails, iso(0));
    for (const id of backendIds) {
      await repository.updateTargetStatus(profile, id, { status: "already_collected", updated_at: iso(0) });
    }

    const staleQueue = Array.from({ length: 500 }, (_, index) => makeQueueItem(awemeId(index + 1), index + 1));
    const staleDetails = staleQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    const windowedClassificationTargets = staleQueue.map((item, index) => ({
      aweme_id: item.aweme_id,
      classification: "new" as const,
      collect: true,
      reason: "fixture_window_only",
      required_missing_fields: [],
      existing_item_id: null,
      metadata_status: null,
      review_status: null,
      video_url: item.source_url,
      source_url: item.source_url,
      thumbnail_url: item.thumbnail_url ?? null,
      caption: item.caption ?? null
    }));

    const storage = new MemoryStorage();
    installChromeStorage(storage);
    storage.values.apiAuthToken = "test-token";
    const seeded = withLargeProfileWindow(buildState(total), staleQueue, staleDetails, total);
    storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = {
      ...seeded,
      classification: {
        ...seeded.classification,
        total_candidates: total,
        collect_aweme_ids: staleQueue.map((item) => item.aweme_id),
        targets: windowedClassificationTargets
      },
      post_scan_counter_snapshot: {
        status: "applied",
        source: "backend_capture_inbox_profile_summary",
        profile_identifier: profile,
        scanned_total: total,
        backend_captured_aweme_ids: backendIds,
        backend_captured: 998,
        backend_ready: 998,
        backend_dup: 0,
        backend_fail: 0,
        already_collected: 998,
        incomplete: 0,
        need_retry: 0,
        new: 6,
        queue: 6,
        applied_at: iso(0)
      },
      harvest: {
        ...seeded.harvest,
        batch_limit: 6,
        queue: staleQueue,
        pending: staleQueue.length,
        planned_total: staleQueue.length
      },
      collect_job: {
        ...seeded.collect_job,
        batch_limit: 6,
        selected_count: 6
      },
      debug: {
        ...seeded.debug,
        last_response_summary: {
          ...(seeded.debug.last_response_summary && typeof seeded.debug.last_response_summary === "object"
            ? seeded.debug.last_response_summary as Record<string, unknown>
            : {}),
          hybrid_network_cache_mode_flag: "enabled"
        }
      }
    };

    installVerifyFetch(() => backendIds, []);
    const flushCalls: FlushCall[] = [];
    const runtime = makeRuntime(storage, flushCalls, { tick: 30 }, { captured: 998, ids: backendIds });

    const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 6, mode: "new_and_incomplete" });
    const flushedIds = flushCalls.flatMap((call) => call.awemeIds);
    assert.ok(flushedIds.includes(awemeId(999)), "large-profile tail must flush repo-discovered id 999");
    assert.ok(flushedIds.includes(awemeId(1000)), "large-profile tail must flush repo-discovered id 1000");
    assert.notEqual(result.collect_job.state, "failed");
  } finally {
    resetProfileTargetRepositoryForTests();
  }
}

async function testEnsureHarvestQueueReadyRebuildsHybridTailGap(): Promise<void> {
  resetProfileTargetRepositoryForTests();
  const repository = new InMemoryProfileTargetRepository();
  setProfileTargetRepositoryFactoryForTests(() => repository);
  try {
    const total = 1000;
    const profile = profileIdentifierFromUrl(PROFILE_URL);
    const backendIds = Array.from({ length: 998 }, (_, index) => awemeId(index + 1));
    const allQueue = Array.from({ length: total }, (_, index) => makeQueueItem(awemeId(index + 1), index + 1));
    const allDetails = allQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    await repository.upsertProfileTargets(profile, allQueue, allDetails, iso(0));
    for (const id of backendIds) {
      await repository.updateTargetStatus(profile, id, { status: "already_collected", updated_at: iso(0) });
    }

    const staleQueue = Array.from({ length: 500 }, (_, index) => makeQueueItem(awemeId(index + 1), index + 1));
    const staleDetails = staleQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    const storage = new MemoryStorage();
    installChromeStorage(storage);
    storage.values.apiAuthToken = "test-token";
    const seeded = withLargeProfileWindow(buildState(total), staleQueue, staleDetails, total);
    storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] = {
      ...seeded,
      classification: {
        ...seeded.classification,
        collect_aweme_ids: staleQueue.map((item) => item.aweme_id),
        targets: staleQueue.map((item) => ({
          aweme_id: item.aweme_id,
          classification: "new" as const,
          collect: true,
          reason: "fixture_window_only",
          required_missing_fields: [],
          existing_item_id: null,
          metadata_status: null,
          review_status: null,
          video_url: item.source_url,
          source_url: item.source_url,
          thumbnail_url: item.thumbnail_url ?? null,
          caption: item.caption ?? null
        }))
      },
      post_scan_counter_snapshot: {
        status: "applied",
        source: "backend_capture_inbox_profile_summary",
        profile_identifier: profile,
        scanned_total: total,
        backend_captured_aweme_ids: backendIds,
        backend_captured: 998,
        backend_ready: 998,
        already_collected: 998,
        new: 6,
        queue: 6,
        applied_at: iso(0)
      },
      harvest: {
        ...seeded.harvest,
        queue: staleQueue,
        pending: staleQueue.length,
        planned_total: staleQueue.length
      },
      debug: {
        ...seeded.debug,
        last_response_summary: {
          hybrid_network_cache_mode_flag: "enabled"
        }
      }
    };

    installVerifyFetch(() => backendIds, []);
    const flushCalls: FlushCall[] = [];
    const runtime = makeRuntime(storage, flushCalls, { tick: 5 }, { captured: 998, ids: backendIds });
    const before = storage.values[WHOLE_PROFILE_HARVEST_STATE_KEY] as WholeProfileHarvestState;
    const prepared = await ensureHarvestQueueReadyForStartCollecting(runtime, before, iso(1));
    const queueIds = prepared.harvest.queue.map((item) => item.aweme_id);
    assert.ok(queueIds.includes(awemeId(999)), "queue prep must target backend gap id 999");
    assert.ok(queueIds.includes(awemeId(1000)), "queue prep must target backend gap id 1000");
    assert.ok(queueIds.length <= 6, "queue prep must not reload stale 500-item window");
  } finally {
    resetProfileTargetRepositoryForTests();
  }
}

async function testPostRunCardAuthorityOverridesLaggingLocalTiles(): Promise<void> {
  // Production: backend card shows 20 after two batches, but local tiles stay at
  // Already=10 / New=128. Post-run card refresh must force Already=20, New=0
  // when the card reports captured=20 for a 20-video profile.
  const { storage, runtime, flushCalls } = await setup(20);
  const cardIds = Array.from({ length: 20 }, (_, index) => awemeId(index + 1));
  // Rebuild runtime with card override: card is ahead of local write arithmetic.
  const nowRef = { tick: 10 };
  const overriddenRuntime = makeRuntime(storage, flushCalls, nowRef, { captured: 20, ids: cardIds });
  installVerifyFetch(() => [], []);

  const result = await runBatchCollectHybridNetworkCacheMode(overriddenRuntime, { batch_limit: 10, mode: "new_and_incomplete" });
  assert.equal(flushCalls.length, 1, "Phase 4.4e: 10 finalized items use one chunked flush");
  assert.equal(result.post_scan_counter_snapshot?.already_collected, 20, "tiles must adopt Capture Inbox card captured count");
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(result.post_scan_counter_snapshot?.scanned_total, 20);
  assert.equal(summary(result).hybrid_runner_post_run_summary_status, "success_runtime_client");
  assert.equal(summary(result).hybrid_runner_post_run_tile_already, 20);
  assert.equal(summary(result).hybrid_runner_post_run_tile_new, 0);
  assertUnlocked(result);
}

async function testWriteOkAdvancesWhenIdsAlreadyListedInSnapshotSet(): Promise<void> {
  // Symptom: backend 130, UI Already 120 after write_ok_count=10.
  // Historical id lists already contained the written aweme ids (newlyAddedCount=0)
  // but queue items were still pending — advance by matchedQueueCount.
  const { storage, runtime, flushCalls } = await setup(20);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  const allIds = Array.from({ length: 20 }, (_, index) => awemeId(index + 1));
  const seeded: WholeProfileHarvestState = {
    ...before,
    // First 10 are already complete in the queue; ids 1-20 are listed in the
    // snapshot set (historical incomplete id list). Only the remaining 10
    // pending items are actionable — Hybrid drains all of them in one click.
    harvest: {
      ...before.harvest,
      queue: before.harvest.queue.map((item, index) => (
        index < 10
          ? { ...item, status: "already_collected" as const, capture_status: "complete" as const }
          : item
      )),
      pending: 10,
      processed: 10
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 20,
      backend_captured_aweme_ids: allIds,
      backend_captured: 10,
      backend_ready: 10,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 10,
      incomplete: 0,
      need_retry: 0,
      new: 10,
      queue: 10,
      applied_at: iso(0)
    },
    collect_job: {
      ...before.collect_job,
      job_id: "hybrid_collect_job",
      state: "starting",
      started_at: iso(1),
      updated_at: iso(1),
      heartbeat_at: iso(1),
      runner_ack_at: null,
      current_step: "starting",
      batch_limit: 10,
      selected_count: 10,
      runtime_generation: (before.collect_job.runtime_generation ?? 0) + 1,
      lock_owner: "hybrid_collect_job",
      lock_acquired_at: iso(1),
      lock_expires_at: iso(60),
      startup_deadline_at: iso(60),
      lock_released: false
    }
  };
  await writeWholeProfileHarvestState(storage, seeded);
  installVerifyFetch(() => [], []);

  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
  assert.equal(flushCalls.length, 1, "Phase 4.4e: write_ok batch uses one chunked flush");
  assert.equal(result.post_scan_counter_snapshot?.already_collected, 20, "write_ok must advance by matched queue items even when ids were already listed");
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(result.post_scan_counter_snapshot?.scanned_total, 20);
  assert.ok((result.post_scan_counter_snapshot?.already_collected ?? 0) + (result.post_scan_counter_snapshot?.new ?? 0) <= (result.post_scan_counter_snapshot?.scanned_total ?? 0));
}

async function testReconcileAdvancesWhenHistoricalIdSetIsIncomplete(): Promise<void> {
  // Reproduces UI stuck at 80 while backend shows 90: snapshot.already_collected=8
  // but backend_captured_aweme_ids only tracked 5 IDs. Writing all remaining pending
  // (12) must yield already_collected=20 (8+12), not max(8, idSet)=15.
  const { storage, runtime, flushCalls } = await setup(20);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  const partialIds = Array.from({ length: 5 }, (_, index) => awemeId(index + 1));
  const seededQueue = before.harvest.queue.map((item, index) => (
    index < 8
      ? {
          ...item,
          status: "already_collected" as const,
          capture_status: "complete" as const,
          profile_card_evidence: {
            ...item.profile_card_evidence,
            backend_reconciled: true,
            backend_reconciled_source: "seed_incomplete_id_set",
            backend_reconciled_at: iso(0)
          }
        }
      : item
  ));
  const seeded: WholeProfileHarvestState = {
    ...before,
    harvest: {
      ...before.harvest,
      queue: seededQueue,
      pending: 12,
      processed: 8
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 20,
      backend_captured_aweme_ids: partialIds,
      backend_captured: 8,
      backend_ready: 8,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 8,
      incomplete: 0,
      need_retry: 0,
      new: 12,
      queue: 12,
      applied_at: iso(0)
    },
    collect_job: {
      ...before.collect_job,
      job_id: "hybrid_collect_job",
      state: "starting",
      started_at: iso(1),
      updated_at: iso(1),
      heartbeat_at: iso(1),
      runner_ack_at: null,
      current_step: "starting",
      batch_limit: 10,
      selected_count: 10,
      runtime_generation: (before.collect_job.runtime_generation ?? 0) + 1,
      lock_owner: "hybrid_collect_job",
      lock_acquired_at: iso(1),
      lock_expires_at: iso(60),
      startup_deadline_at: iso(60),
      lock_released: false
    }
  };
  await writeWholeProfileHarvestState(storage, seeded);
  installVerifyFetch(() => partialIds, []);

  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { batch_limit: 10, mode: "new_and_incomplete" });
  assert.equal(flushCalls.length, 1, "Phase 4.4e: all remaining pending items flush in one chunk");
  assert.equal(result.post_scan_counter_snapshot?.already_collected, 20, "already_collected must advance by newly written count even when historical id set was incomplete");
  assert.equal(result.post_scan_counter_snapshot?.backend_captured, 20);
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(result.post_scan_counter_snapshot?.scanned_total, 20);
}

async function testLateHeartbeatCannotRegressPostRunTiles(): Promise<void> {
  // Production: fossil tile_already=61 / card 61 captured, popup Already=41.
  // A timed-out full-replace heartbeat carried the pre-run snapshot and landed
  // after post-run card refresh. Merge-only heartbeat + monotonic snapshot
  // write must keep Already at the card authority.
  const { storage } = await setup(138);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  const completed: WholeProfileHarvestState = {
    ...before,
    collect_job: {
      ...before.collect_job,
      job_id: "hybrid_collect_job",
      state: "completed",
      runtime_generation: 2,
      completed_at: iso(2),
      lock_owner: null,
      lock_expires_at: null,
      lock_released: true,
      updated_at: iso(2)
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 138,
      backend_captured_aweme_ids: Array.from({ length: 61 }, (_, index) => awemeId(index + 1)),
      backend_captured: 61,
      backend_ready: 61,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 61,
      incomplete: 0,
      need_retry: 0,
      new: 77,
      queue: 77,
      applied_at: iso(2)
    },
    debug: {
      ...before.debug,
      last_response_summary: {
        hybrid_collector_completed: "yes",
        hybrid_runner_post_run_tile_already: 61
      }
    },
    updated_at: iso(2)
  };
  await writeWholeProfileHarvestState(storage, completed);
  await storage.set({
    [HYBRID_COLLECTION_DONE_KEY]: {
      job_id: "hybrid_collect_job",
      runtime_generation: 2,
      completed_at: iso(2),
      outcome: "phase_4_4d_loop_completed",
      tile_already: 61,
      tile_new: 77,
      tile_queue: 77,
      scanned_total: 138
    }
  });

  const staleHeartbeat: WholeProfileHarvestState = {
    ...completed,
    collect_job: {
      ...completed.collect_job,
      state: "running",
      heartbeat_at: iso(1),
      current_step: "hybrid_loop_flushing",
      succeeded_count: 10,
      lock_owner: "hybrid_collect_job",
      lock_expires_at: iso(60),
      lock_released: false,
      completed_at: null,
      updated_at: iso(1)
    },
    active_collect_runtime: {
      ...completed.active_collect_runtime,
      job_id: "hybrid_collect_job",
      canonical_state: "running",
      current_step: "hybrid_loop_flushing",
      succeeded_count: 10,
      heartbeat_at: iso(1)
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 138,
      backend_captured_aweme_ids: Array.from({ length: 41 }, (_, index) => awemeId(index + 1)),
      backend_captured: 41,
      backend_ready: 41,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 41,
      incomplete: 0,
      need_retry: 0,
      new: 97,
      queue: 97,
      applied_at: iso(1)
    },
    updated_at: iso(1)
  };

  const afterHeartbeat = await writeHybridLoopHeartbeat(storage, staleHeartbeat);
  assert.equal(afterHeartbeat.collect_job.state, "completed", "heartbeat must not revive a completed job");
  assert.equal(afterHeartbeat.post_scan_counter_snapshot?.already_collected, 61, "heartbeat must not regress tile_already");
  assert.equal(afterHeartbeat.post_scan_counter_snapshot?.new, 77);

  const afterGuardedWrite = await writeWholeProfileHarvestState(storage, {
    ...staleHeartbeat,
    collect_job: { ...staleHeartbeat.collect_job, state: "completed", completed_at: iso(1) }
  });
  assert.equal(afterGuardedWrite.post_scan_counter_snapshot?.already_collected, 61, "monotonic write must keep higher already_collected");
  assert.equal(afterGuardedWrite.post_scan_counter_snapshot?.new, 77);
}

async function testDoneSignalRestoresTilesAfterMainStateClobber(): Promise<void> {
  // Popup read path: main state was clobbered to Already=41 but hybrid_collection_done
  // still carries card authority 61/77. Override must restore tiles and view model.
  const { storage } = await setup(138);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  const clobbered: WholeProfileHarvestState = {
    ...before,
    collect_job: {
      ...before.collect_job,
      job_id: "hybrid_collect_job",
      state: "completed",
      runtime_generation: 2,
      completed_at: iso(2),
      lock_owner: null,
      lock_expires_at: null,
      lock_released: true,
      updated_at: iso(2)
    },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 138,
      backend_captured_aweme_ids: [],
      backend_captured: 41,
      backend_ready: 41,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 41,
      incomplete: 0,
      need_retry: 0,
      new: 97,
      queue: 97,
      applied_at: iso(1)
    },
    debug: {
      ...before.debug,
      last_response_summary: {
        hybrid_collector_completed: "yes"
      }
    },
    updated_at: iso(2)
  };

  const restored = applyHybridCollectionDoneOverride(clobbered, {
    job_id: "hybrid_collect_job",
    runtime_generation: 2,
    completed_at: iso(2),
    outcome: "phase_4_4d_loop_completed",
    tile_already: 61,
    tile_new: 77,
    tile_queue: 77,
    scanned_total: 138
  });
  assert.equal(restored.post_scan_counter_snapshot?.already_collected, 61);
  assert.equal(restored.post_scan_counter_snapshot?.new, 77);
  assert.equal(restored.post_scan_counter_snapshot?.queue, 77);
  assert.equal(restored.post_scan_counter_snapshot?.scanned_total, 138);

  const viewModel = getScannerControlPanelViewModel(restored);
  assert.equal(viewModel.counts.alreadyCollectedCount, 61);
  assert.equal(viewModel.counts.newCount, 77);
  assert.equal(viewModel.counts.queueCount, 77);
  assert.match(viewModel.headerStatus, /61/);
}

async function testChunkedFlushRespectsFlushChunkSize(): Promise<void> {
  // Phase 4.4e: finalized items must be submitted in chunks of <= flush_chunk_size,
  // not one HTTP request per item (4.4d) and never above the 500 backend contract.
  const { storage, runtime, flushCalls } = await setup(10);
  const result = await runBatchCollectHybridNetworkCacheMode(runtime, {
    batch_limit: 10,
    mode: "new_and_incomplete",
    flush_chunk_size: 3
  });

  assert.equal(flushCalls.length, 4, "10 items with flush_chunk_size=3 must produce 4 chunk requests (3+3+3+1)");
  assert.deepEqual(flushCalls.map((call) => call.awemeIds.length), [3, 3, 3, 1]);
  assert.deepEqual(
    flushCalls.flatMap((call) => call.awemeIds),
    Array.from({ length: 10 }, (_, index) => awemeId(index + 1))
  );
  assert.equal(summary(result).hybrid_runner_flush_mode, "interleaved_chunked");
  assert.equal(summary(result).hybrid_runner_flush_chunk_limit, 3);
  assert.equal(summary(result).hybrid_runner_flush_chunk_count, 4);
  assert.equal(summary(result).hybrid_runner_flush_ready_count, 0);
  assert.equal(summary(result).hybrid_runner_write_ok_count, 10);
  assert.equal(result.post_scan_counter_snapshot?.already_collected, 10);
  assertUnlocked(result);

  // Hard cap: even if caller asks for >500, runner clamps to HYBRID_NETWORK_CACHE_MAX_BATCH_SIZE.
  flushCalls.length = 0;
  const { storage: storage2, runtime: runtime2, flushCalls: flushCalls2 } = await setup(10);
  const capped = await runBatchCollectHybridNetworkCacheMode(runtime2, {
    batch_limit: 10,
    mode: "new_and_incomplete",
    flush_chunk_size: 9999
  });
  assert.equal(flushCalls2.length, 1);
  assert.equal(summary(capped).hybrid_runner_flush_chunk_limit, 500);
  void storage;
  void storage2;
}

await testFullLoopWriteOkReconcilesQueueAndUnlocks();
await testSecondRunSkipsAlreadyCollectedAndFlushesNextBatch();
await testPreSkipAllCollectedReconcilesQueueAndUnlocks();
await testLargeProfilePreSkipUpdatesRepositoryAndCountersThenFlushesNextWindow();
await testStaleStartingWriteCannotClobberCompleted();
await testPreSkipDrainsBackendHitsThenWritesNextBatchInOneClick();
await testPreSkipDoesNotInflateAlreadyCollectedOrScannedTotal();
await testBatch2DoesNotFalseCompleteWhenBackendGapRemains();
await testPreSkipFailsWhenGapRemainsAndRepositoryCannotAdvance();
await testTailGapCollectRecoversMissingIdsFromBackendDiff();
await testLargeProfileTailGapUsesRepositoryWhenClassificationWindowed();
await testEnsureHarvestQueueReadyRebuildsHybridTailGap();
await testPostRunCardAuthorityOverridesLaggingLocalTiles();
await testWriteOkAdvancesWhenIdsAlreadyListedInSnapshotSet();
await testReconcileAdvancesWhenHistoricalIdSetIsIncomplete();
await testLateHeartbeatCannotRegressPostRunTiles();
await testDoneSignalRestoresTilesAfterMainStateClobber();
async function testMetricsMissingBatchIsAutoSkippedAndUnlocks(): Promise<void> {
  // Production: 997/999 with 2 New forever — both items only have profile_repository
  // IDs and no metrics. One Start Collecting must auto-skip them and clear the queue.
  const { storage, runtime, flushCalls } = await setup(2);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  const strippedQueue = before.harvest.queue.map((item) => ({
    ...item,
    profile_card_evidence: {
      aweme_id: item.aweme_id,
      source_url: item.source_url,
      profile_url: PROFILE_URL,
      discovery_source: "network_profile_post_22C11B"
    }
  }));
  await writeWholeProfileHarvestState(storage, {
    ...before,
    harvest: { ...before.harvest, queue: strippedQueue, pending: 2 },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 2,
      backend_captured_aweme_ids: [],
      backend_captured: 0,
      backend_ready: 0,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 0,
      incomplete: 0,
      need_retry: 0,
      new: 2,
      queue: 2,
      applied_at: iso(0)
    }
  });
  installVerifyFetch(() => [], []);

  const result = await runBatchCollectHybridNetworkCacheMode(runtime, { mode: "new_and_incomplete" });
  assert.equal(flushCalls.length, 0, "metrics-missing items must not be written");
  assert.equal(result.harvest.queue.every((item) => item.status === "skipped"), true);
  assert.equal(result.harvest.pending, 0);
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(summary(result).hybrid_runner_uncollectable_skipped_count, 2);
  assertUnlocked(result);
}

await testChunkedFlushRespectsFlushChunkSize();
await testMetricsMissingBatchIsAutoSkippedAndUnlocks();

async function testOperatorSkipHybridIncompleteRemainder(): Promise<void> {
  const { storage, runtime } = await setup(2);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  const strippedQueue = before.harvest.queue.map((item) => ({
    ...item,
    profile_card_evidence: {
      aweme_id: item.aweme_id,
      source_url: item.source_url,
      profile_url: PROFILE_URL,
      discovery_source: "network_profile_post_22C11B"
    }
  }));
  await writeWholeProfileHarvestState(storage, {
    ...before,
    harvest: { ...before.harvest, queue: strippedQueue, pending: 2 },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 999,
      backend_captured_aweme_ids: [],
      backend_captured: 997,
      backend_ready: 997,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 997,
      incomplete: 0,
      need_retry: 0,
      new: 2,
      queue: 2,
      applied_at: iso(0)
    },
    debug: {
      ...before.debug,
      last_response_summary: {
        ...(before.debug.last_response_summary as Record<string, unknown>),
        hybrid_runner_outcome: "phase_4_4c_write_pending",
        hybrid_runner_write_ok_count: 0,
        hybrid_runner_flush_ready_count: 0,
        hybrid_runner_per_item_count: 2
      }
    }
  });

  const result = await runSkipHybridUncollectableRemainder(runtime);
  assert.equal(result.harvest.queue.every((item) => item.status === "skipped"), true);
  assert.equal(result.harvest.pending, 0);
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(summary(result).hybrid_runner_operator_skip, "yes");
  assert.equal(summary(result).hybrid_runner_uncollectable_skipped_count, 2);
  assertUnlocked(result);
}

await testOperatorSkipHybridIncompleteRemainder();

async function testOperatorSkipHydratesLargeProfileRepositoryWindow(): Promise<void> {
  resetProfileTargetRepositoryForTests();
  const repository = new InMemoryProfileTargetRepository();
  setProfileTargetRepositoryFactoryForTests(() => repository);
  try {
    const profile = profileIdentifierFromUrl(PROFILE_URL);
    const pendingQueue = [makeQueueItem(awemeId(998), 998), makeQueueItem(awemeId(999), 999)];
    const pendingDetails = pendingQueue.map((item) => makeTargetDetail(item.aweme_id, item.index));
    await repository.upsertProfileTargets(profile, pendingQueue, pendingDetails, iso(0));

    const { storage, runtime } = await setup(999);
    const before = await readWholeProfileHarvestState(storage, iso(0));
    await writeWholeProfileHarvestState(storage, withLargeProfileWindow({
      ...before,
      harvest: { ...before.harvest, queue: [], queue_preview: [], pending: 2 },
      post_scan_counter_snapshot: {
        status: "applied",
        source: "backend_capture_inbox_profile_summary",
        profile_identifier: profile,
        scanned_total: 999,
        backend_captured_aweme_ids: [],
        backend_captured: 997,
        backend_ready: 997,
        backend_dup: 0,
        backend_fail: 0,
        already_collected: 997,
        incomplete: 0,
        need_retry: 0,
        new: 2,
        queue: 2,
        applied_at: iso(0)
      },
      debug: {
        ...before.debug,
        last_response_summary: {
          ...(before.debug.last_response_summary as Record<string, unknown>),
          hybrid_runner_outcome: "phase_4_4c_write_pending",
          hybrid_runner_write_ok_count: 0,
          hybrid_runner_flush_ready_count: 0,
          hybrid_runner_per_item_count: 2
        }
      }
    }, [], [], 999));

    const result = await runSkipHybridUncollectableRemainder(runtime);
    assert.equal(result.harvest.pending, 0);
    assert.equal(result.post_scan_counter_snapshot?.new, 0);
    assert.equal(result.post_scan_counter_snapshot?.queue, 0);
    assert.equal(summary(result).hybrid_runner_operator_skip, "yes");
    assert.equal(summary(result).hybrid_runner_uncollectable_skipped_count, 2);
    const skippedCounts = await repository.countProfileTargetsByStatus(profile);
    assert.equal(skippedCounts.counts.find((item) => item.status === "skipped")?.count, 2);
    assertUnlocked(result);
  } finally {
    resetProfileTargetRepositoryForTests();
  }
}

await testOperatorSkipHydratesLargeProfileRepositoryWindow();

async function testOperatorSkipUsesSnapshotAuthorityWhenQueueMissing(): Promise<void> {
  const { storage, runtime } = await setup(999);
  const before = await readWholeProfileHarvestState(storage, iso(0));
  await writeWholeProfileHarvestState(storage, withLargeProfileWindow({
    ...before,
    harvest: { ...before.harvest, queue: [], queue_preview: [], pending: 2 },
    post_scan_counter_snapshot: {
      status: "applied",
      source: "backend_capture_inbox_profile_summary",
      profile_identifier: "MS4wLjABAAAA-hybrid-regression",
      scanned_total: 999,
      backend_captured_aweme_ids: [],
      backend_captured: 997,
      backend_ready: 997,
      backend_dup: 0,
      backend_fail: 0,
      already_collected: 997,
      incomplete: 0,
      need_retry: 0,
      new: 2,
      queue: 2,
      applied_at: iso(0)
    },
    debug: {
      ...before.debug,
      last_response_summary: {
        ...(before.debug.last_response_summary as Record<string, unknown>),
        hybrid_runner_outcome: "phase_4_4c_write_pending",
        hybrid_runner_write_ok_count: 0,
        hybrid_runner_flush_ready_count: 0,
        hybrid_runner_per_item_count: 2
      }
    }
  }, [], [], 999));

  const result = await runSkipHybridUncollectableRemainder(runtime);
  assert.equal(result.post_scan_counter_snapshot?.new, 0);
  assert.equal(result.post_scan_counter_snapshot?.queue, 0);
  assert.equal(summary(result).hybrid_runner_operator_skip, "yes");
  assert.equal(summary(result).hybrid_runner_uncollectable_skipped_count, 2);
  assert.equal(summary(result).hybrid_runner_uncollectable_reason, "operator_skip_snapshot_authority");
  assertUnlocked(result);
}

await testOperatorSkipUsesSnapshotAuthorityWhenQueueMissing();

console.log("hybrid runner reconcile regression tests passed");
